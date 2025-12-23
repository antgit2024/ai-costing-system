from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy.orm import Session, joinedload

from .. import models
from . import spec_parser_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    "平台商品Id（网店）",
    "平台规格Id（网店）",
    "匹配状态",
    "货品条码（系统）",
    "最后更新时间",
}

PARSER_VERSION = "v1"


def _sha1_text(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()  # noqa: S324 - idempotency/cache key


def _extract_model_code_hint(spec_text: Optional[str]) -> Optional[str]:
    """
    MVP: try extract model_code from spec_text leading token, e.g. "PM001;50*140;..." or "PM001；..."
    We intentionally keep it strict to avoid false positives.
    """
    raw = (spec_text or "").strip()
    if not raw:
        return None
    first = raw.split(";", 1)[0].split("；", 1)[0].strip()
    if not first:
        return None
    # Accept typical patterns: PM001 / PM-001 / PM001A ...
    if not first.upper().startswith("PM"):
        return None
    # basic safety: only allow letters/digits/_/-
    for ch in first:
        if not (ch.isalnum() or ch in ("_", "-")):
            return None
    return first.upper()


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
            "spec_text": _norm_str(_get(row, headers, "商品规格（网店）")),
            "match_status": _norm_str(_get(row, headers, "匹配状态")),
            "source_updated_at": _parse_excel_datetime(_get(row, headers, "最后更新时间")),
        }
        images = {
            "spec_image": _norm_str(_get(row, headers, "规格图片（网店）")),
            "product_image": _norm_str(_get(row, headers, "商品图片（网店）")),
        }

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
                metadata_json={"source": "erp_import", "requested_by": requested_by},
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
            meta.update({"source": "erp_import", "requested_by": requested_by, "updated_at": _utcnow().isoformat()})
            existing.metadata_json = meta
            _update_erp_parsed_cache(existing, requested_by=requested_by)
            seen[barcode] = existing
            updated += 1

    db.commit()
    return {"total": total, "inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}


def list_sku_master(
    db: Session,
    *,
    search: Optional[str],
    channel: Optional[str],
    match_status: Optional[str],
    page: int,
    page_size: int,
) -> Tuple[int, List[models.SkuMaster]]:
    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 20), 200), 1)
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
    total = q.count()
    items = q.order_by(models.SkuMaster.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    _attach_active_version_bindings(db, items)
    _attach_parsed_fields(items)
    return total, items


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
    return (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == code, models.SkuMaster.is_archived.is_(False))
        .first()
    )


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
        _update_shipment_seen(existing, shipment_spec_text=spec_text, channel=channel, metadata=metadata)
        return existing
    row = models.SkuMaster(
        erp_sku_barcode=barcode,
        channel=(channel or None),
        spec_text=(spec_text or None),
        metadata_json=dict(metadata),
    )
    _update_erp_parsed_cache(row, requested_by=str(metadata.get("requested_by") or ""))
    _update_shipment_seen(row, shipment_spec_text=spec_text, channel=channel, metadata=metadata)
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
) -> None:
    """
    Record last seen shipment spec_text/hash, and mark mismatch vs ERP spec_text if different.
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
        if erp_text and ship_text and erp_text != ship_text:
            meta["spec_mismatch"] = True
            meta["spec_mismatch_at"] = _utcnow().isoformat()
        else:
            # keep False only when both empty or equal; do not delete historical mismatch marker
            meta.setdefault("spec_mismatch", False)
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
                }
            )
    row.metadata_json = meta


def _attach_parsed_fields(rows: List[models.SkuMaster]) -> None:
    """
    Attach parsed summary fields as dynamic attributes for Pydantic response.
    """
    for r in rows:
        meta = dict(getattr(r, "metadata_json", None) or {})
        r.erp_spec_hash = meta.get("erp_spec_hash")
        r.erp_parser_version = meta.get("erp_parser_version")
        r.erp_dimensions = meta.get("erp_dimensions") or {}
        r.erp_tokens = meta.get("erp_tokens") or []
        r.model_code_hint = meta.get("model_code_hint_shipment") or meta.get("model_code_hint_erp")
        r.last_shipment_spec_text = meta.get("last_shipment_spec_text")
        r.last_shipment_spec_hash = meta.get("last_shipment_spec_hash")
        r.spec_mismatch = bool(meta.get("spec_mismatch"))
        r.spec_mismatch_at = meta.get("spec_mismatch_at")


