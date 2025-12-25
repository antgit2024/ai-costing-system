from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from sqlalchemy.orm import Session, joinedload

from .. import models
from . import product_model_service, spec_parser_service


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
    MVP: try extract model_code from spec_text leading token.
    Supported patterns (safe/low false-positive):
    - 3-char code: "A1B;..." / "024;..." / "K7Q；..."
    - token with leading 3 digits: "024画框;..." -> "024"
    - longer PM-prefixed code: "PM001;..." (kept for compatibility)
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

    # Priority 2: leading 3 digits anywhere, e.g. "024画框"
    for seg in segments:
        token = seg.strip().upper()
        if len(token) >= 3 and token[:3].isdigit():
            return token[:3]

    # Priority 3: legacy PM-prefixed code (scan any segment)
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
    bound_state: Optional[str] = None,
    spec_mismatch: Optional[bool] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
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
    # server-side filters for tabs (avoid empty pages caused by client-side filtering)
    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712
    if bound_state in ("bound", "unbound"):
        # Use EXISTS subquery to avoid N+1 and support pagination correctly.
        subq = (
            db.query(models.SkuModelVersionMapping.id)
            .filter(
                models.SkuModelVersionMapping.sku_code == models.SkuMaster.erp_sku_barcode,
                models.SkuModelVersionMapping.is_active.is_(True),
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
        )
        if bound_state == "bound":
            q = q.filter(subq.exists())
        else:
            q = q.filter(~subq.exists())

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
        r.preparse_spec_text = meta.get("preparse_spec_text")
        r.preparse_spec_hash = meta.get("preparse_spec_hash")
        r.preparse_parser_version = meta.get("preparse_parser_version")
        r.preparse_dimensions = meta.get("preparse_dimensions") or {}
        r.preparse_tokens = meta.get("preparse_tokens") or []
        r.preparse_saved_at = meta.get("preparse_saved_at")
        r.preparse_saved_by = meta.get("preparse_saved_by")
        r.spec_mismatch = bool(meta.get("spec_mismatch"))
        r.spec_mismatch_at = meta.get("spec_mismatch_at")


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
    existing = db.query(models.SpecParseSnapshot).filter(models.SpecParseSnapshot.spec_hash == spec_hash).first()
    if not existing:
        parsed0 = spec_parser_service.parse_spec(text)
        dimensions0 = {
            "width_cm": parsed0.get("width_cm"),
            "height_cm": parsed0.get("height_cm"),
            "diameter_cm": parsed0.get("diameter_cm"),
            "area_m2": parsed0.get("area_m2"),
            "perimeter_m": parsed0.get("perimeter_m"),
        }
        snap = models.SpecParseSnapshot(
            spec_hash=spec_hash,
            spec_text=text,
            tokens_json=list(parsed0.get("tokens") or []),
            dimensions_json=_json_safe(dimensions0),
            parser_version=PARSER_VERSION,
            parse_json=_json_safe(parsed0),
        )
        db.add(snap)
        db.flush()

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

    meta = dict(row.metadata_json or {})
    meta.update(
        {
            "preparse_spec_text": text,
            "preparse_spec_hash": spec_hash,
            "preparse_parser_version": PARSER_VERSION,
            "preparse_dimensions": _json_safe(dims),
            "preparse_tokens": list(parsed.get("tokens") or []),
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
    include_terms: Optional[str],
    exclude_terms: Optional[str],
    match_scope: Optional[str],
    skip_if_same_hash: bool = True,
    requested_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bulk pre-parse & persist cache for bound SKUs.
    NOTE: only touches sku_master.metadata_json (preparse_*), and SpecParseSnapshot upsert for audit.
    """
    limit = max(min(int(limit or 200), 5000), 1)

    total, rows = list_sku_master(
        db,
        search=search,
        channel=channel,
        match_status=match_status,
        bound_state="bound",
        spec_mismatch=None,
        include_terms=include_terms,
        exclude_terms=exclude_terms,
        match_scope=match_scope,
        page=1,
        page_size=limit,
    )
    _ = total  # kept for future extension

    scanned = 0
    saved = 0
    skipped_same_hash = 0
    errors: List[Dict[str, Any]] = []

    for r in rows:
        scanned += 1
        try:
            meta = dict(r.metadata_json or {})
            spec_text = (meta.get("last_shipment_spec_text") or r.spec_text or "").strip()
            if not spec_text:
                raise ValueError("spec_text empty")
            spec_hash = _sha1_text(spec_text)
            if skip_if_same_hash and meta.get("preparse_spec_hash") == spec_hash and meta.get("preparse_parser_version") == PARSER_VERSION:
                skipped_same_hash += 1
                continue

            # Upsert SpecParseSnapshot
            existing = (
                db.query(models.SpecParseSnapshot)
                .filter(models.SpecParseSnapshot.spec_hash == spec_hash)
                .first()
            )
            if not existing:
                parsed0 = spec_parser_service.parse_spec(spec_text)
                dimensions0 = {
                    "width_cm": parsed0.get("width_cm"),
                    "height_cm": parsed0.get("height_cm"),
                    "diameter_cm": parsed0.get("diameter_cm"),
                    "area_m2": parsed0.get("area_m2"),
                    "perimeter_m": parsed0.get("perimeter_m"),
                }
                snap = models.SpecParseSnapshot(
                    spec_hash=spec_hash,
                    spec_text=spec_text,
                    tokens_json=list(parsed0.get("tokens") or []),
                    dimensions_json=_json_safe(dimensions0),
                    parser_version=PARSER_VERSION,
                    parse_json=_json_safe(parsed0),
                )
                db.add(snap)
                db.flush()

            parsed = spec_parser_service.parse_spec(spec_text)
            dims = {
                "width_cm": parsed.get("width_cm"),
                "height_cm": parsed.get("height_cm"),
                "diameter_cm": parsed.get("diameter_cm"),
                "area_m2": parsed.get("area_m2"),
                "perimeter_m": parsed.get("perimeter_m"),
            }
            meta.update(
                {
                    "preparse_spec_text": spec_text,
                    "preparse_spec_hash": spec_hash,
                    "preparse_parser_version": PARSER_VERSION,
                    "preparse_dimensions": _json_safe(dims),
                    "preparse_tokens": list(parsed.get("tokens") or []),
                    "preparse_saved_at": _utcnow().isoformat(),
                    "preparse_saved_by": (requested_by or meta.get("requested_by") or None),
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
        "errors": errors,
    }


def preview_spec_preparse(
    db: Session,
    *,
    limit: int,
    search: Optional[str],
    channel: Optional[str],
    match_status: Optional[str],
    include_terms: Optional[str],
    exclude_terms: Optional[str],
    match_scope: Optional[str],
) -> Dict[str, Any]:
    """
    Preview parsed dimensions for bound SKUs, without persisting.
    """
    limit = max(min(int(limit or 200), 5000), 1)
    _, rows = list_sku_master(
        db,
        search=search,
        channel=channel,
        match_status=match_status,
        bound_state="bound",
        spec_mismatch=None,
        include_terms=include_terms,
        exclude_terms=exclude_terms,
        match_scope=match_scope,
        page=1,
        page_size=limit,
    )
    items: List[Dict[str, Any]] = []
    for r in rows:
        meta = dict(r.metadata_json or {})
        spec_text_used = (meta.get("last_shipment_spec_text") or r.spec_text or "").strip()
        if not spec_text_used:
            continue
        parsed = spec_parser_service.parse_spec(spec_text_used)
        items.append(
            {
                "sku_id": r.id,
                "erp_sku_barcode": r.erp_sku_barcode,
                "channel": r.channel,
                "spec_text_used": spec_text_used,
                "spec_hash": _sha1_text(spec_text_used),
                "width_cm": parsed.get("width_cm"),
                "height_cm": parsed.get("height_cm"),
                "diameter_cm": parsed.get("diameter_cm"),
                "area_m2": parsed.get("area_m2"),
                "perimeter_m": parsed.get("perimeter_m"),
            }
        )
    return {"scanned": len(rows), "items": items}


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
    errors: List[Dict[str, Any]] = []
    for r in rows:
        scanned += 1
        try:
            meta = dict(r.metadata_json or {})
            spec_text = (meta.get("last_shipment_spec_text") or r.spec_text or "").strip()
            if not spec_text:
                raise ValueError("spec_text empty")
            spec_hash = _sha1_text(spec_text)
            if skip_if_same_hash and meta.get("preparse_spec_hash") == spec_hash and meta.get("preparse_parser_version") == PARSER_VERSION:
                skipped_same_hash += 1
                continue
            # upsert snapshot
            existing = (
                db.query(models.SpecParseSnapshot)
                .filter(models.SpecParseSnapshot.spec_hash == spec_hash)
                .first()
            )
            if not existing:
                parsed0 = spec_parser_service.parse_spec(spec_text)
                dimensions0 = {
                    "width_cm": parsed0.get("width_cm"),
                    "height_cm": parsed0.get("height_cm"),
                    "diameter_cm": parsed0.get("diameter_cm"),
                    "area_m2": parsed0.get("area_m2"),
                    "perimeter_m": parsed0.get("perimeter_m"),
                }
                snap = models.SpecParseSnapshot(
                    spec_hash=spec_hash,
                    spec_text=spec_text,
                    tokens_json=list(parsed0.get("tokens") or []),
                    dimensions_json=_json_safe(dimensions0),
                    parser_version=PARSER_VERSION,
                    parse_json=_json_safe(parsed0),
                )
                db.add(snap)
                db.flush()
            parsed = spec_parser_service.parse_spec(spec_text)
            dims = {
                "width_cm": parsed.get("width_cm"),
                "height_cm": parsed.get("height_cm"),
                "diameter_cm": parsed.get("diameter_cm"),
                "area_m2": parsed.get("area_m2"),
                "perimeter_m": parsed.get("perimeter_m"),
            }
            meta.update(
                {
                    "preparse_spec_text": spec_text,
                    "preparse_spec_hash": spec_hash,
                    "preparse_parser_version": PARSER_VERSION,
                    "preparse_dimensions": _json_safe(dims),
                    "preparse_tokens": list(parsed.get("tokens") or []),
                    "preparse_saved_at": _utcnow().isoformat(),
                    "preparse_saved_by": (requested_by or meta.get("requested_by") or None),
                }
            )
            r.metadata_json = meta
            saved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_id": getattr(r, "id", None), "sku_code": getattr(r, "erp_sku_barcode", None), "error": str(exc)})
    db.commit()
    return {"scanned": scanned, "saved": saved, "skipped_same_hash": skipped_same_hash, "errors": errors}


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


def bind_sku_master_by_model(
    db: Session,
    *,
    model_id: str,
    sku_master_ids: List[str],
    requested_by: Optional[str],
) -> Dict[str, Any]:
    version = _get_published_standard_version_for_model_id(db, model_id)
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

    for sid in sku_master_ids:
        row = by_id.get(sid)
        if not row:
            errors.append({"sku_master_id": sid, "error": "sku_master not found"})
            continue
        sku = (row.erp_sku_barcode or "").strip()
        if not sku:
            skipped_missing_barcode += 1
            continue
        if product_model_service.get_active_sku_binding(db, sku):
            skipped_already_bound += 1
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
                    "binding_method": "manual_by_model",
                    "skip_prefix_check": True,
                },
            )
            bound_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_master_id": row.id, "sku_code": sku, "error": str(exc)})

    return {
        "total_selected": total_selected,
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "skipped_missing_barcode": skipped_missing_barcode,
        "errors": errors,
    }


def auto_bind_preview(db: Session, *, limit: int, scan_limit: int = 50000) -> Dict[str, Any]:
    limit = max(min(int(limit or 200), 2000), 1)
    scan_limit = max(min(int(scan_limit or 50000), 500000), 100)

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
    for m, v in rows:
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
    rows = q.limit(scan_limit).all()

    total_unbound = q.count()
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
        hint = meta.get("model_code_hint_shipment") or meta.get("model_code_hint_erp")
        if not hint:
            # Fallback: compute from current spec_text (so older imported rows can still be auto-bound)
            hint = _extract_model_code_hint(spec_for_match)
        hint = (str(hint).strip().upper()) if hint else ""
        match_method = None
        matched_keyword = None
        model = None
        version = None

        if hint:
            version = product_model_service.get_latest_published_standard_version_for_model_code(db, hint)
            if version:
                model = db.get(models.ProductModel, version.model_id)
                if model and not model.is_archived:
                    match_method = "model_code_hint"

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
        try:
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
                    "skip_prefix_check": True,
                },
            )
            bound_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"sku_master_id": it.get("sku_master_id"), "sku_code": sku, "error": str(exc)})

    # return a fresh preview after binding
    preview_after = auto_bind_preview(db, limit=limit)
    return {
        "preview": preview_after,
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "errors": errors,
    }


