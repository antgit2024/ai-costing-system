from __future__ import annotations

import hashlib
import io
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
    preparse_state: Optional[str] = None,
    include_terms: Optional[str] = None,
    exclude_terms: Optional[str] = None,
    match_scope: Optional[str] = None,
    excluded_sku_master_ids: Optional[List[str]] = None,
    page: int,
    page_size: int,
    page_size_cap: int = 200,
    compute_total: bool = True,
    include_bindings: bool = True,
    include_parsed_fields: bool = True,
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
        q = q.filter(
            (models.SkuMaster.erp_sku_barcode.ilike(s))
            | (models.SkuMaster.product_name.ilike(s))
            | (models.SkuMaster.product_code.ilike(s))
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
    # server-side filters for tabs (avoid empty pages caused by client-side filtering)
    if spec_mismatch is True:
        q = q.filter(models.SkuMaster.metadata_json["spec_mismatch"].as_boolean() == True)  # noqa: E712
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
        _update_shipment_seen(existing, shipment_spec_text=spec_text, channel=channel, metadata=metadata)
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
                    # 2026 新规则：用于“前置绑定锚点/套装短码”
                    "shop_spec_code": metadata.get("shop_spec_code"),
                    # 维度：平台规格Id（网店）
                    "platform_sku_id": metadata.get("platform_sku_id"),
                }
            )
    row.metadata_json = meta


def _attach_parsed_fields(rows: List[models.SkuMaster]) -> None:
    """
    Attach parsed summary fields as dynamic attributes for Pydantic response.
    """
    for r in rows:
        meta = dict(getattr(r, "metadata_json", None) or {})
        # 商家编码 / 网店规格编码（用于 2026 新规则：渠道侧携带的预置编码，包含模型码/套装码等锚点）
        # 目前来源：ERP SKU 主档导入时写入 metadata_json.shop_spec_code（同时也会写 shop_sku_mappings.shop_spec_code）
        r.shop_spec_code = meta.get("shop_spec_code")
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
            # already aligned to the target published version
            skipped_already_bound += 1
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
            # Record binding metadata on sku_master for downstream "spec-matching" anchor-change detection.
            meta = dict(getattr(row, "metadata_json", None) or {})
            meta.update(
                {
                    "model_bound_at": now_iso,
                    "model_bound_by": (requested_by or meta.get("requested_by") or None),
                    "model_binding_method": "manual_by_model_rebind" if allow_rebind else "manual_by_model",
                    "binding_validation_state": "sampled" if norm_spec else "no_shipment_sample",
                }
            )
            row.metadata_json = meta
            # auto preparse (from latest shipment spec sample)
            if norm_spec:
                try:
                    _apply_preparse_no_commit(db, sku_master_row=row, spec_text=norm_spec, requested_by=requested_by)
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


def _mismatch_warnings_by_keywords(*, sample_text: str, sku_spec_text: Optional[str], product_name: Optional[str], target_label: str) -> List[str]:
    """
    Soft guardrail: warn when shipment sample keywords strongly suggest a different category than the chosen target.
    This is NOT a hard error (users may intentionally map across categories).
    """
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
) -> Dict[str, Any]:
    """
    Bulk bind for manual workbench: bind *unbound* sku masters matched by filters.
    Designed for UI "implicit select all across pages", with an exclusion list.
    """
    version = _get_published_standard_version_for_model_id(db, model_id)
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
            meta = dict(getattr(row, "metadata_json", None) or {})
            meta.update(
                {
                    "model_bound_at": now_iso,
                    "model_bound_by": (requested_by or meta.get("requested_by") or None),
                    "model_binding_method": "manual_by_model_bulk_rebind" if allow_rebind else "manual_by_model_bulk",
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
    preview_after = auto_bind_preview(db, limit=limit, scan_limit=scan_limit)
    return {
        "preview": preview_after,
        "bound_count": bound_count,
        "skipped_already_bound": skipped_already_bound,
        "errors": errors,
    }


