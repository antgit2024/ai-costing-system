"""Jackyun goods / SKU (商品/货品) APIs (placeholder).

Real method names to be filled once subscribed (likely ``goods.query.page`` /
``erp.goods.list`` / ``erp.sku.list``). Same pattern as shipments.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...base.client import ClientResponse
from ..client import JackyunClient

API_GOODS_PAGE = "erp.goods.query.page"


def query_goods_page(
    client: JackyunClient,
    *,
    page_index: int = 1,
    page_size: int = 50,
    start_modify_time: Optional[str] = None,
    end_modify_time: Optional[str] = None,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClientResponse:
    biz: Dict[str, Any] = {
        "pageIndex": int(page_index),
        "pageSize": int(page_size),
    }
    if start_modify_time:
        biz["startModifyTime"] = start_modify_time
    if end_modify_time:
        biz["endModifyTime"] = end_modify_time
    return client.call(API_GOODS_PAGE, biz, sync_run_id=sync_run_id, db=db)
