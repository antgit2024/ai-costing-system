"""add shipment_line_id index to shipment_exception_queue (perf fix)

Revision ID: 0037_shipment_exception_queue_line_idx
Revises: 0036_shipment_line_jackyun_full_fields
Create Date: 2026-05-07 14:20:00.000000

Background
----------
``list_shipment_lines`` (powering /costing/shipments and the 已完成 Tab in
/costing/biz/shipments) joins each row to the latest unresolved exception
via two correlated scalar_subqueries::

    (SELECT reason  FROM shipment_exception_queue WHERE shipment_line_id = sl.id
       AND resolved_at IS NULL ORDER BY created_at DESC LIMIT 1)
    (SELECT message FROM shipment_exception_queue WHERE shipment_line_id = sl.id
       AND resolved_at IS NULL ORDER BY created_at DESC LIMIT 1)

The table grew to 127k rows (99% with ``resolved_at IS NULL``). Because the
table only had indexes on ``id / batch_id / reason``, both subqueries fell
back to Seq Scan once per row of the outer LIMIT 50, plus once per row of
the COUNT(*). Real-world impact: 已完成 30 天 page took 31 seconds even
though the underlying SELECT planned at ~60 ms.

Fix: a partial index that exactly covers the access pattern. We use a
COMPOSITE on ``(shipment_line_id, created_at DESC)`` and partial
``WHERE resolved_at IS NULL`` so the planner can do an Index-Only Scan
for the LIMIT 1 ORDER BY at zero buffer cost.
"""

from __future__ import annotations

import sqlalchemy as sa  # noqa: F401  (kept for parity / future op.execute)
from alembic import op


revision = "0037_shipment_exception_queue_line_idx"
down_revision = "0036_shipment_line_jackyun_full_fields"
branch_labels = None
depends_on = None


_INDEX_NAME = "ix_shipment_exception_queue_line_unresolved"


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "shipment_exception_queue",
        ["shipment_line_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="shipment_exception_queue")
