from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy.orm import Session

from .. import models
from . import bom_generation_service, product_model_service, spec_parser_service


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


def _build_header_index(header_row: Iterable[Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        name = _norm_str(cell)
        if not name:
            continue
        mapping[name] = idx
    return mapping


def _get_by_headers(row: List[Any], headers: Dict[str, int], names: List[str]) -> Any:
    for name in names:
        idx = headers.get(name)
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

    # Minimal header sanity (do not hard-fail; push warnings)
    required_any = ["发货单号", "完成时间", "销售渠道", "货品条码", "数量"]
    missing = [h for h in required_any if h not in headers]
    if missing:
        _warn("MISSING_HEADERS", missing=missing)

    normalized: List[Dict[str, Any]] = []
    for i, row in enumerate(rows[1:], start=2):
        row_list = list(row)
        # skip fully empty rows
        if not any(v not in (None, "") for v in row_list):
            continue

        shipment_no = _norm_str(_get_by_headers(row_list, headers, ["发货单号", "单号", "订单号"]))
        completed_at = _parse_excel_datetime(_get_by_headers(row_list, headers, ["完成时间", "付款时间"]))
        channel = _norm_str(_get_by_headers(row_list, headers, ["销售渠道", "店铺", "渠道"]))
        sku_code = _norm_str(_get_by_headers(row_list, headers, ["货品条码", "SKU", "sku_code"]))
        spec_text = _norm_str(_get_by_headers(row_list, headers, ["交易规格", "规格", "规格信息"]))
        if not spec_text:
            spec_text = _guess_spec_text(row_list)
        qty = _to_decimal(_get_by_headers(row_list, headers, ["数量", "数量合计"]))
        revenue_amount = _to_decimal(_get_by_headers(row_list, headers, ["金额", "实付金额"]))

        raw_row: Dict[str, Any] = {}
        for name, idx in headers.items():
            if idx < len(row_list):
                raw_row[name] = row_list[idx]

        normalized.append(
            {
                "row_index": i,
                "shipment_no": shipment_no,
                "completed_at": completed_at,
                "channel": channel,
                "sku_code": sku_code,
                "spec_text": spec_text,
                "qty": qty,
                "revenue_amount": revenue_amount,
                "raw_row": _json_safe(raw_row),
            }
        )
    return normalized, warnings


def _upsert_spec_snapshot(db: Session, *, spec_text: str) -> models.SpecParseSnapshot:
    spec_hash = _sha1_text(spec_text)
    existing = (
        db.query(models.SpecParseSnapshot)
        .filter(models.SpecParseSnapshot.spec_hash == spec_hash)
        .first()
    )
    if existing:
        return existing

    parsed = spec_parser_service.parse_spec(spec_text)
    dimensions = {
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


def _generate_bom_snapshot(
    db: Session,
    *,
    batch: models.ShipmentImportBatch,
    line: models.ShipmentLine,
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
            message="SKU 未绑定已发布标准版本",
            payload={"sku_code": sku},
        )
        return None

    # spec cache (by spec_hash)
    spec_snap = _upsert_spec_snapshot(db, spec_text=spec_text)

    qty = line.qty if line.qty is not None else Decimal("1")
    try:
        bom = bom_generation_service.generate_bom(
            db,
            spec_text=spec_text,
            model_version_id=None,
            sku_code=sku,
            quantity=Decimal(str(qty)),
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

    trace = dict(bom.get("trace") or {})
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


def import_shipment_xlsx(
    db: Session,
    *,
    file_name: str,
    file_bytes: bytes,
    export_date: Optional[str],
    requested_by: Optional[str],
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

    rows, warnings = _normalize_rows_from_xlsx(file_bytes)
    batch.warnings_json = warnings

    for payload in rows:
        batch.total_rows += 1
        shipment_no = payload.get("shipment_no")
        sku_code = payload.get("sku_code")
        spec_text = payload.get("spec_text")
        qty = payload.get("qty")
        revenue_amount = payload.get("revenue_amount")

        revision_group = _sha1_text("|".join([shipment_no or "", sku_code or "", spec_text or ""]))
        ext_hash = _sha1_text(
            "|".join(
                [
                    shipment_no or "",
                    sku_code or "",
                    spec_text or "",
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
            shipment_no=shipment_no,
            completed_at=payload.get("completed_at"),
            channel=payload.get("channel"),
            sku_code=sku_code,
            spec_text=spec_text,
            spec_hash=_sha1_text(spec_text) if spec_text else None,
            qty=qty,
            revenue_amount=revenue_amount,
            external_line_key_hash=ext_hash,
            revision_group_hash=revision_group,
            revision_no=1,
            is_active=True,
            raw_row_json=payload.get("raw_row") or {},
            normalize_warnings_json=[],
            metadata_json={},
        )
        db.add(line)
        db.flush()

        # revision chain: if same (shipment_no, sku_code, spec_text) but different qty/amount, mark old active as superseded
        prevs = (
            db.query(models.ShipmentLine)
            .filter(
                models.ShipmentLine.revision_group_hash == revision_group,
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

        batch.inserted_rows += 1

        existing_snapshot = (
            db.query(models.BomSnapshot)
            .filter(models.BomSnapshot.shipment_line_id == line.id)
            .first()
        )
        if not existing_snapshot:
            snap = _generate_bom_snapshot(db, batch=batch, line=line)
            if not snap:
                batch.exception_rows += 1

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
    items = query.order_by(models.ShipmentExceptionQueue.created_at.desc()).limit(limit).all()

    # Attach shipment line fields for readability (Excel-like columns)
    line_ids = [x.shipment_line_id for x in items if getattr(x, "shipment_line_id", None)]
    if not line_ids:
        return items
    lines = (
        db.query(models.ShipmentLine)
        .filter(models.ShipmentLine.id.in_(list(set(line_ids))))
        .all()
    )
    by_id = {l.id: l for l in lines}
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
    return query.order_by(models.BomSnapshot.created_at.desc()).limit(limit).all()


