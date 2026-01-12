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
    UniqueConstraint,
    and_,
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
    calculation_method: Mapped[str] = Column(String(32), nullable=False, default="count")
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
    is_bom_material: Mapped[bool | None] = Column(Boolean, default=False, index=True)
    conversion_purchase_to_bom: Mapped[float] = Column(Numeric(18, 6), default=1)
    conversion_bom_to_inventory: Mapped[float] = Column(Numeric(18, 6), default=1)
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
    category: Mapped[str | None] = Column(String(128))
    unit: Mapped[str | None] = Column(String(32), nullable=False, default="套")
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    version: Mapped[int] = Column(Integer, nullable=False, default=1)
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


class CodeCounter(Base):
    __tablename__ = "code_counters"

    prefix: Mapped[str] = Column(String(16), primary_key=True)
    next_value: Mapped[int] = Column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime | None] = Column(DateTime)


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
    materials: Mapped[List["ProcessModuleMaterial"]] = relationship(
        "ProcessModuleMaterial",
        primaryjoin="and_(ProcessModule.id==ProcessModuleMaterial.module_id, ProcessModuleMaterial.is_archived.is_(False))",
        order_by="ProcessModuleMaterial.sequence_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    steps: Mapped[List["ProcessModuleStep"]] = relationship(
        "ProcessModuleStep",
        primaryjoin="and_(ProcessModule.id==ProcessModuleStep.module_id, ProcessModuleStep.is_archived.is_(False))",
        order_by="ProcessModuleStep.sequence_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProcessModuleMaterial(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "process_module_materials"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = Column(
        String(36), ForeignKey("process_modules.id", ondelete="CASCADE"), nullable=False
    )
    material_kind: Mapped[str] = Column(String(16), nullable=False, default="real")
    material_ref_id: Mapped[str | None] = Column(String(36))
    material_code: Mapped[str | None] = Column(String(64))
    material_name: Mapped[str | None] = Column(String(255))
    unit_of_measure: Mapped[str | None] = Column(String(32))
    calculation_method: Mapped[str] = Column(String(32), nullable=False, default="count")
    quantity: Mapped[float] = Column(Numeric(18, 6), nullable=False, default=0)
    loss_rate: Mapped[float] = Column(Numeric(5, 2), nullable=False, default=0)
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    material_category: Mapped[str | None] = Column(String(128))
    selection_notes: Mapped[str | None] = Column(Text)
    loss_notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class ProcessModuleStep(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "process_module_steps"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = Column(
        String(36), ForeignKey("process_modules.id", ondelete="CASCADE"), nullable=False
    )
    process_id: Mapped[str | None] = Column(
        String(36), ForeignKey("processes.id", ondelete="SET NULL")
    )
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    team_name: Mapped[str | None] = Column(String(128))
    pricing_method: Mapped[str] = Column(String(32), nullable=False, default="count")
    work_minutes: Mapped[float] = Column(Numeric(10, 2), nullable=False, default=0)
    unit_of_measure: Mapped[str | None] = Column(String(32))
    description: Mapped[str | None] = Column(Text)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    process: Mapped[Process | None] = relationship("Process")


class Process(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "processes"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    process_code: Mapped[str] = Column(String(64), unique=True, nullable=False)
    process_name: Mapped[str] = Column(String(255), nullable=False)
    description: Mapped[str | None] = Column(Text)
    category: Mapped[str | None] = Column(String(128))
    team_name: Mapped[str | None] = Column(String(128))
    charging_mode: Mapped[str] = Column(String(32), nullable=False, default="count")
    standard_rate: Mapped[float | None] = Column(Numeric(18, 6))
    unit_of_measure: Mapped[str | None] = Column(String(32))
    status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class ProcessFeedback(Base, TimestampMixin, SoftDeleteMixin):
    """
    AI/continuous-improvement feedback records for processes.

    This table is designed as a durable learning corpus:
    - link to a process
    - store observed execution outcomes (time/cost/quality) with optional context references
    - keep everything extensible via metadata_json
    """

    __tablename__ = "process_feedback"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    process_id: Mapped[str] = Column(String(36), ForeignKey("processes.id", ondelete="CASCADE"), nullable=False, index=True)

    # optional context pointers
    source_type: Mapped[str | None] = Column(String(32))  # e.g. model_version / process_module / order / manual
    source_id: Mapped[str | None] = Column(String(64))

    product_line_tag: Mapped[str | None] = Column(String(64))  # e.g. 画艺/布艺/通用
    team_name: Mapped[str | None] = Column(String(128))

    quantity: Mapped[float | None] = Column(Numeric(18, 6))
    unit_of_measure: Mapped[str | None] = Column(String(32))
    actual_minutes: Mapped[float | None] = Column(Numeric(10, 2))
    actual_cost: Mapped[float | None] = Column(Numeric(18, 6))
    quality_score: Mapped[float | None] = Column(Numeric(5, 2))  # 0-100 or 0-10 (caller defines)
    is_success: Mapped[bool | None] = Column(Boolean)

    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    process: Mapped["Process"] = relationship("Process")


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


class ProductModelVersion(Base, TimestampMixin, SoftDeleteMixin):
    """
    Version snapshot for a product model.

    Semantics:
    - `version_kind`: sample (打样/单品算价) or standard (标准 1m×1m 发布版本)
    - `version_status`: draft/published/archived
    - version-level metadata should freeze placeholder_mappings and spec, enabling reproducible preview.
    """

    __tablename__ = "product_model_versions"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = Column(
        String(36), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_kind: Mapped[str] = Column(String(32), nullable=False, default="sample")
    version_status: Mapped[str] = Column(String(32), nullable=False, default="draft")
    version_label: Mapped[str | None] = Column(String(64))
    published_at: Mapped[datetime | None] = Column(DateTime)
    published_by: Mapped[str | None] = Column(String(64))
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model: Mapped["ProductModel"] = relationship("ProductModel")


class ModelVersionMaterial(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_version_materials"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = Column(
        String(36),
        ForeignKey("product_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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

    version: Mapped["ProductModelVersion"] = relationship("ProductModelVersion")


class ModelVersionProcess(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_version_processes"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = Column(
        String(36),
        ForeignKey("product_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_id: Mapped[str] = Column(
        String(36), ForeignKey("processes.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    version: Mapped["ProductModelVersion"] = relationship("ProductModelVersion")
    process: Mapped["Process"] = relationship("Process")


class ProductModelLineVariant(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "product_model_line_variants"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = Column(
        String(36), ForeignKey("product_model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_line_id: Mapped[str] = Column(
        String(36), ForeignKey("model_version_materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[int] = Column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    action: Mapped[str] = Column(String(32), nullable=False, default="replace_bundle")
    stop_on_hit: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = Column(Text)
    conditions_json: Mapped[Dict[str, Any]] = Column("conditions", JSON, default=dict)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    version: Mapped["ProductModelVersion"] = relationship("ProductModelVersion")
    base_line: Mapped["ModelVersionMaterial"] = relationship("ModelVersionMaterial")
    items: Mapped[List["ProductModelLineVariantItem"]] = relationship(
        "ProductModelLineVariantItem",
        primaryjoin="and_(ProductModelLineVariant.id==ProductModelLineVariantItem.variant_id, ProductModelLineVariantItem.is_archived.is_(False))",
        order_by="ProductModelLineVariantItem.sequence_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProductModelLineVariantItem(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "product_model_line_variant_items"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    variant_id: Mapped[str] = Column(
        String(36), ForeignKey("product_model_line_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    material_kind: Mapped[str] = Column(String(16), nullable=False, default="real")
    material_ref_id: Mapped[str | None] = Column(String(36))
    material_code: Mapped[str | None] = Column(String(64))
    material_name: Mapped[str | None] = Column(String(255))
    unit_of_measure: Mapped[str | None] = Column(String(32))
    calculation_method: Mapped[str] = Column(String(32), nullable=False, default="count")
    base_quantity: Mapped[float] = Column(Numeric(18, 6), nullable=False, default=0)
    fixed_quantity: Mapped[float] = Column(Numeric(18, 6), nullable=False, default=0)
    coverage_ratio: Mapped[float] = Column(Numeric(18, 6), nullable=False, default=1)
    loss_rate: Mapped[float] = Column(Numeric(5, 2), nullable=False, default=0)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    variant: Mapped["ProductModelLineVariant"] = relationship("ProductModelLineVariant", back_populates="items")


class ModelVersionModule(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_version_modules"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = Column(
        String(36),
        ForeignKey("product_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_id: Mapped[str] = Column(
        String(36), ForeignKey("process_modules.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    version: Mapped["ProductModelVersion"] = relationship("ProductModelVersion")
    module: Mapped["ProcessModule"] = relationship("ProcessModule")


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
    # Optional: bind rules to a specific version for fully reproducible SKU pricing.
    version_id: Mapped[str | None] = Column(
        String(36), ForeignKey("product_model_versions.id", ondelete="SET NULL"), nullable=True, index=True
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
    version: Mapped["ProductModelVersion | None"] = relationship("ProductModelVersion")


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


class SkuModelVersionMapping(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sku_model_version_mapping"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    # Note: sku_code is NOT globally unique to support binding history.
    # Uniqueness is enforced for active bindings via a partial unique index in migrations.
    sku_code: Mapped[str] = Column(String(64), nullable=False, index=True)
    model_version_id: Mapped[str] = Column(
        String(36),
        ForeignKey("product_model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_system: Mapped[str | None] = Column(String(64))
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model_version: Mapped["ProductModelVersion"] = relationship("ProductModelVersion")


class BundleTemplate(Base, TimestampMixin, SoftDeleteMixin):
    """
    Bundle/kit template definition addressed by a short human-friendly code.

    The code is intended to be embedded in ERP/customer-facing spec_text, e.g.:
    - "BUNDLE:K8F3J2"
    """

    __tablename__ = "bundle_templates"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = Column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = Column(String(128))
    components_json: Mapped[List[Dict[str, Any]]] = Column("components", JSON, default=list, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict, nullable=False)


class ShippingRule(Base, TimestampMixin, SoftDeleteMixin):
    """
    Shipping / conditional material rules.

    This module is intentionally separated from product model variant rules:
    - Variant rules: product BOM substitution (生产/核算口径)
    - Shipping rules: order/shipping conditional materials (发货/按单扣库口径)
    """

    __tablename__ = "shipping_rules"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    rule_name: Mapped[str] = Column(String(255), nullable=False)
    priority: Mapped[int] = Column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    conditions_json: Mapped[Dict[str, Any]] = Column("conditions", JSON, default=dict, nullable=False)
    outputs_json: Mapped[List[Dict[str, Any]]] = Column("outputs", JSON, default=list, nullable=False)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict, nullable=False)


class ModelProcessModule(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "model_process_modules"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = Column(
        String(36), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[str] = Column(
        String(36), ForeignKey("process_modules.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = Column(Text)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    model: Mapped[ProductModel] = relationship("ProductModel")
    module: Mapped["ProcessModule"] = relationship("ProcessModule")


class TaxonomyItem(Base, TimestampMixin, SoftDeleteMixin):
    """
    Flat taxonomy dictionary item for admin-maintained categories.

    Notes:
    - Keep it flat (no parent_id) per current project requirements.
    - `scopes_json`: required list; use ["*"] to mean universal (all product lines).
    """

    __tablename__ = "taxonomy_items"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    domain: Mapped[str] = Column(String(64), nullable=False, index=True)
    name: Mapped[str] = Column(String(128), nullable=False)
    scopes_json: Mapped[List[str]] = Column("scopes", JSON, default=list, nullable=False)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    source: Mapped[str] = Column(String(32), nullable=False, default="local")
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class TaxonomyMapping(Base, TimestampMixin):
    """
    Map external values (e.g. YiDa raw category strings) to internal taxonomy items.
    """

    __tablename__ = "taxonomy_mappings"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    domain: Mapped[str] = Column(String(64), nullable=False, index=True)
    external_system: Mapped[str] = Column(String(32), nullable=False, default="yida", index=True)
    external_value: Mapped[str] = Column(String(255), nullable=False)
    taxonomy_item_id: Mapped[str] = Column(
        String(36), ForeignKey("taxonomy_items.id", ondelete="CASCADE"), nullable=False, index=True
    )

    item: Mapped["TaxonomyItem"] = relationship("TaxonomyItem")


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


class ShipmentImportBatch(Base, TimestampMixin):
    __tablename__ = "shipment_import_batches"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    file_name: Mapped[str | None] = Column(String(255))
    file_hash: Mapped[str] = Column(String(64), nullable=False, unique=True, index=True)
    export_date: Mapped[str | None] = Column(String(32))
    requested_by: Mapped[str | None] = Column(String(64))
    status: Mapped[str] = Column(String(32), nullable=False, default="processing")
    total_rows: Mapped[int] = Column(Integer, nullable=False, default=0)
    inserted_rows: Mapped[int] = Column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = Column(Integer, nullable=False, default=0)
    exception_rows: Mapped[int] = Column(Integer, nullable=False, default=0)
    warnings_json: Mapped[List[Dict[str, Any]]] = Column("warnings", JSON, default=list)
    result_json: Mapped[Dict[str, Any]] = Column("result", JSON, default=dict)

    lines: Mapped[List["ShipmentLine"]] = relationship(
        "ShipmentLine",
        primaryjoin="ShipmentImportBatch.id==ShipmentLine.batch_id",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    exceptions: Mapped[List["ShipmentExceptionQueue"]] = relationship(
        "ShipmentExceptionQueue",
        primaryjoin="ShipmentImportBatch.id==ShipmentExceptionQueue.batch_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    bom_snapshots: Mapped[List["BomSnapshot"]] = relationship(
        "BomSnapshot",
        primaryjoin="ShipmentImportBatch.id==BomSnapshot.batch_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ShipmentLine(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "shipment_lines"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = Column(
        String(36), ForeignKey("shipment_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_index: Mapped[int] = Column(Integer, nullable=False, default=0)

    shipment_no: Mapped[str | None] = Column(String(64), index=True)
    completed_at: Mapped[datetime | None] = Column(DateTime, index=True)
    channel: Mapped[str | None] = Column(String(128))
    sku_code: Mapped[str | None] = Column(String(64), index=True)
    spec_text: Mapped[str | None] = Column(Text)
    spec_hash: Mapped[str | None] = Column(String(64), index=True)
    qty: Mapped[float | None] = Column(Numeric(18, 6))
    revenue_amount: Mapped[float | None] = Column(Numeric(18, 6))

    external_line_key_hash: Mapped[str] = Column(String(64), nullable=False, unique=True, index=True)
    revision_group_hash: Mapped[str | None] = Column(String(64), index=True)
    revision_no: Mapped[int] = Column(Integer, nullable=False, default=1)
    superseded_by_id: Mapped[str | None] = Column(String(36), ForeignKey("shipment_lines.id"))
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)

    raw_row_json: Mapped[Dict[str, Any]] = Column("raw_row", JSON, default=dict)
    normalize_warnings_json: Mapped[List[Dict[str, Any]]] = Column("normalize_warnings", JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    batch: Mapped["ShipmentImportBatch"] = relationship("ShipmentImportBatch", back_populates="lines")


class SpecParseSnapshot(Base, TimestampMixin):
    __tablename__ = "spec_parse_snapshots"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    spec_hash: Mapped[str] = Column(String(64), nullable=False, unique=True, index=True)
    spec_text: Mapped[str] = Column(Text, nullable=False)
    tokens_json: Mapped[List[str]] = Column("tokens", JSON, default=list)
    dimensions_json: Mapped[Dict[str, Any]] = Column("dimensions", JSON, default=dict)
    parser_version: Mapped[str] = Column(String(32), nullable=False, default="v1")
    parse_json: Mapped[Dict[str, Any]] = Column("parse", JSON, default=dict)


class BomSnapshot(Base, TimestampMixin):
    __tablename__ = "bom_snapshots"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = Column(
        String(36), ForeignKey("shipment_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shipment_line_id: Mapped[str] = Column(
        String(36), ForeignKey("shipment_lines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shipment_no: Mapped[str | None] = Column(String(64), index=True)
    sku_code: Mapped[str | None] = Column(String(64), index=True)
    model_version_id: Mapped[str | None] = Column(String(36), ForeignKey("product_model_versions.id"))
    spec_hash: Mapped[str | None] = Column(String(64), index=True)
    qty: Mapped[float | None] = Column(Numeric(18, 6))
    final_lines_json: Mapped[List[Dict[str, Any]]] = Column("final_lines", JSON, default=list)
    trace_json: Mapped[Dict[str, Any]] = Column("trace", JSON, default=dict)
    generated_at: Mapped[datetime | None] = Column(DateTime, default=utcnow)

    @property
    def final_material_lines(self) -> List[Dict[str, Any]]:
        return list(self.final_lines_json or [])

    @property
    def trace(self) -> Dict[str, Any]:
        return dict(self.trace_json or {})


class ShipmentExceptionQueue(Base, TimestampMixin):
    __tablename__ = "shipment_exception_queue"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = Column(
        String(36), ForeignKey("shipment_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shipment_line_id: Mapped[str | None] = Column(
        String(36), ForeignKey("shipment_lines.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reason: Mapped[str] = Column(String(64), nullable=False, index=True)
    message: Mapped[str | None] = Column(Text)
    payload_json: Mapped[Dict[str, Any]] = Column("payload", JSON, default=dict)
    resolved_at: Mapped[datetime | None] = Column(DateTime)


class SkuMaster(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sku_master"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    erp_sku_barcode: Mapped[str] = Column(String(64), nullable=False, unique=True, index=True)
    platform_product_id: Mapped[str | None] = Column(String(64))
    platform_sku_id: Mapped[str | None] = Column(String(64))
    channel: Mapped[str | None] = Column(String(128))
    product_name: Mapped[str | None] = Column(String(255))
    product_code: Mapped[str | None] = Column(String(128))
    spec_text: Mapped[str | None] = Column(Text)
    images_json: Mapped[Dict[str, Any]] = Column("images", JSON, default=dict)
    match_status: Mapped[str | None] = Column(String(64))
    source_updated_at: Mapped[datetime | None] = Column(DateTime)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)


class ShopSkuMapping(Base, TimestampMixin, SoftDeleteMixin):
    """
    Platform/shop SKU mapping (preserve platform_sku_id dimension).

    Why: In real data, one ERP barcode can be reused across multiple platform_sku_id (and even across platform_product_id).
    We keep `SkuMaster` unique on erp_sku_barcode as SSOT for costing, while this table preserves the many-side rows for
    reverse-sync and shop-level reconciliation.
    """

    __tablename__ = "shop_sku_mappings"

    id: Mapped[str] = Column(String(36), primary_key=True, default=_uuid)
    channel: Mapped[str | None] = Column(String(128), index=True)
    platform_product_id: Mapped[str | None] = Column(String(64), index=True)
    platform_sku_id: Mapped[str] = Column(String(64), nullable=False, index=True)

    # may be empty in exports; keep nullable (mapping can exist without barcode)
    erp_sku_barcode: Mapped[str | None] = Column(String(64), index=True)

    shop_spec_code: Mapped[str | None] = Column(String(128))
    production_process: Mapped[str | None] = Column(Text)
    match_status: Mapped[str | None] = Column(String(64))
    match_method: Mapped[str | None] = Column(String(64))
    source_updated_at: Mapped[datetime | None] = Column(DateTime)
    metadata_json: Mapped[Dict[str, Any]] = Column("metadata", JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("channel", "platform_sku_id", "is_archived", name="uq_shop_sku_channel_platform_sku_active"),
    )

