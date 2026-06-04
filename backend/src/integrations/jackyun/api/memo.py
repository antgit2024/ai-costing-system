"""Jackyun memo / seller-note write-back APIs (placeholder).

Use this from ``integration_writeback_jobs`` to push production-process /
打单备注 / customization info back to Jackyun. Final method names to be
confirmed (likely ``wms.order.update.memo`` or ``trade.update.memo``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...base.client import ClientResponse
from ..client import JackyunClient

API_UPDATE_SELLER_MEMO = "wms.order.update.memo"


def update_seller_memo(
    client: JackyunClient,
    *,
    order_no: Optional[str] = None,
    erp_order_no: Optional[str] = None,
    seller_memo: str,
    append_only: bool = False,
    sync_run_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClientResponse:
    if not order_no and not erp_order_no:
        raise ValueError("update_seller_memo requires order_no or erp_order_no")
    biz: Dict[str, Any] = {
        "sellerMemo": seller_memo,
        "appendOnly": int(bool(append_only)),
    }
    if order_no:
        biz["orderNo"] = order_no
    if erp_order_no:
        biz["erporderNo"] = erp_order_no
    return client.call(API_UPDATE_SELLER_MEMO, biz, sync_run_id=sync_run_id, db=db)
