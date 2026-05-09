from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .. import models


PARSER_VERSION = "v1"


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()  # noqa: S324 - non-crypto use (idempotency key)


def _sha1_text(text: str) -> str:
    return _sha1_bytes((text or "").encode("utf-8"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _norm_header(value: Any) -> Optional[str]:
    s = _norm_str(value)
    if not s:
        return None
    s2 = (
        s.replace("（", "(")
        .replace("）", ")")
        .replace("\u00a0", " ")
    )
    s2 = re.sub(r"\s+", " ", s2).strip()
    s2 = re.sub(r"\([^)]*\)\s*$", "", s2).strip()
    return s2 or None


AFTER_SALES_FIELD_ALIASES: Dict[str, List[str]] = {
    "after_sales_no": ["退换补发单号", "售后单号", "after_sales_no", "afterSalesNo"],
    # 网店原始订单号（天猫订单编号等）
    "order_no": ["网店订单号", "原始单号", "订单编号", "order_no", "shop_order_no"],
    # 商品链接ID（天猫链接ID等）
    "product_link_id": ["商品链接ID", "商品链接Id", "商品链接id", "product_link_id", "productLinkId"],
    "applied_at": ["申请时间", "申请日期", "applied_at", "apply_time"],
    "channel": ["销售渠道", "店铺", "渠道", "channel", "shop_name"],
    "reason": ["退换原因", "原因", "reason"],
    "product_code": ["货品编号", "商品编码", "product_code"],
    "product_name": ["货品名称", "商品名称", "product_name"],
    "spec_text": ["规格", "交易规格", "商品规格（网店）", "spec_text"],
    # 货品条码（系统 SKU 主键）
    "sku_code": ["货品条码", "货品条码（系统）", "sku_code", "erp_sku_barcode", "barcode"],
    "unit": ["单位", "uom", "unit"],
    "sale_unit_price": ["销售单价", "单价", "sale_unit_price"],
    "return_qty": ["退货数量", "退货件数", "return_qty"],
    "actual_return_qty": ["实退数量", "实际退货数量", "actual_return_qty"],
    "refund_amount": ["退货金额", "退款金额", "refund_amount"],
    "allocated_refund_amount": ["分摊后退货金额", "分摊后退款金额", "allocated_refund_amount"],
    # optional trace fields
    "customer_account": ["客户账号", "customer_account"],
    # Optional tag for downstream filtering (e.g. 刷单退货/正常退货/补发关联等)
    "tag": ["标记", "标签", "tag"],
}


def _build_header_index(header_row: Iterable[Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        name = _norm_header(cell)
        if not name:
            continue
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


def _get_field(row: List[Any], headers: Dict[str, int], field: str) -> Any:
    aliases = AFTER_SALES_FIELD_ALIASES.get(field) or []
    return _get_by_headers(row, headers, aliases)


def _has_any_header(headers: Dict[str, int], candidates: List[str]) -> bool:
    for c in candidates or []:
        key = _norm_header(c) or str(c)
        if key in headers:
            return True
    return False


def _parse_occurred_at_from_after_sales_no(after_sales_no: str | None) -> Optional[datetime]:
    """
    Common pattern: SH202601250033 -> 2026-01-25 (UTC)
    If not matched, return None.
    """
    s = (after_sales_no or "").strip()
    if not s:
        return None
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", s)
    if not m:
        return None
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _resolve_sku_code_by_product_code(
    db: Session,
    *,
    product_code: Optional[str],
    channel: Optional[str],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Best-effort mapping for analytics:
    - If SkuMaster has a unique match by product_code (and optionally channel), return erp_sku_barcode.
    - Otherwise return None + a warning payload.
    """
    pc = (product_code or "").strip()
    if not pc:
        return None, {"warning": "SKU_RESOLVE_SKIPPED", "reason": "EMPTY_PRODUCT_CODE"}

    q = db.query(models.SkuMaster).filter(models.SkuMaster.product_code == pc)
    # prefer channel match if provided
    if channel:
        q2 = q.filter(models.SkuMaster.channel == channel)
        items = q2.limit(5).all()
        if len(items) == 1:
            return items[0].erp_sku_barcode, None
        if len(items) > 1:
            return None, {
                "warning": "SKU_RESOLVE_AMBIGUOUS",
                "product_code": pc,
                "channel": channel,
                "candidates": [it.erp_sku_barcode for it in items],
            }
        # fall back to no-channel query

    items = q.limit(5).all()
    if len(items) == 1:
        return items[0].erp_sku_barcode, None
    if len(items) == 0:
        return None, {"warning": "SKU_RESOLVE_NOT_FOUND", "product_code": pc, "channel": channel}
    return None, {
        "warning": "SKU_RESOLVE_AMBIGUOUS",
        "product_code": pc,
        "channel": channel,
        "candidates": [it.erp_sku_barcode for it in items],
    }


def _normalize_rows_from_xlsx(file_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], [{"warning": "EMPTY_FILE"}]

    headers = _build_header_index(list(rows[0]))
    warnings: List[Dict[str, Any]] = []

    def _warn(code: str, **extra: Any) -> None:
        payload = {"warning": code}
        payload.update(extra)
        warnings.append(payload)

    # 2025 分析期：不强制要求 spec_text（可能过时），订单号/条码优先作为关联键
    required_fields = ["after_sales_no", "channel", "return_qty", "refund_amount"]
    missing_fields = [
        f for f in required_fields
        if not _has_any_header(headers, AFTER_SALES_FIELD_ALIASES.get(f) or [])
    ]
    if missing_fields:
        _warn("MISSING_HEADERS", missing_fields=missing_fields)

    normalized: List[Dict[str, Any]] = []
    for i, row in enumerate(rows[1:], start=2):
        row_list = list(row)
        if not any(v not in (None, "") for v in row_list):
            continue

        after_sales_no = _norm_str(_get_field(row_list, headers, "after_sales_no"))
        order_no = _norm_str(_get_field(row_list, headers, "order_no"))
        product_link_id = _norm_str(_get_field(row_list, headers, "product_link_id"))
        applied_at_raw = _get_field(row_list, headers, "applied_at")
        channel = _norm_str(_get_field(row_list, headers, "channel"))
        reason = _norm_str(_get_field(row_list, headers, "reason"))
        product_code = _norm_str(_get_field(row_list, headers, "product_code"))
        product_name = _norm_str(_get_field(row_list, headers, "product_name"))
        spec_text = _norm_str(_get_field(row_list, headers, "spec_text"))
        sku_code = _norm_str(_get_field(row_list, headers, "sku_code"))
        unit = _norm_str(_get_field(row_list, headers, "unit"))
        sale_unit_price = _to_decimal(_get_field(row_list, headers, "sale_unit_price"))
        return_qty = _to_decimal(_get_field(row_list, headers, "return_qty"))
        actual_return_qty = _to_decimal(_get_field(row_list, headers, "actual_return_qty"))
        refund_amount = _to_decimal(_get_field(row_list, headers, "refund_amount"))
        allocated_refund_amount = _to_decimal(_get_field(row_list, headers, "allocated_refund_amount"))
        tag = _norm_str(_get_field(row_list, headers, "tag"))

        raw_row: Dict[str, Any] = {}
        for name, idx in headers.items():
            if idx < len(row_list):
                raw_row[name] = row_list[idx]

        normalize_warnings: List[Dict[str, Any]] = []
        occurred_at = _parse_occurred_at_from_after_sales_no(after_sales_no)
        if after_sales_no and occurred_at is None:
            normalize_warnings.append({"warning": "OCCURRED_AT_PARSE_FAILED", "after_sales_no": after_sales_no})

        # applied_at: accept datetime, excel numeric, or iso strings (best-effort)
        applied_at: Optional[datetime] = None
        if isinstance(applied_at_raw, datetime):
            applied_at = applied_at_raw if applied_at_raw.tzinfo else applied_at_raw.replace(tzinfo=timezone.utc)
        elif isinstance(applied_at_raw, (int, float)):
            # Some ERP exports store excel datetimes as serial numbers.
            try:
                dt = from_excel(applied_at_raw)
                if isinstance(dt, datetime):
                    applied_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                else:
                    # date -> datetime at 00:00
                    applied_at = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                applied_at = None
        elif isinstance(applied_at_raw, str):
            s = applied_at_raw.strip()
            if s:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(s, fmt)
                        applied_at = dt.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        applied_at = None
                if applied_at is None:
                    try:
                        dt = datetime.fromisoformat(s)
                        applied_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                    except Exception:  # noqa: BLE001
                        applied_at = None
        if applied_at_raw not in (None, "") and applied_at is None:
            normalize_warnings.append({"warning": "APPLIED_AT_PARSE_FAILED", "raw": str(applied_at_raw)[:64]})

        normalized.append(
            {
                "row_index": i,
                "after_sales_no": after_sales_no,
                "occurred_at": occurred_at,
                "applied_at": applied_at,
                "channel": channel,
                "reason": reason,
                "order_no": order_no,
                "product_link_id": product_link_id,
                "product_code": product_code,
                "product_name": product_name,
                "spec_text": spec_text,
                "sku_code": sku_code,
                "unit": unit,
                "sale_unit_price": sale_unit_price,
                "return_qty": return_qty,
                "actual_return_qty": actual_return_qty,
                "refund_amount": refund_amount,
                "allocated_refund_amount": allocated_refund_amount,
                "tag": tag,
                "raw_row": _json_safe(raw_row),
                "normalize_warnings": _json_safe(normalize_warnings),
            }
        )

    return normalized, warnings


def _enqueue_exception(
    db: Session,
    *,
    batch_id: str,
    after_sales_line_id: Optional[str],
    reason: str,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> models.AfterSalesExceptionQueue:
    exc = models.AfterSalesExceptionQueue(
        batch_id=batch_id,
        after_sales_line_id=after_sales_line_id,
        reason=reason,
        message=message,
        payload_json=_json_safe(payload or {}),
    )
    db.add(exc)
    db.flush()
    return exc


def import_after_sales_xlsx(
    db: Session,
    *,
    file_name: str,
    file_bytes: bytes,
    export_date: Optional[str],
    requested_by: Optional[str],
) -> models.AfterSalesImportBatch:
    file_hash = _sha1_bytes(file_bytes)
    batch = (
        db.query(models.AfterSalesImportBatch)
        .filter(models.AfterSalesImportBatch.file_hash == file_hash)
        .first()
    )
    if batch and batch.status == "success":
        return batch

    if not batch:
        batch = models.AfterSalesImportBatch(
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

    rows, warnings = _normalize_rows_from_xlsx(file_bytes)
    batch.warnings_json = warnings

    for payload in rows:
        batch.total_rows += 1

        after_sales_no = payload.get("after_sales_no")
        channel = payload.get("channel")
        order_no = payload.get("order_no")
        product_link_id = payload.get("product_link_id")
        product_code = payload.get("product_code")
        spec_text = payload.get("spec_text")
        sku_code_in = payload.get("sku_code")
        return_qty = payload.get("return_qty")
        refund_amount = payload.get("refund_amount")

        # External idempotency key (row-level)
        key_text = "|".join(
            [
                str(after_sales_no or ""),
                str(order_no or ""),
                str(product_link_id or ""),
                str(channel or ""),
                str(sku_code_in or ""),
                str(product_code or ""),
                str(spec_text or ""),
                str(return_qty or ""),
                str(refund_amount or ""),
            ]
        )
        external_line_key_hash = _sha1_text(key_text)

        # Basic validation (queue exception; still insert line for traceability)
        missing = []
        for f in ("after_sales_no", "channel", "product_code", "spec_text"):
            if not (payload.get(f) or "").strip():
                missing.append(f)
        if missing:
            payload.setdefault("normalize_warnings", [])
            payload["normalize_warnings"].append({"warning": "MISSING_REQUIRED_FIELDS", "missing": missing})

        # Prefer barcode from export; fallback to SkuMaster by product_code if missing.
        sku_code = (sku_code_in or "").strip() or None
        if not sku_code:
            sku_code, sku_warn = _resolve_sku_code_by_product_code(
                db, product_code=product_code, channel=channel
            )
            if sku_warn:
                payload.setdefault("normalize_warnings", [])
                payload["normalize_warnings"].append(sku_warn)

        exists = (
            db.query(models.AfterSalesLine)
            .filter(
                models.AfterSalesLine.external_line_key_hash == external_line_key_hash,
                models.AfterSalesLine.is_archived.is_(False),
            )
            .first()
        )
        if exists:
            batch.skipped_rows += 1
            continue

        line = models.AfterSalesLine(
            batch_id=batch.id,
            row_index=int(payload.get("row_index") or 0),
            after_sales_no=after_sales_no,
            occurred_at=payload.get("occurred_at"),
            applied_at=payload.get("applied_at"),
            channel=channel,
            reason=payload.get("reason"),
            order_no=order_no,
            product_link_id=product_link_id,
            product_code=product_code,
            product_name=payload.get("product_name"),
            spec_text=spec_text,
            unit=payload.get("unit"),
            sale_unit_price=payload.get("sale_unit_price"),
            return_qty=return_qty,
            actual_return_qty=payload.get("actual_return_qty"),
            refund_amount=refund_amount,
            allocated_refund_amount=payload.get("allocated_refund_amount"),
            sku_code=sku_code,
            external_line_key_hash=external_line_key_hash,
            tag=(payload.get("tag") or None),
            raw_row_json=_json_safe(payload.get("raw_row") or {}),
            normalize_warnings_json=_json_safe(payload.get("normalize_warnings") or []),
            metadata_json={"parser_version": PARSER_VERSION},
        )
        db.add(line)
        db.flush()
        batch.inserted_rows += 1

        # Exception queue for unresolved sku_code (for model-level attribution)
        if not sku_code:
            _enqueue_exception(
                db,
                batch_id=batch.id,
                after_sales_line_id=line.id,
                reason="SKU_NOT_RESOLVED",
                message="无法从货品编号解析到唯一 sku_code（货品条码）",
                payload={
                    "product_code": product_code,
                    "channel": channel,
                    "after_sales_no": after_sales_no,
                    "order_no": order_no,
                    "product_link_id": product_link_id,
                },
            )
            batch.exception_rows += 1

    batch.status = "success"
    batch.result_json = {
        "parser_version": PARSER_VERSION,
        "note": "2025 analysis mode: returns import only; costing uses current price strategy in analytics layer.",
    }
    db.commit()
    db.refresh(batch)
    return batch


def list_batches(db: Session, *, page: int, page_size: int) -> Tuple[int, List[models.AfterSalesImportBatch]]:
    q = db.query(models.AfterSalesImportBatch)
    total = q.count()
    items = (
        q.order_by(models.AfterSalesImportBatch.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def get_batch(db: Session, batch_id: str) -> Optional[models.AfterSalesImportBatch]:
    return db.get(models.AfterSalesImportBatch, batch_id)


def list_lines(db: Session, *, batch_id: Optional[str], limit: int) -> List[models.AfterSalesLine]:
    q = db.query(models.AfterSalesLine)
    if batch_id:
        q = q.filter(models.AfterSalesLine.batch_id == batch_id)
    return q.order_by(models.AfterSalesLine.created_at.desc()).limit(limit).all()


def search_lines(
    db: Session,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
    channel: Optional[str],
    sku_code: Optional[str],
    reason: Optional[str],
    model_code: Optional[str],
    product_link_id: Optional[str],
    time_basis: str = "applied",
    page: int,
    page_size: int,
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    List after-sales lines (detail view) with best-effort model binding info.
    Filters are applied on coalesce(applied_at, occurred_at) for robustness:
    some ERP exports miss applied_at or provide excel serial numbers.
    """
    tb = (time_basis or "applied").strip().lower()
    applied_time_expr = func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at)
    mapping_on = and_(
        models.SkuModelVersionMapping.is_archived.is_(False),
        models.SkuModelVersionMapping.is_active.is_(True),
        models.SkuModelVersionMapping.sku_code == models.AfterSalesLine.sku_code,
    )
    q = (
        db.query(models.AfterSalesLine)
        .outerjoin(models.SkuModelVersionMapping, mapping_on)
        .outerjoin(
            models.ProductModelVersion,
            models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
        )
        .outerjoin(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
        .filter(models.AfterSalesLine.is_archived.is_(False))
    )

    shipment_completed_expr = None
    if tb == "shipment_completed":
        # Match returns to shipment lines by strong keys, then filter by shipment completed_at window.
        q = q.join(
            models.ShipmentLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
            ),
        )
        shipment_completed_expr = models.ShipmentLine.completed_at
        if start is not None:
            q = q.filter(shipment_completed_expr.isnot(None), shipment_completed_expr >= start)
        if end is not None:
            q = q.filter(shipment_completed_expr.isnot(None), shipment_completed_expr < end)
    else:
        if start is not None:
            q = q.filter(applied_time_expr.isnot(None), applied_time_expr >= start)
        if end is not None:
            q = q.filter(applied_time_expr.isnot(None), applied_time_expr < end)
    if channel:
        q = q.filter(models.AfterSalesLine.channel == channel)
    if sku_code:
        q = q.filter(models.AfterSalesLine.sku_code == sku_code)
    if reason:
        q = q.filter(models.AfterSalesLine.reason == reason)
    if product_link_id:
        q = q.filter(models.AfterSalesLine.product_link_id == product_link_id)
    if model_code:
        q = q.filter(models.ProductModel.model_code == model_code)

    total = int(q.with_entities(func.count(func.distinct(models.AfterSalesLine.id))).scalar() or 0)

    entity_fields = [
        models.AfterSalesLine,
        models.ProductModel.model_code.label("bound_model_code"),
        models.ProductModel.model_name.label("bound_model_name"),
        models.ProductModelVersion.version_label.label("bound_version_label"),
    ]
    if shipment_completed_expr is not None:
        entity_fields.append(models.ShipmentLine.completed_at.label("shipment_completed_at"))
    rows = (
        q.with_entities(*entity_fields)
        .order_by(
            (shipment_completed_expr if shipment_completed_expr is not None else applied_time_expr).desc().nullslast(),
            models.AfterSalesLine.created_at.desc(),
        )
        .offset((max(page, 1) - 1) * max(page_size, 1))
        .limit(max(page_size, 1))
        .all()
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        if shipment_completed_expr is not None:
            line, bmc, bmn, bvl, shipment_completed_at = row
        else:
            line, bmc, bmn, bvl = row
            shipment_completed_at = None
        items.append(
            {
                "id": line.id,
                "batch_id": line.batch_id,
                "row_index": line.row_index,
                "after_sales_no": line.after_sales_no,
                "occurred_at": line.occurred_at,
                # For UI readability: show applied date if present, else fallback to occurred_at.
                "applied_at": line.applied_at or line.occurred_at,
                "shipment_completed_at": shipment_completed_at,
                "channel": line.channel,
                "reason": line.reason,
                "bound_model_code": bmc,
                "bound_model_name": bmn,
                "bound_version_label": bvl,
                "order_no": line.order_no,
                "product_link_id": line.product_link_id,
                "product_code": line.product_code,
                "product_name": line.product_name,
                "spec_text": line.spec_text,
                "unit": line.unit,
                "sale_unit_price": line.sale_unit_price,
                "return_qty": line.return_qty,
                "actual_return_qty": line.actual_return_qty,
                "refund_amount": line.refund_amount,
                "allocated_refund_amount": line.allocated_refund_amount,
                "sku_code": line.sku_code,
                "normalize_warnings_json": line.normalize_warnings_json,
                "metadata_json": line.metadata_json,
                "created_at": line.created_at,
                "updated_at": line.updated_at,
            }
        )

    return total, items


def reason_options(
    db: Session,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
    channel: Optional[str],
    sku_code: Optional[str],
    model_code: Optional[str],
    time_basis: str = "applied",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    tb = (time_basis or "applied").strip().lower()
    applied_time_expr = func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at)
    mapping_on = and_(
        models.SkuModelVersionMapping.is_archived.is_(False),
        models.SkuModelVersionMapping.is_active.is_(True),
        models.SkuModelVersionMapping.sku_code == models.AfterSalesLine.sku_code,
    )
    q = (
        db.query(models.AfterSalesLine.reason, func.count(models.AfterSalesLine.id).label("count"))
        .outerjoin(models.SkuModelVersionMapping, mapping_on)
        .outerjoin(
            models.ProductModelVersion,
            models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
        )
        .outerjoin(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
        .filter(models.AfterSalesLine.is_archived.is_(False))
        .filter(models.AfterSalesLine.reason.isnot(None), func.length(func.trim(models.AfterSalesLine.reason)) > 0)
    )
    if tb == "shipment_completed":
        q = q.join(
            models.ShipmentLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
            ),
        )
        if start is not None:
            q = q.filter(models.ShipmentLine.completed_at.isnot(None), models.ShipmentLine.completed_at >= start)
        if end is not None:
            q = q.filter(models.ShipmentLine.completed_at.isnot(None), models.ShipmentLine.completed_at < end)
    else:
        if start is not None:
            q = q.filter(applied_time_expr.isnot(None), applied_time_expr >= start)
        if end is not None:
            q = q.filter(applied_time_expr.isnot(None), applied_time_expr < end)
    if channel:
        q = q.filter(models.AfterSalesLine.channel == channel)
    if sku_code:
        q = q.filter(models.AfterSalesLine.sku_code == sku_code)
    if model_code:
        q = q.filter(models.ProductModel.model_code == model_code)

    rows = (
        q.group_by(models.AfterSalesLine.reason)
        .order_by(func.count(models.AfterSalesLine.id).desc())
        .limit(max(1, min(int(limit or 200), 500)))
        .all()
    )
    return [{"reason": str(r.reason), "count": int(r.count or 0)} for r in rows if r.reason]


def model_options(
    db: Session,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
    channel: Optional[str],
    sku_code: Optional[str],
    reason: Optional[str],
    time_basis: str = "applied",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    tb = (time_basis or "applied").strip().lower()
    applied_time_expr = func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at)
    mapping_on = and_(
        models.SkuModelVersionMapping.is_archived.is_(False),
        models.SkuModelVersionMapping.is_active.is_(True),
        models.SkuModelVersionMapping.sku_code == models.AfterSalesLine.sku_code,
    )
    q = (
        db.query(
            models.ProductModel.model_code,
            models.ProductModel.model_name,
            func.count(models.AfterSalesLine.id).label("count"),
        )
        .outerjoin(models.SkuModelVersionMapping, mapping_on)
        .outerjoin(
            models.ProductModelVersion,
            models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
        )
        .outerjoin(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
        .filter(models.AfterSalesLine.is_archived.is_(False))
        .filter(models.ProductModel.model_code.isnot(None), func.length(func.trim(models.ProductModel.model_code)) > 0)
    )
    if tb == "shipment_completed":
        q = q.join(
            models.ShipmentLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.is_active.is_(True),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
            ),
        )
        if start is not None:
            q = q.filter(models.ShipmentLine.completed_at.isnot(None), models.ShipmentLine.completed_at >= start)
        if end is not None:
            q = q.filter(models.ShipmentLine.completed_at.isnot(None), models.ShipmentLine.completed_at < end)
    else:
        if start is not None:
            q = q.filter(applied_time_expr.isnot(None), applied_time_expr >= start)
        if end is not None:
            q = q.filter(applied_time_expr.isnot(None), applied_time_expr < end)
    if channel:
        q = q.filter(models.AfterSalesLine.channel == channel)
    if sku_code:
        q = q.filter(models.AfterSalesLine.sku_code == sku_code)
    if reason:
        q = q.filter(models.AfterSalesLine.reason == reason)

    rows = (
        q.group_by(models.ProductModel.model_code, models.ProductModel.model_name)
        .order_by(func.count(models.AfterSalesLine.id).desc())
        .limit(max(1, min(int(limit or 200), 500)))
        .all()
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "model_code": str(r.model_code),
                "model_name": r.model_name,
                "count": int(r.count or 0),
            }
        )
    return out


def list_exceptions(
    db: Session, *, batch_id: Optional[str], resolved: Optional[bool], limit: int
) -> List[models.AfterSalesExceptionQueue]:
    q = db.query(models.AfterSalesExceptionQueue)
    if batch_id:
        q = q.filter(models.AfterSalesExceptionQueue.batch_id == batch_id)
    if resolved is True:
        q = q.filter(models.AfterSalesExceptionQueue.resolved_at.isnot(None))
    if resolved is False:
        q = q.filter(models.AfterSalesExceptionQueue.resolved_at.is_(None))
    return q.order_by(models.AfterSalesExceptionQueue.created_at.desc()).limit(limit).all()

