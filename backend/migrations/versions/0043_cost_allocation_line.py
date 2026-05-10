"""cost_allocation_line — A4 allocator output table

Revision ID: 0043_cost_allocation_line
Revises: 0042_fixed_cost_amortization_line
Create Date: 2026-05-10

Background
----------
Path A §A4 — cost_allocator_service distributes A3's amortized
(beneficiary_company_id, expense_category) groups to every active
cost_center using a multi-level fallback driver chain:

| 费用类型 | 主分摊基础 | fallback 1 | fallback 2 |
|---|---|---|---|
| rent / utility / admin (rent-like) | floor_area_sqm | headcount | revenue |
| platform_recharge / selling | revenue (按店铺) | headcount | floor_area_sqm |
| financial / capital_recovery | headcount | floor_area_sqm | 均摊 |

Each row records the actual basis used + total/value/weight (so the UI
can render "占 X%" tooltip), plus ``fallback_chain`` JSON list of the
basis types that were tried before this one (audit trail).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0043_cost_allocation_line"
down_revision = "0042_fixed_cost_amortization_line"
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
        "cost_allocation_line",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("source_company_id", sa.String(length=64), nullable=False),
        sa.Column("source_expense_category", sa.String(length=32), nullable=False),
        sa.Column("source_total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("target_cost_center_id", sa.String(length=36), nullable=False),
        sa.Column("allocation_basis", sa.String(length=32), nullable=False),
        sa.Column("allocation_basis_value", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("allocation_basis_total", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("allocation_weight", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("amount_allocated", sa.Numeric(14, 2), nullable=False),
        sa.Column("fallback_chain", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_index(
        "idx_cal_period_cc",
        "cost_allocation_line",
        ["period", "target_cost_center_id"],
    )
    op.create_index(
        "idx_cal_company",
        "cost_allocation_line",
        ["source_company_id"],
    )
    op.create_index(
        "idx_cal_category",
        "cost_allocation_line",
        ["source_expense_category"],
    )

    if _dialect_name() == "postgresql":
        op.create_foreign_key(
            "fk_cal_cost_center",
            "cost_allocation_line",
            "cost_center",
            ["target_cost_center_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    if _dialect_name() == "postgresql":
        try:
            op.drop_constraint(
                "fk_cal_cost_center",
                "cost_allocation_line",
                type_="foreignkey",
            )
        except Exception:  # noqa: BLE001
            pass
    op.drop_index("idx_cal_category", table_name="cost_allocation_line")
    op.drop_index("idx_cal_company", table_name="cost_allocation_line")
    op.drop_index("idx_cal_period_cc", table_name="cost_allocation_line")
    op.drop_table("cost_allocation_line")
