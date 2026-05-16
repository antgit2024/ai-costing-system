"""Jackyun ERP-API 货品主档分页 (erp.storage.goodslist).

Method-name reference (from 吉客云开放平台 → ERP-API 接口列表):
- ``erp.storage.goodslist``  分页查询货品信息 ← default for sync (本期主接口)

Hard upstream constraints (verified live 2026-05-16 against appKey=22258171):
- ``pageIndex`` is **0-based** (NOT the OMS 1-based convention!).
- ``pageSize`` upper bound is **200** (verified; ``pageSize=200`` returns 200 rows).
- Response envelope: ``code=200`` + ``subCode="0030000004"`` + ``msg="操作成功"``
  on success. NOT zero, NOT 200 — see ``client._BUSINESS_OK_SUB_CODES``.
- Response payload shape:
    result.data.goods = [
        {
            "goodsId": "<long-as-str>",
            "skuId":   "<long-as-str>",
            "goodsNo":      "...",       # 货品编号
            "skuNo":        "...",       # 规格编号 (≈"模型编码")
            "skuBarcode":   "...",       # 条码 (PRIMARY KEY in our system)
            "skuCode":      "..." | None, # 外部编码 (=outSkuCode); 100% null
                                          # for this tenant — populated only after
                                          # we run the writeback line G1-H.
            "goodsName":    "...",
            "skuName":      "...",
            "isBlockup":     0|1,        # 货品级停用
            "skuIsBlockup":  0|1,        # 规格级停用
            "isDelete":      0|1,
            "goodsAttr":     <int>,      # 1=成品 / 2=半成品 / 3=原料 / ...
            "cateName":     "...",
            "cateFullName": "...",
            "flagData":     [...] | None, # 规格标记 (multi-value array)
            "imgUrlList":   [...],       # main-image objects (rare, ~8% rate)
            "skuImgUrl":    "...",       # spec image url (~68% rate)
            "goodsGmtModified": 1751707629000,  # ms epoch
            "skuGmtModified":   1716605439000,  # ms epoch
            "goodsField1..50": ...,      # 货品自定义字段 (mostly null)
            "skuField1..30":   ...,      # 规格自定义字段 (mostly null)
            ... (~140 more fields)
        },
        ...
    ]

Two pagination modes (per `core_interfaces_extracted.md` §"erp.storage.goodslist"):
- **Incremental** (recommended for daily cron): pass
    ``startDateModifiedSku`` / ``endDateModifiedSku``
    (and/or ``startDateModifiedGoods`` / ``endDateModifiedGoods``)
  + bump ``pageIndex`` page by page until short page.
- **Full bootstrap cursor**: pass ``maxSkuId`` (= last seen ``skuId``, 0 for
  first call); upstream returns the next batch with ``skuId > maxSkuId``,
  no traditional pagination needed. Use this for the very first 40-万-row
  bootstrap load if Excel import wasn't available.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

from sqlalchemy.orm import Session

from ...base.client import ClientResponse
from ..client import JackyunClient

API_LIST_GOODS = "erp.storage.goodslist"
DEFAULT_LIST_API = API_LIST_GOODS

# Upstream-verified upper bound. Use the maximum to minimize RTTs against
# the 168-field heavy payload — even 200 rows came back in ~500 ms.
DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 200

# No explicit 24h window cap on this endpoint (verified: a 30-day window
# still works), but `sync_jobs.sync_goods` still chunks into 24h windows
# for watermark-advance hygiene + dead-letter triage clarity.

# Safety cap for incremental iter_goods (pages * page_size = max records per call).
# 2000 * 200 = 400_000 records — comfortably above any single-day delta.
DEFAULT_MAX_PAGES = 2000

# Safety cap for cursor mode: 40-万 / 200 = 2000 calls; allow 10000 just in case.
DEFAULT_MAX_CURSOR_CALLS = 10000


def list_goods_page(
    client: JackyunClient,
    *,
    page_index: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
    start_date_modified_sku: Optional[str] = None,
    end_date_modified_sku: Optional[str] = None,
    start_date_modified_goods: Optional[str] = None,
    end_date_modified_goods: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_sku_id: Optional[int] = None,
    goods_no_list: Optional[Iterable[str]] = None,
    sku_barcode_list: Optional[Iterable[str]] = None,
    sku_no_list: Optional[Iterable[str]] = None,
    sku_code_list: Optional[Iterable[str]] = None,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClientResponse:
    """Single page call against ``erp.storage.goodslist``.

    All time params are upstream-formatted strings: ``YYYY-MM-DD HH:MM:SS``.
    Pass at least one filter (modify-time window OR maxSkuId OR explicit list
    of barcodes/codes); a bare call with only paging WILL return data but
    isn't useful for daily sync.
    """
    if page_index < 0:
        raise ValueError("page_index is 0-based for erp.storage.goodslist")
    if page_size <= 0 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be 1..{MAX_PAGE_SIZE}")

    biz: Dict[str, Any] = {
        "pageIndex": int(page_index),
        "pageSize": int(page_size),
    }
    if start_date_modified_sku:
        biz["startDateModifiedSku"] = start_date_modified_sku
    if end_date_modified_sku:
        biz["endDateModifiedSku"] = end_date_modified_sku
    if start_date_modified_goods:
        biz["startDateModifiedGoods"] = start_date_modified_goods
    if end_date_modified_goods:
        biz["endDateModifiedGoods"] = end_date_modified_goods
    if start_date:
        biz["startDate"] = start_date
    if end_date:
        biz["endDate"] = end_date
    if max_sku_id is not None:
        biz["maxSkuId"] = int(max_sku_id)
    if goods_no_list:
        biz["goodsNos"] = list(goods_no_list)
    if sku_barcode_list:
        biz["skuBarcodes"] = list(sku_barcode_list)
    if sku_no_list:
        biz["skuNos"] = list(sku_no_list)
    if sku_code_list:
        biz["skuCodes"] = list(sku_code_list)

    return client.call(DEFAULT_LIST_API, biz, sync_run_id=sync_run_id, db=db)


def _extract_goods(resp: ClientResponse) -> List[Dict[str, Any]]:
    """Pull the ``result.data.goods`` list out of a response, defensively."""
    data = resp.data if isinstance(resp.data, dict) else {}
    goods = data.get("goods")
    if not isinstance(goods, list):
        return []
    return [g for g in goods if isinstance(g, dict)]


def iter_goods(
    client: JackyunClient,
    *,
    start_date_modified_sku: Optional[str] = None,
    end_date_modified_sku: Optional[str] = None,
    start_date_modified_goods: Optional[str] = None,
    end_date_modified_goods: Optional[str] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield goods records for an incremental sync window.

    Stops on:
      * empty page,
      * short page (``len(records) < page_size``),
      * ``max_pages`` safety cap.

    NOTE: caller MUST pass at least one of (sku-modify, goods-modify) windows
    or this becomes an unbounded scan from page 0.
    """
    if not any([
        start_date_modified_sku, end_date_modified_sku,
        start_date_modified_goods, end_date_modified_goods,
    ]):
        raise ValueError(
            "iter_goods requires at least one *DateModifiedSku/Goods bound; "
            "use iter_goods_by_cursor for full bootstrap loads instead."
        )

    page_index = 0
    while page_index < max_pages:
        resp = list_goods_page(
            client,
            page_index=page_index,
            page_size=page_size,
            start_date_modified_sku=start_date_modified_sku,
            end_date_modified_sku=end_date_modified_sku,
            start_date_modified_goods=start_date_modified_goods,
            end_date_modified_goods=end_date_modified_goods,
            sync_run_id=sync_run_id,
            db=db,
        )
        records = _extract_goods(resp)
        if not records:
            return
        for rec in records:
            yield rec
        if len(records) < page_size:
            return
        page_index += 1


def iter_goods_by_cursor(
    client: JackyunClient,
    *,
    start_max_sku_id: int = 0,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_calls: int = DEFAULT_MAX_CURSOR_CALLS,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield goods records using ``maxSkuId`` cursor mode (full bootstrap).

    Per upstream docs: pass ``maxSkuId=0`` first; subsequent calls pass the
    last seen ``skuId``. ``pageIndex`` is ignored in cursor semantics (we
    keep ``pageIndex=0`` to satisfy required-field validation).

    Stops on:
      * empty page,
      * short page (``len(records) < page_size``),
      * ``max_calls`` safety cap (10000 by default — covers ~2 million SKUs).
    """
    cursor = int(start_max_sku_id or 0)
    for _ in range(max_calls):
        resp = list_goods_page(
            client,
            page_index=0,
            page_size=page_size,
            max_sku_id=cursor,
            sync_run_id=sync_run_id,
            db=db,
        )
        records = _extract_goods(resp)
        if not records:
            return
        for rec in records:
            yield rec
        if len(records) < page_size:
            return
        last_sku_id = records[-1].get("skuId")
        try:
            new_cursor = int(last_sku_id)
        except (TypeError, ValueError):
            return
        if new_cursor <= cursor:
            return
        cursor = new_cursor
