from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, relationship

from ..database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = Column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class SoftDeleteMixin:
    is_archived: Mapped[bool] = Column(Boolean, default=False, nullable=False)


class CostInitiative(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "cost_initiatives"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = Column(String(50), nullable=False, unique=True)
    name: Mapped[str] = Column(String(255), nullable=False)
    description: Mapped[str | None] = Column(Text)
    owner_id: Mapped[str] = Column(String(64), nullable=False)
    sponsor: Mapped[str | None] = Column(String(128))
    currency: Mapped[str] = Column(String(8), nullable=False, default="CNY")
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    target_launch_date: Mapped[date | None] = Column(Date)
    tags: Mapped[List[str]] = Column(JSON, default=list)

    packages: Mapped[List["CostPackage"]] = relationship(
        "CostPackage", back_populates="initiative", cascade="all, delete-orphan"
    )
    assumptions: Mapped[List["InputAssumption"]] = relationship(
        "InputAssumption", back_populates="initiative", cascade="all, delete-orphan"
    )
    scenarios: Mapped[List["ScenarioVersion"]] = relationship(
        "ScenarioVersion", back_populates="initiative", cascade="all, delete-orphan"
    )


class CostPackage(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "cost_packages"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    initiative_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_initiatives.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = Column(String(255), nullable=False)
    category: Mapped[str | None] = Column(String(64))
    parent_package_id: Mapped[str | None] = Column(
        String(36), ForeignKey("cost_packages.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[str | None] = Column(String(64))
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    notes: Mapped[str | None] = Column(Text)

    initiative: Mapped[CostInitiative] = relationship("CostInitiative", back_populates="packages")
    parent_package: Mapped[Optional["CostPackage"]] = relationship(
        "CostPackage", remote_side=[id]
    )
    line_items: Mapped[List["CostLineItem"]] = relationship(
        "CostLineItem", back_populates="package", cascade="all, delete-orphan"
    )


class CostLineItem(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "cost_line_items"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    package_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_packages.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = Column(String(32), nullable=False)
    reference_code: Mapped[str | None] = Column(String(64))
    description: Mapped[str] = Column(Text, nullable=False)
    unit_of_measure: Mapped[str] = Column(String(32), nullable=False)
    quantity: Mapped[float] = Column(Numeric(18, 4), nullable=False, default=0)
    unit_cost_estimate: Mapped[float] = Column(Numeric(18, 4), nullable=False, default=0)
    currency: Mapped[str] = Column(String(8), nullable=False, default="CNY")
    supplier_id: Mapped[str | None] = Column(String(64))
    preferred_quote_id: Mapped[str | None] = Column(String(36))
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    package: Mapped[CostPackage] = relationship("CostPackage", back_populates="line_items")
    supplier_quotes: Mapped[List["SupplierQuote"]] = relationship(
        "SupplierQuote", back_populates="line_item", cascade="all, delete-orphan"
    )


class SupplierQuote(Base, TimestampMixin):
    __tablename__ = "supplier_quotes"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    supplier_name: Mapped[str] = Column(String(255), nullable=False)
    contact: Mapped[str | None] = Column(String(255))
    line_item_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_line_items.id", ondelete="CASCADE"), nullable=False
    )
    quote_version: Mapped[int] = Column(Integer, nullable=False)
    currency: Mapped[str] = Column(String(8), nullable=False, default="CNY")
    unit_cost: Mapped[float] = Column(Numeric(18, 4), nullable=False)
    moq: Mapped[int | None] = Column(Integer)
    lead_time_days: Mapped[int | None] = Column(Integer)
    valid_through: Mapped[date | None] = Column(Date)
    attachments: Mapped[List[str]] = Column(JSON, default=list)
    notes: Mapped[str | None] = Column(Text)

    line_item: Mapped[CostLineItem] = relationship("CostLineItem", back_populates="supplier_quotes")


class InputAssumption(Base):
    __tablename__ = "input_assumptions"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    initiative_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_initiatives.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = Column(String(128), nullable=False)
    type: Mapped[str] = Column(String(64), nullable=False)
    value: Mapped[float] = Column(Numeric(18, 6), nullable=False)
    unit: Mapped[str | None] = Column(String(32))
    effective_date: Mapped[date] = Column(Date, nullable=False)
    source: Mapped[str | None] = Column(String(128))
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = Column(DateTime, default=utcnow, nullable=False)

    initiative: Mapped[CostInitiative] = relationship("CostInitiative", back_populates="assumptions")


class ScenarioVersion(Base, TimestampMixin):
    __tablename__ = "scenario_versions"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    initiative_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_initiatives.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = Column(String(50), nullable=False)
    name: Mapped[str] = Column(String(255), nullable=False)
    baseline_flag: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    assumption_set_id: Mapped[str | None] = Column(String(36))
    total_cost: Mapped[float | None] = Column(Numeric(18, 4), default=0)
    variance_vs_baseline: Mapped[float | None] = Column(Numeric(18, 4))
    notes: Mapped[str | None] = Column(Text)

    initiative: Mapped[CostInitiative] = relationship("CostInitiative", back_populates="scenarios")
    favorites: Mapped[List["ScenarioFavorite"]] = relationship(
        "ScenarioFavorite", back_populates="scenario", cascade="all, delete-orphan"
    )


class ScenarioLineSnapshot(Base):
    __tablename__ = "scenario_line_snapshots"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = Column(
        String(36), ForeignKey("scenario_versions.id", ondelete="CASCADE"), nullable=False
    )
    line_item_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_line_items.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[float] = Column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[float] = Column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = Column(String(8), nullable=False, default="CNY")
    fx_rate_used: Mapped[float | None] = Column(Numeric(18, 6))
    markup_percent: Mapped[float | None] = Column(Numeric(5, 2))
    total_cost: Mapped[float] = Column(Numeric(18, 4), nullable=False)
    drivers: Mapped[Dict[str, Any]] = Column(JSON, default=dict)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = Column(String(32), nullable=False)
    target_id: Mapped[str] = Column(String(36), nullable=False)
    action: Mapped[str] = Column(String(32), nullable=False)
    actor_id: Mapped[str] = Column(String(64), nullable=False)
    comment: Mapped[str | None] = Column(Text)
    created_at: Mapped[datetime] = Column(DateTime, default=utcnow, nullable=False)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = Column(String(32), nullable=False)
    target_id: Mapped[str] = Column(String(36), nullable=False)
    file_name: Mapped[str] = Column(String(255), nullable=False)
    file_url: Mapped[str] = Column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = Column(String(64))
    uploader_id: Mapped[str] = Column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = Column(DateTime, default=utcnow, nullable=False)
    category: Mapped[str | None] = Column(String(32))


class PlannerJob(Base, TimestampMixin):
    __tablename__ = "planner_import_jobs"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    initiative_id: Mapped[str] = Column(
        String(36), ForeignKey("cost_initiatives.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = Column(String(255), nullable=False)
    status: Mapped[str] = Column(String(32), nullable=False, default="pending")
    requested_by: Mapped[str] = Column(String(64), nullable=False)
    total_rows: Mapped[int] = Column(Integer, default=0)
    processed_rows: Mapped[int] = Column(Integer, default=0)
    error_rows: Mapped[int] = Column(Integer, default=0)
    errors: Mapped[List[Dict[str, Any]]] = Column(JSON, default=list)
    job_type: Mapped[str] = Column(String(64), nullable=False, default="line_item_import")
    payload: Mapped[Dict[str, Any]] = Column(JSON, default=dict)
    result: Mapped[Dict[str, Any]] = Column(JSON, default=dict)

    initiative: Mapped[CostInitiative] = relationship("CostInitiative")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = Column(String(50), nullable=False)
    target_id: Mapped[str] = Column(String(64), nullable=False)
    action: Mapped[str] = Column(String(50), nullable=False)
    actor_id: Mapped[str] = Column(String(64), nullable=False)
    payload: Mapped[Dict[str, Any]] = Column(JSON, default=dict)
    trace_id: Mapped[str] = Column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = Column(DateTime, default=utcnow, nullable=False)


class ScenarioFavorite(Base, TimestampMixin):
    __tablename__ = "scenario_favorites"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = Column(
        String(36), ForeignKey("scenario_versions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = Column(String(64), nullable=False)

    scenario: Mapped[ScenarioVersion] = relationship("ScenarioVersion", back_populates="favorites")


class BenchmarkFavorite(Base, TimestampMixin):
    __tablename__ = "benchmark_favorites"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    benchmark_key: Mapped[str] = Column(String(128), nullable=False)
    user_id: Mapped[str] = Column(String(64), nullable=False)
    payload: Mapped[Dict[str, Any]] = Column(JSON, default=dict)


class PlannerExecutorCallback(Base, TimestampMixin):
    __tablename__ = "planner_executor_callbacks"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = Column(
        String(36), ForeignKey("scenario_versions.id", ondelete="CASCADE"), nullable=False
    )
    callback_url: Mapped[str] = Column(String(255), nullable=False)
    signature: Mapped[str] = Column(String(128), nullable=False, default="")
    status: Mapped[str] = Column(String(32), nullable=False, default="pending")
    payload: Mapped[Dict[str, Any]] = Column(JSON, default=dict)
    trace_id: Mapped[str] = Column(String(64), nullable=False, default="")

    scenario: Mapped[ScenarioVersion] = relationship("ScenarioVersion")


class Material(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "materials"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    material_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    material_name: Mapped[str] = Column(String(255), nullable=False)
    material_type: Mapped[str] = Column(String(32), nullable=False, default="raw")
    category: Mapped[str | None] = Column(String(128))
    model_category: Mapped[str | None] = Column(String(128))
    unit: Mapped[str | None] = Column(String(32))
    purchase_unit: Mapped[str | None] = Column(String(32))
    inventory_unit: Mapped[str | None] = Column(String(32))
    conversion_formula: Mapped[str | None] = Column(String(255))
    unit_price: Mapped[float] = Column(Numeric(18, 4), nullable=False, default=0)
    currency: Mapped[str] = Column(String(8), nullable=False, default="CNY")
    supplier_code: Mapped[str | None] = Column(String(64))
    supplier_name: Mapped[str | None] = Column(String(255))
    usage_scope: Mapped[str | None] = Column(String(255))
    bom_notes: Mapped[str | None] = Column(Text)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    source_created_at: Mapped[datetime | None] = Column(DateTime)
    source_updated_at: Mapped[datetime | None] = Column(DateTime)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class VirtualMaterial(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "virtual_materials"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    virtual_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    name: Mapped[str] = Column(String(255), nullable=False)
    description: Mapped[str | None] = Column(Text)
    unit: Mapped[str | None] = Column(String(32))
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    version: Mapped[int] = Column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class VirtualMaterialBinding(Base, TimestampMixin):
    __tablename__ = "virtual_material_bindings"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    virtual_material_id: Mapped[str] = Column(
        String(36), ForeignKey("virtual_materials.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[str] = Column(
        String(36), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    material_type: Mapped[str] = Column(String(16), nullable=False, default="real")
    material_ref_id: Mapped[str] = Column(String(36), nullable=False)
    quantity_ratio: Mapped[float] = Column(Numeric(18, 6), nullable=False, default=1)
    loss_rate: Mapped[float] = Column(Numeric(5, 2), nullable=False, default=0)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    virtual_material: Mapped[VirtualMaterial] = relationship("VirtualMaterial")
    material: Mapped[Material] = relationship("Material")


class ProcessModule(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "process_modules"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    module_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    module_name: Mapped[str] = Column(String(255), nullable=False)
    description: Mapped[str | None] = Column(Text)
    category: Mapped[str | None] = Column(String(128))
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    version: Mapped[int] = Column(Integer, nullable=False, default=1)
    tags: Mapped[List[str]] = Column(JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class Process(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "processes"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    process_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    process_name: Mapped[str] = Column(String(255), nullable=False)
    description: Mapped[str | None] = Column(Text)
    default_module_id: Mapped[str | None] = Column(
        String(36), ForeignKey("process_modules.id", ondelete="SET NULL")
    )
    fixed_time_minutes: Mapped[float | None] = Column(Numeric(10, 2))
    hourly_rate: Mapped[float | None] = Column(Numeric(18, 4))
    piece_rate: Mapped[float | None] = Column(Numeric(18, 4))
    piece_rate_formula: Mapped[str | None] = Column(Text)
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    default_module: Mapped[ProcessModule | None] = relationship("ProcessModule")


class ProductModel(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "product_models"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    model_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    model_name: Mapped[str] = Column(String(255), nullable=False)
    description: Mapped[str | None] = Column(Text)
    category: Mapped[str | None] = Column(String(128))
    calc_mode: Mapped[str] = Column(String(32), nullable=False, default="ratio")
    fixed_price: Mapped[float | None] = Column(Numeric(18, 4))
    standard_width_mm: Mapped[float | None] = Column(Numeric(18, 4))
    standard_height_mm: Mapped[float | None] = Column(Numeric(18, 4))
    unit_of_measure: Mapped[str | None] = Column(String(32))
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    tags: Mapped[List[str]] = Column(JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class ModelMaterial(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_materials"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = Column(
        String(36), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=False
    )
    material_type: Mapped[str] = Column(String(16), nullable=False, default="real")
    material_ref_id: Mapped[str] = Column(String(36), nullable=False)
    material_code: Mapped[str | None] = Column(String(64))
    material_name: Mapped[str | None] = Column(String(255))
    unit_of_measure: Mapped[str | None] = Column(String(32))
    calculation_method: Mapped[str] = Column(String(32), nullable=False, default="count")
    base_quantity: Mapped[float] = Column(Numeric(18, 6), nullable=False, default=0)
    loss_rate: Mapped[float] = Column(Numeric(5, 2), nullable=False, default=0)
    unit_cost: Mapped[float | None] = Column(Numeric(18, 4))
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model: Mapped[ProductModel] = relationship("ProductModel")


class ModelProcess(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_processes"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = Column(
        String(36), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=False
    )
    process_id: Mapped[str] = Column(
        String(36), ForeignKey("processes.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model: Mapped[ProductModel] = relationship("ProductModel")
    process: Mapped[Process] = relationship("Process")


class ModelVariantRule(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_variant_rules"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = Column(
        String(36), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=False
    )
    rule_name: Mapped[str] = Column(String(255), nullable=False)
    source_material_ref_id: Mapped[str | None] = Column(String(36))
    trigger_type: Mapped[str] = Column(String(32), nullable=False)
    trigger_operator: Mapped[str] = Column(String(16), nullable=False, default="equals")
    trigger_value: Mapped[str | None] = Column(String(255))
    action_type: Mapped[str] = Column(String(32), nullable=False)
    target_material_ref_id: Mapped[str | None] = Column(String(36))
    quantity_delta: Mapped[float | None] = Column(Numeric(18, 6))
    status: Mapped[str] = Column(String(32), nullable=False, default="active")
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model: Mapped[ProductModel] = relationship("ProductModel")


class SkuModelMapping(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sku_model_mapping"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    sku_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    model_id: Mapped[str] = Column(
        String(36), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=False
    )
    source_system: Mapped[str | None] = Column(String(64))
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model: Mapped[ProductModel] = relationship("ProductModel")


class MaterialSyncJob(Base, TimestampMixin):
    __tablename__ = "material_sync_jobs"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    job_type: Mapped[str] = Column(String(32), nullable=False, default="materials")
    config_path: Mapped[str] = Column(String(512), nullable=False)
    requested_by: Mapped[str] = Column(String(64), nullable=False)
    status: Mapped[str] = Column(String(32), nullable=False, default="pending")
    limit: Mapped[int | None] = Column(Integer)
    dry_run: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    dump_path: Mapped[str | None] = Column(String(512))
    payload: Mapped[Dict[str, Any]] = Column(JSON, default=dict)
    result_json: Mapped[Dict[str, Any]] = Column(JSON, default=dict)
    error_message: Mapped[str | None] = Column(Text)
    started_at: Mapped[datetime | None] = Column(DateTime)
    finished_at: Mapped[datetime | None] = Column(DateTime)
