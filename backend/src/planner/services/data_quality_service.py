"""SKU 数据质量检测服务。

目前只负责一件事：识别"SPU 属性冲突 SKU"——
即同一个 ``erp_sku_barcode`` 在历史发货里承载了多个完全不同
的商品（比如同一条码既卖装饰画又卖枕套又卖地毯）。这种 SKU
ERP 端绑定混乱、实际发货 spec 多样性极高，**任何自动绑定/算
法路由都不可信**，需要在 UI 上隔离标识，让运营介入清理。

判定规则（双信号 OR）：

  R1 关键词冲突
    --------------
    复用 ``shipment_import_service`` 里那一套 ``recognition_keywords``
    反向索引（模型级 + 变体级）。对该 SKU 的每条 (spec_text, qty)
    分组，按"独占关键词"命中累加各模型权重。如果次模型在该 SKU
    总命中里占比 >= 5%（去掉"主模型 99% + 次模型 0.7%"这种噪声），
    且至少有 2 个不同模型被显著命中，就算 R1 命中。
    场景：能用建好的关键词捕捉的"已知品类间冲突"。

  R2 高变异规格
    --------------
    该 SKU 的发货里出现 >= 3 个不同的 spec_text（每个至少 2 条），
    且不全部豁免（豁免条件：所有 variant 都命中关键词且都指向
    同一个模型——这种情况下"以实际发货为主"信任主模型）。
    场景：捕捉"未建模品类"之间的冲突——比如装饰画/油画/拉门
    没有 recognition_keywords，但 SKU 的 spec 显著跨品类。

写入位置（``SkuMaster.metadata``）：

  ``data_quality_status``     str | None
      ``"spu_attribute_conflict"`` 或 ``None``。
  ``data_quality_evidence``   dict | None
      详细证据（命中规则 / 模型 share / 变体清单等），UI 渲染用。
  ``data_quality_evaluated_at`` ISO 时间戳

任何 unbind / bind / 手动绑定时都**保留**该字段——它代表的是
"历史发货的客观事实"，不随绑定变化。只有 nightly 重算或
手动 recompute 才会刷新。

设计取舍：
  - 不自动解绑：mark_only 模式。绑定不变，仅 UI 红 Tag 提示，
    成本/盈亏报表照常计算（用户决定后续是否升级到自动解绑）。
  - nightly 跑一次：跟现有 BOM 快照定时任务一起调度。
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .. import models

logger = logging.getLogger(__name__)


# ============================================================================
# 阈值（保持和 diag_spu_attribute_conflict.py 脚本一致）
# ============================================================================

# R1: 次模型占该 SKU 总命中数的最小比例 — 低于此值视作噪声
R1_MIN_SECONDARY_RATIO = 0.05

# R2: 发货 spec_text 唯一数下限
R2_SPEC_DIVERSITY_THRESHOLD = 3

# R2/R1: 单个 (sku, spec_text) 至少出现的发货行数 — 过滤偶发拼写差异
MIN_SPEC_LINES = 2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _real_order_filter():
    """SQL 过滤：只保留有真实 ERP/平台订单号的发货行。

    历史背景（2026-05-09）：测试期间运营手工导入了大量 Excel 历史回测
    数据，这些行没有 ``erp_order_no`` / ``platform_order_no``。如果把它们
    当成真实业务来做"SPU 错配"判定，会大量误报（同一 sku_code 的 Excel
    历史行可能跨多个商品规格——往往是测试 / 老映射 / 平台混乱）。

    这里只信任来自 ERP 同步（吉客云）或带平台订单号的行——这些行才是
    "当下 ERP 端对该条码的真实认知"。
    """
    return or_(
        and_(
            models.ShipmentLine.erp_order_no.isnot(None),
            models.ShipmentLine.erp_order_no != "",
        ),
        and_(
            models.ShipmentLine.platform_order_no.isnot(None),
            models.ShipmentLine.platform_order_no != "",
        ),
    )


# ============================================================================
# 反向索引：keyword → set(model_id)
# ============================================================================

def build_keyword_to_models(db: Session) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    """构建 (kw → model_ids) 反向索引。

    数据源：
      - 模型级 ``ProductModel.metadata.recognition_keywords``
      - 变体级 ``ProductModelLineVariant.conditions_json.spec_contains_all/any``
        （跳过 ``MODEL:xxx`` / ``ATTR:xxx`` 这类系统注入 token）

    Returns: ``(kw_owners, mid_to_code)``
      - ``kw_owners[keyword]`` = set of model_id
      - ``mid_to_code[model_id]`` = model_code（UI 渲染用）
    """
    kw_owners: Dict[str, Set[str]] = {}

    # Tier A: 模型级
    pm_rows = (
        db.query(models.ProductModel)
        .join(
            models.ProductModelVersion,
            models.ProductModelVersion.model_id == models.ProductModel.id,
        )
        .filter(
            models.ProductModel.is_archived.is_(False),
            models.ProductModelVersion.is_archived.is_(False),
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
        )
        .all()
    )
    for m in pm_rows:
        meta = m.metadata_json or {}
        kws = meta.get("recognition_keywords") if isinstance(meta, dict) else None
        if not isinstance(kws, list):
            continue
        for k in kws:
            ks = str(k or "").strip()
            if not ks:
                continue
            kw_owners.setdefault(ks, set()).add(str(m.id))

    # Tier B: 变体级
    version_to_model = {
        str(v.id): str(v.model_id)
        for v in (
            db.query(models.ProductModelVersion.id, models.ProductModelVersion.model_id)
            .filter(
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModelVersion.version_kind == "standard",
                models.ProductModelVersion.version_status == "published",
            )
            .all()
        )
    }
    if version_to_model:
        variants = (
            db.query(
                models.ProductModelLineVariant.version_id,
                models.ProductModelLineVariant.conditions_json,
            )
            .filter(
                models.ProductModelLineVariant.is_archived.is_(False),
                models.ProductModelLineVariant.version_id.in_(list(version_to_model.keys())),
            )
            .all()
        )
        for ver_id, cond in variants:
            if not isinstance(cond, dict):
                continue
            mid = version_to_model.get(str(ver_id))
            if not mid:
                continue
            for ck in ("spec_contains_all", "spec_contains_any"):
                tokens = cond.get(ck) or []
                if not isinstance(tokens, list):
                    continue
                for tok in tokens:
                    ts = str(tok or "").strip()
                    if not ts or ":" in ts:
                        continue
                    kw_owners.setdefault(ts, set()).add(mid)

    mid_to_code = {
        str(m.id): m.model_code
        for m in db.query(models.ProductModel.id, models.ProductModel.model_code).all()
    }

    return kw_owners, mid_to_code


# ============================================================================
# 单 SKU 评估
# ============================================================================

def _evaluate_one_sku(
    *,
    sku_code: str,
    spec_rows: List[Tuple[str, int]],
    kw_owners_exclusive: Dict[str, Set[str]],
    mid_to_code: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """评估单个 sku_code 是否构成 SPU 属性冲突。

    Args:
      sku_code: ERP 货品条码
      spec_rows: ``[(spec_text, count), ...]`` — 该 SKU 的所有发货按 spec 分组
      kw_owners_exclusive: 独占关键词反向索引（已排除多模型共享的关键词）
      mid_to_code: model_id → model_code

    Returns:
      None 表示不是冲突 SKU；
      dict 是 ``data_quality_evidence`` 的内容（UI 直接用）。
    """
    if not spec_rows:
        return None

    total_lines = sum(c for _, c in spec_rows)
    if total_lines <= 0:
        return None

    # 每条 (spec, cnt) 找出独占关键词命中的模型集合
    # 然后选 most_common 作为该 variant 的"主命中模型"
    per_model_lines: Counter = Counter()  # 模型 → 累计发货行数
    variant_summaries: List[Dict[str, Any]] = []

    distinct_specs = 0
    unmatched_specs = 0
    keyword_matched_models: Set[str] = set()

    for spec, cnt in spec_rows:
        if cnt < MIN_SPEC_LINES:
            # 偶发噪声，仍计入 per_model_lines 但不计入 distinct_specs / variant_summaries
            spec_lower = (spec or "").lower()
            tmp_hits: Counter = Counter()
            for kw, mids in kw_owners_exclusive.items():
                if kw and kw.lower() in spec_lower:
                    for mid in mids:
                        tmp_hits[mid] += 1
            if tmp_hits:
                top_mid = tmp_hits.most_common(1)[0][0]
                per_model_lines[top_mid] += cnt
            continue

        distinct_specs += 1
        spec_lower = (spec or "").lower()
        per_kw_hits: Counter = Counter()
        for kw, mids in kw_owners_exclusive.items():
            if kw and kw.lower() in spec_lower:
                for mid in mids:
                    per_kw_hits[mid] += 1

        if per_kw_hits:
            top_mid = per_kw_hits.most_common(1)[0][0]
            per_model_lines[top_mid] += cnt
            keyword_matched_models.add(top_mid)
            variant_summaries.append({
                "spec": spec,
                "qty": cnt,
                "top_model_code": mid_to_code.get(top_mid),
            })
        else:
            unmatched_specs += 1
            variant_summaries.append({
                "spec": spec,
                "qty": cnt,
                "top_model_code": None,
            })

    # ----- R1: 关键词冲突（次模型占比 >= 5%） -----
    r1_hit = False
    r1_share: List[Dict[str, Any]] = []
    if len(per_model_lines) >= 2:
        share_ranked = per_model_lines.most_common()
        secondary_ratio = share_ranked[1][1] / total_lines
        if secondary_ratio >= R1_MIN_SECONDARY_RATIO:
            r1_hit = True
        # 不管是否命中 R1，都把 share 算出来给 UI 展示
        r1_share = [
            {
                "model_code": mid_to_code.get(mid) or mid[:8],
                "lines": cnt,
                "ratio": round(cnt / total_lines, 4),
            }
            for mid, cnt in share_ranked
        ]

    # ----- R2: 高变异规格 -----
    r2_hit = False
    r2_exempt = False
    if distinct_specs >= R2_SPEC_DIVERSITY_THRESHOLD:
        # 豁免：所有 variant 都命中了关键词 + 都指向同一个模型
        if len(keyword_matched_models) == 1 and unmatched_specs == 0:
            r2_exempt = True
        else:
            r2_hit = True

    if not r1_hit and not r2_hit:
        return None

    # 拼装 evidence — 留 TOP 6 variant 给 UI 展示（避免 metadata 暴涨）
    variant_summaries.sort(key=lambda x: -int(x.get("qty") or 0))
    return {
        "version": 1,
        "rules_hit": [r for r, hit in [("R1", r1_hit), ("R2", r2_hit)] if hit],
        "total_lines": total_lines,
        "distinct_specs": distinct_specs,
        "unmatched_specs": unmatched_specs,
        "keyword_matched_models": sorted(
            mid_to_code.get(m) or m[:8] for m in keyword_matched_models
        ),
        "model_share": r1_share,                       # R1 评估细节
        "top_variants": variant_summaries[:6],         # UI 展示用
        "r2_exempt_due_to_single_model": r2_exempt,    # 调试观测用
    }


# ============================================================================
# 全库批量评估 + 落库
# ============================================================================

def recompute_all(
    db: Session,
    *,
    lookback_days: int = 90,
    dry_run: bool = False,
    only_with_real_order: bool = True,
    clear_stale_for_skus_without_real_data: bool = False,
) -> Dict[str, Any]:
    """扫描全库，重新评估所有 SkuMaster 的"SPU 属性冲突"状态。

    nightly 任务和一次性回填脚本都用这个入口。

    Args:
      lookback_days: 只看最近 N 天的发货行（默认 90）。设 0 表示全部历史。
      dry_run: True 时只算不落库，方便上线前预演。
      only_with_real_order: 默认 True — 只用有真实 erp_order_no/platform_order_no
        的发货行（吉客云同步），过滤掉测试期间 Excel 灌的历史回测数据。
        设 False 会把 Excel 历史也算进去（容易大量误报）。
      clear_stale_for_skus_without_real_data:
        True 时，对那些"之前被打过 spu_attribute_conflict 标记、本次扫描却扫不
        到（即 lookback 范围内没有真实订单）"的 SKU 也强制清掉旧标记。
        用于规则切换 / 一次性回填，给运营一个干净的起点。
        nightly 任务不要开（沉默 SKU 维持现状即可）。

    Returns: 统计 dict
    """
    started_at = _utcnow()
    logger.info(
        "[data_quality.recompute_all] start lookback_days=%s dry_run=%s only_with_real_order=%s",
        lookback_days, dry_run, only_with_real_order,
    )

    # 1. 反向索引
    kw_owners_all, mid_to_code = build_keyword_to_models(db)
    # 只保留独占关键词（一个 kw 只属于一个模型）
    kw_owners_exclusive = {kw: mids for kw, mids in kw_owners_all.items() if len(mids) == 1}
    excluded_shared = len(kw_owners_all) - len(kw_owners_exclusive)
    logger.info(
        "[data_quality.recompute_all] keyword index: %s total, %s shared excluded, %s exclusive",
        len(kw_owners_all), excluded_shared, len(kw_owners_exclusive),
    )

    # 2. 拉发货行 ── 按 sku_code, spec_text 分组聚合 count
    q = db.query(
        models.ShipmentLine.sku_code,
        models.ShipmentLine.spec_text,
        func.count("*").label("cnt"),
    ).filter(
        models.ShipmentLine.is_archived.is_(False),
        models.ShipmentLine.sku_code.isnot(None),
    )
    if only_with_real_order:
        q = q.filter(_real_order_filter())
    if lookback_days and lookback_days > 0:
        cutoff = _utcnow() - timedelta(days=lookback_days)
        q = q.filter(models.ShipmentLine.completed_at >= cutoff)
    rows = q.group_by(
        models.ShipmentLine.sku_code,
        models.ShipmentLine.spec_text,
    ).all()
    logger.info(
        "[data_quality.recompute_all] loaded %s (sku, spec) groups", len(rows),
    )

    # 3. 按 sku_code 聚合 spec_rows
    sku_to_specs: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for sku, spec, cnt in rows:
        sku_to_specs[str(sku)].append((spec or "", int(cnt)))

    # 4. 拉所有 SkuMaster 一次（按 erp_sku_barcode index）
    sm_rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.is_archived.is_(False))
        .all()
    )
    barcode_to_sm: Dict[str, models.SkuMaster] = {}
    for sm in sm_rows:
        if sm.erp_sku_barcode:
            barcode_to_sm[str(sm.erp_sku_barcode)] = sm

    # 5. 评估
    flagged = 0
    cleared = 0
    unchanged = 0
    skipped_no_master = 0
    flagged_examples: List[Dict[str, Any]] = []

    # 5a. 所有"被发货过 + 在 sku_master 里有记录"的 SKU
    seen_sm_ids: Set[str] = set()
    for sku_code, spec_rows in sku_to_specs.items():
        sm = barcode_to_sm.get(sku_code)
        if sm is None:
            skipped_no_master += 1
            continue
        seen_sm_ids.add(str(sm.id))
        evidence = _evaluate_one_sku(
            sku_code=sku_code,
            spec_rows=spec_rows,
            kw_owners_exclusive=kw_owners_exclusive,
            mid_to_code=mid_to_code,
        )
        meta = dict(sm.metadata_json or {})
        prev_status = meta.get("data_quality_status")
        if evidence is not None:
            meta["data_quality_status"] = "spu_attribute_conflict"
            meta["data_quality_evidence"] = evidence
            meta["data_quality_evaluated_at"] = _utcnow().isoformat()
            if prev_status != "spu_attribute_conflict":
                flagged += 1
                if len(flagged_examples) < 10:
                    flagged_examples.append({
                        "sku_code": sku_code,
                        "rules_hit": evidence.get("rules_hit"),
                        "distinct_specs": evidence.get("distinct_specs"),
                        "models": evidence.get("keyword_matched_models"),
                    })
            else:
                unchanged += 1
        else:
            if prev_status == "spu_attribute_conflict":
                # 之前标记过、现在不再命中 → 清除
                meta.pop("data_quality_status", None)
                meta.pop("data_quality_evidence", None)
                meta["data_quality_evaluated_at"] = _utcnow().isoformat()
                cleared += 1
            else:
                # 一直没命中，只更新评估时间戳
                meta["data_quality_evaluated_at"] = _utcnow().isoformat()
                unchanged += 1
        if not dry_run:
            sm.metadata_json = meta
            flag_modified(sm, "metadata_json")

    # 5b. 那些"在 sku_master 里、但本次扫描未涉及（lookback 内无真实订单发货）"的：
    #   - nightly 默认保留旧标记（沉默 SKU 维持现状），
    #   - 一次性回填可以打开 clear_stale_for_skus_without_real_data 强制清掉，
    #     用于规则切换后给运营一个干净起点。
    cleared_stale = 0
    if clear_stale_for_skus_without_real_data:
        for sm in sm_rows:
            if str(sm.id) in seen_sm_ids:
                continue
            meta = sm.metadata_json or {}
            if not isinstance(meta, dict):
                continue
            if meta.get("data_quality_status") != "spu_attribute_conflict":
                continue
            new_meta = dict(meta)
            new_meta.pop("data_quality_status", None)
            new_meta.pop("data_quality_evidence", None)
            new_meta["data_quality_evaluated_at"] = _utcnow().isoformat()
            cleared_stale += 1
            if not dry_run:
                sm.metadata_json = new_meta
                flag_modified(sm, "metadata_json")

    if not dry_run:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    finished_at = _utcnow()
    stats = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": round((finished_at - started_at).total_seconds(), 2),
        "lookback_days": lookback_days,
        "dry_run": dry_run,
        "only_with_real_order": only_with_real_order,
        "clear_stale_for_skus_without_real_data": clear_stale_for_skus_without_real_data,
        "keyword_total": len(kw_owners_all),
        "keyword_shared_excluded": excluded_shared,
        "keyword_exclusive": len(kw_owners_exclusive),
        "shipment_groups": len(rows),
        "sku_evaluated": len(seen_sm_ids),
        "flagged_new": flagged,
        "cleared": cleared,
        "cleared_stale": cleared_stale,
        "unchanged": unchanged,
        "skipped_no_master": skipped_no_master,
        "flagged_examples": flagged_examples,
    }
    logger.info("[data_quality.recompute_all] done: %s", stats)
    return stats


def detect_for_one_sku(
    db: Session,
    *,
    sku_master_id: str,
    lookback_days: int = 90,
    persist: bool = True,
    only_with_real_order: bool = True,
) -> Optional[Dict[str, Any]]:
    """为单条 SKU 重算（运营在主档详情页"重新评估"按钮调用）。

    Returns: evidence dict 或 None
    """
    sm = db.query(models.SkuMaster).filter(models.SkuMaster.id == str(sku_master_id)).first()
    if not sm or not sm.erp_sku_barcode:
        return None

    sku = str(sm.erp_sku_barcode)
    kw_owners_all, mid_to_code = build_keyword_to_models(db)
    kw_owners_exclusive = {kw: mids for kw, mids in kw_owners_all.items() if len(mids) == 1}

    q = db.query(
        models.ShipmentLine.spec_text,
        func.count("*").label("cnt"),
    ).filter(
        models.ShipmentLine.is_archived.is_(False),
        models.ShipmentLine.sku_code == sku,
    )
    if only_with_real_order:
        q = q.filter(_real_order_filter())
    if lookback_days and lookback_days > 0:
        cutoff = _utcnow() - timedelta(days=lookback_days)
        q = q.filter(models.ShipmentLine.completed_at >= cutoff)
    rows = q.group_by(models.ShipmentLine.spec_text).all()
    spec_rows = [(r.spec_text or "", int(r.cnt)) for r in rows]

    evidence = _evaluate_one_sku(
        sku_code=sku,
        spec_rows=spec_rows,
        kw_owners_exclusive=kw_owners_exclusive,
        mid_to_code=mid_to_code,
    )

    if persist:
        meta = dict(sm.metadata_json or {})
        if evidence is not None:
            meta["data_quality_status"] = "spu_attribute_conflict"
            meta["data_quality_evidence"] = evidence
        else:
            meta.pop("data_quality_status", None)
            meta.pop("data_quality_evidence", None)
        meta["data_quality_evaluated_at"] = _utcnow().isoformat()
        sm.metadata_json = meta
        flag_modified(sm, "metadata_json")
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return evidence
