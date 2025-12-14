"""Costing core base tables"""

from alembic import op
import sqlalchemy as sa


revision = "0005_costing_core_base"
down_revision = "0004_phase35_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("material_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("material_name", sa.String(length=255), nullable=False),
        sa.Column("material_type", sa.String(length=32), nullable=False, server_default="raw"),
        sa.Column("category", sa.String(length=128)),
        sa.Column("model_category", sa.String(length=128)),
        sa.Column("unit", sa.String(length=32)),
        sa.Column("purchase_unit", sa.String(length=32)),
        sa.Column("inventory_unit", sa.String(length=32)),
        sa.Column("conversion_formula", sa.String(length=255)),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("supplier_code", sa.String(length=64)),
        sa.Column("supplier_name", sa.String(length=255)),
        sa.Column("usage_scope", sa.String(length=255)),
        sa.Column("bom_notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("source_created_at", sa.DateTime()),
        sa.Column("source_updated_at", sa.DateTime()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "process_modules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("module_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=128)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "product_models",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=128)),
        sa.Column("calc_mode", sa.String(length=32), nullable=False, server_default="ratio"),
        sa.Column("fixed_price", sa.Numeric(18, 4)),
        sa.Column("standard_width_mm", sa.Numeric(18, 4)),
        sa.Column("standard_height_mm", sa.Numeric(18, 4)),
        sa.Column("unit_of_measure", sa.String(length=32)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "processes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("process_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("process_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("default_module_id", sa.String(length=36)),
        sa.Column("fixed_time_minutes", sa.Numeric(10, 2)),
        sa.Column("hourly_rate", sa.Numeric(18, 4)),
        sa.Column("piece_rate", sa.Numeric(18, 4)),
        sa.Column("piece_rate_formula", sa.Text()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["default_module_id"], ["process_modules.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "virtual_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("virtual_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("unit", sa.String(length=32)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "model_processes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("process_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["model_id"], ["product_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_model_processes_model",
        "model_processes",
        ["model_id"],
    )
    op.create_index(
        "ix_model_processes_process",
        "model_processes",
        ["process_id"],
    )

    op.create_table(
        "model_variant_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("source_material_ref_id", sa.String(length=36)),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_operator", sa.String(length=16), nullable=False, server_default="equals"),
        sa.Column("trigger_value", sa.String(length=255)),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("target_material_ref_id", sa.String(length=36)),
        sa.Column("quantity_delta", sa.Numeric(18, 6)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["model_id"], ["product_models.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_model_variant_rules_model",
        "model_variant_rules",
        ["model_id"],
    )

    op.create_table(
        "model_materials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("material_type", sa.String(length=16), nullable=False, server_default="real"),
        sa.Column("material_ref_id", sa.String(length=36), nullable=False),
        sa.Column("material_code", sa.String(length=64)),
        sa.Column("material_name", sa.String(length=255)),
        sa.Column("unit_of_measure", sa.String(length=32)),
        sa.Column("calculation_method", sa.String(length=32), nullable=False, server_default="count"),
        sa.Column("base_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("loss_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 4)),
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["model_id"], ["product_models.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "model_id",
            "material_type",
            "material_ref_id",
            name="uq_model_material_ref",
        ),
    )
    op.create_index(
        "ix_model_materials_model",
        "model_materials",
        ["model_id"],
    )

    op.create_table(
        "sku_model_mapping",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sku_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("source_system", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["model_id"], ["product_models.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "virtual_material_bindings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("virtual_material_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("material_type", sa.String(length=16), nullable=False, server_default="real"),
        sa.Column("material_ref_id", sa.String(length=36), nullable=False),
        sa.Column("quantity_ratio", sa.Numeric(18, 6), nullable=False, server_default="1"),
        sa.Column("loss_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["virtual_material_id"],
            ["virtual_materials.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "virtual_material_id",
            "material_ref_id",
            name="uq_virtual_material_binding",
        ),
    )


def downgrade() -> None:
    op.drop_table("virtual_material_bindings")
    op.drop_table("sku_model_mapping")
    op.drop_index("ix_model_materials_model", table_name="model_materials")
    op.drop_table("model_materials")
    op.drop_index("ix_model_variant_rules_model", table_name="model_variant_rules")
    op.drop_table("model_variant_rules")
    op.drop_index("ix_model_processes_process", table_name="model_processes")
    op.drop_index("ix_model_processes_model", table_name="model_processes")
    op.drop_table("model_processes")
    op.drop_table("virtual_materials")
    op.drop_table("processes")
    op.drop_table("product_models")
    op.drop_table("process_modules")
    op.drop_table("materials")


