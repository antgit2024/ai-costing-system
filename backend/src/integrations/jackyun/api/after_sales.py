"""Jackyun after-sales / refund / return APIs (placeholder).

The actual Jackyun method names will be filled in once we subscribe to their
after-sales endpoints. Until then this module documents the planned shape so
the rest of the integration layer can compile against it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...base.client import ClientResponse
from ..client import JackyunClient

# Replace with the real method once subscribed (e.g. "after.sales.query-info.page").
API_AFTER_SALES_PAGE = "after.sales.query-info.page"


def query_after_sales_page(
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
    return client.call(API_AFTER_SALES_PAGE, biz, sync_run_id=sync_run_id, db=db)
