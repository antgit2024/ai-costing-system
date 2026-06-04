"""Jackyun shipment (发货单/出仓) APIs.

Method-name reference (from 吉客云开放平台 → 应用管理 → API 列表):
- ``wms.order.query-info``         查询发货单 (single, by orderNo / erporderNo)
- ``wms.order.query-info.page``    查询发货单(分页)              ← default for sync
- ``wms.order.query-info.page.v2`` 查询**未完成**发货单(分页)    (subset only)
- ``wms.order.query.page``         查询发货单(分页带货位)

We default to ``query-info.page`` for sync jobs because v2 only covers
unfinished shipments and rejects calls that don't carry a status filter.

Hard upstream constraints we have to honor:
- ``startModifyTime`` ~ ``endModifyTime`` window MUST be <= 24h
  (sub-code ``0050030002`` is raised otherwise — see ``sync_jobs.py`` for
  the per-day splitter that respects this).
- ``pageInfo.total`` is unreliable in this endpoint (often 0 even when
  ``data`` is non-empty); pagination MUST stop on a short page rather than
  on ``page_index * page_size >= total``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

from sqlalchemy.orm import Session

from ...base.client import ClientResponse
from ..client import JackyunClient

API_QUERY_INFO = "wms.order.query-info"
API_QUERY_INFO_PAGE = "wms.order.query-info.page"
API_QUERY_INFO_PAGE_V2 = "wms.order.query-info.page.v2"  # unfinished shipments only

# Backwards-compat alias: callers that imported ``API_QUERY_INFO_PAGE_V2``
# expecting the "default list" endpoint should migrate to the page-without-v2
# constant. The shim keeps existing imports working until that's done.
DEFAULT_LIST_API = API_QUERY_INFO_PAGE


def query_shipment_detail(
    client: JackyunClient,
    *,
    order_no: Optional[str] = None,
    erp_order_no: Optional[str] = None,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClientResponse:
    """Query a single shipment by Jackyun shipment number or ERP order number."""

    biz: Dict[str, Any] = {}
    if order_no:
        biz["orderNo"] = order_no
    if erp_order_no:
        biz["erporderNo"] = erp_order_no
    if not biz:
        raise ValueError("query_shipment_detail requires at least one of order_no/erp_order_no")
    return client.call(
        API_QUERY_INFO,
        biz,
        sync_run_id=sync_run_id,
        db=db,
    )


def query_shipments_page(
    client: JackyunClient,
    *,
    page_index: int = 1,
    page_size: int = 50,
    start_modify_time: Optional[str] = None,
    end_modify_time: Optional[str] = None,
    start_gmt_create: Optional[str] = None,
    end_gmt_create: Optional[str] = None,
    order_status_list: Optional[Iterable[int]] = None,
    out_type_list: Optional[Iterable[int]] = None,
    flag_name_list: Optional[Iterable[str]] = None,
    need_has_logistics_no: Optional[int] = None,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClientResponse:
    """Page through shipments. Use this for incremental sync."""

    biz: Dict[str, Any] = {
        "pageIndex": int(page_index),
        "pageSize": int(page_size),
    }
    if start_modify_time:
        biz["startModifyTime"] = start_modify_time
    if end_modify_time:
        biz["endModifyTime"] = end_modify_time
    if start_gmt_create:
        biz["startGmtCreate"] = start_gmt_create
    if end_gmt_create:
        biz["endGmtCreate"] = end_gmt_create
    if order_status_list:
        biz["orderStatusList"] = list(order_status_list)
    if out_type_list:
        biz["outTypeList"] = list(out_type_list)
    if flag_name_list:
        biz["flagNameList"] = list(flag_name_list)
    if need_has_logistics_no is not None:
        biz["needHasLogisticsNo"] = int(need_has_logistics_no)

    return client.call(
        DEFAULT_LIST_API,
        biz,
        sync_run_id=sync_run_id,
        db=db,
    )


def iter_shipments(
    client: JackyunClient,
    *,
    page_size: int = 50,
    start_modify_time: Optional[str] = None,
    end_modify_time: Optional[str] = None,
    order_status_list: Optional[Iterable[int]] = None,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
    api_method: str = DEFAULT_LIST_API,
    max_pages: int = 200,
) -> Iterator[List[Dict[str, Any]]]:
    """Yield shipment-list pages until the upstream returns a short / empty page.

    Pagination contract (verified against the live gateway 2026-05):
    - ``pageInfo.total`` is unreliable on ``query-info.page`` (frequently
      reports ``0`` even when ``data`` has rows). DO NOT use it to decide
      when to stop.
    - Stop conditions, in order:
        1. upstream returned no rows;
        2. upstream returned fewer rows than ``page_size`` (last page);
        3. ``max_pages`` safety cap (avoids runaway loops if upstream ever
           starts returning a phantom full page indefinitely).
    """

    page_index = 1
    while page_index <= max_pages:
        biz: Dict[str, Any] = {
            "pageIndex": int(page_index),
            "pageSize": int(page_size),
        }
        if start_modify_time:
            biz["startModifyTime"] = start_modify_time
        if end_modify_time:
            biz["endModifyTime"] = end_modify_time
        if order_status_list:
            biz["orderStatusList"] = list(order_status_list)

        resp = client.call(api_method, biz, sync_run_id=sync_run_id, db=db)
        result = resp.raw.get("result") if isinstance(resp.raw, dict) else None
        rows = (result or {}).get("data") or []
        if not rows:
            return
        yield rows
        if len(rows) < page_size:
            return
        page_index += 1
