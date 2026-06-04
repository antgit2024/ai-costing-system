"""Jackyun → ai-costing 售后单 mapper.

Translates ``omsapi-business.refund.listrefund`` payloads (one record per
network refund/after-sales order, with N product lines) into N rows of
``after_sales_lines`` — one row per product, mirroring how the Excel
import service stores rows.

Two non-obvious behaviors documented here so the next maintainer doesn't
have to re-derive them:

1. **Excel → Jackyun supersession** (per user decision 2026-05-12):
   When a Jackyun refund arrives for an ``after_sales_no`` that already
   exists in the table from an Excel upload (``source_system != 'jackyun'``),
   we DO NOT delete the Excel row. We tag it ``superseded_by_jackyun`` +
   write a metadata pointer to the new Jackyun line. Audit-friendly,
   reversible, and analytics queries can filter on the tag.

2. **best-effort ``erp_order_no`` enrichment**:
   Jackyun listrefund only returns ``platOrderNo`` (taobao/tmall order
   id); the ERP order id (吉客云 erpOrderNo, what 商家后台 uses) is NOT
   in the response. We left-join ``shipment_lines.platform_order_no`` to
   resolve it. If the matching shipment hasn't synced yet, the field
   stays null and the analytics_service join still works on
   ``platform_order_no``.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ....planner import models as planner_models


REFUND_SOURCE_SYSTEM = "jackyun"

# `tradeAfterOnlineDTO` redacts customer PII as e.g.
#   "~王**~/tb/~1~~"   (name)
#   "~***********~/tb/~1~~"   (mobile)
#   "~东**镇钱湖人家**幢**单元***~/tb/~1~~"   (address)
# This regex strips the outer ``~...~/tb/~N~~`` wrapper but keeps the masked
# middle (so 王** stays 王**). Idempotent — non-wrapped values pass through.
_REDACTION_WRAPPER_RE = re.compile(r"^~(.*?)~/tb/~\d+~~$")

# Map upstream refund/after-sales lifecycle codes to a coarse internal status.
# Built from real responses on 2026-05-12 (``refundStatus`` / ``orderStatus``).
# Anything not in this map flows through verbatim — UI shows ``status_name``
# (the upstream-provided ``refundStatusExplain``) so users see the right
# Chinese label even when we don't know the canonical code yet.
_REFUND_STATUS_NORMALIZED = {
    "SUCCESS": "success",
    "WAIT_SELLER_AGREE": "pending",
    "WAIT_BUYER_RETURN_GOODS": "pending",
    "WAIT_SELLER_CONFIRM_GOODS": "pending",
    "SELLER_REFUSE_BUYER": "rejected",
    "CLOSED": "closed",
    "REFUND_CLOSED": "closed",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_jackyun_dt(value: Any) -> Optional[datetime]:
    """Parse Jackyun's ``YYYY-MM-DD HH:MM:SS`` (Shanghai local) into a naive datetime.

    Stores naive timestamps because the rest of after_sales_lines schema is
    naive (TimestampMixin uses naive UTC). Caller must remember Jackyun
    timestamps are Asia/Shanghai; analytics_service already treats them as
    Asia/Shanghai for "occurred today" filters.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    s = str(value).strip()
    if not s or s == "-":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce Jackyun's BigDecimal field to Python Decimal (or None)."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _strip_redaction(value: Any) -> Optional[str]:
    """Strip the ``~...~/tb/~N~~`` wrapper from PII-masked Jackyun fields.

    Returns the inner masked string (e.g. ``"王**"``) so analytics still
    works for "did this customer return again?" without leaking the
    wrapper noise into UI tooltips.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _REDACTION_WRAPPER_RE.match(s)
    return m.group(1) if m else s


def _line_key_hash(*, trade_after_online_id: str, after_sub_trade_id: str) -> str:
    """SHA1(``jackyun|{header_id}|{line_id}``) — globally unique per refund line.

    Using SHA1 (not SHA256) to match the convention in
    ``after_sales_import_service._sha1_text``. Collision risk is irrelevant
    given how short the input space is.
    """
    raw = f"{REFUND_SOURCE_SYSTEM}|{trade_after_online_id}|{after_sub_trade_id}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324


def _lookup_erp_order_no(db: Session, *, plat_order_no: Optional[str]) -> Optional[str]:
    """Best-effort: find the ERP order number for a given platform order id.

    Reads ``shipment_lines.platform_order_no``. Returns None if either the
    shipment hasn't synced yet or the platform order maps to multiple ERP
    orders (we refuse to guess).
    """
    if not plat_order_no:
        return None
    row = (
        db.query(planner_models.ShipmentLine.erp_order_no)
        .filter(
            planner_models.ShipmentLine.platform_order_no == str(plat_order_no).strip(),
            planner_models.ShipmentLine.erp_order_no.isnot(None),
            planner_models.ShipmentLine.is_archived.is_(False),
        )
        .limit(2)
        .all()
    )
    if len(row) != 1:
        return None
    return row[0][0]


def get_or_create_jackyun_refund_batch(
    db: Session,
    *,
    sync_run_id: str,
    file_name: Optional[str] = None,
) -> planner_models.AfterSalesImportBatch:
    """Reuse one AfterSalesImportBatch per sync run.

    Mirrors ``shipment_mapper.get_or_create_jackyun_batch`` but for
    after-sales. Status starts at ``processing`` and is flipped to
    ``success`` by the caller (sync_jobs) when the run completes — there's
    no async worker for refunds so we don't need the queued/processing
    handoff that shipment uses.
    """
    file_hash = f"jackyun-refund-sync:{sync_run_id}"
    existing = (
        db.query(planner_models.AfterSalesImportBatch)
        .filter(planner_models.AfterSalesImportBatch.file_hash == file_hash)
        .one_or_none()
    )
    if existing is not None:
        return existing
    batch = planner_models.AfterSalesImportBatch(
        id=str(uuid.uuid4()),
        file_name=file_name or f"jackyun-refund-sync-{sync_run_id}.json",
        file_hash=file_hash,
        export_date=_utcnow().strftime("%Y-%m-%d"),
        requested_by="jackyun-refund-sync",
        status="processing",
        result_json={
            "source_system": REFUND_SOURCE_SYSTEM,
            "sync_run_id": sync_run_id,
            "schema_version": "jackyun.refund.v1",
        },
    )
    db.add(batch)
    db.flush()
    return batch


def _supersede_excel_rows(
    db: Session,
    *,
    after_sales_no: str,
    new_jackyun_line_id: str,
    new_jackyun_external_key: str,
) -> int:
    """Mark all non-jackyun rows for the same after_sales_no as superseded.

    Per user decision 2026-05-12 — API is authoritative. We tag (don't
    delete) so the audit trail and the original Excel-uploaded numbers
    stay queryable. Returns count of rows marked.
    """
    if not after_sales_no:
        return 0

    excel_rows = (
        db.query(planner_models.AfterSalesLine)
        .filter(
            planner_models.AfterSalesLine.after_sales_no == after_sales_no,
            planner_models.AfterSalesLine.is_archived.is_(False),
            (planner_models.AfterSalesLine.source_system != REFUND_SOURCE_SYSTEM)
            | (planner_models.AfterSalesLine.source_system.is_(None)),
        )
        .all()
    )
    n = 0
    now_iso = _utcnow().isoformat()
    for row in excel_rows:
        existing_tag = (row.tag or "").strip()
        # Idempotent: don't double-tag if already superseded.
        if "superseded_by_jackyun" in existing_tag:
            continue
        row.tag = (existing_tag + " superseded_by_jackyun").strip()
        meta = dict(row.metadata_json or {})
        meta["superseded_by_jackyun"] = {
            "at": now_iso,
            "jackyun_line_id": new_jackyun_line_id,
            "jackyun_external_key": new_jackyun_external_key,
        }
        row.metadata_json = meta
        flag_modified(row, "metadata_json")
        n += 1
    return n


def upsert_refund_from_payload(
    db: Session,
    *,
    record: Dict[str, Any],
    batch: planner_models.AfterSalesImportBatch,
    source_payload_id: Optional[str] = None,
) -> Tuple[List[planner_models.AfterSalesLine], int, int, int]:
    """Upsert one Jackyun refund record into ``after_sales_lines``.

    ``record`` shape (from ``iter_refunds``):
        {
          "tradeAfterOnlineDTO":          {... header ...},
          "tradeAfterOnlineGoodsDTOList": [{...}, {...}, ...],
        }

    Returns ``(rows, inserted_count, updated_count, superseded_excel_count)``.
    """
    header = record.get("tradeAfterOnlineDTO") or {}
    lines = record.get("tradeAfterOnlineGoodsDTOList") or []

    after_sales_no = (header.get("refundNo") or "").strip()
    if not after_sales_no:
        # Without refundNo we cannot dedupe or supersede; surface to dead-letter
        # in the caller (sync_jobs) instead of silently dropping.
        raise ValueError("refund record missing refundNo")

    trade_after_online_id = str(header.get("tradeAfterOnlineId") or "").strip()
    if not trade_after_online_id:
        raise ValueError(f"refundNo={after_sales_no} missing tradeAfterOnlineId")

    plat_order_no = (header.get("platOrderNo") or "").strip() or None
    erp_order_no = _lookup_erp_order_no(db, plat_order_no=plat_order_no)
    occurred_at = _parse_jackyun_dt(header.get("refundTimeCreate"))
    applied_at = _parse_jackyun_dt(header.get("gmtCreate")) or occurred_at
    refund_status = (header.get("refundStatus") or "").strip() or None
    status_normalized = _REFUND_STATUS_NORMALIZED.get(refund_status, refund_status)
    status_name = (header.get("refundStatusExplain") or "").strip() or None
    channel = (header.get("shopName") or header.get("platName") or "").strip() or None
    warehouse_name = (header.get("warehouseName") or "").strip() or None
    reason = (header.get("reason") or header.get("refundDesc") or "").strip() or None

    # Header-level numbers go into metadata so per-line rows still sum
    # correctly (we don't want every line to look like the full refund).
    header_meta = {
        "refund_amount_total": header.get("refundAmount"),
        "plat_refund_amount": header.get("platRefundAmount"),
        "has_goods_return": header.get("hasGoodsReturn"),
        "refund_type": header.get("refundType"),
        "refund_phase": header.get("refundPhase"),
        "refund_phase_explain": header.get("refundPhaseExplain"),
        "cur_status": header.get("curStatus"),
        "cur_status_explain": header.get("curStatusExplain"),
        "order_status": header.get("orderStatus"),
        "order_status_explain": header.get("orderStatusExplain"),
        "goods_status": header.get("goodsStatus"),
        "goods_status_explain": header.get("goodsStatusExplain"),
        "logistic_name": header.get("logisticName"),
        "main_postid": header.get("mainPostid"),
        "sys_flag_ids": header.get("sysFlagIds"),
        "shop_id": header.get("shopId"),
        "plat_id": header.get("platId"),
        "plat_name": header.get("platName"),
        "shop_name": header.get("shopName"),
        "refund_success_time": header.get("refundSuccessTime"),
        "refund_time_modified": header.get("refundTimeModified"),
        "plat_order_create_time": header.get("platOrderCreateTime"),
        "gmt_modified": header.get("gmtModified"),
        # PII-stripped customer / address pieces (kept for ops debugging only —
        # never surfaced in analytics aggregates).
        "customer_name": _strip_redaction(header.get("customerName")) or _strip_redaction(header.get("name")),
        "customer_account": header.get("customerAccount"),
        "buyer_memo": header.get("buyerMemo") or None,
        "seller_memo": header.get("sellerMemo") or None,
        "address_province": header.get("province"),
        "address_city": header.get("city"),
        "address_district": header.get("district"),
    }
    # Drop empty/None entries to keep metadata small + greppable.
    header_meta = {k: v for k, v in header_meta.items() if v not in (None, "", "-")}

    rows: List[planner_models.AfterSalesLine] = []
    inserted = 0
    updated = 0
    superseded = 0

    for line_idx, ln in enumerate(lines):
        if not isinstance(ln, dict):
            continue
        after_sub_trade_id = str(ln.get("afterSubTradeId") or "").strip()
        if not after_sub_trade_id:
            # Synthetic id so dedupe key stays stable even if upstream omits it
            # (rare — observed only for very old records).
            after_sub_trade_id = f"_synth_{trade_after_online_id}_{line_idx}"

        external_key = _line_key_hash(
            trade_after_online_id=trade_after_online_id,
            after_sub_trade_id=after_sub_trade_id,
        )

        # Map to AfterSalesLine columns.
        product_code = (ln.get("outerId") or "").strip() or None  # 商家编码
        product_link_id = (ln.get("platSkuId") or ln.get("platGoodsId") or "").strip() or None
        product_name = (ln.get("goodsName") or ln.get("tradeGoodsName") or "").strip() or None
        spec_text = (ln.get("specName") or ln.get("tradeGoodsSpec") or "").strip() or None
        unit = (ln.get("unit") or "").strip() or None
        sku_code = (ln.get("barcode") or "").strip() or None
        sale_unit_price = _to_decimal(ln.get("price"))
        return_qty = _to_decimal(ln.get("sellCount"))
        actual_return_qty = _to_decimal(ln.get("returnCount")) or return_qty
        # Per-line refund amount: prefer ``refundFee`` if present (actual
        # refund booked by ERP), else ``sellTotal`` (gross order line value).
        refund_fee = _to_decimal(ln.get("refundFee"))
        sell_total = _to_decimal(ln.get("sellTotal"))
        refund_amount = refund_fee if refund_fee and refund_fee > 0 else sell_total
        allocated_refund = refund_fee or sell_total

        line_meta = {
            **header_meta,
            "outer_sku_id": ln.get("outerSkuId"),
            "plat_sku_id": ln.get("platSkuId"),
            "plat_goods_id": ln.get("platGoodsId"),
            "goods_id": ln.get("goodsId"),
            "goods_no": ln.get("goodsNo"),
            "spec_id": ln.get("specId"),
            "trade_goods_name": ln.get("tradeGoodsName"),
            "trade_goods_spec": ln.get("tradeGoodsSpec"),
            "discount_fee": ln.get("discountFee"),
            "should_return_fee": ln.get("shouldReturnFee"),
            "return_fee": ln.get("returnFee"),
            "send_count": ln.get("sendCount"),
            "send_fee": ln.get("sendFee"),
            "is_fit": ln.get("isFit"),
            "is_gift": ln.get("isGift"),
            "is_virtual": ln.get("isVirtual"),
            "line_has_goods_return": ln.get("hasGoodsReturn"),
            "line_refund_phase": ln.get("refundPhase"),
            "line_type": ln.get("type"),
            "reason_desc": ln.get("reasonDesc"),
            "sub_plat_order_no": ln.get("subPlatOrderNo"),
            "source_trade_no": ln.get("sourceTradeNo"),
            "source_subtrade_no": ln.get("sourceSubtradeNo"),
            "plat_warehouse_code": ln.get("platWarehouseCode"),
            "schema_version": "jackyun.refund.v1",
        }
        line_meta = {k: v for k, v in line_meta.items() if v not in (None, "", "-")}

        existing = (
            db.query(planner_models.AfterSalesLine)
            .filter(planner_models.AfterSalesLine.external_line_key_hash == external_key)
            .one_or_none()
        )
        if existing is not None:
            # Update in place — Jackyun status can flip from pending → success
            # weeks later, and we want the latest state.
            existing.status = status_normalized
            existing.status_name = status_name
            existing.refund_amount = refund_amount
            existing.allocated_refund_amount = allocated_refund
            existing.return_qty = return_qty
            existing.actual_return_qty = actual_return_qty
            existing.warehouse_name = warehouse_name
            existing.reason = reason
            existing.erp_order_no = erp_order_no or existing.erp_order_no
            existing.platform_order_no = plat_order_no or existing.platform_order_no
            existing.applied_at = applied_at or existing.applied_at
            existing.occurred_at = occurred_at or existing.occurred_at
            existing.metadata_json = line_meta
            flag_modified(existing, "metadata_json")
            existing.raw_row_json = {"header": header, "line": ln}
            flag_modified(existing, "raw_row_json")
            existing.source_payload_id = source_payload_id or existing.source_payload_id
            rows.append(existing)
            updated += 1
            continue

        # Insert new
        new_line = planner_models.AfterSalesLine(
            id=str(uuid.uuid4()),
            batch_id=batch.id,
            row_index=line_idx,
            after_sales_no=after_sales_no,
            occurred_at=occurred_at,
            applied_at=applied_at,
            channel=channel,
            reason=reason,
            order_no=plat_order_no,  # legacy column kept aligned with platform_order_no
            product_link_id=product_link_id,
            product_code=product_code,
            product_name=product_name,
            spec_text=spec_text,
            unit=unit,
            sale_unit_price=sale_unit_price,
            return_qty=return_qty,
            actual_return_qty=actual_return_qty,
            refund_amount=refund_amount,
            allocated_refund_amount=allocated_refund,
            sku_code=sku_code,
            external_line_key_hash=external_key,
            tag=None,
            source_system=REFUND_SOURCE_SYSTEM,
            source_record_id=trade_after_online_id,
            source_line_id=after_sub_trade_id,
            source_payload_id=source_payload_id,
            erp_order_no=erp_order_no,
            platform_order_no=plat_order_no,
            warehouse_name=warehouse_name,
            status=status_normalized,
            status_name=status_name,
            raw_row_json={"header": header, "line": ln},
            metadata_json=line_meta,
        )
        db.add(new_line)
        db.flush()  # assign id for supersession metadata
        rows.append(new_line)
        inserted += 1

        # Supersede any pre-existing Excel rows for this after_sales_no.
        # Doing it AFTER insert so supersession metadata can point at the
        # canonical Jackyun row. Only run on insert (not update) to avoid
        # spamming the same supersession marker every nightly sync.
        superseded += _supersede_excel_rows(
            db,
            after_sales_no=after_sales_no,
            new_jackyun_line_id=new_line.id,
            new_jackyun_external_key=external_key,
        )

    return rows, inserted, updated, superseded
