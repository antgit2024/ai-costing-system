"""Map a Jackyun ``wms.order.query-info(.page.v2)`` row to ``shipment_lines``.

We DO NOT call the upstream here. Mappers are pure: payload in, ORM rows out
(plus side-effects on the session). This keeps them easy to unit test.

Strategy:
- Each Jackyun shipment header contains a ``goodsDetail[]`` array. We create
  one ``ShipmentLine`` per detail row, attached to a single ``ShipmentImportBatch``.
- ``external_line_key_hash`` keeps existing dedupe semantics (used by the xlsx
  import path too).
- All upstream-only fields are stashed in ``raw_row_json`` for future replay.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from ....planner import models as planner_models
from ....planner.services import sku_master_service


# Jackyun upstream serializes ALL timestamps in Asia/Shanghai (no tz suffix in
# the JSON payload). We normalize them to UTC for storage so the rest of the
# system can treat ShipmentLine timestamps uniformly.
_BEIJING_TZ = timezone(timedelta(hours=8))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse a Jackyun upstream timestamp (Beijing-time string) to a
    timezone-aware UTC datetime.

    Historical bug (fixed 2026-05-07): the original implementation tagged the
    parsed datetime with ``tzinfo=timezone.utc``, effectively storing Beijing
    timestamps as if they were already UTC. Frontends then re-applied a +8h
    Asia/Shanghai render, so every Jackyun row showed up 8 hours late
    (e.g. an order placed at 16:16 Beijing displayed as 00:16 next day).
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            # Treat the upstream string as Beijing local, convert to UTC.
            return dt.replace(tzinfo=_BEIJING_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()  # noqa: S324 - non-crypto idempotency key


def _line_key(*, source_system: str, external_id: str, external_line_id: Optional[str]) -> str:
    return _hash(f"{source_system}|{external_id}|{external_line_id or ''}")


def get_or_create_jackyun_batch(
    db: Session, *, sync_run_id: str, file_name: Optional[str] = None
) -> planner_models.ShipmentImportBatch:
    """Reuse one ShipmentImportBatch per sync run for traceability.

    Status policy
    -------------
    Created as ``queued`` (not ``processing``) so ``shipment_import_worker``
    will pick it up and run the shared finalize/parse pipeline (BOM snapshots,
    exception queue, model binding). Without this, Jackyun-imported lines
    would sit in ``shipment_lines`` un-parsed and invisible in the
    ``/costing/shipments/ops`` exception queue.

    The ``processor`` marker tells the worker to dispatch to
    ``shipment_import_service.process_existing_shipment_lines`` (lines are
    already in DB, no Excel preview cache needed) instead of the default
    Excel-based ``execute_shipment_xlsx_from_preview`` entry point.
    """

    file_hash = f"jackyun-sync:{sync_run_id}"
    existing = (
        db.query(planner_models.ShipmentImportBatch)
        .filter(planner_models.ShipmentImportBatch.file_hash == file_hash)
        .one_or_none()
    )
    if existing is not None:
        return existing
    batch = planner_models.ShipmentImportBatch(
        id=str(uuid.uuid4()),
        file_name=file_name or f"jackyun-sync-{sync_run_id}.json",
        file_hash=file_hash,
        export_date=_utcnow().strftime("%Y-%m-%d"),
        requested_by="jackyun-sync",
        status="queued",
        result_json={
            "source_system": "jackyun",
            "sync_run_id": sync_run_id,
            "processor": "jackyun_existing_lines",
        },
    )
    db.add(batch)
    db.flush()
    return batch


def upsert_shipment_from_payload(
    db: Session,
    *,
    payload: Dict[str, Any],
    batch: planner_models.ShipmentImportBatch,
    source_payload_id: Optional[str] = None,
    source_system: str = "jackyun",
) -> Tuple[List[planner_models.ShipmentLine], int, int]:
    """Upsert all detail rows for one Jackyun shipment header.

    Returns (rows, inserted_count, updated_count).
    """

    order_no = (payload.get("orderNo") or "").strip()
    if not order_no:
        return [], 0, 0

    erp_order_no = (payload.get("erporderNo") or "").strip() or None
    plat_order_no = (payload.get("platOrderNo") or "").strip() or None
    channel = (payload.get("shopName") or payload.get("ownerName") or "").strip() or None
    sent_at = _parse_dt(payload.get("sendTime"))
    # Per Jackyun API doc (wms.order.query-info.page.v2), ``sendTime`` is the
    # canonical "发货时间" (warehouse-out timestamp). The frontend column is
    # also labeled 发货时间 so operators can reconcile against the ERP
    # directly. We use sendTime as the primary anchor for ``completed_at``.
    #
    # ``finishTime`` is NOT a documented field — the field we briefly tried
    # before that name does not exist in the v2 schema.
    #
    # Fallback cascade for orders that have not yet shipped (so sendTime is
    # null): payTime -> orderTime -> gmtCreate -> sync time. ``completed_at``
    # must never be NULL or downstream listing/sorting/snapshot retry sweep
    # all silently break (Issue 0.0 / 0.0b / 0.0c in known_issues.md).
    # ``completed_at_source`` records which level was used so the UI / reports
    # can highlight pre-shipment rows.
    completed_at = None
    completed_at_source = "fallback_sync_time"
    for key, source in (
        ("sendTime", "upstream_send"),
        ("payTime", "upstream_pay"),
        ("orderTime", "upstream_order"),
        ("gmtCreate", "upstream_gmt_create"),
    ):
        dt = _parse_dt(payload.get(key))
        if dt is not None:
            completed_at = dt
            completed_at_source = source
            break
    if completed_at is None:
        completed_at = _utcnow()
        completed_at_source = "fallback_sync_time"
    logistic_no = (payload.get("logisticNo") or "").strip() or None
    logistic_name = (payload.get("logisticName") or "").strip() or None
    warehouse_code = (payload.get("warehouseCode") or "").strip() or None
    warehouse_name = (payload.get("warehouseName") or "").strip() or None
    seller_memo = payload.get("sellerMemo") or None
    buyer_memo = payload.get("buyerMemo") or None
    flag_names = payload.get("flagNames") or None

    # Jackyun v2 header extensions (migration 0036).
    # Doc: https://open.jackyun.com/developer/apidocinfo.html?id=wms.order.query-info.page.v2
    # NOTE: ``LogisticCode`` is upper-camel in the official spec (verified by
    #       sample payload provided 2026-05-07). All other keys are lowerCamel.
    order_status_name = (payload.get("orderStatusName") or "").strip() or None
    logistic_type_name = (payload.get("logisticTypeName") or "").strip() or None
    logistic_code = (payload.get("LogisticCode") or payload.get("logisticCode") or "").strip() or None
    wave_no = (payload.get("waveNo") or "").strip() or None
    customer_name = (payload.get("customerName") or "").strip() or None
    picker = (payload.get("picker") or "").strip() or None
    packer = (payload.get("packer") or "").strip() or None
    checker = (payload.get("checker") or "").strip() or None
    check_started_at = _parse_dt(payload.get("checkStartTime"))
    paid_at = _parse_dt(payload.get("payTime"))
    ordered_at = _parse_dt(payload.get("orderTime"))
    trade_type_raw = payload.get("tradeType")
    try:
        trade_type = int(trade_type_raw) if trade_type_raw not in (None, "") else None
    except (TypeError, ValueError):
        trade_type = None
    trade_type_msg = (payload.get("tradeTypeMsg") or "").strip() or None

    details: Iterable[Dict[str, Any]] = payload.get("goodsDetail") or []
    rows: List[planner_models.ShipmentLine] = []
    inserted = 0
    updated = 0
    for idx, det in enumerate(details):
        detail_id = (det.get("detailId") or det.get("outDetailId") or f"{order_no}#{idx}").strip()
        external_line_key_hash = _line_key(
            source_system=source_system, external_id=order_no, external_line_id=detail_id
        )
        line = (
            db.query(planner_models.ShipmentLine)
            .filter(planner_models.ShipmentLine.external_line_key_hash == external_line_key_hash)
            .one_or_none()
        )
        sku_code = (det.get("skuBarcode") or det.get("outSkuCode") or "").strip() or None
        spec_text = det.get("tradeSpec") or det.get("skuName") or det.get("tradeName")
        qty = _to_decimal(det.get("sellCount") or det.get("actualCount"))
        revenue = _to_decimal(det.get("sellTotal"))

        # Jackyun v2 goodsDetail extensions (migration 0036).
        unit_price = _to_decimal(det.get("sellPrice"))
        unit_of_measure = (det.get("unit") or "").strip() or None
        category_name = (det.get("cateName") or "").strip() or None
        goods_name = (det.get("goodsName") or "").strip() or None
        goods_no = (det.get("goodsNo") or "").strip() or None
        # ``isGift`` upstream is 0/1 (sometimes "0"/"1"). Treat any truthy
        # numeric/string as gift; never write False on missing — leave NULL
        # so reports can distinguish "not a gift" vs "unknown legacy row".
        is_gift_raw = det.get("isGift")
        if is_gift_raw in (None, ""):
            is_gift = None
        else:
            try:
                is_gift = bool(int(str(is_gift_raw).strip()))
            except (TypeError, ValueError):
                is_gift = bool(is_gift_raw)
        actual_qty = _to_decimal(det.get("actualCount"))

        defaults = dict(
            batch_id=batch.id,
            row_index=idx + 1,
            shipment_no=order_no,
            order_no=plat_order_no or order_no,
            product_link_id=str(det.get("tradeGoodsno") or "")[:255] or None,
            completed_at=completed_at,
            channel=channel,
            sku_code=sku_code,
            spec_text=spec_text,
            qty=qty,
            revenue_amount=revenue,
            external_line_key_hash=external_line_key_hash,
            tag=flag_names,
            source_system=source_system,
            source_record_id=order_no,
            source_line_id=detail_id,
            source_payload_id=source_payload_id,
            erp_order_no=erp_order_no,
            platform_order_no=plat_order_no,
            sent_at=sent_at,
            logistic_no=logistic_no,
            logistic_name=logistic_name,
            warehouse_code=warehouse_code,
            warehouse_name=warehouse_name,
            seller_memo=seller_memo,
            buyer_memo=buyer_memo,
            order_status_name=order_status_name,
            logistic_type_name=logistic_type_name,
            logistic_code=logistic_code,
            wave_no=wave_no,
            customer_name=customer_name,
            picker=picker,
            packer=packer,
            checker=checker,
            check_started_at=check_started_at,
            paid_at=paid_at,
            ordered_at=ordered_at,
            trade_type=trade_type,
            trade_type_msg=trade_type_msg,
            unit_price=unit_price,
            unit_of_measure=unit_of_measure,
            category_name=category_name,
            goods_name=goods_name,
            goods_no=goods_no,
            is_gift=is_gift,
            actual_qty=actual_qty,
            raw_row_json={"shipment": payload, "detail": det},
        )
        if line is None:
            line = planner_models.ShipmentLine(id=str(uuid.uuid4()), **defaults)
            db.add(line)
            inserted += 1
        else:
            for key, value in defaults.items():
                setattr(line, key, value)
            updated += 1

        # 商家编码（吉客云 detail.tradeGoodsno）：自动匹配引擎的 P0 锚点。
        # 写到 line.metadata.shop_spec_code（标准协议字段，与 Excel 路径对齐），
        # 后续 _finalize_shipment_line 会读这个字段并下沉到 SkuMaster.metadata。
        trade_goodsno = (det.get("tradeGoodsno") or det.get("tradeGoodsNo") or "").strip() or None

        # Tag completed_at provenance so analytics / financial audits can
        # opt out of fallback rows. Always overwrite (idempotent on resync).
        meta = dict(line.metadata_json or {})
        meta["completed_at_source"] = completed_at_source
        if trade_goodsno:
            meta["shop_spec_code"] = trade_goodsno
        line.metadata_json = meta

        rows.append(line)

        # Belt-and-suspenders: ensure a SkuMaster exists immediately, even
        # before the worker picks the batch up. The worker will call this
        # again during finalize - ensure_from_shipment is idempotent
        # (just refreshes _shipment_seen metadata for existing rows).
        # Reasons for doing it here:
        #   1. Operators see new SKUs in the SKU master list right after
        #      sync, without waiting for the worker poll cycle.
        #   2. If the worker dies / lags, governance-status transitions
        #      (Sprint 2) still have a SkuMaster row to attach to.
        if sku_code:
            try:
                sku_master_service.ensure_from_shipment(
                    db,
                    erp_sku_barcode=sku_code,
                    spec_text=spec_text,
                    channel=channel,
                    metadata={
                        "source": "jackyun_autobackfill",
                        "batch_id": batch.id,
                        "shipment_import_batch_id": batch.id,
                        "shipment_line_id": line.id,
                        "shipment_no": order_no,
                        "source_system": source_system,
                        "source_record_id": order_no,
                        "source_line_id": detail_id,
                        "shop_spec_code": trade_goodsno,
                    },
                )
            except Exception:
                # Per-line ensure failures must NOT abort the whole sync;
                # the worker's ensure_from_shipment retry will catch it.
                pass

    if inserted:
        batch.inserted_rows = (batch.inserted_rows or 0) + inserted
    if updated:
        # We don't have a dedicated updated_rows column on ShipmentImportBatch,
        # so log it under result_json.
        result = dict(batch.result_json or {})
        result["updated_rows"] = (result.get("updated_rows") or 0) + updated
        batch.result_json = result
    batch.total_rows = (batch.total_rows or 0) + len(rows)
    return rows, inserted, updated
