"""extend long_tail_cogs_rate_strategies into cost_rate_master (v1.3 Cost Rate Hub)

Revision ID: 0038_cost_rate_master
Revises: 0037_shipment_exception_queue_line_idx
Create Date: 2026-05-09

Background
----------
Cost Rate Hub v1.3 §4.3.2 — extend the existing 0035 long-tail table
into the unified ``cost_rate_master`` so all rate types (cogs /
overhead_rate / labor_per_*) share the same 4-layer scope chain
(model > category > cost_center > global).

Strategy:
1. Add 11 new columns with safe defaults so existing 'cogs' rows stay
   100% backwards compatible.
2. Backfill legacy long-tail rows: ``rate_type='cogs'`` /
   ``scope_type='category'`` / ``scope_id=category`` /
   ``rate_basis='pct_of_revenue'`` / ``source='long_tail_legacy'``.
3. Add two lookup indexes (PostgreSQL partial; SQLite plain).
4. Rename the table to ``cost_rate_master`` and create a backwards
   compatibility view ``long_tail_cogs_rate_strategies`` filtered to
   ``rate_type='cogs'`` so any unconverted SQL keeps working through
   the migration window.

Downgrade fully reverses these steps. Tested with both PostgreSQL
(production) and SQLite (planner_test pytest fixtures).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0038_cost_rate_master"
down_revision = "0037_shipment_exception_queue_line_idx"
branch_labels = None
depends_on = None


_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    # name, type, kwargs (server_default / nullable)
    ("rate_type", sa.String(32), {"nullable": False, "server_default": "cogs"}),
    ("scope_type", sa.String(32), {"nullable": False, "server_default": "category"}),
    ("scope_id", sa.String(128), {"nullable": True}),
    ("rate_basis", sa.String(32), {"nullable": False, "server_default": "pct_of_revenue"}),
    ("source", sa.String(64), {"nullable": False, "server_default": "manual"}),
    ("effective_from", sa.DateTime(), {"nullable": True}),
    ("effective_to", sa.DateTime(), {"nullable": True}),
    ("data_quality", sa.String(16), {"nullable": True}),  # green / yellow / red
    # 3 placeholder columns — v1 may stay all NULL; reserved for Stage 2.
    ("cost_center_id", sa.String(36), {"nullable": True}),
    ("legal_entity_id", sa.String(36), {"nullable": True}),
    ("production_unit_id", sa.String(36), {"nullable": True}),
]


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def upgrade() -> None:
    dialect = _dialect_name()

    # 1) Add the 11 new columns. Use batch_alter_table for SQLite friendliness.
    with op.batch_alter_table("long_tail_cogs_rate_strategies") as batch:
        for name, type_, kwargs in _NEW_COLUMNS:
            batch.add_column(sa.Column(name, type_, **kwargs))

    # 2) Backfill legacy rows so the new resolve chain treats them as
    #    rate_type='cogs' + scope_type='category' transparently.
    op.execute(
        sa.text(
            """
            UPDATE long_tail_cogs_rate_strategies
            SET rate_type = 'cogs',
                scope_type = 'category',
                scope_id = category,
                rate_basis = 'pct_of_revenue',
                source = 'long_tail_legacy'
            WHERE rate_type IS NULL OR rate_type = 'cogs'
            """
        )
    )

    # 3) Lookup indexes. PostgreSQL gets partial indexes; SQLite gets
    #    plain composite indexes (still helps the planner).
    if dialect == "postgresql":
        op.create_index(
            "idx_cost_rate_lookup",
            "long_tail_cogs_rate_strategies",
            ["rate_type", "scope_type", "scope_id", "enabled", sa.text("effective_from DESC")],
            postgresql_where=sa.text("is_archived = FALSE"),
        )
        op.create_index(
            "idx_cost_rate_global_active",
            "long_tail_cogs_rate_strategies",
            ["rate_type", sa.text("effective_from DESC")],
            postgresql_where=sa.text("enabled = TRUE AND is_archived = FALSE AND scope_type = 'global'"),
        )
    else:
        # SQLite (or other) — plain indexes; partial WHERE is harder to
        # express portably and we don't run perf-critical queries on
        # SQLite anyway (it's only used for unit tests).
        op.create_index(
            "idx_cost_rate_lookup",
            "long_tail_cogs_rate_strategies",
            ["rate_type", "scope_type", "scope_id", "enabled"],
        )
        op.create_index(
            "idx_cost_rate_global_active",
            "long_tail_cogs_rate_strategies",
            ["rate_type", "scope_type"],
        )

    # 4) Rename to cost_rate_master + create the compat view (filter to cogs).
    op.rename_table("long_tail_cogs_rate_strategies", "cost_rate_master")
    op.execute(
        "CREATE VIEW long_tail_cogs_rate_strategies AS "
        "SELECT * FROM cost_rate_master WHERE rate_type = 'cogs'"
    )


def downgrade() -> None:
    dialect = _dialect_name()

    # Reverse step 4: drop the view, rename back.
    op.execute("DROP VIEW IF EXISTS long_tail_cogs_rate_strategies")
    op.rename_table("cost_rate_master", "long_tail_cogs_rate_strategies")

    # Reverse step 3: drop the lookup indexes.
    op.drop_index("idx_cost_rate_global_active", table_name="long_tail_cogs_rate_strategies")
    op.drop_index("idx_cost_rate_lookup", table_name="long_tail_cogs_rate_strategies")

    # Reverse step 1: drop the 11 columns. SQLite needs batch mode.
    with op.batch_alter_table("long_tail_cogs_rate_strategies") as batch:
        for name, _type, _kwargs in reversed(_NEW_COLUMNS):
            batch.drop_column(name)

    # Note: we don't restore "rate_type IS NULL" semantics from the
    # backfill UPDATE — that data is monotonic (NULL → 'cogs') and
    # legacy code never read these columns in the first place.
    _ = dialect  # keep parity with upgrade signature
