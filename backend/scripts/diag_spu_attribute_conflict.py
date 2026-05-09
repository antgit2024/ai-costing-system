"""
诊断: 扫描所有 sku_code → 历史发货 spec_text → 命中模型分布。

输出：
- 命中 1 个模型的 SKU 数（正常）
- 命中 2/3/4+ 个模型的 SKU 数（"SPU 属性冲突" 候选）
- TOP-N 冲突 SKU 列表 + 命中分布

复用 shipment_import_service 里同源的反向索引（Tier A 模型级 + Tier B 变体级）。
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from typing import Dict, Set

sys.path.insert(0, ".")

from src.database import SessionLocal
from src.planner import models
from sqlalchemy import func


def build_keyword_to_models(db) -> Dict[str, Set[str]]:
    kw_owners: Dict[str, Set[str]] = {}

    # Tier A: 模型级
    rows = (
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
    for m in rows:
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

    return kw_owners


def main() -> None:
    db = SessionLocal()
    print("=== 构建关键词 → 模型反向索引 ...")
    kw_owners_all = build_keyword_to_models(db)
    print(f"    共 {len(kw_owners_all)} 个关键词，覆盖 {len({m for s in kw_owners_all.values() for m in s})} 个模型")

    # 模型 ID → model_code 映射，便于打印
    mid_to_code = {
        str(m.id): m.model_code
        for m in db.query(models.ProductModel.id, models.ProductModel.model_code).all()
    }

    # 打印关键词→模型清单，看是否有共享关键词造成假冲突
    print()
    print("=== 关键词 → 模型清单 (★=共享关键词，会被排除) ===")
    for kw, mids in sorted(kw_owners_all.items()):
        codes = sorted(mid_to_code.get(m, m[:8]) for m in mids)
        marker = "★" if len(mids) > 1 else " "
        print(f"    {marker} {kw!s:20s} → {codes}")

    # 只保留"独占关键词"（一个关键词只属于一个模型）做命中判定
    # 共享关键词（如"枕套"既在 YS2 也在 PI5 里）不能作为冲突判定依据
    kw_owners = {kw: mids for kw, mids in kw_owners_all.items() if len(mids) == 1}
    excluded = len(kw_owners_all) - len(kw_owners)
    print()
    print(f"=== 排除 {excluded} 个共享关键词后，剩 {len(kw_owners)} 个独占关键词 ===")

    import os
    only_real_orders = os.getenv("ONLY_REAL_ORDERS", "1") == "1"
    print()
    if only_real_orders:
        print("=== 扫描发货行 (只算有真实 ERP/平台订单号的，过滤 Excel 测试导入) ...")
    else:
        print("=== 扫描所有发货行的 spec_text (含 Excel 历史导入)...")
    # 一次性把所有发货行拉出来分组。数据量大不大都不要紧，这是离线诊断脚本。
    q = (
        db.query(
            models.ShipmentLine.sku_code,
            models.ShipmentLine.spec_text,
            func.count("*").label("cnt"),
        )
        .filter(models.ShipmentLine.is_archived.is_(False))
        .filter(models.ShipmentLine.sku_code.isnot(None))
        .filter(models.ShipmentLine.spec_text.isnot(None))
    )
    if only_real_orders:
        from sqlalchemy import or_, and_
        q = q.filter(
            or_(
                and_(
                    models.ShipmentLine.erp_order_no.isnot(None),
                    models.ShipmentLine.erp_order_no != "",
                ),
                and_(
                    models.ShipmentLine.platform_order_no.isnot(None),
                    models.ShipmentLine.platform_order_no != "",
                ),
            )
        )
    rows = q.group_by(models.ShipmentLine.sku_code, models.ShipmentLine.spec_text).all()
    print(f"    共 {len(rows)} 条 (sku_code, spec_text) 唯一组合")

    # 对每个 (sku, spec_text variant) 单独算一个"主命中模型"——
    # 主命中模型 = 独占关键词命中数最多的那个模型（无命中则跳过）。
    # 然后按 SKU 看有没有 ≥ 2 个 variant 分别命中不同主模型。
    MIN_VARIANT_LINES = 2   # variant 至少 N 条发货行才参与冲突判定（过滤偶发噪声）
    sku_to_variants: Dict[str, list] = defaultdict(list)  # sku → [(spec, cnt, top_model_id)]
    sku_to_total: Counter = Counter()

    for sku, spec, cnt in rows:
        sku_to_total[sku] += cnt
        if not spec or cnt < MIN_VARIANT_LINES:
            sku_to_variants[sku].append((spec, cnt, None))
            continue
        spec_lower = spec.lower()
        per_model_hits: Counter = Counter()
        for kw, mids in kw_owners.items():
            if kw.lower() in spec_lower:
                # 每个独占关键词只属于一个模型
                for mid in mids:
                    per_model_hits[mid] += 1
        if per_model_hits:
            top_mid = per_model_hits.most_common(1)[0][0]
            sku_to_variants[sku].append((spec, cnt, top_mid))
        else:
            sku_to_variants[sku].append((spec, cnt, None))

    # 判定冲突：variant 命中模型集合的 distinct 数 ≥ 2
    # 且 第二高模型在该 SKU 内的发货占比 ≥ MIN_SECONDARY_RATIO （过滤"几乎单一模型 + 噪声"）
    MIN_SECONDARY_RATIO = 0.05  # 次模型至少 5% 才算真有"两类"

    def model_share(vlist):
        """汇总 sku 内每个模型的发货数; 返回 [(mid, cnt), ...] 倒序"""
        c = Counter()
        for _spec, cnt, mid in vlist:
            if mid:
                c[mid] += cnt
        return c.most_common()

    print()
    print("=== 按 variant 命中模型分布 ===")
    bucket = Counter()
    sku_to_share: Dict[str, list] = {}
    for sku, vlist in sku_to_variants.items():
        share = model_share(vlist)
        sku_to_share[sku] = share
        bucket[len(share)] += 1
    for n in sorted(bucket.keys()):
        label = "无变体命中" if n == 0 else f"variant 命中 {n} 个模型"
        print(f"    {label:24s}: {bucket[n]:6d} 个 SKU")

    # 过滤：第二高模型占比 ≥ 5%
    conflict_strict = []
    for sku in sku_to_total:
        share = sku_to_share.get(sku) or []
        if len(share) < 2:
            continue
        total = sku_to_total[sku]
        if total <= 0:
            continue
        secondary_ratio = share[1][1] / total
        if secondary_ratio < MIN_SECONDARY_RATIO:
            continue
        conflict_strict.append((sku, total, share, secondary_ratio))

    conflict_strict.sort(key=lambda x: -x[1])

    print()
    print(f"=== 加上次模型 >= {int(MIN_SECONDARY_RATIO*100)}% 后真冲突 SKU 总数: {len(conflict_strict)} ===")
    total_lines = sum(t for _, t, _, _ in conflict_strict)
    print(f"=== 涉及发货行数: {total_lines} ===")

    print()
    print("=== TOP 40 真冲突 SKU ===")
    for sku, total, share, secondary_ratio in conflict_strict[:40]:
        parts = []
        for mid, cnt in share:
            code = mid_to_code.get(mid) or mid[:8]
            pct = 100 * cnt / total
            parts.append(f"{code}={cnt}({pct:.0f}%)")
        print(f"    sku={sku:20s} total={total:5d} share=[{', '.join(parts)}]")

    print()
    print("=== 冲突 SKU 按命中模型数 细分 ===")
    by_n = Counter()
    by_n_total_lines = Counter()
    for sku, total, share, _r in conflict_strict:
        n = len(share)
        by_n[n] += 1
        by_n_total_lines[n] += total
    for n in sorted(by_n.keys()):
        print(f"    命中 {n} 个模型: {by_n[n]:5d} SKU, 涉及 {by_n_total_lines[n]:7d} 条发货行")

    # === 规则 2: 高变异 SKU ===
    # spec_text 唯一数 >= N，且每个 spec 都至少有 K 条发货（过滤偶发拼写差异）
    # 用于捕捉"未建模品类"之间的冲突（如装饰画/油画/桌布/拉门交叉）
    # 豁免: 如果该 SKU 所有 variant 命中的模型全部一致（同一主模型），
    # 则信任主模型，不算冲突（用户原话："以实际发货为主"）
    SPEC_DIVERSITY_THRESHOLD = 3   # >= 3 个不同 spec 才算
    MIN_SPEC_LINES = 2             # 每个 spec 至少 2 条

    sku_to_spec_count: Dict[str, int] = defaultdict(int)
    sku_to_keyword_models: Dict[str, set] = defaultdict(set)
    sku_to_unmatched_specs: Dict[str, int] = defaultdict(int)
    for sku, vlist in sku_to_variants.items():
        sku_to_spec_count[sku] = sum(
            1 for _spec, cnt, _mid in vlist if cnt >= MIN_SPEC_LINES
        )
        for _spec, cnt, mid in vlist:
            if cnt < MIN_SPEC_LINES:
                continue
            if mid:
                sku_to_keyword_models[sku].add(mid)
            else:
                sku_to_unmatched_specs[sku] += 1

    high_diversity = []
    for sku in sku_to_total:
        n_specs = sku_to_spec_count[sku]
        if n_specs < SPEC_DIVERSITY_THRESHOLD:
            continue
        # 豁免：所有变体都命中了关键词 + 都指向同一模型（信任主模型）
        # 只要有 1 个 variant 没命中任何关键词，说明该品类未建模 → 不能豁免
        if (
            len(sku_to_keyword_models[sku]) == 1
            and sku_to_unmatched_specs[sku] == 0
        ):
            continue
        high_diversity.append(
            (sku, sku_to_total[sku], n_specs, sku_to_unmatched_specs[sku], sku_to_keyword_models[sku])
        )
    high_diversity.sort(key=lambda x: -x[2])

    print()
    print(f"=== 规则 2: spec_text >= {SPEC_DIVERSITY_THRESHOLD} 个不同(每个 >= {MIN_SPEC_LINES} 条) 的 SKU 数: {len(high_diversity)} ===")
    print("=== TOP 30 高变异 SKU (含未识别 spec 数 + 已识别模型) ===")
    for sku, total, n_specs, unmatched, mids in high_diversity[:30]:
        codes = sorted(mid_to_code.get(m, m[:8]) for m in mids)
        print(f"    sku={sku:20s} total={total:5d} specs={n_specs} unmatched={unmatched} models={codes}")

    # === 综合：rule1 OR rule2 ===
    rule1_set = {x[0] for x in conflict_strict}
    rule2_set = {x[0] for x in high_diversity}
    union = rule1_set | rule2_set
    intersection = rule1_set & rule2_set
    print()
    print(f"=== 综合（rule1 OR rule2）: {len(union)} SKU ===")
    print(f"    rule1 only: {len(rule1_set - rule2_set)}")
    print(f"    rule2 only: {len(rule2_set - rule1_set)}")
    print(f"    both:       {len(intersection)}")
    print()
    print("=== 用户案例 5970014255535 是否被检出？ ===")
    sku = "5970014255535"
    print(f"    rule1: {sku in rule1_set}")
    print(f"    rule2: {sku in rule2_set}")
    print(f"    distinct_specs={sku_to_spec_count.get(sku)}, total={sku_to_total.get(sku)}")

    db.close()


if __name__ == "__main__":
    main()
