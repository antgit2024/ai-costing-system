from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, joinedload

from .. import models
from . import bom_generation_service, product_model_service, spec_parser_service
from . import bundle_template_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    """
    Ensure JSON-serializable payloads for JSON columns (metadata_json / SpecParseSnapshot JSON fields).
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def _norm_str(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    s = str(value).strip()
    return s or None


def _parse_excel_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = from_excel(value)
        except Exception:  # noqa: BLE001
            return None
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                dt = None  # type: ignore[assignment]
        if dt is None:
            try:
                dt = datetime.fromisoformat(raw)
            except Exception:  # noqa: BLE001
                return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_header_index(header_row: Tuple[Any, ...]) -> Dict[str, int]:
    idx: Dict[str, int] = {}
    for i, cell in enumerate(header_row):
        name = _norm_str(cell)
        if not name:
            continue
        idx[name] = i
    return idx


def _get(row: Tuple[Any, ...], headers: Dict[str, int], name: str) -> Any:
    i = headers.get(name)
    if i is None:
        return None
    if i < 0 or i >= len(row):
        return None
    return row[i]


ALLOWED_COLUMNS = {
    "规格图片（网店）",
    "销售渠道",
    "商品名称（网店）",
    "商品编码（网店）",
    "商品图片（网店）",
    "商品规格（网店）",
    "货品规格（系统）",
    "规格编码（网店）",
    "平台商品Id（网店）",
    "平台规格Id（网店）",
    "匹配状态",
    "货品条码（系统）",
    "最后更新时间",
    "匹配方式",
    # 可选：若ERP侧后续新增/开放该列，用于回写生产工艺
    "生产工艺",
    # 兼容旧列名（用户更正前的写法）
    "生产工艺注",
}

PARSER_VERSION = "v1"


def _sha1_text(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()  # noqa: S324 - idempotency/cache key


def _ensure_spec_parse_snapshot(
    db: Session,
    *,
    spec_hash: str,
    spec_text: str,
    parsed: Dict[str, Any],
) -> None:
    """
    Best-effort, idempotent insert for SpecParseSnapshot(spec_hash UNIQUE).
    Avoid 500s caused by concurrent inserts of the same spec_hash.
    """
    if not spec_hash or not spec_text:
        return
    dimensions0 = {
        "width_cm": parsed.get("width_cm"),
        "height_cm": parsed.get("height_cm"),
        "diameter_cm": parsed.get("diameter_cm"),
        "area_m2": parsed.get("area_m2"),
        "perimeter_m": parsed.get("perimeter_m"),
    }
    snap = models.SpecParseSnapshot(
        spec_hash=spec_hash,
        spec_text=spec_text,
        tokens_json=list(parsed.get("tokens") or []),
        dimensions_json=_json_safe(dimensions0),
        parser_version=PARSER_VERSION,
        parse_json=_json_safe(parsed),
    )
    # Use a nested transaction so a UNIQUE conflict won't poison the outer transaction.
    try:
        with db.begin_nested():
            db.add(snap)
            db.flush()
    except IntegrityError:
        # Someone else inserted the same spec_hash concurrently. Ignore.
        try:
            db.rollback()
        except Exception:
            pass


def _extract_model_code_hint(spec_text: Optional[str]) -> Optional[str]:
    """
    MVP: try extract model_code from spec_text leading token.
    Supported patterns (safe/low false-positive):
    - 3-char code: "A1B;..." / "024;..." / "K7Q；..."
    - token with leading 3 digits: "024画框;..." -> "024"
    - longer PM-prefixed code: "PM001;..." (kept for compatibility)
    - structured variant code: "KB8-001" / "KB8-MG" / "KB8-001-TMALL" -> "KB8"
      （商家编码常见 "<3字符模型码>-<2~8 位变体码>[-<后缀>]" 格式；用于 sku-master 自动绑定到 KB8 模型）
    """
    raw = (spec_text or "").strip()
    if not raw:
        return None

    # Split by common separators and scan all segments.
    # Examples:
    # - "PM001;50*140;024画框" -> PM001
    # - "50*140;024画框" -> 024
    segments: List[str] = []
    for part in raw.replace("；", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        segments.append(part)

    if not segments:
        return None

    # Priority 1: exact 3-char alnum code segment (matches our default model_code length=3)
    for seg in segments:
        token = seg.strip().upper()
        if len(token) == 3 and token.isalnum():
            return token

    # Priority 2: structured variant code "<MMM>-<NNN..>" → take the leading MMM
    # 之所以放在“纯3位数字”前面：当商家编码是 "KB8-001" 时优先识别为 KB8 而不是被误抽成数字段。
    for seg in segments:
        m = re.match(r"^([A-Z0-9]{3})-[A-Z0-9]{2,8}(?:-[A-Z0-9]{1,16})?$", seg.strip().upper())
        if m:
            return m.group(1)

    # Priority 3: leading 3 digits anywhere, e.g. "024画框"
    for seg in segments:
        token = seg.strip().upper()
        if len(token) >= 3 and token[:3].isdigit():
            return token[:3]

    # Priority 4: legacy PM-prefixed code (scan any segment)
    for seg in segments:
        token = seg.strip().upper()
        if not token.startswith("PM"):
            continue
        for ch in token:
            if not (ch.isalnum() or ch in ("_", "-")):
                break
        else:
            return token

    return None


def _extract_model_code_from_shop_spec(
    shop_spec: Optional[str],
    *,
    known_model_codes: Optional[set] = None,
) -> Optional[str]:
    """
    严格版"商家编码 → 模型码"抽取器（用于 auto_bind_preview 的 P0 锚点）。

    与通用的 ``_extract_model_code_hint`` 不同，本函数**拒绝**像
    "986153092837"（12 位淘宝平台 ID）这种"前 3 位数字 + 一长串后缀"的格式，
    避免吉客云历史 tradeGoodsno 全是平台默认 ID 的场景下，所有同前缀 ID
    被错绑到一个模型上的连锁误判。

    接受的格式：
      - "KB8"            纯 3-char 字母数字，且**不能全是数字**（数字开头容易和平台 ID 冲撞）
      - "KB8-001"        XXX-XXX 结构化变体码
      - "KB8-001-TMALL"  XXX-XXX-XXX 三段式
      - "PMxxx_yy"       PM 前缀的传统模型码（保留兼容）

    拒绝的格式：
      - "986153092837"   全数字（平台 ID）
      - "F26040205"      9 位无破折号字符（订单号 / 批次号样式）
      - "Q26010601C丝圈地垫"  前 3 位字母数字但后接非破折号字符

    防御性容错（2026-05-12）：当传入 ``known_model_codes`` 时，对于 strict
    规则抓不到的输入，再尝试"末尾子串匹配"——识别像 ``Q26041801KB8-001``
    这种 ERP 端运营把"款号前缀+模型变体码"拼起来录入的脏数据，**前提是
    末尾段的 3 字符头确实在 known_model_codes 里**，避免误剥
    ``DDXNEF001X-4060`` / ``J22082101`` 等不该剥的尾段。
    一般 mapper 入库时已归一化，这里是双保险。

    返回 None 时，调用方应回退到 spec_text 关键词匹配。
    """
    raw = (shop_spec or "").strip().upper()
    if not raw:
        return None
    # 单一 token：3-char 字母数字 且不能全数字
    if len(raw) == 3 and raw.isalnum() and not raw.isdigit():
        return raw
    # XXX-XXX[-XXX] 结构
    m = re.match(r"^([A-Z0-9]{3})-[A-Z0-9]{2,8}(?:-[A-Z0-9]{1,16})?$", raw)
    if m:
        head = m.group(1)
        if not head.isdigit():
            return head
    # PM 传统前缀
    if raw.startswith("PM") and all(ch.isalnum() or ch in ("_", "-") for ch in raw):
        return raw
    # 容错：末尾子串匹配 "<前缀><MMM-NNN[-XXX]>"，仅当 MMM 是真实存在的 model_code
    if known_model_codes:
        m2 = re.search(
            r"(?P<head>[A-Z][A-Z0-9]{2})-(?P<tail>[A-Z0-9]{2,8})(?:-(?P<extra>[A-Z0-9]{1,16}))?$",
            raw,
        )
        if m2 and m2.start() > 0:  # 必须有前缀才剥
            head = m2.group("head")
            if head in known_model_codes:
                return head
    return None


def _extract_variant_code_hint(text: Optional[str]) -> Optional[str]:
    """
    抽取“模型-变体”短码（如 KB8-001 / KB8-MG），用于：
    - sku-master 列表展示：商家编码命中变体编码后显示给运营
    - 后续 BOM 生成阶段精确命中线变体（已在 _augment_runtime_tokens 兜底）
    """
    raw = (text or "").strip().upper()
    if not raw:
        return None
    m = re.search(r"\b([A-Z0-9]{3}-[A-Z0-9]{2,8})\b", raw)
    return m.group(1) if m else None


def _clear_suspect_misbind_resolved(meta: Dict[str, Any]) -> None:
    """绑定变更时调用：清掉之前的"运营声明绑定正确"标记。

    新绑定可能命中或不命中关键词体系，让算法重新评估，避免老的忽略状态遗留。
    """
    for k in (
        "suspect_misbind_resolved",
        "suspect_misbind_resolved_at",
        "suspect_misbind_resolved_by",
        "suspect_misbind_resolved_note",
    ):
        meta.pop(k, None)


def resolve_suspect_misbind(
    db: Session,
    *,
    sku_master_id: str,
    requested_by: Optional[str],
    note: Optional[str],
) -> Dict[str, Any]:
    """Operator-action: explicitly mark this SKU's binding as "verified correct",
    suppressing future "疑似绑错" warnings for all shipment lines of this SKU.

    Use case: 算法基于关键词反向索引误判（例如伞型模型变体覆盖了某品类，
    但变体的 spec_contains_all 还没维护到位，或者运营有意做跨品类映射）。
    这是个声明式开关，不影响实际绑定，只是抑制告警，便于运营聚焦真问题。

    自动撤销：当 SKU 的绑定模型变更时（``bind_sku_to_version`` / ``unbind`` 路径），
    此标记会被重置——新绑定需要重新被判定。
    """
    sm = db.query(models.SkuMaster).filter(models.SkuMaster.id == str(sku_master_id)).first()
    if not sm:
        raise ValueError(f"sku_master {sku_master_id!r} 不存在")
    meta = dict(sm.metadata_json or {})
    meta["suspect_misbind_resolved"] = True
    meta["suspect_misbind_resolved_at"] = _utcnow().isoformat()
    if requested_by:
        meta["suspect_misbind_resolved_by"] = requested_by
    if note:
        meta["suspect_misbind_resolved_note"] = note
    sm.metadata_json = meta
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(sm, "metadata_json")
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return {
        "sku_master_id": str(sm.id),
        "erp_sku_barcode": sm.erp_sku_barcode,
        "suspect_misbind_resolved": True,
    }


def resolve_spec_mismatch(
    db: Session,
    *,
    sku_master_id: str,
    requested_by: Optional[str],
    note: Optional[str],
) -> Dict[str, Any]:
    """Operator-action: explicitly ignore the current spec_mismatch flag.

    Writes ``spec_mismatch_resolved=True`` + audit fields.  Auto-revoked
    by ``_update_shipment_seen`` when a real dimension_mismatch shows up later.
    """
    sm = db.query(models.SkuMaster).filter(models.SkuMaster.id == str(sku_master_id)).first()
    if not sm:
        raise ValueError(f"sku_master {sku_master_id!r} 不存在")
    meta = dict(sm.metadata_json or {})
    meta["spec_mismatch_resolved"] = True
    meta["spec_mismatch_resolved_at"] = _utcnow().isoformat()
    if requested_by:
        meta["spec_mismatch_resolved_by"] = requested_by
    if note:
        meta["spec_mismatch_resolved_note"] = note
    # 同步把"展示用" spec_mismatch 标记一并下掉，运营立即看到效果
    meta["spec_mismatch"] = False
    sm.metadata_json = meta
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(sm, "metadata_json")
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return {
        "sku_master_id": str(sm.id),
        "erp_sku_barcode": sm.erp_sku_barcode,
        "spec_mismatch": False,
        "spec_mismatch_resolved": True,
    }


def reevaluate_spec_mismatch_by_id(
    db: Session,
    *,
    sku_master_id: str,
) -> Dict[str, Any]:
    """Re-run ``_evaluate_spec_mismatch`` for one SKU and persist the result.
    Used by the backfill script and any future "重新评估" button.

    Skips rows that have ``spec_mismatch_resolved=True`` (operator already decided).
    """
    sm = db.query(models.SkuMaster).filter(models.SkuMaster.id == str(sku_master_id)).first()
    if not sm:
        return {"sku_master_id": sku_master_id, "skipped": True, "reason": "not_found"}
    meta = dict(sm.metadata_json or {})
    if meta.get("spec_mismatch_resolved") is True:
        return {"sku_master_id": sku_master_id, "skipped": True, "reason": "operator_resolved"}
    erp_text = (sm.spec_text or "").strip()
    ship_text = str(meta.get("last_shipment_spec_text") or "").strip()
    if not erp_text or not ship_text:
        return {"sku_master_id": sku_master_id, "skipped": True, "reason": "missing_spec"}
    judge = _evaluate_spec_mismatch(
        db,
        sku_master_row=sm,
        erp_spec_text=erp_text,
        shipment_spec_text=ship_text,
    )
    is_mismatch = bool(judge.get("is_mismatch"))
    prev = bool(meta.get("spec_mismatch"))
    meta["spec_mismatch"] = is_mismatch
    if is_mismatch:
        meta["spec_mismatch_at"] = _utcnow().isoformat()
        meta["spec_mismatch_reason"] = judge.get("reason")
        if judge.get("detail"):
            meta["spec_mismatch_detail"] = judge.get("detail")
    else:
        meta.pop("spec_mismatch_reason", None)
        meta.pop("spec_mismatch_detail", None)
    sm.metadata_json = meta
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(sm, "metadata_json")
    except Exception:  # noqa: BLE001
        pass
    return {
        "sku_master_id": str(sm.id),
        "erp_sku_barcode": sm.erp_sku_barcode,
        "before": prev,
        "after": is_mismatch,
        "reason": judge.get("reason"),
        "detail": judge.get("detail"),
    }


def _evaluate_spec_mismatch(
    db: Session,
    *,
    sku_master_row: models.SkuMaster,
    erp_spec_text: Optional[str],
    shipment_spec_text: Optional[str],
) -> Dict[str, Any]:
    """智能"规格差异"评估器（替换早期的字面 != 比较）。

    判定规则（OR 合取，命中任一即真差异）：
      1. 解析出的尺寸不一致（width_cm / height_cm / diameter_cm）
         —— 尺寸是钱，必须报警
      2. 关键词冲突：发货 spec 命中"别的已发布模型"的 recognition_keywords，
         且"不命中"当前已绑模型的关键词 —— 疑似贴错码 / 商家改了 SKU 含义

    锚点优先级：
      - 第一锚点：已落库的 ``metadata.bound_variant_code`` / 已绑模型 model_code
        （已绑定就是真理，关键词只用于交叉校验）
      - 关键词单独不能作为充分条件，因为很多模型有相同关键词

    不算差异的常见情况（即使字面 != ）：
      - 颜色 / 版本前缀差异（"颜色分类:" / "规格:" 等）
      - 字符顺序变化、token 子集差异、normalize 后 punctuation 差异
      - ERP 末尾重复 SKU 编码而发货没有，等等

    Returns
    -------
    {
      "is_mismatch": bool,
      "reason": str | None,           # "dimension_mismatch" / "keyword_conflict" / None
      "detail": str | None,           # 人类可读说明
      "erp_normalized": str,
      "shipment_normalized": str,
    }
    """
    erp_raw = (erp_spec_text or "").strip()
    ship_raw = (shipment_spec_text or "").strip()
    if not erp_raw or not ship_raw:
        # 任一为空：无法比较 → 视为无差异（不打标）
        return {
            "is_mismatch": False,
            "reason": None,
            "detail": None,
            "erp_normalized": "",
            "shipment_normalized": "",
        }

    # 等价判定用 normalize_for_compare (比 normalize_tx_spec_text 更激进, 把空格也视为分隔符)
    # 这样能识别 "Q25120402C皮革桌垫;80*160" ↔ "Q25120402C皮革桌垫 80*160" 这种等价情况.
    erp_norm = spec_parser_service.normalize_for_compare(erp_raw)
    ship_norm = spec_parser_service.normalize_for_compare(ship_raw)
    if erp_norm == ship_norm:
        # normalize 后字面相等：肯定无差异
        return {
            "is_mismatch": False,
            "reason": None,
            "detail": None,
            "erp_normalized": erp_norm,
            "shipment_normalized": ship_norm,
        }

    # ---- 规则 1：尺寸比较 ----
    # 解析失败的情况下当成"无尺寸约束"——避免因 parser 不认识某种格式导致误报
    erp_p = spec_parser_service.parse_spec(erp_raw)
    ship_p = spec_parser_service.parse_spec(ship_raw)

    def _eq_dim(a, b) -> bool:
        if a is None or b is None:
            return True
        try:
            from decimal import Decimal as _D
            return _D(str(a)) == _D(str(b))
        except Exception:  # noqa: BLE001
            return str(a).strip() == str(b).strip()

    if not (
        _eq_dim(erp_p.get("width_cm"), ship_p.get("width_cm"))
        and _eq_dim(erp_p.get("height_cm"), ship_p.get("height_cm"))
        and _eq_dim(erp_p.get("diameter_cm"), ship_p.get("diameter_cm"))
    ):
        return {
            "is_mismatch": True,
            "reason": "dimension_mismatch",
            "detail": (
                f"ERP 解析尺寸 = {erp_p.get('width_cm')}×{erp_p.get('height_cm')}cm; "
                f"发货解析尺寸 = {ship_p.get('width_cm')}×{ship_p.get('height_cm')}cm"
            ),
            "erp_normalized": erp_norm,
            "shipment_normalized": ship_norm,
        }

    # ---- 规则 2：关键词冲突（仅在已绑定的情况下校验） ----
    # 取当前已绑模型的 recognition_keywords vs 其它已发布 standard 模型的关键词集合，
    # 看发货 spec_text 是否命中"别人"+"不命中自己"。这种才是真冲突。
    bound_model_id: Optional[str] = None
    sku = (getattr(sku_master_row, "erp_sku_barcode", None) or "").strip()
    if sku:
        try:
            bind = (
                db.query(models.SkuModelVersionMapping)
                .filter(
                    models.SkuModelVersionMapping.sku_code == sku,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                )
                .order_by(models.SkuModelVersionMapping.created_at.desc())
                .first()
            )
            if bind:
                v = db.get(models.ProductModelVersion, bind.model_version_id)
                if v and not v.is_archived:
                    bound_model_id = v.model_id
        except Exception:  # noqa: BLE001
            bound_model_id = None

    if not bound_model_id:
        # 未绑定：关键词无锚点，跳过 rule 2，仅依靠 rule 1 已通过判定 → 不算差异
        return {
            "is_mismatch": False,
            "reason": None,
            "detail": "normalize 后字面不等但解析尺寸一致；未绑定无法做关键词交叉校验",
            "erp_normalized": erp_norm,
            "shipment_normalized": ship_norm,
        }

    # 取所有已发布 standard 模型 + recognition_keywords
    rows = (
        db.query(models.ProductModel, models.ProductModelVersion)
        .join(models.ProductModelVersion, models.ProductModelVersion.model_id == models.ProductModel.id)
        .filter(
            models.ProductModel.is_archived.is_(False),
            models.ProductModelVersion.is_archived.is_(False),
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
        )
        .all()
    )
    ship_norm_upper = "".join(ship_norm.split()).upper()
    bound_kw_hit = False
    other_model_hit_codes: List[str] = []
    for m, _v in rows:
        meta = m.metadata_json or {}
        raw_kws = meta.get("recognition_keywords") if isinstance(meta, dict) else None
        if not isinstance(raw_kws, list):
            continue
        kws = [
            "".join(str(x).strip().split()).upper()
            for x in raw_kws
            if x is not None and "".join(str(x).strip().split())
        ]
        if not kws:
            continue
        hit_any = any(kw and kw in ship_norm_upper for kw in kws)
        if not hit_any:
            continue
        if str(m.id) == str(bound_model_id):
            bound_kw_hit = True
        else:
            other_model_hit_codes.append(str(m.model_code or ""))

    # 只有"命中别人 且 没命中自己"才算真冲突
    if other_model_hit_codes and not bound_kw_hit:
        unique_others = sorted(set(c for c in other_model_hit_codes if c))[:5]
        return {
            "is_mismatch": True,
            "reason": "keyword_conflict",
            "detail": (
                f"发货规格命中其它模型关键词 [{', '.join(unique_others)}]，"
                f"且不命中当前已绑模型 → 疑似贴错码"
            ),
            "erp_normalized": erp_norm,
            "shipment_normalized": ship_norm,
        }

    return {
        "is_mismatch": False,
        "reason": None,
        "detail": "normalize 后字面不等但尺寸一致 + 关键词不冲突（颜色/版本前缀差异等无害变化）",
        "erp_normalized": erp_norm,
        "shipment_normalized": ship_norm,
    }


def _compute_parsed_summary(spec_text: Optional[str]) -> Dict[str, Any]:
    text = (spec_text or "").strip()
    if not text:
        return {
            "spec_text": None,
            "spec_hash": None,
            "parser_version": PARSER_VERSION,
            "tokens": [],
            "dimensions": {},
            "model_code_hint": None,
        }
    parsed = spec_parser_service.parse_spec(text)
    dims = {
        "width_cm": str(parsed.get("width_cm")) if parsed.get("width_cm") is not None else None,
        "height_cm": str(parsed.get("height_cm")) if parsed.get("height_cm") is not None else None,
        "diameter_cm": str(parsed.get("diameter_cm")) if parsed.get("diameter_cm") is not None else None,
        "area_m2": str(parsed.get("area_m2")) if parsed.get("area_m2") is not None else None,
        "perimeter_m": str(parsed.get("perimeter_m")) if parsed.get("perimeter_m") is not None else None,
    }
    return {
        "spec_text": text,
        "spec_hash": _sha1_text(text),
        "parser_version": PARSER_VERSION,
        "tokens": list(parsed.get("tokens") or []),
        "dimensions": {k: v for k, v in dims.items() if v not in (None, "")},
        "model_code_hint": _extract_model_code_hint(text),
    }


def _merge_metadata(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    out.update({k: v for k, v in (patch or {}).items() if v is not None})
    return out


def import_erp_sku_master_xlsx(
    db: Session,
    *,
    file_bytes: bytes,
    requested_by: Optional[str],
) -> Dict[str, Any]:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": []}

    headers = _build_header_index(rows[0])
    missing = [c for c in ("货品条码（系统）",) if c not in headers]
    errors: List[Dict[str, Any]] = []
    if missing:
        errors.append({"row": 1, "error": f"Missing required headers: {missing}"})
        return {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": errors}

    inserted = 0
    updated = 0
    skipped = 0
    total = 0
    # Guardrail: shop_sku_mappings might not exist in some deployments before migration runs.
    # We optimistically try once and disable on first OperationalError ("no such table").
    has_shop_sku_mappings = True
    # Handle duplicates within the same file/import run deterministically.
    seen: Dict[str, models.SkuMaster] = {}

    for row_idx, row in enumerate(rows[1:], start=2):
        if not any(v not in (None, "") for v in row):
            continue
        total += 1

        barcode = _norm_str(_get(row, headers, "货品条码（系统）"))
        if not barcode:
            skipped += 1
            errors.append({"row": row_idx, "error": "Missing barcode"})
            continue

        payload = {
            "platform_product_id": _norm_str(_get(row, headers, "平台商品Id（网店）")),
            "platform_sku_id": _norm_str(_get(row, headers, "平台规格Id（网店）")),
            "channel": _norm_str(_get(row, headers, "销售渠道")),
            "product_name": _norm_str(_get(row, headers, "商品名称（网店）")),
            "product_code": _norm_str(_get(row, headers, "商品编码（网店）")),
            # 解析主来源：保持与现状一致（用户确认“货品规格（系统）仍作为解析来源”）
            # - 优先：商品规格（网店）
            # - 回退：货品规格（系统）
            "spec_text": _norm_str(_get(row, headers, "商品规格（网店）"))
            or _norm_str(_get(row, headers, "货品规格（系统）")),
            # 额外保留原始规格文本，便于排查“网店规格 vs 系统规格”的差异
            "shop_spec_text_raw": _norm_str(_get(row, headers, "商品规格（网店）")),
            "system_spec_text_raw": _norm_str(_get(row, headers, "货品规格（系统）")),
            # 重点：网店侧规格编码（新品会回填我们系统编码；老品可能为空）
            "shop_spec_code": _norm_str(_get(row, headers, "规格编码（网店）")),
            "match_status": _norm_str(_get(row, headers, "匹配状态")),
            "match_method": _norm_str(_get(row, headers, "匹配方式")),
            "source_updated_at": _parse_excel_datetime(_get(row, headers, "最后更新时间")),
            # 可选：如果ERP下载表未来包含该列，可在这里直接导入；否则可由我们后续回写到ERP
            "production_process": _norm_str(_get(row, headers, "生产工艺"))
            or _norm_str(_get(row, headers, "生产工艺注")),
        }
        images = {
            "spec_image": _norm_str(_get(row, headers, "规格图片（网店）")),
            "product_image": _norm_str(_get(row, headers, "商品图片（网店）")),
        }

        # Preserve platform_sku_id dimension (optional; requires migration).
        if has_shop_sku_mappings:
            try:
                _upsert_shop_sku_mapping(
                    db,
                    platform_sku_id=payload.get("platform_sku_id"),
                    channel=payload.get("channel"),
                    platform_product_id=payload.get("platform_product_id"),
                    erp_sku_barcode=barcode,
                    shop_spec_code=payload.get("shop_spec_code"),
                    production_process=payload.get("production_process"),
                    match_status=payload.get("match_status"),
                    match_method=payload.get("match_method"),
                    source_updated_at=payload.get("source_updated_at"),
                    requested_by=requested_by,
                )
            except OperationalError:
                # table not present in this deployment -> disable for rest of import
                has_shop_sku_mappings = False
            except Exception as exc:  # noqa: BLE001
                # do not fail the whole import; keep best-effort mapping
                errors.append({"row": row_idx, "error": f"ShopSkuMapping upsert failed: {exc}"})

        existing = seen.get(barcode)
        if not existing:
            existing = (
                db.query(models.SkuMaster)
                .filter(
                    models.SkuMaster.erp_sku_barcode == barcode,
                    models.SkuMaster.is_archived.is_(False),
                )
                .first()
            )
        if not existing:
            row_obj = models.SkuMaster(
                erp_sku_barcode=barcode,
                platform_product_id=payload["platform_product_id"],
                platform_sku_id=payload["platform_sku_id"],
                channel=payload["channel"],
                product_name=payload["product_name"],
                product_code=payload["product_code"],
                spec_text=payload["spec_text"],
                images_json={k: v for k, v in images.items() if v},
                match_status=payload["match_status"],
                source_updated_at=payload["source_updated_at"],
                metadata_json={
                    "source": "erp_import",
                    "requested_by": requested_by,
                    # 为后续反向同步预留：这些字段在后续ERP表单里通常不可见
                    "shop_spec_code": payload.get("shop_spec_code"),
                    "match_method": payload.get("match_method"),
                    # 生产工艺：用户确认列名为“生产工艺”（兼容旧名“生产工艺注”）
                    "production_process": payload.get("production_process"),
                    # 兼容旧key（如果前端/脚本还在用 production_note）
                    "production_note": payload.get("production_process"),
                    # 保留原始规格文本（便于回溯）
                    "shop_spec_text_raw": payload.get("shop_spec_text_raw"),
                    "system_spec_text_raw": payload.get("system_spec_text_raw"),
                },
            )
            _update_erp_parsed_cache(row_obj, requested_by=requested_by)
            db.add(row_obj)
            db.flush()
            seen[barcode] = row_obj
            inserted += 1
        else:
            # MVP: overwrite fields (do not attempt per-field merge)
            existing.platform_product_id = payload["platform_product_id"]
            existing.platform_sku_id = payload["platform_sku_id"]
            existing.channel = payload["channel"]
            existing.product_name = payload["product_name"]
            existing.product_code = payload["product_code"]
            existing.spec_text = payload["spec_text"]
            existing.images_json = {k: v for k, v in images.items() if v}
            existing.match_status = payload["match_status"]
            existing.source_updated_at = payload["source_updated_at"]
            meta = dict(existing.metadata_json or {})
            meta.update(
                {
                    "source": "erp_import",
                    "requested_by": requested_by,
                    "updated_at": _utcnow().isoformat(),
                    "shop_spec_code": payload.get("shop_spec_code"),
                    "match_method": payload.get("match_method"),
                    "production_process": payload.get("production_process"),
                    "production_note": payload.get("production_process"),
                    "shop_spec_text_raw": payload.get("shop_spec_text_raw"),
                    "system_spec_text_raw": payload.get("system_spec_text_raw"),
                }
            )
            existing.metadata_json = meta
            _update_erp_parsed_cache(existing, requested_by=requested_by)
            seen[barcode] = existing
            updated += 1

    db.commit()
    return {"total": total, "inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}


def _upsert_shop_sku_mapping(
    db: Session,
    *,
    platform_sku_id: Optional[str],
    channel: Optional[str],
    platform_product_id: Optional[str],
    erp_sku_barcode: Optional[str],
    shop_spec_code: Optional[str],
    production_process: Optional[str],
    match_status: Optional[str],
    match_method: Optional[str],
    source_updated_at: Optional[datetime],
    requested_by: Optional[str],
) -> None:
    """
    Preserve platform_sku_id dimension: unique key is (channel, platform_sku_id, is_archived=false).
    """
    psku = (platform_sku_id or "").strip()
    if not psku:
        return
    ch = (channel or "").strip() or None
    barcode = (erp_sku_barcode or "").strip() or None

    existing = (
        db.query(models.ShopSkuMapping)
        .filter(
            models.ShopSkuMapping.platform_sku_id == psku,
            models.ShopSkuMapping.channel == ch,
            models.ShopSkuMapping.is_archived.is_(False),
        )
        .first()
    )
    meta_patch = {
        "source": "erp_import",
        "requested_by": requested_by,
        "updated_at": _utcnow().isoformat(),
    }
    if not existing:
        row = models.ShopSkuMapping(
            channel=ch,
            platform_product_id=platform_product_id,
            platform_sku_id=psku,
            erp_sku_barcode=barcode,
            shop_spec_code=shop_spec_code,
            production_process=production_process,
            match_status=match_status,
            match_method=match_method,
            source_updated_at=source_updated_at,
            metadata_json={k: v for k, v in meta_patch.items() if v is not None},
        )
        db.add(row)
        db.flush()
        return

    existing.platform_product_id = platform_product_id
    existing.erp_sku_barcode = barcode
    existing.shop_spec_code = shop_spec_code
    existing.production_process = production_process
    existing.match_status = match_status
    existing.match_method = match_method
    existing.source_updated_at = source_updated_at
    meta = dict(existing.metadata_json or {})
    meta.update({k: v for k, v in meta_patch.items() if v is not None})
    existing.metadata_json = meta


def list_shop_skus_by_barcode(
    db: Session,
    *,
    erp_sku_barcode: str,
    channel: Optional[str] = None,
    limit: int = 20,
) -> List[models.ShopSkuMapping]:
    """
    Best-effort query of shop SKU mappings by ERP barcode.
    If table does not exist (migration not applied), return [].
    """
    code = (erp_sku_barcode or "").strip()
    if not code:
        return []
    try:
        q = db.query(models.ShopSkuMapping).filter(
            models.ShopSkuMapping.is_archived.is_(False),
            models.ShopSkuMapping.erp_sku_barcode == code,
        )
        if channel:
            q = q.filter(models.ShopSkuMapping.channel == channel)
        limit2 = max(min(int(limit or 20), 200), 1)
        # NOTE: avoid NULLS LAST because sqlite doesn't support it.
        # Put NULL timestamps at the end by sorting "is NULL" flag first.
        return (
            q.order_by(
                models.ShopSkuMapping.source_updated_at.is_(None),
                models.ShopSkuMapping.source_updated_at.desc(),
                models.ShopSkuMapping.updated_at.desc(),
            )
            .limit(limit2)
            .all()
        )
    except OperationalError:
        # migration not applied yet in this deployment
        return []


# ============================================================================
# 商家编码（merchant SKU）分类 — 与 frontend/src/utils/shopSpecCode.ts 同步
# ============================================================================
#   structured  = 可自动匹配（KB8 / KB8-001 / PMxxx）
#   platform    = 平台默认 ID（淘宝纯数字）
#   malformed   = 不规范（其它非空非数字字符串）
#   empty       = 未同步（NULL / 空串）
# ============================================================================

# PostgreSQL 正则：3 位字母数字且不全数字
_SHOP_SPEC_RE_3CHAR = r"^[A-Z0-9]{3}$"
# XXX-YYY[-ZZZ] 结构化变体码（不全数字开头）
_SHOP_SPEC_RE_PAIR = r"^[A-Z0-9]{3}-[A-Z0-9]{2,8}(-[A-Z0-9]{1,16})?$"
_SHOP_SPEC_RE_PM = r"^PM[A-Z0-9_-]+$"
_SHOP_SPEC_RE_PURE_DIGITS = r"^[0-9]+$"


def _shop_spec_expr():
    """COALESCE(metadata->>'shop_spec_code', ''), uppercased and trimmed."""
    return func.upper(func.trim(func.coalesce(
        models.SkuMaster.metadata_json["shop_spec_code"].as_string(), ""
    )))


def _apply_shop_spec_code_kind_filter(q, kind: str):
    """Filter `q` (a SkuMaster query) by shop_spec_code classification kind.

    `kind` must be one of:
      - structured     : KB8 / KB8-001 / PMxxx — 可触发 P0 锚点
      - platform       : 纯数字（淘宝/天猫平台默认 ID）
      - malformed      : 非空非数字但格式不规范
      - nonstructured  : 合并视图 = platform ∪ malformed（运营单一动作类）
      - empty          : NULL / 空串
      - all            : 不筛选
    """
    if kind == "all":
        return q
    expr = _shop_spec_expr()
    if kind == "empty":
        return q.filter(expr == "")
    if kind == "platform":
        return q.filter(expr.op("~")(_SHOP_SPEC_RE_PURE_DIGITS))
    if kind == "structured":
        # 3-char alnum (NOT pure digits) OR XXX-YYY[-ZZZ] (head not pure digits) OR PM*
        return q.filter(
            expr != "",
            ~expr.op("~")(_SHOP_SPEC_RE_PURE_DIGITS),
            or_(
                expr.op("~")(_SHOP_SPEC_RE_3CHAR),
                expr.op("~")(_SHOP_SPEC_RE_PAIR),
                expr.op("~")(_SHOP_SPEC_RE_PM),
            ),
        )
    if kind == "malformed":
        # everything not empty, not platform, not structured
        return q.filter(
            expr != "",
            ~expr.op("~")(_SHOP_SPEC_RE_PURE_DIGITS),
            ~expr.op("~")(_SHOP_SPEC_RE_3CHAR),
            ~expr.op("~")(_SHOP_SPEC_RE_PAIR),
            ~expr.op("~")(_SHOP_SPEC_RE_PM),
        )
    if kind == "nonstructured":
        # 非空 且 非 structured（=platform ∪ malformed）。
        # 运营关心的是"需不需要去吉客云改"，这两类都需要，合并展示更高效。
        return q.filter(
            expr != "",
            or_(
                # platform: 纯数字
                expr.op("~")(_SHOP_SPEC_RE_PURE_DIGITS),
                # malformed: 非纯数字 且 不匹配任一 structured 模式
                ~expr.op("~")(_SHOP_SPEC_RE_PURE_DIGITS)
                & ~expr.op("~")(_SHOP_SPEC_RE_3CHAR)
                & ~expr.op("~")(_SHOP_SPEC_RE_PAIR)
                & ~expr.op("~")(_SHOP_SPEC_RE_PM),
            ),
        )
    return q


def summarize_triple_tag_overview(
    db: Session,
    *,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """三标签全局指标 — 给商品档案顶部"指标条"用.

    Returns:
      {
        "total": int,                  # 总 SKU 数
        "sys_bound": int,              # 系统标签: 已绑定到 standard_model (反写源)
        "sys_bundle": int,             # 系统标签: 已绑定到 bundle template
        "shop_clean": int,             # 商家标签: 干净的标准变体码 (KB8-001 格式)
        "shop_dirty": int,             # 商家标签: 历史脏值 (Q24091001 等)
        "shop_empty": int,             # 商家标签: 网店未填
        "erp_synced": int,             # ERP 标签: out_sku_code 已填 (反写已发生)
        "erp_waiting": int,            # ERP 标签: 待反写
        "ready_to_writeback": int,     # 已绑标模但 ERP 还没反写 (M4 的真正目标量)
      }

    设计 (2026-05-16 与用户对齐, jackyun_erp_goods_master_sync_backlog.md §17):
    - 系统标签 = 真源 (bound_*)
    - 商家标签 = 输入材料 (shop_spec_code, 含历史脏)
    - ERP 标签 = 下游镜像 (out_sku_code, 反写后才有)
    - 三者数据单向流动: 商家 → 系统 → ERP, ERP 严禁反推
    """
    # 商家编码"干净格式"判定 (跟前端 isShopSpecCodeClean 一致):
    #   ^[A-Z0-9]{3}-[A-Z0-9]{2,8}(-[A-Z0-9]{1,16})?$
    CLEAN_RE = r"^[A-Z0-9]{3}-[A-Z0-9]{2,8}(-[A-Z0-9]{1,16})?$"

    base = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))
    if channel:
        base = base.filter(models.SkuMaster.channel == channel)

    # 单条 SQL 把 shop / erp 一起算 (110ms 实测扫 43 万行)
    row = base.with_entities(
        func.count().label("total"),
        func.count().filter(models.SkuMaster.shop_spec_code.op("~")(CLEAN_RE)).label("shop_clean"),
        func.count()
        .filter(
            models.SkuMaster.shop_spec_code.isnot(None),
            models.SkuMaster.shop_spec_code != "",
            ~models.SkuMaster.shop_spec_code.op("~")(CLEAN_RE),
        )
        .label("shop_dirty"),
        func.count()
        .filter(
            or_(
                models.SkuMaster.shop_spec_code.is_(None),
                models.SkuMaster.shop_spec_code == "",
            )
        )
        .label("shop_empty"),
        func.count()
        .filter(
            models.SkuMaster.out_sku_code.isnot(None),
            models.SkuMaster.out_sku_code != "",
        )
        .label("erp_synced"),
    ).one()

    # 系统标签 (bound) 走 EXISTS 子查询, 避免重复计数
    bound_subq = (
        db.query(models.SkuModelVersionMapping.id)
        .filter(
            models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
    )

    sys_bound_q = base.filter(bound_subq.exists())
    sys_bound = sys_bound_q.with_entities(func.count()).scalar() or 0

    # 套装绑定: metadata.bundle_template_id 非空
    bt_expr = func.coalesce(
        models.SkuMaster.metadata_json["bundle_template_id"].as_string(), ""
    )
    sys_bundle = (
        base.filter(bt_expr != "")
        .with_entities(func.count())
        .scalar()
        or 0
    )

    # ready_to_writeback: 已绑标模 AND ERP 待反写
    ready_to_writeback = (
        sys_bound_q.filter(
            or_(
                models.SkuMaster.out_sku_code.is_(None),
                models.SkuMaster.out_sku_code == "",
            )
        )
        .with_entities(func.count())
        .scalar()
        or 0
    )

    total = int(row.total or 0)
    erp_synced = int(row.erp_synced or 0)

    return {
        "total": total,
        "sys_bound": int(sys_bound),
        "sys_bundle": int(sys_bundle),
        "shop_clean": int(row.shop_clean or 0),
        "shop_dirty": int(row.shop_dirty or 0),
        "shop_empty": int(row.shop_empty or 0),
        "erp_synced": erp_synced,
        "erp_waiting": total - erp_synced,
        "ready_to_writeback": int(ready_to_writeback),
    }


def summarize_shop_spec_code(
    db: Session,
    *,
    channel: Optional[str] = None,
    bound_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate count of SkuMaster rows by shop_spec_code classification.

    Optional filters mirror `list_sku_master` so the strip can be scoped to
    the same context the user is viewing (e.g. only bound rows / a specific
    channel).
    """
    base = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))
    if channel:
        base = base.filter(models.SkuMaster.channel == channel)
    if bound_state in ("bound", "unbound"):
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
        )
        base = base.filter(subq.exists() if bound_state == "bound" else ~subq.exists())

    out: Dict[str, int] = {"structured": 0, "platform": 0, "malformed": 0, "empty": 0}
    total = 0
    for k in out.keys():
        out[k] = _apply_shop_spec_code_kind_filter(base, k).count()
        total += out[k]
    return {"total": total, **out}


def list_sku_master(
    db: Session,
    *,
    search: Optional[str],
    channel: Optional[str],
    match_status: Optional[str],
    target_kind: Optional[str] = None,
    bound_state: Optional[str] = None,
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    bundle_bound_state: Optional[str] = None,
    bundle_template_id: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    data_quality_status: Optional[str] = None,
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
    shop_spec_code_kind: Optional[str] = None,
    page: int,
    page_size: int,
    page_size_cap: int = 200,
    compute_total: bool = True,
    include_bindings: bool = True,
    include_parsed_fields: bool = True,
    include_shop_count: bool = False,
) -> Tuple[int, List[models.SkuMaster]]:
    page = max(int(page or 1), 1)
    cap = int(page_size_cap or 200)
    if cap <= 0:
        cap = 200
    page_size = max(min(int(page_size or 20), cap), 1)
    q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))

    target_kind2 = (target_kind or "").strip().lower()
    if target_kind2 not in ("", "any", "all", "model", "bundle"):
        target_kind2 = ""

    # If filtering by bound model/version, default to "bound" unless caller explicitly requests otherwise.
    if (bound_model_id or bound_model_code or bound_version_id) and bound_state not in ("bound", "unbound", "all"):
        bound_state = "bound"
    if search:
        s = f"%{search.strip()}%"
        # 让用户可以直接粘贴"本系统已有的任何编码"做搜索：
        # - erp_sku_barcode                  ：货品条码（SSOT）
        # - platform_product_id              ：平台货品 ID
        # - platform_sku_id                  ：平台 SKU ID（同一货品条码可能有多条）
        # - product_code                     ：货品编号
        # - product_name                     ：商品名称
        # - metadata_json.shop_spec_code     ：商家编码 / 网店规格编码（多数二级码从这里来）
        # - metadata_json.bound_variant_code ：已绑定的变体编码（如 OZU-001 / KB8-001），重绑过时变体码时直接粘贴
        # - 已绑模型 model_code / model_name ：通过 sku_model_version_mapping 子查询命中（用于按模型短码/中文名找已绑 SKU，如 OZU 直喷切割垫类）
        shop_spec_expr = func.coalesce(models.SkuMaster.metadata_json["shop_spec_code"].as_string(), "")
        bound_variant_expr = func.coalesce(models.SkuMaster.metadata_json["bound_variant_code"].as_string(), "")
        bound_model_subq = (
            db.query(models.SkuModelVersionMapping.id)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
            )
            .join(
                models.ProductModel,
                models.ProductModel.id == models.ProductModelVersion.model_id,
            )
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModel.is_archived.is_(False),
                or_(
                    models.ProductModel.model_code.ilike(s),
                    models.ProductModel.model_name.ilike(s),
                ),
            )
            .exists()
        )
        q = q.filter(
            (models.SkuMaster.erp_sku_barcode.ilike(s))
            | (models.SkuMaster.platform_product_id.ilike(s))
            | (models.SkuMaster.platform_sku_id.ilike(s))
            | (models.SkuMaster.product_name.ilike(s))
            | (models.SkuMaster.product_code.ilike(s))
            | (shop_spec_expr.ilike(s))
            | (bound_variant_expr.ilike(s))
            | bound_model_subq
        )
    if channel:
        q = q.filter(models.SkuMaster.channel == channel)
    if match_status:
        q = q.filter(models.SkuMaster.match_status == match_status)

    # Bundle-bound-state and bundle filters are based on sku_master.metadata_json (written by sku-master bind-by-bundle).
    bt_id_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_id"].as_string(), "")
    bt_code_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_code"].as_string(), "")
    bp_sel_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_preset_selector"].as_string(), "")

    if bundle_bound_state:
        bs = str(bundle_bound_state).strip().lower()
        if bs in ("bound", "yes", "1", "true"):
            q = q.filter(bt_id_expr != "")
        elif bs in ("unbound", "none", "no", "0", "false"):
            q = q.filter(bt_id_expr == "")

    if bundle_template_id:
        tid = str(bundle_template_id).strip()
        if tid:
            q = q.filter(bt_id_expr == tid)
    if bundle_template_code:
        tcode = str(bundle_template_code).strip()
        if tcode:
            q = q.filter(bt_code_expr == tcode)
    if bundle_preset_selector:
        sel = str(bundle_preset_selector).strip().upper()
        if sel:
            q = q.filter(func.upper(bp_sel_expr) == sel)

    excluded_list = list(set([str(x) for x in (excluded_sku_master_ids or []) if str(x).strip()]))
    if excluded_list:
        q = q.filter(~models.SkuMaster.id.in_(excluded_list))

    # 商家编码分类筛选 — 与前端 utils/shopSpecCode.ts::classifyShopSpecCode 保持同样规则。
    # structured  = 规范化商家编码（KB8 / KB8-001 / PMxxx），可触发 P0 锚点
    # platform    = 纯数字（淘宝/天猫平台默认 ID），自动匹配会忽略
    # malformed   = 非空非数字但格式不规范（F26040205、Q26010601C丝圈地垫 等）
    # empty       = NULL 或空串
    if shop_spec_code_kind:
        kind = str(shop_spec_code_kind).strip().lower()
        if kind in ("structured", "platform", "malformed", "empty", "all"):
            q = _apply_shop_spec_code_kind_filter(q, kind)
    # server-side filters for tabs (avoid empty pages caused by client-side filtering)
    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712
    # 数据质量状态筛选（"spu_attribute_conflict" / "ok" / None）
    # 用于让运营一眼圈出"SPU 错配"的 SKU，由 data_quality_service 写入。
    dqs = (data_quality_status or "").strip()
    if dqs:
        if dqs.lower() == "ok":
            # 没有 status 字段 = OK
            q = q.filter(
                or_(
                    models.SkuMaster.metadata_json["data_quality_status"].as_string().is_(None),
                    models.SkuMaster.metadata_json["data_quality_status"].as_string() == "",
                )
            )
        else:
            q = q.filter(
                models.SkuMaster.metadata_json["data_quality_status"].as_string() == dqs
            )
    # Bound-state filter and bound model/version filters (correlated EXISTS).
    # IMPORTANT: keep the common case (bound_state only) lightweight (no joins),
    # because these endpoints may run at very large scale (hundreds of thousands of rows).
    if bound_state in ("bound", "unbound") or (bound_model_id or bound_model_code or bound_version_id):
        if bound_model_id or bound_model_code or bound_version_id:
            subq = (
                db.query(models.SkuModelVersionMapping.id)
                .join(
                    models.ProductModelVersion,
                    models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
                )
                .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
                .filter(
                    models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                    models.ProductModelVersion.is_archived.is_(False),
                    models.ProductModel.is_archived.is_(False),
                )
            )
            if bound_version_id:
                subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
            if bound_model_id:
                subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
            if bound_model_code:
                subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
        else:
            subq = (
                db.query(models.SkuModelVersionMapping.id)
                .filter(
                    models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                )
            )

        if bound_state == "unbound":
            q = q.filter(~subq.exists())
        else:
            q = q.filter(subq.exists())

    # target_kind can further constrain results:
    # - model: require active model binding (same check as bound_state=bound)
    # - bundle: require bundle binding in metadata_json
    if target_kind2 in ("model", "bundle", "any"):
        # Generic "has model binding" filter.
        #
        # IMPORTANT: avoid correlated EXISTS here because `target_kind=any` is used by spec-matching
        # and can degrade into a nested-loop scan on large datasets.
        # Using a semi-join style `IN (SELECT DISTINCT sku_code ...)` allows DB to plan it as a hash/bitmap semi-join.
        active_sku_codes = (
            db.query(models.SkuModelVersionMapping.sku_code)
            .filter(
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
            .distinct()
        )
        has_model_binding_expr = models.SkuMaster.erp_sku_barcode.in_(active_sku_codes)
        if target_kind2 == "bundle":
            q = q.filter(bt_id_expr != "")
        elif target_kind2 == "model":
            q = q.filter(has_model_binding_expr)
        else:
            # any: model-bound OR bundle-bound
            q = q.filter(or_(has_model_binding_expr, bt_id_expr != ""))

    # preparse state filter (server-side; avoid empty pages)
    if preparse_state:
        state = str(preparse_state).strip().lower()
        ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
        if state in ("parsed", "done", "yes", "1", "true"):
            # Use COALESCE instead of IS NULL checks for better cross-db JSON behavior.
            q = q.filter(func.coalesce(ph, "") != "")
        elif state in ("unparsed", "none", "no", "0", "false"):
            q = q.filter(func.coalesce(ph, "") == "")

    def _parse_terms(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        s = str(raw)
        for ch in ("，", ";", "；", "\n", "\t"):
            s = s.replace(ch, " ")
        parts = [p.strip() for p in s.split(" ") if p.strip()]
        out: List[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    include_list = _parse_terms(include_terms)
    exclude_list = _parse_terms(exclude_terms)
    scope = (match_scope or "auto").strip()
    if scope not in ("auto", "spec", "name", "spec_or_name"):
        scope = "auto"

    # Per-channel default: some channels put spec tokens into product_name.
    name_channels = ["小红书", "京东"]

    def _field_expr_for_scope(term: str):
        pattern = f"%{term}%"
        spec_hit = models.SkuMaster.spec_text.ilike(pattern)
        name_hit = models.SkuMaster.product_name.ilike(pattern)
        if scope == "spec":
            return spec_hit
        if scope == "name":
            return name_hit
        if scope == "spec_or_name":
            return spec_hit | name_hit
        # auto
        return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (~models.SkuMaster.channel.in_(name_channels) & spec_hit)

    for t in include_list:
        q = q.filter(_field_expr_for_scope(t))
    for t in exclude_list:
        q = q.filter(~_field_expr_for_scope(t))
    total = int(q.count() or 0) if compute_total else -1
    # Default ordering: ERP source timestamp desc (NULLs last), then updated_at desc.
    # NOTE: avoid NULLS LAST because sqlite doesn't support it; use (is NULL) ordering for portability.
    items = (
        q.order_by(
            models.SkuMaster.source_updated_at.is_(None),
            models.SkuMaster.source_updated_at.desc(),
            models.SkuMaster.updated_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    if include_bindings:
        _attach_active_version_bindings(db, items)
    if include_parsed_fields:
        _attach_parsed_fields(items)
    if include_shop_count:
        _attach_shop_count(db, items)
    return total, items


def _attach_shop_count(db: Session, rows: List[models.SkuMaster]) -> None:
    """注入 row.shop_count: int — 该条码在 shop_sku_mappings (active) 里的店铺映射条数.

    一个 ERP 货品 (barcode) 可能在多个店铺 / 多个 platform_sku_id 下卖,
    商品档案展示时需要让用户一眼看到「这个商品有多少店铺映射」。
    """
    if not rows:
        return
    barcodes = [r.erp_sku_barcode for r in rows if getattr(r, "erp_sku_barcode", None)]
    if not barcodes:
        for r in rows:
            r.shop_count = 0  # type: ignore[attr-defined]
        return
    counts = dict(
        db.query(
            models.ShopSkuMapping.erp_sku_barcode,
            func.count(models.ShopSkuMapping.id),
        )
        .filter(
            models.ShopSkuMapping.erp_sku_barcode.in_(list(set(barcodes))),
            models.ShopSkuMapping.is_archived.is_(False),
        )
        .group_by(models.ShopSkuMapping.erp_sku_barcode)
        .all()
    )
    for r in rows:
        r.shop_count = int(counts.get(r.erp_sku_barcode, 0) or 0)  # type: ignore[attr-defined]


def get_sku_master(db: Session, sku_id: str) -> Optional[models.SkuMaster]:
    row = db.get(models.SkuMaster, sku_id)
    if not row or row.is_archived:
        return None
    _attach_active_version_bindings(db, [row])
    _attach_parsed_fields([row])
    return row


def get_by_barcode(db: Session, barcode: str) -> Optional[models.SkuMaster]:
    code = (barcode or "").strip()
    if not code:
        return None
    row = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == code, models.SkuMaster.is_archived.is_(False))
        .first()
    )
    if not row:
        return None
    # Keep behavior consistent with list/detail endpoints:
    # attach computed binding fields and parsed-cache fields so scan page can show "已绑定模型"
    _attach_active_version_bindings(db, [row])
    _attach_parsed_fields([row])
    return row


def ensure_from_shipment(
    db: Session,
    *,
    erp_sku_barcode: str,
    spec_text: Optional[str],
    channel: Optional[str],
    metadata: Dict[str, Any],
) -> models.SkuMaster | None:
    barcode = (erp_sku_barcode or "").strip()
    if not barcode:
        return None
    existing = get_by_barcode(db, barcode)
    if existing:
        _update_shipment_seen(existing, shipment_spec_text=spec_text, channel=channel, metadata=metadata, db=db)
        return existing
    # 发货时按需同步（更省资源）：
    # - 发货导入遇到未建档SKU：先创建“最小SKU主档”以便后续绑定/排障/重试异常
    # - 同时打标 needs_erp_sync，后续可由定时任务或按需接口拉取ERP的完整关联字段进行补齐
    meta = dict(metadata or {})
    meta.setdefault("source", "shipment_autobackfill")
    meta.setdefault("needs_erp_sync", True)
    meta.setdefault("erp_sync_status", "pending")
    meta.setdefault("erp_sync_reason", "created_from_shipment_missing_master")
    row = models.SkuMaster(
        erp_sku_barcode=barcode,
        channel=(channel or None),
        spec_text=(spec_text or None),
        metadata_json=meta,
    )
    _update_erp_parsed_cache(row, requested_by=str(metadata.get("requested_by") or ""))
    _update_shipment_seen(row, shipment_spec_text=spec_text, channel=channel, metadata=metadata, db=db)
    db.add(row)
    db.flush()
    return row


def _attach_active_version_bindings(db: Session, rows: List[models.SkuMaster]) -> None:
    """
    Attach computed fields to sku_master rows for frontend readability:
    - active_version_binding_id
    - active_model_version_id

    NOTE: We reuse existing sku_model_version_mapping as the current SSOT for "是否已绑定可用版本".
    """
    if not rows:
        return
    barcodes = [r.erp_sku_barcode for r in rows if getattr(r, "erp_sku_barcode", None)]
    if not barcodes:
        return

    mappings = (
        db.query(models.SkuModelVersionMapping)
        .filter(
            models.SkuModelVersionMapping.sku_code.in_(list(set(barcodes))),
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
        .order_by(models.SkuModelVersionMapping.sku_code.asc(), models.SkuModelVersionMapping.created_at.desc())
        .all()
    )

    latest: Dict[str, models.SkuModelVersionMapping] = {}
    for m in mappings:
        if m.sku_code not in latest:
            latest[m.sku_code] = m

    for r in rows:
        m = latest.get(r.erp_sku_barcode)
        if not m:
            r.active_version_binding_id = None
            r.active_model_version_id = None
            r.bound_model_code = None
            r.bound_model_name = None
            r.bound_version_label = None
            r.bound_version_kind = None
            r.bound_version_status = None
        else:
            r.active_version_binding_id = m.id
            r.active_model_version_id = m.model_version_id
            # fill after we load version/model

    version_ids = [r.active_model_version_id for r in rows if getattr(r, "active_model_version_id", None)]
    if not version_ids:
        return
    versions = (
        db.query(models.ProductModelVersion)
        .options(joinedload(models.ProductModelVersion.model))
        .filter(
            models.ProductModelVersion.id.in_(list(set(version_ids))),
            models.ProductModelVersion.is_archived.is_(False),
        )
        .all()
    )
    by_id: Dict[str, models.ProductModelVersion] = {v.id: v for v in versions}
    for r in rows:
        vid = getattr(r, "active_model_version_id", None)
        v = by_id.get(vid)
        if not v:
            r.bound_model_code = None
            r.bound_model_name = None
            r.bound_version_label = None
            r.bound_version_kind = None
            r.bound_version_status = None
            continue
        model = getattr(v, "model", None)
        r.bound_model_code = getattr(model, "model_code", None)
        r.bound_model_name = getattr(model, "model_name", None)
        r.bound_version_label = getattr(v, "version_label", None)
        r.bound_version_kind = getattr(v, "version_kind", None)
        r.bound_version_status = getattr(v, "version_status", None)

    # ---- 变体展示：直接读绑定时落库的 metadata_json.bound_variant_code，不做任何反推 ----
    # 设计原因：人工审核没有可靠的 spec→variant 反推规则；自动识别也已经在
    # auto_bind_execute 里把 variant_code_hint 写入了 bound_variant_code。
    # 这里只负责"拿编码 → 查 ProductModelLineVariant → 拼 display_name(KB8-001) 给前端"。
    bound_variant_pairs: List[tuple[str, str]] = []  # (version_id, variant_code_upper)
    for r in rows:
        vid = getattr(r, "active_model_version_id", None)
        if not vid:
            continue
        meta = getattr(r, "metadata_json", None) or {}
        code = str(meta.get("bound_variant_code") or "").strip().upper()
        if code:
            bound_variant_pairs.append((str(vid), code))
    if bound_variant_pairs:
        # 一次性 query 当前列表用到的所有 (version, variant_code) 组合的 line variants
        version_id_set = list({p[0] for p in bound_variant_pairs})
        rows_var = (
            db.query(models.ProductModelLineVariant)
            .filter(
                models.ProductModelLineVariant.version_id.in_(version_id_set),
                models.ProductModelLineVariant.is_archived.is_(False),
            )
            .all()
        )
        # 索引：(version_id, variant_code_upper) → variant 实例
        var_by_key: Dict[tuple[str, str], models.ProductModelLineVariant] = {}
        for vr in rows_var:
            vmeta = vr.metadata_json or {}
            vc = str(vmeta.get("variant_code") or "").strip().upper()
            if not vc:
                continue
            var_by_key[(str(vr.version_id), vc)] = vr
        for r in rows:
            vid = getattr(r, "active_model_version_id", None)
            meta = getattr(r, "metadata_json", None) or {}
            code = str(meta.get("bound_variant_code") or "").strip().upper()
            if not vid or not code:
                r.bound_variant_code = None
                r.bound_variant_label = None
                continue
            vr = var_by_key.get((str(vid), code))
            if not vr:
                # 编码已落库但变体被删了 / 切版本：仍展示编码，让运营看到异常
                r.bound_variant_code = code
                r.bound_variant_label = code
                continue
            vmeta = vr.metadata_json or {}
            display_name = str(vmeta.get("display_name") or "").strip() or None
            material_name: Optional[str] = display_name
            if not material_name:
                for it in vr.items or []:
                    name = str(getattr(it, "material_name", "") or "").strip()
                    if name:
                        material_name = name
                        break
            r.bound_variant_code = code
            r.bound_variant_label = f"{material_name}({code})" if material_name else code
    else:
        # 没有任何 row 带 bound_variant_code：批量清空，避免 ORM 残留旧值
        for r in rows:
            r.bound_variant_code = None
            r.bound_variant_label = None


def _update_erp_parsed_cache(row: models.SkuMaster, *, requested_by: Optional[str]) -> None:
    """
    Pre-parse ERP spec_text and store summary into metadata_json for reuse/display.
    """
    meta = dict(row.metadata_json or {})
    summary = _compute_parsed_summary(row.spec_text)
    meta = _merge_metadata(
        meta,
        {
            "erp_spec_hash": summary.get("spec_hash"),
            "erp_parser_version": summary.get("parser_version"),
            "erp_dimensions": summary.get("dimensions"),
            "erp_tokens": summary.get("tokens"),
            "model_code_hint_erp": summary.get("model_code_hint"),
            "erp_parsed_at": _utcnow().isoformat(),
            "requested_by": requested_by or meta.get("requested_by"),
        },
    )
    row.metadata_json = meta


def _update_shipment_seen(
    row: models.SkuMaster,
    *,
    shipment_spec_text: Optional[str],
    channel: Optional[str],
    metadata: Dict[str, Any],
    db: Optional[Session] = None,
) -> None:
    """
    Record last seen shipment spec_text/hash, and intelligently flag spec_mismatch.

    spec_mismatch 判定改用 ``_evaluate_spec_mismatch``：
      - 尺寸不一致 → 真差异
      - 关键词命中"别人"且不命中"自己已绑模型" → 疑似贴错码
      - 其它字符差异（颜色前缀、字符顺序、token 子集）一律放行

    操作员手动点过"忽略此差异"（``spec_mismatch_resolved=True``）后，
    只要发货规格继续无尺寸差异，就保持忽略状态；如果出现真的尺寸差异，
    新差异会自动覆盖忽略，重新打标。

    We do NOT overwrite ERP fields (spec_text/platform ids), only augment metadata.
    """
    meta = dict(row.metadata_json or {})
    ship_summary = _compute_parsed_summary(shipment_spec_text)
    if ship_summary.get("spec_text"):
        meta["last_shipment_spec_text"] = ship_summary.get("spec_text")
        meta["last_shipment_spec_hash"] = ship_summary.get("spec_hash")
        meta["last_shipment_parser_version"] = ship_summary.get("parser_version")
        meta["last_shipment_dimensions"] = ship_summary.get("dimensions")
        meta["last_shipment_tokens"] = ship_summary.get("tokens")
        meta["model_code_hint_shipment"] = ship_summary.get("model_code_hint")
        meta["last_shipment_seen_at"] = _utcnow().isoformat()

        erp_text = (row.spec_text or "").strip()
        ship_text = (ship_summary.get("spec_text") or "").strip()

        # 没有 db session（极少数早期调用路径）退化到 normalize 后字面比较，
        # 避免空指针；普通运行链路一定会传 db。
        if db is not None:
            judge = _evaluate_spec_mismatch(
                db,
                sku_master_row=row,
                erp_spec_text=erp_text,
                shipment_spec_text=ship_text,
            )
            is_mismatch = bool(judge.get("is_mismatch"))
            mismatch_reason = judge.get("reason")
            mismatch_detail = judge.get("detail")
        else:
            erp_norm = spec_parser_service.normalize_for_compare(erp_text)
            ship_norm = spec_parser_service.normalize_for_compare(ship_text)
            is_mismatch = bool(erp_text and ship_text and erp_norm != ship_norm)
            mismatch_reason = "legacy_text_diff" if is_mismatch else None
            mismatch_detail = None

        prev_resolved = bool(meta.get("spec_mismatch_resolved"))
        if is_mismatch:
            meta["spec_mismatch"] = True
            meta["spec_mismatch_at"] = _utcnow().isoformat()
            meta["spec_mismatch_reason"] = mismatch_reason
            if mismatch_detail:
                meta["spec_mismatch_detail"] = mismatch_detail
            # 出现新差异（尤其是 dimension_mismatch）→ 自动撤销之前的"已忽略"
            if prev_resolved and mismatch_reason == "dimension_mismatch":
                meta["spec_mismatch_resolved"] = False
                meta["spec_mismatch_resolved_revoked_at"] = _utcnow().isoformat()
        else:
            meta["spec_mismatch"] = False
            meta.pop("spec_mismatch_reason", None)
            meta.pop("spec_mismatch_detail", None)
            # 已自然消失：清除"已忽略"标记，避免运营误以为还在忽略
            if prev_resolved:
                meta["spec_mismatch_resolved"] = False
    # keep channel only if empty (avoid overwriting ERP import data)
    if not row.channel and channel:
        row.channel = channel
    # preserve existing source; but record that we saw shipments
    meta.setdefault("seen_sources", [])
    if isinstance(meta["seen_sources"], list) and "shipments" not in meta["seen_sources"]:
        meta["seen_sources"].append("shipments")
    # merge provenance
    if metadata:
        meta.setdefault("shipment_backfill", {})
        if isinstance(meta["shipment_backfill"], dict):
            meta["shipment_backfill"].update(
                {
                    "batch_id": metadata.get("batch_id"),
                    "shipment_no": metadata.get("shipment_no"),
                    "spec_hash": metadata.get("spec_hash"),
                    # 2026 新规则：用于“前置绑定锚点/套装短码”
                    "shop_spec_code": metadata.get("shop_spec_code"),
                    # 维度：平台规格Id（网店）
                    "platform_sku_id": metadata.get("platform_sku_id"),
                }
            )
        # 顶层 shop_spec_code：auto_bind_preview 的 P0 锚点（从这里取值）。
        # 仅在传入的 shop_spec_code 非空时覆盖，避免后续不带商家编码的同步把已有值清掉。
        # 这是吉客云 ERP 没在 SKU 主档维护商家编码、却在发货 detail 里带了 tradeGoodsno 的关键回流通道。
        new_shop = (str(metadata.get("shop_spec_code") or "").strip()) or None
        if new_shop:
            meta["shop_spec_code"] = new_shop
            meta["shop_spec_code_source"] = "shipment"
            meta["shop_spec_code_seen_at"] = _utcnow().isoformat()
            # migration 0045 后：物理列同步双写（前端 D 阶段切到物理列后这里就是唯一源）
            row.shop_spec_code = new_shop
    row.metadata_json = meta


def _attach_parsed_fields(rows: List[models.SkuMaster]) -> None:
    """
    Attach parsed summary fields as dynamic attributes for Pydantic response.
    """
    for r in rows:
        meta = dict(getattr(r, "metadata_json", None) or {})
        # 商家编码 / 网店规格编码（用于 2026 新规则：渠道侧携带的预置编码，包含模型码/套装码等锚点）
        # 升列后（migration 0045）：物理列 r.shop_spec_code 优先；老数据 fallback metadata。
        # Stage D（前端 ProductInfoPage 切换列）后再下线这个 fallback。
        _phys_shop = getattr(r, "shop_spec_code", None)
        r.shop_spec_code = _phys_shop if _phys_shop else meta.get("shop_spec_code")
        # 生产工艺：同样的物理列优先 / metadata fallback 策略
        _phys_proc = getattr(r, "production_process", None)
        r.production_process = _phys_proc if _phys_proc else meta.get("production_process")
        # 套装模板绑定（Phase0：存 metadata_json；用于 sku-master 人工兜底/前置校验）
        r.bundle_template_id = meta.get("bundle_template_id")
        r.bundle_template_code = meta.get("bundle_template_code")
        r.bundle_preset_selector = meta.get("bundle_preset_selector")
        # 套装模板发布版本（用于口径稳定：发布版本 → 套装模型版本）
        r.bundle_template_version_id = meta.get("bundle_template_version_id")
        r.bundle_template_version_label = meta.get("bundle_template_version_label")
        r.bundle_model_version_id = meta.get("bundle_model_version_id")
        r.erp_spec_hash = meta.get("erp_spec_hash")
        r.erp_parser_version = meta.get("erp_parser_version")
        r.erp_dimensions = meta.get("erp_dimensions") or {}
        r.erp_tokens = meta.get("erp_tokens") or []
        r.model_code_hint = meta.get("model_code_hint_shipment") or meta.get("model_code_hint_erp")
        r.last_shipment_spec_text = meta.get("last_shipment_spec_text")
        r.last_shipment_spec_hash = meta.get("last_shipment_spec_hash")
        r.preparse_spec_text = meta.get("preparse_spec_text")
        r.preparse_spec_hash = meta.get("preparse_spec_hash")
        r.preparse_parser_version = meta.get("preparse_parser_version")
        r.preparse_dimensions = meta.get("preparse_dimensions") or {}
        r.preparse_tokens = meta.get("preparse_tokens") or []
        r.preparse_has_dims = meta.get("preparse_has_dims")
        r.preparse_saved_at = meta.get("preparse_saved_at")
        r.preparse_saved_by = meta.get("preparse_saved_by")
        r.spec_mismatch = bool(meta.get("spec_mismatch"))
        r.spec_mismatch_at = meta.get("spec_mismatch_at")
        r.data_quality_status = meta.get("data_quality_status")
        r.data_quality_evidence = meta.get("data_quality_evidence")
        r.data_quality_evaluated_at = meta.get("data_quality_evaluated_at")
        # 识别依据 + 识别用的输入源 (前端「识别依据」列直接读这两个字段, 见 SkuMasterRead schema)
        rec_src, rec_input = _compute_recognition_source(r, meta)
        r.recognition_source = rec_src
        r.recognition_input_source = rec_input


def _compute_recognition_source(
    row: models.SkuMaster, meta: Dict[str, Any]
) -> tuple[Optional[str], Optional[str]]:
    """
    回放 ``auto_bind_preview/_execute`` 的优先级, 还原"这条 SKU 的系统标签是怎么得出来的".

    返回 (recognition_source, recognition_input_source).

    优先级与字段含义见 ``SkuMasterRead`` schema 的注释.
    设计原则: 只读已落库的事实 (bound_*/shop_spec_code/metadata.bundle_template_id/
    metadata.last_shipment_spec_text), 不再次扫规格不命中, 因为列表场景对延时极敏感.
    """
    bound_model_code = (getattr(row, "bound_model_code", None) or "").strip()
    bound_variant = (meta.get("bound_variant_code") or "").strip().upper()
    bundle_id = (meta.get("bundle_template_id") or "").strip()
    shop_code = (getattr(row, "shop_spec_code", None) or meta.get("shop_spec_code") or "").strip()
    variant_hint = _extract_variant_code_hint(shop_code) if shop_code else None
    variant_hint = (variant_hint or "").upper()

    # 没绑定 → 未识别
    if not bound_model_code and not bundle_id:
        return "none", None

    # P2 套装模板强绑 (独立通道)
    if bundle_id:
        return "bundle", None

    # P0 商家编码直锁: 商家编码抽出的 variant hint 与 bound_variant_code 一致
    # → 说明系统就是按商家编码锁定的 (而不是再回头跑了关键词匹配后碰巧一致)
    if variant_hint and bound_variant and variant_hint == bound_variant:
        return "merchant_code", None

    # P1 / P1' 规格类识别 — 看是否锁到变体
    # 用了哪个 spec 作为输入: 优先 last_shipment_spec_text (发过货), 回退 spec_text (档案)
    last_ship = (meta.get("last_shipment_spec_text") or "").strip()
    input_src = "shipment" if last_ship else "archive"
    if bound_variant:
        return "keyword_variant", input_src
    return "keyword_model_only", input_src


def save_spec_preparse(
    db: Session,
    *,
    sku_id: str,
    spec_text: str,
    width_cm: Any = None,
    height_cm: Any = None,
    diameter_cm: Any = None,
    requested_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a "pre-parse cache / manual audit" result into sku_master.metadata_json.
    This is for acceleration & preview only; shipment BOM generation MUST still re-parse on each import.
    """
    row = db.get(models.SkuMaster, sku_id)
    if not row or row.is_archived:
        raise ValueError("SKU master not found")
    text = (spec_text or "").strip()
    if not text:
        raise ValueError("spec_text 不能为空")

    # Upsert SpecParseSnapshot (for cross-reference & audit)
    spec_hash = _sha1_text(text)
    parsed0 = spec_parser_service.parse_spec(text)
    _ensure_spec_parse_snapshot(db, spec_hash=spec_hash, spec_text=text, parsed=parsed0)

    # Save cache to sku_master.metadata_json, allowing manual overrides
    parsed = spec_parser_service.parse_spec(text)
    dims = {
        "width_cm": parsed.get("width_cm"),
        "height_cm": parsed.get("height_cm"),
        "diameter_cm": parsed.get("diameter_cm"),
        "area_m2": parsed.get("area_m2"),
        "perimeter_m": parsed.get("perimeter_m"),
    }
    if width_cm not in (None, ""):
        dims["width_cm"] = width_cm
    if height_cm not in (None, ""):
        dims["height_cm"] = height_cm
    if diameter_cm not in (None, ""):
        dims["diameter_cm"] = diameter_cm
    has_dims = any(dims.get(k) not in (None, "") for k in ("width_cm", "height_cm", "diameter_cm"))

    meta = dict(row.metadata_json or {})
    meta.update(
        {
            "preparse_spec_text": text,
            "preparse_spec_hash": spec_hash,
            "preparse_parser_version": PARSER_VERSION,
            "preparse_dimensions": _json_safe(dims),
            "preparse_tokens": list(parsed.get("tokens") or []),
            # Mark whether this preparse yielded any measurable dimensions.
            # Some "定制尺寸/联系客服" SKUs will never have dims; treat as processed but show as "无尺寸".
            "preparse_has_dims": bool(has_dims),
            "preparse_saved_at": _utcnow().isoformat(),
            "preparse_saved_by": (requested_by or meta.get("requested_by") or None),
        }
    )
    row.metadata_json = meta
    db.commit()
    db.refresh(row)

    return {
        "sku_id": row.id,
        "preparse_spec_hash": spec_hash,
        "preparse_dimensions": meta.get("preparse_dimensions") or {},
        "preparse_tokens": meta.get("preparse_tokens") or [],
        "preparse_saved_at": meta.get("preparse_saved_at"),
        "preparse_saved_by": meta.get("preparse_saved_by"),
    }


def bulk_save_spec_preparse(
    db: Session,
    *,
    limit: int,
    search: Optional[str],
    channel: Optional[str],
    match_status: Optional[str],
    target_kind: Optional[str] = None,
    bundle_bound_state: Optional[str] = None,
    bundle_template_id: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    include_terms: Optional[str],
    exclude_terms: Optional[str],
    match_scope: Optional[str],
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    preparse_state: Optional[str] = None,
    cursor_id: Optional[str] = None,
    excluded_sku_ids: Optional[List[str]] = None,
    skip_if_same_hash: bool = True,
    requested_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bulk pre-parse & persist cache for bound SKUs.
    NOTE: only touches sku_master.metadata_json (preparse_*), and SpecParseSnapshot upsert for audit.
    """
    limit = max(min(int(limit or 200), 5000), 1)

    # For bundle "Z/force" presets: allow marking preparse as done even when spec_text is empty.
    # This prevents "一键跑完累计保存0" for Z-mode bundle items that do not rely on spec_text parsing.
    _tpl_cache: Dict[str, Any] = {}
    _preset_mode_cache: Dict[tuple[str, str], str] = {}

    def _bundle_preset_mode(meta: Dict[str, Any]) -> str:
        tid = str(meta.get("bundle_template_id") or "").strip()
        sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
        if not tid or not sel:
            return ""
        key = (tid, sel)
        if key in _preset_mode_cache:
            return _preset_mode_cache[key]
        mode = ""
        try:
            t = _tpl_cache.get(tid)
            if t is None:
                t = bundle_template_service.get_template(db, tid, include_archived=True)
                _tpl_cache[tid] = t
            tcode = str(getattr(t, "code", "") or "").strip().upper()
            tmeta = getattr(t, "metadata_json", None) or getattr(t, "metadata", None) or {}
            if not isinstance(tmeta, dict):
                tmeta = {}
            presets = tmeta.get("phrase_presets") or []
            if isinstance(presets, list):
                for p in presets:
                    if str((p or {}).get("selector", "") or "").strip().upper() == sel:
                        mode = str((p or {}).get("mode", "") or "").strip().lower()
                        break
            # Template code starting with Z- is also treated as "force" mode.
            if not mode and tcode.startswith("Z-"):
                mode = "force"
        except Exception:
            mode = ""
        _preset_mode_cache[key] = mode
        return mode

    def _parse_terms(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        s = str(raw)
        for ch in ("，", ";", "；", "\n", "\t"):
            s = s.replace(ch, " ")
        parts = [p.strip() for p in s.split(" ") if p.strip()]
        out: List[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    def _query_for_bulk_preparse():
        """
        Build a Query for bulk preparse, mirroring `list_sku_master` semantics,
        but allowing a cursor-friendly order (used for huge datasets).
        """
        q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))

        if search:
            s_like = f"%{search.strip()}%"
            q = q.filter(
                (models.SkuMaster.erp_sku_barcode.ilike(s_like))
                | (models.SkuMaster.platform_product_id.ilike(s_like))
                | (models.SkuMaster.product_name.ilike(s_like))
                | (models.SkuMaster.product_code.ilike(s_like))
            )
        if channel:
            q = q.filter(models.SkuMaster.channel == channel)
        if match_status:
            q = q.filter(models.SkuMaster.match_status == match_status)

        excluded_list = list(set([str(x) for x in (excluded_sku_ids or []) if str(x).strip()]))
        if excluded_list:
            q = q.filter(~models.SkuMaster.id.in_(excluded_list))

        # Decide target kind. If caller provides explicit anchor filters, infer kind.
        kind2 = (target_kind or "").strip().lower()
        if kind2 not in ("", "any", "all", "model", "bundle"):
            kind2 = ""
        if bound_model_id or bound_model_code or bound_version_id:
            kind2 = "model"
        if bundle_template_id or bundle_template_code or bundle_preset_selector:
            kind2 = "bundle"
        if kind2 in ("", "all"):
            kind2 = "model"  # preserve old behavior for existing callers
        if kind2 == "any":
            # any: allow either model-bound or bundle-bound
            kind2 = "any"

        bt_id_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_id"].as_string(), "")
        bt_code_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_code"].as_string(), "")
        bp_sel_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_preset_selector"].as_string(), "")

        # Bundle filters
        if bundle_bound_state:
            bs = str(bundle_bound_state).strip().lower()
            if bs in ("bound", "yes", "1", "true"):
                q = q.filter(bt_id_expr != "")
            elif bs in ("unbound", "none", "no", "0", "false"):
                q = q.filter(bt_id_expr == "")
        if bundle_template_id:
            tid = str(bundle_template_id).strip()
            if tid:
                q = q.filter(bt_id_expr == tid)
        if bundle_template_code:
            tcode = str(bundle_template_code).strip()
            if tcode:
                q = q.filter(bt_code_expr == tcode)
        if bundle_preset_selector:
            sel = str(bundle_preset_selector).strip().upper()
            if sel:
                q = q.filter(func.upper(bp_sel_expr) == sel)

        # Model binding EXISTS (optionally constrained to a specific model/version)
        if bound_model_id or bound_model_code or bound_version_id:
            subq = (
                db.query(models.SkuModelVersionMapping.id)
                .join(
                    models.ProductModelVersion,
                    models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
                )
                .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
                .filter(
                    models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                    models.ProductModelVersion.is_archived.is_(False),
                    models.ProductModel.is_archived.is_(False),
                )
            )
            if bound_version_id:
                subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
            if bound_model_id:
                subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
            if bound_model_code:
                subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
        else:
            subq = (
                db.query(models.SkuModelVersionMapping.id)
                .filter(
                    models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                )
            )

        if kind2 == "bundle":
            q = q.filter(bt_id_expr != "")
        elif kind2 == "any":
            q = q.filter(or_(subq.exists(), bt_id_expr != ""))
        else:
            q = q.filter(subq.exists())

        # preparse state filter (server-side)
        if preparse_state:
            state = str(preparse_state).strip().lower()
            ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
            if state in ("parsed", "done", "yes", "1", "true"):
                q = q.filter(func.coalesce(ph, "") != "")
            elif state in ("unparsed", "none", "no", "0", "false"):
                q = q.filter(func.coalesce(ph, "") == "")

        include_list = _parse_terms(include_terms)
        exclude_list = _parse_terms(exclude_terms)
        scope = (match_scope or "auto").strip()
        if scope not in ("auto", "spec", "name", "spec_or_name"):
            scope = "auto"

        name_channels = ["小红书", "京东"]

        def _field_expr_for_scope(term: str):
            pattern = f"%{term}%"
            spec_hit = models.SkuMaster.spec_text.ilike(pattern)
            name_hit = models.SkuMaster.product_name.ilike(pattern)
            if scope == "spec":
                return spec_hit
            if scope == "name":
                return name_hit
            if scope == "spec_or_name":
                return spec_hit | name_hit
            # auto
            return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (
                ~models.SkuMaster.channel.in_(name_channels) & spec_hit
            )

        for t in include_list:
            q = q.filter(_field_expr_for_scope(t))
        for t in exclude_list:
            q = q.filter(~_field_expr_for_scope(t))

        return q

    next_cursor_id: Optional[str] = None
    mode: str = "top"

    if cursor_id:
        # Cursor-friendly scan for huge datasets:
        # - stable order by primary key
        # - no COUNT()
        q = _query_for_bulk_preparse().filter(models.SkuMaster.id > str(cursor_id).strip())
        rows0 = q.order_by(models.SkuMaster.id.asc()).limit(limit + 1).all()
        has_more = len(rows0) > limit
        rows = rows0[:limit]
        next_cursor_id = rows[-1].id if rows else None
        mode = "cursor_id"
    else:
        # Default mode: reuse `list_sku_master` ordering for UX (latest first),
        # while still avoiding expensive COUNT().
        kind2 = (target_kind or "").strip().lower()
        if kind2 not in ("", "any", "all", "model", "bundle"):
            kind2 = ""
        if bound_model_id or bound_model_code or bound_version_id:
            kind2 = "model"
        if bundle_template_id or bundle_template_code or bundle_preset_selector:
            kind2 = "bundle"
        if kind2 in ("", "all"):
            kind2 = "model"

        bound_state2 = "bound" if kind2 == "model" else "all"
        _total_unused, rows0 = list_sku_master(
            db,
            search=search,
            channel=channel,
            match_status=match_status,
            target_kind=target_kind,
            bound_state=bound_state2,
            bound_model_id=bound_model_id,
            bound_model_code=bound_model_code,
            bound_version_id=bound_version_id,
            bundle_bound_state=bundle_bound_state,
            bundle_template_id=bundle_template_id,
            bundle_template_code=bundle_template_code,
            bundle_preset_selector=bundle_preset_selector,
            spec_mismatch=None,
            preparse_state=preparse_state,
            include_terms=include_terms,
            exclude_terms=exclude_terms,
            match_scope=match_scope,
            excluded_sku_master_ids=excluded_sku_ids,
            page=1,
            page_size=limit + 1,
            page_size_cap=5000,
            compute_total=False,
            include_bindings=False,
            include_parsed_fields=False,
        )
        has_more = len(rows0) > limit
        rows = rows0[:limit]

    scanned = 0
    saved = 0
    skipped_same_hash = 0
    skipped_empty_spec = 0
    errors: List[Dict[str, Any]] = []

    # First pass: decide which rows need work, compute hash once
    # work item: (row, spec_text_used_or_key, spec_hash, is_bundle_force)
    work: List[Tuple[models.SkuMaster, str, str, bool]] = []
    for r in rows:
        scanned += 1
        try:
            meta = dict(r.metadata_json or {})
            spec_text = (meta.get("last_shipment_spec_text") or r.spec_text or "").strip()
            if not spec_text:
                mode = _bundle_preset_mode(meta)
                if mode == "force":
                    tid = str(meta.get("bundle_template_id") or "").strip()
                    sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
                    key_text = f"__BUNDLE_FORCE__:{tid}:{sel}"
                    spec_hash = _sha1_text(key_text)
                    if (
                        skip_if_same_hash
                        and meta.get("preparse_spec_hash") == spec_hash
                        and meta.get("preparse_parser_version") == PARSER_VERSION
                    ):
                        skipped_same_hash += 1
                        continue
                    work.append((r, key_text, spec_hash, True))
                    continue
                skipped_empty_spec += 1
                continue
            spec_hash = _sha1_text(spec_text)
            if skip_if_same_hash and meta.get("preparse_spec_hash") == spec_hash and meta.get("preparse_parser_version") == PARSER_VERSION:
                skipped_same_hash += 1
                continue
            work.append((r, spec_text, spec_hash, False))
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_id": getattr(r, "id", None), "sku_code": getattr(r, "erp_sku_barcode", None), "error": str(exc)})

    hashes = sorted({h for _r, _t, h, is_force in work if not is_force})
    existing_hashes: set[str] = set()
    if hashes:
        existing_hashes = {
            str(x[0])
            for x in db.query(models.SpecParseSnapshot.spec_hash)
            .filter(models.SpecParseSnapshot.spec_hash.in_(hashes))
            .all()
        }

    parsed_cache: Dict[str, Dict[str, Any]] = {}  # spec_hash -> parsed dict
    for _r, spec_text, spec_hash, is_force in work:
        if is_force:
            continue
        parsed = parsed_cache.get(spec_hash)
        if parsed is None:
            parsed = spec_parser_service.parse_spec(spec_text)
            parsed_cache[spec_hash] = parsed
        if spec_hash not in existing_hashes:
            _ensure_spec_parse_snapshot(db, spec_hash=spec_hash, spec_text=spec_text, parsed=parsed)

    now_iso = _utcnow().isoformat()
    for r, spec_text, spec_hash, is_force in work:
        try:
            meta = dict(r.metadata_json or {})
            if is_force:
                parsed = {"tokens": []}
            else:
                parsed = parsed_cache.get(spec_hash) or spec_parser_service.parse_spec(spec_text)
            dims = {
                "width_cm": parsed.get("width_cm"),
                "height_cm": parsed.get("height_cm"),
                "diameter_cm": parsed.get("diameter_cm"),
                "area_m2": parsed.get("area_m2"),
                "perimeter_m": parsed.get("perimeter_m"),
            }
            has_dims2 = any(dims.get(k) not in (None, "") for k in ("width_cm", "height_cm", "diameter_cm"))
            meta.update(
                {
                    "preparse_spec_text": spec_text,
                    "preparse_spec_hash": spec_hash,
                    "preparse_parser_version": PARSER_VERSION,
                    "preparse_dimensions": _json_safe(dims),
                    "preparse_tokens": list(parsed.get("tokens") or []),
                    "preparse_has_dims": bool(has_dims2),
                    "preparse_saved_at": now_iso,
                    "preparse_saved_by": (requested_by or meta.get("requested_by") or None),
                    "preparse_mode": "bundle_force" if is_force else "spec_parse",
                }
            )
            r.metadata_json = meta
            saved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_id": getattr(r, "id", None), "sku_code": getattr(r, "erp_sku_barcode", None), "error": str(exc)})

    db.commit()

    # has_more computed by limit+1 query above (no extra DB round-trip)

    return {
        "scanned": scanned,
        "saved": saved,
        "skipped_same_hash": skipped_same_hash,
        "skipped_empty_spec": skipped_empty_spec,
        "errors": errors,
        "batch_candidates": scanned,
        "has_more": has_more,
        "next_cursor_id": next_cursor_id,
        "mode": mode,
    }


def preview_spec_preparse(
    db: Session,
    *,
    limit: int,
    search: Optional[str],
    channel: Optional[str],
    match_status: Optional[str],
    target_kind: Optional[str] = None,
    bundle_bound_state: Optional[str] = None,
    bundle_template_id: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    include_terms: Optional[str],
    exclude_terms: Optional[str],
    match_scope: Optional[str],
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    preparse_state: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Preview parsed dimensions for bound SKUs, without persisting.
    """
    limit = max(min(int(limit or 200), 5000), 1)
    kind2 = (target_kind or "").strip().lower()
    if kind2 not in ("", "any", "all", "model", "bundle"):
        kind2 = ""
    if bound_model_id or bound_model_code or bound_version_id:
        kind2 = "model"
    if bundle_template_id or bundle_template_code or bundle_preset_selector:
        kind2 = "bundle"
    if kind2 in ("", "all"):
        kind2 = "model"
    bound_state2 = "bound" if kind2 == "model" else "all"

    _, rows0 = list_sku_master(
        db,
        search=search,
        channel=channel,
        match_status=match_status,
        target_kind=target_kind,
        bound_state=bound_state2,
        bound_model_id=bound_model_id,
        bound_model_code=bound_model_code,
        bound_version_id=bound_version_id,
        bundle_bound_state=bundle_bound_state,
        bundle_template_id=bundle_template_id,
        bundle_template_code=bundle_template_code,
        bundle_preset_selector=bundle_preset_selector,
        spec_mismatch=None,
        preparse_state=preparse_state,
        include_terms=include_terms,
        exclude_terms=exclude_terms,
        match_scope=match_scope,
        page=1,
        page_size=limit,
        page_size_cap=5000,
        compute_total=False,
    )
    rows = rows0[:limit]
    items: List[Dict[str, Any]] = []
    skipped_empty_spec = 0
    errors: List[Dict[str, Any]] = []

    _tpl_cache: Dict[str, Any] = {}
    _preset_mode_cache: Dict[tuple[str, str], str] = {}

    def _bundle_preset_mode(meta: Dict[str, Any]) -> str:
        tid = str(meta.get("bundle_template_id") or "").strip()
        sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
        if not tid or not sel:
            return ""
        key = (tid, sel)
        if key in _preset_mode_cache:
            return _preset_mode_cache[key]
        mode = ""
        try:
            t = _tpl_cache.get(tid)
            if t is None:
                t = bundle_template_service.get_template(db, tid, include_archived=True)
                _tpl_cache[tid] = t
            tcode = str(getattr(t, "code", "") or "").strip().upper()
            tmeta = getattr(t, "metadata_json", None) or getattr(t, "metadata", None) or {}
            if not isinstance(tmeta, dict):
                tmeta = {}
            presets = tmeta.get("phrase_presets") or []
            if isinstance(presets, list):
                for p in presets:
                    if str((p or {}).get("selector", "") or "").strip().upper() == sel:
                        mode = str((p or {}).get("mode", "") or "").strip().lower()
                        break
            if not mode and tcode.startswith("Z-"):
                mode = "force"
        except Exception:
            mode = ""
        _preset_mode_cache[key] = mode
        return mode

    for r in rows:
        try:
            meta = dict(r.metadata_json or {})
            spec_text_used = (meta.get("last_shipment_spec_text") or r.spec_text or "").strip()
            if not spec_text_used:
                # Z/force bundle preset does not require spec_text; still include it for "mark as parsed".
                mode = _bundle_preset_mode(meta)
                if mode == "force":
                    tid = str(meta.get("bundle_template_id") or "").strip()
                    sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
                    key_text = f"__BUNDLE_FORCE__:{tid}:{sel}"
                    items.append(
                        {
                            "sku_id": r.id,
                            "erp_sku_barcode": r.erp_sku_barcode,
                            "channel": r.channel,
                            "product_name": getattr(r, "product_name", None),
                            "product_code": getattr(r, "product_code", None),
                            "spec_text": getattr(r, "spec_text", None),
                            "bundle_template_id": meta.get("bundle_template_id"),
                            "bundle_template_code": meta.get("bundle_template_code"),
                            "bundle_preset_selector": meta.get("bundle_preset_selector"),
                            "bound_model_code": getattr(r, "bound_model_code", None),
                            "bound_model_name": getattr(r, "bound_model_name", None),
                            "bound_version_label": getattr(r, "bound_version_label", None),
                            "spec_text_used": f"[Z指定型：无需规格解析 {sel}]",
                            "spec_hash": _sha1_text(key_text),
                            "width_cm": None,
                            "height_cm": None,
                            "diameter_cm": None,
                            "area_m2": None,
                            "perimeter_m": None,
                        }
                    )
                    continue
                skipped_empty_spec += 1
                continue
            parsed = spec_parser_service.parse_spec(spec_text_used)
            items.append(
                {
                    "sku_id": r.id,
                    "erp_sku_barcode": r.erp_sku_barcode,
                    "channel": r.channel,
                    "product_name": getattr(r, "product_name", None),
                    "product_code": getattr(r, "product_code", None),
                    "spec_text": getattr(r, "spec_text", None),
                    "bundle_template_id": meta.get("bundle_template_id"),
                    "bundle_template_code": meta.get("bundle_template_code"),
                    "bundle_preset_selector": meta.get("bundle_preset_selector"),
                    "bound_model_code": getattr(r, "bound_model_code", None),
                    "bound_model_name": getattr(r, "bound_model_name", None),
                    "bound_version_label": getattr(r, "bound_version_label", None),
                    "spec_text_used": spec_text_used,
                    "spec_hash": _sha1_text(spec_text_used),
                    "width_cm": parsed.get("width_cm"),
                    "height_cm": parsed.get("height_cm"),
                    "diameter_cm": parsed.get("diameter_cm"),
                    "area_m2": parsed.get("area_m2"),
                    "perimeter_m": parsed.get("perimeter_m"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_id": getattr(r, "id", None), "sku_code": getattr(r, "erp_sku_barcode", None), "error": str(exc)})
    return {"scanned": len(rows), "skipped_empty_spec": skipped_empty_spec, "errors": errors, "items": items}


def execute_spec_preparse(
    db: Session,
    *,
    sku_ids: List[str],
    skip_if_same_hash: bool = True,
    requested_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute preparse save for selected sku_ids.
    """
    ids = [str(x).strip() for x in (sku_ids or []) if str(x).strip()]
    if not ids:
        return {"scanned": 0, "saved": 0, "skipped_same_hash": 0, "errors": []}
    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(ids), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    scanned = 0
    saved = 0
    skipped_same_hash = 0
    skipped_empty_spec = 0
    errors: List[Dict[str, Any]] = []

    _tpl_cache: Dict[str, Any] = {}
    _preset_mode_cache: Dict[tuple[str, str], str] = {}

    def _bundle_preset_mode(meta: Dict[str, Any]) -> str:
        tid = str(meta.get("bundle_template_id") or "").strip()
        sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
        if not tid or not sel:
            return ""
        key = (tid, sel)
        if key in _preset_mode_cache:
            return _preset_mode_cache[key]
        mode = ""
        try:
            t = _tpl_cache.get(tid)
            if t is None:
                t = bundle_template_service.get_template(db, tid, include_archived=True)
                _tpl_cache[tid] = t
            tcode = str(getattr(t, "code", "") or "").strip().upper()
            tmeta = getattr(t, "metadata_json", None) or getattr(t, "metadata", None) or {}
            if not isinstance(tmeta, dict):
                tmeta = {}
            presets = tmeta.get("phrase_presets") or []
            if isinstance(presets, list):
                for p in presets:
                    if str((p or {}).get("selector", "") or "").strip().upper() == sel:
                        mode = str((p or {}).get("mode", "") or "").strip().lower()
                        break
            if not mode and tcode.startswith("Z-"):
                mode = "force"
        except Exception:
            mode = ""
        _preset_mode_cache[key] = mode
        return mode

    work: List[Tuple[models.SkuMaster, str, str, bool]] = []
    for r in rows:
        scanned += 1
        try:
            meta = dict(r.metadata_json or {})
            spec_text = (meta.get("last_shipment_spec_text") or r.spec_text or "").strip()
            if not spec_text:
                mode = _bundle_preset_mode(meta)
                if mode == "force":
                    tid = str(meta.get("bundle_template_id") or "").strip()
                    sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
                    key_text = f"__BUNDLE_FORCE__:{tid}:{sel}"
                    spec_hash = _sha1_text(key_text)
                    if (
                        skip_if_same_hash
                        and meta.get("preparse_spec_hash") == spec_hash
                        and meta.get("preparse_parser_version") == PARSER_VERSION
                    ):
                        skipped_same_hash += 1
                        continue
                    work.append((r, key_text, spec_hash, True))
                    continue
                skipped_empty_spec += 1
                continue
            spec_hash = _sha1_text(spec_text)
            if skip_if_same_hash and meta.get("preparse_spec_hash") == spec_hash and meta.get("preparse_parser_version") == PARSER_VERSION:
                skipped_same_hash += 1
                continue
            work.append((r, spec_text, spec_hash, False))
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_id": getattr(r, "id", None), "sku_code": getattr(r, "erp_sku_barcode", None), "error": str(exc)})

    hashes = sorted({h for _r, _t, h, is_force in work if not is_force})
    existing_hashes: set[str] = set()
    if hashes:
        existing_hashes = {
            str(x[0])
            for x in db.query(models.SpecParseSnapshot.spec_hash)
            .filter(models.SpecParseSnapshot.spec_hash.in_(hashes))
            .all()
        }

    parsed_cache: Dict[str, Dict[str, Any]] = {}
    for _r, spec_text, spec_hash, is_force in work:
        if is_force:
            continue
        parsed = parsed_cache.get(spec_hash)
        if parsed is None:
            parsed = spec_parser_service.parse_spec(spec_text)
            parsed_cache[spec_hash] = parsed
        if spec_hash not in existing_hashes:
            _ensure_spec_parse_snapshot(db, spec_hash=spec_hash, spec_text=spec_text, parsed=parsed)

    now_iso = _utcnow().isoformat()
    for r, spec_text, spec_hash, is_force in work:
        try:
            meta = dict(r.metadata_json or {})
            if is_force:
                parsed = {"tokens": []}
            else:
                parsed = parsed_cache.get(spec_hash) or spec_parser_service.parse_spec(spec_text)
            dims = {
                "width_cm": parsed.get("width_cm"),
                "height_cm": parsed.get("height_cm"),
                "diameter_cm": parsed.get("diameter_cm"),
                "area_m2": parsed.get("area_m2"),
                "perimeter_m": parsed.get("perimeter_m"),
            }
            has_dims2 = any(dims.get(k) not in (None, "") for k in ("width_cm", "height_cm", "diameter_cm"))
            meta.update(
                {
                    "preparse_spec_text": spec_text,
                    "preparse_spec_hash": spec_hash,
                    "preparse_parser_version": PARSER_VERSION,
                    "preparse_dimensions": _json_safe(dims),
                    "preparse_tokens": list(parsed.get("tokens") or []),
                    "preparse_has_dims": bool(has_dims2),
                    "preparse_saved_at": now_iso,
                    "preparse_saved_by": (requested_by or meta.get("requested_by") or None),
                    "preparse_mode": "bundle_force" if is_force else "spec_parse",
                }
            )
            r.metadata_json = meta
            saved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_id": getattr(r, "id", None), "sku_code": getattr(r, "erp_sku_barcode", None), "error": str(exc)})

    db.commit()
    return {
        "scanned": scanned,
        "saved": saved,
        "skipped_same_hash": skipped_same_hash,
        "skipped_empty_spec": skipped_empty_spec,
        "errors": errors,
    }


def list_published_standard_model_candidates(
    db: Session,
    *,
    search: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Return published standard version candidates for manual binding.
    Contract: one model has at most one published standard version (enforced by publish).
    """
    limit = max(min(int(limit or 50), 200), 1)
    q = (
        db.query(models.ProductModel, models.ProductModelVersion)
        .join(models.ProductModelVersion, models.ProductModelVersion.model_id == models.ProductModel.id)
        .filter(
            models.ProductModel.is_archived.is_(False),
            models.ProductModelVersion.is_archived.is_(False),
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
        )
        .order_by(models.ProductModel.model_code.asc())
    )
    if search:
        s = f"%{search.strip()}%"
        q = q.filter((models.ProductModel.model_code.ilike(s)) | (models.ProductModel.model_name.ilike(s)))
    rows = q.limit(limit).all()
    items: List[Dict[str, Any]] = []
    for m, v in rows:
        items.append(
            {
                "model_id": m.id,
                "model_code": m.model_code,
                "model_name": m.model_name,
                "published_version_id": v.id,
                "version_label": v.version_label,
            }
        )
    return items


def _get_published_standard_version_for_model_id(db: Session, model_id: str) -> models.ProductModelVersion:
    mid = (model_id or "").strip()
    if not mid:
        raise ValueError("model_id 不能为空")
    v = (
        db.query(models.ProductModelVersion)
        .options(joinedload(models.ProductModelVersion.model))
        .filter(
            models.ProductModelVersion.model_id == mid,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
            models.ProductModelVersion.is_archived.is_(False),
        )
        # SQLite doesn't support "NULLS LAST"; use (published_at IS NULL) ordering for portability.
        .order_by(
            models.ProductModelVersion.published_at.is_(None).asc(),
            models.ProductModelVersion.published_at.desc(),
            models.ProductModelVersion.created_at.desc(),
        )
        .first()
    )
    if not v:
        raise ValueError("该模型没有在线发布的标准版本（published standard）")
    return v


def unbind_sku_masters(
    db: Session,
    *,
    sku_master_ids: List[str],
    requested_by: Optional[str],
) -> Dict[str, Any]:
    """
    Clear current binding for selected sku masters.

    What it does:
    - Deactivate active `sku_model_version_mapping` rows (model or bundle-as-model).
    - Clear bundle-template related metadata fields on `sku_master.metadata_json`.

    What it does NOT do:
    - It does NOT delete historical shipment BOM snapshots (immutable/auditable).
      To fix historical profit/analytics, re-run "重建快照/计价" in shipments ops center.
    """
    ids = [str(x).strip() for x in (sku_master_ids or []) if str(x).strip()]
    total_selected = len(ids)
    if total_selected <= 0:
        return {"total_selected": 0, "unbound_count": 0, "skipped_missing_barcode": 0, "errors": []}

    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(list(set(ids))), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    by_id = {r.id: r for r in rows}

    unbound_count = 0
    skipped_missing_barcode = 0
    errors: List[Dict[str, Any]] = []
    now_iso = _utcnow().isoformat()

    for sid in ids:
        row = by_id.get(sid)
        if not row:
            errors.append({"sku_master_id": sid, "error": "sku_master not found"})
            continue
        sku = (getattr(row, "erp_sku_barcode", None) or "").strip()
        if not sku:
            skipped_missing_barcode += 1
            continue

        # deactivate active bindings (keep history)
        mappings = (
            db.query(models.SkuModelVersionMapping)
            .filter(
                models.SkuModelVersionMapping.sku_code == sku,
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.SkuModelVersionMapping.is_active.is_(True),
            )
            .all()
        )
        for m in mappings:
            m.is_active = False
            meta2 = dict(getattr(m, "metadata_json", None) or {})
            meta2.update({"unbound_at": now_iso, "unbound_by": requested_by, "unbound_reason": "manual_clear"})
            m.metadata_json = meta2
            db.add(m)

        # Clear bundle-template metadata fields (Phase0 fields)
        meta = dict(getattr(row, "metadata_json", None) or {})
        for k in (
            "bundle_template_id",
            "bundle_template_code",
            "bundle_preset_selector",
            "bundle_template_version_id",
            "bundle_template_version_label",
            "bundle_model_version_id",
        ):
            if k in meta:
                meta.pop(k, None)
        meta.update(
            {
                "binding_cleared_at": now_iso,
                "binding_cleared_by": requested_by,
                "binding_cleared_reason": "manual_clear",
            }
        )
        row.metadata_json = meta
        db.add(row)

        if mappings:
            unbound_count += 1

    db.commit()
    return {
        "total_selected": total_selected,
        "unbound_count": unbound_count,
        "skipped_missing_barcode": skipped_missing_barcode,
        "errors": errors,
    }


def generate_preparse_and_snapshots(
    db: Session,
    *,
    sku_master_ids: List[str],
    operator_id: Optional[str],
    limit_per_sku: int = 50,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Convenience automation for SKU master UI:
    - Generate/update pre-parse cache (dimensions/tokens) from latest shipment spec sample (if exists).
    - Generate shipment BOM snapshots for lines that are currently pending or in unresolved exception queue.

    Safety:
    - overwrite defaults to False (fill-missing only).
    - limit_per_sku caps workload.
    """
    from . import shipment_import_service  # local import to avoid circular deps

    ids = [str(x).strip() for x in (sku_master_ids or []) if str(x).strip()]
    total_selected = len(ids)
    if total_selected <= 0:
        return {
            "total_selected": 0,
            "parsed_count": 0,
            "created_snapshots": 0,
            "recomputed_snapshots": 0,
            "skipped_snapshots": 0,
            "failed_snapshots": 0,
            "skipped_missing_barcode": 0,
            "errors": [],
        }

    lim = max(min(int(limit_per_sku or 50), 500), 1)
    op = (operator_id or "").strip() or None

    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(list(set(ids))), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    by_id = {r.id: r for r in rows}

    parsed_count = 0
    created_snapshots = 0
    recomputed_snapshots = 0
    skipped_snapshots = 0
    failed_snapshots = 0
    skipped_missing_barcode = 0
    errors: List[Dict[str, Any]] = []

    # helpers to identify pending lines quickly
    has_bom = (
        db.query(models.BomSnapshot.id)
        .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
        .limit(1)
        .correlate(models.ShipmentLine)
        .exists()
    )
    has_costing = (
        db.query(models.ShipmentCostingResult.id)
        .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
        .limit(1)
        .correlate(models.ShipmentLine)
        .exists()
    )

    for sid in ids:
        sm = by_id.get(sid)
        if not sm:
            errors.append({"sku_master_id": sid, "error": "sku_master not found"})
            continue

        sku = (getattr(sm, "erp_sku_barcode", None) or "").strip()
        if not sku:
            skipped_missing_barcode += 1
            continue

        # 1) preparse from latest shipment sample (best-effort)
        try:
            _sh, _raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
            if norm_spec and norm_spec.strip():
                _apply_preparse_no_commit(db, sku_master_row=sm, spec_text=norm_spec, requested_by=op)
                parsed_count += 1
                db.add(sm)
                db.commit()
        except Exception as exc:
            db.rollback()
            errors.append({"sku_master_id": sid, "sku_code": sku, "error": f"preparse_failed: {str(exc)}"})

        # IMPORTANT: snapshot generation requires an active binding.
        # If user has cleared binding, they must go to shipments ops center to decide scope (all orders vs partial)
        # and perform overwrite rebuild if needed.
        binding = product_model_service.get_active_sku_binding(db, sku)
        if not binding:
            errors.append(
                {
                    "sku_master_id": sid,
                    "sku_code": sku,
                    "error": "skip_snapshots_unbound: SKU 当前未绑定；请先重新绑定，再执行“补齐缺失”。如需覆盖重建历史快照，请到发货作业中心操作。",
                }
            )
            continue

        # 2) snapshots: unresolved exceptions first (strong signal of missing snapshot)
        excs = (
            db.query(models.ShipmentExceptionQueue)
            .join(models.ShipmentLine, models.ShipmentLine.id == models.ShipmentExceptionQueue.shipment_line_id)
            .filter(
                models.ShipmentExceptionQueue.resolved_at.is_(None),
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                models.ShipmentLine.sku_code == sku,
            )
            .order_by(models.ShipmentExceptionQueue.created_at.desc())
            .limit(lim)
            .all()
        )
        line_ids: List[str] = [str(getattr(e, "shipment_line_id", "") or "").strip() for e in excs if getattr(e, "shipment_line_id", None)]

        # also include pending lines (no snapshot/costing) even if no exception row exists
        more_pending = (
            db.query(models.ShipmentLine.id)
            .filter(
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.sku_code == sku,
                func.nullif(func.trim(func.coalesce(models.ShipmentLine.spec_text, "")), "").isnot(None),
                ~or_(has_bom, has_costing),
            )
            .order_by(models.ShipmentLine.completed_at.desc().nullslast(), models.ShipmentLine.created_at.desc())
            .limit(lim)
            .all()
        )
        for (lid,) in more_pending:
            x = str(lid or "").strip()
            if x:
                line_ids.append(x)

        # de-dup and cap
        uniq: List[str] = []
        seen: set[str] = set()
        for lid in line_ids:
            if lid in seen:
                continue
            seen.add(lid)
            uniq.append(lid)
            if len(uniq) >= lim:
                break

        for lid in uniq:
            try:
                res = shipment_import_service.compute_snapshot_for_shipment_line(
                    db,
                    shipment_line_id=lid,
                    operator_id=op,
                    overwrite=bool(overwrite),
                )
                action = str(res.get("action") or "")
                if action == "created":
                    created_snapshots += 1
                elif action == "recomputed":
                    recomputed_snapshots += 1
                elif action == "skipped":
                    skipped_snapshots += 1
                    # If an exception row exists but line is already processed, resolve it to avoid "stale exceptions".
                    try:
                        db.query(models.ShipmentExceptionQueue).filter(
                            models.ShipmentExceptionQueue.shipment_line_id == lid,
                            models.ShipmentExceptionQueue.resolved_at.is_(None),
                        ).update({"resolved_at": _utcnow(), "message": "resolved_by_existing_snapshot"})
                        db.commit()
                    except Exception:
                        db.rollback()
                else:
                    failed_snapshots += 1
            except Exception as exc:
                db.rollback()
                failed_snapshots += 1
                errors.append({"sku_master_id": sid, "sku_code": sku, "shipment_line_id": lid, "error": str(exc)})

    return {
        "total_selected": total_selected,
        "parsed_count": parsed_count,
        "created_snapshots": created_snapshots,
        "recomputed_snapshots": recomputed_snapshots,
        "skipped_snapshots": skipped_snapshots,
        "failed_snapshots": failed_snapshots,
        "skipped_missing_barcode": skipped_missing_barcode,
        "errors": errors,
    }


def bind_sku_master_by_model(
    db: Session,
    *,
    model_id: str,
    sku_master_ids: List[str],
    requested_by: Optional[str],
    allow_rebind: bool = False,
    variant_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bind selected SKU masters to a (model, optional variant) pair.

    `variant_code`：可选的"最终绑定变体编码"（如 KB8-001）。会被规范化为大写写入
    ``sku_master.metadata_json.bound_variant_code``，列表/详情后续直接读这个字段做展示，
    不再靠 spec_text 反推（人工审核场景不存在可靠的反推规则）。
    传 None / 空串 = "不指定变体"，与历史行为一致。
    """
    version = _get_published_standard_version_for_model_id(db, model_id)
    norm_variant_code = (str(variant_code).strip().upper() or None) if variant_code else None
    total_selected = len(sku_master_ids or [])
    if total_selected <= 0:
        return {
            "total_selected": 0,
            "bound_count": 0,
            "skipped_already_bound": 0,
            "skipped_missing_barcode": 0,
            "errors": [],
        }

    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(list(set(sku_master_ids or []))), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    by_id = {r.id: r for r in rows}

    bound_count = 0
    skipped_already_bound = 0
    skipped_missing_barcode = 0
    errors: List[Dict[str, Any]] = []
    now_iso = _utcnow().isoformat()

    for sid in sku_master_ids:
        row = by_id.get(sid)
        if not row:
            errors.append({"sku_master_id": sid, "error": "sku_master not found"})
            continue
        sku = (row.erp_sku_barcode or "").strip()
        if not sku:
            skipped_missing_barcode += 1
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            skipped_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(version.id) and allow_rebind:
            # 已经绑到同一个发布版本——以前直接 skip，但这样会让"模型对了，只想补 / 改
            # variant_code"的常见场景在 UI 上根本无路可走。
            # 现在的语义：版本相同时，仍然把 bound_variant_code 当成"可单独更新的轻字段"
            # 处理；如果新值与旧值不一样，只 patch sku_master.metadata_json，不重建
            # SkuModelVersionMapping（保留 mapping 历史与 effective_from）。
            existing_meta = dict(getattr(active, "metadata_json", None) or {})
            existing_code = str(existing_meta.get("bound_variant_code") or "").strip().upper() or None
            sm_meta = dict(getattr(row, "metadata_json", None) or {})
            existing_sm_code = str(sm_meta.get("bound_variant_code") or "").strip().upper() or None
            new_code = norm_variant_code  # 已在函数顶部归一化为大写
            # 比较"sku_master 上落的 bound_variant_code"，因为列表 / 详情读的就是它
            if (new_code or None) == (existing_sm_code or None):
                skipped_already_bound += 1
                continue
            # 仅 patch sku_master.metadata_json.bound_variant_code，不动 mapping
            if new_code:
                sm_meta["bound_variant_code"] = new_code
            else:
                sm_meta.pop("bound_variant_code", None)
            _clear_suspect_misbind_resolved(sm_meta)
            sm_meta["model_bound_at"] = now_iso
            sm_meta["model_bound_by"] = requested_by or sm_meta.get("model_bound_by") or None
            sm_meta["model_binding_method"] = "manual_variant_only_update"
            row.metadata_json = sm_meta
            try:
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(row, "metadata_json")
            except Exception:
                pass
            bound_count += 1
            continue
        # Validation by latest shipment spec sample (relaxed):
        # - If no sample, allow binding but mark as "no_shipment_sample".
        # - If sample exists but BOM preview fails, block binding.
        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if norm_spec:
            try:
                bom_generation_service.generate_bom(
                    db,
                    spec_text=norm_spec,
                    model_version_id=str(version.id),
                    sku_code=sku,
                    quantity=Decimal("1"),
                    include_disabled_variants=False,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"sku_master_id": row.id, "sku_code": sku, "error": f"BOM试算失败：{str(exc)}"})
                continue
        try:
            product_model_service.bind_sku_to_version(
                db,
                sku_code=sku,
                version_id=version.id,
                source_system="sku_master_manual",
                metadata={
                    "requested_by": requested_by,
                    "sku_master_id": row.id,
                    "binding_method": "manual_by_model_rebind" if allow_rebind else "manual_by_model",
                    "skip_prefix_check": True,
                },
            )
            # 先跑 preparse（让它先 read-modify-write 一遍 metadata_json）
            if norm_spec:
                try:
                    _apply_preparse_no_commit(db, sku_master_row=row, spec_text=norm_spec, requested_by=requested_by)
                except Exception:
                    pass
            # ⚠ 必须在 preparse 之后写"我们要落的字段"。
            # 历史 bug：bind_sku_to_version 内部 db.commit() 触发 SQLAlchemy
            # expire_on_commit，row 被标 expired。如果我们先写、后跑 preparse，
            # preparse 内 `meta = dict(row.metadata_json or {})` 触发 lazy reload 拿到
            # stale baseline（不含我们刚 set 的 in-memory 值），update preparse 字段
            # 后写回 row.metadata_json，**把 model_bound_at / bound_variant_code 全抹掉**。
            # 把"我们要落的字段"放最后写，避免被 preparse 覆盖。
            # （回归测试：test_bind_with_shipment_sample_keeps_variant_code）
            meta = dict(getattr(row, "metadata_json", None) or {})
            meta.update(
                {
                    "model_bound_at": now_iso,
                    "model_bound_by": (requested_by or meta.get("requested_by") or None),
                    "model_binding_method": "manual_by_model_rebind" if allow_rebind else "manual_by_model",
                    "binding_validation_state": "sampled" if norm_spec else "no_shipment_sample",
                }
            )
            if norm_variant_code:
                meta["bound_variant_code"] = norm_variant_code
            else:
                meta.pop("bound_variant_code", None)
            _clear_suspect_misbind_resolved(meta)
            row.metadata_json = meta
            try:
                from sqlalchemy.orm.attributes import flag_modified  # local import to avoid global churn
                flag_modified(row, "metadata_json")
            except Exception:
                pass
            bound_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_master_id": row.id, "sku_code": sku, "error": str(exc)})

    db.commit()
    return {
        "total_selected": total_selected,
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "skipped_missing_barcode": skipped_missing_barcode,
        "errors": errors,
    }


def _latest_shipment_spec_sample(db: Session, *, sku_code: str) -> Tuple[Optional[models.ShipmentLine], Optional[str], Optional[str]]:
    """
    Return (shipment_line, raw_spec_text, normalized_spec_text) for the latest shipment line of this sku_code.
    """
    sku = (sku_code or "").strip()
    if not sku:
        return None, None, None
    row = (
        db.query(models.ShipmentLine)
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            models.ShipmentLine.is_active.is_(True),
            models.ShipmentLine.sku_code == sku,
            func.coalesce(models.ShipmentLine.spec_text, "") != "",
        )
        .order_by(
            models.ShipmentLine.completed_at.is_(None).asc(),
            models.ShipmentLine.completed_at.desc(),
            models.ShipmentLine.created_at.desc(),
        )
        .first()
    )
    raw = str(getattr(row, "spec_text", "") or "").strip() if row else None
    if not raw:
        return row, None, None
    try:
        norm = spec_parser_service.normalize_tx_spec_text(raw)
    except Exception:  # noqa: BLE001
        norm = raw
    norm = str(norm or "").strip() or None
    return row, raw, norm


def _mismatch_warnings_by_keywords_v2(
    db: Session,
    *,
    combined_text: str,
    bound_model_id: str,
) -> List[str]:
    """新版「疑似绑错」精筛：基于运营自定义的 ``recognition_keywords``。

    判定：发货样本文本命中"其它已发布标准模型"的关键词，且不命中"当前已绑模型"的关键词
    → 可能贴错码 / 误绑模型。

    这与 ``_evaluate_spec_mismatch`` 用的判定核心一致，但本函数返回的是
    给发货行用的"人话告警字符串"，可以拼到 hint 列里展示。

    设计考虑：
      - 与 SKU 主档「规格差异」共享同一套关键词来源（`metadata.recognition_keywords`）
      - 运营在标准模型编辑里加新关键词 → 立刻生效到发货管理「疑似绑错」
      - 多模型命中相同关键词时不报警（避免歧义噪音；类似 _match_by_model_keywords）

    返回 [] 表示：未找到冲突 / 无关键词配置。
    """
    text = "".join(str(combined_text or "").split()).upper()
    if not text or not bound_model_id:
        return []
    try:
        rows = (
            db.query(models.ProductModel, models.ProductModelVersion)
            .join(models.ProductModelVersion, models.ProductModelVersion.model_id == models.ProductModel.id)
            .filter(
                models.ProductModel.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModelVersion.version_kind == "standard",
                models.ProductModelVersion.version_status == "published",
            )
            .all()
        )
    except Exception:  # noqa: BLE001
        return []
    # 模型级 keywords + 变体级 spec_contains_all/_any 合并构造 model→keywords 映射
    # （与 SQL 端反向索引同语义：伞型模型靠变体覆盖品类）
    model_kws: Dict[str, List[str]] = {}
    model_code_by_id: Dict[str, str] = {}
    version_to_model: Dict[str, str] = {}
    for m, v in rows:
        model_code_by_id[str(m.id)] = str(m.model_code or "").strip() or "(未知)"
        version_to_model[str(v.id)] = str(m.id)
        meta = m.metadata_json or {}
        raw = meta.get("recognition_keywords") if isinstance(meta, dict) else None
        if isinstance(raw, list):
            for x in raw:
                k = "".join(str(x).strip().split()).upper()
                if k:
                    model_kws.setdefault(str(m.id), []).append(k)
    if version_to_model:
        try:
            variant_rows = (
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
            for ver_id, cond in variant_rows:
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
                        norm_t = "".join(ts.split()).upper()
                        if norm_t:
                            model_kws.setdefault(mid, []).append(norm_t)
        except Exception:  # noqa: BLE001
            pass

    bound_kw_hit = False
    other_model_hits: Dict[str, List[str]] = {}
    for mid, kws in model_kws.items():
        matched = [k for k in kws if k and k in text]
        if not matched:
            continue
        if mid == str(bound_model_id):
            bound_kw_hit = True
        else:
            code = model_code_by_id.get(mid) or "(未知)"
            other_model_hits.setdefault(code, []).extend(matched)
    if other_model_hits and not bound_kw_hit:
        # 列出冲突最严重的前 3 个模型，避免提示过长
        items = sorted(other_model_hits.items(), key=lambda x: -len(x[1]))[:3]
        labels = []
        for code, matched_kws in items:
            uniq = sorted(set(matched_kws))[:3]
            labels.append(f"{code}（命中：{', '.join(uniq)}）")
        return [
            f"疑似绑错：发货规格命中其它模型关键词 → {' / '.join(labels)}，且不命中当前已绑模型；请确认目标是否选对。"
        ]
    return []


def _mismatch_warnings_by_keywords(
    *,
    sample_text: str,
    sku_spec_text: Optional[str],
    product_name: Optional[str],
    target_label: str,
    db: Optional[Session] = None,
    bound_model_id: Optional[str] = None,
) -> List[str]:
    """
    Soft guardrail: warn when shipment sample keywords strongly suggest a different
    category than the chosen target.

    Two-tier strategy（向后兼容 + 渐进升级）：
      Tier 1（精筛，优先）: ``recognition_keywords`` 体系 — 当 caller 传入 ``db`` +
        ``bound_model_id`` 时启用。运营在标准模型里维护的关键词立刻生效。
      Tier 2（粗筛，兜底）: 硬编码 5 组品类（丝圈/地垫、抱枕、地毯、桌垫、装饰画/画框）
        — 旧行为，对未配置 recognition_keywords 的模型仍然有效，避免行级提示忽然全消失。

    Returns [] when no warning. This is NOT a hard error (users may intentionally
    map across categories).
    """
    # Tier 1: 统一关键词体系（运营维护的 recognition_keywords）
    # 当前已绑模型如果**已经配过 recognition_keywords**，就信任 Tier 1 的判断结果——
    # 不论是命中冲突（报警）还是无冲突（放行），都不再回退到硬编码 Tier 2。
    # 这样运营给 OZU 配了"丝圈地垫"后，发货命中"丝圈地垫"就**不会再被 Tier 2 的
    # "目标名称未含对应关键词" 兜底误报**。
    if db is not None and bound_model_id:
        try:
            bound_model_row = db.get(models.ProductModel, str(bound_model_id))
        except Exception:  # noqa: BLE001
            bound_model_row = None
        bound_kws: List[str] = []
        if bound_model_row is not None:
            # 模型级关键词
            meta_b = bound_model_row.metadata_json or {}
            raw_b = meta_b.get("recognition_keywords") if isinstance(meta_b, dict) else None
            if isinstance(raw_b, list):
                bound_kws.extend([str(x).strip() for x in raw_b if str(x or "").strip()])
            # 变体级关键词（伞型模型靠这个；如 OZU 模型只配"丝圈地垫"，
            # 但 OZU-002 变体覆盖"皮革桌垫" → 必须把变体级合并）
            try:
                vrows = (
                    db.query(
                        models.ProductModelLineVariant.conditions_json,
                    )
                    .join(
                        models.ProductModelVersion,
                        models.ProductModelVersion.id == models.ProductModelLineVariant.version_id,
                    )
                    .filter(
                        models.ProductModelLineVariant.is_archived.is_(False),
                        models.ProductModelVersion.is_archived.is_(False),
                        models.ProductModelVersion.model_id == bound_model_row.id,
                        models.ProductModelVersion.version_kind == "standard",
                        models.ProductModelVersion.version_status == "published",
                    )
                    .all()
                )
                for (cond,) in vrows:
                    if not isinstance(cond, dict):
                        continue
                    for ck in ("spec_contains_all", "spec_contains_any"):
                        for tok in (cond.get(ck) or []):
                            ts = str(tok or "").strip()
                            if not ts or ":" in ts:
                                continue
                            bound_kws.append(ts)
            except Exception:  # noqa: BLE001
                pass
        if bound_kws:
            combined = " ".join(
                x for x in [str(sample_text or ""), str(product_name or ""), str(sku_spec_text or "")] if x
            ).strip()
            return _mismatch_warnings_by_keywords_v2(
                db, combined_text=combined, bound_model_id=str(bound_model_id)
            )
        # 已绑模型没配 recognition_keywords → 走 Tier 2 兜底

    # Tier 2: 硬编码品类组（向后兼容 + 兜底，仅在 Tier 1 不可用时启用）
    s = str(sample_text or "")
    p = str(product_name or "")
    sku_spec = str(sku_spec_text or "")
    combined = f"{s}；{p}；{sku_spec}"
    combined = combined.replace("（", "(").replace("）", ")").strip()
    target = str(target_label or "").strip()
    if not combined or not target:
        return []

    # Mutually exclusive-ish category markers (Phase0 heuristic)
    groups: List[Dict[str, Any]] = [
        {"id": "siquan_dian", "label": "丝圈/地垫", "keys": ["丝圈", "地垫"]},
        {"id": "baozhen", "label": "抱枕", "keys": ["抱枕", "枕套"]},
        {"id": "ditan", "label": "地毯", "keys": ["地毯"]},
        {"id": "zhuodian", "label": "桌垫", "keys": ["桌垫"]},
        {"id": "zhuangshihua", "label": "装饰画/画框", "keys": ["装饰画", "画框", "挂画"]},
    ]

    def _hit(text: str, keys: List[str]) -> bool:
        return any(k and k in text for k in (keys or []))

    sample_hits = [g for g in groups if _hit(combined, g["keys"])]
    if not sample_hits:
        return []
    target_hits = [g for g in groups if _hit(target, g["keys"])]

    # If target has an explicit category marker and it's disjoint with sample markers -> strong warning.
    sample_ids = {g["id"] for g in sample_hits}
    target_ids = {g["id"] for g in target_hits}
    if target_ids and sample_ids.isdisjoint(target_ids):
        return [
            f"疑似选错目标：样本更像“{'/'.join([g['label'] for g in sample_hits])}”，但当前目标更像“{'/'.join([g['label'] for g in target_hits])}”。请确认未误选。"
        ]

    # If sample has a clear marker but target contains none -> softer warning.
    if not target_ids:
        return [
            f"请确认目标是否选对：样本命中“{'/'.join([g['label'] for g in sample_hits])}”关键词，但目标名称未包含对应关键词。"
        ]

    return []


def _apply_preparse_no_commit(db: Session, *, sku_master_row: models.SkuMaster, spec_text: str, requested_by: Optional[str]) -> None:
    """
    Same effect as save_spec_preparse but without per-row commit/refresh.
    """
    row = sku_master_row
    text = (spec_text or "").strip()
    if not text:
        return
    spec_hash = _sha1_text(text)
    parsed0 = spec_parser_service.parse_spec(text)
    _ensure_spec_parse_snapshot(db, spec_hash=spec_hash, spec_text=text, parsed=parsed0)

    parsed = spec_parser_service.parse_spec(text)
    dims = {
        "width_cm": parsed.get("width_cm"),
        "height_cm": parsed.get("height_cm"),
        "diameter_cm": parsed.get("diameter_cm"),
        "area_m2": parsed.get("area_m2"),
        "perimeter_m": parsed.get("perimeter_m"),
    }
    has_dims = any(dims.get(k) not in (None, "") for k in ("width_cm", "height_cm", "diameter_cm"))

    meta = dict(row.metadata_json or {})
    meta.update(
        {
            "preparse_spec_text": text,
            "preparse_spec_hash": spec_hash,
            "preparse_parser_version": PARSER_VERSION,
            "preparse_dimensions": _json_safe(dims),
            "preparse_tokens": list(parsed.get("tokens") or []),
            "preparse_has_dims": bool(has_dims),
            "preparse_saved_at": _utcnow().isoformat(),
            "preparse_saved_by": (requested_by or meta.get("requested_by") or None),
        }
    )
    row.metadata_json = meta


def preview_bind_by_model(
    db: Session,
    *,
    model_id: str,
    sku_master_ids: List[str],
    requested_by: Optional[str],
    allow_rebind: bool = False,
) -> Dict[str, Any]:
    version = _get_published_standard_version_for_model_id(db, model_id)
    model = getattr(version, "model", None)
    target_label = f"{getattr(model, 'model_code', '')} {getattr(model, 'model_name', '')}".strip()
    ids = [str(x).strip() for x in (sku_master_ids or []) if str(x).strip()]
    total_selected = len(ids)
    if total_selected <= 0:
        return {"total_selected": 0, "can_bind": 0, "skip_already_bound": 0, "skip_missing_barcode": 0, "hard_errors": 0, "items": []}

    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(list(set(ids))), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    by_id = {r.id: r for r in rows}

    items: List[Dict[str, Any]] = []
    can_bind = 0
    skip_already_bound = 0
    skip_missing_barcode = 0
    hard_errors = 0

    for sid in ids:
        row = by_id.get(sid)
        if not row:
            items.append(
                {
                    "sku_master_id": sid,
                    "status": "hard_error",
                    "hard_errors": ["sku_master not found"],
                    "warnings": [],
                    "model_version_id": str(version.id),
                }
            )
            hard_errors += 1
            continue
        sku = (row.erp_sku_barcode or "").strip() or None
        base = {"sku_master_id": row.id, "sku_code": sku, "channel": row.channel, "model_version_id": str(version.id)}
        if not sku:
            items.append({**base, "status": "skip_missing_barcode", "hard_errors": [], "warnings": []})
            skip_missing_barcode += 1
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已有绑定且不允许覆盖"]})
            skip_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(version.id) and allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已绑定到目标版本"]})
            skip_already_bound += 1
            continue

        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if not norm_spec:
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": ["无发货交易规格样本：本次绑定未做BOM试算校验"],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            can_bind += 1
            continue

        try:
            bom = bom_generation_service.generate_bom(
                db,
                spec_text=norm_spec,
                model_version_id=str(version.id),
                sku_code=sku,
                quantity=Decimal("1"),
                include_disabled_variants=False,
            )
            trace = bom.get("trace") if isinstance(bom.get("trace"), dict) else {}
            costing = trace.get("costing") if isinstance(trace.get("costing"), dict) else {}
            inventory = trace.get("inventory") if isinstance(trace.get("inventory"), dict) else {}
            warn2 = _mismatch_warnings_by_keywords(
                sample_text=norm_spec,
                sku_spec_text=getattr(row, "spec_text", None),
                product_name=getattr(row, "product_name", None),
                target_label=target_label or str(version.id),
            )
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": warn2,
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                    "cost_total": costing.get("total_cost"),
                    "inventory_line_count": inventory.get("inventory_line_count") if isinstance(inventory, dict) else None,
                }
            )
            can_bind += 1
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    **base,
                    "status": "hard_error",
                    "hard_errors": [f"BOM试算失败：{str(exc)}"],
                    "warnings": [],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            hard_errors += 1

    return {
        "total_selected": total_selected,
        "can_bind": can_bind,
        "skip_already_bound": skip_already_bound,
        "skip_missing_barcode": skip_missing_barcode,
        "hard_errors": hard_errors,
        "items": items,
    }


def preview_bind_by_bundle_template(
    db: Session,
    *,
    template_id: str,
    preset_selector: Optional[str] = None,
    sku_master_ids: List[str],
    requested_by: Optional[str],
    allow_rebind: bool = False,
) -> Dict[str, Any]:
    tid = (template_id or "").strip()
    if not tid:
        raise ValueError("template_id 不能为空")
    selector = str(preset_selector or "").strip().upper() or None
    if not selector:
        raise ValueError("preset_selector 不能为空")
    t = bundle_template_service.get_template(db, tid, include_archived=True)
    if not t or getattr(t, "is_archived", False):
        raise ValueError("套装模板不存在或已归档")
    v = bundle_template_service.get_latest_published_version(db, template_id=tid)
    if not v:
        raise ValueError("套装模板尚未发布版本：请先在“套装模板”里点“发布为新版本”")
    bundle_model_version = product_model_service.ensure_bundle_model_version(
        db, template_version=v, preset_selector=selector, requested_by=requested_by
    )
    target_label = f"{str(getattr(t, 'code', '') or '').strip()} {str(getattr(t, 'name', '') or '').strip()}".strip()

    ids = [str(x).strip() for x in (sku_master_ids or []) if str(x).strip()]
    total_selected = len(ids)
    if total_selected <= 0:
        return {"total_selected": 0, "can_bind": 0, "skip_already_bound": 0, "skip_missing_barcode": 0, "hard_errors": 0, "items": []}

    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(list(set(ids))), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    by_id = {r.id: r for r in rows}

    items: List[Dict[str, Any]] = []
    can_bind = 0
    skip_already_bound = 0
    skip_missing_barcode = 0
    hard_errors = 0

    for sid in ids:
        row = by_id.get(sid)
        if not row:
            items.append(
                {
                    "sku_master_id": sid,
                    "status": "hard_error",
                    "hard_errors": ["sku_master not found"],
                    "warnings": [],
                    "model_version_id": str(bundle_model_version.id),
                }
            )
            hard_errors += 1
            continue
        sku = (row.erp_sku_barcode or "").strip() or None
        base = {"sku_master_id": row.id, "sku_code": sku, "channel": row.channel, "model_version_id": str(bundle_model_version.id)}
        if not sku:
            items.append({**base, "status": "skip_missing_barcode", "hard_errors": [], "warnings": []})
            skip_missing_barcode += 1
            continue

        meta = dict(row.metadata_json or {})
        existing_tid = str(meta.get("bundle_template_id") or "").strip()
        if existing_tid and not allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已绑定套装模板且不允许覆盖"]})
            skip_already_bound += 1
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已有绑定且不允许覆盖"]})
            skip_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(bundle_model_version.id) and allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已绑定到目标套装版本"]})
            skip_already_bound += 1
            continue

        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if not norm_spec:
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": ["无发货交易规格样本：本次绑定未做BOM试算校验"],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            can_bind += 1
            continue

        try:
            bom = bom_generation_service.generate_bom_by_spec(
                db,
                spec_text=norm_spec,
                sku_code=sku,
                include_disabled_variants=False,
                return_components=False,
                bundle_template_version_id=str(v.id),
                bundle_preset_selector=selector,
            )
            trace = bom.get("trace") if isinstance(bom.get("trace"), dict) else {}
            costing = trace.get("costing") if isinstance(trace.get("costing"), dict) else {}
            inventory = trace.get("inventory") if isinstance(trace.get("inventory"), dict) else {}
            warn2 = _mismatch_warnings_by_keywords(
                sample_text=norm_spec,
                sku_spec_text=getattr(row, "spec_text", None),
                product_name=getattr(row, "product_name", None),
                target_label=target_label or str(bundle_model_version.id),
            )
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": warn2,
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                    "cost_total": costing.get("total_cost"),
                    "inventory_line_count": inventory.get("inventory_line_count") if isinstance(inventory, dict) else None,
                }
            )
            can_bind += 1
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    **base,
                    "status": "hard_error",
                    "hard_errors": [f"BOM试算失败：{str(exc)}"],
                    "warnings": [],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            hard_errors += 1

    return {
        "total_selected": total_selected,
        "can_bind": can_bind,
        "skip_already_bound": skip_already_bound,
        "skip_missing_barcode": skip_missing_barcode,
        "hard_errors": hard_errors,
        "items": items,
    }


def bind_sku_master_by_model_bulk(
    db: Session,
    *,
    model_id: str,
    requested_by: Optional[str],
    limit: int = 200,
    bound_state: str = "unbound",
    allow_rebind: bool = False,
    search: Optional[str] = None,
    channel: Optional[str] = None,
    match_status: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
    variant_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bulk bind for manual workbench: bind *unbound* sku masters matched by filters.
    Designed for UI "implicit select all across pages", with an exclusion list.

    `variant_code`：可选，整批 SKU 共享的"最终绑定变体编码"。同 bind_sku_master_by_model。
    """
    version = _get_published_standard_version_for_model_id(db, model_id)
    norm_variant_code = (str(variant_code).strip().upper() or None) if variant_code else None
    limit2 = max(min(int(limit or 200), 2000), 1)

    excluded_list = list(set([str(x) for x in (excluded_sku_master_ids or []) if str(x).strip()]))
    skipped_excluded = len(excluded_list)

    q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))

    if search:
        s = f"%{search.strip()}%"
        q = q.filter(
            (models.SkuMaster.erp_sku_barcode.ilike(s))
            | (models.SkuMaster.product_name.ilike(s))
            | (models.SkuMaster.product_code.ilike(s))
        )
    if channel:
        q = q.filter(models.SkuMaster.channel == channel)
    if match_status:
        q = q.filter(models.SkuMaster.match_status == match_status)

    # enforce bound/unbound state (server-side) via correlated EXISTS subquery
    if bound_model_id or bound_model_code or bound_version_id:
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
            )
            .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModel.is_archived.is_(False),
            )
        )
        if bound_version_id:
            subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
        if bound_model_id:
            subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
        if bound_model_code:
            subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
    else:
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
        )
    state = str(bound_state or "unbound").strip().lower()
    if state not in ("unbound", "bound", "all"):
        state = "unbound"
    if state == "unbound":
        q = q.filter(~subq.exists())
    elif state == "bound":
        q = q.filter(subq.exists())
    else:
        # all: no filter
        pass

    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712

    if preparse_state:
        state = str(preparse_state).strip().lower()
        ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
        if state in ("parsed", "done", "yes", "1", "true"):
            q = q.filter(func.coalesce(ph, "") != "")
        elif state in ("unparsed", "none", "no", "0", "false"):
            q = q.filter(func.coalesce(ph, "") == "")

    def _parse_terms(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        s2 = str(raw)
        for ch in ("，", ";", "；", "\n", "\t"):
            s2 = s2.replace(ch, " ")
        parts = [p.strip() for p in s2.split(" ") if p.strip()]
        out: List[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    include_list = _parse_terms(include_terms)
    exclude_list = _parse_terms(exclude_terms)
    scope = (match_scope or "auto").strip()
    if scope not in ("auto", "spec", "name", "spec_or_name"):
        scope = "auto"

    name_channels = ["小红书", "京东"]

    def _field_expr_for_scope(term: str):
        pattern = f"%{term}%"
        spec_hit = models.SkuMaster.spec_text.ilike(pattern)
        name_hit = models.SkuMaster.product_name.ilike(pattern)
        if scope == "spec":
            return spec_hit
        if scope == "name":
            return name_hit
        if scope == "spec_or_name":
            return spec_hit | name_hit
        return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (
            ~models.SkuMaster.channel.in_(name_channels) & spec_hit
        )

    for t in include_list:
        q = q.filter(_field_expr_for_scope(t))
    for t in exclude_list:
        q = q.filter(~_field_expr_for_scope(t))

    if excluded_list:
        q = q.filter(~models.SkuMaster.id.in_(excluded_list))

    # Fetch limit+1 to compute has_more without an extra COUNT()
    rows = (
        q.order_by(models.SkuMaster.updated_at.desc())
        .limit(limit2 + 1)
        .all()
    )
    has_more = len(rows) > limit2
    batch_rows = rows[:limit2]

    bound_count = 0
    skipped_already_bound = 0
    skipped_missing_barcode = 0
    errors: List[Dict[str, Any]] = []
    now_iso = _utcnow().isoformat()

    for row in batch_rows:
        sku = (row.erp_sku_barcode or "").strip()
        if not sku:
            skipped_missing_barcode += 1
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            skipped_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(version.id) and allow_rebind:
            skipped_already_bound += 1
            continue
        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if norm_spec:
            try:
                bom_generation_service.generate_bom(
                    db,
                    spec_text=norm_spec,
                    model_version_id=str(version.id),
                    sku_code=sku,
                    quantity=Decimal("1"),
                    include_disabled_variants=False,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"sku_master_id": row.id, "sku_code": sku, "error": f"BOM试算失败：{str(exc)}"})
                continue
        try:
            product_model_service.bind_sku_to_version(
                db,
                sku_code=sku,
                version_id=version.id,
                source_system="sku_master_manual_bulk",
                metadata={
                    "requested_by": requested_by,
                    "sku_master_id": row.id,
                    "binding_method": "manual_by_model_bulk_rebind" if allow_rebind else "manual_by_model_bulk",
                    "skip_prefix_check": True,
                },
            )
            # 先跑 preparse 再写"我们要落的字段"——避免 preparse 内部 read-modify-write
            # 把 model_bound_at / bound_variant_code 抹掉。详见 bind_sku_master_by_model 同位置注释。
            if norm_spec:
                try:
                    _apply_preparse_no_commit(db, sku_master_row=row, spec_text=norm_spec, requested_by=requested_by)
                except Exception:
                    pass
            meta = dict(getattr(row, "metadata_json", None) or {})
            meta.update(
                {
                    "model_bound_at": now_iso,
                    "model_bound_by": (requested_by or meta.get("requested_by") or None),
                    "model_binding_method": "manual_by_model_bulk_rebind" if allow_rebind else "manual_by_model_bulk",
                    "binding_validation_state": "sampled" if norm_spec else "no_shipment_sample",
                }
            )
            if norm_variant_code:
                meta["bound_variant_code"] = norm_variant_code
            else:
                meta.pop("bound_variant_code", None)
            _clear_suspect_misbind_resolved(meta)
            row.metadata_json = meta
            try:
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(row, "metadata_json")
            except Exception:
                pass
            bound_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_master_id": row.id, "sku_code": sku, "error": str(exc)})

    db.commit()
    return {
        "batch_candidates": len(batch_rows),
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "skipped_missing_barcode": skipped_missing_barcode,
        "skipped_excluded": skipped_excluded,
        "errors": errors,
        "has_more": has_more,
    }


# ============================================================================
# update_sku_master_field_bulk — 通用字段批量更新 (商品档案 / 商品关联 共用入口)
# ============================================================================
#
# 设计 (2026-05-16 与用户对齐, 见 jackyun_erp_goods_master_sync_backlog.md §17)
# - 商品档案是【运营做字段维护的 UI】(改工艺 / 打标签)
# - 商品关联是【本系统侧的批量落库引擎】("一键跑完"那一套筛-分批-写库框架)
# - 当用户在商品档案上批量改字段, 不重新造写库轮子, 直接复用本函数 —
#   它跟 bind_sku_master_by_model_bulk 是平级动作, 共用同一套范式
#   (筛选 / excluded_ids / limit+1+has_more / 进度 / 错误)
#
# 安全策略 — ALLOWED_FIELDS 白名单
# - 只允许编辑业务字段 (production_process, metadata.erp.sku_flag)
# - 严禁碰 binding 字段 (active_model_version_id / bound_variant_code / bundle_*)
#   ↑ 这些字段必须走 bind_*_bulk / unbind, 它们有 BOM 试算 / 版本校验等业务规则
#
# ERP 反写
# - 本函数只管"本系统落库". 反写 ERP 是【独立模块】(erp_writeback_service),
#   由 mutation callback 触发 enqueue 即可, 不在本函数内部做 ERP 通信
# ----------------------------------------------------------------------------

# 字段白名单 — 只列出本系统允许"批量改字段"的字段
# kind:
#   - "physical"        : 直接写 SkuMaster 物理列
#   - "metadata_array"  : 写 metadata_json 嵌套路径下的 JSON 数组
# modes:
#   - "set"             : 完全替换 (字符串字段 / 数组整体替换)
#   - "append_unique"   : 数组追加 (去重, 仅 metadata_array 支持)
#   - "remove"          : 数组移除 (仅 metadata_array 支持)
_UPDATE_BULK_ALLOWED_FIELDS: Dict[str, Dict[str, Any]] = {
    "production_process": {
        "kind": "physical",
        "column": "production_process",
        "modes": {"set"},
        "value_type": "string_or_null",
    },
    "metadata.erp.sku_flag": {
        "kind": "metadata_array",
        "json_path": ("erp", "sku_flag"),
        "modes": {"set", "append_unique", "remove"},
        "value_type": "string_array",
    },
    # 商家标签 - 网店"商家编码" 物理列. 允许编辑让运营把脏值 (Q26041801KB8-001)
    # 手动归一化为干净的标准变体码 (KB8-001). 见 §17 三标签架构.
    # 不允许批量"按筛选改 N 万条", 因为不同 SKU 的脏值各不相同, 必须人工逐个看;
    # 后端不限制 (允许批量), 但 UI 上只在抽屉单条入口暴露.
    "shop_spec_code": {
        "kind": "physical",
        "column": "shop_spec_code",
        "modes": {"set"},
        "value_type": "string_or_null",
    },
    # 属性规格 - 商品档案 spec_text (吉客云后台「规格」/ skuName).
    # 允许在抽屉里手动覆盖, 用于发货规格已更新但商品档案没更新的场景.
    # 同 shop_spec_code 一样: 后端允许批量, UI 仅在抽屉单条入口暴露.
    "spec_text": {
        "kind": "physical",
        "column": "spec_text",
        "modes": {"set"},
        "value_type": "string_or_null",
    },
}


def _coerce_update_bulk_value(field_name: str, raw: Any, spec: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
    """Normalize incoming value per ALLOWED_FIELDS spec.

    Returns ``(ok, normalized_value, error_message)``.
    """
    vtype = spec.get("value_type")
    if vtype == "string_or_null":
        if raw in (None, ""):
            return True, None, None
        s = str(raw).strip()
        return True, (s if s else None), None
    if vtype == "string_array":
        if raw is None:
            return True, [], None
        if isinstance(raw, str):
            # accept comma/semicolon-separated input as convenience
            parts = [p.strip() for p in re.split(r"[,;，；\n\t]+", raw) if p.strip()]
            return True, parts, None
        if isinstance(raw, (list, tuple)):
            out: List[str] = []
            seen: set[str] = set()
            for x in raw:
                if x in (None, ""):
                    continue
                s = str(x).strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                out.append(s)
            return True, out, None
        return False, None, f"字段 {field_name} 需要字符串数组, 收到 {type(raw).__name__}"
    return False, None, f"字段 {field_name} 缺少 value_type 配置, 联系开发"


def _apply_update_bulk_mutation(
    row: "models.SkuMaster",
    *,
    field_name: str,
    spec: Dict[str, Any],
    mode: str,
    new_value: Any,
    now_iso: str,
    requested_by: Optional[str],
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Apply one row's mutation. Returns ``(status, audit_entry)``.

    status: "updated" | "no_change" | "error:<msg>"
    audit_entry: dict to be merged into metadata_json.field_writeback (optional)
    """
    kind = spec.get("kind")
    if kind == "physical":
        col = spec["column"]
        current = getattr(row, col, None)
        if mode != "set":
            return f"error:物理列 {col} 仅支持 set 模式", None
        if (current or None) == (new_value or None):
            return "no_change", None
        setattr(row, col, new_value)
        return "updated", {
            "field": field_name,
            "mode": mode,
            "old": current,
            "new": new_value,
            "at": now_iso,
            "by": requested_by,
        }

    if kind == "metadata_array":
        path = spec["json_path"]  # e.g. ("erp", "sku_flag")
        meta = dict(getattr(row, "metadata_json", None) or {})
        # walk to parent of last key, creating intermediate dicts
        cursor = meta
        for k in path[:-1]:
            if not isinstance(cursor.get(k), dict):
                cursor[k] = {}
            cursor = cursor[k]
        leaf_key = path[-1]
        current_list = cursor.get(leaf_key)
        if not isinstance(current_list, list):
            current_list = []

        if mode == "set":
            next_list = list(new_value or [])
        elif mode == "append_unique":
            seen = set(str(x) for x in current_list)
            next_list = list(current_list)
            for x in (new_value or []):
                if str(x) not in seen:
                    next_list.append(x)
                    seen.add(str(x))
        elif mode == "remove":
            drop = set(str(x) for x in (new_value or []))
            next_list = [x for x in current_list if str(x) not in drop]
        else:
            return f"error:metadata 字段不支持 mode={mode}", None

        # dedupe + stable-stringify for comparison
        if [str(x) for x in current_list] == [str(x) for x in next_list]:
            return "no_change", None
        cursor[leaf_key] = next_list
        row.metadata_json = meta
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(row, "metadata_json")
        except Exception:
            pass
        return "updated", {
            "field": field_name,
            "mode": mode,
            "old": current_list,
            "new": next_list,
            "at": now_iso,
            "by": requested_by,
        }

    return f"error:未知 kind={kind}", None


def update_sku_master_field_bulk(
    db: Session,
    *,
    field_name: str,
    new_value: Any,
    mode: str = "set",
    requested_by: Optional[str],
    dry_run: bool = False,
    # 显式 ID 列表 (混合模式: 如提供则跳过 filter, 直接按 ID 操作)
    sku_master_ids: Optional[List[str]] = None,
    # 筛选参数 (与 bind_sku_master_by_model_bulk 同型, 缺失时不过滤)
    limit: int = 200,
    search: Optional[str] = None,
    channel: Optional[str] = None,
    match_status: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    bound_state: Optional[str] = None,
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    bundle_bound_state: Optional[str] = None,
    bundle_template_id: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """通用字段批量更新 — 商品档案 / 商品关联 共用入口.

    工作流:
    1. 白名单校验 field_name → 必须在 _UPDATE_BULK_ALLOWED_FIELDS 内
    2. mode 校验 → 必须在该字段允许的 modes 内
    3. value 归一化 → 按 value_type coerce
    4. 候选行获取:
       - 如 sku_master_ids 非空: 按 ID 列表精确取 (不走筛选, 不限 limit)
       - 否则按筛选 query (limit+1 + has_more)
    5. 逐行应用 mutation, 收集 updated/no_change/errors
    6. dry_run=True 时不 commit (仅返回预演结果)
    7. 返回与 bind_*_bulk 同结构的统计

    Returns dict:
      - batch_candidates: int
      - updated_count: int
      - skipped_no_change: int
      - skipped_excluded: int
      - errors: List[{sku_master_id, sku_code, error}]
      - has_more: bool (仅筛选模式有意义)
      - dry_run: bool
      - field_name / mode / new_value (echo for caller audit)
    """
    # ---- 1. 白名单校验 ----
    spec = _UPDATE_BULK_ALLOWED_FIELDS.get(field_name)
    if spec is None:
        allowed = sorted(_UPDATE_BULK_ALLOWED_FIELDS.keys())
        raise ValueError(f"不允许批量改字段: {field_name}. 允许字段: {allowed}")
    mode_norm = str(mode or "set").strip().lower()
    if mode_norm not in spec["modes"]:
        raise ValueError(
            f"字段 {field_name} 不支持 mode={mode_norm}, 允许: {sorted(spec['modes'])}"
        )

    # ---- 2. 值归一化 ----
    ok, normalized_value, err = _coerce_update_bulk_value(field_name, new_value, spec)
    if not ok:
        raise ValueError(err or "value 校验失败")

    # ---- 3. 候选行 ----
    limit2 = max(min(int(limit or 200), 2000), 1)
    excluded_list = list(set([str(x) for x in (excluded_sku_master_ids or []) if str(x).strip()]))
    skipped_excluded = len(excluded_list)
    has_more = False

    if sku_master_ids:
        # 显式 ID 模式 (单条编辑 / 精确多选): 不走筛选, 不限 limit
        id_list = list(dict.fromkeys([str(x).strip() for x in sku_master_ids if str(x).strip()]))
        if excluded_list:
            id_list = [x for x in id_list if x not in set(excluded_list)]
        if not id_list:
            return {
                "batch_candidates": 0, "updated_count": 0, "skipped_no_change": 0,
                "skipped_excluded": skipped_excluded, "errors": [], "has_more": False,
                "dry_run": bool(dry_run), "field_name": field_name, "mode": mode_norm,
                "new_value": normalized_value,
            }
        batch_rows = (
            db.query(models.SkuMaster)
            .filter(models.SkuMaster.id.in_(id_list))
            .filter(models.SkuMaster.is_archived.is_(False))
            .all()
        )
    else:
        # 筛选模式 (跨页隐式全选): 沿用 bind_*_bulk 范式
        q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))

        if search:
            s = f"%{search.strip()}%"
            q = q.filter(
                (models.SkuMaster.erp_sku_barcode.ilike(s))
                | (models.SkuMaster.product_name.ilike(s))
                | (models.SkuMaster.product_code.ilike(s))
            )
        if channel:
            q = q.filter(models.SkuMaster.channel == channel)
        if match_status:
            q = q.filter(models.SkuMaster.match_status == match_status)

        if bound_model_id or bound_model_code or bound_version_id:
            subq = (
                db.query(models.SkuModelVersionMapping.id)
                .join(models.ProductModelVersion, models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id)
                .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
                .filter(
                    models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                    models.ProductModelVersion.is_archived.is_(False),
                    models.ProductModel.is_archived.is_(False),
                )
            )
            if bound_version_id:
                subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
            if bound_model_id:
                subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
            if bound_model_code:
                subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
        else:
            subq = (
                db.query(models.SkuModelVersionMapping.id)
                .filter(
                    models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.is_archived.is_(False),
                )
            )
        bstate = str(bound_state or "all").strip().lower()
        if bstate == "unbound":
            q = q.filter(~subq.exists())
        elif bstate == "bound":
            q = q.filter(subq.exists())

        # bundle filter (同 list_sku_master 范式)
        bt_id_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_id"].as_string(), "")
        bp_sel_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_preset_selector"].as_string(), "")
        if bundle_bound_state:
            bbs = str(bundle_bound_state).strip().lower()
            if bbs in ("bound", "yes", "1", "true"):
                q = q.filter(bt_id_expr != "")
            elif bbs in ("unbound", "none", "no", "0", "false"):
                q = q.filter(bt_id_expr == "")
        if bundle_template_id:
            q = q.filter(bt_id_expr == str(bundle_template_id).strip())
        if bundle_preset_selector:
            q = q.filter(func.upper(bp_sel_expr) == str(bundle_preset_selector).strip().upper())

        if spec_mismatch is True:
            q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712

        if preparse_state:
            pstate = str(preparse_state).strip().lower()
            ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
            if pstate in ("parsed", "done", "yes", "1", "true"):
                q = q.filter(func.coalesce(ph, "") != "")
            elif pstate in ("unparsed", "none", "no", "0", "false"):
                q = q.filter(func.coalesce(ph, "") == "")

        def _parse_terms(raw: Optional[str]) -> List[str]:
            if not raw:
                return []
            s2 = str(raw)
            for ch in ("，", ";", "；", "\n", "\t"):
                s2 = s2.replace(ch, " ")
            parts = [p.strip() for p in s2.split(" ") if p.strip()]
            out: List[str] = []
            seen: set[str] = set()
            for p in parts:
                if p in seen:
                    continue
                seen.add(p)
                out.append(p)
            return out

        include_list = _parse_terms(include_terms)
        exclude_list = _parse_terms(exclude_terms)
        scope = (match_scope or "auto").strip()
        if scope not in ("auto", "spec", "name", "spec_or_name"):
            scope = "auto"
        name_channels = ["小红书", "京东"]

        def _field_expr_for_scope(term: str):
            pattern = f"%{term}%"
            spec_hit = models.SkuMaster.spec_text.ilike(pattern)
            name_hit = models.SkuMaster.product_name.ilike(pattern)
            if scope == "spec":
                return spec_hit
            if scope == "name":
                return name_hit
            if scope == "spec_or_name":
                return spec_hit | name_hit
            return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (
                ~models.SkuMaster.channel.in_(name_channels) & spec_hit
            )

        for t in include_list:
            q = q.filter(_field_expr_for_scope(t))
        for t in exclude_list:
            q = q.filter(~_field_expr_for_scope(t))

        if excluded_list:
            q = q.filter(~models.SkuMaster.id.in_(excluded_list))

        rows_all = (
            q.order_by(models.SkuMaster.updated_at.desc())
            .limit(limit2 + 1)
            .all()
        )
        has_more = len(rows_all) > limit2
        batch_rows = rows_all[:limit2]

    # ---- 4. 应用 mutation ----
    updated_count = 0
    skipped_no_change = 0
    errors: List[Dict[str, Any]] = []
    now_iso = _utcnow().isoformat()

    for row in batch_rows:
        try:
            status, _audit = _apply_update_bulk_mutation(
                row,
                field_name=field_name,
                spec=spec,
                mode=mode_norm,
                new_value=normalized_value,
                now_iso=now_iso,
                requested_by=requested_by,
            )
            if status == "updated":
                updated_count += 1
            elif status == "no_change":
                skipped_no_change += 1
            elif status.startswith("error:"):
                errors.append({
                    "sku_master_id": row.id,
                    "sku_code": (row.erp_sku_barcode or ""),
                    "error": status[len("error:"):],
                })
        except Exception as exc:  # noqa: BLE001
            errors.append({
                "sku_master_id": row.id,
                "sku_code": (row.erp_sku_barcode or ""),
                "error": str(exc),
            })

    # ---- 5. commit (dry_run 时 rollback) ----
    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "batch_candidates": len(batch_rows),
        "updated_count": updated_count,
        "skipped_no_change": skipped_no_change,
        "skipped_excluded": skipped_excluded,
        "errors": errors,
        "has_more": has_more,
        "dry_run": bool(dry_run),
        "field_name": field_name,
        "mode": mode_norm,
        "new_value": normalized_value,
        "requested_by": requested_by,
    }


# ============================================================================
# 抽屉「字段编辑」统一表单 — 单条 SKU 4 字段一次保存 + 自动重识别
# ----------------------------------------------------------------------------
# 配套前端: ProductInfoDetailDrawer.tsx 「字段编辑」卡片 (合并原 3 个分散卡片).
#
# 设计要点:
# 1. 复用 update_sku_master_field_bulk(sku_master_ids=[id]) 单条入口, 避免重复代码.
# 2. 用 ``update_fields`` 显式列表区分 "未传字段" 与 "传 None 清空".
# 3. ``shop_spec_code`` 被修改后自动触发 auto_bind_execute, 让系统编码 (bound_variant_code)
#    跟随商家编码重新识别 (P0 锚点 > P1 关键词).
# 4. 返回 ``row`` (最新的 SkuMaster ORM 对象, 已 attach 识别字段) + 子调用统计,
#    让前端立即拿到 recognition_source / bound_variant_code 等更新后的值.
# ============================================================================

_EDIT_FORM_FIELD_MAP: Dict[str, str] = {
    # 表单字段 → update_sku_master_field_bulk 的 field_name
    "production_process": "production_process",
    "sku_flag": "metadata.erp.sku_flag",
    "shop_spec_code": "shop_spec_code",
    "spec_text": "spec_text",
}


def edit_sku_form(
    db: Session,
    *,
    sku_master_id: str,
    requested_by: Optional[str],
    update_fields: List[str],
    production_process: Optional[str] = None,
    sku_flag: Optional[List[str]] = None,
    shop_spec_code: Optional[str] = None,
    spec_text: Optional[str] = None,
    trigger_rebind: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """单条 SKU 统一表单编辑 (4 字段任意子集 + 自动重识别).

    Args:
        sku_master_id: 必填.
        update_fields: 显式声明要更新的字段名 (production_process/sku_flag/
            shop_spec_code/spec_text). 不在此列表中的字段即使带了值也不会被改, 避免
            "未传 vs 传 None" 歧义.
        production_process: 当 "production_process" 在 update_fields 中时生效;
            None/"" 视为清空字段.
        sku_flag: 当 "sku_flag" 在 update_fields 中时生效; None 视为清空数组.
        shop_spec_code: 同上规则; 变更后会触发 auto_bind_execute (除非 trigger_rebind=False).
        spec_text: 同上规则.
        trigger_rebind: shop_spec_code 变更后是否自动重识别 (默认 True).
        dry_run: 预演模式; True 时所有子调用 rollback, 不写库, 也不重识别.

    Returns dict:
        - sku_master_id
        - row: SkuMaster ORM 对象 (最新值, 含 attach 后的识别字段) | None
        - per_field_results: [{field, updated, no_change, errors}]
        - rebind: {triggered, bound, before_variant, after_variant, errors}
        - dry_run
    """
    row = db.get(models.SkuMaster, sku_master_id)
    if not row or row.is_archived:
        raise ValueError("SKU master not found")

    valid_fields = [f for f in (update_fields or []) if f in _EDIT_FORM_FIELD_MAP]
    if not valid_fields:
        # 啥都没改, 直接返回当前最新值供 UI 刷新
        fresh = get_sku_master(db, sku_master_id)
        return {
            "sku_master_id": sku_master_id,
            "row": fresh,
            "per_field_results": [],
            "rebind": {"triggered": False},
            "dry_run": bool(dry_run),
        }

    # 字段值映射 (用于按顺序传给 update_sku_master_field_bulk)
    value_map: Dict[str, Any] = {
        "production_process": production_process,
        "sku_flag": sku_flag,
        "shop_spec_code": shop_spec_code,
        "spec_text": spec_text,
    }

    per_field_results: List[Dict[str, Any]] = []
    shop_spec_changed = False

    for f in valid_fields:
        backend_field = _EDIT_FORM_FIELD_MAP[f]
        try:
            sub = update_sku_master_field_bulk(
                db,
                field_name=backend_field,
                new_value=value_map[f],
                mode="set",
                requested_by=requested_by,
                dry_run=dry_run,
                sku_master_ids=[sku_master_id],
            )
            per_field_results.append({
                "field": f,
                "updated": int(sub.get("updated_count", 0) or 0) > 0,
                "no_change": int(sub.get("skipped_no_change", 0) or 0) > 0,
                "errors": list(sub.get("errors") or []),
            })
            if f == "shop_spec_code" and int(sub.get("updated_count", 0) or 0) > 0:
                shop_spec_changed = True
        except ValueError as exc:
            per_field_results.append({
                "field": f,
                "updated": False,
                "no_change": False,
                "errors": [{"sku_master_id": sku_master_id, "error": str(exc)}],
            })

    # ---- 自动重识别: shop_spec_code 变了 且 触发开关开 且 非 dry_run ----
    rebind_info: Dict[str, Any] = {"triggered": False, "bound": False, "errors": []}
    if shop_spec_changed and trigger_rebind and not dry_run:
        # 重读 row 拿到 commit 后的最新 metadata
        db.expire(row)
        row = db.get(models.SkuMaster, sku_master_id)  # reload after commit
        before_meta = dict(getattr(row, "metadata_json", None) or {})
        before_variant = (before_meta.get("bound_variant_code") or "").strip().upper() or None

        try:
            # CRITICAL: auto_bind_preview 优先读 metadata.shop_spec_code (L5534),
            # update_sku_master_field_bulk 只改了物理列, 必须同步 metadata 否则
            # 重识别会用旧值. 这里把物理列的新值同步到 metadata.shop_spec_code.
            new_shop = (str(getattr(row, "shop_spec_code", "") or "").strip()) or None
            sync_meta = dict(getattr(row, "metadata_json", None) or {})
            if new_shop:
                sync_meta["shop_spec_code"] = new_shop
                sync_meta["shop_spec_code_source"] = "manual_edit"
                sync_meta["shop_spec_code_seen_at"] = _utcnow().isoformat()
            else:
                sync_meta.pop("shop_spec_code", None)
                sync_meta.pop("shop_spec_code_source", None)
            row.metadata_json = _json_safe(sync_meta)
            try:
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(row, "metadata_json")
            except Exception:  # noqa: BLE001
                pass
            db.commit()

            # auto_bind_execute 的 "已绑跳过" 逻辑会拦住已绑 SKU 的重识别
            # (见 L5625 get_active_sku_binding 命中就 skip).
            # 改商家编码场景下用户的诉求就是 "重走一遍识别", 所以先把旧绑定 deactivate,
            # 让 auto_bind_execute 把新识别结果作为新 active binding 落库.
            sku_code = (row.erp_sku_barcode or "").strip()
            existing = product_model_service.get_active_sku_binding(db, sku_code) if sku_code else None
            if existing is not None:
                existing.is_active = False
                meta_e = dict(existing.metadata_json or {})
                meta_e.setdefault("effective_through", _utcnow().isoformat())
                meta_e["deactivated_reason"] = "shop_spec_code_edited_trigger_rebind"
                meta_e["deactivated_by"] = requested_by
                existing.metadata_json = _json_safe(meta_e)
                db.commit()

            rebind_result = auto_bind_execute(
                db,
                limit=1,
                requested_by=requested_by,
                sku_master_ids=[sku_master_id],
            )
            db.expire(row)
            after_meta = dict(getattr(row, "metadata_json", None) or {})
            after_variant = (after_meta.get("bound_variant_code") or "").strip().upper() or None
            rebind_info = {
                "triggered": True,
                "bound": int(rebind_result.get("bound_count", 0) or 0) > 0,
                "skipped_already_bound": int(rebind_result.get("skipped_already_bound", 0) or 0) > 0,
                "before_variant": before_variant,
                "after_variant": after_variant,
                "errors": list(rebind_result.get("errors") or []),
            }
        except Exception as exc:  # noqa: BLE001
            rebind_info = {
                "triggered": True,
                "bound": False,
                "before_variant": before_variant,
                "after_variant": before_variant,
                "errors": [{"sku_master_id": sku_master_id, "error": f"rebind failed: {exc}"}],
            }

    # 取最新 row (含 attach 识别字段) 给前端
    fresh = get_sku_master(db, sku_master_id)
    return {
        "sku_master_id": sku_master_id,
        "row": fresh,
        "per_field_results": per_field_results,
        "rebind": rebind_info,
        "dry_run": bool(dry_run),
    }


def preview_bind_by_model_bulk(
    db: Session,
    *,
    model_id: str,
    requested_by: Optional[str],
    limit: int = 200,
    bound_state: str = "unbound",
    allow_rebind: bool = False,
    search: Optional[str] = None,
    channel: Optional[str] = None,
    match_status: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    version = _get_published_standard_version_for_model_id(db, model_id)
    model = getattr(version, "model", None)
    target_label = f"{getattr(model, 'model_code', '')} {getattr(model, 'model_name', '')}".strip()
    limit2 = max(min(int(limit or 200), 2000), 1)

    excluded_list = list(set([str(x) for x in (excluded_sku_master_ids or []) if str(x).strip()]))
    skipped_excluded = len(excluded_list)

    q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))

    if search:
        s = f"%{search.strip()}%"
        q = q.filter(
            (models.SkuMaster.erp_sku_barcode.ilike(s))
            | (models.SkuMaster.product_name.ilike(s))
            | (models.SkuMaster.product_code.ilike(s))
        )
    if channel:
        q = q.filter(models.SkuMaster.channel == channel)
    if match_status:
        q = q.filter(models.SkuMaster.match_status == match_status)

    # enforce bound/unbound state (server-side) via correlated EXISTS subquery
    if bound_model_id or bound_model_code or bound_version_id:
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
            )
            .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModel.is_archived.is_(False),
            )
        )
        if bound_version_id:
            subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
        if bound_model_id:
            subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
        if bound_model_code:
            subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
    else:
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
        )
    state = str(bound_state or "unbound").strip().lower()
    if state not in ("unbound", "bound", "all"):
        state = "unbound"
    if state == "unbound":
        q = q.filter(~subq.exists())
    elif state == "bound":
        q = q.filter(subq.exists())

    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712

    if preparse_state:
        state2 = str(preparse_state).strip().lower()
        ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
        if state2 in ("parsed", "done", "yes", "1", "true"):
            q = q.filter(func.coalesce(ph, "") != "")
        elif state2 in ("unparsed", "none", "no", "0", "false"):
            q = q.filter(func.coalesce(ph, "") == "")

    def _parse_terms(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        s2 = str(raw)
        for ch in ("，", ";", "；", "\n", "\t"):
            s2 = s2.replace(ch, " ")
        parts = [p.strip() for p in s2.split(" ") if p.strip()]
        out: List[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    include_list = _parse_terms(include_terms)
    exclude_list = _parse_terms(exclude_terms)
    scope = (match_scope or "auto").strip()
    if scope not in ("auto", "spec", "name", "spec_or_name"):
        scope = "auto"

    name_channels = ["小红书", "京东"]

    def _field_expr_for_scope(term: str):
        pattern = f"%{term}%"
        spec_hit = models.SkuMaster.spec_text.ilike(pattern)
        name_hit = models.SkuMaster.product_name.ilike(pattern)
        if scope == "spec":
            return spec_hit
        if scope == "name":
            return name_hit
        if scope == "spec_or_name":
            return spec_hit | name_hit
        return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (
            ~models.SkuMaster.channel.in_(name_channels) & spec_hit
        )

    for t in include_list:
        q = q.filter(_field_expr_for_scope(t))
    for t in exclude_list:
        q = q.filter(~_field_expr_for_scope(t))

    if excluded_list:
        q = q.filter(~models.SkuMaster.id.in_(excluded_list))

    rows = q.order_by(models.SkuMaster.updated_at.desc()).limit(limit2 + 1).all()
    has_more = len(rows) > limit2
    batch_rows = rows[:limit2]

    items: List[Dict[str, Any]] = []
    can_bind = 0
    skip_already_bound = 0
    skip_missing_barcode = 0
    hard_errors = 0

    for row in batch_rows:
        sku = (row.erp_sku_barcode or "").strip() or None
        base = {"sku_master_id": row.id, "sku_code": sku, "channel": row.channel, "model_version_id": str(version.id)}
        if not sku:
            items.append({**base, "status": "skip_missing_barcode", "hard_errors": [], "warnings": []})
            skip_missing_barcode += 1
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已有绑定且不允许覆盖"]})
            skip_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(version.id) and allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已绑定到目标版本"]})
            skip_already_bound += 1
            continue

        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if not norm_spec:
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": ["无发货交易规格样本：本次绑定未做BOM试算校验"],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            can_bind += 1
            continue

        try:
            bom = bom_generation_service.generate_bom(
                db,
                spec_text=norm_spec,
                model_version_id=str(version.id),
                sku_code=sku,
                quantity=Decimal("1"),
                include_disabled_variants=False,
            )
            trace = bom.get("trace") if isinstance(bom.get("trace"), dict) else {}
            costing = trace.get("costing") if isinstance(trace.get("costing"), dict) else {}
            inventory = trace.get("inventory") if isinstance(trace.get("inventory"), dict) else {}
            warn2 = _mismatch_warnings_by_keywords(
                sample_text=norm_spec,
                sku_spec_text=getattr(row, "spec_text", None),
                product_name=getattr(row, "product_name", None),
                target_label=target_label or str(version.id),
            )
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": warn2,
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                    "cost_total": costing.get("total_cost"),
                    "inventory_line_count": inventory.get("inventory_line_count") if isinstance(inventory, dict) else None,
                }
            )
            can_bind += 1
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    **base,
                    "status": "hard_error",
                    "hard_errors": [f"BOM试算失败：{str(exc)}"],
                    "warnings": [],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            hard_errors += 1

    return {
        "batch_candidates": len(batch_rows),
        "can_bind": can_bind,
        "skip_already_bound": skip_already_bound,
        "skip_missing_barcode": skip_missing_barcode,
        "hard_errors": hard_errors,
        "skipped_excluded": skipped_excluded,
        "has_more": has_more,
        "items": items,
    }


def bind_sku_master_by_bundle_template(
    db: Session,
    *,
    template_id: str,
    preset_selector: Optional[str] = None,
    sku_master_ids: List[str],
    requested_by: Optional[str],
    allow_rebind: bool = False,
) -> Dict[str, Any]:
    tid = (template_id or "").strip()
    if not tid:
        raise ValueError("template_id 不能为空")
    t = bundle_template_service.get_template(db, tid, include_archived=True)
    if not t or getattr(t, "is_archived", False):
        raise ValueError("套装模板不存在或已归档")

    ids = [str(x).strip() for x in (sku_master_ids or []) if str(x).strip()]
    total_selected = len(ids)
    if total_selected <= 0:
        return {"total_selected": 0, "bound_count": 0, "skipped_already_bound": 0, "errors": []}

    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.id.in_(list(set(ids))), models.SkuMaster.is_archived.is_(False))
        .all()
    )
    by_id = {r.id: r for r in rows}

    bound_count = 0
    skipped_already_bound = 0
    errors: List[Dict[str, Any]] = []
    now_iso = _utcnow().isoformat()
    tcode = str(getattr(t, "code", "") or "").strip() or None
    selector = str(preset_selector or "").strip().upper() or None
    if not selector:
        raise ValueError("preset_selector 不能为空")

    # Require a published bundle template version for reproducibility.
    v = bundle_template_service.get_latest_published_version(db, template_id=tid)
    if not v:
        raise ValueError("套装模板尚未发布版本：请先在“套装模板”里点“发布为新版本”")
    bundle_model_version = product_model_service.ensure_bundle_model_version(
        db,
        template_version=v,
        preset_selector=selector,
        requested_by=requested_by,
    )

    for sid in ids:
        row = by_id.get(sid)
        if not row:
            errors.append({"sku_master_id": sid, "error": "sku_master not found"})
            continue
        meta = dict(row.metadata_json or {})
        existing_tid = str(meta.get("bundle_template_id") or "").strip()
        if existing_tid and not allow_rebind:
            skipped_already_bound += 1
            continue
        sku = (row.erp_sku_barcode or "").strip()
        if not sku:
            errors.append({"sku_master_id": sid, "error": "sku_code missing"})
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            skipped_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(bundle_model_version.id) and allow_rebind:
            skipped_already_bound += 1
            continue
        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if norm_spec:
            try:
                bom_generation_service.generate_bom_by_spec(
                    db,
                    spec_text=norm_spec,
                    sku_code=sku,
                    include_disabled_variants=False,
                    return_components=False,
                    bundle_template_version_id=str(v.id),
                    bundle_preset_selector=selector,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"sku_master_id": row.id, "sku_code": sku, "error": f"BOM试算失败：{str(exc)}"})
                continue
        # Bind SKU to bundle model version (single-exit)
        product_model_service.bind_sku_to_version(
            db,
            sku_code=sku,
            version_id=bundle_model_version.id,
            source_system="sku_master_bundle_bind",
            metadata={
                "requested_by": requested_by,
                "sku_master_id": row.id,
                "binding_method": "manual_by_template_rebind" if allow_rebind else "manual_by_template",
                "skip_prefix_check": True,
                "bundle_template_id": tid,
                "bundle_template_code": tcode,
                "bundle_template_version_id": v.id,
                "bundle_template_version_label": v.version_label,
                "bundle_preset_selector": selector,
            },
        )
        meta.update(
            {
                "bundle_template_id": tid,
                "bundle_template_code": tcode,
                "bundle_preset_selector": selector,
                "bundle_template_version_id": v.id,
                "bundle_template_version_label": v.version_label,
                "bundle_model_version_id": bundle_model_version.id,
                "bundle_bound_at": now_iso,
                "bundle_bound_by": (requested_by or meta.get("requested_by") or None),
                "bundle_binding_method": "manual_by_template_rebind" if allow_rebind else "manual_by_template",
                "binding_validation_state": "sampled" if norm_spec else "no_shipment_sample",
            }
        )
        row.metadata_json = meta
        if norm_spec:
            try:
                _apply_preparse_no_commit(db, sku_master_row=row, spec_text=norm_spec, requested_by=requested_by)
            except Exception:
                pass
        bound_count += 1

    db.commit()
    return {
        "total_selected": total_selected,
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "errors": errors,
    }


def bind_sku_master_by_bundle_template_bulk(
    db: Session,
    *,
    template_id: str,
    preset_selector: Optional[str] = None,
    requested_by: Optional[str],
    limit: int = 200,
    bound_state: str = "unbound",
    allow_rebind: bool = False,
    search: Optional[str] = None,
    channel: Optional[str] = None,
    match_status: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    tid = (template_id or "").strip()
    if not tid:
        raise ValueError("template_id 不能为空")
    t = bundle_template_service.get_template(db, tid, include_archived=True)
    if not t or getattr(t, "is_archived", False):
        raise ValueError("套装模板不存在或已归档")
    tcode = str(getattr(t, "code", "") or "").strip() or None
    selector = str(preset_selector or "").strip().upper() or None
    if not selector:
        raise ValueError("preset_selector 不能为空")

    v = bundle_template_service.get_latest_published_version(db, template_id=tid)
    if not v:
        raise ValueError("套装模板尚未发布版本：请先在“套装模板”里点“发布为新版本”")
    bundle_model_version = product_model_service.ensure_bundle_model_version(
        db,
        template_version=v,
        preset_selector=selector,
        requested_by=requested_by,
    )

    limit2 = max(min(int(limit or 200), 2000), 1)
    excluded_list = list(set([str(x) for x in (excluded_sku_master_ids or []) if str(x).strip()]))
    skipped_excluded = len(excluded_list)

    # Reuse list_sku_master semantics to build the base query (server-side filters)
    q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))
    if search:
        s_like = f"%{search.strip()}%"
        q = q.filter(
            (models.SkuMaster.erp_sku_barcode.ilike(s_like))
            | (models.SkuMaster.product_name.ilike(s_like))
            | (models.SkuMaster.product_code.ilike(s_like))
        )
    if channel:
        q = q.filter(models.SkuMaster.channel == channel)
    if match_status:
        q = q.filter(models.SkuMaster.match_status == match_status)
    if excluded_list:
        q = q.filter(~models.SkuMaster.id.in_(excluded_list))
    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712
    if preparse_state:
        state = str(preparse_state).strip().lower()
        ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
        if state in ("parsed", "done", "yes", "1", "true"):
            q = q.filter(func.coalesce(ph, "") != "")
        elif state in ("unparsed", "none", "no", "0", "false"):
            q = q.filter(func.coalesce(ph, "") == "")

    # Keep consistency with model bulk binding filters
    # (bound_model_id/bound_model_code/bound_version_id are optional extra restrictors)
    if bound_model_id or bound_model_code or bound_version_id:
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
            )
            .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModel.is_archived.is_(False),
            )
        )
        if bound_version_id:
            subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
        if bound_model_id:
            subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
        if bound_model_code:
            subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
        q = q.filter(subq.exists())

    # bound_state here refers to "bundle already bound" state
    state = str(bound_state or "unbound").strip().lower()
    if state not in ("unbound", "bound", "all"):
        state = "unbound"
    existing_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_id"].as_string(), "")
    if state == "unbound":
        q = q.filter(existing_expr == "")
    elif state == "bound":
        q = q.filter(existing_expr != "")
    else:
        pass

    # NOTE: include_terms/exclude_terms/match_scope are interpreted the same as list_sku_master.
    # For Phase0, we keep it minimal and reuse list_sku_master helper by calling it is expensive here,
    # so we approximate using spec_text/product_name filter patterns.
    def _parse_terms(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        s0 = str(raw)
        for ch in ("，", ";", "；", "\n", "\t"):
            s0 = s0.replace(ch, " ")
        parts = [p.strip() for p in s0.split(" ") if p.strip()]
        out: List[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    include_list = _parse_terms(include_terms)
    exclude_list = _parse_terms(exclude_terms)
    scope = (match_scope or "auto").strip()
    if scope not in ("auto", "spec", "name", "spec_or_name"):
        scope = "auto"
    name_channels = ["小红书", "京东"]

    def _field_expr_for_scope(term: str):
        pattern = f"%{term}%"
        spec_hit = models.SkuMaster.spec_text.ilike(pattern)
        name_hit = models.SkuMaster.product_name.ilike(pattern)
        if scope == "spec":
            return spec_hit
        if scope == "name":
            return name_hit
        if scope == "spec_or_name":
            return spec_hit | name_hit
        return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (
            ~models.SkuMaster.channel.in_(name_channels) & spec_hit
        )

    for tterm in include_list:
        q = q.filter(_field_expr_for_scope(tterm))
    for tterm in exclude_list:
        q = q.filter(~_field_expr_for_scope(tterm))

    rows = q.order_by(models.SkuMaster.updated_at.desc()).limit(limit2 + 1).all()
    has_more = len(rows) > limit2
    batch_rows = rows[:limit2]

    bound_count = 0
    skipped_already_bound = 0
    errors: List[Dict[str, Any]] = []
    now_iso = _utcnow().isoformat()

    for row in batch_rows:
        meta = dict(row.metadata_json or {})
        existing_tid = str(meta.get("bundle_template_id") or "").strip()
        if existing_tid and not allow_rebind:
            skipped_already_bound += 1
            continue
        sku = (row.erp_sku_barcode or "").strip()
        if not sku:
            errors.append({"sku_master_id": row.id, "error": "sku_code missing"})
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            skipped_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(bundle_model_version.id) and allow_rebind:
            skipped_already_bound += 1
            continue
        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if norm_spec:
            try:
                bom_generation_service.generate_bom_by_spec(
                    db,
                    spec_text=norm_spec,
                    sku_code=sku,
                    include_disabled_variants=False,
                    return_components=False,
                    bundle_template_version_id=str(v.id),
                    bundle_preset_selector=selector,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"sku_master_id": row.id, "sku_code": sku, "error": f"BOM试算失败：{str(exc)}"})
                continue
        product_model_service.bind_sku_to_version(
            db,
            sku_code=sku,
            version_id=bundle_model_version.id,
            source_system="sku_master_bundle_bind_bulk",
            metadata={
                "requested_by": requested_by,
                "sku_master_id": row.id,
                "binding_method": "manual_bulk_template_rebind" if allow_rebind else "manual_bulk_template",
                "skip_prefix_check": True,
                "bundle_template_id": tid,
                "bundle_template_code": tcode,
                "bundle_template_version_id": v.id,
                "bundle_template_version_label": v.version_label,
                "bundle_preset_selector": selector,
            },
        )
        meta.update(
            {
                "bundle_template_id": tid,
                "bundle_template_code": tcode,
                "bundle_preset_selector": selector,
                "bundle_template_version_id": v.id,
                "bundle_template_version_label": v.version_label,
                "bundle_model_version_id": bundle_model_version.id,
                "bundle_bound_at": now_iso,
                "bundle_bound_by": (requested_by or meta.get("requested_by") or None),
                "bundle_binding_method": "manual_bulk_template_rebind" if allow_rebind else "manual_bulk_template",
                "binding_validation_state": "sampled" if norm_spec else "no_shipment_sample",
            }
        )
        row.metadata_json = meta
        if norm_spec:
            try:
                _apply_preparse_no_commit(db, sku_master_row=row, spec_text=norm_spec, requested_by=requested_by)
            except Exception:
                pass
        bound_count += 1

    db.commit()
    return {
        "batch_candidates": len(batch_rows),
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "skipped_excluded": skipped_excluded,
        "errors": errors,
        "has_more": has_more,
    }


def preview_bind_by_bundle_template_bulk(
    db: Session,
    *,
    template_id: str,
    preset_selector: Optional[str] = None,
    requested_by: Optional[str],
    limit: int = 200,
    bound_state: str = "unbound",
    allow_rebind: bool = False,
    search: Optional[str] = None,
    channel: Optional[str] = None,
    match_status: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    bound_model_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bound_version_id: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    tid = (template_id or "").strip()
    if not tid:
        raise ValueError("template_id 不能为空")
    t = bundle_template_service.get_template(db, tid, include_archived=True)
    if not t or getattr(t, "is_archived", False):
        raise ValueError("套装模板不存在或已归档")
    selector = str(preset_selector or "").strip().upper() or None
    if not selector:
        raise ValueError("preset_selector 不能为空")
    v = bundle_template_service.get_latest_published_version(db, template_id=tid)
    if not v:
        raise ValueError("套装模板尚未发布版本：请先在“套装模板”里点“发布为新版本”")
    bundle_model_version = product_model_service.ensure_bundle_model_version(
        db, template_version=v, preset_selector=selector, requested_by=requested_by
    )
    target_label = f"{str(getattr(t, 'code', '') or '').strip()} {str(getattr(t, 'name', '') or '').strip()}".strip()

    limit2 = max(min(int(limit or 200), 2000), 1)
    excluded_list = list(set([str(x) for x in (excluded_sku_master_ids or []) if str(x).strip()]))
    skipped_excluded = len(excluded_list)

    q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))
    if search:
        s_like = f"%{search.strip()}%"
        q = q.filter(
            (models.SkuMaster.erp_sku_barcode.ilike(s_like))
            | (models.SkuMaster.product_name.ilike(s_like))
            | (models.SkuMaster.product_code.ilike(s_like))
        )
    if channel:
        q = q.filter(models.SkuMaster.channel == channel)
    if match_status:
        q = q.filter(models.SkuMaster.match_status == match_status)
    if excluded_list:
        q = q.filter(~models.SkuMaster.id.in_(excluded_list))
    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712
    if preparse_state:
        state2 = str(preparse_state).strip().lower()
        ph = models.SkuMaster.metadata_json["preparse_spec_hash"].as_string()
        if state2 in ("parsed", "done", "yes", "1", "true"):
            q = q.filter(func.coalesce(ph, "") != "")
        elif state2 in ("unparsed", "none", "no", "0", "false"):
            q = q.filter(func.coalesce(ph, "") == "")

    if bound_model_id or bound_model_code or bound_version_id:
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
            )
            .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModel.is_archived.is_(False),
            )
        )
        if bound_version_id:
            subq = subq.filter(models.SkuModelVersionMapping.model_version_id == str(bound_version_id).strip())
        if bound_model_id:
            subq = subq.filter(models.ProductModelVersion.model_id == str(bound_model_id).strip())
        if bound_model_code:
            subq = subq.filter(models.ProductModel.model_code == str(bound_model_code).strip())
        q = q.filter(subq.exists())

    # bound_state here refers to "bundle already bound" state
    state3 = str(bound_state or "unbound").strip().lower()
    if state3 not in ("unbound", "bound", "all"):
        state3 = "unbound"
    existing_expr = func.coalesce(models.SkuMaster.metadata_json["bundle_template_id"].as_string(), "")
    if state3 == "unbound":
        q = q.filter(existing_expr == "")
    elif state3 == "bound":
        q = q.filter(existing_expr != "")

    def _parse_terms(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        s0 = str(raw)
        for ch in ("，", ";", "；", "\n", "\t"):
            s0 = s0.replace(ch, " ")
        parts = [p.strip() for p in s0.split(" ") if p.strip()]
        out: List[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    include_list = _parse_terms(include_terms)
    exclude_list = _parse_terms(exclude_terms)
    scope = (match_scope or "auto").strip()
    if scope not in ("auto", "spec", "name", "spec_or_name"):
        scope = "auto"
    name_channels = ["小红书", "京东"]

    def _field_expr_for_scope(term: str):
        pattern = f"%{term}%"
        spec_hit = models.SkuMaster.spec_text.ilike(pattern)
        name_hit = models.SkuMaster.product_name.ilike(pattern)
        if scope == "spec":
            return spec_hit
        if scope == "name":
            return name_hit
        if scope == "spec_or_name":
            return spec_hit | name_hit
        return (models.SkuMaster.channel.in_(name_channels) & name_hit) | (
            ~models.SkuMaster.channel.in_(name_channels) & spec_hit
        )

    for tterm in include_list:
        q = q.filter(_field_expr_for_scope(tterm))
    for tterm in exclude_list:
        q = q.filter(~_field_expr_for_scope(tterm))

    rows = q.order_by(models.SkuMaster.updated_at.desc()).limit(limit2 + 1).all()
    has_more = len(rows) > limit2
    batch_rows = rows[:limit2]

    items: List[Dict[str, Any]] = []
    can_bind = 0
    skip_already_bound = 0
    skip_missing_barcode = 0
    hard_errors = 0

    for row in batch_rows:
        meta = dict(row.metadata_json or {})
        existing_tid = str(meta.get("bundle_template_id") or "").strip()
        sku = (row.erp_sku_barcode or "").strip() or None
        base = {"sku_master_id": row.id, "sku_code": sku, "channel": row.channel, "model_version_id": str(bundle_model_version.id)}

        if existing_tid and not allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已绑定套装模板且不允许覆盖"]})
            skip_already_bound += 1
            continue
        if not sku:
            items.append({**base, "status": "skip_missing_barcode", "hard_errors": [], "warnings": []})
            skip_missing_barcode += 1
            continue
        active = product_model_service.get_active_sku_binding(db, sku)
        if active and not allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已有绑定且不允许覆盖"]})
            skip_already_bound += 1
            continue
        if active and str(getattr(active, "model_version_id", "") or "") == str(bundle_model_version.id) and allow_rebind:
            items.append({**base, "status": "skip_already_bound", "hard_errors": [], "warnings": ["SKU已绑定到目标套装版本"]})
            skip_already_bound += 1
            continue

        sh, raw_spec, norm_spec = _latest_shipment_spec_sample(db, sku_code=sku)
        if not norm_spec:
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": ["无发货交易规格样本：本次绑定未做BOM试算校验"],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            can_bind += 1
            continue

        try:
            bom = bom_generation_service.generate_bom_by_spec(
                db,
                spec_text=norm_spec,
                sku_code=sku,
                include_disabled_variants=False,
                return_components=False,
                bundle_template_version_id=str(v.id),
                bundle_preset_selector=selector,
            )
            trace = bom.get("trace") if isinstance(bom.get("trace"), dict) else {}
            costing = trace.get("costing") if isinstance(trace.get("costing"), dict) else {}
            inventory = trace.get("inventory") if isinstance(trace.get("inventory"), dict) else {}
            warn2 = _mismatch_warnings_by_keywords(
                sample_text=norm_spec,
                sku_spec_text=getattr(row, "spec_text", None),
                product_name=getattr(row, "product_name", None),
                target_label=target_label or str(bundle_model_version.id),
            )
            items.append(
                {
                    **base,
                    "status": "can_bind",
                    "hard_errors": [],
                    "warnings": warn2,
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                    "cost_total": costing.get("total_cost"),
                    "inventory_line_count": inventory.get("inventory_line_count") if isinstance(inventory, dict) else None,
                }
            )
            can_bind += 1
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    **base,
                    "status": "hard_error",
                    "hard_errors": [f"BOM试算失败：{str(exc)}"],
                    "warnings": [],
                    "sample_shipment_line_id": getattr(sh, "id", None) if sh else None,
                    "sample_completed_at": getattr(sh, "completed_at", None) if sh else None,
                    "sample_spec_text": raw_spec,
                    "sample_spec_text_norm": norm_spec,
                }
            )
            hard_errors += 1

    return {
        "batch_candidates": len(batch_rows),
        "can_bind": can_bind,
        "skip_already_bound": skip_already_bound,
        "skip_missing_barcode": skip_missing_barcode,
        "hard_errors": hard_errors,
        "skipped_excluded": skipped_excluded,
        "has_more": has_more,
        "items": items,
    }


def auto_bind_preview(
    db: Session,
    *,
    limit: int,
    scan_limit: int = 50000,
    restrict_to_sku_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Identify unbound SkuMaster rows that match a published standard model
    via either ``model_code_hint`` (extracted from spec_text) or
    ``recognition_keywords`` (from model.metadata_json). Returns a list of
    auto-bind candidates (no writes).

    Args:
        limit: max number of candidate items to return.
        scan_limit: max number of unbound SkuMaster rows to inspect.
        restrict_to_sku_codes: when provided, scope scanning to these
            ``erp_sku_barcode`` values only. Used by
            ``shipment_import_service.auto_resolve_pending_shipment_lines_*``
            so that the recognition engine only runs against SKUs that
            actually appear in recent pending shipment lines (instead of
            spending CPU on long-tail historical SKUs that are not selling).
    """
    limit = max(min(int(limit or 200), 2000), 1)
    scan_limit = max(min(int(scan_limit or 50000), 500000), 100)
    restrict_codes_norm: Optional[List[str]] = None
    if restrict_to_sku_codes is not None:
        restrict_codes_norm = sorted({(c or "").strip() for c in restrict_to_sku_codes if (c or "").strip()})

    def _norm_text(t: Optional[str]) -> str:
        return "".join(str(t or "").strip().split()).upper()

    def _extract_model_keywords(meta: Dict[str, Any]) -> List[str]:
        raw = meta.get("recognition_keywords")
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        for x in raw:
            if x is None:
                continue
            k = "".join(str(x).strip().split()).upper()
            if not k:
                continue
            out.append(k)
        # de-dup
        seen: set[str] = set()
        uniq: List[str] = []
        for k in out:
            if k in seen:
                continue
            seen.add(k)
            uniq.append(k)
        return uniq

    # Load all published standard models for keyword matching (in-memory) once.
    published_models: List[Dict[str, Any]] = []
    rows = (
        db.query(models.ProductModel, models.ProductModelVersion)
        .join(models.ProductModelVersion, models.ProductModelVersion.model_id == models.ProductModel.id)
        .filter(
            models.ProductModel.is_archived.is_(False),
            models.ProductModelVersion.is_archived.is_(False),
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
        )
        .order_by(models.ProductModel.model_code.asc())
        .all()
    )
    # 真实存在的 model_code 集合：传给 _extract_model_code_from_shop_spec
    # 做容错（识别 "<款号前缀><MMM-NNN>" 复合形式末尾的真实模型码）
    known_model_codes: set = set()
    # PERF: 把 (model_code → (model, latest_published_version)) 全部 cache 到内存,
    # 避免每行 SKU 命中 hint 时再调 get_latest_published_standard_version_for_model_code()
    # (该函数每次 2 次 SQL, scan_limit=50000 + hint 命中率 50% 会触发 ~5w 次 query,
    # 是"一键跑完"在数据量大时 canceled 的根本原因).
    # 同 model 多版本时, 用 (published_at, created_at) DESC 取最新, 与
    # product_model_service.get_latest_published_standard_version_for_model_code() 同语义.
    model_code_to_version: Dict[str, Tuple[Any, Any]] = {}
    for m, v in rows:
        mc = str(getattr(m, "model_code", "") or "").strip().upper()
        if mc:
            known_model_codes.add(mc)
            existing = model_code_to_version.get(mc)
            if existing is None:
                model_code_to_version[mc] = (m, v)
            else:
                # 选择更新的版本: published_at desc, then created_at desc, NULL 排最后
                _, ev = existing
                ev_pub = getattr(ev, "published_at", None)
                v_pub = getattr(v, "published_at", None)
                if (v_pub is not None and ev_pub is None) or (
                    v_pub is not None and ev_pub is not None and v_pub > ev_pub
                ):
                    model_code_to_version[mc] = (m, v)
                elif v_pub == ev_pub:
                    ev_cre = getattr(ev, "created_at", None)
                    v_cre = getattr(v, "created_at", None)
                    if v_cre is not None and (ev_cre is None or v_cre > ev_cre):
                        model_code_to_version[mc] = (m, v)
        meta = m.metadata_json or {}
        kws = _extract_model_keywords(meta)
        if not kws:
            continue
        published_models.append({"model": m, "version": v, "keywords": kws})

    def _match_by_model_keywords(text_raw: Optional[str]) -> Optional[Dict[str, Any]]:
        text = _norm_text(text_raw)
        if not text:
            return None
        hits: List[Dict[str, Any]] = []
        for rec in published_models:
            m = rec["model"]
            v = rec["version"]
            kws: List[str] = rec["keywords"]
            matched: List[str] = [k for k in kws if k and k in text]
            if not matched:
                continue
            # choose longest keyword within the same model
            best = sorted(matched, key=lambda x: len(x), reverse=True)[0]
            hits.append({"model": m, "version": v, "matched_keyword": best})

        if not hits:
            return None
        # If multiple models hit, prefer strictly-longest keyword; otherwise ambiguous -> no match.
        hits_sorted = sorted(hits, key=lambda x: len(str(x["matched_keyword"])), reverse=True)
        if len(hits_sorted) == 1:
            return hits_sorted[0]
        top_len = len(str(hits_sorted[0]["matched_keyword"]))
        second_len = len(str(hits_sorted[1]["matched_keyword"]))
        if top_len > second_len:
            return hits_sorted[0]
        return None

    # Find unbound SKU masters (server-side filter; avoid empty pages from client-side filtering)
    subq = (
        db.query(models.SkuModelVersionMapping.id)
        .filter(
            models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
    )
    q = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.is_archived.is_(False))
        .filter(~subq.exists())
        .order_by(models.SkuMaster.updated_at.desc())
    )
    if restrict_codes_norm is not None:
        if not restrict_codes_norm:
            return {"total_unbound": 0, "candidates": 0, "items": []}
        q = q.filter(models.SkuMaster.erp_sku_barcode.in_(restrict_codes_norm))
    rows = q.limit(scan_limit).all()

    # NOTE: q.count() can be very expensive on large tables and may trigger gateway timeouts.
    # For Phase0 operations we only need a rough indicator, so we avoid full-table count here.
    # Use a bounded approximation: when rows hits scan_limit, report scan_limit (meaning ">= scan_limit").
    total_unbound = 0
    items: List[Dict[str, Any]] = []
    candidates = 0

    for r in rows:
        sku = (r.erp_sku_barcode or "").strip()
        if not sku:
            continue
        meta = r.metadata_json or {}
        # Prefer latest shipment spec when present; otherwise fallback to ERP spec_text.
        spec_for_match = meta.get("last_shipment_spec_text") or r.spec_text
        # Keyword recognition is STRICT: only match against spec_text (prefer latest shipment spec).
        match_text = str(spec_for_match or "")
        # 商家编码（线上 ERP 维护的"规格编码（网店）"）作为最强识别源：
        # 优先级 1 = 商家编码命中"模型-变体"短码（KB8-001 → KB8）→ 100% 锁定模型
        # 优先级 2 = spec_text 抽取的 hint
        # 优先级 3 = 模型识别关键词（recognition_keywords）
        shop_code = str(meta.get("shop_spec_code") or getattr(r, "shop_spec_code", "") or "").strip()
        variant_hint = _extract_variant_code_hint(shop_code) if shop_code else None
        # P0 锚点：商家编码必须用**严格抽取器**，拒绝 12 位淘宝 ID 形态
        # （避免 model_code='024' 一旦上线，所有 024 开头的平台 ID 被错绑）。
        # 同时传入 known_model_codes 启用"末尾子串容错"——识别 ERP 端遗留的
        # 复合脏数据 "Q26041801KB8-001" → KB8（mapper 已归一化新数据）。
        shop_hint = (
            _extract_model_code_from_shop_spec(shop_code, known_model_codes=known_model_codes)
            if shop_code else None
        )
        # P1：spec_text 抽取的 hint（保留 _extract_model_code_hint 宽松行为，因为规格文本上下文更可信）
        hint = meta.get("model_code_hint_shipment") or meta.get("model_code_hint_erp")
        if not hint:
            hint = _extract_model_code_hint(spec_for_match)
        # 商家编码 hint 命中时优先（仅在严格抽取器通过时才覆盖）
        if shop_hint:
            hint = shop_hint
        hint = (str(hint).strip().upper()) if hint else ""
        match_method = None
        matched_keyword = None
        model = None
        version = None

        if hint:
            # PERF: 用内存 cache 替代 get_latest_published_standard_version_for_model_code(),
            # 避免 N+1 DB 查询. hint 已 strip+upper, 直接对 dict key.
            cached = model_code_to_version.get(hint)
            if cached is not None:
                _model_cached, _version_cached = cached
                if _model_cached and not _model_cached.is_archived:
                    model = _model_cached
                    version = _version_cached
                    # 注意：只有 shop_hint 严格通过 + 与最终 hint 一致时才标 shop_spec_code，
                    # 否则归类到 model_code_hint（说明命中来自 spec_text 而非商家编码）
                    match_method = "shop_spec_code" if (shop_hint and shop_hint == hint) else "model_code_hint"

        if not model or not version:
            kw_match = _match_by_model_keywords(match_text)
            if kw_match:
                model = kw_match["model"]
                version = kw_match["version"]
                matched_keyword = kw_match.get("matched_keyword")
                match_method = "model_keyword"

        if not model or not version:
            continue

        candidates += 1
        items.append(
            {
                "sku_master_id": r.id,
                "erp_sku_barcode": sku,
                "channel": r.channel,
                "spec_text": spec_for_match,
                "shop_spec_code": shop_code or None,
                "variant_code_hint": variant_hint,
                "model_code_hint": hint,
                "model_id": model.id,
                "model_code": model.model_code,
                "model_name": model.model_name,
                "published_version_id": version.id,
                "version_label": version.version_label,
                "match_method": match_method,
                "matched_keyword": matched_keyword,
            }
        )
        if len(items) >= limit:
            break

    total_unbound = len(rows) if len(rows) < scan_limit else scan_limit
    return {"total_unbound": total_unbound, "candidates": candidates, "items": items}


def auto_bind_execute(
    db: Session,
    *,
    limit: int,
    requested_by: Optional[str],
    sku_master_ids: Optional[List[str]] = None,
    scan_limit: int = 50000,
) -> Dict[str, Any]:
    preview = auto_bind_preview(db, limit=limit, scan_limit=scan_limit)
    items_all = list(preview.get("items") or [])
    selected_set = {str(x) for x in (sku_master_ids or []) if str(x).strip()}
    items = items_all
    if selected_set:
        items = [it for it in items_all if str(it.get("sku_master_id") or "") in selected_set]
    bound_count = 0
    skipped_already_bound = 0
    errors: List[Dict[str, Any]] = []

    for it in items:
        sku = str(it.get("erp_sku_barcode") or "").strip()
        if not sku:
            continue
        if product_model_service.get_active_sku_binding(db, sku):
            skipped_already_bound += 1
            continue
        # 自动识别模式：preview 阶段已经从商家编码（shop_spec_code）正则抽出
        # variant_code_hint（如 KB8-001），这里直接落到 SkuMaster.metadata_json.bound_variant_code，
        # 与人工审核走同一份字段，下游列表/详情统一从这里读，不再反推。
        norm_variant_code = str(it.get("variant_code_hint") or "").strip().upper() or None
        try:
            # CRITICAL ORDERING:
            # bind_sku_to_version() internally calls db.commit() AND then
            # invokes _trigger_pending_snapshots_for_sku() which does
            # db.rollback() on failure — that rollback would erase any
            # SkuMaster.metadata.bound_variant_code we wrote AFTER the bind.
            # So we write bound_variant_code on the SkuMaster BEFORE binding,
            # ensuring both rows are committed atomically by bind_sku_to_version.
            sku_master_id = it.get("sku_master_id")
            if sku_master_id:
                row = db.get(models.SkuMaster, str(sku_master_id))
                if row is not None:
                    meta = dict(getattr(row, "metadata_json", None) or {})
                    if norm_variant_code:
                        meta["bound_variant_code"] = norm_variant_code
                    else:
                        meta.pop("bound_variant_code", None)
                    _clear_suspect_misbind_resolved(meta)
                    row.metadata_json = meta
                    try:
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(row, "metadata_json")
                    except Exception:
                        pass

            product_model_service.bind_sku_to_version(
                db,
                sku_code=sku,
                version_id=str(it.get("published_version_id")),
                source_system="sku_master_auto",
                metadata={
                    "requested_by": requested_by,
                    "sku_master_id": it.get("sku_master_id"),
                    "binding_method": it.get("match_method") or "auto",
                    "model_code_hint": it.get("model_code_hint"),
                    "matched_keyword": it.get("matched_keyword"),
                    "variant_code_hint": norm_variant_code,
                    "skip_prefix_check": True,
                },
            )
            bound_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_master_id": it.get("sku_master_id"), "sku_code": sku, "error": str(exc)})

    # return a fresh preview after binding
    preview_after = auto_bind_preview(db, limit=limit, scan_limit=scan_limit)
    return {
        "preview": preview_after,
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "errors": errors,
    }


# ============================================================================
# SKU Governance (Sprint 2 of "SKU 治理与按需建模")
# ----------------------------------------------------------------------------
# Background:
#   With ~1M SKUs in Jackyun, we cannot pre-import or pre-model every SKU.
#   Instead, ``ensure_from_shipment`` creates SkuMaster rows on-demand and
#   each SKU traverses a 4-state governance lifecycle managed by operators
#   from the BatchWorkbench exception queue UI.
#
# State machine (stored in SkuMaster.metadata_json.governance_status):
#
#       unmanaged ---bind/build model---> auto_bound
#           |                                ^
#           |---add to backlog---> pending_model
#           |                                |
#           |---mark as long-tail---> do_not_model (silent skip)
#           |                                |
#           +-------- operator revert -------+
#
# Why metadata_json (not a column):
#   - No Alembic migration cost; unblocks 4-state UI immediately.
#   - Pattern aligns with existing extension keys (needs_erp_sync,
#     bundle_template_id, spec_mismatch, ...).
#   - Audit trail (governance_history[]) lives next to the status.
#
# Worker contract (see shipment_import_service._finalize_shipment_line and
# Sprint 2-2 work for shipment_import_service.py):
#   - do_not_model     -> skip the line silently (no exception, no snapshot)
#   - pending_model    -> enqueue exception with reason='MODEL_PENDING'
#   - unmanaged        -> default behaviour (SKU_NOT_BOUND if unbound)
#   - auto_bound       -> normal parse + BomSnapshot
# ============================================================================


GOVERNANCE_UNMANAGED = "unmanaged"
GOVERNANCE_AUTO_BOUND = "auto_bound"
GOVERNANCE_PENDING_MODEL = "pending_model"
GOVERNANCE_DO_NOT_MODEL = "do_not_model"

GOVERNANCE_STATUSES = frozenset(
    {
        GOVERNANCE_UNMANAGED,
        GOVERNANCE_AUTO_BOUND,
        GOVERNANCE_PENDING_MODEL,
        GOVERNANCE_DO_NOT_MODEL,
    }
)


def get_sku_governance_status(sku_master: Optional[models.SkuMaster]) -> str:
    """Read governance_status from SkuMaster.metadata_json. Default: unmanaged.

    Safe to call with None (returns 'unmanaged') so callers don't need to
    null-check before deciding the worker behaviour.
    """
    if sku_master is None:
        return GOVERNANCE_UNMANAGED
    meta = dict(getattr(sku_master, "metadata_json", None) or {})
    return str(meta.get("governance_status") or GOVERNANCE_UNMANAGED)


def is_do_not_model(sku_master: Optional[models.SkuMaster]) -> bool:
    """Check whether a SKU is marked as long-tail (worker should skip)."""
    return get_sku_governance_status(sku_master) == GOVERNANCE_DO_NOT_MODEL


def is_pending_model(sku_master: Optional[models.SkuMaster]) -> bool:
    """Check whether a SKU is in the modeling backlog."""
    return get_sku_governance_status(sku_master) == GOVERNANCE_PENDING_MODEL


def set_sku_governance(
    db: Session,
    *,
    sku_codes: List[str],
    status: str,
    decided_by: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, int]:
    """Bulk-set governance_status for the given barcodes.

    Side-effects (atomic per row, all under one db.flush()):
      - metadata_json.governance_status        = <status>
      - metadata_json.governance_decided_at    = ISO timestamp
      - metadata_json.governance_decided_by    = <decided_by> if provided
      - metadata_json.governance_note          = <note> if provided
      - metadata_json.governance_history       = appended audit entry
        (capped at last 20 entries to avoid metadata bloat)

    Returns
    -------
    counters: {"updated": int, "unchanged": int, "missing": int}
        - updated:    rows whose status actually changed
        - unchanged:  rows already at the requested status (idempotent)
        - missing:    barcodes with no SkuMaster row in DB

    Raises
    ------
    ValueError: if ``status`` not in GOVERNANCE_STATUSES.
    """
    if status not in GOVERNANCE_STATUSES:
        raise ValueError(
            f"Unknown governance status: {status!r}; allowed={sorted(GOVERNANCE_STATUSES)}"
        )
    if not sku_codes:
        return {"updated": 0, "unchanged": 0, "missing": 0}

    barcodes = [c for c in (str(s).strip() for s in sku_codes) if c]
    if not barcodes:
        return {"updated": 0, "unchanged": 0, "missing": 0}

    unique_barcodes = list({b for b in barcodes})
    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode.in_(unique_barcodes))
        .all()
    )
    found = {r.erp_sku_barcode: r for r in rows}

    updated = 0
    unchanged = 0
    now_iso = _utcnow().isoformat()

    for code in unique_barcodes:
        r = found.get(code)
        if r is None:
            continue
        meta = dict(r.metadata_json or {})
        prev = meta.get("governance_status") or GOVERNANCE_UNMANAGED
        if prev == status:
            unchanged += 1
            continue
        meta["governance_status"] = status
        meta["governance_decided_at"] = now_iso
        if decided_by:
            meta["governance_decided_by"] = decided_by
        if note is not None:
            meta["governance_note"] = note
        history = list(meta.get("governance_history") or [])
        history.append(
            {
                "at": now_iso,
                "by": decided_by,
                "from": prev,
                "to": status,
                "note": note,
            }
        )
        meta["governance_history"] = history[-20:]
        r.metadata_json = _json_safe(meta)
        r.updated_at = _utcnow()
        updated += 1

    missing = len(unique_barcodes) - len(found)
    db.flush()
    return {"updated": updated, "unchanged": unchanged, "missing": missing}


def set_sku_long_tail_category(
    db: Session,
    *,
    sku_codes: List[str],
    category: Optional[str],
    actor: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, int]:
    """Issue 28 follow-up: bulk-set ``metadata_json.long_tail_category`` for
    the given barcodes.

    This is the "manual override" branch of the long-tail rate resolver.
    When a SKU has this field set, the long-tail snapshot will pick the
    matching strategy regardless of keywords (see
    ``long_tail_strategy_service.resolve_rate_for_sku``).

    Side-effects (atomic per row, all under one db.flush()):
      - metadata_json.long_tail_category          = <category> (or removed when empty)
      - metadata_json.long_tail_category_decided_at  = ISO timestamp
      - metadata_json.long_tail_category_decided_by  = <actor> if provided
      - metadata_json.long_tail_category_note     = <note> if provided
      - metadata_json.long_tail_category_history  = appended audit entry
        (capped at last 20)

    Validation:
      - if category is non-empty, it must match a non-archived enabled
        strategy's category (case-insensitive). Pass empty string / None
        to *clear* the override.

    Returns
    -------
    {"updated": int, "unchanged": int, "missing": int, "cleared": int}
    """
    raw = (category or "").strip()
    clearing = raw == ""

    if not clearing:
        # Local import to avoid a circular import at module load.
        from . import long_tail_strategy_service as ltss

        strategies = ltss.list_strategies(db, include_archived=False)
        valid_categories = {
            (s.category or "").strip().lower(): (s.category or "").strip()
            for s in strategies
            if s.enabled
        }
        if raw.lower() not in valid_categories:
            raise ValueError(
                f"category {raw!r} not found in strategies; allowed="
                f"{sorted(valid_categories.values())}"
            )
        # Normalise to the canonical casing stored in the strategy table.
        raw = valid_categories[raw.lower()]

    if not sku_codes:
        return {"updated": 0, "unchanged": 0, "missing": 0, "cleared": 0}

    barcodes = [c for c in (str(s).strip() for s in sku_codes) if c]
    if not barcodes:
        return {"updated": 0, "unchanged": 0, "missing": 0, "cleared": 0}

    unique_barcodes = list({b for b in barcodes})
    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode.in_(unique_barcodes))
        .all()
    )
    found = {r.erp_sku_barcode: r for r in rows}

    updated = 0
    unchanged = 0
    cleared = 0
    now_iso = _utcnow().isoformat()

    for code in unique_barcodes:
        r = found.get(code)
        if r is None:
            continue
        meta = dict(r.metadata_json or {})
        prev = (meta.get("long_tail_category") or "").strip()
        new_value = raw  # already validated/normalised above

        if prev == new_value and not clearing:
            unchanged += 1
            continue
        if clearing and not prev:
            unchanged += 1
            continue

        history = list(meta.get("long_tail_category_history") or [])
        history.append(
            {
                "at": now_iso,
                "by": actor,
                "from": prev or None,
                "to": new_value or None,
                "note": note,
            }
        )
        meta["long_tail_category_history"] = history[-20:]
        meta["long_tail_category_decided_at"] = now_iso
        if actor:
            meta["long_tail_category_decided_by"] = actor
        if note is not None:
            meta["long_tail_category_note"] = note

        if clearing:
            meta.pop("long_tail_category", None)
            cleared += 1
        else:
            meta["long_tail_category"] = new_value
            updated += 1

        r.metadata_json = _json_safe(meta)
        r.updated_at = _utcnow()

    missing = len(unique_barcodes) - len(found)
    db.flush()
    return {
        "updated": updated,
        "unchanged": unchanged,
        "missing": missing,
        "cleared": cleared,
    }


def auto_suggest_long_tail_category(
    db: Session,
    *,
    sku_codes: Optional[List[str]] = None,
    include_already_labeled: bool = False,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Issue 28 follow-up: scan long-tail SKUs and suggest a category for
    each one based on the strategy keyword table.

    Scope:
      - If ``sku_codes`` is provided, only those SKUs are scanned (useful
        for "re-evaluate this batch" workflows).
      - Otherwise scan all SkuMaster rows whose
        ``metadata.governance_status='do_not_model'``.

    Skip rules:
      - ``include_already_labeled=False`` (default) → skip SKUs whose
        ``metadata.long_tail_category`` is already set (don't overwrite
        human decisions).
      - SKUs with no haystack text (no spec_text/product_name/...) are
        included with ``suggested_category=None`` (counted in
        ``no_match_count``).

    Returns
    -------
    {
      "scanned": int,                 # total SKUs scanned
      "already_labeled_skipped": int, # SKUs skipped because they had a category
      "suggested": [                  # ordered by occurrence in scan
        {
          "sku_code": str,
          "current_category": Optional[str],
          "suggested_category": str,
          "matched_keyword": str,
          "strategy_id": str,
          "strategy_rate": float,
          "spec_text": Optional[str],
          "product_name": Optional[str],
        }, ...
      ],
      "no_match_count": int,          # scanned but no keyword hit
      "limited": bool,                # True if hit ``limit`` (truncated)
    }
    """
    from . import long_tail_strategy_service as ltss

    strategies = ltss.list_strategies(db, include_archived=False)
    enabled = [s for s in strategies if s.enabled]
    if not enabled:
        return {
            "scanned": 0,
            "already_labeled_skipped": 0,
            "suggested": [],
            "no_match_count": 0,
            "limited": False,
            "reason": "no enabled strategies",
        }

    q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))
    if sku_codes:
        codes = list({(c or "").strip() for c in sku_codes if (c or "").strip()})
        if not codes:
            return {
                "scanned": 0,
                "already_labeled_skipped": 0,
                "suggested": [],
                "no_match_count": 0,
                "limited": False,
            }
        q = q.filter(models.SkuMaster.erp_sku_barcode.in_(codes))
    else:
        # Scan only do_not_model rows. Use the same JSON path query the
        # backlog list uses, so SQLite + PG behave the same.
        status_expr = func.coalesce(
            models.SkuMaster.metadata_json["governance_status"].as_string(),
            GOVERNANCE_UNMANAGED,
        )
        q = q.filter(status_expr == GOVERNANCE_DO_NOT_MODEL)

    # Order is stable (by erp_sku_barcode) so two consecutive previews on
    # the same data return the same prefix when ``limit`` truncates.
    rows = (
        q.order_by(models.SkuMaster.erp_sku_barcode.asc())
        .limit(max(int(limit or 5000), 1))
        .all()
    )

    suggested: List[Dict[str, Any]] = []
    already_labeled_skipped = 0
    no_match_count = 0
    limited = len(rows) >= int(limit or 5000)

    for r in rows:
        meta = r.metadata_json or {}
        current = (meta.get("long_tail_category") or "").strip() or None
        if current and not include_already_labeled:
            already_labeled_skipped += 1
            continue
        haystack = " ".join(
            [
                r.spec_text or "",
                r.product_name or "",
                r.product_code or "",
                r.erp_sku_barcode or "",
            ]
        ).lower()
        hit = ltss.match_keyword_strategy(enabled, haystack)
        if hit is None:
            no_match_count += 1
            continue
        strategy, matched_kw = hit
        suggested.append(
            {
                "sku_code": r.erp_sku_barcode,
                "current_category": current,
                "suggested_category": strategy.category,
                "matched_keyword": matched_kw,
                "strategy_id": strategy.id,
                "strategy_rate": float(strategy.rate or 0.0),
                "spec_text": r.spec_text,
                "product_name": r.product_name,
            }
        )

    return {
        "scanned": len(rows),
        "already_labeled_skipped": already_labeled_skipped,
        "suggested": suggested,
        "no_match_count": no_match_count,
        "limited": limited,
    }


def auto_apply_long_tail_category(
    db: Session,
    *,
    sku_codes: Optional[List[str]] = None,
    include_already_labeled: bool = False,
    limit: int = 5000,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """One-shot: run ``auto_suggest_long_tail_category`` then apply each
    candidate via ``set_sku_long_tail_category`` (grouped per-category).

    Returns the suggest result plus per-category apply counters and a
    flat ``applied`` total.
    """
    preview = auto_suggest_long_tail_category(
        db,
        sku_codes=sku_codes,
        include_already_labeled=include_already_labeled,
        limit=limit,
    )
    suggestions = preview.get("suggested") or []
    if not suggestions:
        return {**preview, "applied": 0, "apply_results": []}

    by_cat: Dict[str, List[str]] = {}
    for item in suggestions:
        by_cat.setdefault(item["suggested_category"], []).append(item["sku_code"])

    apply_results: List[Dict[str, Any]] = []
    applied = 0
    for cat, codes in by_cat.items():
        try:
            counters = set_sku_long_tail_category(
                db,
                sku_codes=codes,
                category=cat,
                actor=actor or "auto-suggest",
                note="auto-applied via keyword match",
            )
        except ValueError as exc:
            apply_results.append({"category": cat, "error": str(exc), "sku_count": len(codes)})
            continue
        applied += int(counters.get("updated") or 0)
        apply_results.append(
            {
                "category": cat,
                "sku_count": len(codes),
                **counters,
            }
        )

    return {**preview, "applied": applied, "apply_results": apply_results}


def list_governance_backlog(
    db: Session,
    *,
    status: str,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "shipment_score",
    sales_window_days: int = 30,
) -> Dict[str, Any]:
    """List SkuMaster rows by governance_status, with shipment stats for triage.

    The "建模 Backlog" UI uses this to surface ``pending_model`` SKUs sorted by
    sales potential, so operators can prioritise modeling work by impact.
    The "长尾 SKU" UI uses it with ``status='do_not_model'`` for read-only
    statistics + manual revert.

    Parameters
    ----------
    status : one of GOVERNANCE_STATUSES
    page, page_size : pagination
    order_by : 'shipment_score' (default, by revenue desc) | 'updated_at'
               | 'last_shipment_at'
    sales_window_days : look-back window for the per-SKU shipment stats
                        attached to each item (default 30 days)

    Returns
    -------
    {"items": [...], "total": int, "page": int, "page_size": int}
        item shape:
          erp_sku_barcode, spec_text, channel,
          governance_status, governance_decided_at, governance_decided_by,
          governance_note,
          last_shipment_at, qty_window, revenue_window, line_count_window
    """
    if status not in GOVERNANCE_STATUSES:
        raise ValueError(f"Unknown governance status: {status!r}")

    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 50), 500), 1)
    sales_window_days = max(int(sales_window_days or 30), 1)

    status_expr = func.coalesce(
        models.SkuMaster.metadata_json["governance_status"].as_string(),
        GOVERNANCE_UNMANAGED,
    )

    base_q = db.query(models.SkuMaster).filter(status_expr == status)
    total = base_q.count()

    # NULLS LAST is Postgres-only; portable form uses a CASE so the same
    # query works for both SQLite (tests) and Postgres (production).
    page_rows = (
        base_q.order_by(
            models.SkuMaster.updated_at.is_(None),
            models.SkuMaster.updated_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    barcodes = [r.erp_sku_barcode for r in page_rows if r.erp_sku_barcode]
    stats_by_code: Dict[str, Dict[str, Any]] = {}
    if barcodes:
        from datetime import timedelta as _td

        cutoff = _utcnow() - _td(days=sales_window_days)
        stat_rows = (
            db.query(
                models.ShipmentLine.sku_code,
                func.max(models.ShipmentLine.completed_at).label("last_shipment_at"),
                func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("qty_w"),
                func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label(
                    "rev_w"
                ),
                func.count(models.ShipmentLine.id).label("line_count_w"),
            )
            .filter(
                models.ShipmentLine.sku_code.in_(list(set(barcodes))),
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                or_(
                    models.ShipmentLine.completed_at >= cutoff,
                    models.ShipmentLine.completed_at.is_(None),
                ),
            )
            .group_by(models.ShipmentLine.sku_code)
            .all()
        )
        for s in stat_rows:
            stats_by_code[s.sku_code] = {
                "last_shipment_at": s.last_shipment_at.isoformat()
                if s.last_shipment_at
                else None,
                "qty_window": float(s.qty_w) if s.qty_w is not None else 0.0,
                "revenue_window": float(s.rev_w) if s.rev_w is not None else 0.0,
                "line_count_window": int(s.line_count_w or 0),
            }

    items: List[Dict[str, Any]] = []
    for r in page_rows:
        meta = dict(r.metadata_json or {})
        s = stats_by_code.get(r.erp_sku_barcode, {})
        items.append(
            {
                "erp_sku_barcode": r.erp_sku_barcode,
                "spec_text": r.spec_text,
                "channel": r.channel,
                "governance_status": meta.get("governance_status") or GOVERNANCE_UNMANAGED,
                "governance_decided_at": meta.get("governance_decided_at"),
                "governance_decided_by": meta.get("governance_decided_by"),
                "governance_note": meta.get("governance_note"),
                # Issue 28 follow-up: surface manual long-tail category override
                # so the long-tail Tab can show + let user re-edit it inline.
                "long_tail_category": meta.get("long_tail_category"),
                "long_tail_category_decided_at": meta.get("long_tail_category_decided_at"),
                "long_tail_category_decided_by": meta.get("long_tail_category_decided_by"),
                "last_shipment_at": s.get("last_shipment_at"),
                "qty_window": s.get("qty_window") or 0,
                "revenue_window": s.get("revenue_window") or 0,
                "line_count_window": s.get("line_count_window") or 0,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
        )

    if order_by == "shipment_score":
        items.sort(key=lambda x: float(x.get("revenue_window") or 0), reverse=True)
    elif order_by == "last_shipment_at":
        items.sort(key=lambda x: x.get("last_shipment_at") or "", reverse=True)
    # 'updated_at' is already the SQL order; keep page order

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "order_by": order_by,
        "sales_window_days": sales_window_days,
    }


def auto_promote_pending_model(
    db: Session,
    *,
    sku_codes: List[str],
    decided_by: Optional[str] = None,
) -> Dict[str, int]:
    """Promote SKUs from ``pending_model`` -> ``auto_bound``.

    Called when a ProductModelVersion is published+bound, so the modeling
    backlog UI no longer shows SKUs whose model has shipped. Idempotent:
    SKUs not in pending_model are skipped (counted as 'skipped'); SKUs
    with no SkuMaster row are reported as 'missing'.

    Returns
    -------
    {"promoted": int, "skipped": int, "missing": int}
    """
    if not sku_codes:
        return {"promoted": 0, "skipped": 0, "missing": 0}

    barcodes = [c for c in (str(s).strip() for s in sku_codes) if c]
    if not barcodes:
        return {"promoted": 0, "skipped": 0, "missing": 0}

    unique_barcodes = list({b for b in barcodes})

    present_rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode.in_(unique_barcodes))
        .all()
    )
    by_code = {r.erp_sku_barcode: r for r in present_rows}
    missing = len(unique_barcodes) - len(by_code)

    now_iso = _utcnow().isoformat()
    promoted = 0
    skipped = 0
    for code in unique_barcodes:
        r = by_code.get(code)
        if r is None:
            continue
        meta = dict(r.metadata_json or {})
        prev = meta.get("governance_status") or GOVERNANCE_UNMANAGED
        if prev != GOVERNANCE_PENDING_MODEL:
            skipped += 1
            continue
        meta["governance_status"] = GOVERNANCE_AUTO_BOUND
        meta["governance_decided_at"] = now_iso
        meta["governance_decided_by"] = decided_by or "auto_promote"
        history = list(meta.get("governance_history") or [])
        history.append(
            {
                "at": now_iso,
                "by": decided_by or "auto_promote",
                "from": prev,
                "to": GOVERNANCE_AUTO_BOUND,
                "note": "promoted after model published",
            }
        )
        meta["governance_history"] = history[-20:]
        r.metadata_json = _json_safe(meta)
        r.updated_at = _utcnow()
        promoted += 1

    db.flush()
    return {"promoted": promoted, "skipped": skipped, "missing": missing}

