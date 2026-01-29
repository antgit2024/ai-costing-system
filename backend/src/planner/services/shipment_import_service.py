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
from sqlalchemy import and_, func, or_
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
    required_fields = ["shipment_no", "completed_at", "channel", "sku_code", "qty"]
    missing_fields = [f for f in required_fields if not _has_any_header(headers, SHIPMENT_FIELD_ALIASES.get(f) or [])]
    if missing_fields:
        _warn("MISSING_HEADERS", missing_fields=missing_fields)

    normalized: List[Dict[str, Any]] = []
    for i, row in enumerate(rows[1:], start=2):
        row_list = list(row)
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
                "spec_text": spec_text,
                "qty": qty,
                "revenue_amount": revenue_amount,
                "raw_row": _json_safe(raw_row),
            }
        )
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
                # Bundle anchors for audits & analytics (Phase0).
                "bundle_template_id": (line.metadata_json or {}).get("bundle_template_id")
                if isinstance(line.metadata_json, dict)
                else None,
                "bundle_template_code": (line.metadata_json or {}).get("bundle_template_code")
                if isinstance(line.metadata_json, dict)
                else None,
                "bundle_preset_selector": (line.metadata_json or {}).get("bundle_preset_selector")
                if isinstance(line.metadata_json, dict)
                else None,
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
            shipment_no=shipment_no,
            order_no=payload.get("order_no"),
            product_link_id=payload.get("product_link_id"),
            completed_at=payload.get("completed_at"),
            channel=payload.get("channel"),
            sku_code=sku_code,
            spec_text=spec_text,
            spec_hash=_sha1_text(spec_text_norm) if spec_text_norm else None,
            qty=qty,
            revenue_amount=revenue_amount,
            external_line_key_hash=ext_hash,
            revision_group_hash=revision_group,
            revision_no=1,
            is_active=True,
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

        # Bundle anchor (Phase0): if SKU master has a bundle binding, carry it to shipment_lines metadata.
        # This enables bundle-level auditing & analytics without recomputing historical snapshots.
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
            # best-effort only; do not fail shipment import
            pass

        # SKU master autobackfill (MVP): if barcode not in sku_master, create minimal record for next imports.
        sku_master_service.ensure_from_shipment(
            db,
            erp_sku_barcode=sku_code or "",
            spec_text=spec_text,
            channel=payload.get("channel"),
            metadata={
                "source": "shipment_autobackfill",
                # keep keys aligned with sku_master_service._update_shipment_seen expectations
                "batch_id": batch.id,
                "shipment_import_batch_id": batch.id,
                "shipment_line_id": line.id,
                "shipment_no": shipment_no,
                "spec_hash": _sha1_text(spec_text_norm) if spec_text_norm else None,
                "shop_spec_code": payload.get("shop_spec_code"),
                "platform_sku_id": payload.get("platform_sku_id"),
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

        persist_snapshot = str(mode or "2026") != "2025"
        if persist_snapshot:
            existing_snapshot = (
                db.query(models.BomSnapshot)
                .filter(models.BomSnapshot.shipment_line_id == line.id)
                .first()
            )
            if not existing_snapshot:
                snap = _generate_bom_snapshot(db, batch=batch, line=line, persist_snapshot=True, mode=mode)
                if not snap:
                    batch.exception_rows += 1
        else:
            # 2025 mode: no per-line snapshots; still persist deduction artifacts
            _generate_bom_snapshot(db, batch=batch, line=line, persist_snapshot=False, mode=mode)

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
    mode: str = "2026",
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
    # Root-cause fix for slow queries:
    # - Avoid correlated scalar_subquery() per row
    # - Build ONE binding subquery and LEFT JOIN it on shipment_lines.sku_code
    m = models.SkuModelVersionMapping
    v = models.ProductModelVersion
    pm = models.ProductModel
    binding_sq = (
        db.query(
            m.sku_code.label("sku_code"),
            m.model_version_id.label("model_version_id"),
            pm.model_code.label("bound_model_code"),
            pm.model_name.label("bound_model_name"),
            v.version_label.label("bound_version_label"),
            func.nullif(
                func.upper(func.coalesce(v.metadata_json["bundle_preset_selector"].as_string(), "")),
                "",
            ).label("bundle_preset_selector"),
            func.row_number()
            .over(
                partition_by=m.sku_code,
                order_by=(m.updated_at.desc(), m.created_at.desc()),
            )
            .label("rn"),
        )
        .select_from(m)
        .join(v, v.id == m.model_version_id)
        .join(pm, pm.id == v.model_id)
        .filter(
            m.is_archived.is_(False),
            m.is_active.is_(True),
            v.is_archived.is_(False),
            pm.is_archived.is_(False),
        )
        .subquery()
    )

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
        binding_sq.c.model_version_id.label("bound_model_version_id"),
        binding_sq.c.bound_model_code.label("bound_model_code"),
        binding_sq.c.bound_model_name.label("bound_model_name"),
        binding_sq.c.bound_version_label.label("bound_version_label"),
        binding_sq.c.bundle_preset_selector.label("bundle_preset_selector"),
        )
        .outerjoin(
            binding_sq,
            and_(
                binding_sq.c.sku_code == models.ShipmentLine.sku_code,
                binding_sq.c.rn == 1,
            ),
        )
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

    # "疑似绑错" heuristic (SQL-side filter for pagination correctness).
    # NOTE: This is intentionally a SOFT guardrail; it may contain false positives.
    def _has_any(col, keys: List[str]):
        col2 = func.coalesce(col, "")
        return or_(*[col2.ilike(f"%{k}%") for k in (keys or []) if str(k).strip()])

    sample_siquan_dian = _has_any(models.ShipmentLine.spec_text, ["丝圈", "地垫"])
    sample_baozhen = _has_any(models.ShipmentLine.spec_text, ["抱枕", "枕套"])
    sample_ditan = _has_any(models.ShipmentLine.spec_text, ["地毯"])
    sample_zhuodian = _has_any(models.ShipmentLine.spec_text, ["桌垫"])
    sample_zhuangshihua = _has_any(models.ShipmentLine.spec_text, ["装饰画", "画框", "挂画"])
    sample_any = or_(sample_siquan_dian, sample_baozhen, sample_ditan, sample_zhuodian, sample_zhuangshihua)

    # Target hits: check both model_name and model_code (some users only remember codes)
    target_siquan_dian = or_(
        _has_any(binding_sq.c.bound_model_name, ["丝圈", "地垫"]),
        _has_any(binding_sq.c.bound_model_code, ["丝圈", "地垫"]),
    )
    target_baozhen = or_(
        _has_any(binding_sq.c.bound_model_name, ["抱枕", "枕套"]),
        _has_any(binding_sq.c.bound_model_code, ["抱枕", "枕套"]),
    )
    target_ditan = or_(_has_any(binding_sq.c.bound_model_name, ["地毯"]), _has_any(binding_sq.c.bound_model_code, ["地毯"]))
    target_zhuodian = or_(_has_any(binding_sq.c.bound_model_name, ["桌垫"]), _has_any(binding_sq.c.bound_model_code, ["桌垫"]))
    target_zhuangshihua = or_(
        _has_any(binding_sq.c.bound_model_name, ["装饰画", "画框", "挂画"]),
        _has_any(binding_sq.c.bound_model_code, ["装饰画", "画框", "挂画"]),
    )
    target_any = or_(target_siquan_dian, target_baozhen, target_ditan, target_zhuodian, target_zhuangshihua)

    has_target_binding = or_(
        binding_sq.c.bound_model_code.isnot(None),
        binding_sq.c.bound_model_name.isnot(None),
    )
    suspected_mismatch_pred = and_(
        has_target_binding,
        or_(
            and_(sample_siquan_dian, target_baozhen),
            and_(sample_baozhen, target_siquan_dian),
            and_(sample_zhuangshihua, target_baozhen),
            and_(sample_baozhen, target_zhuangshihua),
            and_(sample_zhuodian, target_baozhen),
            and_(sample_baozhen, target_zhuodian),
            and_(sample_ditan, target_baozhen),
            and_(sample_baozhen, target_ditan),
            # Softer case (align with sku-master preview): sample hits a category but target contains none.
            and_(sample_any, ~target_any),
        ),
    )

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
    if bound_model_code:
        pat = f"%{str(bound_model_code).strip()}%"
        q = q.filter(func.coalesce(binding_sq.c.bound_model_code, "").ilike(pat))
    if bound_version_label:
        vlab = str(bound_version_label).strip()
        if vlab:
            q = q.filter(binding_sq.c.bound_version_label == vlab)
    if bundle_preset_selector:
        sel = str(bundle_preset_selector).strip().upper()
        if sel:
            q = q.filter(binding_sq.c.bundle_preset_selector == sel)
    if bound_target_kind:
        k = str(bound_target_kind).strip().lower()
        if k in ("bundle", "bundles"):
            q = q.filter(or_(binding_sq.c.bound_model_code.ilike("B-%"), binding_sq.c.bound_model_code.ilike("Z-%")))
        elif k in ("model", "models", "standard"):
            q = q.filter(
                and_(
                    binding_sq.c.bound_model_code.isnot(None),
                    ~binding_sq.c.bound_model_code.ilike("B-%"),
                    ~binding_sq.c.bound_model_code.ilike("Z-%"),
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
            binding_sq.c.model_version_id.isnot(None),
            func.nullif(func.trim(func.coalesce(models.ShipmentLine.sku_code, "")), "").isnot(None),
            func.nullif(func.trim(func.coalesce(models.ShipmentLine.spec_text, "")), "").isnot(None),
        )
    if need_rebuild_snapshot is True:
        # “需重建”口径：已有快照（已处理），但快照记录的 model_version_id 与当前绑定不一致（包含“已清空绑定但有快照”）
        q = q.filter(
            has_bom,
            func.coalesce(binding_sq.c.model_version_id, "") != func.coalesce(latest_snapshot_model_version_id_sq, ""),
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
        shop_spec_code = (
            meta.get("shop_spec_code")
            # raw_row_json keys are normalized by _norm_header (often stripping trailing "(网店)" notes)
            or raw_row.get("规格编码")
            or raw_row.get("规格编码(网店)")
            or raw_row.get("商家编码")
            or raw_row.get("shop_spec_code")
            or raw_row.get("merchant_sku")
        )
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
                    mismatch_warnings = sku_master_service._mismatch_warnings_by_keywords(  # noqa: SLF001
                        sample_text=norm_spec,
                        sku_spec_text=None,
                        product_name=None,
                        target_label=target_label,
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
                "shop_spec_code": (str(shop_spec_code).strip() if shop_spec_code not in (None, "") else None),
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

