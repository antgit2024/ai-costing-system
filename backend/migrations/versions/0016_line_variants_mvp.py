"""line variants + items for standard model overlays

Revision ID: 0016_line_variants_mvp
Revises: 0015_model_process_modules
Create Date: 2025-12-21 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_line_variants_mvp"
down_revision = "0015_model_process_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_model_line_variants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("base_line_id", sa.String(length=36), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="replace_bundle"),
        sa.Column("stop_on_hit", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["version_id"], ["product_model_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_line_id"], ["model_version_materials.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_product_model_line_variants_version",
        "product_model_line_variants",
        ["version_id", "is_archived"],
    )
    op.create_index(
        "ix_product_model_line_variants_base_line",
        "product_model_line_variants",
        ["base_line_id", "is_archived"],
    )

    op.create_table(
        "product_model_line_variant_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("variant_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("material_kind", sa.String(length=16), nullable=False, server_default="real"),
        sa.Column("material_ref_id", sa.String(length=36), nullable=True),
        sa.Column("material_code", sa.String(length=64), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=32), nullable=True),
        sa.Column("calculation_method", sa.String(length=32), nullable=False, server_default="count"),
        sa.Column("base_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("fixed_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("coverage_ratio", sa.Numeric(18, 6), nullable=False, server_default="1"),
        sa.Column("loss_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["variant_id"], ["product_model_line_variants.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_product_model_line_variant_items_variant",
        "product_model_line_variant_items",
        ["variant_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_model_line_variant_items_variant", table_name="product_model_line_variant_items")
    op.drop_table("product_model_line_variant_items")
    op.drop_index("ix_product_model_line_variants_base_line", table_name="product_model_line_variants")
    op.drop_index("ix_product_model_line_variants_version", table_name="product_model_line_variants")
    op.drop_table("product_model_line_variants")

