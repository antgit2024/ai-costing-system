"""cost_center_payroll_snapshot — A2 aggregator output table

Revision ID: 0041_cost_center_payroll_snapshot
Revises: 0040_cost_center
Create Date: 2026-05-10

Background
----------
Path A §A2 — cost_center_aggregator_service consumes finance C1 payroll
``aggregation=by_employee`` data per (cost_center, period) and writes a
materialized snapshot here. Hub upserts a labor_per_minute row into
cost_rate_master keyed by this snapshot.

Schema follows the brief §A2.1 verbatim. Indexes:
- (cost_center_id, period DESC) for "拿最新 N 个月" queries
- (period) for "本月所有班组聚合"
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0041_cost_center_payroll_snapshot"
down_revision = "0040_cost_center"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def _defaults() -> tuple[sa.TextClause, sa.TextClause, sa.TextClause]:
    if _dialect_name() == "postgresql":
        return (
            sa.text("'{}'::json"),
            sa.text("'[]'::json"),
            sa.text("now()"),
        )
    return sa.text("'{}'"), sa.text("'[]'"), sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    json_obj_default, json_arr_default, now_default = _defaults()
    op.create_table(
        "cost_center_payroll_snapshot",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("cost_center_id", sa.String(length=36), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("headcount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_paid", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("avg_salary", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_minutes", sa.Numeric(14, 2), nullable=True),
        sa.Column("rate_per_minute", sa.Numeric(10, 4), nullable=True),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("data_quality", sa.String(length=16), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_unique_constraint(
        "uq_cost_center_payroll_period",
        "cost_center_payroll_snapshot",
        ["cost_center_id", "period"],
    )
    op.create_index(
        "idx_ccps_period",
        "cost_center_payroll_snapshot",
        ["period"],
    )
    op.create_index(
        "idx_ccps_cc_period",
        "cost_center_payroll_snapshot",
        ["cost_center_id", "period"],
    )

    if _dialect_name() == "postgresql":
        op.create_foreign_key(
            "fk_ccps_cost_center",
            "cost_center_payroll_snapshot",
            "cost_center",
            ["cost_center_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    if _dialect_name() == "postgresql":
        try:
            op.drop_constraint(
                "fk_ccps_cost_center",
                "cost_center_payroll_snapshot",
                type_="foreignkey",
            )
        except Exception:  # noqa: BLE001
            pass
    op.drop_index("idx_ccps_cc_period", table_name="cost_center_payroll_snapshot")
    op.drop_index("idx_ccps_period", table_name="cost_center_payroll_snapshot")
    op.drop_constraint(
        "uq_cost_center_payroll_period",
        "cost_center_payroll_snapshot",
        type_="unique",
    )
    op.drop_table("cost_center_payroll_snapshot")
