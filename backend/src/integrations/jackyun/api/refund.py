"""Jackyun OMS-API 售后退款单 (omsapi-business.refund.listrefund).

Method-name reference (from 吉客云开放平台 → OMS-API 接口列表):
- ``omsapi-business.refund.listrefund``  分页查询网店售后单 ← default for sync

Hard upstream constraints (verified live 2026-05-12 — different from WMS namespace!):
- ``pageInfo`` is a **NESTED OBJECT** ``{pageIndex, pageSize}``, NOT flat keys.
- ``pageIndex`` is **1-based** (sending 0 returns an empty array).
- ``memberName`` (吉客号, e.g. ``"jackyun"``) is **REQUIRED**; without it the
  upstream rejects the request with the misleading message
  「创建起止时间或更新起止时间不能全为空」.
- One of these time-window pairs MUST be sent:
    * ``gmtCreateBegin`` / ``gmtCreateEnd``      (创建时间)
    * ``gmtModifiedBegin`` / ``gmtModifiedEnd``  (更新时间) ← best for incremental sync
    * ``createTimeBegin`` / ``createTimeEnd``    (退款申请时间)
    * ``modifiedTimeBegin`` / ``modifiedTimeEnd`` (退款修改时间)
- ``isQueryCount=true`` returns a real ``count`` but an EMPTY array; pass
  ``isQueryCount=false`` (or omit) to get records. Don't trust ``count`` for
  pagination — stop on a short page (same rule as wms.order.query-info.page).
- Response envelope: ``code=200`` + ``subCode="200"`` for success (NOT zero;
  see ``client._BUSINESS_OK_SUB_CODES``).
- ``result.data`` is a **JSON-encoded string**, not a nested object; the
  generic Jackyun ``parse_response`` decodes it once so callers see a dict
  ``{count, tradeAfterOnlineDtoArr}``.

Response shape:
    result.data = {
        "count": <int>,
        "tradeAfterOnlineDtoArr": [
            {
                "tradeAfterOnlineDTO":          {... header fields ...},
                "tradeAfterOnlineGoodsDTOList": [{... per-product line ...}, ...],
            },
            ...
        ],
    }
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

from sqlalchemy.orm import Session

from ...base.client import ClientResponse
from ..client import JackyunClient

API_LIST_REFUND = "omsapi-business.refund.listrefund"
DEFAULT_LIST_API = API_LIST_REFUND

# Upstream allows pageSize 1-100; OMS list APIs are heavier than WMS so use 50
# by default to balance throughput vs. memory.
DEFAULT_PAGE_SIZE = 50

# Upstream gateway tolerates wider windows than WMS (refund is lower volume),
# but to keep individual responses bounded and watermark advance predictable
# we still chunk into 24h slices in sync_jobs.
MAX_WINDOW_HOURS = 24

# Refund types per docs (header: hasGoodsReturn / refundType).
REFUND_TYPE_REFUND_ONLY = 0
REFUND_TYPE_RETURN = 1
REFUND_TYPE_EXCHANGE = 2
REFUND_TYPE_RESHIP = 3
REFUND_TYPE_REPAIR = 4


def list_refunds_page(
    client: JackyunClient,
    *,
    page_index: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    member_name: str = "jackyun",
    gmt_modified_begin: Optional[str] = None,
    gmt_modified_end: Optional[str] = None,
    gmt_create_begin: Optional[str] = None,
    gmt_create_end: Optional[str] = None,
    create_time_begin: Optional[str] = None,
    create_time_end: Optional[str] = None,
    modified_time_begin: Optional[str] = None,
    modified_time_end: Optional[str] = None,
    has_goods_return: Optional[Iterable[int]] = None,
    refund_no: Optional[Iterable[str]] = None,
    plat_order_no: Optional[Iterable[str]] = None,
    shop_id: Optional[Iterable[int]] = None,
    has_query_history: int = 0,
    is_query_count: bool = False,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClientResponse:
    """Page through refund/after-sales orders. Use for incremental sync.

    Pass exactly one (or more) of the four time-window pairs. ``gmtModified*``
    is the recommended one for incremental sync because the upstream updates
    that field on every status change (申请→退货→收货→退款成功).
    """

    if not member_name:
        raise ValueError("member_name (memberName / 吉客号) is required by upstream")
    if page_index < 1:
        raise ValueError("page_index is 1-based; sending 0 returns an empty array")

    biz: Dict[str, Any] = {
        "pageInfo": {"pageIndex": int(page_index), "pageSize": int(page_size)},
        "memberName": member_name,
        "isQueryCount": bool(is_query_count),
        "hasQueryHistory": int(has_query_history),
    }
    if gmt_modified_begin:
        biz["gmtModifiedBegin"] = gmt_modified_begin
    if gmt_modified_end:
        biz["gmtModifiedEnd"] = gmt_modified_end
    if gmt_create_begin:
        biz["gmtCreateBegin"] = gmt_create_begin
    if gmt_create_end:
        biz["gmtCreateEnd"] = gmt_create_end
    if create_time_begin:
        biz["createTimeBegin"] = create_time_begin
    if create_time_end:
        biz["createTimeEnd"] = create_time_end
    if modified_time_begin:
        biz["modifiedTimeBegin"] = modified_time_begin
    if modified_time_end:
        biz["modifiedTimeEnd"] = modified_time_end
    if has_goods_return:
        biz["hasGoodsReturn"] = list(has_goods_return)
    if refund_no:
        biz["refundNo"] = list(refund_no)
    if plat_order_no:
        biz["platOrderNo"] = list(plat_order_no)
    if shop_id:
        biz["shopId"] = list(shop_id)

    return client.call(DEFAULT_LIST_API, biz, sync_run_id=sync_run_id, db=db)


def iter_refunds(
    client: JackyunClient,
    *,
    gmt_modified_begin: str,
    gmt_modified_end: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = 200,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
    **extra_filters: Any,
) -> Iterator[Dict[str, Any]]:
    """Yield refund records (each = ``{tradeAfterOnlineDTO, tradeAfterOnlineGoodsDTOList}``).

    Stops on:
      * empty page (no records),
      * short page (``len(records) < page_size``),
      * ``max_pages`` safety cap.

    NOTE: never relies on ``count`` for the stop condition — the OMS endpoint
    returns ``count=0`` whenever ``isQueryCount=false`` (the default for sync
    runs because true makes the same call return an empty array).
    """

    page_index = 1
    while page_index <= max_pages:
        resp = list_refunds_page(
            client,
            page_index=page_index,
            page_size=page_size,
            gmt_modified_begin=gmt_modified_begin,
            gmt_modified_end=gmt_modified_end,
            sync_run_id=sync_run_id,
            db=db,
            **extra_filters,
        )
        data = resp.data if isinstance(resp.data, dict) else {}
        records: List[Dict[str, Any]] = list(data.get("tradeAfterOnlineDtoArr") or [])
        if not records:
            return
        for rec in records:
            yield rec
        if len(records) < page_size:
            return
        page_index += 1
