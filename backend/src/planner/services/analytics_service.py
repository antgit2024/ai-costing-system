from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from .. import models
from . import bom_generation_service, product_model_service


_BUNDLE_MODEL_CODE_RE = re.compile(r"^B-(?P<tpl>[A-Z0-9]{4})(?P<sel>[A-Z]{2})$", re.IGNORECASE)


def _not_snapshot_cleared_pred():
    # Cross-dialect safe: we store a non-empty ISO string in metadata_json["snapshot_cleared_at"] when cleared.
    return func.coalesce(models.ShipmentLine.metadata_json["snapshot_cleared_at"].as_string(), "") == ""


def _try_get_bundle_phrase_preset(db: Session, model_code: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    BundleAsModel display enrichment.

    For bundle model_code like "B-DB9EAE":
    - tpl_code: "DB9E"
    - selector: "AE"
    - phrase:  metadata.phrase_presets[*].phrase matched by selector
    """
    mc = (model_code or "").strip().upper()
    m = _BUNDLE_MODEL_CODE_RE.match(mc)
    if not m:
        return None, None, None
    tpl_code = str(m.group("tpl") or "").strip().upper()
    selector = str(m.group("sel") or "").strip().upper()
    if not tpl_code or not selector:
        return None, None, None

    tpl = (
        db.query(models.BundleTemplate)
        .filter(models.BundleTemplate.is_archived.is_(False), models.BundleTemplate.code == tpl_code)
        .first()
    )
    if not tpl:
        return tpl_code, selector, None

    meta = getattr(tpl, "metadata_json", {}) or {}
    presets = meta.get("phrase_presets") or []
    phrase: Optional[str] = None
    if isinstance(presets, list):
        for p in presets:
            if not isinstance(p, dict):
                continue
            sel = str(p.get("selector") or "").strip().upper()
            if sel == selector:
                raw = str(p.get("phrase") or "").strip()
                phrase = raw or None
                break
    return tpl_code, selector, phrase


def _utc_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _fmt_period_label(period_dt: Any, group_by: Literal["week", "month"]) -> str:
    """
    Format period label for dashboard:
    - week: YYYY-MM-DD~YYYY-MM-DD (Mon~Sun)
    - month: YYYY-MM
    """
    dt = period_dt
    if isinstance(dt, str):
        # try best-effort parse: "2026-01-05 00:00:00"
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return dt
    if isinstance(dt, date) and not isinstance(dt, datetime):
        start_date = dt
    elif isinstance(dt, datetime):
        start_date = _utc_date(dt)
    else:
        return str(period_dt)

    if group_by == "month":
        return start_date.strftime("%Y-%m")
    end_date = start_date + timedelta(days=6)
    return f"{start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}"


def _group_time_expr(db: Session, column, group_by: Literal["day", "month"]):
    dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
    if dialect == "postgresql":
        if group_by == "month":
            return func.date_trunc("month", column)
        return func.date_trunc("day", column)
    # sqlite / mysql fallback
    if group_by == "month":
        return func.strftime("%Y-%m-01", column)
    return func.date(column)


def _group_time_expr_dash(db: Session, column, group_by: Literal["week", "month"]):
    dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
    if dialect == "postgresql":
        if group_by == "month":
            return func.date_trunc("month", column)
        # week: date_trunc('week') => week start (Mon) in postgres
        return func.date_trunc("week", column)
    # sqlite / mysql fallback (best-effort)
    if group_by == "month":
        return func.strftime("%Y-%m-01", column)
    # week start (Mon) best-effort: date(column, 'weekday 1', '-7 days')
    return func.date(column, "weekday 1", "-7 days")


def after_sales_dashboard(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["week", "month"] = "week",
    channel: Optional[str] = None,
    top_n: int = 12,
    view: Literal["factory", "ops"] = "factory",
) -> Dict[str, Any]:
    """
    After-sales dashboard:
    - Denominator: shipments within [start, end) by completed_at.
    - Numerator: matched after-sales lines attributed to shipment period via strong keys:
      order_no + product_link_id + sku_code.
    - Amount/qty: prefer ERP-stable fields:
      returned_qty := coalesce(actual_return_qty, return_qty)
      refund_amount := coalesce(allocated_refund_amount, refund_amount)
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # -------------------------------
    # 运营看板（申请口径，全量，不做归因）
    # - 发货：shipment_lines.completed_at ∈ [start, end)
    # - 退货：after_sales_lines.applied_at/occurred_at ∈ [start, end)（不要求能匹配到发货行）
    # -------------------------------
    if view == "ops":
        ship_period_expr = _group_time_expr_dash(db, models.ShipmentLine.completed_at, group_by).label("period")
        applied_time_expr = func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at)
        ret_period_expr = _group_time_expr_dash(db, applied_time_expr, group_by).label("period")

        shipped_qty_sum = func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty")
        shipped_amount_sum = func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label("shipped_amount")
        returned_qty_sum = func.coalesce(
            func.sum(func.coalesce(models.AfterSalesLine.actual_return_qty, models.AfterSalesLine.return_qty)),
            0,
        ).label("returned_qty")
        refund_amount_sum = func.coalesce(
            func.sum(func.coalesce(models.AfterSalesLine.allocated_refund_amount, models.AfterSalesLine.refund_amount)),
            0,
        ).label("refund_amount")

        ship_total_q = db.query(shipped_qty_sum, shipped_amount_sum).filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
        if channel:
            ship_total_q = ship_total_q.filter(models.ShipmentLine.channel == channel)
        ship_total = ship_total_q.one()

        ret_total_q = db.query(returned_qty_sum, refund_amount_sum).filter(
            models.AfterSalesLine.is_archived.is_(False),
            applied_time_expr.isnot(None),
            applied_time_expr >= start,
            applied_time_expr < end,
        )
        if channel:
            ret_total_q = ret_total_q.filter(models.AfterSalesLine.channel == channel)
        ret_total = ret_total_q.one()

        shipped_qty_total = Decimal(str(ship_total.shipped_qty or 0))
        shipped_amount_total = Decimal(str(ship_total.shipped_amount or 0))
        returned_qty_total = Decimal(str(ret_total.returned_qty or 0))
        refund_amount_total = Decimal(str(ret_total.refund_amount or 0))
        return_rate_total = (returned_qty_total / shipped_qty_total) if shipped_qty_total > 0 else None
        refund_rate_total = (refund_amount_total / shipped_amount_total) if shipped_amount_total > 0 else None

        # series: merge shipments(completed_at) and after-sales(applied_at/occurred_at) into same week/month buckets
        ship_series_rows = (
            db.query(ship_period_expr, shipped_qty_sum, shipped_amount_sum)
            .filter(
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.completed_at >= start,
                models.ShipmentLine.completed_at < end,
                models.ShipmentLine.is_archived.is_(False),
            )
            .group_by(ship_period_expr)
            .order_by(ship_period_expr)
        )
        if channel:
            ship_series_rows = ship_series_rows.filter(models.ShipmentLine.channel == channel)
        ship_series_rows = ship_series_rows.all()

        ret_series_rows = (
            db.query(ret_period_expr, returned_qty_sum, refund_amount_sum)
            .filter(
                models.AfterSalesLine.is_archived.is_(False),
                applied_time_expr.isnot(None),
                applied_time_expr >= start,
                applied_time_expr < end,
            )
            .group_by(ret_period_expr)
            .order_by(ret_period_expr)
        )
        if channel:
            ret_series_rows = ret_series_rows.filter(models.AfterSalesLine.channel == channel)
        ret_series_rows = ret_series_rows.all()

        series_by_label: Dict[str, Dict[str, Any]] = {}
        for r in ship_series_rows:
            label = _fmt_period_label(r.period, group_by)
            series_by_label[label] = {
                "period": label,
                "shipped_qty": Decimal(str(r.shipped_qty or 0)),
                "shipped_amount": Decimal(str(r.shipped_amount or 0)),
                "returned_qty": Decimal("0"),
                "refund_amount": Decimal("0"),
                "return_rate": None,
                "refund_rate": None,
            }
        for r in ret_series_rows:
            label = _fmt_period_label(r.period, group_by)
            cur = series_by_label.get(label) or {
                "period": label,
                "shipped_qty": Decimal("0"),
                "shipped_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "refund_amount": Decimal("0"),
                "return_rate": None,
                "refund_rate": None,
            }
            cur["returned_qty"] = Decimal(str(r.returned_qty or 0))
            cur["refund_amount"] = Decimal(str(r.refund_amount or 0))
            series_by_label[label] = cur

        series: List[Dict[str, Any]] = []
        for label in sorted(series_by_label.keys()):
            cur = series_by_label[label]
            sq = Decimal(str(cur["shipped_qty"] or 0))
            sa = Decimal(str(cur["shipped_amount"] or 0))
            rq = Decimal(str(cur["returned_qty"] or 0))
            ra = Decimal(str(cur["refund_amount"] or 0))
            cur["return_rate"] = (rq / sq) if sq > 0 else None
            cur["refund_rate"] = (ra / sa) if sa > 0 else None
            series.append(cur)

        # top reasons (applied window, no attribution)
        reasons_q = db.query(
            models.AfterSalesLine.reason.label("reason"),
            returned_qty_sum,
            refund_amount_sum,
        ).filter(
            models.AfterSalesLine.is_archived.is_(False),
            applied_time_expr.isnot(None),
            applied_time_expr >= start,
            applied_time_expr < end,
        )
        if channel:
            reasons_q = reasons_q.filter(models.AfterSalesLine.channel == channel)
        reasons_q = reasons_q.group_by(models.AfterSalesLine.reason).order_by(returned_qty_sum.desc()).limit(top_n)
        reason_rows = reasons_q.all()
        top_reasons: List[Dict[str, Any]] = []
        total_rq = returned_qty_total
        total_ra = refund_amount_total
        for r in reason_rows:
            qty = Decimal(str(r.returned_qty or 0))
            amt = Decimal(str(r.refund_amount or 0))
            top_reasons.append(
                {
                    "reason": str(r.reason or "-"),
                    "returned_qty": qty,
                    "refund_amount": amt,
                    "share_returned_qty": (qty / total_rq) if total_rq > 0 else None,
                    "share_refund_amount": (amt / total_ra) if total_ra > 0 else None,
                }
            )

        # helper: build top list from shipped/returned maps
        def _merge_top_by_key(keys: List[str], shipped_map: Dict[str, Decimal], returned_map: Dict[str, Decimal]) -> List[Dict[str, Any]]:
            items: List[Dict[str, Any]] = []
            for k in keys:
                sq = shipped_map.get(k, Decimal("0"))
                rq = returned_map.get(k, Decimal("0"))
                items.append(
                    {
                        "key": k,
                        "shipped_qty": sq,
                        "returned_qty": rq,
                        "return_rate": (rq / sq) if sq > 0 else None,
                    }
                )
            items.sort(key=lambda x: (x["returned_qty"], x["shipped_qty"]), reverse=True)
            return items[:top_n]

        # top skus (shipments completed_at window vs after-sales applied window)
        ship_sku_rows = (
            db.query(models.ShipmentLine.sku_code.label("sku_code"), shipped_qty_sum)
            .filter(
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.completed_at >= start,
                models.ShipmentLine.completed_at < end,
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.sku_code.isnot(None),
            )
            .group_by(models.ShipmentLine.sku_code)
        )
        if channel:
            ship_sku_rows = ship_sku_rows.filter(models.ShipmentLine.channel == channel)
        ship_sku_rows = ship_sku_rows.all()
        shipped_by_sku: Dict[str, Decimal] = {str(r.sku_code): Decimal(str(r.shipped_qty or 0)) for r in ship_sku_rows}

        ret_sku_rows = (
            db.query(models.AfterSalesLine.sku_code.label("sku_code"), returned_qty_sum)
            .filter(
                models.AfterSalesLine.is_archived.is_(False),
                applied_time_expr.isnot(None),
                applied_time_expr >= start,
                applied_time_expr < end,
                models.AfterSalesLine.sku_code.isnot(None),
            )
            .group_by(models.AfterSalesLine.sku_code)
        )
        if channel:
            ret_sku_rows = ret_sku_rows.filter(models.AfterSalesLine.channel == channel)
        ret_sku_rows = ret_sku_rows.all()
        returned_by_sku: Dict[str, Decimal] = {str(r.sku_code): Decimal(str(r.returned_qty or 0)) for r in ret_sku_rows}

        sku_keys = list(set(list(shipped_by_sku.keys()) + list(returned_by_sku.keys())))
        merged_skus = _merge_top_by_key(sku_keys, shipped_by_sku, returned_by_sku)

        # most common spec_text for top skus (from after_sales within applied window)
        sku_spec_map: Dict[str, Optional[str]] = {}
        for item in merged_skus:
            sku = str(item["key"])
            spec_row = (
                db.query(models.AfterSalesLine.spec_text, func.count(models.AfterSalesLine.id).label("c"))
                .filter(
                    models.AfterSalesLine.is_archived.is_(False),
                    applied_time_expr.isnot(None),
                    applied_time_expr >= start,
                    applied_time_expr < end,
                    models.AfterSalesLine.sku_code == sku,
                    models.AfterSalesLine.spec_text.isnot(None),
                )
                .group_by(models.AfterSalesLine.spec_text)
                .order_by(func.count(models.AfterSalesLine.id).desc())
                .limit(1)
                .one_or_none()
            )
            sku_spec_map[sku] = (str(spec_row.spec_text) if spec_row and spec_row.spec_text else None)

        top_skus: List[Dict[str, Any]] = []
        for it in merged_skus:
            sku = str(it["key"])
            top_skus.append(
                {
                    "sku_code": sku,
                    "spec_text": sku_spec_map.get(sku),
                    "shipped_qty": it["shipped_qty"],
                    "returned_qty": it["returned_qty"],
                    "return_rate": it["return_rate"],
                }
            )

        # top links
        ship_link_rows = (
            db.query(models.ShipmentLine.product_link_id.label("product_link_id"), shipped_qty_sum)
            .filter(
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.completed_at >= start,
                models.ShipmentLine.completed_at < end,
                models.ShipmentLine.is_archived.is_(False),
                models.ShipmentLine.product_link_id.isnot(None),
            )
            .group_by(models.ShipmentLine.product_link_id)
        )
        if channel:
            ship_link_rows = ship_link_rows.filter(models.ShipmentLine.channel == channel)
        ship_link_rows = ship_link_rows.all()
        shipped_by_link: Dict[str, Decimal] = {str(r.product_link_id): Decimal(str(r.shipped_qty or 0)) for r in ship_link_rows}

        ret_link_rows = (
            db.query(models.AfterSalesLine.product_link_id.label("product_link_id"), returned_qty_sum)
            .filter(
                models.AfterSalesLine.is_archived.is_(False),
                applied_time_expr.isnot(None),
                applied_time_expr >= start,
                applied_time_expr < end,
                models.AfterSalesLine.product_link_id.isnot(None),
            )
            .group_by(models.AfterSalesLine.product_link_id)
        )
        if channel:
            ret_link_rows = ret_link_rows.filter(models.AfterSalesLine.channel == channel)
        ret_link_rows = ret_link_rows.all()
        returned_by_link: Dict[str, Decimal] = {str(r.product_link_id): Decimal(str(r.returned_qty or 0)) for r in ret_link_rows}

        link_keys = list(set(list(shipped_by_link.keys()) + list(returned_by_link.keys())))
        merged_links = _merge_top_by_key(link_keys, shipped_by_link, returned_by_link)

        link_spec_map: Dict[str, Optional[str]] = {}
        for item in merged_links:
            lid = str(item["key"])
            spec_row = (
                db.query(models.AfterSalesLine.spec_text, func.count(models.AfterSalesLine.id).label("c"))
                .filter(
                    models.AfterSalesLine.is_archived.is_(False),
                    applied_time_expr.isnot(None),
                    applied_time_expr >= start,
                    applied_time_expr < end,
                    models.AfterSalesLine.product_link_id == lid,
                    models.AfterSalesLine.spec_text.isnot(None),
                )
                .group_by(models.AfterSalesLine.spec_text)
                .order_by(func.count(models.AfterSalesLine.id).desc())
                .limit(1)
                .one_or_none()
            )
            link_spec_map[lid] = (str(spec_row.spec_text) if spec_row and spec_row.spec_text else None)

        top_links: List[Dict[str, Any]] = []
        for it in merged_links:
            lid = str(it["key"])
            top_links.append(
                {
                    "product_link_id": lid,
                    "spec_text": link_spec_map.get(lid),
                    "shipped_qty": it["shipped_qty"],
                    "returned_qty": it["returned_qty"],
                    "return_rate": it["return_rate"],
                }
            )

        # top models (shipments by model vs returns by model) - use sku->model mapping for both sides
        mapping_q_ship = (
            db.query(
                models.ProductModel.model_code.label("model_code"),
                models.ProductModel.model_name.label("model_name"),
                shipped_qty_sum,
            )
            .select_from(models.ShipmentLine)
            .join(
                models.SkuModelVersionMapping,
                and_(
                    models.SkuModelVersionMapping.is_archived.is_(False),
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.sku_code == models.ShipmentLine.sku_code,
                ),
            )
            .join(
                models.ProductModelVersion,
                and_(
                    models.ProductModelVersion.is_archived.is_(False),
                    models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
                ),
            )
            .join(
                models.ProductModel,
                and_(
                    models.ProductModel.is_archived.is_(False),
                    models.ProductModel.id == models.ProductModelVersion.model_id,
                ),
            )
            .filter(
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.completed_at >= start,
                models.ShipmentLine.completed_at < end,
                models.ShipmentLine.is_archived.is_(False),
            )
            .group_by(models.ProductModel.model_code, models.ProductModel.model_name)
        )
        if channel:
            mapping_q_ship = mapping_q_ship.filter(models.ShipmentLine.channel == channel)
        ship_model_rows = mapping_q_ship.all()
        shipped_by_model: Dict[str, Decimal] = {str(r.model_code): Decimal(str(r.shipped_qty or 0)) for r in ship_model_rows}
        model_name_map: Dict[str, Optional[str]] = {str(r.model_code): (str(r.model_name) if r.model_name else None) for r in ship_model_rows}

        mapping_q_ret = (
            db.query(
                models.ProductModel.model_code.label("model_code"),
                returned_qty_sum,
            )
            .select_from(models.AfterSalesLine)
            .join(
                models.SkuModelVersionMapping,
                and_(
                    models.SkuModelVersionMapping.is_archived.is_(False),
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.sku_code == models.AfterSalesLine.sku_code,
                ),
            )
            .join(
                models.ProductModelVersion,
                and_(
                    models.ProductModelVersion.is_archived.is_(False),
                    models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
                ),
            )
            .join(
                models.ProductModel,
                and_(
                    models.ProductModel.is_archived.is_(False),
                    models.ProductModel.id == models.ProductModelVersion.model_id,
                ),
            )
            .filter(
                models.AfterSalesLine.is_archived.is_(False),
                applied_time_expr.isnot(None),
                applied_time_expr >= start,
                applied_time_expr < end,
                models.AfterSalesLine.sku_code.isnot(None),
            )
            .group_by(models.ProductModel.model_code)
        )
        if channel:
            mapping_q_ret = mapping_q_ret.filter(models.AfterSalesLine.channel == channel)
        ret_model_rows = mapping_q_ret.all()
        returned_by_model: Dict[str, Decimal] = {str(r.model_code): Decimal(str(r.returned_qty or 0)) for r in ret_model_rows}

        model_keys = list(set(list(shipped_by_model.keys()) + list(returned_by_model.keys())))
        merged_models = _merge_top_by_key(model_keys, shipped_by_model, returned_by_model)
        top_models: List[Dict[str, Any]] = []
        for it in merged_models:
            mc = str(it["key"])
            tpl_code, selector, phrase = _try_get_bundle_phrase_preset(db, mc)
            top_models.append(
                {
                    "model_code": mc,
                    "model_name": model_name_map.get(mc),
                    "bundle_template_code": tpl_code,
                    "bundle_preset_selector": selector,
                    "bundle_preset_phrase": phrase,
                    "shipped_qty": it["shipped_qty"],
                    "returned_qty": it["returned_qty"],
                    "return_rate": it["return_rate"],
                }
            )

        # applied window total (for ops KPI display only; UI may choose to ignore)
        after_sales_lines_total = int(
            db.query(func.count(models.AfterSalesLine.id))
            .filter(
                models.AfterSalesLine.is_archived.is_(False),
                applied_time_expr.isnot(None),
                applied_time_expr >= start,
                applied_time_expr < end,
            )
            .filter(*( [models.AfterSalesLine.channel == channel] if channel else [] ))
            .scalar()
            or 0
        )

        return {
            "group_by": group_by,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "kpis": {
                "shipped_qty": shipped_qty_total,
                "shipped_amount": shipped_amount_total,
                "returned_qty": returned_qty_total,
                "refund_amount": refund_amount_total,
                "return_rate": return_rate_total,
                "refund_rate": refund_rate_total,
                "model_mapped_shipped_qty": Decimal("0"),
                "model_mapped_rate": None,
                "matched_return_lines": 0,
                "matched_return_lines_with_applied_at": 0,
                "after_sales_lines_total": after_sales_lines_total,
                "after_sales_lines_matched_any_shipment": 0,
                "after_sales_lines_unmatched": 0,
                "after_sales_lines_unmatched_rate": None,
                "after_sales_lines_missing_order_no": 0,
                "after_sales_lines_missing_product_link_id": 0,
                "after_sales_lines_missing_sku_code": 0,
            },
            "series": series,
            "top_reasons": top_reasons,
            "top_models": top_models,
            "top_skus": top_skus,
            "top_links": top_links,
            "lag_buckets": [],
        }

    period_expr = _group_time_expr_dash(db, models.ShipmentLine.completed_at, group_by).label("period")

    shipped_qty_sum = func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty")
    shipped_amount_sum = func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label("shipped_amount")

    returned_qty_expr = func.coalesce(
        func.sum(func.coalesce(models.AfterSalesLine.actual_return_qty, models.AfterSalesLine.return_qty)),
        0,
    ).label("returned_qty")
    refund_amount_expr = func.coalesce(
        func.sum(func.coalesce(models.AfterSalesLine.allocated_refund_amount, models.AfterSalesLine.refund_amount)),
        0,
    ).label("refund_amount")

    # ----- KPI totals -----
    ship_total_q = db.query(
        shipped_qty_sum,
        shipped_amount_sum,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_total_q = ship_total_q.filter(models.ShipmentLine.channel == channel)
    ship_total = ship_total_q.one()

    ret_total_q = db.query(
        returned_qty_expr,
        refund_amount_expr,
    ).select_from(
        models.ShipmentLine
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_total_q = ret_total_q.filter(models.ShipmentLine.channel == channel)
    ret_total = ret_total_q.one()

    shipped_qty_total = Decimal(str(ship_total.shipped_qty or 0))
    shipped_amount_total = Decimal(str(ship_total.shipped_amount or 0))
    returned_qty_total = Decimal(str(ret_total.returned_qty or 0))
    refund_amount_total = Decimal(str(ret_total.refund_amount or 0))
    return_rate_total = (returned_qty_total / shipped_qty_total) if shipped_qty_total > 0 else None
    refund_rate_total = (refund_amount_total / shipped_amount_total) if shipped_amount_total > 0 else None

    # matched return lines count within shipment window (and with applied_at for lag)
    matched_lines_q = (
        db.query(func.count(func.distinct(models.AfterSalesLine.id)))
        .select_from(models.ShipmentLine)
        .join(
            models.AfterSalesLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
            ),
        )
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            models.AfterSalesLine.is_archived.is_(False),
        )
    )
    if channel:
        matched_lines_q = matched_lines_q.filter(models.ShipmentLine.channel == channel)
    matched_return_lines = int(matched_lines_q.scalar() or 0)

    matched_lines_with_applied_q = (
        db.query(func.count(func.distinct(models.AfterSalesLine.id)))
        .select_from(models.ShipmentLine)
        .join(
            models.AfterSalesLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
            ),
        )
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            models.AfterSalesLine.is_archived.is_(False),
            models.AfterSalesLine.applied_at.isnot(None),
        )
    )
    if channel:
        matched_lines_with_applied_q = matched_lines_with_applied_q.filter(models.ShipmentLine.channel == channel)
    matched_return_lines_with_applied_at = int(matched_lines_with_applied_q.scalar() or 0)

    # data quality ("unattributed share") within applied window
    # use applied_at first, fallback to occurred_at
    applied_time_expr = func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at)
    after_sales_total_q = (
        db.query(func.count(models.AfterSalesLine.id))
        .filter(
            models.AfterSalesLine.is_archived.is_(False),
            applied_time_expr.isnot(None),
            applied_time_expr >= start,
            applied_time_expr < end,
        )
    )
    if channel:
        after_sales_total_q = after_sales_total_q.filter(models.AfterSalesLine.channel == channel)
    after_sales_lines_total = int(after_sales_total_q.scalar() or 0)

    after_sales_matched_any_q = (
        db.query(func.count(func.distinct(models.AfterSalesLine.id)))
        .select_from(models.AfterSalesLine)
        .join(
            models.ShipmentLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
                models.ShipmentLine.is_archived.is_(False),
            ),
        )
        .filter(
            models.AfterSalesLine.is_archived.is_(False),
            applied_time_expr.isnot(None),
            applied_time_expr >= start,
            applied_time_expr < end,
        )
    )
    if channel:
        after_sales_matched_any_q = after_sales_matched_any_q.filter(models.AfterSalesLine.channel == channel)
    after_sales_lines_matched_any_shipment = int(after_sales_matched_any_q.scalar() or 0)

    after_sales_lines_unmatched = max(after_sales_lines_total - after_sales_lines_matched_any_shipment, 0)
    after_sales_lines_unmatched_rate = (
        Decimal(str(after_sales_lines_unmatched)) / Decimal(str(after_sales_lines_total))
        if after_sales_lines_total > 0
        else None
    )

    def _missing_count(cond):
        q = (
            db.query(func.count(models.AfterSalesLine.id))
            .filter(
                models.AfterSalesLine.is_archived.is_(False),
                applied_time_expr.isnot(None),
                applied_time_expr >= start,
                applied_time_expr < end,
                cond,
            )
        )
        if channel:
            q = q.filter(models.AfterSalesLine.channel == channel)
        return int(q.scalar() or 0)

    after_sales_lines_missing_order_no = _missing_count(models.AfterSalesLine.order_no.is_(None))
    after_sales_lines_missing_product_link_id = _missing_count(models.AfterSalesLine.product_link_id.is_(None))
    after_sales_lines_missing_sku_code = _missing_count(models.AfterSalesLine.sku_code.is_(None))

    # model-mapped shipped qty (coverage for model analysis)
    mapping_on = and_(
        models.SkuModelVersionMapping.is_archived.is_(False),
        models.SkuModelVersionMapping.is_active.is_(True),
        models.SkuModelVersionMapping.sku_code == models.ShipmentLine.sku_code,
    )
    ship_model_cover_q = db.query(
        func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("mapped_shipped_qty"),
    ).join(
        models.SkuModelVersionMapping,
        mapping_on,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_model_cover_q = ship_model_cover_q.filter(models.ShipmentLine.channel == channel)
    mapped_shipped_qty = Decimal(str(ship_model_cover_q.scalar() or 0))
    model_mapped_rate = (mapped_shipped_qty / shipped_qty_total) if shipped_qty_total > 0 else None

    # ----- series (period totals) -----
    ship_series_q = db.query(
        period_expr,
        shipped_qty_sum,
        shipped_amount_sum,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_series_q = ship_series_q.filter(models.ShipmentLine.channel == channel)
    ship_series_q = ship_series_q.group_by(period_expr)
    ship_rows = ship_series_q.all()

    ret_series_q = db.query(
        period_expr,
        returned_qty_expr,
        refund_amount_expr,
    ).select_from(
        models.ShipmentLine
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_series_q = ret_series_q.filter(models.ShipmentLine.channel == channel)
    ret_series_q = ret_series_q.group_by(period_expr)
    ret_rows = ret_series_q.all()

    ret_map: Dict[str, Dict[str, Decimal]] = {}
    for r in ret_rows:
        ret_map[str(r.period)] = {
            "returned_qty": Decimal(str(r.returned_qty or 0)),
            "refund_amount": Decimal(str(r.refund_amount or 0)),
        }

    series: List[Dict[str, Any]] = []
    for r in ship_rows:
        p_label = _fmt_period_label(r.period, group_by)
        p_key = str(r.period)
        shipped_qty = Decimal(str(r.shipped_qty or 0))
        shipped_amount = Decimal(str(r.shipped_amount or 0))
        ret = ret_map.get(p_key) or {"returned_qty": Decimal("0"), "refund_amount": Decimal("0")}
        returned_qty = ret["returned_qty"]
        refund_amount = ret["refund_amount"]
        series.append(
            {
                "period": p_label,
                "shipped_qty": shipped_qty,
                "shipped_amount": shipped_amount,
                "returned_qty": returned_qty,
                "refund_amount": refund_amount,
                "return_rate": (returned_qty / shipped_qty) if shipped_qty > 0 else None,
                "refund_rate": (refund_amount / shipped_amount) if shipped_amount > 0 else None,
            }
        )

    # ----- top reasons -----
    top_n = max(1, min(int(top_n or 12), 50))
    reasons_q = db.query(
        models.AfterSalesLine.reason.label("reason"),
        returned_qty_expr,
        refund_amount_expr,
    ).select_from(
        models.ShipmentLine
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
        models.AfterSalesLine.reason.isnot(None),
        func.length(func.trim(models.AfterSalesLine.reason)) > 0,
    )
    if channel:
        reasons_q = reasons_q.filter(models.ShipmentLine.channel == channel)
    reasons_q = reasons_q.group_by(models.AfterSalesLine.reason).order_by(returned_qty_expr.desc()).limit(top_n)
    reason_rows = reasons_q.all()
    top_reasons: List[Dict[str, Any]] = []
    for r in reason_rows:
        qty = Decimal(str(r.returned_qty or 0))
        amt = Decimal(str(r.refund_amount or 0))
        top_reasons.append(
            {
                "reason": str(r.reason),
                "returned_qty": qty,
                "refund_amount": amt,
                "share_returned_qty": (qty / returned_qty_total) if returned_qty_total > 0 else None,
                "share_refund_amount": (amt / refund_amount_total) if refund_amount_total > 0 else None,
            }
        )

    # ----- top skus -----
    ship_sku_q = db.query(
        models.ShipmentLine.sku_code.label("sku_code"),
        shipped_qty_sum,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.ShipmentLine.sku_code.isnot(None),
    )
    if channel:
        ship_sku_q = ship_sku_q.filter(models.ShipmentLine.channel == channel)
    ship_sku_q = ship_sku_q.group_by(models.ShipmentLine.sku_code)
    ship_sku_rows = ship_sku_q.all()
    ship_sku_map: Dict[str, Decimal] = {str(r.sku_code): Decimal(str(r.shipped_qty or 0)) for r in ship_sku_rows}

    ret_sku_q = db.query(
        models.ShipmentLine.sku_code.label("sku_code"),
        returned_qty_expr,
    ).select_from(
        models.ShipmentLine
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
        models.ShipmentLine.sku_code.isnot(None),
    )
    if channel:
        ret_sku_q = ret_sku_q.filter(models.ShipmentLine.channel == channel)
    ret_sku_q = ret_sku_q.group_by(models.ShipmentLine.sku_code).order_by(returned_qty_expr.desc()).limit(top_n)
    sku_rows = ret_sku_q.all()
    top_skus: List[Dict[str, Any]] = []
    for r in sku_rows:
        sku = str(r.sku_code or "")
        shipped_qty = ship_sku_map.get(sku) or Decimal("0")
        returned_qty = Decimal(str(r.returned_qty or 0))
        top_skus.append(
            {
                "sku_code": sku,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": (returned_qty / shipped_qty) if shipped_qty > 0 else None,
            }
        )

    # ----- top links -----
    ship_link_q = db.query(
        models.ShipmentLine.product_link_id.label("product_link_id"),
        shipped_qty_sum,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.ShipmentLine.product_link_id.isnot(None),
    )
    if channel:
        ship_link_q = ship_link_q.filter(models.ShipmentLine.channel == channel)
    ship_link_q = ship_link_q.group_by(models.ShipmentLine.product_link_id)
    ship_link_rows = ship_link_q.all()
    ship_link_map: Dict[str, Decimal] = {str(r.product_link_id): Decimal(str(r.shipped_qty or 0)) for r in ship_link_rows}

    ret_link_q = db.query(
        models.ShipmentLine.product_link_id.label("product_link_id"),
        returned_qty_expr,
    ).select_from(
        models.ShipmentLine
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
        models.ShipmentLine.product_link_id.isnot(None),
    )
    if channel:
        ret_link_q = ret_link_q.filter(models.ShipmentLine.channel == channel)
    ret_link_q = ret_link_q.group_by(models.ShipmentLine.product_link_id).order_by(returned_qty_expr.desc()).limit(top_n)
    link_rows = ret_link_q.all()
    top_links: List[Dict[str, Any]] = []
    for r in link_rows:
        link = str(r.product_link_id or "")
        shipped_qty = ship_link_map.get(link) or Decimal("0")
        returned_qty = Decimal(str(r.returned_qty or 0))
        top_links.append(
            {
                "product_link_id": link,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": (returned_qty / shipped_qty) if shipped_qty > 0 else None,
            }
        )

    # ----- attach most common spec_text for top skus/links (best-effort, small N) -----
    join_on = and_(
        models.AfterSalesLine.order_no.isnot(None),
        models.AfterSalesLine.product_link_id.isnot(None),
        models.AfterSalesLine.sku_code.isnot(None),
        models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
        models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
        models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
    )

    sku_codes = [it.get("sku_code") for it in top_skus if it.get("sku_code")]
    if sku_codes:
        spec_rows = (
            db.query(
                models.ShipmentLine.sku_code.label("sku_code"),
                models.AfterSalesLine.spec_text.label("spec_text"),
                func.count(models.AfterSalesLine.id).label("cnt"),
            )
            .select_from(models.ShipmentLine)
            .join(models.AfterSalesLine, join_on)
            .filter(
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.completed_at >= start,
                models.ShipmentLine.completed_at < end,
                models.ShipmentLine.is_archived.is_(False),
                models.AfterSalesLine.is_archived.is_(False),
                models.ShipmentLine.sku_code.in_(sku_codes),
                models.AfterSalesLine.spec_text.isnot(None),
                func.length(func.trim(models.AfterSalesLine.spec_text)) > 0,
            )
            .group_by(models.ShipmentLine.sku_code, models.AfterSalesLine.spec_text)
            .order_by(models.ShipmentLine.sku_code, func.count(models.AfterSalesLine.id).desc())
            .all()
        )
        best_spec_by_sku: Dict[str, str] = {}
        for r in spec_rows:
            code = str(r.sku_code or "")
            if code and code not in best_spec_by_sku:
                best_spec_by_sku[code] = str(r.spec_text or "")
        for it in top_skus:
            code = str(it.get("sku_code") or "")
            if code and best_spec_by_sku.get(code):
                it["spec_text"] = best_spec_by_sku[code]

    link_ids = [it.get("product_link_id") for it in top_links if it.get("product_link_id")]
    if link_ids:
        link_spec_rows = (
            db.query(
                models.ShipmentLine.product_link_id.label("product_link_id"),
                models.AfterSalesLine.spec_text.label("spec_text"),
                func.count(models.AfterSalesLine.id).label("cnt"),
            )
            .select_from(models.ShipmentLine)
            .join(models.AfterSalesLine, join_on)
            .filter(
                models.ShipmentLine.completed_at.isnot(None),
                models.ShipmentLine.completed_at >= start,
                models.ShipmentLine.completed_at < end,
                models.ShipmentLine.is_archived.is_(False),
                models.AfterSalesLine.is_archived.is_(False),
                models.ShipmentLine.product_link_id.in_(link_ids),
                models.AfterSalesLine.spec_text.isnot(None),
                func.length(func.trim(models.AfterSalesLine.spec_text)) > 0,
            )
            .group_by(models.ShipmentLine.product_link_id, models.AfterSalesLine.spec_text)
            .order_by(models.ShipmentLine.product_link_id, func.count(models.AfterSalesLine.id).desc())
            .all()
        )
        best_spec_by_link: Dict[str, str] = {}
        for r in link_spec_rows:
            link = str(r.product_link_id or "")
            if link and link not in best_spec_by_link:
                best_spec_by_link[link] = str(r.spec_text or "")
        for it in top_links:
            link = str(it.get("product_link_id") or "")
            if link and best_spec_by_link.get(link):
                it["spec_text"] = best_spec_by_link[link]

    # ----- top models -----
    ship_model_q = db.query(
        models.ProductModel.model_code.label("model_code"),
        models.ProductModel.model_name.label("model_name"),
        func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty"),
    ).join(
        models.SkuModelVersionMapping,
        mapping_on,
    ).join(
        models.ProductModelVersion,
        models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
    ).join(
        models.ProductModel,
        models.ProductModel.id == models.ProductModelVersion.model_id,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_model_q = ship_model_q.filter(models.ShipmentLine.channel == channel)
    ship_model_rows = ship_model_q.group_by(models.ProductModel.model_code, models.ProductModel.model_name).all()
    ship_model_map: Dict[str, Decimal] = {str(r.model_code): Decimal(str(r.shipped_qty or 0)) for r in ship_model_rows}
    ship_model_name: Dict[str, str] = {str(r.model_code): str(r.model_name or "") for r in ship_model_rows}

    ret_model_q = db.query(
        models.ProductModel.model_code.label("model_code"),
        models.ProductModel.model_name.label("model_name"),
        returned_qty_expr,
    ).select_from(
        models.ShipmentLine
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).join(
        models.SkuModelVersionMapping,
        mapping_on,
    ).join(
        models.ProductModelVersion,
        models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
    ).join(
        models.ProductModel,
        models.ProductModel.id == models.ProductModelVersion.model_id,
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_model_q = ret_model_q.filter(models.ShipmentLine.channel == channel)
    ret_model_q = ret_model_q.group_by(models.ProductModel.model_code, models.ProductModel.model_name).order_by(returned_qty_expr.desc()).limit(top_n)
    model_rows = ret_model_q.all()
    top_models: List[Dict[str, Any]] = []
    for r in model_rows:
        code = str(r.model_code or "")
        tpl_code, selector, phrase = _try_get_bundle_phrase_preset(db, code)
        shipped_qty = ship_model_map.get(code) or Decimal("0")
        returned_qty = Decimal(str(r.returned_qty or 0))
        top_models.append(
            {
                "model_code": code,
                "model_name": ship_model_name.get(code) or str(r.model_name or ""),
                "bundle_template_code": tpl_code,
                "bundle_preset_selector": selector,
                "bundle_preset_phrase": phrase,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": (returned_qty / shipped_qty) if shipped_qty > 0 else None,
            }
        )

    # ----- lag buckets (matched returns, by applied_at - completed_at) -----
    dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
    if dialect == "postgresql":
        lag_days_expr = func.floor(
            func.extract(
                "epoch",
                func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at) - models.ShipmentLine.completed_at,
            )
            / 86400.0
        )
    else:
        # sqlite best-effort
        lag_days_expr = func.floor(
            (func.julianday(func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at)) - func.julianday(models.ShipmentLine.completed_at))
        )

    lag_qty_expr = func.coalesce(
        func.sum(func.coalesce(models.AfterSalesLine.actual_return_qty, models.AfterSalesLine.return_qty)),
        0,
    ).label("returned_qty")

    lag_base = (
        db.query(lag_days_expr.label("lag_days"), lag_qty_expr)
        .select_from(models.ShipmentLine)
        .join(
            models.AfterSalesLine,
            and_(
                models.AfterSalesLine.order_no.isnot(None),
                models.AfterSalesLine.product_link_id.isnot(None),
                models.AfterSalesLine.sku_code.isnot(None),
                models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
                models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
                models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
            ),
        )
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            models.AfterSalesLine.is_archived.is_(False),
            func.coalesce(models.AfterSalesLine.applied_at, models.AfterSalesLine.occurred_at).isnot(None),
        )
    )
    if channel:
        lag_base = lag_base.filter(models.ShipmentLine.channel == channel)

    lag_rows = lag_base.group_by(lag_days_expr).all()
    buckets = {
        "0-7天": Decimal("0"),
        "8-14天": Decimal("0"),
        "15-30天": Decimal("0"),
        "30天+": Decimal("0"),
        "未知/负值": Decimal("0"),
    }
    for r in lag_rows:
        try:
            lag_days = int(r.lag_days) if r.lag_days is not None else None
        except Exception:  # noqa: BLE001
            lag_days = None
        qty = Decimal(str(r.returned_qty or 0))
        if lag_days is None:
            buckets["未知/负值"] += qty
        elif lag_days < 0:
            buckets["未知/负值"] += qty
        elif lag_days <= 7:
            buckets["0-7天"] += qty
        elif lag_days <= 14:
            buckets["8-14天"] += qty
        elif lag_days <= 30:
            buckets["15-30天"] += qty
        else:
            buckets["30天+"] += qty

    lag_total = sum(buckets.values(), Decimal("0"))
    lag_buckets: List[Dict[str, Any]] = []
    for name in ["0-7天", "8-14天", "15-30天", "30天+", "未知/负值"]:
        v = buckets[name]
        lag_buckets.append(
            {
                "bucket": name,
                "returned_qty": v,
                "share": (v / lag_total) if lag_total > 0 else None,
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "kpis": {
            "shipped_qty": shipped_qty_total,
            "shipped_amount": shipped_amount_total,
            "returned_qty": returned_qty_total,
            "refund_amount": refund_amount_total,
            "return_rate": return_rate_total,
            "refund_rate": refund_rate_total,
            "model_mapped_shipped_qty": mapped_shipped_qty,
            "model_mapped_rate": model_mapped_rate,
            "matched_return_lines": matched_return_lines,
            "matched_return_lines_with_applied_at": matched_return_lines_with_applied_at,
            "after_sales_lines_total": after_sales_lines_total,
            "after_sales_lines_matched_any_shipment": after_sales_lines_matched_any_shipment,
            "after_sales_lines_unmatched": after_sales_lines_unmatched,
            "after_sales_lines_unmatched_rate": after_sales_lines_unmatched_rate,
            "after_sales_lines_missing_order_no": after_sales_lines_missing_order_no,
            "after_sales_lines_missing_product_link_id": after_sales_lines_missing_product_link_id,
            "after_sales_lines_missing_sku_code": after_sales_lines_missing_sku_code,
        },
        "series": series,
        "top_reasons": top_reasons,
        "top_models": top_models,
        "top_skus": top_skus,
        "top_links": top_links,
        "lag_buckets": lag_buckets,
    }


def returns_rate_by_sku(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "day",
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return-rate analytics (2025 analysis mode):
    - Attribute returns to the shipment completion period by strong keys:
      order_no + product_link_id + sku_code.
    - Only matched after-sales lines contribute to returned_qty/refund_amount.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    period_expr = _group_time_expr(db, models.ShipmentLine.completed_at, group_by).label("period")

    ship_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        models.ShipmentLine.sku_code.label("sku_code"),
        func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty"),
        func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label("shipped_amount"),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        ship_q = ship_q.filter(models.ShipmentLine.sku_code == sku_code)

    ship_q = ship_q.group_by(period_expr, models.ShipmentLine.channel, models.ShipmentLine.sku_code)
    ship_rows = ship_q.all()

    # returns matched to shipments in the period
    ret_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        models.ShipmentLine.sku_code.label("sku_code"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_q = ret_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        ret_q = ret_q.filter(models.ShipmentLine.sku_code == sku_code)
    ret_q = ret_q.group_by(period_expr, models.ShipmentLine.channel, models.ShipmentLine.sku_code)
    ret_rows = ret_q.all()

    ret_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in ret_rows:
        key = (str(r.period), str(r.channel or ""), str(r.sku_code or ""))
        ret_map[key] = {
            "returned_qty": r.returned_qty,
            "refund_amount": r.refund_amount,
        }

    items: List[Dict[str, Any]] = []
    for r in ship_rows:
        key = (str(r.period), str(r.channel or ""), str(r.sku_code or ""))
        ret = ret_map.get(key) or {"returned_qty": Decimal("0"), "refund_amount": Decimal("0")}
        shipped_qty = Decimal(str(r.shipped_qty or 0))
        shipped_amount = Decimal(str(r.shipped_amount or 0))
        returned_qty = Decimal(str(ret["returned_qty"] or 0))
        refund_amount = Decimal(str(ret["refund_amount"] or 0))
        return_rate = (returned_qty / shipped_qty) if shipped_qty > 0 else None
        refund_rate = (refund_amount / shipped_amount) if shipped_amount > 0 else None

        items.append(
            {
                "period": str(r.period),
                "channel": r.channel,
                "sku_code": r.sku_code,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": return_rate,
                "shipped_amount": shipped_amount,
                "refund_amount": refund_amount,
                "refund_rate": refund_rate,
            }
        )

    # unmatched returns within the same time window (for data quality)
    unmatched_q = db.query(func.count(models.AfterSalesLine.id)).filter(
        models.AfterSalesLine.is_archived.is_(False),
        models.AfterSalesLine.applied_at.isnot(None),
        models.AfterSalesLine.applied_at >= start,
        models.AfterSalesLine.applied_at < end,
        func.coalesce(models.AfterSalesLine.order_no, "") == "",
    )
    unmatched_returns = int(unmatched_q.scalar() or 0)

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "items": items,
        "unmatched_returns_missing_order_no": unmatched_returns,
    }


def returns_rate_by_channel(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "day",
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns-rate aggregated by channel.
    - Shipment baseline uses shipment_lines within [start, end) by completed_at.
    - Returns are attributed to shipment period via strong keys:
      order_no + product_link_id + sku_code.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    period_expr = _group_time_expr(db, models.ShipmentLine.completed_at, group_by).label("period")

    ship_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty"),
        func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label("shipped_amount"),
        func.count(models.ShipmentLine.id).label("shipment_lines_total"),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    ship_q = ship_q.group_by(period_expr, models.ShipmentLine.channel)
    ship_rows = ship_q.all()

    ret_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_q = ret_q.filter(models.ShipmentLine.channel == channel)
    ret_q = ret_q.group_by(period_expr, models.ShipmentLine.channel)
    ret_rows = ret_q.all()

    ret_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in ret_rows:
        ret_map[(str(r.period), str(r.channel or ""))] = {
            "returned_qty": r.returned_qty,
            "refund_amount": r.refund_amount,
        }

    items: List[Dict[str, Any]] = []
    for r in ship_rows:
        key = (str(r.period), str(r.channel or ""))
        ret = ret_map.get(key) or {"returned_qty": Decimal("0"), "refund_amount": Decimal("0")}
        shipped_qty = Decimal(str(r.shipped_qty or 0))
        shipped_amount = Decimal(str(r.shipped_amount or 0))
        returned_qty = Decimal(str(ret["returned_qty"] or 0))
        refund_amount = Decimal(str(ret["refund_amount"] or 0))
        return_rate = (returned_qty / shipped_qty) if shipped_qty > 0 else None
        refund_rate = (refund_amount / shipped_amount) if shipped_amount > 0 else None
        items.append(
            {
                "period": str(r.period),
                "channel": r.channel,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": return_rate,
                "shipped_amount": shipped_amount,
                "refund_amount": refund_amount,
                "refund_rate": refund_rate,
                "shipment_lines_total": int(r.shipment_lines_total or 0),
            }
        )

    unmatched_q = db.query(func.count(models.AfterSalesLine.id)).filter(
        models.AfterSalesLine.is_archived.is_(False),
        models.AfterSalesLine.applied_at.isnot(None),
        models.AfterSalesLine.applied_at >= start,
        models.AfterSalesLine.applied_at < end,
        func.coalesce(models.AfterSalesLine.order_no, "") == "",
    )
    unmatched_returns = int(unmatched_q.scalar() or 0)

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "items": items,
        "unmatched_returns_missing_order_no": unmatched_returns,
    }


def _d(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _extract_total_cost_from_trace(trace_json: Any) -> Tuple[Optional[Decimal], str]:
    """
    Extract total cost from a bom_snapshot-like trace JSON.
    Returns (cost, status): status in {"costed","missing_costing"}.
    """
    trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
    costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
    total_cost = costing.get("total_cost")
    if total_cost in (None, ""):
        total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
    cost = _d(total_cost)
    if cost == 0 and total_cost in (None, "", 0):
        return None, "missing_costing"
    return cost, "costed"


def _extract_cost_breakdown_from_trace(trace_json: Any) -> Tuple[Optional[Decimal], Decimal, Decimal, Decimal, str]:
    """
    Extract (total, material, process, overhead, status) from a bom_snapshot-like trace JSON.
    status in {"costed","missing_costing"}.
    """
    trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
    costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}

    material = costing.get("material_cost_total")
    process = costing.get("process_cost_total")
    overhead = costing.get("overhead_cost")
    total_cost = costing.get("total_cost")

    m = _d(material)
    p = _d(process)
    o = _d(overhead)

    if total_cost in (None, ""):
        total_cost = m + p + o
    total = _d(total_cost)

    if total == 0 and (costing.get("total_cost") in (None, "", 0)) and (material in (None, "")) and (process in (None, "")) and (overhead in (None, "")):
        return None, Decimal("0"), Decimal("0"), Decimal("0"), "missing_costing"
    return total, m, p, o, "costed"


def _period_key(dt: datetime, group_by: Literal["day", "month"]) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if group_by == "month":
        return f"{dt.year:04d}-{dt.month:02d}-01"
    return dt.date().isoformat()


def profit_by_sku(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "month",
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Profit analytics by SKU:
    - Revenue/qty baseline uses ALL shipment_lines within [start, end) by completed_at.
    - Cost uses shipment_costing_results when present (2025/2026 unified). For legacy data, falls back to latest bom_snapshot trace.
    - Refunds (returns) are attributed to shipment period via strong join (order_no+product_link_id+sku_code).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # Revenue baseline: all shipments (even those without BOM snapshots)
    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        ship_q = ship_q.filter(models.ShipmentLine.sku_code == sku_code)

    total_ship_lines = ship_q.count()

    # Latest snapshot per shipment_line_id (legacy fallback)
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    cost_q = (
        db.query(
            models.ShipmentLine,
            models.ShipmentCostingResult,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.model_version_id,
            snap_sq.c.trace_json,
        )
        .outerjoin(models.ShipmentCostingResult, models.ShipmentLine.id == models.ShipmentCostingResult.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            or_(models.ShipmentCostingResult.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)),
        )
    )
    if channel:
        cost_q = cost_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        cost_q = cost_q.filter(models.ShipmentLine.sku_code == sku_code)
    cost_rows = cost_q.all()

    # Refund aggregation (same keying as returns-rate)
    refund_q = db.query(
        models.ShipmentLine,
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        refund_q = refund_q.filter(models.ShipmentLine.sku_code == sku_code)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_rows = refund_q.all()

    refund_by_line: Dict[str, Dict[str, Decimal]] = {}
    for sl, ra, rq in refund_rows:
        refund_by_line[str(sl.id)] = {"refund_amount": _d(ra), "returned_qty": _d(rq)}

    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    missing_cost = 0

    for line, res, _snap_id, _snap_model_version_id, snap_trace_json in cost_rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(line.channel or ""), str(line.sku_code or ""))
        bucket = agg.setdefault(
            key,
            {
                "period": period,
                "channel": line.channel,
                "sku_code": line.sku_code,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "lines_with_bom": 0,
            },
        )

        bucket["lines_with_bom"] += 1
        bucket["shipped_qty"] += _d(line.qty)
        bucket["revenue_amount"] += _d(line.revenue_amount)

        if res is not None:
            total_cost = getattr(res, "cost_total", None)
            if total_cost in (None, ""):
                total_cost = (
                    _d(getattr(res, "cost_material_total", None))
                    + _d(getattr(res, "cost_process_total", None))
                    + _d(getattr(res, "cost_overhead_total", None))
                )
            cost = _d(total_cost)
            if cost == 0 and total_cost in (None, "", 0):
                # If the lightweight result is missing cost (edge/legacy), try to fall back to snapshot trace if present.
                snap_cost, status = _extract_total_cost_from_trace(snap_trace_json)
                if status == "costed":
                    cost = _d(snap_cost)
                else:
                    missing_cost += 1
            bucket["cost_amount"] += cost
        else:
            cost, status = _extract_total_cost_from_trace(snap_trace_json)
            if status == "missing_costing":
                missing_cost += 1
            bucket["cost_amount"] += _d(cost)

        ref = refund_by_line.get(str(line.id))
        if ref:
            bucket["refund_amount"] += ref["refund_amount"]
            bucket["returned_qty"] += ref["returned_qty"]

    items: List[Dict[str, Any]] = []
    for _, b in sorted(agg.items(), key=lambda kv: kv[0]):
        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None

        items.append(
            {
                **{k: v for k, v in b.items() if k not in ("lines_with_bom",)},
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_shipment_lines": total_ship_lines,
        "lines_with_bom_snapshots": len(cost_rows),
        "lines_missing_costing": missing_cost,
        "items": items,
        "note": "Profit by SKU uses shipment_lines revenue baseline; cost from shipment_costing_results (coverage tracked). net_profit=(revenue-refund)-cost.",
    }


def profit_by_channel(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "month",
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Profit analytics aggregated by channel.
    - Revenue/qty baseline uses ALL shipment_lines within [start, end) by completed_at.
    - Cost uses shipment_costing_results when present; falls back to latest bom_snapshot trace for legacy data.
    - Refunds are attributed to shipment period via strong keys (order_no+product_link_id+sku_code).
    - Coverage is explicit (total shipment lines vs costed lines).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = ship_q.count()
    ship_rows = ship_q.all()

    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    cost_q = (
        db.query(
            models.ShipmentLine,
            models.ShipmentCostingResult,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
        )
        .outerjoin(models.ShipmentCostingResult, models.ShipmentLine.id == models.ShipmentCostingResult.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            or_(models.ShipmentCostingResult.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)),
        )
    )
    if channel:
        cost_q = cost_q.filter(models.ShipmentLine.channel == channel)
    cost_rows = cost_q.all()

    refund_q = db.query(
        models.ShipmentLine.id.label("shipment_line_id"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_by_line = {str(r.shipment_line_id): {"refund_amount": _d(r.refund_amount), "returned_qty": _d(r.returned_qty)} for r in refund_q.all()}

    # Baseline aggregation by period+channel (ALL shipment lines)
    base: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for line in ship_rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(line.channel or ""))
        bucket = base.setdefault(
            key,
            {
                "period": period,
                "channel": line.channel,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "shipment_lines_total": 0,
                "lines_with_bom_snapshots": 0,
                "lines_missing_costing": 0,
                "cost_amount": Decimal("0"),
            },
        )
        bucket["shipment_lines_total"] += 1
        bucket["shipped_qty"] += _d(line.qty)
        bucket["revenue_amount"] += _d(line.revenue_amount)
        ref = refund_by_line.get(str(line.id))
        if ref:
            bucket["refund_amount"] += ref["refund_amount"]
            bucket["returned_qty"] += ref["returned_qty"]

    # Add costs (prefer costing results; fallback to snapshot trace)
    total_missing_costing = 0
    for line, res, _snap_id, snap_trace_json in cost_rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(line.channel or ""))
        bucket = base.get(key)
        if not bucket:
            # safety: should not happen, but keep consistent
            bucket = base.setdefault(
                key,
                {
                    "period": period,
                    "channel": line.channel,
                    "shipped_qty": Decimal("0"),
                    "revenue_amount": Decimal("0"),
                    "refund_amount": Decimal("0"),
                    "returned_qty": Decimal("0"),
                    "shipment_lines_total": 0,
                    "lines_with_bom_snapshots": 0,
                    "lines_missing_costing": 0,
                    "cost_amount": Decimal("0"),
                },
            )
        bucket["lines_with_bom_snapshots"] += 1
        if res is not None:
            total_cost = getattr(res, "cost_total", None)
            if total_cost in (None, ""):
                total_cost = (
                    _d(getattr(res, "cost_material_total", None))
                    + _d(getattr(res, "cost_process_total", None))
                    + _d(getattr(res, "cost_overhead_total", None))
                )
            cost = _d(total_cost)
            if cost == 0 and total_cost in (None, "", 0):
                # lightweight result missing cost -> fallback to snapshot trace if possible
                snap_cost, status = _extract_total_cost_from_trace(snap_trace_json)
                if status == "costed":
                    cost = _d(snap_cost)
                else:
                    bucket["lines_missing_costing"] += 1
                    total_missing_costing += 1
            bucket["cost_amount"] += cost
        else:
            cost, status = _extract_total_cost_from_trace(snap_trace_json)
            if status == "missing_costing":
                bucket["lines_missing_costing"] += 1
                total_missing_costing += 1
            bucket["cost_amount"] += _d(cost)

    items: List[Dict[str, Any]] = []
    for _, b in sorted(base.items(), key=lambda kv: kv[0]):
        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None
        items.append(
            {
                "period": b["period"],
                "channel": b["channel"],
                "shipped_qty": b["shipped_qty"],
                "revenue_amount": revenue,
                "cost_amount": cost,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "refund_amount": refund,
                "returned_qty": b["returned_qty"],
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
                "shipment_lines_total": int(b["shipment_lines_total"]),
                "lines_with_bom_snapshots": int(b["lines_with_bom_snapshots"]),
                "lines_missing_costing": int(b["lines_missing_costing"]),
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_shipment_lines": total_ship_lines,
        "lines_with_bom_snapshots": len(cost_rows),
        "lines_missing_costing": total_missing_costing,
        "items": items,
        "note": "Channel profit uses shipment_lines revenue baseline; cost from shipment_costing_results (coverage tracked). net_profit=(revenue-refund)-cost.",
    }


def profit_by_model(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "month",
    channel: Optional[str] = None,
    model_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    模型分析（按模型聚合）：
    - 收入/数量基线：时间范围内全部发货行（completed_at）
    - 模型归因：优先 shipment_costing_results.model_version_id，缺失时回退到最新 bom_snapshot.model_version_id
    - 成本：优先 shipment_costing_results（三段成本齐全），回退到 bom_snapshot.trace.costing
    - 版本：同一个模型可能涉及多个版本；返回“主版本”（按销售额最大的版本）+ version_count
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # Revenue baseline: all shipments (even those without model attribution)
    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = int(ship_q.count() or 0)

    # Costing result per shipment_line_id (supports 2025 no-snapshot mode)
    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )

    # Legacy fallback: latest bom_snapshot per shipment_line_id
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_sq.c.model_version_id)

    base_q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id.label("res_ship_line_id"),
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
            mv_id_expr.label("model_version_id"),
            models.ProductModelVersion.version_kind,
            models.ProductModelVersion.version_status,
            models.ProductModelVersion.version_label,
            models.ProductModel.id.label("model_id"),
            models.ProductModel.model_code.label("model_code"),
            models.ProductModel.model_name.label("model_name"),
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .outerjoin(
            models.ProductModelVersion,
            and_(models.ProductModelVersion.id == mv_id_expr, models.ProductModelVersion.is_archived.is_(False)),
        )
        .outerjoin(models.ProductModel, and_(models.ProductModel.id == models.ProductModelVersion.model_id, models.ProductModel.is_archived.is_(False)))
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        base_q = base_q.filter(models.ShipmentLine.channel == channel)
    if model_code:
        base_q = base_q.filter(models.ProductModel.model_code == model_code)
    rows = base_q.all()

    # Refund by shipment line (same as profit_by_sku)
    refund_q = db.query(
        models.ShipmentLine.id.label("shipment_line_id"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_by_line = {str(r.shipment_line_id): _d(r.refund_amount) for r in refund_q.all()}

    mapped_lines = 0
    costed_lines = 0
    missing_costing_lines = 0

    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for (
        line,
        res_ship_line_id,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        _bom_snapshot_id,
        snap_trace_json,
        mv_id,
        ver_kind,
        ver_status,
        ver_label,
        mdl_id,
        mdl_code,
        mdl_name,
    ) in rows:
        if not line.completed_at:
            continue
        if not mdl_id or not mdl_code or not mdl_name:
            continue

        period = _period_key(line.completed_at, group_by)
        store = str(line.channel or "").strip()
        key = (period, store, str(mdl_id))

        bucket = agg.setdefault(
            key,
            {
                "period": period,
                "channel": store or None,
                "model_id": str(mdl_id),
                "model_code": str(mdl_code),
                "model_name": str(mdl_name),
                # top version (filled at the end)
                "version_id": "",
                "version_kind": "",
                "version_status": "",
                "version_label": None,
                "version_count": 0,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_material_amount": Decimal("0"),
                "cost_process_amount": Decimal("0"),
                "cost_overhead_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "line_count": 0,
                "costed_line_count": 0,
                "missing_costing_line_count": 0,
                # internal
                "_ver_rev": {},  # version_id -> revenue
                "_ver_info": {},  # version_id -> (kind,status,label)
            },
        )

        mapped_lines += 1
        bucket["line_count"] += 1

        qty = _d(line.qty)
        revenue = _d(line.revenue_amount)
        bucket["shipped_qty"] += qty
        bucket["revenue_amount"] += revenue
        bucket["refund_amount"] += refund_by_line.get(str(line.id), Decimal("0"))

        # Version tracking (for top-version selection)
        mv_id_str = str(mv_id or "").strip()
        if mv_id_str:
            bucket["_ver_rev"][mv_id_str] = _d(bucket["_ver_rev"].get(mv_id_str, 0)) + revenue
            bucket["_ver_info"][mv_id_str] = (str(ver_kind or ""), str(ver_status or ""), str(ver_label or "") or None)

        # Cost breakdown
        if res_ship_line_id is not None:
            m = _d(cost_material_total)
            p = _d(cost_process_total)
            o = _d(cost_overhead_total)
            total_src = cost_total
            if total_src in (None, ""):
                total_src = m + p + o
            total = _d(total_src)
            if total == 0 and (cost_total in (None, "", 0)) and (cost_material_total in (None, "")) and (cost_process_total in (None, "")) and (cost_overhead_total in (None, "")):
                # lightweight result missing cost -> fallback to snapshot trace if possible
                snap_total, sm, sp, so, s = _extract_cost_breakdown_from_trace(snap_trace_json)
                if s == "costed":
                    bucket["costed_line_count"] += 1
                    costed_lines += 1
                    bucket["cost_material_amount"] += _d(sm)
                    bucket["cost_process_amount"] += _d(sp)
                    bucket["cost_overhead_amount"] += _d(so)
                    bucket["cost_amount"] += _d(snap_total)
                else:
                    bucket["missing_costing_line_count"] += 1
                    missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += m
                bucket["cost_process_amount"] += p
                bucket["cost_overhead_amount"] += o
                bucket["cost_amount"] += total
        else:
            total, m, p, o, status = _extract_cost_breakdown_from_trace(snap_trace_json)
            if status == "missing_costing":
                bucket["missing_costing_line_count"] += 1
                missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += _d(m)
                bucket["cost_process_amount"] += _d(p)
                bucket["cost_overhead_amount"] += _d(o)
                bucket["cost_amount"] += _d(total)

    items: List[Dict[str, Any]] = []
    for _, b in sorted(agg.items(), key=lambda kv: kv[0]):
        # resolve top version (by revenue)
        ver_rev = b.pop("_ver_rev", {}) or {}
        ver_info = b.pop("_ver_info", {}) or {}
        if ver_rev:
            top_ver_id = max(ver_rev.items(), key=lambda kv: kv[1])[0]
            kind, status, label = ver_info.get(top_ver_id, ("", "", None))
            b["version_id"] = top_ver_id
            b["version_kind"] = kind
            b["version_status"] = status
            b["version_label"] = label
            b["version_count"] = len(ver_rev)
        else:
            b["version_id"] = ""
            b["version_kind"] = ""
            b["version_status"] = ""
            b["version_label"] = None
            b["version_count"] = 0

        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None
        items.append(
            {
                **b,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_shipment_lines": total_ship_lines,
        "mapped_model_lines": int(mapped_lines),
        "costed_lines": int(costed_lines),
        "lines_missing_costing": int(missing_costing_lines),
        "items": items,
        "note": "模型分析：成本优先 shipment_costing_results（三段成本），回退 bom_snapshot.trace；版本为主版本（按销售额最大）。净利润=(销售额-退款)-成本。",
    }


def sales_lines(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    page: int = 1,
    page_size: int = 50,
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
    shipment_no: Optional[str] = None,
    order_no: Optional[str] = None,
    product_link_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    include_missing: bool = True,
) -> Dict[str, Any]:
    """
    Sales analysis (line-level) for shipped orders within [start, end).
    - Revenue baseline: shipment_lines.revenue_amount
    - Cost baseline: latest bom_snapshot.trace.costing.total_cost (per shipment_line_id)
    - Rows without snapshots are kept (cost shows null) when include_missing is True.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    p = max(int(page or 1), 1)
    ps = max(min(int(page_size or 50), 200), 1)

    def _to_str(v: Any) -> Optional[str]:
        if v in (None, ""):
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)

    def _guess(raw: Dict[str, Any], keys: List[str]) -> Optional[str]:
        if not isinstance(raw, dict) or not raw:
            return None
        for k in keys:
            if k in raw and raw.get(k) not in (None, ""):
                return _to_str(raw.get(k))
        lower = {str(k).lower(): k for k in raw.keys()}
        for k in keys:
            src = lower.get(str(k).lower())
            if src and raw.get(src) not in (None, ""):
                return _to_str(raw.get(src))
        return None

    # Costing result per shipment_line_id (lightweight; supports 2025 no-snapshot mode)
    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
            models.ShipmentCostingResult.spec_hash.label("spec_hash"),
            models.ShipmentCostingResult.computed_at.label("computed_at"),
        )
        .subquery()
    )

    # Legacy fallback: latest bom_snapshot per shipment_line_id
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    # Active SKU -> model binding (BundleAsModel is represented as model_code like "B-XXXXYY").
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

    base_q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            res_sq.c.model_version_id,
            res_sq.c.spec_hash,
            binding_sq.c.bound_model_code,
            binding_sq.c.bound_model_name,
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .outerjoin(
            binding_sq,
            and_(
                binding_sq.c.sku_code == models.ShipmentLine.sku_code,
                binding_sq.c.rn == 1,
            ),
        )
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            _not_snapshot_cleared_pred(),
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
        )
    )
    if channel:
        base_q = base_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        base_q = base_q.filter(models.ShipmentLine.sku_code == sku_code)
    if shipment_no:
        base_q = base_q.filter(models.ShipmentLine.shipment_no == shipment_no)
    if order_no:
        base_q = base_q.filter(models.ShipmentLine.order_no == order_no)
    if product_link_id:
        base_q = base_q.filter(models.ShipmentLine.product_link_id == product_link_id)
    if bound_model_code:
        mc = str(bound_model_code or "").strip()
        if mc:
            base_q = base_q.filter(func.coalesce(binding_sq.c.bound_model_code, "") == mc)
    if bundle_template_code:
        b = str(bundle_template_code or "").strip()
        if b:
            base_q = base_q.filter(
                func.coalesce(models.ShipmentLine.metadata_json["bundle_template_code"].as_string(), "") == b
            )
    if bundle_preset_selector:
        s = str(bundle_preset_selector or "").strip().upper()
        if s:
            base_q = base_q.filter(
                func.coalesce(models.ShipmentLine.metadata_json["bundle_preset_selector"].as_string(), "") == s
            )

    # When user requests "only costed", pagination total must match the rows we will return.
    # We define "costed" as having a costing result OR a legacy BOM snapshot.
    if not include_missing:
        base_q = base_q.filter(or_(res_sq.c.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)))

    total = base_q.count()
    rows = (
        base_q.order_by(models.ShipmentLine.completed_at.desc(), models.ShipmentLine.created_at.desc())
        .offset((p - 1) * ps)
        .limit(ps)
        .all()
    )

    # Avoid N+1 lookups for bundle phrase presets on the current page.
    bundle_phrase_cache: Dict[Tuple[str, str], Optional[str]] = {}

    items: List[Dict[str, Any]] = []
    with_bom = 0
    missing_costing = 0

    for (
        line,
        result_line_id,
        bom_snapshot_id,
        snap_trace_json,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        model_version_id,
        spec_hash,
        bound_model_code,
        bound_model_name,
    ) in rows:
        meta_line = getattr(line, "metadata_json", None) or {}
        if not isinstance(meta_line, dict):
            meta_line = {}
        bundle_code = str(meta_line.get("bundle_template_code") or "").strip() or None
        bundle_sel = str(meta_line.get("bundle_preset_selector") or "").strip().upper() or None
        bundle_phrase: Optional[str] = None
        if bundle_code and bundle_sel:
            ck = (bundle_code, bundle_sel)
            if ck in bundle_phrase_cache:
                bundle_phrase = bundle_phrase_cache[ck]
            else:
                # Construct BundleAsModel-like code (B-<tpl><sel>) for phrase lookup.
                _, _, phrase = _try_get_bundle_phrase_preset(db, f"B-{bundle_code}{bundle_sel}")
                bundle_phrase_cache[ck] = phrase
                bundle_phrase = phrase
        raw = getattr(line, "raw_row_json", None) or getattr(line, "raw_row", None) or {}
        payment_at = _guess(raw, ["付款时间", "支付时间", "pay_time", "paid_at", "付款日期", "payment_at", "payment_time"])
        sku_no = _guess(raw, ["货品编号", "商品编号", "货品编码", "goods_code", "sku_no", "product_code"])
        sku_name = _guess(raw, ["货品名称", "商品名称", "商品标题", "title", "goods_name", "product_name"])
        logistics_company = _guess(raw, ["物流公司", "快递公司", "carrier", "logistics_company"])
        logistics_no = _guess(raw, ["物流单号", "快递单号", "tracking_no", "logistics_no", "waybill_no"])

        qty = _d(getattr(line, "qty", None))
        revenue = _d(getattr(line, "revenue_amount", None))
        sale_unit = (revenue / qty) if qty > 0 else None

        has_result = bool(result_line_id)
        has_snap = bool(bom_snapshot_id)
        cost_amount: Optional[Decimal] = None
        cost_unit: Optional[Decimal] = None
        status = "missing_snapshot"
        note = None
        if has_result:
            with_bom += 1
            # Prefer stored total cost; fall back to components sum.
            cost_amount = _d(cost_total)
            if cost_amount == 0 and cost_total in (None, "", 0):
                parts = _d(cost_material_total) + _d(cost_process_total) + _d(cost_overhead_total)
                cost_amount = parts if parts != 0 else None
            if cost_amount is None:
                status = "missing_costing"
                missing_costing += 1
                note = "计价结果缺成本字段（cost_total 为空）"
            else:
                status = "costed"
                if qty > 0:
                    cost_unit = cost_amount / qty
        elif has_snap:
            with_bom += 1
            cost_amount, status = _extract_total_cost_from_trace(snap_trace_json)
            if status == "missing_costing":
                missing_costing += 1
                note = "BOM 快照缺成本字段（trace.costing.total_cost 为空）"
            if cost_amount is not None and qty > 0:
                cost_unit = cost_amount / qty
        else:
            if include_missing:
                note = "缺计价结果（未计价）"
            else:
                continue

        mark = None
        if status == "missing_snapshot":
            mark = "未计价"
        elif status == "missing_costing":
            mark = "缺成本"

        items.append(
            {
                "shipment_line_id": str(line.id),
                "batch_id": str(getattr(line, "batch_id", "")) if getattr(line, "batch_id", None) else None,
                "row_index": getattr(line, "row_index", None),
                "payment_at": payment_at,
                "completed_at": getattr(line, "completed_at", None),
                "channel": getattr(line, "channel", None),
                "sku_no": sku_no,
                "sku_name": sku_name,
                "spec_text": getattr(line, "spec_text", None),
                "sku_code": getattr(line, "sku_code", None),
                "sale_unit_price": sale_unit,
                "qty": qty if qty != 0 else None,
                "revenue_amount": revenue if revenue != 0 else None,
                "cost_unit_price": cost_unit,
                "cost_amount": cost_amount,
                "order_no": getattr(line, "order_no", None),
                "product_link_id": getattr(line, "product_link_id", None),
                "logistics_company": logistics_company,
                "logistics_no": logistics_no,
                "mark": mark,
                "bundle_template_code": bundle_code,
                "bundle_preset_selector": bundle_sel,
                "bundle_preset_phrase": bundle_phrase,
                "bound_model_code": str(bound_model_code).strip() if bound_model_code not in (None, "") else None,
                "bound_model_name": str(bound_model_name).strip() if bound_model_name not in (None, "") else None,
                "bom_snapshot_id": str(bom_snapshot_id) if has_snap else None,
                "status": status,
                "note": note,
            }
        )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": int(total),
        "page": p,
        "page_size": ps,
        "lines_with_bom_snapshots": int(with_bom),
        "lines_missing_costing": int(missing_costing),
        "items": items,
        "note": "明细口径：cost 优先来自计价结果（shipment_costing_results.cost_total），缺失时回退到最新 BOM 快照 trace.costing.total_cost。缺计价结果/快照的行成本显示为空。",
    }


def sales_profit_dashboard(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["week", "month"] = "week",
    channel: Optional[str] = None,
    top_n: int = 12,
) -> Dict[str, Any]:
    """
    销售利润看板（给运营判断“哪些赚钱/哪些亏钱”）：
    - 时间口径：发货完成时间 completed_at（与成本结果一致）
    - 利润口径：仅对“有成本”的行计算利润，避免缺成本导致利润虚高
      gross_profit = sum(revenue - cost) over costed lines
    - 给出成本覆盖率（按销售额/按行数）
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    def _period_label(dt: datetime) -> str:
        if group_by == "month":
            d = _utc_date(dt)
            return d.strftime("%Y-%m")
        d = _utc_date(dt)
        start_date = d - timedelta(days=d.weekday())  # Monday
        end_date = start_date + timedelta(days=6)
        return f"{start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}"

    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        _not_snapshot_cleared_pred(),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    ship_rows = ship_q.all()

    # latest bom_snapshot per shipment_line_id (legacy fallback)
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    cost_q = (
        db.query(
            models.ShipmentLine.id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            snap_sq.c.trace_json.label("trace_json"),
        )
        .select_from(models.ShipmentLine)
        .outerjoin(models.ShipmentCostingResult, models.ShipmentLine.id == models.ShipmentCostingResult.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            _not_snapshot_cleared_pred(),
            or_(models.ShipmentCostingResult.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)),
        )
    )
    if channel:
        cost_q = cost_q.filter(models.ShipmentLine.channel == channel)
    cost_rows = cost_q.all()

    cost_by_line: Dict[str, Decimal] = {}
    for r in cost_rows:
        if r.cost_total not in (None, ""):
            c = _d(r.cost_total)
            if c > 0:
                cost_by_line[str(r.shipment_line_id)] = c
                continue
        c2, status = _extract_total_cost_from_trace(r.trace_json)
        if status == "costed" and c2 is not None and c2 > 0:
            cost_by_line[str(r.shipment_line_id)] = c2

    # model mapping by sku_code (active mapping)
    sku_to_model: Dict[str, Tuple[str, Optional[str]]] = {}
    if ship_rows:
        sku_codes = [str(s.sku_code) for s in ship_rows if s.sku_code]
        uniq = list(dict.fromkeys(sku_codes))
        chunk_size = 800
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            rows = (
                db.query(
                    models.SkuModelVersionMapping.sku_code,
                    models.ProductModel.model_code,
                    models.ProductModel.model_name,
                )
                .select_from(models.SkuModelVersionMapping)
                .join(
                    models.ProductModelVersion,
                    and_(
                        models.ProductModelVersion.is_archived.is_(False),
                        models.ProductModelVersion.id == models.SkuModelVersionMapping.model_version_id,
                    ),
                )
                .join(
                    models.ProductModel,
                    and_(models.ProductModel.is_archived.is_(False), models.ProductModel.id == models.ProductModelVersion.model_id),
                )
                .filter(
                    models.SkuModelVersionMapping.is_archived.is_(False),
                    models.SkuModelVersionMapping.is_active.is_(True),
                    models.SkuModelVersionMapping.sku_code.in_(chunk),
                )
                .all()
            )
            for sku_code, model_code, model_name in rows:
                if sku_code and model_code:
                    sku_to_model[str(sku_code)] = (str(model_code), str(model_name) if model_name else None)

    kpi: Dict[str, Any] = {
        "shipped_qty": Decimal("0"),
        "revenue_amount": Decimal("0"),
        "shipment_lines_total": 0,
        "costed_revenue_amount": Decimal("0"),
        "costed_lines": 0,
        "lines_missing_costing": 0,
        "costed_revenue_rate": None,
        "cost_amount": Decimal("0"),
        "gross_profit": Decimal("0"),
        "gross_margin": None,
    }

    series: Dict[str, Dict[str, Any]] = {}
    sku_agg: Dict[str, Dict[str, Any]] = {}
    model_agg: Dict[str, Dict[str, Any]] = {}
    sku_spec_count: Dict[Tuple[str, str], int] = {}

    for line in ship_rows:
        if not line.completed_at:
            continue
        lid = str(line.id)
        period = _period_label(line.completed_at)
        sku = str(line.sku_code or "").strip()
        spec = str(line.spec_text or "").strip()
        qty = _d(line.qty)
        rev = _d(line.revenue_amount)

        kpi["shipment_lines_total"] += 1
        kpi["shipped_qty"] += qty
        kpi["revenue_amount"] += rev

        b = series.setdefault(
            period,
            {
                "period": period,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "costed_revenue_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "gross_profit": Decimal("0"),
                "gross_margin": None,
                "shipment_lines_total": 0,
                "costed_lines": 0,
                "lines_missing_costing": 0,
            },
        )
        b["shipment_lines_total"] += 1
        b["shipped_qty"] += qty
        b["revenue_amount"] += rev

        cost = cost_by_line.get(lid)
        if cost is None:
            kpi["lines_missing_costing"] += 1
            b["lines_missing_costing"] += 1
        else:
            kpi["costed_lines"] += 1
            kpi["costed_revenue_amount"] += rev
            kpi["cost_amount"] += cost
            kpi["gross_profit"] += (rev - cost)

            b["costed_lines"] += 1
            b["costed_revenue_amount"] += rev
            b["cost_amount"] += cost
            b["gross_profit"] += (rev - cost)

        if sku:
            sb = sku_agg.setdefault(
                sku,
                {
                    "sku_code": sku,
                    "spec_text": None,
                    "bound_model_code": (sku_to_model.get(sku, (None, None))[0] if sku in sku_to_model else None),
                    "bound_model_name": (sku_to_model.get(sku, (None, None))[1] if sku in sku_to_model else None),
                    "bundle_template_code": None,
                    "bundle_preset_selector": None,
                    "bundle_preset_phrase": None,
                    "shipped_qty": Decimal("0"),
                    "revenue_amount": Decimal("0"),
                    "costed_revenue_amount": Decimal("0"),
                    "cost_amount": Decimal("0"),
                    "gross_profit": Decimal("0"),
                    "gross_margin": None,
                    "shipment_lines_total": 0,
                    "costed_lines": 0,
                },
            )
            sb["shipment_lines_total"] += 1
            sb["shipped_qty"] += qty
            sb["revenue_amount"] += rev
            if cost is not None:
                sb["costed_lines"] += 1
                sb["costed_revenue_amount"] += rev
                sb["cost_amount"] += cost
                sb["gross_profit"] += (rev - cost)
            if spec:
                sku_spec_count[(sku, spec)] = sku_spec_count.get((sku, spec), 0) + 1

            m = sku_to_model.get(sku)
            if m:
                mc, mn = m
                mb = model_agg.setdefault(
                    mc,
                    {
                        "model_code": mc,
                        "model_name": mn,
                        "shipped_qty": Decimal("0"),
                        "revenue_amount": Decimal("0"),
                        "costed_revenue_amount": Decimal("0"),
                        "cost_amount": Decimal("0"),
                        "gross_profit": Decimal("0"),
                        "gross_margin": None,
                        "shipment_lines_total": 0,
                        "costed_lines": 0,
                    },
                )
                mb["shipment_lines_total"] += 1
                mb["shipped_qty"] += qty
                mb["revenue_amount"] += rev
                if cost is not None:
                    mb["costed_lines"] += 1
                    mb["costed_revenue_amount"] += rev
                    mb["cost_amount"] += cost
                    mb["gross_profit"] += (rev - cost)

    # fill spec_text for sku (most common)
    best_spec: Dict[str, Tuple[int, str]] = {}
    for (sku, spec), c in sku_spec_count.items():
        prev = best_spec.get(sku)
        if prev is None or c > prev[0]:
            best_spec[sku] = (c, spec)
    for sku, sb in sku_agg.items():
        sb["spec_text"] = best_spec.get(sku, (0, None))[1]

    # finalize KPI margins (profit computed only on costed revenue)
    kpi_costed_rev = _d(kpi["costed_revenue_amount"])
    kpi_rev = _d(kpi["revenue_amount"])
    if kpi_rev > 0:
        kpi["costed_revenue_rate"] = (kpi_costed_rev / kpi_rev)
    if kpi_costed_rev > 0:
        kpi["gross_margin"] = (_d(kpi["gross_profit"]) / kpi_costed_rev)

    # finalize series margins
    series_items: List[Dict[str, Any]] = []
    for p in sorted(series.keys()):
        b = series[p]
        costed_rev = _d(b["costed_revenue_amount"])
        if costed_rev > 0:
            b["gross_margin"] = (_d(b["gross_profit"]) / costed_rev)
        series_items.append(b)

    def _finalize_bucket(x: Dict[str, Any]) -> Dict[str, Any]:
        # IMPORTANT: gross_profit is computed only on costed lines.
        # Therefore gross_margin must use costed_revenue_amount as denominator, not total revenue_amount,
        # otherwise margin will be artificially "too low" when there are missing-cost lines.
        rev = _d(x.get("costed_revenue_amount") or x.get("revenue_amount"))
        gp = _d(x["gross_profit"])
        x["gross_margin"] = (gp / rev) if rev > 0 else None
        return x

    # rankings: only entries with at least 1 costed line (avoid fake profit)
    sku_items_all = [_finalize_bucket(v) for v in sku_agg.values() if int(v.get("costed_lines") or 0) > 0]
    sku_items_all.sort(key=lambda x: (_d(x["gross_profit"]), _d(x["revenue_amount"])), reverse=True)
    top_skus_profit = sku_items_all[:top_n]
    top_skus_loss = sorted(sku_items_all, key=lambda x: (_d(x["gross_profit"]), _d(x["revenue_amount"])))[:top_n]

    model_items_all = [_finalize_bucket(v) for v in model_agg.values() if int(v.get("costed_lines") or 0) > 0]
    model_items_all.sort(key=lambda x: (_d(x["gross_profit"]), _d(x["revenue_amount"])), reverse=True)
    top_models_profit = model_items_all[:top_n]
    top_models_loss = sorted(model_items_all, key=lambda x: (_d(x["gross_profit"]), _d(x["revenue_amount"])))[:top_n]

    # Enrich top models for BundleAsModel display (optional).
    def _enrich_bundle_fields(items0: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for it in items0:
            mc = str(it.get("model_code") or "")
            tpl_code, selector, phrase = _try_get_bundle_phrase_preset(db, mc)
            it2 = dict(it)
            it2["bundle_template_code"] = tpl_code
            it2["bundle_preset_selector"] = selector
            it2["bundle_preset_phrase"] = phrase
            out.append(it2)
        return out

    top_models_profit = _enrich_bundle_fields(top_models_profit)
    top_models_loss = _enrich_bundle_fields(top_models_loss)

    # Enrich top SKUs for model/bundle display.
    def _enrich_sku_bound_fields(items0: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for it in items0:
            mc = str(it.get("bound_model_code") or "").strip()
            tpl_code, selector, phrase = _try_get_bundle_phrase_preset(db, mc)
            it2 = dict(it)
            it2["bundle_template_code"] = tpl_code
            it2["bundle_preset_selector"] = selector
            it2["bundle_preset_phrase"] = phrase
            out.append(it2)
        return out

    top_skus_profit = _enrich_sku_bound_fields(top_skus_profit)
    top_skus_loss = _enrich_sku_bound_fields(top_skus_loss)

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "top_n": int(top_n),
        "kpis": kpi,
        "series": series_items,
        "top_skus_profit": top_skus_profit,
        "top_skus_loss": top_skus_loss,
        "top_models_profit": top_models_profit,
        "top_models_loss": top_models_loss,
        "note": "利润仅在“已计价行”上计算；请关注成本覆盖率 costed_revenue_rate，避免因缺成本误判。",
    }


def model_insights_summary(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    channel: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
) -> Dict[str, Any]:
    """
    模型分析（统计榜单）：
    - 聚合维度：模型（可选按店铺过滤；若不传则为全店铺汇总）
    - 指标：发货数量/销售额/三段成本/毛利/退款/净利润 + 覆盖率（按行数）
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    if bundle_template_code:
        b = str(bundle_template_code or "").strip()
        if b:
            ship_q = ship_q.filter(
                func.coalesce(models.ShipmentLine.metadata_json["bundle_template_code"].as_string(), "") == b
            )
    if bundle_preset_selector:
        s = str(bundle_preset_selector or "").strip().upper()
        if s:
            ship_q = ship_q.filter(
                func.coalesce(models.ShipmentLine.metadata_json["bundle_preset_selector"].as_string(), "") == s
            )
    total_ship_lines = int(ship_q.count() or 0)

    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )

    snap_sq = (
        db.query(
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_sq.c.model_version_id)
    q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id.label("res_ship_line_id"),
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            snap_sq.c.trace_json,
            mv_id_expr.label("model_version_id"),
            models.ProductModelVersion.version_kind,
            models.ProductModelVersion.version_status,
            models.ProductModelVersion.version_label,
            models.ProductModel.id.label("model_id"),
            models.ProductModel.model_code.label("model_code"),
            models.ProductModel.model_name.label("model_name"),
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .outerjoin(
            models.ProductModelVersion,
            and_(models.ProductModelVersion.id == mv_id_expr, models.ProductModelVersion.is_archived.is_(False)),
        )
        .outerjoin(models.ProductModel, and_(models.ProductModel.id == models.ProductModelVersion.model_id, models.ProductModel.is_archived.is_(False)))
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        q = q.filter(models.ShipmentLine.channel == channel)
    if bundle_template_code:
        b = str(bundle_template_code or "").strip()
        if b:
            q = q.filter(func.coalesce(models.ShipmentLine.metadata_json["bundle_template_code"].as_string(), "") == b)
    if bundle_preset_selector:
        s = str(bundle_preset_selector or "").strip().upper()
        if s:
            q = q.filter(func.coalesce(models.ShipmentLine.metadata_json["bundle_preset_selector"].as_string(), "") == s)
    rows = q.all()

    refund_q = db.query(
        models.ShipmentLine.id.label("shipment_line_id"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    if bundle_template_code:
        b = str(bundle_template_code or "").strip()
        if b:
            refund_q = refund_q.filter(
                func.coalesce(models.ShipmentLine.metadata_json["bundle_template_code"].as_string(), "") == b
            )
    if bundle_preset_selector:
        s = str(bundle_preset_selector or "").strip().upper()
        if s:
            refund_q = refund_q.filter(
                func.coalesce(models.ShipmentLine.metadata_json["bundle_preset_selector"].as_string(), "") == s
            )
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_by_line = {
        str(r.shipment_line_id): {"refund_amount": _d(r.refund_amount), "returned_qty": _d(r.returned_qty)}
        for r in refund_q.all()
    }

    mapped_lines = 0
    costed_lines = 0
    missing_costing_lines = 0

    agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (
        line,
        res_ship_line_id,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        snap_trace_json,
        mv_id,
        ver_kind,
        ver_status,
        ver_label,
        mdl_id,
        mdl_code,
        mdl_name,
    ) in rows:
        if not line.completed_at:
            continue
        if not mdl_id or not mdl_code or not mdl_name:
            continue

        mapped_lines += 1
        key = (str(line.channel or "").strip(), str(mdl_id))
        bucket = agg.setdefault(
            key,
            {
                "channel": str(line.channel or "").strip() or None,
                "model_id": str(mdl_id),
                "model_code": str(mdl_code),
                "model_name": str(mdl_name),
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_material_amount": Decimal("0"),
                "cost_process_amount": Decimal("0"),
                "cost_overhead_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "line_count": 0,
                "costed_line_count": 0,
                "missing_costing_line_count": 0,
                "_ver_rev": {},
                "_ver_info": {},
            },
        )

        bucket["line_count"] += 1
        qty = _d(line.qty)
        revenue = _d(line.revenue_amount)
        bucket["shipped_qty"] += qty
        bucket["revenue_amount"] += revenue
        ref = refund_by_line.get(str(line.id)) or {"refund_amount": Decimal("0"), "returned_qty": Decimal("0")}
        bucket["refund_amount"] += _d(ref.get("refund_amount"))
        bucket["returned_qty"] += _d(ref.get("returned_qty"))

        mv_id_str = str(mv_id or "").strip()
        if mv_id_str:
            bucket["_ver_rev"][mv_id_str] = _d(bucket["_ver_rev"].get(mv_id_str, 0)) + revenue
            bucket["_ver_info"][mv_id_str] = (str(ver_kind or ""), str(ver_status or ""), str(ver_label or "") or None)

        if res_ship_line_id is not None:
            m = _d(cost_material_total)
            p = _d(cost_process_total)
            o = _d(cost_overhead_total)
            total_src = cost_total
            if total_src in (None, ""):
                total_src = m + p + o
            total = _d(total_src)
            if total == 0 and (cost_total in (None, "", 0)) and (cost_material_total in (None, "")) and (cost_process_total in (None, "")) and (cost_overhead_total in (None, "")):
                snap_total, sm, sp, so, s = _extract_cost_breakdown_from_trace(snap_trace_json)
                if s == "costed":
                    bucket["costed_line_count"] += 1
                    costed_lines += 1
                    bucket["cost_material_amount"] += _d(sm)
                    bucket["cost_process_amount"] += _d(sp)
                    bucket["cost_overhead_amount"] += _d(so)
                    bucket["cost_amount"] += _d(snap_total)
                else:
                    bucket["missing_costing_line_count"] += 1
                    missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += m
                bucket["cost_process_amount"] += p
                bucket["cost_overhead_amount"] += o
                bucket["cost_amount"] += total
        else:
            total, m, p, o, status = _extract_cost_breakdown_from_trace(snap_trace_json)
            if status == "missing_costing":
                bucket["missing_costing_line_count"] += 1
                missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += _d(m)
                bucket["cost_process_amount"] += _d(p)
                bucket["cost_overhead_amount"] += _d(o)
                bucket["cost_amount"] += _d(total)

    items: List[Dict[str, Any]] = []
    for _, b in agg.items():
        ver_rev = b.pop("_ver_rev", {}) or {}
        ver_info = b.pop("_ver_info", {}) or {}
        if ver_rev:
            top_ver_id = max(ver_rev.items(), key=lambda kv: kv[1])[0]
            kind, status, label = ver_info.get(top_ver_id, ("", "", None))
            b["top_version_id"] = top_ver_id
            b["top_version_kind"] = kind or None
            b["top_version_status"] = status or None
            b["top_version_label"] = label
            b["version_count"] = len(ver_rev)
        else:
            b["top_version_id"] = None
            b["top_version_kind"] = None
            b["top_version_status"] = None
            b["top_version_label"] = None
            b["version_count"] = 0

        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None
        items.append(
            {
                **b,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
            }
        )

    items.sort(key=lambda r: _d(r.get("revenue_amount")), reverse=True)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "total_shipment_lines": total_ship_lines,
        "mapped_model_lines": int(mapped_lines),
        "costed_lines": int(costed_lines),
        "lines_missing_costing": int(missing_costing_lines),
        "items": items,
        "note": "模型统计榜单：按模型聚合；成本优先 shipment_costing_results（三段），回退 bom_snapshot.trace；覆盖率按行数。",
    }


def model_insights_detail(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    model_code: str,
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
) -> Dict[str, Any]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    mdl = (
        db.query(models.ProductModel)
        .filter(models.ProductModel.model_code == model_code, models.ProductModel.is_archived.is_(False))
        .first()
    )
    if not mdl:
        raise ValueError("模型不存在或已归档")

    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )
    snap_sq = (
        db.query(
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_sq.c.model_version_id)
    base_q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id.label("res_ship_line_id"),
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            snap_sq.c.trace_json,
            mv_id_expr.label("model_version_id"),
            models.ProductModelVersion.version_kind,
            models.ProductModelVersion.version_status,
            models.ProductModelVersion.version_label,
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .join(
            models.ProductModelVersion,
            and_(
                models.ProductModelVersion.id == mv_id_expr,
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModelVersion.model_id == mdl.id,
            ),
        )
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        base_q = base_q.filter(models.ShipmentLine.channel == channel)
    if bundle_template_code:
        b = str(bundle_template_code or "").strip()
        if b:
            base_q = base_q.filter(func.coalesce(models.ShipmentLine.metadata_json["bundle_template_code"].as_string(), "") == b)
    if bundle_preset_selector:
        s = str(bundle_preset_selector or "").strip().upper()
        if s:
            base_q = base_q.filter(func.coalesce(models.ShipmentLine.metadata_json["bundle_preset_selector"].as_string(), "") == s)
    rows = base_q.all()

    ver_agg: Dict[str, Dict[str, Any]] = {}
    for (
        line,
        res_ship_line_id,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        snap_trace_json,
        mv_id,
        ver_kind,
        ver_status,
        ver_label,
    ) in rows:
        vid = str(mv_id or "").strip()
        if not vid:
            continue
        b = ver_agg.setdefault(
            vid,
            {
                "version_id": vid,
                "version_kind": str(ver_kind or "") or None,
                "version_status": str(ver_status or "") or None,
                "version_label": str(ver_label or "") or None,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_material_amount": Decimal("0"),
                "cost_process_amount": Decimal("0"),
                "cost_overhead_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "line_count": 0,
                "costed_line_count": 0,
                "missing_costing_line_count": 0,
            },
        )
        b["line_count"] += 1
        b["shipped_qty"] += _d(line.qty)
        revenue = _d(line.revenue_amount)
        b["revenue_amount"] += revenue

        if res_ship_line_id is not None:
            m = _d(cost_material_total)
            p = _d(cost_process_total)
            o = _d(cost_overhead_total)
            total_src = cost_total
            if total_src in (None, ""):
                total_src = m + p + o
            total = _d(total_src)
            if total == 0 and (cost_total in (None, "", 0)) and (cost_material_total in (None, "")) and (cost_process_total in (None, "")) and (cost_overhead_total in (None, "")):
                snap_total, sm, sp, so, s = _extract_cost_breakdown_from_trace(snap_trace_json)
                if s == "costed":
                    b["costed_line_count"] += 1
                    b["cost_material_amount"] += _d(sm)
                    b["cost_process_amount"] += _d(sp)
                    b["cost_overhead_amount"] += _d(so)
                    b["cost_amount"] += _d(snap_total)
                else:
                    b["missing_costing_line_count"] += 1
            else:
                b["costed_line_count"] += 1
                b["cost_material_amount"] += m
                b["cost_process_amount"] += p
                b["cost_overhead_amount"] += o
                b["cost_amount"] += total
        else:
            total, m, p, o, status = _extract_cost_breakdown_from_trace(snap_trace_json)
            if status == "missing_costing":
                b["missing_costing_line_count"] += 1
            else:
                b["costed_line_count"] += 1
                b["cost_material_amount"] += _d(m)
                b["cost_process_amount"] += _d(p)
                b["cost_overhead_amount"] += _d(o)
                b["cost_amount"] += _d(total)

    versions: List[Dict[str, Any]] = []
    for b in ver_agg.values():
        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        versions.append({**b, "gross_profit": gross_profit, "gross_margin": gross_margin})
    versions.sort(key=lambda r: _d(r.get("revenue_amount")), reverse=True)

    selected_version_id = str(version_id or (versions[0]["version_id"] if versions else "")).strip() or None

    sample_row = None
    if selected_version_id:
        sample_row = (
            base_q.filter(mv_id_expr == selected_version_id)
            .order_by(models.ShipmentLine.completed_at.desc(), models.ShipmentLine.created_at.desc())
            .first()
        )
    sample_line = sample_row[0] if sample_row else None

    bom: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    if sample_line and selected_version_id:
        try:
            qty = _d(sample_line.qty) if sample_line.qty not in (None, "") else Decimal("1")
            bom = bom_generation_service.generate_bom(
                db,
                spec_text=str(sample_line.spec_text or ""),
                model_version_id=str(selected_version_id),
                sku_code=str(sample_line.sku_code or ""),
                quantity=qty,
                include_disabled_variants=False,
            )
            note = "右侧 BOM 为样本发货行“现场生成”（与测试台 bom/generate 同口径）。"
        except Exception as e:  # noqa: BLE001
            bom = {"final_material_lines": [], "trace": {"costing": {}, "inventory": {}}}
            note = f"生成样本 BOM 失败：{e}"

    persisted = []
    if sample_line:
        persisted_rows = (
            db.query(models.ShipmentInventoryDeductionLine)
            .filter(models.ShipmentInventoryDeductionLine.shipment_line_id == sample_line.id)
            .order_by(models.ShipmentInventoryDeductionLine.material_code.asc())
            .all()
        )
        for r in persisted_rows:
            meta = getattr(r, "metadata_json", None) or {}
            sources = meta.get("sources")
            persisted.append(
                {
                    "material_code": getattr(r, "material_code", None),
                    "material_name": getattr(r, "material_name", None),
                    "unit_of_measure": getattr(r, "unit_of_measure", None),
                    "quantity": getattr(r, "quantity", None),
                    "sources": (len(sources) if isinstance(sources, list) else None),
                }
            )

    base_material_lines = []
    base_process_lines = []
    if selected_version_id:
        try:
            mats = product_model_service.list_version_material_lines(db, str(selected_version_id))
            for r in mats or []:
                base_material_lines.append(
                    {
                        "material_type": getattr(r, "material_type", None),
                        "material_ref_id": getattr(r, "material_ref_id", None),
                        "material_code": getattr(r, "material_code", None),
                        "material_name": getattr(r, "material_name", None),
                        "unit_of_measure": getattr(r, "unit_of_measure", None),
                        "calculation_method": getattr(r, "calculation_method", None),
                        "base_quantity": getattr(r, "base_quantity", None),
                        "loss_rate": getattr(r, "loss_rate", None),
                        "unit_cost": getattr(r, "unit_cost", None),
                        "sequence_order": getattr(r, "sequence_order", None),
                        "notes": getattr(r, "notes", None),
                    }
                )
            procs = product_model_service.list_version_process_lines(db, str(selected_version_id))
            for r in procs or []:
                p = getattr(r, "process", None)
                base_process_lines.append(
                    {
                        "process_id": getattr(r, "process_id", None),
                        "process_code": getattr(p, "process_code", None) if p is not None else None,
                        "process_name": getattr(p, "process_name", None) if p is not None else None,
                        "team_name": getattr(p, "team_name", None) if p is not None else None,
                        "pricing_method": getattr(p, "pricing_method", None) if p is not None else None,
                        "piece_rate": getattr(p, "piece_rate", None) if p is not None else None,
                        "rate_per_minute": getattr(p, "rate_per_minute", None) if p is not None else None,
                        "notes": getattr(r, "notes", None),
                    }
                )
        except Exception:
            pass

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "model_id": str(mdl.id),
        "model_code": str(mdl.model_code),
        "model_name": str(mdl.model_name),
        "selected_version_id": selected_version_id,
        "versions": versions,
        "sample_shipment_line_id": str(sample_line.id) if sample_line else None,
        "sample_completed_at": sample_line.completed_at if sample_line else None,
        "sample_sku_code": str(sample_line.sku_code) if sample_line and sample_line.sku_code else None,
        "sample_spec_text": str(sample_line.spec_text) if sample_line and sample_line.spec_text else None,
        "sample_qty": sample_line.qty if sample_line else None,
        "bom": bom,
        "persisted_deductions": persisted,
        "base_material_lines": base_material_lines,
        "base_process_lines": base_process_lines,
        "note": note,
    }


def _latest_bom_snapshot_sq(db: Session):
    """
    Cross-dialect "latest snapshot per shipment_line_id" subquery.
    Avoid DISTINCT ON (postgres-only).
    """
    snap_max = (
        db.query(
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            func.max(models.BomSnapshot.created_at).label("max_created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .group_by(models.BomSnapshot.shipment_line_id)
        .subquery()
    )
    snap_latest = (
        db.query(
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .join(
            snap_max,
            and_(
                models.BomSnapshot.shipment_line_id == snap_max.c.shipment_line_id,
                models.BomSnapshot.created_at == snap_max.c.max_created_at,
            ),
        )
        .subquery()
    )
    return snap_latest


def _mapped_model_lines_sq(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    channel: Optional[str],
    model_code: str,
    version_id: Optional[str],
):
    """
    Return a subquery of mapped shipment lines:
    - shipment_line_id
    - qty
    - model_version_id (resolved by coalesce(costing_result, latest snapshot))
    """
    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )
    snap_latest = _latest_bom_snapshot_sq(db)
    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_latest.c.model_version_id)

    q = (
        db.query(
            models.ShipmentLine.id.label("shipment_line_id"),
            models.ShipmentLine.qty.label("qty"),
            mv_id_expr.label("model_version_id"),
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_latest, models.ShipmentLine.id == snap_latest.c.shipment_line_id)
        .join(
            models.ProductModelVersion,
            and_(models.ProductModelVersion.id == mv_id_expr, models.ProductModelVersion.is_archived.is_(False)),
        )
        .join(
            models.ProductModel,
            and_(models.ProductModel.id == models.ProductModelVersion.model_id, models.ProductModel.is_archived.is_(False)),
        )
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            models.ProductModel.model_code == model_code,
        )
    )
    if channel:
        q = q.filter(models.ShipmentLine.channel == channel)
    if version_id:
        q = q.filter(mv_id_expr == version_id)
    return q.subquery()


def model_usage_materials_summary(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    model_code: str,
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate REAL material usage across shipped lines for a model (and optional version),
    based on persisted inventory deduction lines.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    # baseline shipments (all lines in range)
    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = int(ship_q.count() or 0)

    mapped_sq = _mapped_model_lines_sq(db, start=start, end=end, channel=channel, model_code=model_code, version_id=version_id)
    mapped_lines = int(db.query(func.count(mapped_sq.c.shipment_line_id)).scalar() or 0)
    shipped_qty_total = _d(db.query(func.coalesce(func.sum(mapped_sq.c.qty), 0)).scalar())

    # group by material
    items_rows = (
        db.query(
            models.ShipmentInventoryDeductionLine.material_id.label("material_id"),
            models.ShipmentInventoryDeductionLine.material_code.label("material_code"),
            models.ShipmentInventoryDeductionLine.material_name.label("material_name"),
            models.ShipmentInventoryDeductionLine.unit_of_measure.label("unit_of_measure"),
            func.coalesce(func.sum(models.ShipmentInventoryDeductionLine.quantity), 0).label("total_quantity"),
            func.count(func.distinct(models.ShipmentInventoryDeductionLine.shipment_line_id)).label("line_count"),
        )
        .join(mapped_sq, models.ShipmentInventoryDeductionLine.shipment_line_id == mapped_sq.c.shipment_line_id)
        .group_by(
            models.ShipmentInventoryDeductionLine.material_id,
            models.ShipmentInventoryDeductionLine.material_code,
            models.ShipmentInventoryDeductionLine.material_name,
            models.ShipmentInventoryDeductionLine.unit_of_measure,
        )
        .all()
    )

    # coverage: distinct shipment_line_id with at least 1 deduction line
    covered_sq = (
        db.query(models.ShipmentInventoryDeductionLine.shipment_line_id.label("shipment_line_id"))
        .join(mapped_sq, models.ShipmentInventoryDeductionLine.shipment_line_id == mapped_sq.c.shipment_line_id)
        .distinct()
        .subquery()
    )
    lines_with_deductions = int(db.query(func.count(covered_sq.c.shipment_line_id)).scalar() or 0)
    shipped_qty_covered = _d(
        db.query(func.coalesce(func.sum(mapped_sq.c.qty), 0))
        .select_from(mapped_sq)
        .join(covered_sq, mapped_sq.c.shipment_line_id == covered_sq.c.shipment_line_id)
        .scalar()
    )

    items: List[Dict[str, Any]] = []
    for r in items_rows:
        items.append(
            {
                "material_id": str(r.material_id) if r.material_id else None,
                "material_code": r.material_code,
                "material_name": r.material_name,
                "unit_of_measure": r.unit_of_measure,
                "total_quantity": _d(r.total_quantity),
                "line_count": int(r.line_count or 0),
            }
        )
    items.sort(key=lambda x: (str(x.get("material_code") or ""), str(x.get("material_name") or "")))

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "model_code": model_code,
        "version_id": version_id,
        "total_shipment_lines": total_ship_lines,
        "mapped_model_lines": mapped_lines,
        "shipped_qty_total": shipped_qty_total,
        "lines_with_deductions": lines_with_deductions,
        "shipped_qty_covered": shipped_qty_covered,
        "items": items,
        "note": "物料合计=按发货行汇总的扣库明细（shipment_inventory_deduction_lines）。覆盖率取决于该范围内有无落库扣库明细/计价结果。",
    }


def model_usage_processes_summary(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    model_code: str,
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate REAL process usage across shipped lines for a model (and optional version),
    based on latest bom_snapshot.trace.costing.process_lines (when available).
    Note: 2025 lightweight mode may not persist per-line process details.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = int(ship_q.count() or 0)

    mapped_sq = _mapped_model_lines_sq(db, start=start, end=end, channel=channel, model_code=model_code, version_id=version_id)
    mapped_lines = int(db.query(func.count(mapped_sq.c.shipment_line_id)).scalar() or 0)
    shipped_qty_total = _d(db.query(func.coalesce(func.sum(mapped_sq.c.qty), 0)).scalar())

    snap_latest = _latest_bom_snapshot_sq(db)
    rows = (
        db.query(mapped_sq.c.shipment_line_id, mapped_sq.c.qty, snap_latest.c.trace_json)
        .join(snap_latest, mapped_sq.c.shipment_line_id == snap_latest.c.shipment_line_id)
        .all()
    )

    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    covered_line_ids: set[str] = set()
    shipped_qty_covered = Decimal("0")

    for shipment_line_id, qty, trace_json in rows:
        trace = trace_json if isinstance(trace_json, dict) else {}
        costing = trace.get("costing") if isinstance(trace.get("costing"), dict) else {}
        process_lines = costing.get("process_lines")
        if not isinstance(process_lines, list) or not process_lines:
            continue
        sid = str(shipment_line_id)
        if sid not in covered_line_ids:
            covered_line_ids.add(sid)
            shipped_qty_covered += _d(qty)
        for pl in process_lines:
            if not isinstance(pl, dict):
                continue
            pcode = str(pl.get("process_code") or "").strip()
            pname = str(pl.get("process_name") or "").strip()
            team = str(pl.get("team_name") or "").strip()
            key = (pcode, pname, team)
            b = agg.setdefault(
                key,
                {
                    "process_code": pcode or None,
                    "process_name": pname or None,
                    "team_name": team or None,
                    "total_minutes": Decimal("0"),
                    "total_cost": Decimal("0"),
                    "line_count": 0,
                    "_lines": set(),
                },
            )
            b["total_minutes"] += _d(pl.get("total_minutes"))
            b["total_cost"] += _d(pl.get("total_cost"))
            b["_lines"].add(sid)

    items: List[Dict[str, Any]] = []
    for b in agg.values():
        line_set = b.pop("_lines", set())
        b["line_count"] = len(line_set)
        items.append(b)
    items.sort(key=lambda x: _d(x.get("total_cost")), reverse=True)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "model_code": model_code,
        "version_id": version_id,
        "total_shipment_lines": total_ship_lines,
        "mapped_model_lines": mapped_lines,
        "shipped_qty_total": shipped_qty_total,
        "lines_with_process_details": len(covered_line_ids),
        "shipped_qty_covered": shipped_qty_covered,
        "items": items,
        "note": "工序合计=按发货行汇总的最新 BOM 快照 trace.costing.process_lines（若存在）。2025 轻量结果通常不含工序明细，覆盖率可能低于成本覆盖率。",
    }

