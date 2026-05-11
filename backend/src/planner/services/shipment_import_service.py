from __future__ import annotations

import hashlib
import io
import re
import os
import subprocess
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy import and_, exists, func, literal, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from .. import models
from ...config import settings
from ...database import SessionLocal
from . import (
    bom_generation_service,
    long_tail_strategy_service,
    product_model_service,
    spec_parser_service,
    sku_master_service,
)


PARSER_VERSION = "v1"
PREVIEW_CACHE_DIR = Path("logs") / "shipment_previews"


def _extract_shop_spec_code_from_line(line: Any) -> Optional[str]:
    """
    从 ShipmentLine 抽取"商家编码"（merchant SKU，归一化后的展示值），按可靠度排序：
      1. line.metadata_json.shop_spec_code（最新协议；新版 jackyun mapper 已做"剥前缀"归一化）
      2. line.product_link_id（旧版 jackyun mapper 把 tradeGoodsno 写在这；可能含前缀）
      3. raw_row_json.detail.tradeGoodsno（吉客云 detail 段；可能含前缀）
      4. raw_row_json.shipment.goodsDetail[*].tradeGoodsno（极少数嵌套场景）
      5. raw_row_json 顶层中文/英文别名（手工 Excel 路径）

    返回 None 表示真没有；调用方应避免用空串覆盖已有值。
    需要拿到 ERP 原始拼装值（归一化前）请用 ``_extract_shop_spec_code_raw_from_line``。
    """
    if line is None:
        return None
    try:
        meta = dict(getattr(line, "metadata_json", None) or {})
        v = meta.get("shop_spec_code")
        if v not in (None, "", "null"):
            return str(v).strip() or None

        plid = getattr(line, "product_link_id", None)
        if plid not in (None, "", "null"):
            return str(plid).strip() or None

        rr = dict(getattr(line, "raw_row_json", None) or {})
        det = rr.get("detail") if isinstance(rr, dict) else None
        if isinstance(det, dict):
            v = det.get("tradeGoodsno") or det.get("tradeGoodsNo")
            if v not in (None, "", "null"):
                return str(v).strip() or None
        ship = rr.get("shipment") if isinstance(rr, dict) else None
        if isinstance(ship, dict):
            gd = ship.get("goodsDetail")
            if isinstance(gd, list):
                for g in gd:
                    if isinstance(g, dict):
                        v = g.get("tradeGoodsno") or g.get("tradeGoodsNo")
                        if v not in (None, "", "null"):
                            return str(v).strip() or None
        for key in ("规格编码", "规格编码(网店)", "商家编码", "shop_spec_code", "merchant_sku"):
            v = rr.get(key) if isinstance(rr, dict) else None
            if v not in (None, "", "null"):
                return str(v).strip() or None
    except Exception:  # noqa: BLE001
        return None
    return None


def _extract_shop_spec_code_raw_from_line(line: Any) -> Optional[str]:
    """
    返回归一化前的 ERP 原始 ``tradeGoodsno`` —— 仅当它跟归一化后的展示值不同时返回，否则 None。

    给 UI Tooltip 用：让运营能看到我们对脏数据"剥前缀"的归一化决策。
    若该行从未做过归一化（或 raw 已与 normalized 一致），返回 None；前端就不会显示
    "(已归一化) ERP 原始: ..." 提示。
    """
    if line is None:
        return None
    try:
        meta = getattr(line, "metadata_json", None) or {}
        if isinstance(meta, dict):
            raw = meta.get("shop_spec_code_raw")
            if raw not in (None, "", "null"):
                s = str(raw).strip()
                normalized = str(meta.get("shop_spec_code") or "").strip()
                if s and s != normalized:
                    return s
    except Exception:  # noqa: BLE001
        return None
    return None


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()  # noqa: S324 - non-crypto use (idempotency key)


def _sha1_text(text: str) -> str:
    return _sha1_bytes((text or "").encode("utf-8"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_preview_dir() -> None:
    PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _preview_cache_path(file_hash: str) -> Path:
    safe = str(file_hash or "").strip()
    return PREVIEW_CACHE_DIR / f"{safe}.xlsx"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


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
        # minimal parsing: try common formats
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


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _norm_str(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    s = str(value).strip()
    return s or None


def _clip(value: Optional[str], max_len: int) -> Optional[str]:
    if not value:
        return None
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _norm_header(value: Any) -> Optional[str]:
    """
    Normalize Excel header cells for robustness across ERP export variants:
    - collapse whitespace
    - convert full-width parentheses （） -> ()
    - strip trailing parenthesized notes, e.g. "货品条码（系统）" -> "货品条码"
    """
    s = _norm_str(value)
    if not s:
        return None
    s2 = (
        s.replace("（", "(")
        .replace("）", ")")
        .replace("\u00a0", " ")
    )
    s2 = re.sub(r"\s+", " ", s2).strip()
    # Strip trailing notes "(...)" — keep the core label
    s2 = re.sub(r"\([^)]*\)\s*$", "", s2).strip()
    return s2 or None


SHIPMENT_FIELD_ALIASES: Dict[str, List[str]] = {
    # Excel headers / future API keys (keep most common first)
    "shipment_no": ["发货单号", "单号", "订单号", "shipment_no"],
    # 网店原始订单号（天猫订单编号等）
    "order_no": ["原始单号", "网店订单号", "订单编号", "order_no", "shop_order_no"],
    # 商品链接ID（天猫链接ID等）
    "product_link_id": ["商品链接ID", "商品链接Id", "商品链接id", "product_link_id", "productLinkId"],
    "completed_at": ["完成时间", "付款时间", "completed_at", "finished_at"],
    "channel": ["销售渠道", "店铺", "渠道", "channel", "shop_name"],
    # ERP: 货品条码（系统）是主键；但发货表里通常写成“货品条码”
    "sku_code": ["货品条码", "货品条码（系统）", "SKU", "sku_code", "erp_sku_barcode", "barcode"],
    # “交易规格”/“商品规格（网店）”同义：以网店实时规格为第一优先
    "spec_text": ["商品规格（网店）", "交易规格", "规格", "规格信息", "货品规格（系统）", "spec_text", "shop_spec_text", "system_spec_text"],
    "qty": ["数量", "数量合计", "发货数量", "qty", "quantity"],
    "revenue_amount": ["金额", "实付金额", "revenue_amount", "paid_amount"],
    # Important for future ERP API: our pre-filled merchant code (spec code on shop)
    "shop_spec_code": ["规格编码（网店）", "商家编码", "shop_spec_code", "merchant_sku"],
    # Mapping dimension (1 barcode -> many platform_sku_id)
    "platform_sku_id": ["平台规格Id（网店）", "platform_sku_id", "platformSkuId"],
    # Optional tag for downstream filtering (e.g. 刷单/正常/补发)
    "tag": ["标记", "标签", "tag"],
}


def _has_any_header(headers: Dict[str, int], candidates: List[str]) -> bool:
    for c in candidates or []:
        key = _norm_header(c) or str(c)
        if key in headers:
            return True
    return False


def _get_field(row: List[Any], headers: Dict[str, int], field: str) -> Any:
    aliases = SHIPMENT_FIELD_ALIASES.get(field) or []
    return _get_by_headers(row, headers, aliases)


def _build_header_index(header_row: Iterable[Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        name = _norm_header(cell)
        if not name:
            continue
        # keep the first occurrence for deterministic behavior
        if name not in mapping:
            mapping[name] = idx
    return mapping


def _get_by_headers(row: List[Any], headers: Dict[str, int], names: List[str]) -> Any:
    for name in names:
        key = _norm_header(name) or str(name)
        idx = headers.get(key)
        if idx is None:
            continue
        if 0 <= idx < len(row):
            return row[idx]
    return None


def _guess_spec_text(row: List[Any]) -> Optional[str]:
    # Heuristic for messy exports: if "交易规格" column missing, try find a cell like "颜色分类:...;尺寸:..."
    for v in row:
        s = _norm_str(v)
        if not s:
            continue
        if ("颜色" in s or "颜色分类" in s or "尺寸" in s) and (";" in s or "；" in s):
            return s
    return None


def _normalize_rows_from_xlsx(file_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.active
    # Some ERP/WPS exports write an invalid worksheet dimension like ref="A1"
    # even though sheetData contains the full table. In openpyxl read-only mode
    # that makes iter_rows stop at A1 and preview becomes "总行0".
    if hasattr(ws, "reset_dimensions"):
        try:
            ws.reset_dimensions()
        except Exception:
            pass
    it = ws.iter_rows(values_only=True)

    # Read a small prefix to detect header row reliably.
    prefix: List[Tuple[Any, ...]] = []
    for _ in range(50):
        try:
            prefix.append(next(it))
        except StopIteration:
            break
    if not prefix:
        return [], [{"warning": "EMPTY_FILE"}]

    alias_pool = {(_norm_header(x) or str(x)).strip() for xs in SHIPMENT_FIELD_ALIASES.values() for x in xs}
    best_idx = 0
    best_score = -1
    for idx, r in enumerate(prefix):
        cells = [(_norm_header(c) or "") for c in list(r or [])]
        score = sum(1 for c in cells if c and c in alias_pool)
        if score > best_score:
            best_score = score
            best_idx = idx

    headers = _build_header_index(list(prefix[best_idx]))
    warnings: List[Dict[str, Any]] = []

    def _warn(code: str, **extra: Any) -> None:
        payload = {"warning": code}
        payload.update(extra)
        warnings.append(payload)

    # Minimal header sanity (do not hard-fail; push warnings)
    required_fields = ["shipment_no", "completed_at", "channel", "sku_code", "qty"]
    missing_fields = [f for f in required_fields if not _has_any_header(headers, SHIPMENT_FIELD_ALIASES.get(f) or [])]
    if missing_fields:
        _warn("MISSING_HEADERS", missing_fields=missing_fields)

    normalized: List[Dict[str, Any]] = []

    # 1) Remaining rows in prefix after header
    for i, row in enumerate(prefix[best_idx + 1 :], start=best_idx + 2):
        row_list = list(row or [])
        # skip fully empty rows
        if not any(v not in (None, "") for v in row_list):
            continue

        shipment_no = _norm_str(_get_field(row_list, headers, "shipment_no"))
        order_no = _norm_str(_get_field(row_list, headers, "order_no"))
        product_link_id = _norm_str(_get_field(row_list, headers, "product_link_id"))
        completed_at = _parse_excel_datetime(_get_field(row_list, headers, "completed_at"))
        channel = _norm_str(_get_field(row_list, headers, "channel"))
        # ERP: 货品条码（系统）是主键；发货表可能写成“货品条码”
        sku_code = _norm_str(_get_field(row_list, headers, "sku_code"))
        # 规格优先：商品规格（网店）/交易规格（实时真实） -> 货品规格（系统）（可能滞后）
        spec_text = _norm_str(_get_field(row_list, headers, "spec_text"))
        if not spec_text:
            spec_text = _guess_spec_text(row_list)
        qty = _to_decimal(_get_field(row_list, headers, "qty"))
        revenue_amount = _to_decimal(_get_field(row_list, headers, "revenue_amount"))
        # 2026 新规则：渠道侧会携带“商家编码/网店规格编码”，用于前置绑定模型码/套装码等锚点
        shop_spec_code = _norm_str(_get_field(row_list, headers, "shop_spec_code"))
        # 维度：平台规格Id（网店）
        platform_sku_id = _norm_str(_get_field(row_list, headers, "platform_sku_id"))
        tag = _norm_str(_get_field(row_list, headers, "tag"))

        raw_row: Dict[str, Any] = {}
        for name, idx in headers.items():
            if idx < len(row_list):
                raw_row[name] = row_list[idx]

        normalized.append(
            {
                "row_index": i,
                "shipment_no": shipment_no,
                "order_no": order_no,
                "product_link_id": product_link_id,
                "completed_at": completed_at,
                "channel": channel,
                "sku_code": sku_code,
                "shop_spec_code": shop_spec_code,
                "platform_sku_id": platform_sku_id,
                "tag": tag,
                "spec_text": spec_text,
                "qty": qty,
                "revenue_amount": revenue_amount,
                "raw_row": _json_safe(raw_row),
            }
        )

    # 2) Stream the rest rows (iterator continues after prefix)
    row_i = len(prefix) + 1
    for row in it:
        row_list = list(row or [])
        if not any(v not in (None, "") for v in row_list):
            row_i += 1
            continue

        shipment_no = _norm_str(_get_field(row_list, headers, "shipment_no"))
        order_no = _norm_str(_get_field(row_list, headers, "order_no"))
        product_link_id = _norm_str(_get_field(row_list, headers, "product_link_id"))
        completed_at = _parse_excel_datetime(_get_field(row_list, headers, "completed_at"))
        channel = _norm_str(_get_field(row_list, headers, "channel"))
        sku_code = _norm_str(_get_field(row_list, headers, "sku_code"))
        spec_text = _norm_str(_get_field(row_list, headers, "spec_text"))
        if not spec_text:
            spec_text = _guess_spec_text(row_list)
        qty = _to_decimal(_get_field(row_list, headers, "qty"))
        revenue_amount = _to_decimal(_get_field(row_list, headers, "revenue_amount"))
        shop_spec_code = _norm_str(_get_field(row_list, headers, "shop_spec_code"))
        platform_sku_id = _norm_str(_get_field(row_list, headers, "platform_sku_id"))
        tag = _norm_str(_get_field(row_list, headers, "tag"))

        raw_row: Dict[str, Any] = {}
        for name, idx in headers.items():
            if idx < len(row_list):
                raw_row[name] = row_list[idx]

        normalized.append(
            {
                "row_index": row_i,
                "shipment_no": shipment_no,
                "order_no": order_no,
                "product_link_id": product_link_id,
                "completed_at": completed_at,
                "channel": channel,
                "sku_code": sku_code,
                "shop_spec_code": shop_spec_code,
                "platform_sku_id": platform_sku_id,
                "tag": tag,
                "spec_text": spec_text,
                "qty": qty,
                "revenue_amount": revenue_amount,
                "raw_row": _json_safe(raw_row),
            }
        )
        row_i += 1

    return normalized, warnings


def _upsert_spec_snapshot(db: Session, *, spec_text: str) -> models.SpecParseSnapshot:
    normalized = spec_parser_service.normalize_tx_spec_text(spec_text)
    spec_hash = _sha1_text(normalized)
    existing = (
        db.query(models.SpecParseSnapshot)
        .filter(models.SpecParseSnapshot.spec_hash == spec_hash)
        .first()
    )
    if existing:
        return existing

    parsed = spec_parser_service.parse_spec(normalized)
    dimensions = {
        "width_cm": parsed.get("width_cm"),
        "height_cm": parsed.get("height_cm"),
        "diameter_cm": parsed.get("diameter_cm"),
        "area_m2": parsed.get("area_m2"),
        "perimeter_m": parsed.get("perimeter_m"),
    }
    snap = models.SpecParseSnapshot(
        spec_hash=spec_hash,
        # store normalized text (raw tx spec is kept on shipment_lines.spec_text for audit)
        spec_text=normalized,
        tokens_json=list(parsed.get("tokens") or []),
        dimensions_json=_json_safe(dimensions),
        parser_version=PARSER_VERSION,
        parse_json=_json_safe(parsed),
    )
    db.add(snap)
    db.flush()
    return snap


def _enqueue_exception(
    db: Session,
    *,
    batch_id: str,
    shipment_line_id: Optional[str],
    reason: str,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> models.ShipmentExceptionQueue:
    exc = models.ShipmentExceptionQueue(
        batch_id=batch_id,
        shipment_line_id=shipment_line_id,
        reason=reason,
        message=message,
        payload_json=_json_safe(payload or {}),
    )
    db.add(exc)
    db.flush()
    return exc


def _generate_long_tail_fallback_snapshot(
    db: Session,
    *,
    batch: models.ShipmentImportBatch,
    line: models.ShipmentLine,
) -> Optional[models.BomSnapshot]:
    """Sprint 3-2 / Issue 28: build a placeholder BomSnapshot +
    ShipmentCostingResult for a long-tail SKU using a per-category rate.

    Why: SKUs marked ``governance_status='do_not_model'`` skip BOM
    generation, but profit reports still need a cogs estimate so margins
    aren't artificially inflated. The rate comes from
    ``long_tail_strategy_service.resolve_rate_for_sku`` which picks (in
    order): manual category override → keyword strategy → 'default'
    strategy → ``settings.long_tail_cogs_rate``.

    The chosen rate + source + category + matched_keyword are written into
    ``trace_json``, so historical reports remain auditable even after the
    strategy table changes. Re-runs are idempotent (existing snapshot
    returned as-is).
    """
    sku_code = (line.sku_code or "").strip()
    if not sku_code:
        return None

    existing = (
        db.query(models.BomSnapshot)
        .filter(models.BomSnapshot.shipment_line_id == line.id)
        .first()
    )
    if existing is not None:
        return existing

    sku_master = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == sku_code)
        .first()
    )
    resolved = long_tail_strategy_service.resolve_rate_for_sku(
        db, sku=sku_master, sku_code=sku_code
    )
    rate = float(resolved.rate)
    revenue = line.revenue_amount or Decimal("0")
    qty = line.qty if line.qty is not None else Decimal("1")
    fallback_cogs = (Decimal(str(revenue)) * Decimal(str(rate))).quantize(Decimal("0.01"))

    note_pieces = [
        "SKU is marked governance_status='do_not_model'; cogs estimated "
        f"as revenue * {rate}.",
    ]
    if resolved.source == "manual":
        note_pieces.append(f"strategy: 人工标 long_tail_category='{resolved.category}'")
    elif resolved.source == "keyword":
        note_pieces.append(
            f"strategy: 关键字命中 category='{resolved.category}', keyword='{resolved.matched_keyword}'"
        )
    elif resolved.source == "default_strategy":
        note_pieces.append("strategy: 兜底策略 category='default'")
    else:
        note_pieces.append("strategy: 全局 settings.long_tail_cogs_rate")

    trace: Dict[str, Any] = {
        "kind": "long_tail_fallback",
        "long_tail_cogs_rate": rate,
        "rate_source": resolved.source,
        "strategy_id": resolved.strategy_id,
        "strategy_category": resolved.category,
        "matched_keyword": resolved.matched_keyword,
        "shipment_line_id": line.id,
        "batch_id": batch.id,
        "revenue_at_compute": str(revenue),
        "fallback_cogs": str(fallback_cogs),
        "note": " | ".join(note_pieces),
    }
    snap = models.BomSnapshot(
        batch_id=batch.id,
        shipment_line_id=line.id,
        shipment_no=line.shipment_no,
        sku_code=sku_code,
        model_version_id=None,
        spec_hash=None,
        qty=Decimal(str(qty)),
        final_lines_json=[],
        trace_json=_json_safe(trace),
        generated_at=_utcnow(),
    )
    db.add(snap)
    db.flush()

    # Persist a costing result so profit reports can sum cogs without
    # special-casing long-tail SKUs.
    existing_costing = (
        db.query(models.ShipmentCostingResult)
        .filter(models.ShipmentCostingResult.shipment_line_id == line.id)
        .first()
    )
    if existing_costing is None:
        costing = models.ShipmentCostingResult(
            batch_id=batch.id,
            shipment_line_id=line.id,
            mode="2026",
            sku_code=sku_code,
            model_version_id=None,
            spec_hash=None,
            qty=Decimal(str(qty)),
            cost_total=fallback_cogs,
            cost_material_total=fallback_cogs,
            computed_at=_utcnow(),
            metadata_json=_json_safe(
                {
                    "kind": "long_tail_fallback",
                    "long_tail_cogs_rate": rate,
                    "rate_source": resolved.source,
                    "strategy_id": resolved.strategy_id,
                    "strategy_category": resolved.category,
                    "matched_keyword": resolved.matched_keyword,
                    "revenue_at_compute": str(revenue),
                }
            ),
        )
        db.add(costing)
        db.flush()

    return snap


def _finalize_shipment_line(
    db: Session,
    *,
    batch: models.ShipmentImportBatch,
    line: models.ShipmentLine,
    channel: Optional[str] = None,
    shop_spec_code: Optional[str] = None,
    platform_sku_id: Optional[str] = None,
    spec_text_norm: Optional[str] = None,
    autobackfill_source: str = "shipment_autobackfill",
    extra_metadata: Optional[Dict[str, Any]] = None,
    mode: str = "2026",
    process_snapshots: bool = True,
) -> Optional[models.BomSnapshot]:
    """
    Per-line "post-create" pipeline shared by both shipment-line producers:

    - Excel path  (``import_shipment_xlsx``)  - line just inserted from xlsx row
    - Jackyun path (``process_existing_shipment_lines``) - line already in DB
       from ``integrations.jackyun.mappers.shipment.upsert_shipment_from_payload``

    What it does, in order:
      1. Copy bundle-template metadata from SkuMaster onto the line
         (so BOM snapshot trace can preserve bundle anchors).
      2. ``ensure_from_shipment`` - autobackfill SkuMaster if first-seen,
         refresh ``_shipment_seen`` metadata otherwise. Idempotent.
      3. Revision chain: if a previous active line for the same
         ``revision_group_hash`` exists, mark them superseded.
      4. Generate ``BomSnapshot`` (or persist deduction artifacts only,
         depending on mode + ``process_snapshots``).

    Returns the BomSnapshot if one was created, else None.

    NOTE: callers are responsible for committing. This function only
    flushes to make ids visible.
    """
    sku_code = line.sku_code
    spec_text = line.spec_text
    shipment_no = line.shipment_no

    try:
        sm = sku_master_service.get_by_barcode(db, sku_code or "")
        sm_meta = dict(getattr(sm, "metadata_json", None) or {}) if sm else {}
        bt_code = sm_meta.get("bundle_template_code")
        bt_id = sm_meta.get("bundle_template_id")
        bt_sel = sm_meta.get("bundle_preset_selector")
        if bt_code not in (None, "") or bt_id not in (None, "") or bt_sel not in (None, ""):
            meta_line = dict(line.metadata_json or {})
            meta_line.setdefault("bundle_template_id", bt_id)
            meta_line.setdefault("bundle_template_code", bt_code)
            meta_line.setdefault("bundle_preset_selector", bt_sel)
            line.metadata_json = {k: v for k, v in meta_line.items() if v not in (None, "")}
    except Exception:
        # best-effort only; do not fail shipment processing
        pass

    sm_metadata: Dict[str, Any] = {
        "source": autobackfill_source,
        # keys aligned with sku_master_service._update_shipment_seen expectations
        "batch_id": batch.id,
        "shipment_import_batch_id": batch.id,
        "shipment_line_id": line.id,
        "shipment_no": shipment_no,
        "spec_hash": _sha1_text(spec_text_norm) if spec_text_norm else None,
        "shop_spec_code": shop_spec_code,
        "platform_sku_id": platform_sku_id,
    }
    if extra_metadata:
        sm_metadata.update({k: v for k, v in extra_metadata.items() if v is not None})

    sm_row = sku_master_service.ensure_from_shipment(
        db,
        erp_sku_barcode=sku_code or "",
        spec_text=spec_text,
        channel=channel or line.channel,
        metadata=sm_metadata,
    )

    # ----- Governance gating (Sprint 2-2 of "SKU 治理与按需建模") -----
    # Operators classify each SkuMaster.metadata_json.governance_status
    # via BatchWorkbench. The worker reacts:
    #   do_not_model     -> silently skip parsing & exception queue (long-tail
    #                       SKU; cost is filled later by the long-tail fallback,
    #                       Sprint 3-2). Operators are not pestered again.
    #   pending_model    -> still enqueue exception (so it stays visible in
    #                       BatchWorkbench), but with reason='MODEL_PENDING'
    #                       so the UI can present a different action set
    #                       ("modeling in progress, do not bind manually").
    #   unmanaged        -> default path; SKU_NOT_BOUND etc.
    #   auto_bound       -> default path; will produce a BomSnapshot.
    governance_status = sku_master_service.get_sku_governance_status(sm_row)
    if governance_status == sku_master_service.GOVERNANCE_DO_NOT_MODEL:
        meta_line = dict(line.metadata_json or {})
        meta_line["skipped_reason"] = "governance:do_not_model"
        line.metadata_json = _json_safe(meta_line)
        # Sprint 3-2: long-tail fallback. Generate a placeholder snapshot
        # + costing row using the global rate, so profit reports include
        # an estimated cogs (instead of zero, which inflates margin).
        # Disabled via settings.long_tail_cogs_fallback_enabled=False
        # for ops that prefer "no number > wrong number".
        if process_snapshots and getattr(
            settings, "long_tail_cogs_fallback_enabled", True
        ):
            return _generate_long_tail_fallback_snapshot(db, batch=batch, line=line)
        return None
    if governance_status == sku_master_service.GOVERNANCE_PENDING_MODEL:
        _enqueue_exception(
            db,
            batch_id=batch.id,
            shipment_line_id=line.id,
            reason="MODEL_PENDING",
            message="SKU 已加入建模 backlog，等待模型建好后自动绑定",
            payload={"sku_code": sku_code, "governance_status": governance_status},
        )
        batch.exception_rows = (batch.exception_rows or 0) + 1
        return None

    if line.revision_group_hash:
        prevs = (
            db.query(models.ShipmentLine)
            .filter(
                models.ShipmentLine.revision_group_hash == line.revision_group_hash,
                models.ShipmentLine.id != line.id,
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
            )
            .order_by(models.ShipmentLine.revision_no.desc())
            .all()
        )
        if prevs:
            line.revision_no = (prevs[0].revision_no or 1) + 1
            for p in prevs:
                p.is_active = False
                p.superseded_by_id = line.id

    if not process_snapshots:
        return None

    persist_snapshot = str(mode or "2026") != "2025"
    if persist_snapshot:
        existing_snapshot = (
            db.query(models.BomSnapshot)
            .filter(models.BomSnapshot.shipment_line_id == line.id)
            .first()
        )
        if existing_snapshot:
            return existing_snapshot
        snap = _generate_bom_snapshot(db, batch=batch, line=line, persist_snapshot=True, mode=mode)
        if snap is None:
            batch.exception_rows = (batch.exception_rows or 0) + 1
        return snap

    # 2025 mode: no per-line snapshots; still persist deduction artifacts
    _generate_bom_snapshot(db, batch=batch, line=line, persist_snapshot=False, mode=mode)
    return None


def _generate_bom_snapshot(
    db: Session,
    *,
    batch: models.ShipmentImportBatch,
    line: models.ShipmentLine,
    persist_snapshot: bool = True,
    mode: str = "2026",
) -> Optional[models.BomSnapshot]:
    sku = (line.sku_code or "").strip()
    if not sku:
        _enqueue_exception(
            db,
            batch_id=batch.id,
            shipment_line_id=line.id,
            reason="MISSING_SKU",
            message="sku_code 为空",
        )
        return None

    spec_text = (line.spec_text or "").strip()
    if not spec_text:
        _enqueue_exception(
            db,
            batch_id=batch.id,
            shipment_line_id=line.id,
            reason="SPEC_EMPTY",
            message="spec_text 为空",
        )
        return None

    binding = product_model_service.get_active_sku_binding(db, sku)
    if not binding:
        _enqueue_exception(
            db,
            batch_id=batch.id,
            shipment_line_id=line.id,
            reason="SKU_NOT_BOUND",
            message="SKU 未绑定已发布版本",
            payload={"sku_code": sku},
        )
        return None

    # spec cache (by spec_hash)
    spec_snap = _upsert_spec_snapshot(db, spec_text=spec_text)

    qty = line.qty if line.qty is not None else Decimal("1")
    # Stage 2（2026-05-10）：发货行回溯按发货当日取价。`completed_at` 缺失时
    # （比如 PoD/手填行）保持老行为 None=今天，避免 break 已有路径。
    as_of: Optional[date] = None
    if isinstance(line.completed_at, datetime):
        as_of = line.completed_at.date()
    try:
        bom = bom_generation_service.generate_bom(
            db,
            spec_text=spec_text,
            model_version_id=None,
            sku_code=sku,
            quantity=Decimal(str(qty)),
            as_of_date=as_of,
        )
    except Exception as exc:  # noqa: BLE001 - queue exception
        _enqueue_exception(
            db,
            batch_id=batch.id,
            shipment_line_id=line.id,
            reason="BOM_GENERATION_FAILED",
            message=str(exc),
            payload={"sku_code": sku, "spec_hash": spec_snap.spec_hash},
        )
        return None

    # Persist lightweight deduction artifacts (2025/2026 unified)
    _persist_deduction_artifacts(
        db,
        batch=batch,
        line=line,
        bom=bom,
        bound_version_id=binding.model_version_id,
        spec_hash=spec_snap.spec_hash,
        mode=mode,
    )

    if not persist_snapshot:
        return None

    trace = dict(bom.get("trace") or {})
    # Bundle anchors (Phase0): carry bundle binding from shipment line metadata into snapshot trace.
    try:
        meta_line = dict(getattr(line, "metadata_json", None) or {})
        bt_code = meta_line.get("bundle_template_code")
        bt_id = meta_line.get("bundle_template_id")
        bt_sel = meta_line.get("bundle_preset_selector")
        if bt_code not in (None, "") or bt_id not in (None, "") or bt_sel not in (None, ""):
            trace.setdefault("bundle", {})
            if isinstance(trace.get("bundle"), dict):
                trace["bundle"].update(
                    {
                        "template_id": bt_id,
                        "template_code": bt_code,
                        "preset_selector": bt_sel,
                    }
                )
    except Exception:
        pass
    trace.update(
        {
            "bound_version_id": binding.model_version_id,
            "spec_hash": spec_snap.spec_hash,
            "shipment_line_id": line.id,
            "batch_id": batch.id,
        }
    )
    snap = models.BomSnapshot(
        batch_id=batch.id,
        shipment_line_id=line.id,
        shipment_no=line.shipment_no,
        sku_code=sku,
        model_version_id=trace.get("model_version_id") or binding.model_version_id,
        spec_hash=spec_snap.spec_hash,
        qty=Decimal(str(qty)),
        final_lines_json=_json_safe(list(bom.get("final_material_lines") or [])),
        trace_json=_json_safe(trace),
        generated_at=_utcnow(),
    )
    db.add(snap)
    db.flush()
    return snap


def _persist_deduction_artifacts(
    db: Session,
    *,
    batch: models.ShipmentImportBatch,
    line: models.ShipmentLine,
    bom: Dict[str, Any],
    bound_version_id: Optional[str],
    spec_hash: str,
    mode: str,
) -> None:
    """
    Persist lightweight costing + inventory deduction lines without storing big per-line snapshot trace.
    This is the backbone for 2025 "deduct but no snapshots" mode.
    """

    # Idempotent upsert-by-replace for this shipment line
    db.query(models.ShipmentInventoryDeductionLine).filter(
        models.ShipmentInventoryDeductionLine.shipment_line_id == line.id
    ).delete(synchronize_session=False)
    db.query(models.ShipmentCostingResult).filter(
        models.ShipmentCostingResult.shipment_line_id == line.id
    ).delete(synchronize_session=False)

    trace = bom.get("trace") if isinstance(bom.get("trace"), dict) else {}
    costing = trace.get("costing") if isinstance(trace.get("costing"), dict) else {}
    inventory = trace.get("inventory") if isinstance(trace.get("inventory"), dict) else {}
    inv_lines = inventory.get("inventory_lines") if isinstance(inventory.get("inventory_lines"), list) else []
    inv_warnings = inventory.get("warnings") if isinstance(inventory.get("warnings"), list) else []

    # model_version_id is critical for historical explainability
    model_version_id = trace.get("model_version_id") or bound_version_id

    qty = line.qty if line.qty is not None else Decimal("1")

    def _d(v: Any) -> Optional[Decimal]:
        if v in (None, ""):
            return None
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:  # noqa: BLE001
            return None

    cost_total = _d(costing.get("total_cost"))
    cost_material = _d(costing.get("material_cost_total"))
    cost_process = _d(costing.get("process_cost_total"))
    cost_overhead = _d(costing.get("overhead_cost"))

    # backward-compatible fallback: compute total_cost from components if missing
    if cost_total is None:
        parts = [x for x in [cost_material, cost_process, cost_overhead] if x is not None]
        if parts:
            cost_total = sum(parts, Decimal("0"))

    # Stage 2（2026-05-10）：把每行物料的 price_metadata（含税还原 / 生效期 / 价格来源 /
    # 数据质量）汇集到 cost_breakdown.materials[]，供 ShipmentLedgerPage / RealtimePricingPage
    # 直接展示，前端无需重新查 BOM 源。老 cost_breakdown 老字段（price/subtotal）保持兼容，
    # price_metadata 是**新增**子对象——老 endpoint 不读不会崩。
    cost_breakdown_materials: List[Dict[str, Any]] = []
    final_lines = bom.get("final_material_lines") if isinstance(bom.get("final_material_lines"), list) else []
    for fl in final_lines or []:
        if not isinstance(fl, dict):
            continue
        kind = str(fl.get("material_kind") or "real")
        if kind not in ("real", "bom"):
            continue
        line_qty = fl.get("computed_quantity")
        line_price = fl.get("bom_unit_price")
        line_cost = fl.get("line_cost")
        try:
            qty_f = float(line_qty) if line_qty is not None else None
            price_f = float(line_price) if line_price is not None else None
            cost_f = float(line_cost) if line_cost is not None else None
        except Exception:  # noqa: BLE001
            qty_f, price_f, cost_f = None, None, None
        cost_breakdown_materials.append(
            {
                "material_id": fl.get("material_ref_id"),
                "material_code": fl.get("material_code"),
                "material_name": fl.get("material_name"),
                "qty": qty_f,
                # 老字段：price/subtotal 保持向后兼容（不含税口径，本次起被 Stage 2 修正过）
                "price": price_f,
                "subtotal": cost_f,
                # 新增：Stage 2 元数据（前端 tooltip / 新列、反推诊断）
                "price_metadata": fl.get("price_metadata"),
            }
        )

    quality_counts = costing.get("material_price_quality_counts") if isinstance(costing.get("material_price_quality_counts"), dict) else {}

    result = models.ShipmentCostingResult(
        shipment_line_id=line.id,
        batch_id=batch.id,
        mode=str(mode or "2026"),
        sku_code=line.sku_code,
        model_version_id=model_version_id,
        spec_hash=spec_hash,
        parser_version=PARSER_VERSION,
        qty=Decimal(str(qty)),
        cost_total=cost_total,
        cost_material_total=cost_material,
        cost_process_total=cost_process,
        cost_overhead_total=cost_overhead,
        computed_at=_utcnow(),
        metadata_json=_json_safe(
            {
                "inventory_warning_count": len(inv_warnings or []),
                "inventory_warnings": list(inv_warnings or [])[:20],
                "bundle_template_id": (line.metadata_json or {}).get("bundle_template_id")
                if isinstance(line.metadata_json, dict)
                else None,
                "bundle_template_code": (line.metadata_json or {}).get("bundle_template_code")
                if isinstance(line.metadata_json, dict)
                else None,
                "bundle_preset_selector": (line.metadata_json or {}).get("bundle_preset_selector")
                if isinstance(line.metadata_json, dict)
                else None,
                # Stage 2: cost_breakdown 子对象。老前端忽略；新前端读
                # ``cost_breakdown.materials[].price_metadata`` 渲染价格来源/含税/质量徽章。
                "cost_breakdown": {
                    "materials": cost_breakdown_materials,
                    "material_price_quality_counts": dict(quality_counts),
                    "material_price_resolved_at": costing.get("material_price_resolved_at"),
                },
            }
        ),
    )
    db.add(result)
    db.flush()

    for r in inv_lines:
        if not isinstance(r, dict):
            continue
        qty_used = _d(r.get("quantity"))
        if qty_used is None:
            continue
        db.add(
            models.ShipmentInventoryDeductionLine(
                shipment_line_id=line.id,
                batch_id=batch.id,
                mode=str(mode or "2026"),
                material_id=str(r.get("material_id") or "") or None,
                material_code=str(r.get("material_code") or "") or None,
                material_name=str(r.get("material_name") or "") or None,
                unit_of_measure=str(r.get("unit_of_measure") or "") or None,
                quantity=qty_used,
                metadata_json=_json_safe({"sources": r.get("sources")}),
            )
        )


def import_shipment_xlsx(
    db: Session,
    *,
    file_name: str,
    file_bytes: bytes,
    export_date: Optional[str],
    requested_by: Optional[str],
    mode: str = "2026",
    process_snapshots: bool = True,
) -> models.ShipmentImportBatch:
    file_hash = _sha1_bytes(file_bytes)
    batch = (
        db.query(models.ShipmentImportBatch)
        .filter(models.ShipmentImportBatch.file_hash == file_hash)
        .first()
    )
    if batch and batch.status == "success":
        return batch

    if not batch:
        batch = models.ShipmentImportBatch(
            file_name=file_name,
            file_hash=file_hash,
            export_date=export_date,
            requested_by=requested_by,
            status="processing",
        )
        db.add(batch)
        db.flush()
    else:
        # retry for non-success batches
        batch.file_name = file_name
        batch.export_date = export_date
        batch.requested_by = requested_by
        batch.status = "processing"
        batch.total_rows = 0
        batch.inserted_rows = 0
        batch.skipped_rows = 0
        batch.exception_rows = 0
        batch.warnings_json = []
        batch.result_json = {}

    # Persist "processing" status early so UI can reflect long-running imports.
    db.commit()
    db.refresh(batch)

    rows, warnings = _normalize_rows_from_xlsx(file_bytes)
    batch.warnings_json = warnings

    chunk = max(int(getattr(settings, "csv_import_chunk_size", 500) or 500), 50)

    for payload in rows:
        batch.total_rows += 1
        shipment_no = payload.get("shipment_no")
        sku_code = payload.get("sku_code")
        spec_text = payload.get("spec_text")
        qty = payload.get("qty")
        revenue_amount = payload.get("revenue_amount")

        spec_text_norm = spec_parser_service.normalize_tx_spec_text(spec_text or "") if spec_text else ""
        revision_group = _sha1_text("|".join([shipment_no or "", sku_code or "", spec_text_norm or ""]))
        ext_hash = _sha1_text(
            "|".join(
                [
                    shipment_no or "",
                    sku_code or "",
                    spec_text_norm or "",
                    str(qty) if qty is not None else "",
                    str(revenue_amount) if revenue_amount is not None else "",
                ]
            )
        )

        exists = (
            db.query(models.ShipmentLine)
            .filter(
                models.ShipmentLine.external_line_key_hash == ext_hash,
                models.ShipmentLine.is_archived.is_(False),
            )
            .first()
        )
        if exists:
            batch.skipped_rows += 1
            continue

        line = models.ShipmentLine(
            batch_id=batch.id,
            row_index=int(payload.get("row_index") or 0),
            shipment_no=_clip(shipment_no, 255),
            order_no=_clip(payload.get("order_no"), 255),
            product_link_id=_clip(payload.get("product_link_id"), 255),
            completed_at=payload.get("completed_at"),
            channel=_clip(payload.get("channel"), 255),
            sku_code=_clip(sku_code, 255),
            spec_text=spec_text,
            spec_hash=_sha1_text(spec_text_norm) if spec_text_norm else None,
            qty=qty,
            revenue_amount=revenue_amount,
            external_line_key_hash=ext_hash,
            revision_group_hash=revision_group,
            revision_no=1,
            is_active=True,
            tag=(payload.get("tag") or None),
            raw_row_json=payload.get("raw_row") or {},
            normalize_warnings_json=[],
            metadata_json={
                k: v
                for k, v in {
                    "shop_spec_code": payload.get("shop_spec_code"),
                    "platform_sku_id": payload.get("platform_sku_id"),
                }.items()
                if v not in (None, "")
            },
        )
        db.add(line)
        db.flush()

        batch.inserted_rows += 1

        _finalize_shipment_line(
            db,
            batch=batch,
            line=line,
            channel=payload.get("channel"),
            shop_spec_code=payload.get("shop_spec_code"),
            platform_sku_id=payload.get("platform_sku_id"),
            spec_text_norm=spec_text_norm,
            autobackfill_source="shipment_autobackfill",
            mode=mode,
            process_snapshots=process_snapshots,
        )

        # Periodic commit for large imports:
        # - reduce long-running transactions / row locks
        # - make progress visible in UI (total/inserted/exception counts)
        if batch.total_rows % chunk == 0:
            batch.updated_at = _utcnow()
            db.commit()
            db.refresh(batch)

    batch.status = "success"
    batch.result_json = {
        "batch_id": batch.id,
        "file_hash": batch.file_hash,
        "counts": {
            "total_rows": batch.total_rows,
            "inserted_rows": batch.inserted_rows,
            "skipped_rows": batch.skipped_rows,
            "exception_rows": batch.exception_rows,
        },
    }
    db.commit()
    db.refresh(batch)
    return batch


def process_existing_shipment_lines(
    db: Session,
    *,
    batch_id: str,
    mode: str = "2026",
    process_snapshots: bool = True,
    autobackfill_source: str = "jackyun_autobackfill",
) -> models.ShipmentImportBatch:
    """
    Worker entry point for batches whose ``ShipmentLine`` rows are already
    in the database (Jackyun integration path; potentially other future
    integration sources).

    Differs from ``import_shipment_xlsx`` only in the source of lines:
      - xlsx path:    rows come from a parsed Excel file
      - this path:    lines were upserted by an integration mapper
                      (e.g. ``integrations.jackyun.mappers.shipment``)

    Per-line work is delegated to the shared ``_finalize_shipment_line`` so
    that the BOM-generation / model-binding / exception-queue behaviour is
    identical between Excel and integration paths.

    Idempotent: BomSnapshot reuses the per-line existing snapshot (see
    ``_finalize_shipment_line``); ``ensure_from_shipment`` is idempotent;
    revision chain only fires when there is a real prior active row.
    Re-running on the same batch is therefore safe (and used by
    ``_repair_terminal_processing_batches`` indirectly).

    The integration mapper already set ``batch.total_rows`` and
    ``batch.inserted_rows`` based on its own insert/update split; we do
    NOT touch those counters here. We only update ``exception_rows`` (via
    ``_finalize_shipment_line``) and the final ``status`` / ``result_json``.
    """
    batch = db.get(models.ShipmentImportBatch, batch_id)
    if not batch:
        raise ValueError(f"ShipmentImportBatch {batch_id!r} 不存在")

    if batch.status not in ("processing", "queued"):
        # Worker contract: _claim_next_queued_batch already flipped to
        # 'processing'. Treat anything terminal as a no-op so a buggy retry
        # doesn't double-process.
        return batch

    if batch.status == "queued":
        batch.status = "processing"
        batch.updated_at = _utcnow()
        db.commit()
        db.refresh(batch)

    chunk = max(int(getattr(settings, "csv_import_chunk_size", 500) or 500), 50)

    lines = (
        db.query(models.ShipmentLine)
        .filter(
            models.ShipmentLine.batch_id == batch.id,
            models.ShipmentLine.is_archived.is_(False),
        )
        .order_by(models.ShipmentLine.row_index.asc())
        .all()
    )

    # exception_rows is recomputed from scratch by _finalize_shipment_line
    # to keep semantics identical to xlsx path. Reset before the loop so a
    # second run doesn't double-count.
    batch.exception_rows = 0
    processed = 0
    for line in lines:
        spec_text = line.spec_text or ""
        spec_text_norm = (
            spec_parser_service.normalize_tx_spec_text(spec_text) if spec_text else ""
        )
        meta = dict(getattr(line, "metadata_json", None) or {})
        # 商家编码：优先用 line.metadata（新版 jackyun mapper 已经写入），
        # 历史行兜底从 ShipmentLine.product_link_id（旧 mapper 把 tradeGoodsno 写在这）
        # 或 raw_row.detail.tradeGoodsno 兜底，确保旧批次重跑也能补到 shop_spec_code。
        shop_spec_code = meta.get("shop_spec_code") or _extract_shop_spec_code_from_line(line)
        _finalize_shipment_line(
            db,
            batch=batch,
            line=line,
            channel=line.channel,
            shop_spec_code=shop_spec_code,
            platform_sku_id=meta.get("platform_sku_id"),
            spec_text_norm=spec_text_norm,
            autobackfill_source=autobackfill_source,
            extra_metadata={
                "source_system": getattr(line, "source_system", None),
                "source_record_id": getattr(line, "source_record_id", None),
                "source_line_id": getattr(line, "source_line_id", None),
            },
            mode=mode,
            process_snapshots=process_snapshots,
        )
        processed += 1
        if processed % chunk == 0:
            batch.updated_at = _utcnow()
            db.commit()
            db.refresh(batch)

    snapshot_count = (
        db.query(func.count(models.BomSnapshot.id))
        .filter(models.BomSnapshot.batch_id == batch.id)
        .scalar()
        or 0
    )
    exception_count = (
        db.query(func.count(models.ShipmentExceptionQueue.id))
        .filter(models.ShipmentExceptionQueue.batch_id == batch.id)
        .scalar()
        or 0
    )
    costing_count = (
        db.query(func.count(models.ShipmentCostingResult.id))
        .filter(models.ShipmentCostingResult.batch_id == batch.id)
        .scalar()
        or 0
    )

    batch.status = "success"
    batch.exception_rows = int(exception_count)
    prev_result = dict(batch.result_json or {})
    batch.result_json = {
        **prev_result,
        "batch_id": batch.id,
        "file_hash": batch.file_hash,
        "counts": {
            "total_rows": batch.total_rows,
            "inserted_rows": batch.inserted_rows,
            "skipped_rows": batch.skipped_rows,
            "exception_rows": int(exception_count),
            "bom_snapshots": int(snapshot_count),
            "costing_results": int(costing_count),
        },
        "processed_lines": processed,
    }
    batch.updated_at = _utcnow()
    db.commit()
    db.refresh(batch)
    return batch


def preview_shipment_xlsx(
    db: Session,
    *,
    file_name: str,
    file_bytes: bytes,
    export_date: Optional[str],
    requested_by: Optional[str],
    issue_limit: int = 200,
    ready_limit: int = 200,
) -> Dict[str, Any]:
    """
    Preview-only: parse xlsx rows, compute readiness & issues, and cache file bytes for later execute.
    Does NOT write shipment_lines / bom_snapshots.
    """
    issue_limit = max(min(int(issue_limit or 200), 2000), 1)
    file_hash = _sha1_bytes(file_bytes)
    rows, warnings = _normalize_rows_from_xlsx(file_bytes)

    total_rows = 0
    ready_rows = 0
    missing_sku_rows = 0
    missing_spec_rows = 0
    unbound_sku_rows = 0
    issues: List[Dict[str, Any]] = []
    ready_items: List[Dict[str, Any]] = []

    # Preload bindings for this file (avoid per-row db calls)
    sku_codes_all = [str(p.get("sku_code") or "").strip() for p in rows if str(p.get("sku_code") or "").strip()]
    bindings = (
        db.query(models.SkuModelVersionMapping)
        .filter(
            models.SkuModelVersionMapping.sku_code.in_(list(set(sku_codes_all))),
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
        .order_by(models.SkuModelVersionMapping.sku_code.asc(), models.SkuModelVersionMapping.created_at.desc())
        .all()
    )
    latest_binding: Dict[str, models.SkuModelVersionMapping] = {}
    for b in bindings:
        if b.sku_code not in latest_binding:
            latest_binding[b.sku_code] = b

    version_ids = [b.model_version_id for b in latest_binding.values() if getattr(b, "model_version_id", None)]
    versions = (
        db.query(models.ProductModelVersion)
        .options(joinedload(models.ProductModelVersion.model))
        .filter(models.ProductModelVersion.id.in_(list(set(version_ids))), models.ProductModelVersion.is_archived.is_(False))
        .all()
        if version_ids
        else []
    )
    by_vid: Dict[str, models.ProductModelVersion] = {v.id: v for v in versions}

    for payload in rows:
        total_rows += 1
        shipment_no = payload.get("shipment_no")
        sku_code = payload.get("sku_code")
        spec_text = payload.get("spec_text")
        row_index = payload.get("row_index")

        if not sku_code:
            missing_sku_rows += 1
            if len(issues) < issue_limit:
                issues.append(
                    {
                        "row_index": row_index,
                        "shipment_no": shipment_no,
                        "sku_code": sku_code,
                        "spec_text": spec_text,
                        "reason": "MISSING_SKU",
                    }
                )
            continue
        if not spec_text:
            missing_spec_rows += 1
            if len(issues) < issue_limit:
                issues.append(
                    {
                        "row_index": row_index,
                        "shipment_no": shipment_no,
                        "sku_code": sku_code,
                        "spec_text": spec_text,
                        "reason": "SPEC_EMPTY",
                    }
                )
            continue
        binding = latest_binding.get(str(sku_code))
        if not binding:
            unbound_sku_rows += 1
            if len(issues) < issue_limit:
                issues.append(
                    {
                        "row_index": row_index,
                        "shipment_no": shipment_no,
                        "sku_code": sku_code,
                        "spec_text": spec_text,
                        "reason": "SKU_NOT_BOUND",
                    }
                )
            continue
        ready_rows += 1
        if len(ready_items) < max(min(int(ready_limit or 200), 1000), 1):
            v = by_vid.get(getattr(binding, "model_version_id", None))
            m = getattr(v, "model", None) if v else None
            ready_items.append(
                {
                    "row_index": row_index,
                    "shipment_no": shipment_no,
                    "sku_code": sku_code,
                    "spec_text": spec_text,
                    "qty": payload.get("qty"),
                    "model_version_id": getattr(binding, "model_version_id", None),
                    "bound_model_code": getattr(m, "model_code", None),
                    "bound_model_name": getattr(m, "model_name", None),
                    "bound_version_label": getattr(v, "version_label", None),
                }
            )

    # cache file for execute step
    _ensure_preview_dir()
    path = _preview_cache_path(file_hash)
    try:
        path.write_bytes(file_bytes)
    except Exception:  # noqa: BLE001
        # If cache fails, still return preview (but execute will require re-upload)
        pass

    return {
        "preview_id": file_hash,
        "file_name": file_name,
        "export_date": export_date,
        "total_rows": total_rows,
        "ready_rows": ready_rows,
        "missing_sku_rows": missing_sku_rows,
        "missing_spec_rows": missing_spec_rows,
        "unbound_sku_rows": unbound_sku_rows,
        "warnings": warnings,
        "issues": issues,
        "ready_items": ready_items,
        "requested_by": requested_by,
    }


def execute_shipment_xlsx_from_preview(
    db: Session,
    *,
    preview_id: str,
    file_name: Optional[str] = None,
    export_date: Optional[str],
    requested_by: Optional[str],
    mode: str = "2026",
    process_snapshots: bool = True,
) -> models.ShipmentImportBatch:
    """
    Execute import using cached preview file (by file_hash).
    """
    pid = (preview_id or "").strip()
    if not pid:
        raise ValueError("preview_id 不能为空")
    path = _preview_cache_path(pid)
    if not path.exists():
        raise ValueError("预览缓存文件不存在，请重新预览上传")
    file_bytes = path.read_bytes()
    return import_shipment_xlsx(
        db,
        file_name=(file_name or f"preview:{pid}.xlsx"),
        file_bytes=file_bytes,
        export_date=export_date,
        requested_by=requested_by,
        mode=mode,
        process_snapshots=process_snapshots,
    )


def preview_cache_exists(preview_id: str) -> bool:
    pid = (preview_id or "").strip()
    if not pid:
        return False
    return _preview_cache_path(pid).exists()


def process_execute_from_preview_job(
    batch_id: str,
    *,
    preview_id: str,
    file_name: Optional[str],
    export_date: Optional[str],
    requested_by: Optional[str],
    mode: str = "2026",
) -> None:
    """
    Background task entrypoint for /shipments/import/execute.
    Runs the heavy import in a new DB session to avoid request timeouts.
    """
    session: Session = SessionLocal()
    try:
        execute_shipment_xlsx_from_preview(
            session,
            preview_id=preview_id,
            file_name=file_name,
            export_date=export_date,
            requested_by=requested_by,
            mode=mode,
        )
    except Exception as exc:  # noqa: BLE001 - background task must not crash worker
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            batch = session.get(models.ShipmentImportBatch, batch_id)
            if batch:
                batch.status = "failed"
                batch.result_json = {
                    "error": str(exc)[:500],
                    "stage": "execute_from_preview",
                }
                session.commit()
        except Exception:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    finally:
        session.close()


def spawn_execute_from_preview_job(
    batch_id: str,
    *,
    preview_id: str,
    file_name: Optional[str],
    export_date: Optional[str],
    requested_by: Optional[str],
    mode: str = "2026",
) -> None:
    """
    Spawn a detached process to run the heavy import, so the API worker is not blocked.
    """
    pid = (preview_id or "").strip()
    if not pid:
        raise ValueError("preview_id 不能为空")
    if not preview_cache_exists(pid):
        raise ValueError("预览缓存文件不存在，请重新预览上传")

    backend_dir = Path(__file__).resolve().parents[3]
    script = backend_dir / "scripts" / "run_shipment_execute_from_preview.py"
    if not script.exists():
        raise ValueError("后台执行脚本缺失，请联系管理员")

    cmd = [
        sys.executable,
        str(script),
        "--batch-id",
        str(batch_id),
        "--preview-id",
        str(pid),
        "--mode",
        str(mode or "2026"),
    ]
    if file_name:
        cmd += ["--file-name", str(file_name)]
    if export_date:
        cmd += ["--export-date", str(export_date)]
    if requested_by:
        cmd += ["--requested-by", str(requested_by)]

    # Detach: do not block API process; capture output for debugging.
    log_dir = backend_dir / "logs" / "jobs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"shipment_execute_{batch_id}.log"
    with out_path.open("ab") as fp:
        env = dict(os.environ)
        # Ensure backend root is importable for `import src.*`
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{backend_dir}:{existing_pp}" if existing_pp else str(backend_dir)
        subprocess.Popen(  # noqa: S603,S607 - internal trusted command, args are not shell-expanded
            cmd,
            cwd=str(backend_dir),
            stdout=fp,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )


def get_batch(db: Session, batch_id: str) -> Optional[models.ShipmentImportBatch]:
    return db.get(models.ShipmentImportBatch, batch_id)


def list_batches(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[int, List[models.ShipmentImportBatch]]:
    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 20), 200), 1)
    query = db.query(models.ShipmentImportBatch).order_by(models.ShipmentImportBatch.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def list_exceptions(
    db: Session,
    *,
    batch_id: Optional[str] = None,
    resolved: Optional[bool] = None,
    sku_code: Optional[str] = None,
    channel: Optional[str] = None,
    spec_text: Optional[str] = None,
    limit: int = 200,
) -> List[models.ShipmentExceptionQueue]:
    limit = max(min(int(limit or 200), 1000), 1)
    query = db.query(models.ShipmentExceptionQueue)
    if batch_id:
        query = query.filter(models.ShipmentExceptionQueue.batch_id == batch_id)
    if resolved is True:
        query = query.filter(models.ShipmentExceptionQueue.resolved_at.isnot(None))
    elif resolved is False:
        query = query.filter(models.ShipmentExceptionQueue.resolved_at.is_(None))

    # Server-side filters (important for large batches): avoid "limit truncation then client-side filter".
    if sku_code or channel or spec_text:
        query = query.join(
            models.ShipmentLine, models.ShipmentLine.id == models.ShipmentExceptionQueue.shipment_line_id
        ).filter(models.ShipmentLine.is_archived.is_(False))
        if sku_code:
            s = f"%{str(sku_code).strip()}%"
            query = query.filter(models.ShipmentLine.sku_code.ilike(s))
        if channel:
            s = f"%{str(channel).strip()}%"
            query = query.filter(models.ShipmentLine.channel.ilike(s))
        if spec_text:
            s = f"%{str(spec_text).strip()}%"
            query = query.filter(models.ShipmentLine.spec_text.ilike(s))
    items = query.order_by(models.ShipmentExceptionQueue.created_at.desc()).limit(limit).all()

    # Attach shipment line fields for readability (Excel-like columns)
    line_ids = [x.shipment_line_id for x in items if getattr(x, "shipment_line_id", None)]
    if not line_ids:
        return items
    uniq_line_ids = list(set(line_ids))
    lines = db.query(models.ShipmentLine).filter(models.ShipmentLine.id.in_(uniq_line_ids)).all()
    by_id = {l.id: l for l in lines}

    # current binding (sku -> model) for “已重新关联”快速判断
    sku_codes = list({str(getattr(l, "sku_code", "") or "").strip() for l in lines if getattr(l, "sku_code", None)})
    sku_to_model: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    if sku_codes:
        bind_rows = (
            db.query(
                models.SkuModelVersionMapping.sku_code,
                models.ProductModel.model_code,
                models.ProductModel.model_name,
            )
            .select_from(models.SkuModelVersionMapping)
            .join(
                models.ProductModelVersion,
                models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
            )
            .join(
                models.ProductModel,
                models.ProductModel.id == models.ProductModelVersion.model_id,
            )
            .filter(
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.sku_code.in_(sku_codes),
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModel.is_archived.is_(False),
            )
            .all()
        )
        for sku, mc, mn in bind_rows:
            if sku:
                sku_to_model[str(sku)] = (str(mc) if mc else None, str(mn) if mn else None)

    # Prefer sku-master preparse cache for “规格解析” (this matches what users operate in spec-matching).
    sku_to_preparse: Dict[str, Tuple[bool, Optional[Decimal], Optional[Decimal]]] = {}
    if sku_codes:
        sms = (
            db.query(models.SkuMaster)
            .filter(
                models.SkuMaster.is_archived.is_(False),
                models.SkuMaster.erp_sku_barcode.in_(sku_codes),
            )
            .all()
        )
        for sm in sms:
            sku = str(getattr(sm, "erp_sku_barcode", "") or "").strip()
            if not sku:
                continue
            meta = getattr(sm, "metadata_json", None) or {}
            if not isinstance(meta, dict):
                meta = {}
            parsed = bool(str(meta.get("preparse_spec_hash") or "").strip())
            dims = meta.get("preparse_dimensions") if isinstance(meta.get("preparse_dimensions"), dict) else {}
            w = _to_decimal(dims.get("width_cm")) if isinstance(dims, dict) else None
            h = _to_decimal(dims.get("height_cm")) if isinstance(dims, dict) else None
            sku_to_preparse[sku] = (parsed, w, h)

    # Fallback: spec parse snapshot dims (spec_hash -> width/height) for old data
    spec_hashes = list({str(getattr(l, "spec_hash", "") or "").strip() for l in lines if getattr(l, "spec_hash", None)})
    spec_dims: Dict[str, Tuple[Optional[Decimal], Optional[Decimal]]] = {}
    if spec_hashes:
        snaps = db.query(models.SpecParseSnapshot).filter(models.SpecParseSnapshot.spec_hash.in_(spec_hashes)).all()
        for s in snaps:
            dims = getattr(s, "dimensions_json", None) or {}
            w = _to_decimal(dims.get("width_cm")) if isinstance(dims, dict) else None
            h = _to_decimal(dims.get("height_cm")) if isinstance(dims, dict) else None
            spec_dims[str(s.spec_hash)] = (w, h)
    for exc in items:
        line = by_id.get(getattr(exc, "shipment_line_id", None))
        if not line:
            continue
        # Pydantic orm_mode will read these dynamic attributes
        exc.row_index = getattr(line, "row_index", None)
        exc.shipment_no = getattr(line, "shipment_no", None)
        exc.completed_at = getattr(line, "completed_at", None)
        exc.channel = getattr(line, "channel", None)
        exc.sku_code = getattr(line, "sku_code", None)
        exc.spec_text = getattr(line, "spec_text", None)
        exc.spec_hash = getattr(line, "spec_hash", None)
        sku = str(getattr(line, "sku_code", "") or "").strip()
        mc, mn = sku_to_model.get(sku, (None, None))
        exc.bound_model_code = mc
        exc.bound_model_name = mn
        # spec parse status/dims (prefer sku-master preparse)
        if sku and sku in sku_to_preparse:
            parsed, w, h = sku_to_preparse[sku]
            exc.spec_parsed = bool(parsed)
            exc.spec_width_cm = w
            exc.spec_height_cm = h
        else:
            sh = str(getattr(line, "spec_hash", "") or "").strip()
            if sh and sh in spec_dims:
                exc.spec_parsed = True
                w, h = spec_dims.get(sh, (None, None))
                exc.spec_width_cm = w
                exc.spec_height_cm = h
            else:
                exc.spec_parsed = False
        exc.qty = getattr(line, "qty", None)
        exc.revenue_amount = getattr(line, "revenue_amount", None)
    return items


def list_bom_snapshots(
    db: Session,
    *,
    batch_id: Optional[str] = None,
    sku_code: Optional[str] = None,
    shipment_no: Optional[str] = None,
    spec_hash: Optional[str] = None,
    limit: int = 200,
) -> List[models.BomSnapshot]:
    limit = max(min(int(limit or 200), 1000), 1)
    query = db.query(models.BomSnapshot)
    if batch_id:
        query = query.filter(models.BomSnapshot.batch_id == batch_id)
    if sku_code:
        query = query.filter(models.BomSnapshot.sku_code == sku_code)
    if shipment_no:
        query = query.filter(models.BomSnapshot.shipment_no == shipment_no)
    if spec_hash:
        query = query.filter(models.BomSnapshot.spec_hash == spec_hash)
    items = query.order_by(models.BomSnapshot.created_at.desc()).limit(limit).all()

    # Attach shipment line fields for readability (Excel-like columns)
    line_ids = [getattr(x, "shipment_line_id", None) for x in items if getattr(x, "shipment_line_id", None)]
    if not line_ids:
        return items
    lines = (
        db.query(models.ShipmentLine)
        .filter(models.ShipmentLine.id.in_(list(set(line_ids))))
        .all()
    )
    by_id = {l.id: l for l in lines}
    for snap in items:
        line = by_id.get(getattr(snap, "shipment_line_id", None))
        if not line:
            continue
        # Pydantic orm_mode will read these dynamic attributes
        snap.row_index = getattr(line, "row_index", None)
        snap.shipment_no = getattr(line, "shipment_no", None)
        snap.completed_at = getattr(line, "completed_at", None)
        snap.channel = getattr(line, "channel", None)
        snap.sku_code = getattr(line, "sku_code", None)
        snap.spec_text = getattr(line, "spec_text", None)
        snap.spec_hash = getattr(line, "spec_hash", None)
        snap.qty = getattr(line, "qty", None)
        snap.revenue_amount = getattr(line, "revenue_amount", None)
    return items


def get_bom_snapshot(db: Session, *, snapshot_id: str) -> Optional[models.BomSnapshot]:
    sid = (snapshot_id or "").strip()
    if not sid:
        return None
    snap = db.get(models.BomSnapshot, sid)
    if not snap or getattr(snap, "is_archived", False):
        return None
    # Attach shipment line fields for readability (Excel-like columns)
    line = db.get(models.ShipmentLine, getattr(snap, "shipment_line_id", None))
    if line and not getattr(line, "is_archived", False):
        snap.row_index = getattr(line, "row_index", None)
        snap.shipment_no = getattr(line, "shipment_no", None)
        snap.completed_at = getattr(line, "completed_at", None)
        snap.channel = getattr(line, "channel", None)
        snap.sku_code = getattr(line, "sku_code", None)
        snap.spec_text = getattr(line, "spec_text", None)
        snap.spec_hash = getattr(line, "spec_hash", None)
        snap.qty = getattr(line, "qty", None)
        snap.revenue_amount = getattr(line, "revenue_amount", None)
    return snap


def list_deduction_lines(db: Session, *, shipment_line_id: str) -> List[models.ShipmentInventoryDeductionLine]:
    lid = (shipment_line_id or "").strip()
    if not lid:
        return []
    return (
        db.query(models.ShipmentInventoryDeductionLine)
        .filter(
            models.ShipmentInventoryDeductionLine.shipment_line_id == lid,
        )
        .order_by(models.ShipmentInventoryDeductionLine.material_code.asc().nullslast())
        .all()
    )


def get_costing_result(db: Session, *, shipment_line_id: str) -> Optional[models.ShipmentCostingResult]:
    lid = (shipment_line_id or "").strip()
    if not lid:
        return None
    return (
        db.query(models.ShipmentCostingResult)
        .filter(models.ShipmentCostingResult.shipment_line_id == lid)
        .order_by(models.ShipmentCostingResult.created_at.desc())
        .first()
    )


def list_process_cost_lines(db: Session, *, shipment_line_id: str) -> List[Dict[str, Any]]:
    """
    工序明细（用于台账抽屉核对）：
    - 以“该发货行最新 BOM 快照”为准（尺寸来源：snapshot.trace.parsed；数量来源：shipment_lines.qty）
    - 工序来源：当前版本配置的 model_version_processes
    - 计算口径：与 bom_generation_service._compute_process_costing 一致（计时/计件）
    """
    lid = (shipment_line_id or "").strip()
    if not lid:
        return []

    snap = (
        db.query(models.BomSnapshot)
        .filter(models.BomSnapshot.shipment_line_id == lid)
        .order_by(models.BomSnapshot.created_at.desc())
        .first()
    )
    line = db.get(models.ShipmentLine, lid)
    if not snap or not line or getattr(snap, "is_archived", False) or getattr(line, "is_archived", False):
        return []

    trace = snap.trace_json if isinstance(snap.trace_json, dict) else {}
    parsed = trace.get("parsed") if isinstance(trace.get("parsed"), dict) else {}

    # version id: snapshot -> trace -> costing_result fallback
    version_id = (
        str(getattr(snap, "model_version_id", "") or "").strip()
        or str(parsed.get("model_version_id") or "").strip()
        or str(trace.get("model_version_id") or "").strip()
    )
    if not version_id:
        cr = get_costing_result(db, shipment_line_id=lid)
        version_id = str(getattr(cr, "model_version_id", "") or "").strip() if cr else ""
    if not version_id:
        return []

    qty = getattr(line, "qty", None)
    try:
        quantity = Decimal(str(qty)) if qty not in (None, "") else Decimal("1")
    except Exception:  # noqa: BLE001
        quantity = Decimal("1")

    def _d(v: Any) -> Optional[Decimal]:
        if v in (None, ""):
            return None
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:  # noqa: BLE001
            return None

    width_cm = _d(parsed.get("width_cm"))
    height_cm = _d(parsed.get("height_cm"))
    area_m2 = _d(parsed.get("area_m2"))
    perimeter_m = _d(parsed.get("perimeter_m"))

    # best-effort compute from width/height if missing
    if area_m2 is None and width_cm is not None and height_cm is not None:
        try:
            area_m2 = (width_cm * height_cm) / Decimal("10000")
        except Exception:  # noqa: BLE001
            area_m2 = None
    if perimeter_m is None and width_cm is not None and height_cm is not None:
        try:
            perimeter_m = (Decimal("2") * (width_cm + height_cm)) / Decimal("100")
        except Exception:  # noqa: BLE001
            perimeter_m = None

    vps = product_model_service.list_version_process_lines(db, version_id)

    out: List[Dict[str, Any]] = []
    for row in vps or []:
        meta = row.metadata_json or {}
        proc = db.get(models.Process, row.process_id) if getattr(row, "process_id", None) else None

        pricing_method = str(meta.get("pricing_method") or "count")
        pricing_method = pricing_method if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height") else "count"

        # measure qty (unit follows pricing_method):
        # - count: 件数
        # - area: ㎡
        # - perimeter/width/height: 米
        if pricing_method == "fixed":
            measure_qty = Decimal("1")
        elif pricing_method == "area":
            measure_qty = (area_m2 or Decimal("0")) * quantity
        elif pricing_method == "perimeter":
            measure_qty = (perimeter_m or Decimal("0")) * quantity
        elif pricing_method == "width":
            measure_qty = ((width_cm or Decimal("0")) / Decimal("100")) * quantity
        elif pricing_method == "height":
            measure_qty = ((height_cm or Decimal("0")) / Decimal("100")) * quantity
        else:
            measure_qty = quantity

        cost_type = str(meta.get("cost_type") or "").strip() or None
        base_minutes = _d(meta.get("base_minutes")) or Decimal("0")
        unit_minutes = _d(meta.get("unit_minutes")) or Decimal("0")
        rate = _d(meta.get("rate_per_minute"))
        piece = _d(meta.get("piece_rate"))

        if cost_type not in ("time", "piece"):
            cost_type = "piece" if (piece is not None and piece > 0) else "time"

        warnings: List[str] = []
        total_minutes: Optional[Decimal] = None
        total_cost: Optional[Decimal] = None
        if cost_type == "time":
            total_minutes = base_minutes + (unit_minutes * measure_qty)
            if rate is not None and rate > 0:
                total_cost = total_minutes * rate
            else:
                warnings.append("未配置分钟单价（rate_per_minute）")
        else:
            if piece is not None and piece > 0:
                total_cost = measure_qty * piece
            else:
                warnings.append("未配置计件单价（piece_rate）")

        out.append(
            {
                "process_code": getattr(proc, "process_code", None) if proc else None,
                "process_name": getattr(proc, "process_name", None) if proc else None,
                "team_name": (meta.get("team_name") or (getattr(proc, "team_name", None) if proc else None)),
                "pricing_method": pricing_method,
                "measure_quantity": measure_qty,
                "cost_type": cost_type,
                "base_minutes": base_minutes,
                "unit_minutes": unit_minutes,
                "rate_per_minute": rate,
                "piece_rate": piece,
                "total_minutes": total_minutes,
                "total_cost": total_cost,
                "warnings": warnings,
            }
        )

    return out


def list_profit_lines_by_batch(
    db: Session,
    *,
    batch_id: str,
    limit: int = 2000,
    include_missing: bool = False,
) -> Dict[str, Any]:
    """
    Profit sheet for a shipment import batch (line-level).
    - Revenue baseline: shipment_lines.revenue_amount (as imported).
    - Cost baseline: bom_snapshots.trace.costing.total_cost (generated at import-time for each shipment line).
    - Join strategy: left join shipment_lines with latest bom_snapshot per shipment_line_id (within this batch).
    """
    bid = (batch_id or "").strip()
    if not bid:
        raise ValueError("batch_id 不能为空")
    lim = max(min(int(limit or 2000), 5000), 1)

    def _d(v: Any) -> Decimal:
        if v in (None, ""):
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    def _extract_total_cost(trace_json: Any) -> Tuple[Optional[Decimal], str]:
        trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
        costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
        total_cost = costing.get("total_cost")
        if total_cost in (None, ""):
            total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
        cost = _d(total_cost)
        if cost == 0 and total_cost in (None, "", 0):
            return None, "missing_costing"
        return cost, "costed"

    # Latest snapshot per shipment_line_id within this batch.
    # Note: Postgres supports DISTINCT ON; SQLAlchemy maps distinct(column) to it.
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.spec_hash.label("spec_hash"),
            models.BomSnapshot.generated_at.label("generated_at"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.batch_id == bid)
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    q = (
        db.query(models.ShipmentLine, snap_sq)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(models.ShipmentLine.batch_id == bid, models.ShipmentLine.is_archived.is_(False))
        .order_by(models.ShipmentLine.row_index.asc().nullslast(), models.ShipmentLine.created_at.asc())
        .limit(lim)
    )
    rows = q.all()

    total_lines = (
        db.query(models.ShipmentLine)
        .filter(models.ShipmentLine.batch_id == bid, models.ShipmentLine.is_archived.is_(False))
        .count()
    )

    items: List[Dict[str, Any]] = []
    lines_with_bom = 0
    missing_costing = 0

    for line, snap in rows:
        has_snap = bool(getattr(snap, "bom_snapshot_id", None))
        if not include_missing and not has_snap:
            continue

        revenue = _d(getattr(line, "revenue_amount", None))
        qty = _d(getattr(line, "qty", None))

        cost_amount: Optional[Decimal] = None
        status = "missing_snapshot"
        note = None
        if has_snap:
            lines_with_bom += 1
            cost_amount, status = _extract_total_cost(getattr(snap, "trace_json", None))
            if status == "missing_costing":
                missing_costing += 1
                note = "快照缺成本字段（trace.costing.total_cost 为空）"
        else:
            note = "未生成 BOM 快照（未计价/未扣库）"

        gross_profit = (revenue - cost_amount) if (cost_amount is not None) else None
        gross_margin = (gross_profit / revenue) if (gross_profit is not None and revenue > 0) else None

        items.append(
            {
                "shipment_line_id": str(getattr(line, "id", "")),
                "row_index": getattr(line, "row_index", None),
                "shipment_no": getattr(line, "shipment_no", None),
                "completed_at": getattr(line, "completed_at", None),
                "channel": getattr(line, "channel", None),
                "sku_code": getattr(line, "sku_code", None),
                "spec_text": getattr(line, "spec_text", None),
                "qty": qty if qty != 0 else None,
                "revenue_amount": revenue if revenue != 0 else None,
                "bom_snapshot_id": str(getattr(snap, "bom_snapshot_id", "")) if has_snap else None,
                "model_version_id": getattr(snap, "model_version_id", None) if has_snap else None,
                "spec_hash": getattr(snap, "spec_hash", None) if has_snap else None,
                "generated_at": getattr(snap, "generated_at", None) if has_snap else None,
                "cost_amount": cost_amount,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "status": status,
                "note": note,
            }
        )

    return {
        "batch_id": bid,
        "total_shipment_lines": int(total_lines),
        "lines_with_bom_snapshots": int(lines_with_bom),
        "lines_missing_costing": int(missing_costing),
        "items": items,
        "note": "利润表口径：revenue=发货行金额；cost=快照 trace.costing.total_cost（导入时生成）；profit=revenue-cost。",
    }


def list_shipment_lines(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    batch_id: Optional[str] = None,
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
    shipment_no: Optional[str] = None,
    order_no: Optional[str] = None,
    product_link_id: Optional[str] = None,
    status: Optional[str] = None,  # processed | pending | None
    spec_text: Optional[str] = None,
    bound_target_kind: Optional[str] = None,  # any | model | bundle
    bound_model_code: Optional[str] = None,
    bound_version_label: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    unresolved_reason: Optional[str] = None,
    suspected_mismatch: Optional[bool] = None,
    include_issue_hints: Optional[bool] = None,
    ready_to_generate: Optional[bool] = None,
    need_rebuild_snapshot: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Shipment daily ledger (line-level) across batches.

    Status definition (2025/2026 unified):
    - processed: has either bom_snapshot (2026) OR shipment_costing_result (2025 or unified).
    - pending: not processed (often due to missing binding/spec parse/bom generation), can be diagnosed via unresolved exception.
    """
    p = max(int(page or 1), 1)
    ps = max(min(int(page_size or 50), 200), 1)
    st = (status or "").strip().lower() or None
    if st not in (None, "processed", "pending"):
        raise ValueError("status 仅支持 processed / pending / 空")

    # "snapshot_cleared" (soft invalidation): if set, treat line as pending and exclude from analytics until rebuilt.
    cleared_pred = func.nullif(
        func.trim(func.coalesce(models.ShipmentLine.metadata_json["snapshot_cleared_at"].as_string(), "")),
        "",
    ).isnot(None)

    # Backward-compat: older frontend used to concatenate bundle selector into bound_model_code,
    # e.g. "B-DB9EAEAE" (template DB9EAE + selector AE).
    # If caller didn't pass bundle_preset_selector, try split last 2 letters.
    if not bundle_preset_selector and bound_target_kind:
        k0 = str(bound_target_kind or "").strip().lower()
        if k0 in ("bundle", "bundles"):
            raw = str(bound_model_code or "").strip().upper()
            m2 = re.match(r"^([BZ]-[A-Z0-9]{4,32})([A-Z]{2})$", raw)
            if m2:
                bound_model_code = m2.group(1)
                bundle_preset_selector = m2.group(2)

    # Correlated EXISTS predicates (fast with indexes on shipment_line_id).
    has_bom = (
        db.query(models.BomSnapshot.id)
        .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
        .exists()
    )
    has_costing = (
        db.query(models.ShipmentCostingResult.id)
        .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
        .exists()
    )
    processed_pred = and_(or_(has_bom, has_costing), ~cleared_pred)

    unresolved_reason_sq = (
        db.query(models.ShipmentExceptionQueue.reason)
        .filter(
            models.ShipmentExceptionQueue.shipment_line_id == models.ShipmentLine.id,
            models.ShipmentExceptionQueue.resolved_at.is_(None),
        )
        .order_by(models.ShipmentExceptionQueue.created_at.desc())
        .limit(1)
        .correlate(models.ShipmentLine)
        .scalar_subquery()
    )
    unresolved_message_sq = (
        db.query(models.ShipmentExceptionQueue.message)
        .filter(
            models.ShipmentExceptionQueue.shipment_line_id == models.ShipmentLine.id,
            models.ShipmentExceptionQueue.resolved_at.is_(None),
        )
        .order_by(models.ShipmentExceptionQueue.created_at.desc())
        .limit(1)
        .correlate(models.ShipmentLine)
        .scalar_subquery()
    )
    cost_mode_sq = (
        db.query(models.ShipmentCostingResult.mode)
        .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
        .limit(1)
        .correlate(models.ShipmentLine)
        .scalar_subquery()
    )
    cost_total_sq = (
        db.query(models.ShipmentCostingResult.cost_total)
        .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
        .limit(1)
        .correlate(models.ShipmentLine)
        .scalar_subquery()
    )
    latest_snapshot_id_sq = (
        db.query(models.BomSnapshot.id)
        .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
        .order_by(models.BomSnapshot.created_at.desc())
        .limit(1)
        .correlate(models.ShipmentLine)
        .scalar_subquery()
    )
    latest_snapshot_model_version_id_sq = (
        db.query(models.BomSnapshot.model_version_id)
        .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
        .order_by(models.BomSnapshot.created_at.desc())
        .limit(1)
        .correlate(models.ShipmentLine)
        .scalar_subquery()
    )

    # Active SKU -> model binding (BundleAsModel is represented as model_code like "B-XXXXYY").
    #
    # Perf history (read this BEFORE refactoring):
    # ----------------------------------------------
    # v1: 6 correlated scalar_subquery per row → slow (Issue 31, 2026-05-07).
    # v2: ONE binding subquery + LEFT JOIN with row_number() OVER PARTITION BY
    #     sku_code rn=1 → looked clean but Postgres planner picked
    #     Nested Loop Left Join (Materialize binding_sq → 83552 rows, scanned
    #     2156 times = 180 MILLION join-filter comparisons), 30+s on prod.
    # v3 (current): bare LEFT JOIN sku_model_version_mapping. We can drop
    #     row_number() entirely because the table already has a partial
    #     UNIQUE INDEX ``ux_sku_model_version_mapping_sku_code_active`` ON
    #     (sku_code) WHERE is_active=true AND is_archived=false. Each active
    #     SKU has at most ONE row, so a direct join is both correct AND lets
    #     the planner do a cheap unique-index lookup per outer row.
    #     Real-world impact: 已完成 30天 30s → ~0.3s (100×).
    m = models.SkuModelVersionMapping
    v = models.ProductModelVersion
    pm = models.ProductModel

    q = (
        db.query(
        models.ShipmentLine,
        has_bom.label("has_bom_snapshot"),
        has_costing.label("has_costing_result"),
        cleared_pred.label("snapshot_cleared"),
        latest_snapshot_id_sq.label("bom_snapshot_id"),
        latest_snapshot_model_version_id_sq.label("snapshot_model_version_id"),
        unresolved_reason_sq.label("unresolved_reason"),
        unresolved_message_sq.label("unresolved_message"),
        cost_mode_sq.label("cost_mode"),
        cost_total_sq.label("cost_total"),
        # IMPORTANT: read model_version_id from v.id, not m.model_version_id.
        # If the version was archived after binding, the LEFT JOIN below
        # NULLs out v/pm columns; using v.id keeps "no usable binding" a
        # single coherent state (all NULL) instead of a half-bound ghost
        # (id present but model_code/name/label NULL). Matches v2 behavior
        # where binding_sq INNER JOINed v and pm with is_archived=false.
        v.id.label("bound_model_version_id"),
        pm.id.label("bound_model_id"),
        pm.model_code.label("bound_model_code"),
        pm.model_name.label("bound_model_name"),
        v.version_label.label("bound_version_label"),
        func.nullif(
            func.upper(func.coalesce(v.metadata_json["bundle_preset_selector"].as_string(), "")),
            "",
        ).label("bundle_preset_selector"),
        )
        .outerjoin(
            m,
            and_(
                m.sku_code == models.ShipmentLine.sku_code,
                m.is_active.is_(True),
                m.is_archived.is_(False),
            ),
        )
        .outerjoin(v, and_(v.id == m.model_version_id, v.is_archived.is_(False)))
        .outerjoin(pm, and_(pm.id == v.model_id, pm.is_archived.is_(False)))
        .filter(
        models.ShipmentLine.is_archived.is_(False),
        models.ShipmentLine.is_active.is_(True),
        models.ShipmentLine.completed_at.isnot(None),
        )
    )
    if batch_id:
        bid = str(batch_id).strip()
        if bid:
            q = q.filter(models.ShipmentLine.batch_id == bid)

    # "疑似绑错" SQL-side filter — used by ``suspected_mismatch=true`` filter so the
    # paginated total matches what the user sees row-by-row.
    #
    # 数据源：每个已发布 standard 模型的 ``metadata.recognition_keywords``
    # （= 运营在标准模型编辑里维护的关键词，跟 Tier 1 行级精筛同源）。
    # 反向索引 keyword → set(model_id of owners)；SQL 拼成：
    #   OR( spec_text ILIKE %kw% AND pm.id NOT IN (该关键词的拥有模型集合) )
    # 即"发货命中某关键词，但当前绑定模型不是该关键词的拥有者 → 疑似绑错"。
    #
    # 多个模型共享同一关键词时也安全（NOT IN 一次排除全部拥有者）。
    # 完全没配 recognition_keywords 的模型 → 不参与任何 SQL 子句 → 计数 0
    # （行为与 Tier 1 行级精筛一致：运营没给信号就不报警）。
    has_target_binding = or_(
        pm.model_code.isnot(None),
        pm.model_name.isnot(None),
    )
    # 反向索引来自两个层级（OR 合并）：
    #   1) 模型级：ProductModel.metadata.recognition_keywords
    #   2) 变体级：ProductModelLineVariant.conditions_json.spec_contains_all / _any
    #              ── "伞型模型" 场景必须靠它，例如 OZU 模型本身只配"丝圈地垫"，
    #              但 OZU-002 变体覆盖"皮革桌垫"。没有变体级合并，
    #              发货含"皮革桌垫"且绑 OZU 会被误判为"应该绑 F6A"。
    kw_owners: Dict[str, set] = {}
    try:
        kw_index_rows = (
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
    except Exception:  # noqa: BLE001
        kw_index_rows = []
    # Tier A: 模型级
    for _km in kw_index_rows:
        meta_km = _km.metadata_json or {}
        raw_km = meta_km.get("recognition_keywords") if isinstance(meta_km, dict) else None
        if not isinstance(raw_km, list):
            continue
        for _x in raw_km:
            kk = str(_x or "").strip()
            if not kk:
                continue
            kw_owners.setdefault(kk, set()).add(str(_km.id))
    # Tier B: 变体级（spec_contains_all / spec_contains_any 中的非系统 token）
    try:
        version_to_model = {
            str(v.id): str(v.model_id)
            for v in (
                db.query(
                    models.ProductModelVersion.id,
                    models.ProductModelVersion.model_id,
                )
                .filter(
                    models.ProductModelVersion.is_archived.is_(False),
                    models.ProductModelVersion.version_kind == "standard",
                    models.ProductModelVersion.version_status == "published",
                )
                .all()
            )
        }
        if version_to_model:
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
                        # 跳过系统 token（如 ``MODEL:OZU`` / ``ATTR:xxx``，
                        # 它们是 spec 解析时由代码注入的而非真品类词）。
                        if not ts or ":" in ts:
                            continue
                        kw_owners.setdefault(ts, set()).add(mid)
    except Exception:  # noqa: BLE001
        # 变体级合并失败不应阻塞 Tier A；保留模型级反向索引继续工作。
        pass
    suspect_clauses = []
    for _kw, _mids in kw_owners.items():
        if not _kw or not _mids:
            continue
        suspect_clauses.append(
            and_(
                func.coalesce(models.ShipmentLine.spec_text, "").ilike(f"%{_kw}%"),
                ~pm.id.in_(list(_mids)),
            )
        )
    if suspect_clauses:
        # 排除运营已显式声明"绑定正确"的 SKU
        # （SkuMaster.metadata.suspect_misbind_resolved=True）。
        # 这些 SKU 不出现在「只看疑似绑错」总数和列表里，但绑定本身不变。
        not_resolved = ~exists().where(
            and_(
                models.SkuMaster.erp_sku_barcode == models.ShipmentLine.sku_code,
                models.SkuMaster.is_archived.is_(False),
                models.SkuMaster.metadata_json["suspect_misbind_resolved"].as_boolean() == True,  # noqa: E712
            )
        )
        suspected_mismatch_pred = and_(has_target_binding, or_(*suspect_clauses), not_resolved)
    else:
        # 还没有任何模型配 recognition_keywords → 该过滤器恒为 False（计数 0）。
        # 这是符合预期的：避免在"运营完全没维护关键词"时仍误报。
        suspected_mismatch_pred = literal(False)

    if start is not None:
        q = q.filter(models.ShipmentLine.completed_at >= start)
    if end is not None:
        q = q.filter(models.ShipmentLine.completed_at < end)
    if channel:
        q = q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        q = q.filter(models.ShipmentLine.sku_code == sku_code)
    if shipment_no:
        q = q.filter(models.ShipmentLine.shipment_no == shipment_no)
    if order_no:
        q = q.filter(models.ShipmentLine.order_no == order_no)
    if product_link_id:
        q = q.filter(models.ShipmentLine.product_link_id == product_link_id)
    if spec_text:
        pat = f"%{str(spec_text).strip()}%"
        q = q.filter(models.ShipmentLine.spec_text.ilike(pat))

    # Binding filters (current effective binding on SKU).
    # NOTE: All binding filters use ``pm.*`` / ``v.*`` directly (the LEFT JOIN
    # tables) rather than the old binding_sq subquery — see the perf-history
    # comment above the query for context.
    if bound_model_code:
        pat = f"%{str(bound_model_code).strip()}%"
        q = q.filter(func.coalesce(pm.model_code, "").ilike(pat))
    if bound_version_label:
        vlab = str(bound_version_label).strip()
        if vlab:
            q = q.filter(v.version_label == vlab)
    if bundle_preset_selector:
        sel = str(bundle_preset_selector).strip().upper()
        if sel:
            q = q.filter(
                func.nullif(
                    func.upper(func.coalesce(v.metadata_json["bundle_preset_selector"].as_string(), "")),
                    "",
                )
                == sel
            )
    if bound_target_kind:
        k = str(bound_target_kind).strip().lower()
        if k in ("bundle", "bundles"):
            q = q.filter(or_(pm.model_code.ilike("B-%"), pm.model_code.ilike("Z-%")))
        elif k in ("model", "models", "standard"):
            q = q.filter(
                and_(
                    pm.model_code.isnot(None),
                    ~pm.model_code.ilike("B-%"),
                    ~pm.model_code.ilike("Z-%"),
                )
            )

    if st == "processed":
        q = q.filter(processed_pred)
    elif st == "pending":
        q = q.filter(~processed_pred)

    if ready_to_generate is True:
        # “待生成”口径：当前为待处理，且已具备生成快照所需的最小条件（有条码、有规格、有有效绑定）
        q = q.filter(
            ~processed_pred,
            v.id.isnot(None),
            func.nullif(func.trim(func.coalesce(models.ShipmentLine.sku_code, "")), "").isnot(None),
            func.nullif(func.trim(func.coalesce(models.ShipmentLine.spec_text, "")), "").isnot(None),
        )
    if need_rebuild_snapshot is True:
        # “需重建”口径：已有快照（已处理），但快照记录的 model_version_id 与当前绑定不一致（包含“已清空绑定但有快照”）
        q = q.filter(
            has_bom,
            func.coalesce(v.id, "") != func.coalesce(latest_snapshot_model_version_id_sq, ""),
        )
    if unresolved_reason:
        rr = str(unresolved_reason).strip()
        if rr:
            q = q.filter(unresolved_reason_sq == rr)

    if suspected_mismatch is True:
        q = q.filter(suspected_mismatch_pred)
    elif suspected_mismatch is False:
        q = q.filter(~suspected_mismatch_pred)

    total = q.with_entities(func.count(models.ShipmentLine.id)).scalar() or 0

    rows = (
        q.order_by(models.ShipmentLine.completed_at.desc().nullslast(), models.ShipmentLine.created_at.desc())
        .offset((p - 1) * ps)
        .limit(ps)
        .all()
    )

    # Fallback for legacy rows: if costing_results is missing, try reading latest snapshot trace.costing.total_cost
    def _d2(v: Any) -> Decimal:
        if v in (None, ""):
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    def _extract_total_cost2(trace_json: Any) -> Optional[Decimal]:
        trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
        costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
        total_cost = costing.get("total_cost")
        if total_cost in (None, ""):
            total_cost = _d2(costing.get("material_cost_total")) + _d2(costing.get("process_cost_total")) + _d2(costing.get("overhead_cost"))
        cost = _d2(total_cost)
        if cost == 0 and total_cost in (None, "", 0):
            return None
        return cost

    snap_ids_need: List[str] = []
    for (
        _line0,
        _has_bom_snapshot0,
        _has_costing_result0,
        _snapshot_cleared0,
        _bom_snapshot_id0,
        _snapshot_model_version_id0,
        _unresolved_reason0,
        _unresolved_message0,
        _cost_mode0,
        _cost_total0,
        _bound_model_version_id0,
        _bound_model_id0_x,
        _bound_model_code0,
        _bound_model_name0,
        _bound_version_label0,
        _bound_bundle_preset_selector0,
    ) in rows:
        sid = str(_bom_snapshot_id0 or "").strip()
        if sid and _cost_total0 in (None, ""):
            snap_ids_need.append(sid)

    snap_cost: Dict[str, Decimal] = {}
    if snap_ids_need:
        snaps = (
            db.query(models.BomSnapshot.id, models.BomSnapshot.trace_json)
            .filter(models.BomSnapshot.id.in_(list(set(snap_ids_need))))
            .all()
        )
        for sid, tjson in snaps:
            c = _extract_total_cost2(tjson)
            if c is not None:
                snap_cost[str(sid)] = c

    # ---- 变体展示（bound_variant_code / bound_variant_label）----
    # 与 sku_master_service._attach_active_version_bindings 同语义：
    # 直接读 SkuMaster.metadata_json.bound_variant_code（人工 / 自动绑定时已落库），
    # 再去 ProductModelLineVariant.metadata_json.display_name 拼出"麻感冰丝(KB8-001)"。
    # 不做 spec→variant 反推，保持唯一来源。
    page_sku_codes: List[str] = []
    for (
        _line0v,
        _has0v,
        _has2v,
        _cleared0v,
        _bsid0v,
        _smid0v,
        _ur0v,
        _um0v,
        _cm0v,
        _ct0v,
        _bvid0v,
        _bmid0v,
        _bmc0v,
        _bmn0v,
        _bvl0v,
        _bps0v,
    ) in rows:
        sc = str(getattr(_line0v, "sku_code", "") or "").strip()
        if sc:
            page_sku_codes.append(sc)
    sku_to_variant_code: Dict[str, str] = {}
    if page_sku_codes:
        sm_rows = (
            db.query(models.SkuMaster.erp_sku_barcode, models.SkuMaster.metadata_json)
            .filter(models.SkuMaster.erp_sku_barcode.in_(list(set(page_sku_codes))))
            .all()
        )
        for bc, meta_json in sm_rows:
            mj = meta_json or {}
            code = str(mj.get("bound_variant_code") or "").strip().upper()
            if bc and code:
                sku_to_variant_code[str(bc)] = code
    variant_label_by_key: Dict[Tuple[str, str], str] = {}  # (version_id, variant_code) → label
    if sku_to_variant_code:
        # 收集本页用到的 (version_id, variant_code)
        version_ids_for_variant: List[str] = []
        for (
            _line0v,
            _has0v,
            _has2v,
            _cleared0v,
            _bsid0v,
            _smid0v,
            _ur0v,
            _um0v,
            _cm0v,
            _ct0v,
            _bvid0v,
            _bmid0v_x,
            _bmc0v,
            _bmn0v,
            _bvl0v,
            _bps0v,
        ) in rows:
            sc = str(getattr(_line0v, "sku_code", "") or "").strip()
            if not sc:
                continue
            if sc not in sku_to_variant_code:
                continue
            vid = str(_bvid0v or "").strip()
            if vid:
                version_ids_for_variant.append(vid)
        if version_ids_for_variant:
            line_variants = (
                db.query(models.ProductModelLineVariant)
                .filter(
                    models.ProductModelLineVariant.version_id.in_(list(set(version_ids_for_variant))),
                    models.ProductModelLineVariant.is_archived.is_(False),
                )
                .all()
            )
            for vr in line_variants:
                vmeta = vr.metadata_json or {}
                vc = str(vmeta.get("variant_code") or "").strip().upper()
                if not vc:
                    continue
                display_name = str(vmeta.get("display_name") or "").strip() or None
                material_name: Optional[str] = display_name
                if not material_name:
                    for it in vr.items or []:
                        n = str(getattr(it, "material_name", "") or "").strip()
                        if n:
                            material_name = n
                            break
                label = f"{material_name}({vc})" if material_name else vc
                variant_label_by_key[(str(vr.version_id), vc)] = label

    # Snapshot trace for "尺寸疑似异常" check (need latest snapshot measurement_mm for snapshot ids on page).
    snap_trace: Dict[str, Dict[str, Any]] = {}
    if bool(include_issue_hints):
        snap_ids_all: List[str] = []
        for (
            _line0,
            _has_bom_snapshot0,
            _has_costing_result0,
            _snapshot_cleared0,
            _bom_snapshot_id0,
            _snapshot_model_version_id0,
            _unresolved_reason0,
            _unresolved_message0,
            _cost_mode0,
            _cost_total0,
            _bound_model_version_id0,
            _bound_model_id0,
            _bound_model_code0,
            _bound_model_name0,
            _bound_version_label0,
            _bound_bundle_preset_selector0,
        ) in rows:
            sid = str(_bom_snapshot_id0 or "").strip()
            if sid:
                snap_ids_all.append(sid)
        if snap_ids_all:
            snaps = (
                db.query(models.BomSnapshot.id, models.BomSnapshot.trace_json)
                .filter(models.BomSnapshot.id.in_(list(set(snap_ids_all))))
                .all()
            )
            for sid, tjson in snaps:
                if sid:
                    snap_trace[str(sid)] = (tjson or {}) if isinstance(tjson, dict) else {}

    # Batch query "运营已声明绑定正确" 的 SKU 集合 + 「数据质量状态」
    # 行级 hint 用 resolved 集合跳过精筛
    # （SQL 端在 suspected_mismatch=True 时已经在 query 里排除，但「看全部」视图
    #  会让 resolved SKU 也出现，需要在行级精筛 suppress 红 Tag 才一致）。
    # 同一次查询顺便取出 data_quality_status（SPU 错配标识），避免再来一趟 DB。
    page_sku_codes_for_resolved: List[str] = []
    for (_l0,) in [(r[0],) for r in rows]:
        sc0 = str(getattr(_l0, "sku_code", "") or "").strip()
        if sc0:
            page_sku_codes_for_resolved.append(sc0)
    suspect_misbind_resolved_skus: set = set()
    sku_data_quality_status_map: Dict[str, str] = {}
    if page_sku_codes_for_resolved:
        try:
            for sm_code, sm_meta in (
                db.query(
                    models.SkuMaster.erp_sku_barcode,
                    models.SkuMaster.metadata_json,
                )
                .filter(
                    models.SkuMaster.erp_sku_barcode.in_(list(set(page_sku_codes_for_resolved))),
                    models.SkuMaster.is_archived.is_(False),
                )
                .all()
            ):
                if not sm_code:
                    continue
                code_s = str(sm_code)
                meta_d = sm_meta if isinstance(sm_meta, dict) else {}
                if meta_d.get("suspect_misbind_resolved") is True:
                    suspect_misbind_resolved_skus.add(code_s)
                dq = meta_d.get("data_quality_status")
                if isinstance(dq, str) and dq:
                    sku_data_quality_status_map[code_s] = dq
        except Exception:  # noqa: BLE001
            suspect_misbind_resolved_skus = set()
            sku_data_quality_status_map = {}

    items: List[Dict[str, Any]] = []
    for (
        line,
        has_bom_snapshot,
        has_costing_result,
        snapshot_cleared,
        bom_snapshot_id,
        snapshot_model_version_id,
        unresolved_reason,
        unresolved_message,
        cost_mode,
        cost_total,
        bound_model_version_id,
        bound_model_id,
        bound_model_code,
        bound_model_name,
        bound_version_label,
        bound_bundle_preset_selector,
    ) in rows:
        cleared = bool(snapshot_cleared)
        processed = bool((has_bom_snapshot or has_costing_result) and not cleared)
        processed_source = "bom_snapshot" if has_bom_snapshot else ("costing_result" if has_costing_result else None)
        mode = "2026" if has_bom_snapshot else (str(cost_mode) if cost_mode else None)
        meta = dict(getattr(line, "metadata_json", None) or {})
        raw_row = dict(getattr(line, "raw_row_json", None) or {})
        # Best-effort fallback for historical rows (before we started persisting these fields).
        # Sources covered:
        #   - 手工 Excel 导入：raw_row.规格编码 / 商家编码 / merchant_sku
        #   - 聚水潭 (jackyun) 同步：raw_row.detail.tradeGoodsno（detail 由 _ingest_jackyun 写入）
        #     兜底再去 raw_row.shipment.goodsDetail[0].tradeGoodsno（极少数嵌套场景）
        def _from_jackyun_detail(rr: Dict[str, Any]) -> Optional[str]:
            try:
                det = rr.get("detail") if isinstance(rr, dict) else None
                if isinstance(det, dict):
                    v = det.get("tradeGoodsno") or det.get("tradeGoodsNo")
                    if v not in (None, "", "null"):
                        return str(v).strip()
                ship = rr.get("shipment") if isinstance(rr, dict) else None
                if isinstance(ship, dict):
                    gd = ship.get("goodsDetail")
                    if isinstance(gd, list) and gd:
                        for g in gd:
                            if isinstance(g, dict):
                                v = g.get("tradeGoodsno") or g.get("tradeGoodsNo")
                                if v not in (None, "", "null"):
                                    return str(v).strip()
            except Exception:  # noqa: BLE001
                return None
            return None

        shop_spec_code = (
            meta.get("shop_spec_code")
            # raw_row_json keys are normalized by _norm_header (often stripping trailing "(网店)" notes)
            or raw_row.get("规格编码")
            or raw_row.get("规格编码(网店)")
            or raw_row.get("商家编码")
            or raw_row.get("shop_spec_code")
            or raw_row.get("merchant_sku")
            # 聚水潭：raw_row.detail.tradeGoodsno（核心入口）
            or _from_jackyun_detail(raw_row)
        )
        # 归一化前的 ERP 原始拼装值（仅当不同时返回；前端 Tooltip 用）
        shop_spec_code_raw = _extract_shop_spec_code_raw_from_line(line)
        platform_sku_id = (
            meta.get("platform_sku_id")
            or raw_row.get("平台规格Id")
            or raw_row.get("平台规格Id(网店)")
            or raw_row.get("platform_sku_id")
            or raw_row.get("platformSkuId")
        )
        bundle_template_code = meta.get("bundle_template_code")
        bundle_preset_selector = meta.get("bundle_preset_selector") or bound_bundle_preset_selector
        # fill missing cost_total from snapshot trace (legacy rows)
        if cost_total in (None, "") and bom_snapshot_id not in (None, ""):
            sid = str(bom_snapshot_id).strip()
            if sid and sid in snap_cost:
                cost_total = snap_cost[sid]

        # Soft guardrails are expensive (normalize/parse spec per row, inspect snapshot trace).
        # Only compute them when explicitly requested by UI.
        include_hints = bool(include_issue_hints)
        norm_spec = ""
        mismatch_warnings: List[str] = []
        suspected = False
        suspected_size_anomaly = False
        size_anomaly_detail: Optional[str] = None

        if include_hints:
            # 运营已声明该 SKU 绑定正确（suspect_misbind_resolved=True）→ 跳过精筛
            sku_code_for_resolve = str(getattr(line, "sku_code", "") or "").strip()
            if sku_code_for_resolve and sku_code_for_resolve in suspect_misbind_resolved_skus:
                mismatch_warnings = []
                suspected = False
            else:
                # Soft warning: "疑似绑错" (keyword mismatch between transaction spec and bound target label).
                # Use the SAME keyword groups as sku-master bind preview to keep behavior consistent.
                target_label = f"{str(bound_model_code or '').strip()} {str(bound_model_name or '').strip()}".strip()
                try:
                    norm_spec = spec_parser_service.normalize_tx_spec_text(getattr(line, "spec_text", None))
                except Exception:  # noqa: BLE001
                    norm_spec = getattr(line, "spec_text", None)
                norm_spec = str(norm_spec or "").strip()
                if norm_spec and target_label:
                    try:
                        # 行级精筛：优先吃运营在标准模型里维护的 recognition_keywords，
                        # 没命中就回退硬编码 5 组品类（向后兼容）。这里传 db + bound_model_id
                        # 启用 Tier 1（统一关键词体系）。
                        mismatch_warnings = sku_master_service._mismatch_warnings_by_keywords(  # noqa: SLF001
                            sample_text=norm_spec,
                            sku_spec_text=None,
                            product_name=None,
                            target_label=target_label,
                            db=db,
                            bound_model_id=str(bound_model_id) if bound_model_id else None,
                        )
                    except Exception:  # noqa: BLE001
                        mismatch_warnings = []
                suspected = bool(mismatch_warnings)

            # Soft warning: "尺寸疑似异常" (parsed spec area vs snapshot measurement area).
            area_m2: Optional[float] = None
            try:
                parsed2 = spec_parser_service.parse_spec(norm_spec or getattr(line, "spec_text", None) or "")
                area_m2_raw = parsed2.get("area_m2")
                area_m2 = float(area_m2_raw) if area_m2_raw not in (None, "") else None
            except Exception:  # noqa: BLE001
                area_m2 = None

            snap_area_m2: Optional[float] = None
            mm_w: Optional[float] = None
            mm_h: Optional[float] = None
            sid = str(bom_snapshot_id or "").strip()
            if sid and sid in snap_trace:
                mm = (snap_trace.get(sid) or {}).get("measurement_mm") or {}
                if isinstance(mm, dict):
                    try:
                        mm_w = float(str(mm.get("width_mm") or "").strip())
                        mm_h = float(str(mm.get("height_mm") or "").strip())
                    except Exception:  # noqa: BLE001
                        mm_w = None
                        mm_h = None
                if mm_w and mm_h and mm_w > 0 and mm_h > 0:
                    snap_area_m2 = (mm_w * mm_h) / 1_000_000.0

            if area_m2 and snap_area_m2 and area_m2 > 0 and snap_area_m2 > 0:
                ratio = snap_area_m2 / area_m2 if area_m2 else None
                # Heuristic: flag large mismatch (e.g. 0.36㎡ vs ~1.00㎡ => ratio≈2.78)
                if ratio and (ratio >= 1.8 or ratio <= 0.55):
                    suspected_size_anomaly = True
                    wh = f"{int(mm_w)}×{int(mm_h)}mm" if mm_w and mm_h else "-"
                    size_anomaly_detail = f"解析面积≈{area_m2:.2f}㎡；计价面积≈{snap_area_m2:.2f}㎡（{wh}）"
        items.append(
            {
                "id": str(getattr(line, "id", "")),
                "batch_id": str(getattr(line, "batch_id", "")),
                "row_index": getattr(line, "row_index", None),
                "shipment_no": getattr(line, "shipment_no", None),
                "order_no": getattr(line, "order_no", None),
                "product_link_id": getattr(line, "product_link_id", None),
                "completed_at": getattr(line, "completed_at", None),
                "channel": getattr(line, "channel", None),
                "sku_code": getattr(line, "sku_code", None),
                "tag": getattr(line, "tag", None),
                "shop_spec_code": (str(shop_spec_code).strip() if shop_spec_code not in (None, "") else None),
                "shop_spec_code_raw": shop_spec_code_raw,
                "platform_sku_id": (str(platform_sku_id).strip() if platform_sku_id not in (None, "") else None),
                "bundle_template_code": (str(bundle_template_code).strip() if bundle_template_code not in (None, "") else None),
                "bundle_preset_selector": (
                    str(bundle_preset_selector).strip().upper() if bundle_preset_selector not in (None, "") else None
                ),
                "spec_text": getattr(line, "spec_text", None),
                "spec_hash": getattr(line, "spec_hash", None),
                "qty": getattr(line, "qty", None),
                "revenue_amount": getattr(line, "revenue_amount", None),
                "cost_total": cost_total,
                "bound_model_version_id": (str(bound_model_version_id).strip() if bound_model_version_id not in (None, "") else None),
                "snapshot_model_version_id": (str(snapshot_model_version_id).strip() if snapshot_model_version_id not in (None, "") else None),
                "needs_rebuild_snapshot": bool(
                    has_bom_snapshot
                    and str(bound_model_version_id or "").strip() != str(snapshot_model_version_id or "").strip()
                ),
                "bound_model_code": (str(bound_model_code).strip() if bound_model_code not in (None, "") else None),
                "bound_model_name": (str(bound_model_name).strip() if bound_model_name not in (None, "") else None),
                # 变体展示（与 sku-master 列表统一来源：sku_master.metadata_json.bound_variant_code）
                "bound_variant_code": (
                    sku_to_variant_code.get(str(getattr(line, "sku_code", "") or "").strip())
                    if getattr(line, "sku_code", None)
                    else None
                ),
                "bound_variant_label": (
                    variant_label_by_key.get(
                        (
                            str(bound_model_version_id or "").strip(),
                            sku_to_variant_code.get(str(getattr(line, "sku_code", "") or "").strip(), ""),
                        )
                    )
                    if (
                        getattr(line, "sku_code", None)
                        and bound_model_version_id
                        and sku_to_variant_code.get(str(getattr(line, "sku_code", "") or "").strip())
                    )
                    else None
                ),
                "bound_version_label": (
                    str(bound_version_label).strip() if bound_version_label not in (None, "") else None
                ),
                "bom_snapshot_id": (str(bom_snapshot_id).strip() if bom_snapshot_id not in (None, "") else None),
                "status": "processed" if processed else "pending",
                "processed_source": processed_source,
                "mode": mode,
                "unresolved_reason": "SNAPSHOT_CLEARED" if cleared else unresolved_reason,
                "unresolved_message": (
                    "已强制清空快照：销售分析已忽略，等待重新绑定后重建快照"
                    if cleared
                    else unresolved_message
                ),
                "suspected_mismatch": suspected,
                "mismatch_warnings": mismatch_warnings,
                "suspected_size_anomaly": bool(suspected_size_anomaly),
                "size_anomaly_detail": size_anomaly_detail,
                # SPU 错配标识：来自 SkuMaster.metadata.data_quality_status，
                # 跟绑定/计费流程独立，仅用于 UI 灰色 Tag 提示运营。
                "sku_data_quality_status": (
                    sku_data_quality_status_map.get(str(line.sku_code))
                    if getattr(line, "sku_code", None)
                    else None
                ),
                # Jackyun v2 extensions (migration 0036). Plain getattr —
                # legacy rows may be NULL until backfill script runs.
                "erp_order_no": getattr(line, "erp_order_no", None),
                "platform_order_no": getattr(line, "platform_order_no", None),
                "sent_at": getattr(line, "sent_at", None),
                "paid_at": getattr(line, "paid_at", None),
                "ordered_at": getattr(line, "ordered_at", None),
                "check_started_at": getattr(line, "check_started_at", None),
                "order_status_name": getattr(line, "order_status_name", None),
                "trade_type": getattr(line, "trade_type", None),
                "trade_type_msg": getattr(line, "trade_type_msg", None),
                "customer_name": getattr(line, "customer_name", None),
                "logistic_no": getattr(line, "logistic_no", None),
                "logistic_name": getattr(line, "logistic_name", None),
                "logistic_type_name": getattr(line, "logistic_type_name", None),
                "logistic_code": getattr(line, "logistic_code", None),
                "warehouse_code": getattr(line, "warehouse_code", None),
                "warehouse_name": getattr(line, "warehouse_name", None),
                "wave_no": getattr(line, "wave_no", None),
                "picker": getattr(line, "picker", None),
                "packer": getattr(line, "packer", None),
                "checker": getattr(line, "checker", None),
                "seller_memo": getattr(line, "seller_memo", None),
                "buyer_memo": getattr(line, "buyer_memo", None),
                "unit_price": getattr(line, "unit_price", None),
                "unit_of_measure": getattr(line, "unit_of_measure", None),
                "category_name": getattr(line, "category_name", None),
                "goods_name": getattr(line, "goods_name", None),
                "goods_no": getattr(line, "goods_no", None),
                "is_gift": getattr(line, "is_gift", None),
                "actual_qty": getattr(line, "actual_qty", None),
            }
        )

    return {"total": int(total), "page": p, "page_size": ps, "items": items}


def compute_snapshot_for_shipment_line(
    db: Session,
    *,
    shipment_line_id: str,
    operator_id: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Compute (or recompute) a BOM snapshot for a given shipment line using current SKU binding.

    - overwrite=False: only fill missing (skip if already has bom_snapshot or costing_result)
    - overwrite=True : recompute if snapshot exists; otherwise generate a new snapshot
    """
    lid = (shipment_line_id or "").strip()
    if not lid:
        raise ValueError("shipment_line_id 不能为空")

    line = db.get(models.ShipmentLine, lid)
    if not line or getattr(line, "is_archived", False):
        raise ValueError("发货行不存在或已归档")

    # If user force-cleared snapshot for this line, treat it as "pending" even if historical snapshot exists.
    # This flag will be removed once we successfully create/recompute a snapshot.
    meta_line = dict(getattr(line, "metadata_json", None) or {})
    cleared_at = str(meta_line.get("snapshot_cleared_at") or "").strip()
    is_cleared = bool(cleared_at)

    # If not overwriting, skip processed rows (either snapshot or costing result).
    if not overwrite:
        has_bom = (
            db.query(models.BomSnapshot.id)
            .filter(models.BomSnapshot.shipment_line_id == line.id)
            .limit(1)
            .first()
            is not None
        )
        has_costing = (
            db.query(models.ShipmentCostingResult.id)
            .filter(models.ShipmentCostingResult.shipment_line_id == line.id)
            .limit(1)
            .first()
            is not None
        )
        if (has_bom or has_costing) and not is_cleared:
            return {
                "action": "skipped",
                "shipment_line_id": str(line.id),
                "bom_snapshot_id": None,
                "detail": "已存在快照/计价结果，按“只补齐缺失”跳过",
            }

    # latest snapshot id (if any)
    latest = (
        db.query(models.BomSnapshot.id)
        .filter(models.BomSnapshot.shipment_line_id == line.id)
        .order_by(models.BomSnapshot.created_at.desc())
        .first()
    )
    latest_id = str(latest[0]) if latest and latest[0] else None

    if overwrite and latest_id:
        snap = recompute_bom_snapshot(db, snapshot_id=latest_id, operator_id=operator_id)
        # clear snapshot_cleared flag on success
        try:
            meta2 = dict(getattr(line, "metadata_json", None) or {})
            for k in ("snapshot_cleared_at", "snapshot_cleared_by", "snapshot_cleared_reason"):
                if k in meta2:
                    meta2.pop(k, None)
            line.metadata_json = meta2
            db.add(line)
            db.commit()
        except Exception:
            db.rollback()
        # resolve unresolved exceptions for this line (best-effort)
        try:
            db.query(models.ShipmentExceptionQueue).filter(
                models.ShipmentExceptionQueue.shipment_line_id == line.id,
                models.ShipmentExceptionQueue.resolved_at.is_(None),
            ).update({"resolved_at": _utcnow()})
            db.commit()
        except Exception:
            db.rollback()
        return {"action": "recomputed", "shipment_line_id": str(line.id), "bom_snapshot_id": str(snap.id), "detail": None}

    # Otherwise: generate a new snapshot (2026 style, also persists deduction artifacts).
    batch_id = getattr(line, "batch_id", None)
    if not batch_id:
        raise ValueError("发货行缺 batch_id，无法生成快照")
    batch = db.get(models.ShipmentImportBatch, str(batch_id))
    if not batch or getattr(batch, "is_archived", False):
        raise ValueError("关联批次不存在或已归档")

    snap2 = _generate_bom_snapshot(db, batch=batch, line=line, persist_snapshot=True, mode="2026")
    if not snap2:
        # Exception was queued; surface the latest reason/message for UI (more actionable than a generic error).
        try:
            last_exc = (
                db.query(models.ShipmentExceptionQueue)
                .filter(models.ShipmentExceptionQueue.shipment_line_id == line.id)
                .order_by(models.ShipmentExceptionQueue.created_at.desc())
                .first()
            )
            if last_exc and getattr(last_exc, "reason", None):
                msg = str(getattr(last_exc, "message", "") or "").strip()
                detail = f"{str(last_exc.reason)}{f'：{msg}' if msg else ''}"
            else:
                detail = "生成快照失败（已写入异常队列，请到异常处理查看原因）"
        except Exception:
            detail = "生成快照失败（已写入异常队列，请到异常处理查看原因）"
        return {
            "action": "failed",
            "shipment_line_id": str(line.id),
            "bom_snapshot_id": None,
            "detail": detail,
        }

    # resolve unresolved exceptions for this line (best-effort)
    try:
        # clear snapshot_cleared flag on success
        meta2 = dict(getattr(line, "metadata_json", None) or {})
        for k in ("snapshot_cleared_at", "snapshot_cleared_by", "snapshot_cleared_reason"):
            if k in meta2:
                meta2.pop(k, None)
        line.metadata_json = meta2
        db.add(line)
        db.query(models.ShipmentExceptionQueue).filter(
            models.ShipmentExceptionQueue.shipment_line_id == line.id,
            models.ShipmentExceptionQueue.resolved_at.is_(None),
        ).update({"resolved_at": _utcnow()})
        db.commit()
    except Exception:
        db.rollback()

    return {"action": "created", "shipment_line_id": str(line.id), "bom_snapshot_id": str(snap2.id), "detail": None}


# ----------------------------------------------------------------------------
# Snapshot retry sweep — fixes the "⏳ 等出快照(系统处理中)" tooltip promise.
#
# Background:
#   The main shipment_import_worker only loops over batches in status
#   ('queued', 'processing'). Once a batch goes to 'success', the worker
#   never revisits it. But the UI shows ⏳ "等出快照" for any line whose
#   SKU has a binding but no snapshot — that state is reachable when:
#
#     1. Batch finishes with the SKU unbound → exception queued + no snapshot.
#     2. Operator (or auto-resolve) later binds the SKU.
#     3. The line still has no snapshot until SOMETHING re-runs the
#        finalize step. With only the queue-driven worker, that never
#        happens automatically — leaving the ⏳ tag as an empty promise.
#
#   This sweep makes the promise true: every N seconds (driven by
#   shipment_import_worker._loop), find pending lines whose SKU is bound,
#   and call compute_snapshot_for_shipment_line(overwrite=False) on each.
#
#   compute_snapshot_for_shipment_line is idempotent for lines that already
#   got a snapshot (returns action='skipped'); for the bound-no-snapshot
#   ones it goes through _generate_bom_snapshot and produces the snapshot
#   exactly the same way the original batch path would.
# ----------------------------------------------------------------------------


def sweep_bound_lines_missing_snapshot(
    db: Session,
    *,
    lookback_days: int = 14,
    limit: int = 200,
) -> Dict[str, Any]:
    """Find pending ShipmentLine rows whose SKU has an active binding
    and produce snapshots for them. Best-effort: per-row exceptions are
    swallowed and recorded as failed counts so a single bad SKU doesn't
    halt the sweep.

    Performance budget:
      - lookback 14d × LIMIT 200 keeps the sweep ~O(seconds) at
        production scale (~13k pending lines, ~78k SkuMaster).
      - Window kept at 14d (was widened to 60d briefly on 2026-05-07
        but reverted same day per user feedback): bind_sku_to_version
        now eagerly triggers per-SKU snapshot for ALL ages, so this
        background sweep is purely a defensive backstop for hook
        failures and bulk-bind paths that bypassed the hook. For
        operator-initiated wider catch-up (e.g. month-end audit), use
        the manual button via POST /shipments/lines/regenerate-snapshots
        which calls this same function with lookback_days=90 by default.
      - Sweep runs out of band of the main batch worker — its idleness
        cost when there's nothing to do is one indexed SELECT.

    Returns
    -------
    {
      "scanned": int,
      "snapshots_created": int,
      "snapshots_recomputed": int,
      "skipped_already_done": int,    # snapshot existed (rare; race condition)
      "failed": int,
      "duration_ms": int,
      "lookback_days": int,
      "limit": int,
    }
    """
    bulk_t0 = _utcnow()
    cutoff_at = bulk_t0 - timedelta(days=max(int(lookback_days or 14), 1))

    # Same predicate as list_shipment_lines pending path: lines with no
    # BomSnapshot AND no ShipmentCostingResult (or snapshot was cleared).
    has_bom = (
        db.query(models.BomSnapshot.id)
        .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
        .exists()
    )
    has_costing = (
        db.query(models.ShipmentCostingResult.id)
        .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
        .exists()
    )
    cleared_pred = func.nullif(
        func.trim(func.coalesce(models.ShipmentLine.metadata_json["snapshot_cleared_at"].as_string(), "")),
        "",
    ).isnot(None)
    pending_pred = ~and_(or_(has_bom, has_costing), ~cleared_pred)

    # Critical filter: line.sku_code must have an active binding in
    # SkuModelVersionMapping. Joining keeps this O(1) per line instead of
    # the per-row N+1 that bit us in Issue 26 / 31.
    binding_exists = (
        db.query(models.SkuModelVersionMapping.id)
        .filter(
            models.SkuModelVersionMapping.sku_code == models.ShipmentLine.sku_code,
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
        .exists()
    )

    rows = (
        db.query(models.ShipmentLine)
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            models.ShipmentLine.is_active.is_(True),
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= cutoff_at,
            models.ShipmentLine.sku_code.isnot(None),
            pending_pred,
            binding_exists,
        )
        .order_by(models.ShipmentLine.completed_at.asc())  # oldest first → fairness
        .limit(max(int(limit or 200), 1))
        .all()
    )

    snapshots_created = 0
    snapshots_recomputed = 0
    skipped_already = 0
    failed = 0
    failure_samples: List[str] = []

    for line in rows:
        line_id = str(line.id)
        try:
            res = compute_snapshot_for_shipment_line(
                db,
                shipment_line_id=line_id,
                operator_id="snapshot_retry_worker",
                overwrite=False,
            )
            action = (res or {}).get("action")
            if action == "created":
                snapshots_created += 1
            elif action == "recomputed":
                snapshots_recomputed += 1
            elif action == "skipped":
                skipped_already += 1
            else:
                # 'failed' or unknown — don't blow up; the line will hit
                # the next sweep again (or the operator will see the
                # exception in the queue).
                failed += 1
                detail = (res or {}).get("detail") or action or "unknown"
                if len(failure_samples) < 5:
                    failure_samples.append(f"{line_id[:8]}:{str(detail)[:80]}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            if len(failure_samples) < 5:
                failure_samples.append(f"{line_id[:8]}:{str(exc)[:80]}")

    duration_ms = int((_utcnow() - bulk_t0).total_seconds() * 1000)
    return {
        "scanned": len(rows),
        "snapshots_created": snapshots_created,
        "snapshots_recomputed": snapshots_recomputed,
        "skipped_already_done": skipped_already,
        "failed": failed,
        "duration_ms": duration_ms,
        "lookback_days": int(lookback_days),
        "limit": int(limit),
        "failure_samples": failure_samples,
    }


def clear_shipment_line_snapshots(
    db: Session,
    *,
    shipment_line_ids: List[str],
    operator_id: Optional[str],
    reason: Optional[str],
) -> Dict[str, Any]:
    """
    Soft-clear snapshots for shipment lines:
    - Do NOT delete historical bom_snapshot rows (audit trail).
    - Mark shipment_line.metadata.snapshot_cleared_* so analytics/ledger treats it as "pending" and ignores cost.
    - User can later rebuild snapshot after re-binding.
    """
    ids = [str(x).strip() for x in (shipment_line_ids or []) if str(x).strip()]
    total_selected = len(ids)
    if total_selected <= 0:
        return {
            "total_selected": 0,
            "cleared_count": 0,
            "skipped_not_found": 0,
            "skipped_already_cleared": 0,
            "skipped_missing_barcode": 0,
            "errors": [],
        }
    op = (operator_id or "").strip() or None
    why = (reason or "").strip() or "force_clear_snapshot"
    now_iso = _utcnow().isoformat()

    rows = (
        db.query(models.ShipmentLine)
        .filter(models.ShipmentLine.id.in_(list(set(ids))), models.ShipmentLine.is_archived.is_(False))
        .all()
    )
    by_id = {str(r.id): r for r in rows}

    cleared_count = 0
    skipped_not_found = 0
    skipped_already_cleared = 0
    skipped_missing_barcode = 0
    errors: List[Dict[str, Any]] = []

    for lid in ids:
        line = by_id.get(lid)
        if not line:
            skipped_not_found += 1
            continue
        sku = str(getattr(line, "sku_code", "") or "").strip()
        if not sku:
            skipped_missing_barcode += 1
            continue
        meta = dict(getattr(line, "metadata_json", None) or {})
        if str(meta.get("snapshot_cleared_at") or "").strip():
            skipped_already_cleared += 1
            continue
        meta.update(
            {
                "snapshot_cleared_at": now_iso,
                "snapshot_cleared_by": op,
                "snapshot_cleared_reason": why,
            }
        )
        line.metadata_json = meta
        db.add(line)
        cleared_count += 1
    db.commit()
    return {
        "total_selected": total_selected,
        "cleared_count": cleared_count,
        "skipped_not_found": skipped_not_found,
        "skipped_already_cleared": skipped_already_cleared,
        "skipped_missing_barcode": skipped_missing_barcode,
        "errors": errors,
    }


def recompute_bom_snapshot(db: Session, *, snapshot_id: str, operator_id: Optional[str]) -> models.BomSnapshot:
    """
    Recompute and backfill an existing BOM snapshot (for historical records).
    This will overwrite:
    - final_lines_json
    - trace_json
    - model_version_id/spec_hash/qty (based on current shipment_line)
    - generated_at
    """
    snap = db.get(models.BomSnapshot, snapshot_id)
    if not snap:
        raise ValueError("BOM快照不存在")

    line = db.get(models.ShipmentLine, snap.shipment_line_id)
    if not line or line.is_archived:
        raise ValueError("关联的发货行不存在或已归档")

    sku = (line.sku_code or "").strip()
    if not sku:
        raise ValueError("发货行 sku_code 为空，无法回填")

    spec_text = (line.spec_text or "").strip()
    if not spec_text:
        raise ValueError("发货行 spec_text 为空，无法回填")

    binding = product_model_service.get_active_sku_binding(db, sku)
    if not binding:
        raise ValueError("SKU 未绑定已发布标准版本，无法回填")

    spec_snap = _upsert_spec_snapshot(db, spec_text=spec_text)
    qty = line.qty if line.qty is not None else Decimal("1")

    bom = bom_generation_service.generate_bom(
        db,
        spec_text=spec_text,
        model_version_id=None,
        sku_code=sku,
        quantity=Decimal(str(qty)),
    )

    trace = dict(bom.get("trace") or {})
    trace.update(
        {
            "bound_version_id": binding.model_version_id,
            "spec_hash": spec_snap.spec_hash,
            "shipment_line_id": line.id,
            "batch_id": line.batch_id,
            "recomputed_at": _utcnow().isoformat(),
            "recomputed_by": operator_id or "",
        }
    )

    snap.shipment_no = line.shipment_no
    snap.sku_code = sku
    snap.model_version_id = trace.get("model_version_id") or binding.model_version_id
    snap.spec_hash = spec_snap.spec_hash
    snap.qty = Decimal(str(qty))
    snap.final_lines_json = _json_safe(list(bom.get("final_material_lines") or []))
    snap.trace_json = _json_safe(trace)
    snap.generated_at = _utcnow()
    # Attach shipment line fields for readability (Pydantic orm_mode will read these dynamic attributes)
    snap.row_index = getattr(line, "row_index", None)
    snap.completed_at = getattr(line, "completed_at", None)
    snap.channel = getattr(line, "channel", None)
    snap.spec_text = getattr(line, "spec_text", None)
    snap.revenue_amount = getattr(line, "revenue_amount", None)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def retry_exceptions_by_batch(
    db: Session,
    *,
    batch_id: str,
    only_unresolved: bool = True,
    limit: Optional[int] = None,
    operator_id: str,
    reason: str,
) -> Dict[str, Any]:
    """
    MVP: Retry unresolved shipment exceptions for a given batch_id by rerunning:
    binding -> spec parse -> bom generation -> create NEW bom_snapshot (no overwrite).
    On success: mark the existing exception resolved (resolved_at + payload trace).
    On failure: keep unresolved and record retry trace in payload/message.
    """
    bid = (batch_id or "").strip()
    if not bid:
        raise ValueError("batch_id 不能为空")
    if only_unresolved is not True:
        raise ValueError("MVP: only_unresolved 必须为 true")
    op = (operator_id or "").strip()
    if not op:
        raise ValueError("operator_id 不能为空")
    why = (reason or "").strip()
    if not why:
        raise ValueError("reason 不能为空")

    batch = db.get(models.ShipmentImportBatch, bid)
    if not batch:
        raise ValueError("Batch not found")

    q = db.query(models.ShipmentExceptionQueue).filter(models.ShipmentExceptionQueue.batch_id == bid)
    if only_unresolved:
        q = q.filter(models.ShipmentExceptionQueue.resolved_at.is_(None))
    q = q.order_by(models.ShipmentExceptionQueue.created_at.asc())
    if limit is not None:
        lim = max(min(int(limit or 0), 1000), 1)
        q = q.limit(lim)
    excs = q.all()

    now = _utcnow()

    def _bump_retry_payload(payload: Dict[str, Any], *, error: Optional[str]) -> Dict[str, Any]:
        p = dict(payload or {})
        retry = dict(p.get("retry") or {})
        retry["count"] = int(retry.get("count") or 0) + 1
        retry["last_at"] = now.isoformat()
        retry["last_by"] = op
        retry["last_reason"] = why
        if error:
            retry["last_error"] = str(error)
        p["retry"] = retry
        return _json_safe(p)

    def _mark_resolved_payload(payload: Dict[str, Any], *, bom_snapshot_id: str) -> Dict[str, Any]:
        p = dict(payload or {})
        p["resolution"] = {
            "action": "retry",
            "resolved_at": now.isoformat(),
            "resolved_by": op,
            "retry_reason": why,
            "resolved_bom_snapshot_id": bom_snapshot_id,
        }
        return _json_safe(p)

    items: List[Dict[str, Any]] = []
    processed = 0
    resolved = 0
    unresolved = 0

    for exc in excs:
        processed += 1
        line_id = getattr(exc, "shipment_line_id", None)
        line = db.get(models.ShipmentLine, line_id) if line_id else None
        if not line or getattr(line, "is_archived", False):
            msg = "关联的发货行不存在或已归档"
            exc.message = msg
            exc.payload_json = _bump_retry_payload(getattr(exc, "payload_json", {}) or {}, error=msg)
            db.add(exc)
            unresolved += 1
            items.append(
                {
                    "exception_id": exc.id,
                    "shipment_line_id": line_id,
                    "status": "unresolved",
                    "new_bom_snapshot_id": None,
                    "error": msg,
                }
            )
            continue

        sku = (getattr(line, "sku_code", None) or "").strip()
        if not sku:
            msg = "发货行 sku_code 为空"
            exc.message = msg
            exc.payload_json = _bump_retry_payload(getattr(exc, "payload_json", {}) or {}, error=msg)
            db.add(exc)
            unresolved += 1
            items.append(
                {
                    "exception_id": exc.id,
                    "shipment_line_id": line.id,
                    "status": "unresolved",
                    "new_bom_snapshot_id": None,
                    "error": msg,
                }
            )
            continue

        spec_text = (getattr(line, "spec_text", None) or "").strip()
        if not spec_text:
            msg = "发货行 spec_text 为空"
            exc.message = msg
            exc.payload_json = _bump_retry_payload(getattr(exc, "payload_json", {}) or {}, error=msg)
            db.add(exc)
            unresolved += 1
            items.append(
                {
                    "exception_id": exc.id,
                    "shipment_line_id": line.id,
                    "status": "unresolved",
                    "new_bom_snapshot_id": None,
                    "error": msg,
                }
            )
            continue

        binding = product_model_service.get_active_sku_binding(db, sku)
        if not binding:
            msg = "SKU 未绑定已发布标准版本"
            exc.message = msg
            payload0 = dict(getattr(exc, "payload_json", {}) or {})
            payload0.update({"sku_code": sku})
            exc.payload_json = _bump_retry_payload(payload0, error=msg)
            db.add(exc)
            unresolved += 1
            items.append(
                {
                    "exception_id": exc.id,
                    "shipment_line_id": line.id,
                    "status": "unresolved",
                    "new_bom_snapshot_id": None,
                    "error": msg,
                }
            )
            continue

        try:
            spec_snap = _upsert_spec_snapshot(db, spec_text=spec_text)
            qty = line.qty if line.qty is not None else Decimal("1")
            bom = bom_generation_service.generate_bom(
                db,
                spec_text=spec_text,
                model_version_id=None,
                sku_code=sku,
                quantity=Decimal(str(qty)),
            )
            trace = dict(bom.get("trace") or {})
            trace.update(
                {
                    "bound_version_id": binding.model_version_id,
                    "spec_hash": spec_snap.spec_hash,
                    "shipment_line_id": line.id,
                    "batch_id": bid,
                    "retry_exception_id": exc.id,
                    "retried_at": now.isoformat(),
                    "retried_by": op,
                    "retry_reason": why,
                }
            )
            snap = models.BomSnapshot(
                batch_id=bid,
                shipment_line_id=line.id,
                shipment_no=line.shipment_no,
                sku_code=sku,
                model_version_id=trace.get("model_version_id") or binding.model_version_id,
                spec_hash=spec_snap.spec_hash,
                qty=Decimal(str(qty)),
                final_lines_json=_json_safe(list(bom.get("final_material_lines") or [])),
                trace_json=_json_safe(trace),
                generated_at=now,
            )
            db.add(snap)
            db.flush()

            exc.resolved_at = now
            exc.message = "resolved_by_retry"
            exc.payload_json = _mark_resolved_payload(getattr(exc, "payload_json", {}) or {}, bom_snapshot_id=snap.id)
            db.add(exc)
            resolved += 1
            items.append(
                {
                    "exception_id": exc.id,
                    "shipment_line_id": line.id,
                    "status": "resolved",
                    "new_bom_snapshot_id": snap.id,
                    "error": None,
                }
            )
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            exc.message = msg
            payload0 = dict(getattr(exc, "payload_json", {}) or {})
            payload0.update({"sku_code": sku, "spec_hash": getattr(line, "spec_hash", None)})
            exc.payload_json = _bump_retry_payload(payload0, error=msg)
            db.add(exc)
            unresolved += 1
            items.append(
                {
                    "exception_id": exc.id,
                    "shipment_line_id": line.id,
                    "status": "unresolved",
                    "new_bom_snapshot_id": None,
                    "error": msg,
                }
            )

    db.commit()
    return {
        "batch_id": bid,
        "only_unresolved": only_unresolved,
        "limit": limit,
        "processed": processed,
        "resolved": resolved,
        "unresolved": unresolved,
        "items": items,
    }


# ============================================================================
# Auto-resolve pending shipment lines (Phase 1.5 of "业务管理 / 发货管理")
# ----------------------------------------------------------------------------
# Background:
#   The legacy "/costing/sku-master > 自动识别" tab can batch-bind unbound
#   SkuMaster rows to published standard models via keyword recognition
#   (see sku_master_service.auto_bind_preview/auto_bind_execute).
#
#   The new "/costing/biz/shipments > 🔴 待处理" tab only had MANUAL row-level
#   actions, missing this critical automation. Operators reported that the
#   new page felt like a regression because it forced one-by-one decisions
#   for SKUs that the system already knew how to bind.
#
#   These two functions bridge the gap: they run the same recognition
#   algorithm, but scoped to SKUs that actually appear in recent pending
#   shipment lines (instead of the full ~78k unbound SkuMaster pool, of
#   which the long tail hasn't shipped in months). After binding, they
#   immediately generate BomSnapshot for the affected lines and resolve
#   their SKU_NOT_BOUND exceptions, so operators see lines disappear from
#   the pending queue in seconds.
# ============================================================================


def _list_pending_shipment_line_sku_codes(
    db: Session,
    *,
    cutoff_at: datetime,
    sku_codes: Optional[List[str]] = None,
) -> List[Tuple[str, List[models.ShipmentLine]]]:
    """
    Returns [(sku_code, [lines...])] for "pending" shipment lines that landed
    in our DB within ``cutoff_at`` (``ShipmentLine.created_at >= cutoff_at``)
    and whose sku_code has NO active SkuModelVersionMapping.

    "Pending" definition (mirrors ``list_shipment_lines``):
      A line is pending when it has neither a ``BomSnapshot`` nor a
      ``ShipmentCostingResult``, or its snapshot was soft-invalidated via
      ``metadata_json.snapshot_cleared_at``. ``ShipmentLine.status`` is a
      DERIVED column at query time, not a stored field, so we replicate the
      same predicate here.

    Why bind status check here (instead of just relying on the snapshot
    absence):
      - A line may be "snapshot-less" because the SKU just got bound by a
        concurrent operator and the worker hasn't picked it up yet. In that
        case we should NOT try to bind again. Always verify against
        ``get_active_sku_binding`` before declaring an SKU "unbound".
    """
    has_bom = (
        db.query(models.BomSnapshot.id)
        .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
        .exists()
    )
    has_costing = (
        db.query(models.ShipmentCostingResult.id)
        .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
        .exists()
    )
    cleared_pred = func.nullif(
        func.trim(func.coalesce(models.ShipmentLine.metadata_json["snapshot_cleared_at"].as_string(), "")),
        "",
    ).isnot(None)
    pending_pred = ~and_(or_(has_bom, has_costing), ~cleared_pred)

    # Time window anchor: ``created_at`` (the moment the row landed in our DB),
    # NOT ``completed_at`` (the moment the customer marked it as delivered).
    #
    # Why this matters - bug observed 2026-05-07:
    #   Original code required ``completed_at IS NOT NULL`` AND
    #   ``completed_at >= cutoff_at``. That silently dropped TWO common
    #   business cases from the auto-bind candidate pool:
    #     1. Fresh Jackyun sync rows where the upstream ``finishTime`` /
    #        ``sendTime`` were not yet populated (so completed_at was NULL,
    #        even though the row landed in our DB minutes ago and is the
    #        most urgent thing to process).
    #     2. Excel-imported old rows where completed_at sits outside the
    #        30-day window (e.g. dispatched in March, only loaded into the
    #        new system in May) - operators still want them auto-bound.
    #   Effect: 8 of 8 obviously-recognizable SKUs (key model: 皮革桌垫,
    #   丝圈地垫) were missed by the "⚡ 自动绑定" banner.
    q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.is_archived.is_(False),
        models.ShipmentLine.is_active.is_(True),
        models.ShipmentLine.created_at >= cutoff_at,
        pending_pred,
    )
    norm_codes: Optional[List[str]] = None
    if sku_codes is not None:
        norm_codes = sorted({(c or "").strip() for c in sku_codes if (c or "").strip()})
        if not norm_codes:
            return []
        q = q.filter(models.ShipmentLine.sku_code.in_(norm_codes))
    lines = (
        q.order_by(models.ShipmentLine.created_at.desc())
        .limit(20000)
        .all()
    )

    by_sku: Dict[str, List[models.ShipmentLine]] = {}
    for line in lines:
        sku = (line.sku_code or "").strip()
        if not sku:
            continue
        by_sku.setdefault(sku, []).append(line)

    if not by_sku:
        return []

    # PERF: previously this loop called product_model_service.get_active_sku_binding(db, sku)
    # once per SKU. With ~5,800 unbound SKUs that meant ~5,800 sequential round-trips
    # → ~90s API latency (front-end "正在分析..." appeared to hang). Replace with one
    # IN(...) query, chunked at 1,000 (PG/MySQL safe upper bound), to drop to <1s.
    sku_keys: List[str] = list(by_sku.keys())
    bound_skus: set[str] = set()
    CHUNK = 1000
    for i in range(0, len(sku_keys), CHUNK):
        chunk = sku_keys[i : i + CHUNK]
        rows = (
            db.query(models.SkuModelVersionMapping.sku_code)
            .filter(
                models.SkuModelVersionMapping.sku_code.in_(chunk),
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
            .all()
        )
        for row in rows:
            code = (row[0] or "").strip()
            if code:
                bound_skus.add(code)

    out: List[Tuple[str, List[models.ShipmentLine]]] = []
    for sku, lst in by_sku.items():
        if sku in bound_skus:
            continue
        out.append((sku, lst))
    return out


def auto_resolve_pending_shipment_lines_preview(
    db: Session,
    *,
    days: int = 30,
    limit: int = 500,
    sku_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Identify pending shipment lines whose SKU can be auto-recognized to a
    published standard model (no writes).

    Algorithm:
      1. Find pending shipment lines created within the last ``days`` days.
      2. Group by sku_code, keeping only sku_codes with NO active binding.
      3. Run the same recognition engine as ``sku_master_service.auto_bind_preview``,
         scoped to those sku_codes (so we don't waste CPU on the long-tail
         SkuMaster pool).
      4. Return one candidate per sku_code (the first matching line is
         attached as a representative for the UI), plus aggregate stats.

    Returns:
      {
        "scanned_days": int,
        "total_pending_lines": int,            # raw pending lines scanned
        "unique_unbound_skus": int,            # distinct unbound sku_code
        "candidates_count": int,               # SKUs the system can recognize
        "items": [
          {
            "shipment_line_id": str,           # representative line id
            "shipment_line_count_for_sku": int,# how many pending lines share this sku
            "sku_code": str,
            "channel": str | None,
            "spec_text": str | None,
            "model_id": str,
            "model_code": str,
            "model_name": str,
            "version_id": str,
            "version_label": str | None,
            "match_method": "model_code_hint" | "model_keyword",
            "matched_keyword": str | None,
          },
          ...
        ]
      }
    """
    days = max(min(int(days or 30), 365), 1)
    limit = max(min(int(limit or 500), 5000), 1)
    cutoff_at = _utcnow().replace(tzinfo=None) - timedelta(days=days)

    sku_to_lines = _list_pending_shipment_line_sku_codes(
        db, cutoff_at=cutoff_at, sku_codes=sku_codes,
    )
    total_pending_lines = sum(len(lst) for _, lst in sku_to_lines)
    unbound_sku_codes = [sku for sku, _ in sku_to_lines]
    if not unbound_sku_codes:
        return {
            "scanned_days": days,
            "total_pending_lines": total_pending_lines,
            "unique_unbound_skus": 0,
            "candidates_count": 0,
            "items": [],
        }

    # Defensive catch-up: the recognition engine scans SkuMaster, not
    # ShipmentLine directly. Jackyun mapper + finalize pipeline both call
    # ensure_from_shipment, but if a new ingestion path creates shipment_lines
    # without that side-effect (or the worker is lagging), auto-resolve would
    # otherwise miss a perfectly recognizable SKU. Create/refresh the minimal
    # SkuMaster rows from representative pending lines before matching.
    for sku, lines in sku_to_lines:
        if not sku or not lines:
            continue
        rep = lines[0]
        try:
            sku_master_service.ensure_from_shipment(
                db,
                erp_sku_barcode=sku,
                spec_text=rep.spec_text,
                channel=rep.channel,
                metadata={
                    "source": "shipment_auto_resolve_catchup",
                    "shipment_line_id": rep.id,
                    "shipment_no": rep.shipment_no,
                    "batch_id": rep.batch_id,
                    "source_system": getattr(rep, "source_system", None),
                    "source_record_id": getattr(rep, "source_record_id", None),
                    "source_line_id": getattr(rep, "source_line_id", None),
                },
            )
        except Exception:
            # Best-effort. If ensure fails, auto_bind_preview simply won't
            # return that SKU and the operator can still handle it manually.
            try:
                db.rollback()
            except Exception:
                pass
            continue

    # Reuse the recognition engine. ``restrict_to_sku_codes`` keeps it cheap.
    sku_preview = sku_master_service.auto_bind_preview(
        db,
        limit=limit,
        scan_limit=max(len(unbound_sku_codes), 1000),
        restrict_to_sku_codes=unbound_sku_codes,
    )
    sku_items: List[Dict[str, Any]] = list(sku_preview.get("items") or [])
    sku_match_map: Dict[str, Dict[str, Any]] = {
        str(it.get("erp_sku_barcode") or ""): it for it in sku_items
    }

    items: List[Dict[str, Any]] = []
    for sku, lines in sku_to_lines:
        match = sku_match_map.get(sku)
        if not match:
            continue
        rep = lines[0]
        items.append({
            "shipment_line_id": rep.id,
            "shipment_line_count_for_sku": len(lines),
            "sku_code": sku,
            "channel": rep.channel,
            "spec_text": rep.spec_text,
            "model_id": match.get("model_id"),
            "model_code": match.get("model_code"),
            "model_name": match.get("model_name"),
            "version_id": match.get("published_version_id"),
            "version_label": match.get("version_label"),
            "match_method": match.get("match_method"),
            "matched_keyword": match.get("matched_keyword"),
        })
        if len(items) >= limit:
            break

    return {
        "scanned_days": days,
        "total_pending_lines": total_pending_lines,
        "unique_unbound_skus": len(unbound_sku_codes),
        "candidates_count": len(items),
        "items": items,
    }


def auto_resolve_pending_shipment_lines_execute(
    db: Session,
    *,
    days: int = 30,
    limit: int = 500,
    requested_by: Optional[str] = None,
    sku_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute auto-resolution for pending shipment lines:
      1. Run preview to get candidates (sku -> recommended model_version).
      2. For each unique sku_code: bind to the recommended version
         (skipping if already bound by a concurrent operator).
      3. For each pending shipment line whose sku just got bound:
         a. Generate BomSnapshot via ``_generate_bom_snapshot``.
         b. Mark related ``ShipmentExceptionQueue`` rows with
            reason='SKU_NOT_BOUND' as resolved (resolution.action='auto_resolve').
         c. Flip ``ShipmentLine.status`` to 'processed'.
      4. Commit per-line so partial progress is durable on errors.

    Args:
        days, limit, sku_codes: forwarded to preview.
        requested_by: optional operator id stamped onto bindings + resolutions
            for audit.

    Returns:
      {
        "scanned_days": int,
        "preview": <preview response dict, but BEFORE execution>,
        "bound_skus_count": int,         # SKUs newly bound by this run
        "skipped_already_bound": int,    # SKUs that became bound in a race
        "snapshots_created": int,
        "lines_resolved": int,
        "exceptions_resolved": int,
        "bind_errors": [{"sku_code": ..., "error": ...}],
        "snapshot_errors": [{"shipment_line_id": ..., "sku_code": ..., "error": ...}],
        "items": [<per-line outcome>],
      }
    """
    preview = auto_resolve_pending_shipment_lines_preview(
        db, days=days, limit=limit, sku_codes=sku_codes,
    )
    items_in: List[Dict[str, Any]] = list(preview.get("items") or [])
    if not items_in:
        return {
            "scanned_days": preview.get("scanned_days"),
            "preview": preview,
            "bound_skus_count": 0,
            "skipped_already_bound": 0,
            "snapshots_created": 0,
            "lines_resolved": 0,
            "exceptions_resolved": 0,
            "bind_errors": [],
            "snapshot_errors": [],
            "items": [],
        }

    op = (requested_by or "").strip() or None
    bind_errors: List[Dict[str, Any]] = []
    snapshot_errors: List[Dict[str, Any]] = []
    bound_skus: List[str] = []
    skipped_already_bound = 0
    snapshots_created = 0
    lines_resolved = 0
    exceptions_resolved = 0
    out_items: List[Dict[str, Any]] = []

    # Step 1+2: bind sku -> version (one bind per unique sku)
    by_sku: Dict[str, Dict[str, Any]] = {}
    for it in items_in:
        sku = str(it.get("sku_code") or "").strip()
        if sku and sku not in by_sku:
            by_sku[sku] = it

    # Issue 0.0i: snapshot pre-bind pending line ids per SKU. The bind hook
    # will eagerly create snapshots for these, but we still need to walk
    # them after bind to (a) attribute the snapshot to this execute() call,
    # and (b) resolve any open SKU_NOT_BOUND exception rows.
    # Also record which lines had OPEN exceptions before the bind ran;
    # the hook's compute_snapshot_for_shipment_line will resolve them
    # internally, and we want to attribute that resolution to THIS
    # execute() call (so the UI accurately reports "解决异常 N 条").
    candidate_sku_codes = list(by_sku.keys())
    pre_bind_pending_line_ids_by_sku: Dict[str, List[str]] = {}
    pre_bind_open_exception_line_ids: set[str] = set()
    if candidate_sku_codes:
        cutoff_pre = _utcnow().replace(tzinfo=None) - timedelta(days=max(min(int(days or 30), 365), 1))
        has_bom_pre = (
            db.query(models.BomSnapshot.id)
            .filter(models.BomSnapshot.shipment_line_id == models.ShipmentLine.id)
            .exists()
        )
        has_costing_pre = (
            db.query(models.ShipmentCostingResult.id)
            .filter(models.ShipmentCostingResult.shipment_line_id == models.ShipmentLine.id)
            .exists()
        )
        cleared_pre = func.nullif(
            func.trim(func.coalesce(models.ShipmentLine.metadata_json["snapshot_cleared_at"].as_string(), "")),
            "",
        ).isnot(None)
        pending_pre = ~and_(or_(has_bom_pre, has_costing_pre), ~cleared_pre)
        pre_rows = (
            db.query(models.ShipmentLine.id, models.ShipmentLine.sku_code)
            .filter(
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                models.ShipmentLine.created_at >= cutoff_pre,
                models.ShipmentLine.sku_code.in_(candidate_sku_codes),
                pending_pre,
            )
            .all()
        )
        for lid, sk in pre_rows:
            pre_bind_pending_line_ids_by_sku.setdefault(str(sk), []).append(str(lid))

        # Snapshot which of those lines had OPEN exceptions right now.
        # After bind, hook's compute_snapshot will resolve these — we'll
        # attribute the resolution count back to execute() in step 3.
        all_pre_line_ids = [
            lid for ids in pre_bind_pending_line_ids_by_sku.values() for lid in ids
        ]
        if all_pre_line_ids:
            open_exc_rows = (
                db.query(models.ShipmentExceptionQueue.shipment_line_id)
                .filter(
                    models.ShipmentExceptionQueue.shipment_line_id.in_(all_pre_line_ids),
                    models.ShipmentExceptionQueue.resolved_at.is_(None),
                )
                .distinct()
                .all()
            )
            pre_bind_open_exception_line_ids = {str(r[0]) for r in open_exc_rows}

    for sku, it in by_sku.items():
        if product_model_service.get_active_sku_binding(db, sku):
            skipped_already_bound += 1
            continue
        ver_id = str(it.get("version_id") or "").strip()
        if not ver_id:
            bind_errors.append({"sku_code": sku, "error": "missing version_id"})
            continue
        try:
            product_model_service.bind_sku_to_version(
                db,
                sku_code=sku,
                version_id=ver_id,
                source_system="shipment_auto_resolve",
                metadata={
                    "requested_by": op,
                    "binding_method": it.get("match_method") or "auto",
                    "matched_keyword": it.get("matched_keyword"),
                    "skip_prefix_check": True,
                    "trigger": "auto_resolve_pending_shipment_lines",
                },
            )
            bound_skus.append(sku)
        except Exception as exc:  # noqa: BLE001
            bind_errors.append({"sku_code": sku, "error": str(exc)})

    db.commit()

    if not bound_skus:
        return {
            "scanned_days": preview.get("scanned_days"),
            "preview": preview,
            "bound_skus_count": 0,
            "skipped_already_bound": skipped_already_bound,
            "snapshots_created": 0,
            "lines_resolved": 0,
            "exceptions_resolved": 0,
            "bind_errors": bind_errors,
            "snapshot_errors": [],
            "items": [],
        }

    # Step 3: walk the lines we recorded as pending BEFORE bind. Most of
    # them now have a snapshot (created by the bind hook in
    # product_model_service.bind_sku_to_version, Issue 0.0i). For each:
    #   - if snapshot already exists → attribute it to this execute() call
    #   - if snapshot still missing → run _generate_bom_snapshot (defensive,
    #     handles bind-hook failures swallowed by the hook's try/except)
    # In either case, resolve any open SKU_NOT_BOUND exception rows.
    bound_set = set(bound_skus)
    pre_bind_line_ids: List[str] = []
    for sku in bound_set:
        pre_bind_line_ids.extend(pre_bind_pending_line_ids_by_sku.get(sku, []))
    pending_lines = (
        db.query(models.ShipmentLine)
        .filter(
            models.ShipmentLine.id.in_(pre_bind_line_ids) if pre_bind_line_ids else False,
        )
        .order_by(models.ShipmentLine.created_at.desc())
        .all()
    ) if pre_bind_line_ids else []

    now = _utcnow()
    for line in pending_lines:
        # Snapshot key fields up-front so we can still report them in error
        # cases even if ``line`` becomes detached after a rollback.
        sku = (line.sku_code or "").strip()
        line_id = line.id
        line_batch_id = line.batch_id
        outcome: Dict[str, Any] = {
            "shipment_line_id": line_id,
            "sku_code": sku,
            "status": "ok",
            "bom_snapshot_id": None,
            "error": None,
        }

        batch = db.get(models.ShipmentImportBatch, line_batch_id) if line_batch_id else None
        if not batch:
            outcome["status"] = "skipped_no_batch"
            outcome["error"] = "shipment line has no batch"
            out_items.append(outcome)
            continue

        try:
            existing = (
                db.query(models.BomSnapshot)
                .filter(models.BomSnapshot.shipment_line_id == line_id)
                .first()
            )
            if existing:
                snap = existing
            else:
                snap = _generate_bom_snapshot(db, batch=batch, line=line, persist_snapshot=True)
            if snap is None:
                outcome["status"] = "snapshot_failed"
                outcome["error"] = "snapshot generation returned None (see exception queue)"
                out_items.append(outcome)
                snapshot_errors.append({
                    "shipment_line_id": line_id,
                    "sku_code": sku,
                    "error": "snapshot None",
                })
                db.commit()
                continue

            snap_id = snap.id
            # Issue 0.0i: bind_sku_to_version now eagerly creates snapshots
            # for ALL pending lines of the bound SKU. When that hook runs,
            # the snapshot already exists by the time we get here. We MUST
            # still attribute it to this execute() call — the user clicked
            # "⚡ 一键自动绑定" once and expects the snapshot count to
            # reflect what the click produced (whether hook-eager or
            # explicit). Without this, the UI shows "绑定 N 个 / 出快照 0
            # 条" which is misleading.
            snapshots_created += 1
            outcome["bom_snapshot_id"] = snap_id

            # NOTE: ShipmentLine.status is a derived field (presence of
            # BomSnapshot/ShipmentCostingResult), not a stored column. Now
            # that ``snap`` exists, ``list_shipment_lines`` will naturally
            # report this row as 'processed' on the next refresh.
            lines_resolved += 1

            # Resolve any open SKU_NOT_BOUND exception(s) attached to this line.
            # NOTE: ShipmentExceptionQueue does NOT use SoftDeleteMixin
            # (no is_archived column). Use only resolved_at as the open marker.
            open_excs = (
                db.query(models.ShipmentExceptionQueue)
                .filter(
                    models.ShipmentExceptionQueue.shipment_line_id == line_id,
                    models.ShipmentExceptionQueue.resolved_at.is_(None),
                )
                .all()
            )
            for exc_row in open_excs:
                exc_row.resolved_at = now
                exc_row.message = "resolved_by_auto_resolve"
                payload0 = dict(getattr(exc_row, "payload_json", {}) or {})
                payload0["resolution"] = {
                    "action": "auto_resolve",
                    "resolved_at": now.isoformat(),
                    "resolved_by": op,
                    "resolved_bom_snapshot_id": snap_id,
                    "trigger": "auto_resolve_pending_shipment_lines",
                }
                exc_row.payload_json = _json_safe(payload0)
                db.add(exc_row)
                exceptions_resolved += 1
            # Issue 0.0i: if hook (inside bind_sku_to_version) already
            # resolved this line's exceptions, the open_excs query above
            # found nothing — but the operator did cause this resolution
            # by clicking ⚡. Attribute one count per line that had an
            # open exception immediately before the bind.
            if not open_excs and line_id in pre_bind_open_exception_line_ids:
                exceptions_resolved += 1

            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            outcome["status"] = "error"
            outcome["error"] = str(exc)
            snapshot_errors.append({
                "shipment_line_id": line_id,
                "sku_code": sku,
                "error": str(exc),
            })

        out_items.append(outcome)

    return {
        "scanned_days": preview.get("scanned_days"),
        "preview": preview,
        "bound_skus_count": len(bound_skus),
        "skipped_already_bound": skipped_already_bound,
        "snapshots_created": snapshots_created,
        "lines_resolved": lines_resolved,
        "exceptions_resolved": exceptions_resolved,
        "bind_errors": bind_errors,
        "snapshot_errors": snapshot_errors,
        "items": out_items,
    }


def get_recent_shipment_line_stats(
    db: Session,
    *,
    hours: int = 24,
    latest_runs_limit: int = 5,
) -> Dict[str, Any]:
    """
    Lightweight summary for the new 「📦 业务管理 → 🚚 发货管理 → 🔴 待处理」
    page header strip. Returns:

      {
        "window_hours": 24,
        "as_of": "<utc iso>",
        "total_new_lines": 102,                # ShipmentLine.created_at >= cutoff
        "by_source_system": [
          {"source_system": "jackyun", "count": 102},
          {"source_system": "excel_upload", "count": 0},
          {"source_system": null, "count": 0},
        ],
        "latest_runs": [                       # IntegrationSyncRun, source_system=jackyun + sync_type=shipment_pull
          {                                    # latest 5 by finished_at (succeeded or failed)
            "id": "...", "source_system": "jackyun", "sync_type": "shipment_pull",
            "status": "succeeded", "inserted_rows": 102, "updated_rows": 0,
            "started_at": "...", "finished_at": "...", "triggered_by": "ui-quick",
          },
          ...
        ],
      }

    Performance: ~50ms (3 cheap COUNT/GROUP BY + 1 ORDER BY LIMIT) — safe to call
    from the page header on every navigation.
    """
    hours_clamped = max(min(int(hours or 24), 24 * 30), 1)
    runs_limit = max(min(int(latest_runs_limit or 5), 50), 1)
    cutoff_at = _utcnow().replace(tzinfo=None) - timedelta(hours=hours_clamped)

    # 1. Total new shipment lines in window (one COUNT)
    total_new = (
        db.query(func.count(models.ShipmentLine.id))
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            models.ShipmentLine.is_active.is_(True),
            models.ShipmentLine.created_at >= cutoff_at,
        )
        .scalar()
        or 0
    )

    # 2. Per source breakdown (one GROUP BY)
    rows = (
        db.query(
            models.ShipmentLine.source_system,
            func.count(models.ShipmentLine.id),
        )
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            models.ShipmentLine.is_active.is_(True),
            models.ShipmentLine.created_at >= cutoff_at,
        )
        .group_by(models.ShipmentLine.source_system)
        .all()
    )
    by_source: List[Dict[str, Any]] = []
    for src, cnt in rows:
        by_source.append({
            "source_system": (str(src) if src else None),
            "count": int(cnt or 0),
        })
    by_source.sort(key=lambda x: -x["count"])

    # 3. Latest sync runs (limited)
    runs = (
        db.query(models.IntegrationSyncRun)
        .filter(
            models.IntegrationSyncRun.source_system == "jackyun",
            models.IntegrationSyncRun.sync_type == "shipment_pull",
        )
        .order_by(
            models.IntegrationSyncRun.finished_at.is_(None),
            models.IntegrationSyncRun.finished_at.desc(),
            models.IntegrationSyncRun.started_at.desc(),
        )
        .limit(runs_limit)
        .all()
    )
    latest_runs: List[Dict[str, Any]] = []
    for r in runs:
        latest_runs.append({
            "id": r.id,
            "source_system": r.source_system,
            "sync_type": r.sync_type,
            "status": r.status,
            "inserted_rows": int(r.inserted_rows or 0),
            "updated_rows": int(r.updated_rows or 0),
            "error_rows": int(r.error_rows or 0),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "triggered_by": r.triggered_by,
            "error_message": r.error_message,
        })

    # 4. Failed sync runs in the same window (one COUNT) + the most recent
    #    failed run for the user to drill into. PendingTab shows a red
    #    Alert if recent_failed_runs_count > 0, so silent failures don't
    #    get scrolled off the latest_runs list and disappear (Issue 0.0h).
    recent_failed_runs_count = (
        db.query(func.count(models.IntegrationSyncRun.id))
        .filter(
            models.IntegrationSyncRun.source_system == "jackyun",
            models.IntegrationSyncRun.sync_type == "shipment_pull",
            models.IntegrationSyncRun.status == "failed",
            # Use started_at as the anchor: a failed run might never set
            # finished_at if the worker process crashed.
            models.IntegrationSyncRun.started_at >= cutoff_at,
        )
        .scalar()
        or 0
    )
    latest_failed_run_obj = (
        db.query(models.IntegrationSyncRun)
        .filter(
            models.IntegrationSyncRun.source_system == "jackyun",
            models.IntegrationSyncRun.sync_type == "shipment_pull",
            models.IntegrationSyncRun.status == "failed",
            models.IntegrationSyncRun.started_at >= cutoff_at,
        )
        .order_by(models.IntegrationSyncRun.started_at.desc())
        .first()
    )
    latest_failed_run: Optional[Dict[str, Any]] = None
    if latest_failed_run_obj is not None:
        r = latest_failed_run_obj
        latest_failed_run = {
            "id": r.id,
            "source_system": r.source_system,
            "sync_type": r.sync_type,
            "status": r.status,
            "inserted_rows": int(r.inserted_rows or 0),
            "updated_rows": int(r.updated_rows or 0),
            "error_rows": int(r.error_rows or 0),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "triggered_by": r.triggered_by,
            "error_message": r.error_message,
        }

    return {
        "window_hours": hours_clamped,
        "as_of": _utcnow().isoformat(),
        "total_new_lines": int(total_new),
        "by_source_system": by_source,
        "latest_runs": latest_runs,
        "recent_failed_runs_count": int(recent_failed_runs_count),
        "latest_failed_run": latest_failed_run,
    }


# ============================================================================
# Issue 29 — POST /shipments/lines/{id}/resolve  (one-shot bind+spec+snapshot)
# ============================================================================
#
# Until 2026-05-07 the frontend orchestrated 3-4 sequential REST calls per
# row to do one "adopt model" decision (lookup SkuMaster → bind → set
# governance → compute snapshot). That meant:
#   1. ~1.5-2s of network round-trips per row (visible in PendingTab).
#   2. Partial failure handling lived in the browser. If step 3 succeeded
#      and step 4 failed, the SKU ended up bound + auto_bound but with no
#      snapshot — and the user just saw a vague error.
#   3. Bulk operations had to be Promise.all'd at concurrency 8 from the
#      frontend (see PendingTab.tsx BULK_CONCURRENCY).
#
# This server-side function takes a ShipmentLine + an action and runs the
# whole pipeline in one transaction, returning a structured step audit so
# the UI can still render "step 3 failed because X" if needed.
#
# Action menu (mirrors frontend ShipmentLineResolveAction):
#   - 'adopt'           → bind SkuMaster to model_id, set governance=auto_bound,
#                         recompute/generate BOM snapshot. Requires model_id.
#   - 'mark_long_tail'  → governance=do_not_model. (Snapshot picks long-tail
#                         fallback rate next time worker runs; we do NOT
#                         force a snapshot here because the user might still
#                         be batch-tagging long_tail_category afterwards.)
#   - 'defer_modeling'  → governance=pending_model. Same rationale: snapshot
#                         is intentionally deferred (no model is bound yet).
# ============================================================================


_RESOLVE_ACTIONS = ("adopt", "mark_long_tail", "defer_modeling")


def resolve_shipment_line(
    db: Session,
    *,
    shipment_line_id: str,
    action: str,
    model_id: Optional[str] = None,
    operator_id: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """One-shot resolver for a single shipment line. See module banner above.

    Returns
    -------
    {
      "ok": bool,
      "action": str,
      "shipment_line_id": str,
      "snapshot_id": Optional[str],
      "snapshot_action": Optional[str],   # generated|recomputed|skipped|failed
      "error": Optional[str],
      "steps": [
        {"step": str, "ok": bool, "duration_ms": int, "detail": Optional[str]}
      ],
    }
    """
    if action not in _RESOLVE_ACTIONS:
        raise ValueError(
            f"unknown action {action!r}; allowed={list(_RESOLVE_ACTIONS)}"
        )

    lid = (shipment_line_id or "").strip()
    if not lid:
        raise ValueError("shipment_line_id 不能为空")

    line = db.get(models.ShipmentLine, lid)
    if not line or getattr(line, "is_archived", False):
        raise ValueError("发货行不存在或已归档")

    sku_code = (getattr(line, "sku_code", None) or "").strip()
    if not sku_code:
        return {
            "ok": False,
            "action": action,
            "shipment_line_id": str(line.id),
            "snapshot_id": None,
            "snapshot_action": None,
            "error": "该发货行缺 sku_code, 无法做治理决策",
            "steps": [{"step": "precheck", "ok": False, "duration_ms": 0, "detail": "missing sku_code"}],
        }

    steps: List[Dict[str, Any]] = []

    def _step(name: str, fn):
        t0 = datetime.now(timezone.utc)
        try:
            result = fn()
            dur = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            steps.append({"step": name, "ok": True, "duration_ms": dur, "detail": None})
            return result
        except Exception as exc:  # noqa: BLE001 — surface to caller
            dur = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            steps.append(
                {
                    "step": name,
                    "ok": False,
                    "duration_ms": dur,
                    "detail": str(exc) or exc.__class__.__name__,
                }
            )
            raise

    try:
        # ----- defer_modeling / mark_long_tail = governance-only paths -----
        if action == "defer_modeling":
            _step(
                "set_governance_pending_model",
                lambda: sku_master_service.set_sku_governance(
                    db,
                    sku_codes=[sku_code],
                    status=sku_master_service.GOVERNANCE_PENDING_MODEL,
                    decided_by=operator_id,
                    note=note or "发货管理-加入建模 backlog",
                ),
            )
            db.commit()
            return {
                "ok": True,
                "action": action,
                "shipment_line_id": str(line.id),
                "snapshot_id": None,
                "snapshot_action": None,
                "error": None,
                "steps": steps,
            }

        if action == "mark_long_tail":
            _step(
                "set_governance_do_not_model",
                lambda: sku_master_service.set_sku_governance(
                    db,
                    sku_codes=[sku_code],
                    status=sku_master_service.GOVERNANCE_DO_NOT_MODEL,
                    decided_by=operator_id,
                    note=note or "发货管理-标记长尾",
                ),
            )
            db.commit()
            return {
                "ok": True,
                "action": action,
                "shipment_line_id": str(line.id),
                "snapshot_id": None,
                "snapshot_action": None,
                "error": None,
                "steps": steps,
            }

        # ----- adopt = bind + auto_bound + snapshot (the heavy path) -----
        if not model_id:
            return {
                "ok": False,
                "action": action,
                "shipment_line_id": str(line.id),
                "snapshot_id": None,
                "snapshot_action": None,
                "error": "adopt 缺 model_id",
                "steps": steps,
            }

        sku_master = _step(
            "lookup_sku_master",
            lambda: db.query(models.SkuMaster)
            .filter(models.SkuMaster.erp_sku_barcode == sku_code)
            .filter(models.SkuMaster.is_archived.is_(False))
            .first(),
        )
        if sku_master is None:
            return {
                "ok": False,
                "action": action,
                "shipment_line_id": str(line.id),
                "snapshot_id": None,
                "snapshot_action": None,
                "error": f"未找到 SKU 主档(barcode={sku_code}); 请先确保发货同步已建档",
                "steps": steps,
            }
        sku_master_id = str(sku_master.id)

        _step(
            "bind_sku_to_model",
            lambda: sku_master_service.bind_sku_master_by_model(
                db,
                model_id=str(model_id),
                sku_master_ids=[sku_master_id],
                requested_by=operator_id,
                allow_rebind=True,
            ),
        )

        _step(
            "set_governance_auto_bound",
            lambda: sku_master_service.set_sku_governance(
                db,
                sku_codes=[sku_code],
                status=sku_master_service.GOVERNANCE_AUTO_BOUND,
                decided_by=operator_id,
                note=note or "发货管理-一键采纳模型",
            ),
        )

        snap_resp = _step(
            "compute_snapshot",
            lambda: compute_snapshot_for_shipment_line(
                db,
                shipment_line_id=str(line.id),
                operator_id=operator_id,
                overwrite=True,
            ),
        )
        # compute_snapshot already commits internally; commit again is a no-op.
        db.commit()

        snap_action = (snap_resp or {}).get("action")
        snap_id = (snap_resp or {}).get("bom_snapshot_id")
        snap_detail = (snap_resp or {}).get("detail")

        # snapshot=failed is a "soft fail" — earlier steps did succeed
        # (binding + governance) but BOM generation hit an issue. We
        # surface it but keep ok=True for the binding side because that's
        # what the user actually clicked. UI uses snapshot_action to know.
        return {
            "ok": True,
            "action": action,
            "shipment_line_id": str(line.id),
            "snapshot_id": snap_id,
            "snapshot_action": snap_action,
            "error": snap_detail if snap_action == "failed" else None,
            "steps": steps,
        }

    except ValueError as exc:
        db.rollback()
        return {
            "ok": False,
            "action": action,
            "shipment_line_id": str(line.id),
            "snapshot_id": None,
            "snapshot_action": None,
            "error": str(exc),
            "steps": steps,
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {
            "ok": False,
            "action": action,
            "shipment_line_id": str(line.id),
            "snapshot_id": None,
            "snapshot_action": None,
            "error": str(exc) or exc.__class__.__name__,
            "steps": steps,
        }


# ----------------------------------------------------------------------------
# Issue 29 follow-up — POST /shipments/lines/bulk-resolve
#
# Folds the frontend's `Promise.all + concurrency 8` loop in PendingTab into
# a single server-side call. Each row still goes through resolve_shipment_line
# (which commits/rollbacks per-row), so a single bad row never blocks the
# rest. We deliberately keep "best effort" (stop_on_first_error=False) as
# the default — it matches what the UI was already doing.
#
# Why per-row commits instead of one big transaction:
#   - resolve_shipment_line('adopt') already does 4 sub-steps; if we wrapped
#     N rows in one transaction, a SQL constraint failure on row 99 would
#     undo rows 1..98 of governance/binding work — nasty surprise.
#   - Per-row commit also means the UI can refetch mid-stream and watch the
#     queue shrink, identical to the old frontend-fanout behavior.
# ----------------------------------------------------------------------------


def bulk_resolve_shipment_lines(
    db: Session,
    *,
    items: List[Dict[str, Any]],
    operator_id: Optional[str] = None,
    note: Optional[str] = None,
    stop_on_first_error: bool = False,
) -> Dict[str, Any]:
    """Run resolve_shipment_line for every entry in ``items``.

    Each item: ``{"shipment_line_id": str, "action": str, "model_id"?: str}``.
    Item-level ``operator_id`` / ``note`` are inherited from the call args
    (kept simple; operators normally tag a whole batch the same way).

    Returns
    -------
    {
      "total": int,
      "succeeded": int,
      "failed": int,
      "skipped_after_error": int,
      "total_duration_ms": int,
      "results": [
        {
          "shipment_line_id": str,
          "ok": bool,
          "action": str,
          "snapshot_id": Optional[str],
          "snapshot_action": Optional[str],
          "error": Optional[str],
          "duration_ms": int,
        }, ...
      ],
    }

    Errors that resolve_shipment_line raises (ValueError on missing line,
    unknown action) are caught here and turned into per-row failures so
    one bad row never tanks the whole batch.
    """
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if not items:
        return {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped_after_error": 0,
            "total_duration_ms": 0,
            "results": [],
        }

    bulk_t0 = datetime.now(timezone.utc)
    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    skipped = 0
    halt = False

    for idx, raw in enumerate(items):
        if halt:
            results.append(
                {
                    "shipment_line_id": str((raw or {}).get("shipment_line_id") or ""),
                    "ok": False,
                    "action": str((raw or {}).get("action") or ""),
                    "snapshot_id": None,
                    "snapshot_action": None,
                    "error": "skipped after earlier failure (stop_on_first_error=true)",
                    "duration_ms": 0,
                }
            )
            skipped += 1
            continue

        if not isinstance(raw, dict):
            results.append(
                {
                    "shipment_line_id": "",
                    "ok": False,
                    "action": "",
                    "snapshot_id": None,
                    "snapshot_action": None,
                    "error": f"items[{idx}] must be an object",
                    "duration_ms": 0,
                }
            )
            failed += 1
            if stop_on_first_error:
                halt = True
            continue

        line_id = str(raw.get("shipment_line_id") or "").strip()
        action = str(raw.get("action") or "").strip()
        model_id = raw.get("model_id")
        item_t0 = datetime.now(timezone.utc)
        try:
            res = resolve_shipment_line(
                db,
                shipment_line_id=line_id,
                action=action,
                model_id=str(model_id).strip() if model_id else None,
                operator_id=operator_id,
                note=note,
            )
            duration_ms = int((datetime.now(timezone.utc) - item_t0).total_seconds() * 1000)
            row = {
                "shipment_line_id": str(res.get("shipment_line_id") or line_id),
                "ok": bool(res.get("ok")),
                "action": str(res.get("action") or action),
                "snapshot_id": res.get("snapshot_id"),
                "snapshot_action": res.get("snapshot_action"),
                "error": res.get("error"),
                "duration_ms": duration_ms,
            }
        except ValueError as exc:
            duration_ms = int((datetime.now(timezone.utc) - item_t0).total_seconds() * 1000)
            row = {
                "shipment_line_id": line_id,
                "ok": False,
                "action": action,
                "snapshot_id": None,
                "snapshot_action": None,
                "error": str(exc),
                "duration_ms": duration_ms,
            }
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((datetime.now(timezone.utc) - item_t0).total_seconds() * 1000)
            row = {
                "shipment_line_id": line_id,
                "ok": False,
                "action": action,
                "snapshot_id": None,
                "snapshot_action": None,
                "error": str(exc) or exc.__class__.__name__,
                "duration_ms": duration_ms,
            }

        results.append(row)
        if row["ok"]:
            succeeded += 1
        else:
            failed += 1
            if stop_on_first_error:
                halt = True

    total_duration_ms = int((datetime.now(timezone.utc) - bulk_t0).total_seconds() * 1000)
    return {
        "total": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "skipped_after_error": skipped,
        "total_duration_ms": total_duration_ms,
        "results": results,
    }
