from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from .. import models
from . import bom_generation_service, product_model_service, spec_parser_service, sku_master_service


PARSER_VERSION = "v1"
PREVIEW_CACHE_DIR = Path("logs") / "shipment_previews"


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
    missing = [h for h in required_any if _norm_header(h) not in headers]
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
        # ERP: 货品条码（系统）是主键；表头可能带括号备注，已通过 _norm_header 归一化
        sku_code = _norm_str(_get_by_headers(row_list, headers, ["货品条码", "货品条码（系统）", "SKU", "sku_code"]))
        # ERP: 商品规格（网店）是发货时最真实的交易规格；货品规格（系统）为配对写入字段（可能滞后）
        spec_text = _norm_str(
            _get_by_headers(
                row_list,
                headers,
                ["商品规格（网店）", "交易规格", "规格", "规格信息", "货品规格（系统）"],
            )
        )
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

        # SKU master autobackfill (MVP): if barcode not in sku_master, create minimal record for next imports.
        sku_master_service.ensure_from_shipment(
            db,
            erp_sku_barcode=sku_code or "",
            spec_text=spec_text,
            channel=payload.get("channel"),
            metadata={
                "source": "shipment_autobackfill",
                "shipment_import_batch_id": batch.id,
                "shipment_line_id": line.id,
                "shipment_no": shipment_no,
                "spec_hash": _sha1_text(spec_text) if spec_text else None,
            },
        )

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

