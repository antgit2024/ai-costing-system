from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

import json

from pydantic import BaseModel, Field, root_validator, validator
from src.config import settings

CalculationMethod = Literal["area", "perimeter", "count", "width", "height"]
ProcessChargingMode = Literal["fixed", "count", "area", "perimeter", "width", "height"]
LaborPricingMethod = Literal["fixed", "count", "area", "perimeter", "width", "height"]
MaterialReferenceKind = Literal["real", "bom", "virtual"]
ProductCalcMode = Literal["ratio", "fixed", "independent"]
VariantTriggerType = Literal["sku_contains", "area_gte", "perimeter_gte"]
VariantActionType = Literal["replace_material", "add_material"]
LineVariantAction = Literal["replace_bundle", "replace_self", "remove_self", "add_siblings"]


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
    calculation_method: CalculationMethod
    unit: Optional[str]
    purchase_unit: Optional[str]
    inventory_unit: Optional[str]
    unit_price: Decimal
    currency: str
    supplier_code: Optional[str]
    supplier_name: Optional[str]
    status: str
    is_active: bool
    is_bom_material: Optional[bool] = None
    images: List[str] = Field(default_factory=list)
    conversion_purchase_to_bom: Decimal
    conversion_bom_to_inventory: Decimal
    usage_scope: Optional[str]
    bom_notes: Optional[str]
    source_created_at: Optional[datetime]
    source_updated_at: Optional[datetime]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    updated_at: datetime

    @staticmethod
    def _extract_image_sources(metadata: dict | None) -> list[str]:
        if not metadata:
            return []
        candidates = metadata.get("images")
        if not candidates:
            candidates = (
                metadata.get("imageField_lbef2r0b")
                or (metadata.get("raw_form_data") or {}).get("imageField_lbef2r0b")
            )
        if not candidates:
            return []
        data: list[Any]
        if isinstance(candidates, str):
            try:
                parsed = json.loads(candidates)
            except json.JSONDecodeError:
                return [candidates]
            else:
                data = parsed if isinstance(parsed, list) else [parsed]
        elif isinstance(candidates, list):
            data = candidates
        else:
            data = [candidates]

        normalized: list[str] = []
        for item in data:
            if isinstance(item, str) and item:
                normalized.append(item)
            elif isinstance(item, dict):
                url = (
                    item.get("downloadUrl")
                    or item.get("url")
                    or item.get("previewUrl")
                )
                if isinstance(url, str) and url:
                    normalized.append(url)
        return normalized

    @root_validator(pre=True)
    def _populate_images(cls, values):
        if not isinstance(values, dict):
            values = dict(values)
        metadata = values.get("metadata_json") or {}
        raw_images = cls._extract_image_sources(metadata)
        # Persist normalized list back so download endpoint can reuse it.
        metadata["images"] = raw_images
        values["metadata_json"] = metadata
        material_id = values.get("id")
        api_prefix = settings.planner_api_prefix.rstrip("/")
        router_prefix = "/planner"
        base_path = f"{api_prefix}{router_prefix}/base-config/materials"
        if material_id and raw_images:
            values["images"] = [
                f"{base_path}/{material_id}/images/{idx}"
                for idx, _ in enumerate(raw_images)
            ]
        else:
            values["images"] = []
        return values

    @validator("conversion_purchase_to_bom", "conversion_bom_to_inventory", pre=True)
    def _ensure_decimal(cls, value):
        if value is None:
            return Decimal("1")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def dict(self, *args, **kwargs):
        data = super().dict(*args, **kwargs)
        data["conversion_purchase_to_bom"] = _decimal_to_str(Decimal(str(data["conversion_purchase_to_bom"])))
        data["conversion_bom_to_inventory"] = _decimal_to_str(Decimal(str(data["conversion_bom_to_inventory"])))
        return data

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class PaginatedMaterialResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[MaterialRead]
    categories: List[str] = Field(default_factory=list)


class MaterialUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    status: Optional[str] = Field(None, max_length=32)
    is_bom_material: Optional[bool] = None
    unit: Optional[str] = Field(None, max_length=32)
    inventory_unit: Optional[str] = Field(None, max_length=32)
    conversion_purchase_to_bom: Optional[Decimal] = Field(None, gt=0)
    conversion_bom_to_inventory: Optional[Decimal] = Field(None, gt=0)
    bom_unit_price: Optional[Decimal] = Field(None, ge=0)
    calculation_method: Optional[CalculationMethod] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")


class MaterialExportRequest(BaseModel):
    format: str = Field("csv", regex="^(csv|xlsx)$")
    search: Optional[str] = None
    material_type: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    is_bom_material: Optional[bool] = None


class VirtualMaterialCreateRequest(BaseModel):
    virtual_code: str = Field(..., max_length=64)
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    virtual_kind: Literal["recipe", "kit", "placeholder"] = Field(
        "kit",
        description="虚拟物料类型：recipe=配方型(按比例且单位一致)，kit=套件型(按数量且子物料可不同单位)，placeholder=占位型(不绑定子物料，BOM单价为0)",
    )
    unit: Optional[str] = Field(None, max_length=32)
    status: str = Field("draft", max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class VirtualMaterialUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    virtual_kind: Optional[Literal["recipe", "kit", "placeholder"]] = Field(
        None,
        description="虚拟物料类型：recipe=配方型(按比例且单位一致)，kit=套件型(按数量且子物料可不同单位)，placeholder=占位型(不绑定子物料，BOM单价为0)",
    )
    unit: Optional[str] = Field(None, max_length=32)
    status: Optional[str] = Field(None, max_length=32)
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class VirtualMaterialBindingInput(BaseModel):
    material_id: str
    quantity_ratio: Decimal = Field(..., gt=0)
    loss_rate: Decimal = Field(Decimal("0"), ge=0, le=100)
    binding_type: Optional[Literal["ratio", "quantity"]] = Field("ratio")

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class VirtualMaterialBindingBatchRequest(BaseModel):
    bindings: List[VirtualMaterialBindingInput] = Field(default_factory=list)


class VirtualMaterialBindingRead(BaseModel):
    material_id: str
    material_code: str
    material_name: str
    unit: Optional[str]
    quantity_ratio: Decimal
    loss_rate: Decimal
    currency: Optional[str]
    purchase_unit_price: Optional[Decimal]
    purchase_unit: Optional[str]
    bom_unit_price: Optional[Decimal]
    bom_unit: Optional[str]
    image_url: Optional[str]
    status: Optional[str]
    is_active: Optional[bool]
    binding_type: Literal["ratio", "quantity"]

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class VirtualMaterialRead(BaseModel):
    id: str
    virtual_code: str
    name: str
    description: Optional[str]
    category: Optional[str]
    virtual_kind: Literal["recipe", "kit", "placeholder"] = "kit"
    unit: Optional[str]
    status: str
    version: int
    notes: Optional[str]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    bindings: List[VirtualMaterialBindingRead] = Field(default_factory=list)

    @root_validator(pre=True)
    def _fill_virtual_kind(cls, values):
        # Backward compatible: old rows may not have metadata_json.virtual_kind.
        data = dict(values)
        meta = data.get("metadata_json") or data.get("metadata") or {}
        kind = meta.get("virtual_kind") if isinstance(meta, dict) else None
        data["virtual_kind"] = kind or data.get("virtual_kind") or "kit"
        return data

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class PaginatedVirtualMaterialResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[VirtualMaterialRead]


class VirtualMaterialReferenceRead(BaseModel):
    virtual_material_id: str
    virtual_code: str
    virtual_name: str
    status: str
    quantity_ratio: Decimal
    loss_rate: Decimal

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class VirtualMaterialInventoryRequest(BaseModel):
    quantity: Decimal = Field(..., gt=0)
    calculation_method: Optional[CalculationMethod] = Field(
        None, description="调用方此次盘点的计算方式，示例：count/area/height 等"
    )
    usage_context: Optional[str] = Field(
        None, max_length=64, description="调用方自定义场景标识（如产品 SKU/加工阶段）"
    )

    @root_validator
    def _validate_context(cls, values):
        calc = values.get("calculation_method")
        context = values.get("usage_context")
        if calc is None and (context is None or context == ""):
            raise ValueError("calculation_method 或 usage_context 至少需要提供一个")
        return values

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class VirtualMaterialInventoryItem(BaseModel):
    material_id: str
    material_code: str
    material_name: str
    unit: Optional[str]
    quantity_ratio: Decimal
    loss_rate: Decimal
    required_quantity: Decimal

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class VirtualMaterialInventoryResponse(BaseModel):
    virtual_material_id: str
    virtual_code: str
    virtual_name: str
    requested_quantity: Decimal
    calculation_method: Optional[CalculationMethod] = None
    usage_context: Optional[str] = None
    items: List[VirtualMaterialInventoryItem]

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProcessModuleMaterialInput(BaseModel):
    material_kind: MaterialReferenceKind = Field("real")
    material_ref_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    calculation_method: CalculationMethod = Field("count")
    quantity: Decimal = Field(..., gt=0)
    loss_rate: Decimal = Field(Decimal("0"), ge=0, le=100)
    sequence_order: Optional[int] = None
    material_category: Optional[str] = Field(None, max_length=128)
    selection_notes: Optional[str] = None
    loss_notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessModuleMaterialRead(ProcessModuleMaterialInput):
    id: str


class ProcessReferenceRead(BaseModel):
    id: str
    process_code: str
    process_name: str
    charging_mode: ProcessChargingMode
    standard_rate: Optional[Decimal]
    unit_of_measure: Optional[str]
    team_name: Optional[str]
    category: Optional[str]

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProcessModuleStepInput(BaseModel):
    process_id: Optional[str] = None
    sequence_order: Optional[int] = None
    team_name: Optional[str] = Field(None, max_length=128)
    pricing_method: LaborPricingMethod = Field("count")
    work_minutes: Decimal = Field(Decimal("0"), ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    description: Optional[str] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ModelProcessModuleInput(BaseModel):
    module_id: str
    sequence_order: Optional[int] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class ModelProcessModuleRead(ModelProcessModuleInput):
    id: str
    # Avoid ForwardRef issues (schemas order); keep a lightweight embedded summary dict for UI.
    module: Optional[Dict[str, Any]] = None


class ProductModelCreateRequest(BaseModel):
    model_code: Optional[str] = Field(None, max_length=64, description="模型编码；为空则系统自动生成")
    model_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    calc_mode: ProductCalcMode = Field("ratio", description="产品模型计算模式：ratio=比例，一口价=fixed，独立=independent")
    fixed_price: Optional[Decimal] = Field(
        None, ge=0, description="一口价模式下的固定价格（单位：元）；非 fixed 模式可为空"
    )
    status: str = Field("draft", max_length=32)
    tags: List[str] = Field(default_factory=list)
    standard_width_mm: Optional[Decimal] = Field(None, ge=0)
    standard_height_mm: Optional[Decimal] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    modules: List[ModelProcessModuleInput] = Field(default_factory=list)

    @root_validator
    def _validate_calc_mode(cls, values):
        mode = values.get("calc_mode") or "ratio"
        fixed_price = values.get("fixed_price")
        if mode == "fixed" and fixed_price is None:
            raise ValueError("calc_mode=fixed 时必须提供 fixed_price")
        if mode != "fixed":
            # Keep storage clean; fixed_price is only meaningful in fixed mode.
            values["fixed_price"] = None
        code = values.get("model_code")
        if code is not None and str(code).strip() == "":
            values["model_code"] = None
        return values

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelUpdateRequest(BaseModel):
    model_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    calc_mode: Optional[ProductCalcMode] = Field(None, description="产品模型计算模式：ratio/fixed/independent")
    fixed_price: Optional[Decimal] = Field(None, ge=0, description="一口价模式固定价格（元）")
    status: Optional[str] = Field(None, max_length=32)
    tags: Optional[List[str]] = None
    standard_width_mm: Optional[Decimal] = Field(None, ge=0)
    standard_height_mm: Optional[Decimal] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")
    modules: Optional[List[ModelProcessModuleInput]] = None

    @root_validator
    def _validate_calc_mode(cls, values):
        mode = values.get("calc_mode")
        fixed_price = values.get("fixed_price")
        if mode == "fixed" and fixed_price is None:
            raise ValueError("calc_mode=fixed 时必须提供 fixed_price")
        if mode is not None and mode != "fixed":
            values["fixed_price"] = None
        return values

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelRead(BaseModel):
    id: str
    model_code: str
    model_name: str
    description: Optional[str]
    category: Optional[str]
    calc_mode: str
    fixed_price: Optional[Decimal]
    standard_width_mm: Optional[Decimal]
    standard_height_mm: Optional[Decimal]
    unit_of_measure: Optional[str]
    status: str
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    modules: List[ModelProcessModuleRead] = Field(default_factory=list)
    # New: persisted model lines (editable at model layer)
    materials: List[ProductModelMaterialLineRead] = Field(default_factory=list)
    processes: List[ProductModelProcessLineRead] = Field(default_factory=list)
    # New: version stats for list pages
    sample_version_count: int = 0
    standard_version_count: int = 0
    current_published_standard_version_id: Optional[str] = None
    current_published_standard_version_label: Optional[str] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelVersionCreateRequest(BaseModel):
    version_kind: Literal["sample", "standard"] = Field(
        "sample", description="版本类型：sample=打样版本；standard=标准发布版本（1m×1m）"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class ProductModelVersionRead(BaseModel):
    id: str
    model_id: str
    version_kind: str
    version_status: str
    version_label: Optional[str] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelVersionListItem(BaseModel):
    # model master
    model_id: str
    model_code: str
    model_name: str
    model_status: str
    # version
    version_id: str
    version_kind: str
    version_status: str
    version_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None

    class Config:
        orm_mode = False
        json_encoders = {Decimal: _decimal_to_str}


class PaginatedProductModelVersionResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductModelVersionListItem]


class ProductModelVersionPublishRequest(BaseModel):
    published_by: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=255)


class SkuModelVersionMappingCreateRequest(BaseModel):
    sku_code: str = Field(..., max_length=64)
    model_version_id: str
    source_system: Optional[str] = Field(None, max_length=64)
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True


class SkuModelVersionMappingRead(SkuModelVersionMappingCreateRequest):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class PaginatedProductModelResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductModelRead]


class ProductModelPreviewRequest(BaseModel):
    width_mm: Decimal = Field(..., ge=0, description="产品宽度（mm）")
    height_mm: Decimal = Field(..., ge=0, description="产品高度（mm）")
    quantity: Decimal = Field(Decimal("1"), gt=0, description="数量（个）")
    sku_hint: Optional[str] = Field(None, max_length=128, description="用于 sku_contains 触发的 SKU/特征串（可选）")

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelPreviewMaterialLine(BaseModel):
    module_id: Optional[str] = None
    module_code: Optional[str] = None
    module_name: Optional[str] = None
    source_kind: Literal["real", "bom", "virtual", "placeholder"] = "real"
    source_ref_id: Optional[str] = None
    resolved_kind: Optional[Literal["real", "bom", "virtual"]] = None
    resolved_ref_id: Optional[str] = None
    material_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    category: Optional[str] = None
    calculation_method: CalculationMethod
    base_quantity: Decimal
    loss_rate: Decimal
    used_quantity: Decimal
    unit: Optional[str] = None
    bom_unit_price: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    warnings: List[str] = Field(default_factory=list)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelPreviewLaborLine(BaseModel):
    module_id: Optional[str] = None
    module_code: Optional[str] = None
    module_name: Optional[str] = None
    process_id: Optional[str] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    team_name: Optional[str] = None
    pricing_method: LaborPricingMethod
    measure_quantity: Decimal
    cost_type: Optional[Literal["time", "piece"]] = None
    base_minutes: Decimal = Decimal("0")
    unit_minutes: Decimal = Decimal("0")
    rate_per_minute: Optional[Decimal] = None
    piece_rate: Optional[Decimal] = None
    total_minutes: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    warnings: List[str] = Field(default_factory=list)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelPreviewResponse(BaseModel):
    width_mm: Decimal
    height_mm: Decimal
    quantity: Decimal
    material_lines: List[ProductModelPreviewMaterialLine] = Field(default_factory=list)
    labor_lines: List[ProductModelPreviewLaborLine] = Field(default_factory=list)
    totals: Dict[str, Decimal] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelSkuPreviewRequest(BaseModel):
    """
    Preview by SKU:
    - Parse model_code / version token / dimensions / variant tokens from sku_code
    - Resolve to an active SKU binding (preferred) or fallback to latest published standard version of model_code
    """

    sku_code: str = Field(..., max_length=128)
    # optional overrides (when SKU missing or ambiguous)
    width_mm: Optional[Decimal] = Field(None, ge=0)
    height_mm: Optional[Decimal] = Field(None, ge=0)
    quantity: Optional[Decimal] = Field(None, gt=0)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelSkuPreviewResponse(ProductModelPreviewResponse):
    sku_code: str
    model_id: str
    model_code: str
    version_id: str
    version_label: Optional[str] = None
    parsed: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


# -----------------------------
# Standard derivation templates
# -----------------------------

class DeriveRoundRule(BaseModel):
    """
    Rounding rule for derived quantities/minutes.
    step: e.g. 0.01 / 0.1 / 1
    mode: round/floor/ceil
    """

    step: Decimal = Field(Decimal("1"), gt=0)
    mode: Literal["round", "floor", "ceil"] = "round"

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class DeriveTemplateBase(BaseModel):
    template_kind: Literal["linear"] = Field("linear", description="当前仅支持 linear 模板（后续可扩展 piecewise 等）")
    calibrate_from_sample: bool = Field(
        False,
        description="是否用打样数据校准（当 coefficient/单位系数为空时，由 sample_used 或 sample_minutes 反推）",
    )
    fixed_quantity: Optional[Decimal] = Field(None, ge=0, description="固定用量/起步（未计损耗）")
    coverage_ratio: Optional[Decimal] = Field(None, ge=0, le=1, description="覆盖率（默认=1）")
    min_total: Optional[Decimal] = Field(None, ge=0, description="最小起步（作用于标准 1×1 的最终用量/分钟）")
    max_total: Optional[Decimal] = Field(None, ge=0, description="封顶（作用于标准 1×1 的最终用量/分钟）")
    rounding: Optional[DeriveRoundRule] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class DeriveTemplateMaterial(DeriveTemplateBase):
    coefficient: Optional[Decimal] = Field(None, ge=0, description="单位计量系数 β（用于 base_quantity）")


class DeriveTemplateProcess(DeriveTemplateBase):
    coefficient: Optional[Decimal] = Field(None, ge=0, description="单位计量分钟系数（用于 unit_minutes）")
    base_minutes: Optional[Decimal] = Field(None, ge=0, description="基础分钟（用于 base_minutes）")


class DeriveStandardRequest(BaseModel):
    target_mode: Literal["create_new", "overwrite_draft"] = "create_new"
    target_standard_version_id: Optional[str] = None
    apply_to: Literal["materials", "processes", "both"] = "both"


class DeriveStandardResponse(BaseModel):
    standard_version_id: str
    created: bool = True
    overwritten: bool = False
    line_stats: Dict[str, Any] = Field(default_factory=dict)


class ProductModelSampleSpec(BaseModel):
    width_mm: Decimal = Field(..., ge=0)
    height_mm: Decimal = Field(..., ge=0)
    quantity: Decimal = Field(Decimal("1"), gt=0)
    unit_label: str = Field("幅", max_length=16)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelMaterialLineInput(BaseModel):
    id: Optional[str] = None
    source_module_id: Optional[str] = None
    source_module_code: Optional[str] = None
    source_module_name: Optional[str] = None

    material_kind: MaterialReferenceKind = Field("real")
    material_ref_id: str
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    calculation_method: CalculationMethod = Field("count")
    # sample & standard are persisted in metadata_json for traceability
    sample_used_quantity: Optional[Decimal] = Field(None, ge=0, description="打样尺寸下的实际用量（未计损耗）")
    standard_used_quantity: Optional[Decimal] = Field(None, ge=0, description="标准尺寸下的实际用量（未计损耗）")
    fixed_quantity: Optional[Decimal] = Field(
        None,
        ge=0,
        description="固定用量α（起步损耗/边料等，独立于计量值；未计损耗）",
    )
    coverage_ratio: Optional[Decimal] = Field(
        None,
        ge=0,
        le=1,
        description="覆盖率/占比（0~1），用于局部材料：用量 = α + β×M×coverage_ratio；默认=1",
    )
    base_quantity: Optional[Decimal] = Field(None, ge=0, description="单位用量系数（用于比例缩放）")
    loss_rate: Decimal = Field(Decimal("0"), ge=0, le=100)
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelMaterialLineRead(ProductModelMaterialLineInput):
    id: str


class ProductModelProcessLineInput(BaseModel):
    id: Optional[str] = None
    source_module_id: Optional[str] = None
    source_module_code: Optional[str] = None
    source_module_name: Optional[str] = None

    process_id: str
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    team_name: Optional[str] = None
    pricing_method: LaborPricingMethod = Field("count")
    # sample & standard are persisted in metadata_json for traceability
    sample_minutes: Optional[Decimal] = Field(None, ge=0, description="打样尺寸下的实际用时（分钟）")
    standard_minutes: Optional[Decimal] = Field(None, ge=0, description="标准尺寸下的实际用时（分钟）")
    base_minutes: Decimal = Field(Decimal("0"), ge=0)
    unit_minutes: Decimal = Field(Decimal("0"), ge=0)
    rate_per_minute: Optional[Decimal] = Field(None, ge=0)
    piece_rate: Optional[Decimal] = Field(None, ge=0)
    cost_type: Optional[Literal["time", "piece"]] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelProcessLineRead(ProductModelProcessLineInput):
    id: str


class ProductModelLinesResponse(BaseModel):
    sample: ProductModelSampleSpec
    standard: ProductModelSampleSpec
    materials: List[ProductModelMaterialLineRead] = Field(default_factory=list)
    processes: List[ProductModelProcessLineRead] = Field(default_factory=list)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProductModelSyncFromModulesRequest(BaseModel):
    keep_overrides: bool = Field(True, description="同步时保留模型层已调整的参数")


class ProductModelLinesUpdateRequest(BaseModel):
    sample: ProductModelSampleSpec
    standard: ProductModelSampleSpec
    materials: List[ProductModelMaterialLineInput] = Field(default_factory=list)
    processes: List[ProductModelProcessLineInput] = Field(default_factory=list)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}



class ModelVariantRuleBase(BaseModel):
    rule_name: str = Field(..., max_length=255)
    source_material_ref_id: Optional[str] = Field(
        None, description="规则作用的源物料ID（必须是模型展开后能找到的物料ID，作为兜底基础）"
    )
    trigger_type: VariantTriggerType
    trigger_value: Optional[str] = Field(None, max_length=255, description="触发值：sku_contains 用字符串；area/perimeter 用数值字符串")
    action_type: VariantActionType
    target_material_ref_id: Optional[str] = Field(None, description="目标物料ID（replace/add）")
    quantity_delta: Optional[Decimal] = Field(None, ge=0, description="add_material 时额外用量（按模块行同口径折算）")
    status: str = Field("active", max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    @root_validator
    def _validate_rule(cls, values):
        action = values.get("action_type")
        source_id = values.get("source_material_ref_id")
        target_id = values.get("target_material_ref_id")
        trig = values.get("trigger_type")
        trig_value = values.get("trigger_value")
        qty_delta = values.get("quantity_delta")

        if not source_id:
            raise ValueError("source_material_ref_id 必填（用于兜底：未命中规则时回落源物料）")

        if action in ("replace_material", "add_material") and not target_id:
            raise ValueError("target_material_ref_id 必填")

        if action == "add_material" and (qty_delta is None or Decimal(str(qty_delta)) <= 0):
            raise ValueError("add_material 必须提供 quantity_delta > 0")

        if trig == "sku_contains":
            if not trig_value or not str(trig_value).strip():
                raise ValueError("sku_contains 需要 trigger_value（字符串）")
        else:
            # area_gte / perimeter_gte
            if trig_value in (None, ""):
                raise ValueError(f"{trig} 需要 trigger_value（数值）")
            try:
                if Decimal(str(trig_value)) <= 0:
                    raise ValueError
            except Exception:  # noqa: BLE001
                raise ValueError(f"{trig} 的 trigger_value 必须是 >0 的数值字符串")

        if target_id and source_id and str(target_id) == str(source_id) and action == "replace_material":
            raise ValueError("replace_material 不允许目标物料与源物料相同")

        return values

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ModelVariantRuleCreateRequest(ModelVariantRuleBase):
    pass


class ModelVariantRuleUpdateRequest(BaseModel):
    rule_name: Optional[str] = Field(None, max_length=255)
    trigger_type: Optional[VariantTriggerType] = None
    trigger_value: Optional[str] = Field(None, max_length=255)
    action_type: Optional[VariantActionType] = None
    target_material_ref_id: Optional[str] = None
    quantity_delta: Optional[Decimal] = Field(None, ge=0)
    status: Optional[str] = Field(None, max_length=32)
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ModelVariantRuleRead(ModelVariantRuleBase):
    id: str
    model_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessModuleStepRead(ProcessModuleStepInput):
    id: str
    process: Optional[ProcessReferenceRead] = None


class ProcessModuleCreateRequest(BaseModel):
    module_code: str = Field(..., max_length=64)
    module_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    status: Optional[str] = Field("draft", max_length=32)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    materials: List[ProcessModuleMaterialInput] = Field(default_factory=list)
    steps: List[ProcessModuleStepInput] = Field(default_factory=list)
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        allow_population_by_field_name = True


class ProcessModuleUpdateRequest(BaseModel):
    module_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    status: Optional[str] = Field(None, max_length=32)
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")
    materials: Optional[List[ProcessModuleMaterialInput]] = None
    steps: Optional[List[ProcessModuleStepInput]] = None
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        allow_population_by_field_name = True


class ProcessModuleCopyRequest(BaseModel):
    module_code: str = Field(..., max_length=64)
    module_name: str = Field(..., max_length=255)
    status: Optional[str] = Field(None, max_length=32)
    operator_id: Optional[str] = Field("system", max_length=64)


class ProcessModuleSummaryRead(BaseModel):
    id: str
    module_code: str
    module_name: str
    description: Optional[str]
    category: Optional[str]
    status: str
    version: int
    tags: List[str]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class ProcessModuleDetailRead(ProcessModuleSummaryRead):
    materials: List[ProcessModuleMaterialRead] = Field(default_factory=list)
    steps: List[ProcessModuleStepRead] = Field(default_factory=list)


class PaginatedProcessModuleResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProcessModuleSummaryRead]


class ProcessModuleReferenceResponse(BaseModel):
    total: int
    items: List[ProcessModuleDetailRead]


class ProcessCreateRequest(BaseModel):
    process_code: str = Field(..., max_length=64)
    process_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    team_name: Optional[str] = Field(None, max_length=128)
    charging_mode: ProcessChargingMode = Field("count")
    standard_rate: Optional[Decimal] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    status: Optional[str] = Field("draft", max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessUpdateRequest(BaseModel):
    process_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=128)
    team_name: Optional[str] = Field(None, max_length=128)
    charging_mode: Optional[ProcessChargingMode] = None
    standard_rate: Optional[Decimal] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    status: Optional[str] = Field(None, max_length=32)
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessCopyRequest(BaseModel):
    process_code: str = Field(..., max_length=64)
    process_name: str = Field(..., max_length=255)
    status: Optional[str] = Field(None, max_length=32)
    operator_id: Optional[str] = Field("system", max_length=64)


class ProcessBatchStatusRequest(BaseModel):
    ids: List[str] = Field(default_factory=list)
    status: str = Field(..., max_length=32)
    operator_id: Optional[str] = Field("system", max_length=64)


class ProcessBatchStatusResponse(BaseModel):
    updated: int


class ProcessSummaryRead(BaseModel):
    id: str
    process_code: str
    process_name: str
    description: Optional[str]
    category: Optional[str]
    team_name: Optional[str]
    charging_mode: ProcessChargingMode
    standard_rate: Optional[Decimal]
    unit_of_measure: Optional[str]
    status: str
    is_active: bool
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessDetailRead(ProcessSummaryRead):
    pass


class PaginatedProcessResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProcessSummaryRead]


class CodeGenerateRequest(BaseModel):
    prefix: str = Field(..., max_length=16)
    width: int = Field(5, ge=1, le=16)


class CodeGenerateResponse(BaseModel):
    code: str


class RandomCodeGenerateRequest(BaseModel):
    kind: Literal["product_model"] = Field("product_model", description="编码类型")
    length: int = Field(3, ge=2, le=12, description="编码长度")


class RandomCodeGenerateResponse(BaseModel):
    code: str


# Resolve ForwardRefs for models that reference types defined later in this module.
ProductModelRead.update_forward_refs()


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


class SpecTokenExplanation(BaseModel):
    token: str
    source: str
    rule: str


class SpecParseRequest(BaseModel):
    spec_text: str
    sku_code: Optional[str] = None


class SpecParseResponse(BaseModel):
    tokens: List[str] = Field(default_factory=list)
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    diameter_cm: Optional[Decimal] = None
    area_m2: Optional[Decimal] = None
    perimeter_m: Optional[Decimal] = None
    explanations: List[SpecTokenExplanation] = Field(default_factory=list)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class LineVariantCondition(BaseModel):
    spec_contains_any: Optional[List[str]] = None
    spec_contains_all: Optional[List[str]] = None
    width_between: Optional[Tuple[Optional[Decimal], Optional[Decimal]]] = None
    height_between: Optional[Tuple[Optional[Decimal], Optional[Decimal]]] = None
    area_between: Optional[Tuple[Optional[Decimal], Optional[Decimal]]] = None
    perimeter_between: Optional[Tuple[Optional[Decimal], Optional[Decimal]]] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class LineVariantItemPayload(BaseModel):
    sequence_order: Optional[int] = Field(None, ge=0)
    material_kind: MaterialReferenceKind = Field("real")
    material_ref_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    unit_of_measure: Optional[str] = None
    calculation_method: CalculationMethod = Field("count")
    base_quantity: Decimal = Field(Decimal("0"), ge=0)
    fixed_quantity: Decimal = Field(Decimal("0"), ge=0)
    coverage_ratio: Decimal = Field(Decimal("1"), ge=0)
    loss_rate: Decimal = Field(Decimal("0"), ge=0, le=100)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class LineVariantItemRead(LineVariantItemPayload):
    id: str
    sequence_order: int
    created_at: datetime
    updated_at: datetime


class LineVariantCreateRequest(BaseModel):
    version_id: str
    base_line_id: str
    priority: int = Field(100, ge=0)
    enabled: bool = True
    action: LineVariantAction = Field("replace_bundle")
    stop_on_hit: bool = True
    notes: Optional[str] = None
    conditions: LineVariantCondition = Field(default_factory=LineVariantCondition)
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    items: List[LineVariantItemPayload] = Field(default_factory=list)
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        allow_population_by_field_name = True


class LineVariantUpdateRequest(BaseModel):
    base_line_id: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0)
    enabled: Optional[bool] = None
    action: Optional[LineVariantAction] = None
    stop_on_hit: Optional[bool] = None
    notes: Optional[str] = None
    conditions: Optional[LineVariantCondition] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="metadata_json")
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        allow_population_by_field_name = True


class LineVariantItemsReplaceRequest(BaseModel):
    items: List[LineVariantItemPayload] = Field(default_factory=list)


class LineVariantDetailRead(BaseModel):
    id: str
    version_id: str
    base_line_id: str
    priority: int
    enabled: bool
    action: LineVariantAction
    stop_on_hit: bool
    notes: Optional[str] = None
    conditions: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    items: List[LineVariantItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BomLineRead(BaseModel):
    line_index: int
    source_type: Literal["base_line", "variant_item"]
    base_line_id: Optional[str]
    variant_id: Optional[str]
    variant_item_id: Optional[str]
    material_kind: str
    material_ref_id: Optional[str]
    material_code: Optional[str]
    material_name: Optional[str]
    unit_of_measure: Optional[str]
    calculation_method: CalculationMethod
    base_quantity: Decimal
    fixed_quantity: Decimal
    coverage_ratio: Decimal
    loss_rate: Decimal
    computed_quantity: Decimal
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BomGenerateRequest(BaseModel):
    spec_text: str
    model_version_id: Optional[str] = None
    sku_code: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    operator_id: Optional[str] = Field("system", max_length=64)

    @root_validator
    def _ensure_scope(cls, values):
        if not values.get("model_version_id") and not values.get("sku_code"):
            raise ValueError("model_version_id 或 sku_code 至少提供一个")
        return values

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BomGenerateResponse(BaseModel):
    final_material_lines: List[BomLineRead] = Field(default_factory=list)
    trace: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ShipmentImportBatchRead(BaseModel):
    id: str
    file_name: Optional[str] = None
    file_hash: str
    export_date: Optional[str] = None
    requested_by: Optional[str] = None
    status: str
    total_rows: int
    inserted_rows: int
    skipped_rows: int
    exception_rows: int
    warnings: List[Dict[str, Any]] = Field(default_factory=list, alias="warnings_json")
    result: Dict[str, Any] = Field(default_factory=dict, alias="result_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class PaginatedShipmentImportBatchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ShipmentImportBatchRead]


class ShipmentExceptionRead(BaseModel):
    id: str
    batch_id: str
    shipment_line_id: Optional[str] = None
    # fields mirrored from shipment_lines for readability (Excel-like columns)
    row_index: Optional[int] = None
    shipment_no: Optional[str] = None
    completed_at: Optional[datetime] = None
    channel: Optional[str] = None
    sku_code: Optional[str] = None
    spec_text: Optional[str] = None
    spec_hash: Optional[str] = None
    qty: Optional[Decimal] = None
    revenue_amount: Optional[Decimal] = None
    reason: str
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict, alias="payload_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class BomSnapshotRead(BaseModel):
    id: str
    batch_id: str
    shipment_line_id: str
    shipment_no: Optional[str] = None
    sku_code: Optional[str] = None
    model_version_id: Optional[str] = None
    spec_hash: Optional[str] = None
    qty: Optional[Decimal] = None
    final_material_lines: List[Dict[str, Any]] = Field(default_factory=list)
    trace: Dict[str, Any] = Field(default_factory=dict)
    generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class SkuMasterRead(BaseModel):
    id: str
    erp_sku_barcode: str
    platform_product_id: Optional[str] = None
    platform_sku_id: Optional[str] = None
    channel: Optional[str] = None
    product_name: Optional[str] = None
    product_code: Optional[str] = None
    spec_text: Optional[str] = None
    images: Dict[str, Any] = Field(default_factory=dict, alias="images_json")
    match_status: Optional[str] = None
    # Costing integration summary (computed fields; avoid N+1 on frontend)
    active_version_binding_id: Optional[str] = None
    active_model_version_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    bound_version_label: Optional[str] = None
    bound_version_kind: Optional[str] = None
    bound_version_status: Optional[str] = None
    # Parsed spec cache & hints (computed fields; stored in metadata_json)
    model_code_hint: Optional[str] = None
    erp_spec_hash: Optional[str] = None
    erp_parser_version: Optional[str] = None
    erp_dimensions: Dict[str, Any] = Field(default_factory=dict)
    erp_tokens: List[str] = Field(default_factory=list)
    last_shipment_spec_text: Optional[str] = None
    last_shipment_spec_hash: Optional[str] = None
    spec_mismatch: bool = False
    spec_mismatch_at: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class PaginatedSkuMasterResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[SkuMasterRead]


class SkuMasterImportResponse(BaseModel):
    total: int
    inserted: int
    updated: int
    skipped: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class PublishedStandardModelCandidate(BaseModel):
    model_id: str
    model_code: str
    model_name: str
    published_version_id: str
    version_label: Optional[str] = None


class PublishedStandardModelCandidateListResponse(BaseModel):
    items: List[PublishedStandardModelCandidate] = Field(default_factory=list)


class SkuMasterBindByModelRequest(BaseModel):
    model_id: str
    sku_master_ids: List[str] = Field(default_factory=list)
    requested_by: Optional[str] = None


class SkuMasterBindByModelResponse(BaseModel):
    total_selected: int
    bound_count: int
    skipped_already_bound: int
    skipped_missing_barcode: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class SkuMasterAutoBindPreviewRequest(BaseModel):
    limit: int = Field(200, ge=1, le=2000)


class SkuMasterAutoBindPreviewItem(BaseModel):
    sku_master_id: str
    erp_sku_barcode: str
    channel: Optional[str] = None
    spec_text: Optional[str] = None
    model_code_hint: str
    model_id: str
    model_code: str
    model_name: str
    published_version_id: str
    version_label: Optional[str] = None
    match_method: Optional[str] = None
    matched_keyword: Optional[str] = None


class SkuMasterAutoBindPreviewResponse(BaseModel):
    total_unbound: int
    candidates: int
    items: List[SkuMasterAutoBindPreviewItem] = Field(default_factory=list)


class SkuMasterAutoBindExecuteRequest(BaseModel):
    limit: int = Field(200, ge=1, le=2000)
    sku_master_ids: List[str] = Field(default_factory=list)
    requested_by: Optional[str] = None


class SkuMasterAutoBindExecuteResponse(BaseModel):
    preview: SkuMasterAutoBindPreviewResponse
    bound_count: int
    skipped_already_bound: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class RecognitionKeywordsValidateRequest(BaseModel):
    keywords: List[str] = Field(default_factory=list)


class RecognitionKeywordsValidateResponse(BaseModel):
    ok: bool
    normalized_keywords: List[str] = Field(default_factory=list)
    conflicts: Dict[str, str] = Field(default_factory=dict)
