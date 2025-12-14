from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _decimal_to_str(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class InitiativeBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str
    description: Optional[str] = None
    owner_id: str
    sponsor: Optional[str] = None
    currency: str = "CNY"
    status: str = "draft"
    target_launch_date: Optional[date] = None
    tags: List[str] = Field(default_factory=list)


class InitiativeCreate(InitiativeBase):
    pass


class InitiativeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    sponsor: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    target_launch_date: Optional[date] = None
    tags: Optional[List[str]] = None


class InitiativeRead(InitiativeBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class PaginatedInitiativeResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[InitiativeRead]


class PackageBase(BaseModel):
    initiative_id: str
    name: str
    category: Optional[str] = None
    parent_package_id: Optional[str] = None
    owner_id: Optional[str] = None
    status: str = "draft"
    notes: Optional[str] = None


class PackageCreate(PackageBase):
    pass


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    parent_package_id: Optional[str] = None
    owner_id: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PackageRead(PackageBase):
    id: str
    created_at: datetime
    updated_at: datetime
    children: List["PackageRead"] = Field(default_factory=list)

    class Config:
        orm_mode = True


class PaginatedPackageResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PackageRead]


class SupplierQuoteBase(BaseModel):
    supplier_name: str
    contact: Optional[str] = None
    line_item_id: str
    quote_version: int
    currency: str = "CNY"
    unit_cost: Decimal
    moq: Optional[int] = None
    lead_time_days: Optional[int] = None
    valid_through: Optional[date] = None
    attachments: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SupplierQuoteCreate(SupplierQuoteBase):
    pass


class SupplierQuoteRead(SupplierQuoteBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class LineItemBase(BaseModel):
    package_id: str
    type: str
    reference_code: Optional[str] = None
    description: str
    unit_of_measure: str
    quantity: Decimal
    unit_cost_estimate: Decimal
    currency: str = "CNY"
    supplier_id: Optional[str] = None
    preferred_quote_id: Optional[str] = None
    status: str = "draft"
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class LineItemCreate(LineItemBase):
    pass


class LineItemUpdate(BaseModel):
    package_id: Optional[str] = None
    type: Optional[str] = None
    reference_code: Optional[str] = None
    description: Optional[str] = None
    unit_of_measure: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_cost_estimate: Optional[Decimal] = None
    currency: Optional[str] = None
    supplier_id: Optional[str] = None
    preferred_quote_id: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class LineItemRead(LineItemBase):
    id: str
    created_at: datetime
    updated_at: datetime
    supplier_quotes: List[SupplierQuoteRead] = Field(default_factory=list)

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class PaginatedLineItemResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[LineItemRead]


class PlannerJobRead(BaseModel):
    id: str
    initiative_id: str
    file_name: Optional[str] = None
    status: str
    requested_by: str
    total_rows: int
    processed_rows: int
    error_rows: int
    errors: List[Dict[str, Any]]
    job_type: str
    payload: Dict[str, Any]
    result: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class MaterialSyncJobRead(BaseModel):
    id: str
    job_type: str
    config_path: str
    requested_by: str
    status: str
    limit: Optional[int]
    dry_run: bool
    dump_path: Optional[str]
    payload: Dict[str, Any]
    result_json: Dict[str, Any]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class PaginatedMaterialSyncJobResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[MaterialSyncJobRead]


class MaterialRead(BaseModel):
    id: str
    material_code: str
    material_name: str
    material_type: str
    category: Optional[str]
    model_category: Optional[str]
    unit: Optional[str]
    purchase_unit: Optional[str]
    inventory_unit: Optional[str]
    unit_price: Decimal
    currency: str
    supplier_code: Optional[str]
    supplier_name: Optional[str]
    status: str
    is_active: bool
    usage_scope: Optional[str]
    bom_notes: Optional[str]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class PaginatedMaterialResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[MaterialRead]


class MaterialUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    status: Optional[str] = Field(None, max_length=32)


class MaterialExportRequest(BaseModel):
    format: str = Field("csv", regex="^(csv|xlsx)$")
    search: Optional[str] = None
    material_type: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class AssumptionBase(BaseModel):
    initiative_id: str
    name: str
    type: str
    value: Decimal
    unit: Optional[str] = None
    effective_date: date
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class AssumptionCreate(AssumptionBase):
    pass


class AssumptionRead(AssumptionBase):
    id: str
    created_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class AssumptionLatestResponse(BaseModel):
    initiative_id: str
    type: str
    latest: Optional[AssumptionRead]

    class Config:
        orm_mode = True
        json_encoders = {Decimal: _decimal_to_str}


class ScenarioCloneRequest(BaseModel):
    code: str
    name: str
    requested_by: str
    line_item_ids: Optional[List[str]] = None


class ScenarioCloneResponse(BaseModel):
    job_id: str
    scenario_id: str


class ScenarioFavoriteStatus(BaseModel):
    scenario_id: str
    favorite: bool


class ScenarioFavoriteRequest(BaseModel):
    user_id: str


class ScenarioRead(BaseModel):
    id: str
    code: str
    name: str
    status: str
    baseline_flag: bool
    total_cost: Decimal | None = None
    updated_at: datetime
    is_favorite: bool = False

    class Config:
        orm_mode = True


class ScenarioListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ScenarioRead]


class ScenarioDiffLine(BaseModel):
    line_item_id: str
    reference_code: Optional[str] = None
    description: str
    package_id: str
    package_name: Optional[str] = None
    item_type: Optional[str] = None
    quantity_diff: Decimal
    unit_cost_diff: Decimal
    total_cost_diff: Decimal
    source_total: Decimal
    target_total: Decimal


class ScenarioDiffSummary(BaseModel):
    source_scenario_id: str
    target_scenario_id: str
    total_cost_source: Decimal
    total_cost_target: Decimal
    variance: Decimal
    variance_percent: float


class ScenarioDiffResponse(BaseModel):
    job_id: str
    summary: ScenarioDiffSummary
    line_diffs: List[ScenarioDiffLine]
    page: int
    page_size: int
    total: int


class ScenarioExportRequest(BaseModel):
    requested_by: str
    comment: Optional[str] = None


class ScenarioExportResponse(BaseModel):
    job_id: str
    scenario_id: str
    executor_reference: str


class BenchmarkFavoriteCreate(BaseModel):
    benchmark_key: str
    user_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class BenchmarkFavoriteRead(BenchmarkFavoriteCreate):
    id: str
    created_at: datetime

    class Config:
        orm_mode = True


class AuditLogRead(BaseModel):
    id: str
    target_type: str
    target_id: str
    action: str
    actor_id: str
    payload: Dict[str, Any]
    trace_id: str
    created_at: datetime

    class Config:
        orm_mode = True


class PaginatedAuditLogResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogRead]


class ApprovalActionBase(BaseModel):
    scenario_id: str
    actor_id: str
    actor_role: str
    comment: Optional[str] = None


class ApprovalSubmitRequest(ApprovalActionBase):
    pass


class ApprovalApproveRequest(ApprovalActionBase):
    set_baseline: bool = False


class ApprovalRejectRequest(ApprovalActionBase):
    pass


class ApprovalActionResponse(BaseModel):
    scenario_id: str
    scenario_status: str
    initiative_status: str
    baseline_flag: bool


class ProcessSyncResponse(BaseModel):
    total_fetched: int
    processes_created: int
    processes_updated: int
    modules_created: int
    models_created: int
    model_links_created: int
    model_links_updated: int
    skipped: int
    errors: List[str]

    @classmethod
    def from_result(cls, result: Any) -> "ProcessSyncResponse":
        return cls(**result.dict())
