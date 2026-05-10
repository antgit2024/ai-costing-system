"""fixed_cost_amortization_line — A3 amortizer output table

Revision ID: 0042_fixed_cost_amortization_line
Revises: 0041_cost_center_payroll_snapshot
Create Date: 2026-05-10

Background
----------
Path A §A3 — fixed_cost_amortizer_service expands finance C1
payment_requests with ``is_monthly_amortized`` + ``amort_*`` 5 fields
into per-(period, payment_request) lines that A4 cost_allocator can
consume. UNIQUE(period, payment_request_id) gives idempotent re-runs.

Note: ``payment_request_id`` is finance-side opaque id; we store as
``String(64)`` rather than FK because finance owns that table and we
treat it as external. Same for ``beneficiary_company_id`` /
``payer_company_id`` which point to ``master_companies.id`` over there.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0042_fixed_cost_amortization_line"
down_revision = "0041_cost_center_payroll_snapshot"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def _defaults() -> tuple[sa.TextClause, sa.TextClause]:
    if _dialect_name() == "postgresql":
        return sa.text("'{}'::json"), sa.text("now()")
    return sa.text("'{}'"), sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    json_obj_default, now_default = _defaults()
    op.create_table(
        "fixed_cost_amortization_line",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("payment_request_id", sa.String(length=64), nullable=False),
        sa.Column("beneficiary_company_id", sa.String(length=64), nullable=True),
        sa.Column("payer_company_id", sa.String(length=64), nullable=True),
        sa.Column("expense_category", sa.String(length=32), nullable=False),
        sa.Column("amount_amortized", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_monthly_amortized", sa.Boolean(), nullable=False, server_default=sa.text("false") if _dialect_name() == "postgresql" else sa.text("0")),
        sa.Column("amort_months", sa.Integer(), nullable=True),
        sa.Column("amort_start_period", sa.String(length=7), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
    )
    op.create_unique_constraint(
        "uq_fca_period_payment",
        "fixed_cost_amortization_line",
        ["period", "payment_request_id"],
    )
    op.create_index("idx_fca_period", "fixed_cost_amortization_line", ["period"])
    op.create_index(
        "idx_fca_beneficiary",
        "fixed_cost_amortization_line",
        ["beneficiary_company_id"],
    )
    op.create_index(
        "idx_fca_category",
        "fixed_cost_amortization_line",
        ["expense_category"],
    )


def downgrade() -> None:
    op.drop_index("idx_fca_category", table_name="fixed_cost_amortization_line")
    op.drop_index("idx_fca_beneficiary", table_name="fixed_cost_amortization_line")
    op.drop_index("idx_fca_period", table_name="fixed_cost_amortization_line")
    op.drop_constraint(
        "uq_fca_period_payment",
        "fixed_cost_amortization_line",
        type_="unique",
    )
    op.drop_table("fixed_cost_amortization_line")
