from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field, root_validator, validator
from src.config import settings

CalculationMethod = Literal[
    "area",
    "perimeter",
    "count",
    "width",
    "height",
    "long_side",
    "short_side",
]
ProcessChargingMode = Literal[
    "fixed",
    "count",
    "area",
    "perimeter",
    "width",
    "height",
    "long_side",
    "short_side",
]
LaborPricingMethod = Literal[
    "fixed",
    "count",
    "area",
    "perimeter",
    "width",
    "height",
    "long_side",
    "short_side",
]
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


class TaskCenterItemRead(BaseModel):
    id: str
    # planner: planner_import_jobs; material: material_sync_jobs
    source: str
    job_type: str
    status: str
    requested_by: str
    title: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class TaskCenterListResponse(BaseModel):
    items: List[TaskCenterItemRead] = Field(default_factory=list)


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
        # Sources priority:
        # 1) metadata["images"] (canonical normalized list we maintain)
        # 2) YiDa raw_form_data image fields (field ids often look like "imageField_xxx")
        # 3) legacy hard-coded field id fallback (kept for backward compatibility)

        def _normalize_one(value: Any) -> list[str]:
            if value in (None, "", []):
                return []

            data: list[Any]
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return []
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    # could be ossFileHandle or a direct url
                    return [s]
                data = parsed if isinstance(parsed, list) else [parsed]
            elif isinstance(value, list):
                data = value
            else:
                data = [value]

            out: list[str] = []
            for item in data:
                if isinstance(item, str):
                    s = item.strip()
                    if s:
                        out.append(s)
                    continue
                if isinstance(item, dict):
                    # Some YiDa controls wrap the actual file list inside nested keys.
                    for nested_key in ("value", "fileList", "files", "list", "items"):
                        if nested_key in item and item.get(nested_key) not in (None, "", []):
                            out.extend(_normalize_one(item.get(nested_key)))

                    # YiDa attachment objects may contain:
                    # - ossFileHandle / fileUrl (for DingTalk temporary url API)
                    # - downloadUrl / url / previewUrl (sometimes present)
                    url = (
                        item.get("ossFileHandle")
                        or item.get("fileUrl")
                        or item.get("file_id")
                        or item.get("fileId")
                        or item.get("mediaId")
                        or item.get("media_id")
                        or item.get("filePath")
                        or item.get("path")
                        or item.get("downloadUrl")
                        or item.get("url")
                        or item.get("previewUrl")
                    )
                    if isinstance(url, str) and url.strip():
                        out.append(url.strip())

            return out

        # Prefer raw_form_data when present (it reflects the latest YiDa form state).
        raw_form = metadata.get("raw_form_data") or {}
        raw_sources: list[str] = []
        if isinstance(raw_form, dict):
            for k, v in raw_form.items():
                key = str(k)
                # YiDa image control field ids typically start with imageField_.
                if not (key.startswith("imageField_") or key.startswith("attachmentField_")):
                    continue
                raw_sources.extend(_normalize_one(v))

        # legacy fallback (historical field id used in docs)
        legacy = metadata.get("imageField_lbef2r0b") or (
            raw_form.get("imageField_lbef2r0b") if isinstance(raw_form, dict) else None
        )
        raw_sources.extend(_normalize_one(legacy))

        meta_sources = _normalize_one(metadata.get("images"))

        # If raw has any images, use it as authoritative; otherwise fallback to metadata.images.
        merged = raw_sources if raw_sources else meta_sources

        def _dedup_key(s: str) -> str:
            raw = (s or "").strip()
            if not raw:
                return ""
            # Normalize query params for both http(s) urls and /ossFileHandle?... handles.
            # Remove volatile params so the same file won't appear duplicated with different signatures.
            volatile = {
                "token",
                "access_token",
                "signature",
                "sign",
                "expires",
                "expire",
                "timestamp",
                "ts",
            }
            try:
                # For non-http handles, prepend a dummy host to leverage urlparse.
                p = urlparse(raw if raw.startswith("http") else f"http://x{raw}")
                q = [(k, v) for (k, v) in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in volatile]
                q.sort(key=lambda kv: kv[0])
                p2 = p._replace(query=urlencode(q, doseq=True))
                rebuilt = urlunparse(p2)
                return rebuilt.replace("http://x", "") if not raw.startswith("http") else rebuilt
            except Exception:
                return raw

        # de-dup preserve order (by normalized key)
        seen: set[str] = set()
        out: list[str] = []
        for x in merged:
            k = _dedup_key(x)
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

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


class ShippingRuleRead(BaseModel):
    id: str
    rule_name: str
    priority: int
    is_active: bool
    conditions: Dict[str, Any] = Field(alias="conditions_json")
    outputs: List[Dict[str, Any]] = Field(default_factory=list, alias="outputs_json")
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class ShippingRuleUpsertRequest(BaseModel):
    rule_name: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    conditions: Optional[Dict[str, Any]] = None
    outputs: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PaginatedShippingRuleResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ShippingRuleRead]


class ShippingRuleEvaluateRequest(BaseModel):
    shop_code: Optional[str] = None
    channel: Optional[str] = None
    shipping_method: Optional[str] = None
    is_merge: Optional[bool] = None
    province: Optional[str] = None
    city: Optional[str] = None
    weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None
    package_count: Optional[int] = None
    tokens: List[str] = Field(default_factory=list)
    include_disabled_rules: bool = False


class ShippingRuleEvaluateResponse(BaseModel):
    matched_rules: List[Dict[str, Any]] = Field(default_factory=list)
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# -----------------------------
# Taxonomy (admin-maintained dictionaries)
# -----------------------------


class TaxonomyScopeOptionsResponse(BaseModel):
    universal_scope: str
    default_scopes: List[str]


class TaxonomyItemRead(BaseModel):
    id: str
    domain: str
    name: str
    scopes: List[str] = Field(alias="scopes_json")
    is_active: bool
    sort_order: int
    source: str
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class TaxonomyItemListResponse(BaseModel):
    items: List[TaxonomyItemRead]


class TaxonomyMappingRead(BaseModel):
    id: str
    domain: str
    external_system: str
    external_value: str
    taxonomy_item_id: str
    taxonomy_item_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @root_validator(pre=True)
    def _fill_item_name(cls, values):
        if not isinstance(values, dict):
            values = dict(values)
        item = values.get("item")
        if item and not values.get("taxonomy_item_name"):
            try:
                values["taxonomy_item_name"] = getattr(item, "name", None)
            except Exception:
                pass
        return values

    class Config:
        orm_mode = True


class TaxonomyMappingListResponse(BaseModel):
    items: List[TaxonomyMappingRead]
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


class MaterialReferenceVirtualMaterialItem(BaseModel):
    id: str
    virtual_code: str
    name: str
    virtual_kind: Optional[str] = None
    status: Optional[str] = None


class MaterialReferenceProcessModuleItem(BaseModel):
    id: str
    name: str


class MaterialReferenceProductModelVersionItem(BaseModel):
    version_id: str
    model_id: str
    model_name: Optional[str] = None
    version_label: Optional[str] = None
    version_kind: Optional[str] = None
    version_status: Optional[str] = None


class MaterialReferenceVirtualMaterialsBlock(BaseModel):
    count: int = 0
    items: List[MaterialReferenceVirtualMaterialItem] = Field(default_factory=list)


class MaterialReferenceProcessModulesBlock(BaseModel):
    count: int = 0
    items: List[MaterialReferenceProcessModuleItem] = Field(default_factory=list)


class MaterialReferenceProductModelVersionsBlock(BaseModel):
    count: int = 0
    items: List[MaterialReferenceProductModelVersionItem] = Field(default_factory=list)


class MaterialReferencesResponse(BaseModel):
    material_id: str
    virtual_materials: MaterialReferenceVirtualMaterialsBlock = Field(default_factory=MaterialReferenceVirtualMaterialsBlock)
    process_modules: MaterialReferenceProcessModulesBlock = Field(default_factory=MaterialReferenceProcessModulesBlock)
    product_model_versions: MaterialReferenceProductModelVersionsBlock = Field(
        default_factory=MaterialReferenceProductModelVersionsBlock
    )
    errors: List[str] = Field(default_factory=list)


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
    # New: list performance - provide latest sample version id (for list thumbnails) to avoid frontend N+1
    latest_sample_version_id: Optional[str] = None

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


class ProductModelVersionPatchRequest(BaseModel):
    """
    MVP: partial update for version-level metadata_json.
    IMPORTANT: server should MERGE metadata_json (not overwrite entire object).
    """

    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    operator_id: Optional[str] = Field(None, max_length=64)

    class Config:
        allow_population_by_field_name = True


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


class CloneModelFromVersionRequest(BaseModel):
    """
    Clone a *new* product model from an existing model version (typically a standard version).
    Creates a new ProductModel (auto model_code if empty) and a new draft standard version,
    and copies version lines (and optionally line-variants).
    """

    model_name: Optional[str] = Field(None, max_length=255, description="新模型名称；为空则使用“源模型名（克隆）”")
    include_line_variants: bool = Field(True, description="是否复制行级变体（overlay）")
    operator_id: Optional[str] = Field(None, max_length=64)


class CloneModelFromVersionResponse(BaseModel):
    new_model_id: str
    new_model_code: str
    new_model_name: str
    new_standard_version_id: str
    new_standard_version_label: Optional[str] = None


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
    module_ids: Optional[List[str]] = Field(
        None,
        description="可选：仅同步指定模块ID（用于增量添加/勾选同步），不传则同步全部模块",
    )


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
    # allow backend allocate code on save (avoid wasting codes on "open drawer")
    process_code: Optional[str] = Field(None, max_length=64)
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


class ProcessFeedbackCreateRequest(BaseModel):
    process_id: str = Field(..., max_length=36)
    source_type: Optional[str] = Field(None, max_length=32)
    source_id: Optional[str] = Field(None, max_length=64)
    product_line_tag: Optional[str] = Field(None, max_length=64)
    team_name: Optional[str] = Field(None, max_length=128)
    quantity: Optional[Decimal] = None
    unit_of_measure: Optional[str] = Field(None, max_length=32)
    actual_minutes: Optional[Decimal] = None
    actual_cost: Optional[Decimal] = None
    quality_score: Optional[Decimal] = None
    is_success: Optional[bool] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessFeedbackRead(BaseModel):
    id: str
    process_id: str
    source_type: Optional[str]
    source_id: Optional[str]
    product_line_tag: Optional[str]
    team_name: Optional[str]
    quantity: Optional[Decimal]
    unit_of_measure: Optional[str]
    actual_minutes: Optional[Decimal]
    actual_cost: Optional[Decimal]
    quality_score: Optional[Decimal]
    is_success: Optional[bool]
    notes: Optional[str]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ProcessFeedbackListResponse(BaseModel):
    total: int
    items: List[ProcessFeedbackRead]


class AiProcessCorpusItem(BaseModel):
    id: str
    process_code: str
    process_name: str
    description: Optional[str]
    category: Optional[str]
    charging_mode: ProcessChargingMode
    unit_of_measure: Optional[str]
    status: str
    tags: List[str] = Field(default_factory=list)
    ai_spec: Dict[str, Any] = Field(default_factory=dict)


class AiProcessCorpusResponse(BaseModel):
    total: int
    items: List[AiProcessCorpusItem]


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
    diameter_between: Optional[Tuple[Optional[Decimal], Optional[Decimal]]] = None
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
    bom_unit_price: Optional[Decimal] = None
    line_cost: Optional[Decimal] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BomGenerateRequest(BaseModel):
    spec_text: str
    model_version_id: Optional[str] = None
    sku_code: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    operator_id: Optional[str] = Field("system", max_length=64)
    # Preview helper: if true, treat disabled variants as enabled (simulation only).
    include_disabled_variants: bool = False

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


# -----------------------------
# Bundle / Set (组合装/套装) BOM
# -----------------------------


class BomBundleComponent(BaseModel):
    """
    One component inside a bundle/set.

    IMPORTANT:
    - width/height/quantity are explicit inputs (do NOT parse from spec_text).
    - tokens/spec_text are optional and only used for variant matching.
    """

    width_mm: Decimal = Field(..., gt=0, description="组件宽度（mm）")
    height_mm: Decimal = Field(..., gt=0, description="组件高度（mm）")
    quantity: Decimal = Field(Decimal("1"), gt=0, description="组件数量（个）")
    # optional matching hints (NOT used to derive dimensions)
    spec_text: Optional[str] = Field(None, max_length=512, description="组件特征串（仅用于命中变体，可空）")
    tokens: List[str] = Field(default_factory=list, description="额外 tokens（仅用于命中变体，可空）")
    notes: Optional[str] = Field(None, max_length=255)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BomGenerateBundleRequest(BaseModel):
    model_version_id: str = Field(..., max_length=36)
    sku_code: Optional[str] = Field(None, max_length=128)
    components: List[BomBundleComponent] = Field(default_factory=list, min_items=1)
    include_disabled_variants: bool = False
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BomGenerateBundleResponse(BaseModel):
    """
    Response structure:
    - merged: same shape as BomGenerateResponse (final_material_lines + trace{costing,inventory,...})
    - components: per-component BomGenerateResponse-like dicts for debugging.
    """

    merged: Dict[str, Any] = Field(default_factory=dict)
    components: List[Dict[str, Any]] = Field(default_factory=list)


class BomGenerateMultiBundleComponent(BomBundleComponent):
    model_version_id: str = Field(..., max_length=36, description="该组件使用的标准版本ID（允许与其它组件不同）")


class BomGenerateMultiBundleRequest(BaseModel):
    sku_code: Optional[str] = Field(None, max_length=128)
    components: List[BomGenerateMultiBundleComponent] = Field(default_factory=list, min_items=1)
    include_disabled_variants: bool = False
    operator_id: Optional[str] = Field("system", max_length=64)


class BomGenerateMultiBundleResponse(BaseModel):
    merged: Dict[str, Any] = Field(default_factory=dict)
    components: List[Dict[str, Any]] = Field(default_factory=list)


class BundleTemplateComponent(BaseModel):
    model_version_id: str = Field(..., max_length=36)
    width_mm: Decimal = Field(..., ge=0)
    height_mm: Decimal = Field(..., ge=0)
    quantity: Decimal = Field(Decimal("1"), gt=0)
    spec_text: Optional[str] = Field(None, max_length=512, description="组件附加触发词（可选，仅用于补充变体触发；不要写尺寸）")
    label: Optional[str] = Field(None, max_length=128)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BundleTemplateCreateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    # Allow empty: new workflow stores per-preset component rows under metadata.phrase_presets[*].components.
    components: List[BundleTemplateComponent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    shared_trigger_text: Optional[str] = Field(
        None, max_length=512, description="公共触发词（作用于该套装所有组件；不要写尺寸）"
    )

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BundleTemplateRead(BaseModel):
    id: str
    code: str
    name: Optional[str] = None
    components: List[BundleTemplateComponent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    shared_trigger_text: Optional[str] = None
    # Published pointer (best-effort, stored in metadata; used for UI hints)
    published_version_id: Optional[str] = None
    published_version_label: Optional[str] = None
    published_at: Optional[str] = None
    is_archived: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BundleTemplateVersionRead(BaseModel):
    id: str
    template_id: str
    template_code: str
    template_name: Optional[str] = None
    version_status: str = "published"
    version_label: Optional[str] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    components: List[BundleTemplateComponent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_archived: bool = False
    created_at: Optional[datetime] = None


class BundleTemplatePublishRequest(BaseModel):
    operator_id: Optional[str] = Field("system", max_length=64)
    note: Optional[str] = Field(None, max_length=256)


class BundleTemplatePublishResponse(BaseModel):
    version: BundleTemplateVersionRead


class BundleTemplateVersionsResponse(BaseModel):
    total: int
    items: List[BundleTemplateVersionRead] = Field(default_factory=list)


class BundleTemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    components: Optional[List[BundleTemplateComponent]] = None
    metadata: Optional[Dict[str, Any]] = None
    shared_trigger_text: Optional[str] = Field(
        None, max_length=512, description="公共触发词（作用于该套装所有组件；不要写尺寸）"
    )
    operator_id: Optional[str] = Field("system", max_length=64)

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class BundleTemplateCloneRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    operator_id: Optional[str] = Field("system", max_length=64)


class PaginatedBundleTemplateResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[BundleTemplateRead]


class BomGenerateBySpecRequest(BaseModel):
    spec_text: str = Field(..., min_length=1, max_length=512)
    sku_code: Optional[str] = Field(None, max_length=128)
    include_disabled_variants: bool = False



class ModelVersionImageRead(BaseModel):
    index: int
    url: str
    filename: Optional[str] = None
    content_type: Optional[str] = None


class ModelVersionImagesResponse(BaseModel):
    version_id: str
    images: List[ModelVersionImageRead] = Field(default_factory=list)


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


class ShipmentLineListItem(BaseModel):
    id: str
    batch_id: str
    row_index: Optional[int] = None
    shipment_no: Optional[str] = None
    order_no: Optional[str] = None
    product_link_id: Optional[str] = None
    completed_at: Optional[datetime] = None
    channel: Optional[str] = None
    sku_code: Optional[str] = None
    # 商家编码 / 网店规格编码（若渠道/导出表提供）
    shop_spec_code: Optional[str] = None
    # 平台规格Id（网店）（若导出表提供）
    platform_sku_id: Optional[str] = None
    # 套装锚点（Phase0：来自 sku-master 绑定并贯穿到发货行）
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    # 绑定目标（当前生效绑定；BundleAsModel 也会以 model_code="B-XXXXYY" 的形式体现）
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    # 二级：标准版本 / 套装版本（用于筛选与抽屉展示）
    bound_version_label: Optional[str] = None
    spec_text: Optional[str] = None
    spec_hash: Optional[str] = None
    qty: Optional[Decimal] = None
    revenue_amount: Optional[Decimal] = None
    # 成本金额（优先读 shipment_costing_results.cost_total；为台账/毛利展示）
    cost_total: Optional[Decimal] = None
    # 绑定/快照版本（用于“待生成/需重建”工作流）
    bound_model_version_id: Optional[str] = None
    snapshot_model_version_id: Optional[str] = None
    needs_rebuild_snapshot: bool = False
    # latest snapshot id (if any) for bulk recompute
    bom_snapshot_id: Optional[str] = None

    # processing status (2025/2026 unified)
    status: Literal["processed", "pending"]
    processed_source: Optional[Literal["bom_snapshot", "costing_result"]] = None
    mode: Optional[Literal["2025", "2026"]] = None
    unresolved_reason: Optional[str] = None
    unresolved_message: Optional[str] = None
    # Soft guardrail (heuristic): spec keywords seem mismatched with bound target category
    suspected_mismatch: bool = False
    mismatch_warnings: List[str] = Field(default_factory=list)
    # Soft guardrail: size/area mismatch between parsed spec and snapshot measurement.
    suspected_size_anomaly: bool = False
    size_anomaly_detail: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class PaginatedShipmentLineResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ShipmentLineListItem]


class ShipmentLineComputeSnapshotRequest(BaseModel):
    operator_id: Optional[str] = None
    overwrite: bool = False  # True = 覆盖重算（高风险）


class ShipmentLineComputeSnapshotResponse(BaseModel):
    action: Literal["skipped", "created", "recomputed", "failed"]
    shipment_line_id: str
    bom_snapshot_id: Optional[str] = None
    detail: Optional[str] = None


class ShipmentLineClearSnapshotsRequest(BaseModel):
    shipment_line_ids: List[str] = Field(default_factory=list)
    operator_id: Optional[str] = None
    reason: Optional[str] = None


class ShipmentLineClearSnapshotsResponse(BaseModel):
    total_selected: int
    cleared_count: int
    skipped_not_found: int
    skipped_already_cleared: int
    skipped_missing_barcode: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class ShipmentImportPreviewIssue(BaseModel):
    row_index: Optional[int] = None
    shipment_no: Optional[str] = None
    sku_code: Optional[str] = None
    spec_text: Optional[str] = None
    reason: str


class ShipmentImportPreviewReadyItem(BaseModel):
    row_index: Optional[int] = None
    shipment_no: Optional[str] = None
    sku_code: Optional[str] = None
    spec_text: Optional[str] = None
    qty: Optional[Decimal] = None
    model_version_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    bound_version_label: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ShipmentImportPreviewResponse(BaseModel):
    preview_id: str  # file_hash
    file_name: str
    export_date: Optional[str] = None
    total_rows: int
    ready_rows: int
    missing_sku_rows: int
    missing_spec_rows: int
    unbound_sku_rows: int
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    issues: List[ShipmentImportPreviewIssue] = Field(default_factory=list)
    ready_items: List[ShipmentImportPreviewReadyItem] = Field(default_factory=list)


class ShipmentImportExecuteRequest(BaseModel):
    preview_id: str
    file_name: Optional[str] = None
    export_date: Optional[str] = None
    requested_by: Optional[str] = None
    mode: Literal["2025", "2026"] = "2026"


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
    # Current binding & parse cache hints (for “一目了然”的待处理列表)
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    spec_parsed: Optional[bool] = None
    spec_width_cm: Optional[Decimal] = None
    spec_height_cm: Optional[Decimal] = None
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


class ShipmentExceptionRetryRequest(BaseModel):
    batch_id: str = Field(..., min_length=1, max_length=64)
    only_unresolved: bool = True
    limit: Optional[int] = None
    operator_id: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=128)


class ShipmentExceptionRetryResultItem(BaseModel):
    exception_id: str
    shipment_line_id: Optional[str] = None
    status: Literal["resolved", "unresolved"]
    new_bom_snapshot_id: Optional[str] = None
    error: Optional[str] = None


class ShipmentExceptionRetryResponse(BaseModel):
    batch_id: str
    only_unresolved: bool
    limit: Optional[int] = None
    processed: int
    resolved: int
    unresolved: int
    items: List[ShipmentExceptionRetryResultItem] = Field(default_factory=list)


class BomSnapshotRead(BaseModel):
    id: str
    batch_id: str
    shipment_line_id: str
    # fields mirrored from shipment_lines for readability (Excel-like columns)
    row_index: Optional[int] = None
    shipment_no: Optional[str] = None
    completed_at: Optional[datetime] = None
    channel: Optional[str] = None
    sku_code: Optional[str] = None
    spec_text: Optional[str] = None
    model_version_id: Optional[str] = None
    spec_hash: Optional[str] = None
    qty: Optional[Decimal] = None
    revenue_amount: Optional[Decimal] = None
    final_material_lines: List[Dict[str, Any]] = Field(default_factory=list)
    trace: Dict[str, Any] = Field(default_factory=dict)
    generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class ShipmentInventoryDeductionLineRead(BaseModel):
    id: str
    shipment_line_id: str
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    unit_of_measure: Optional[str] = None
    quantity: Optional[Decimal] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ShipmentCostingResultRead(BaseModel):
    id: str
    shipment_line_id: str
    mode: str
    qty: Optional[Decimal] = None
    cost_total: Optional[Decimal] = None
    cost_material_total: Optional[Decimal] = None
    cost_process_total: Optional[Decimal] = None
    cost_overhead_total: Optional[Decimal] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class ShipmentProcessCostLineRead(BaseModel):
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    team_name: Optional[str] = None
    pricing_method: Optional[str] = None
    measure_quantity: Optional[Decimal] = None
    cost_type: Optional[str] = None
    base_minutes: Optional[Decimal] = None
    unit_minutes: Optional[Decimal] = None
    rate_per_minute: Optional[Decimal] = None
    piece_rate: Optional[Decimal] = None
    total_minutes: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    warnings: List[str] = Field(default_factory=list)

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class BomSnapshotRecomputeRequest(BaseModel):
    operator_id: Optional[str] = Field(None, max_length=64)


class AfterSalesImportBatchRead(BaseModel):
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


class PaginatedAfterSalesImportBatchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AfterSalesImportBatchRead]


class AfterSalesLineRead(BaseModel):
    id: str
    batch_id: str
    row_index: int
    after_sales_no: Optional[str] = None
    occurred_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    channel: Optional[str] = None
    reason: Optional[str] = None
    # Best-effort binding info (computed via sku_code -> active version mapping)
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    bound_version_label: Optional[str] = None
    order_no: Optional[str] = None
    product_link_id: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    spec_text: Optional[str] = None
    unit: Optional[str] = None
    sale_unit_price: Optional[Decimal] = None
    return_qty: Optional[Decimal] = None
    actual_return_qty: Optional[Decimal] = None
    refund_amount: Optional[Decimal] = None
    allocated_refund_amount: Optional[Decimal] = None
    sku_code: Optional[str] = None
    normalize_warnings: List[Dict[str, Any]] = Field(default_factory=list, alias="normalize_warnings_json")
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class PaginatedAfterSalesLineResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AfterSalesLineRead]


class AfterSalesReasonOptionItem(BaseModel):
    reason: str
    count: int


class AfterSalesReasonOptionsResponse(BaseModel):
    items: List[AfterSalesReasonOptionItem] = Field(default_factory=list)


class AfterSalesModelOptionItem(BaseModel):
    model_code: str
    model_name: Optional[str] = None
    count: int


class AfterSalesModelOptionsResponse(BaseModel):
    items: List[AfterSalesModelOptionItem] = Field(default_factory=list)


class AfterSalesExceptionRead(BaseModel):
    id: str
    batch_id: str
    after_sales_line_id: Optional[str] = None
    reason: str
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict, alias="payload_json")
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class ReturnsRateBySkuItem(BaseModel):
    period: str
    channel: Optional[str] = None
    sku_code: Optional[str] = None
    shipped_qty: Decimal
    returned_qty: Decimal
    return_rate: Optional[Decimal] = None
    shipped_amount: Decimal
    refund_amount: Decimal
    refund_rate: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ReturnsRateBySkuResponse(BaseModel):
    group_by: Literal["day", "month"]
    start: str
    end: str
    items: List[ReturnsRateBySkuItem] = Field(default_factory=list)
    unmatched_returns_missing_order_no: int = 0


class AfterSalesDashboardKpis(BaseModel):
    shipped_qty: Decimal = Decimal("0")
    shipped_amount: Decimal = Decimal("0")
    returned_qty: Decimal = Decimal("0")
    refund_amount: Decimal = Decimal("0")
    return_rate: Optional[Decimal] = None
    refund_rate: Optional[Decimal] = None
    model_mapped_shipped_qty: Decimal = Decimal("0")
    model_mapped_rate: Optional[Decimal] = None
    # attribution quality
    # 1) within selected shipment window (for lag distribution readiness)
    matched_return_lines: int = 0
    matched_return_lines_with_applied_at: int = 0
    # 2) within selected applied window (data quality: "unattributed share")
    after_sales_lines_total: int = 0
    after_sales_lines_matched_any_shipment: int = 0
    after_sales_lines_unmatched: int = 0
    after_sales_lines_unmatched_rate: Optional[Decimal] = None
    after_sales_lines_missing_order_no: int = 0
    after_sales_lines_missing_product_link_id: int = 0
    after_sales_lines_missing_sku_code: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class AfterSalesDashboardSeriesItem(BaseModel):
    period: str
    shipped_qty: Decimal
    shipped_amount: Decimal
    returned_qty: Decimal
    refund_amount: Decimal
    return_rate: Optional[Decimal] = None
    refund_rate: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class AfterSalesDashboardTopReasonItem(BaseModel):
    reason: str
    returned_qty: Decimal
    refund_amount: Decimal
    share_returned_qty: Optional[Decimal] = None
    share_refund_amount: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class AfterSalesDashboardTopModelItem(BaseModel):
    model_code: str
    model_name: Optional[str] = None
    # Optional bundle (BundleAsModel) display helpers:
    # If model_code is a bundle code like "B-DB9EAE" (template_code=DB9E, selector=AE),
    # we can enrich these fields for clearer UI display.
    bundle_template_code: Optional[str] = None  # e.g. "DB9E"
    bundle_preset_selector: Optional[str] = None  # e.g. "AE"
    bundle_preset_phrase: Optional[str] = None  # e.g. "[{}{毛球}][{黄金绒}{雪尼尔}]0*0*0"
    shipped_qty: Decimal
    returned_qty: Decimal
    return_rate: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class AfterSalesDashboardTopSkuItem(BaseModel):
    sku_code: str
    spec_text: Optional[str] = None
    shipped_qty: Decimal
    returned_qty: Decimal
    return_rate: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class AfterSalesDashboardTopLinkItem(BaseModel):
    product_link_id: str
    spec_text: Optional[str] = None
    shipped_qty: Decimal
    returned_qty: Decimal
    return_rate: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class AfterSalesDashboardResponse(BaseModel):
    group_by: Literal["week", "month"]
    start: str
    end: str
    kpis: AfterSalesDashboardKpis
    series: List[AfterSalesDashboardSeriesItem] = Field(default_factory=list)
    top_reasons: List[AfterSalesDashboardTopReasonItem] = Field(default_factory=list)
    top_models: List[AfterSalesDashboardTopModelItem] = Field(default_factory=list)
    top_skus: List[AfterSalesDashboardTopSkuItem] = Field(default_factory=list)
    top_links: List[AfterSalesDashboardTopLinkItem] = Field(default_factory=list)
    # lag distribution (matched returns vs shipment completed_at)
    lag_buckets: List[Dict[str, Any]] = Field(default_factory=list)


class ProfitBySkuItem(BaseModel):
    period: str
    channel: Optional[str] = None
    sku_code: Optional[str] = None
    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    refund_amount: Decimal
    returned_qty: Decimal
    net_revenue: Decimal
    net_profit: Decimal
    net_margin: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProfitBySkuResponse(BaseModel):
    group_by: Literal["day", "month"]
    start: str
    end: str
    total_shipment_lines: int = 0
    lines_with_bom_snapshots: int = 0
    lines_missing_costing: int = 0
    items: List[ProfitBySkuItem] = Field(default_factory=list)
    note: Optional[str] = None


class ProfitByModelItem(BaseModel):
    period: str
    channel: Optional[str] = None
    model_id: str
    model_code: str
    model_name: str
    # NOTE: model-level aggregation may involve multiple versions.
    # We expose a "top" version for quick reading, plus version_count.
    version_id: str
    version_kind: str
    version_status: str
    version_label: Optional[str] = None
    version_count: int = 1
    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_material_amount: Decimal = Decimal("0")
    cost_process_amount: Decimal = Decimal("0")
    cost_overhead_amount: Decimal = Decimal("0")
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    refund_amount: Decimal
    net_revenue: Decimal
    net_profit: Decimal
    net_margin: Optional[Decimal] = None
    line_count: int = 0
    costed_line_count: int = 0
    missing_costing_line_count: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProfitByModelResponse(BaseModel):
    group_by: Literal["day", "month"]
    start: str
    end: str
    total_shipment_lines: int = 0
    mapped_model_lines: int = 0
    costed_lines: int = 0
    lines_missing_costing: int = 0
    items: List[ProfitByModelItem] = Field(default_factory=list)
    note: Optional[str] = None


class ModelInsightsSummaryItem(BaseModel):
    channel: Optional[str] = None
    model_id: str
    model_code: str
    model_name: str

    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_material_amount: Decimal = Decimal("0")
    cost_process_amount: Decimal = Decimal("0")
    cost_overhead_amount: Decimal = Decimal("0")
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    returned_qty: Decimal = Decimal("0")
    refund_amount: Decimal
    net_revenue: Decimal
    net_profit: Decimal
    net_margin: Optional[Decimal] = None

    line_count: int = 0
    costed_line_count: int = 0
    missing_costing_line_count: int = 0

    top_version_id: Optional[str] = None
    top_version_kind: Optional[str] = None
    top_version_status: Optional[str] = None
    top_version_label: Optional[str] = None
    version_count: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelInsightsSummaryResponse(BaseModel):
    start: str
    end: str
    channel: Optional[str] = None
    total_shipment_lines: int = 0
    mapped_model_lines: int = 0
    costed_lines: int = 0
    lines_missing_costing: int = 0
    items: List[ModelInsightsSummaryItem] = Field(default_factory=list)
    note: Optional[str] = None


class ModelBaseMaterialLine(BaseModel):
    material_type: Optional[str] = None
    material_ref_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    unit_of_measure: Optional[str] = None
    calculation_method: Optional[str] = None
    base_quantity: Optional[Decimal] = None
    loss_rate: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None
    sequence_order: Optional[int] = None
    notes: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelBaseProcessLine(BaseModel):
    process_id: Optional[str] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    team_name: Optional[str] = None
    pricing_method: Optional[str] = None
    piece_rate: Optional[Decimal] = None
    rate_per_minute: Optional[Decimal] = None
    notes: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelInsightsVersionStat(BaseModel):
    version_id: str
    version_kind: Optional[str] = None
    version_status: Optional[str] = None
    version_label: Optional[str] = None
    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_material_amount: Decimal = Decimal("0")
    cost_process_amount: Decimal = Decimal("0")
    cost_overhead_amount: Decimal = Decimal("0")
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    line_count: int = 0
    costed_line_count: int = 0
    missing_costing_line_count: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelInsightsDeductionLine(BaseModel):
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    unit_of_measure: Optional[str] = None
    quantity: Optional[Decimal] = None
    sources: Optional[int] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelInsightsDetailResponse(BaseModel):
    start: str
    end: str
    channel: Optional[str] = None
    model_id: str
    model_code: str
    model_name: str
    selected_version_id: Optional[str] = None
    versions: List[ModelInsightsVersionStat] = Field(default_factory=list)

    sample_shipment_line_id: Optional[str] = None
    sample_completed_at: Optional[datetime] = None
    sample_sku_code: Optional[str] = None
    sample_spec_text: Optional[str] = None
    sample_qty: Optional[Decimal] = None

    bom: Optional[Dict[str, Any]] = None  # same shape as bom/generate (final_material_lines + trace)
    persisted_deductions: List[ModelInsightsDeductionLine] = Field(default_factory=list)
    base_material_lines: List[ModelBaseMaterialLine] = Field(default_factory=list)
    base_process_lines: List[ModelBaseProcessLine] = Field(default_factory=list)
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str, datetime: lambda v: v.isoformat() if v else None}


# -----------------------------
# Model usage aggregates (real shipped lines)
# -----------------------------


class ModelUsageMaterialItem(BaseModel):
    material_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    unit_of_measure: Optional[str] = None
    total_quantity: Decimal = Decimal("0")
    line_count: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelUsageMaterialSummaryResponse(BaseModel):
    start: str
    end: str
    channel: Optional[str] = None
    model_code: str
    version_id: Optional[str] = None

    total_shipment_lines: int = 0  # baseline (all shipments in range)
    mapped_model_lines: int = 0  # lines attributed to the model (and optional version)
    shipped_qty_total: Decimal = Decimal("0")  # sum(qty) for mapped lines

    lines_with_deductions: int = 0  # mapped lines that have persisted deduction lines
    shipped_qty_covered: Decimal = Decimal("0")  # sum(qty) for lines_with_deductions

    items: List[ModelUsageMaterialItem] = Field(default_factory=list)
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelUsageProcessItem(BaseModel):
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    team_name: Optional[str] = None
    total_minutes: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    line_count: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ModelUsageProcessSummaryResponse(BaseModel):
    start: str
    end: str
    channel: Optional[str] = None
    model_code: str
    version_id: Optional[str] = None

    total_shipment_lines: int = 0
    mapped_model_lines: int = 0
    shipped_qty_total: Decimal = Decimal("0")

    lines_with_process_details: int = 0  # mapped lines that have snapshot trace.process_lines
    shipped_qty_covered: Decimal = Decimal("0")

    items: List[ModelUsageProcessItem] = Field(default_factory=list)
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ShipmentProfitLineItem(BaseModel):
    shipment_line_id: str
    row_index: Optional[int] = None
    shipment_no: Optional[str] = None
    completed_at: Optional[datetime] = None
    channel: Optional[str] = None
    sku_code: Optional[str] = None
    spec_text: Optional[str] = None
    qty: Optional[Decimal] = None
    revenue_amount: Optional[Decimal] = None

    bom_snapshot_id: Optional[str] = None
    model_version_id: Optional[str] = None
    spec_hash: Optional[str] = None
    generated_at: Optional[datetime] = None

    cost_amount: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    gross_margin: Optional[Decimal] = None

    status: str = "unknown"  # costed | missing_snapshot | missing_costing
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ShipmentProfitLinesResponse(BaseModel):
    batch_id: str
    total_shipment_lines: int = 0
    lines_with_bom_snapshots: int = 0
    lines_missing_costing: int = 0
    items: List[ShipmentProfitLineItem] = Field(default_factory=list)
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ReturnsRateByChannelItem(BaseModel):
    period: str
    channel: Optional[str] = None
    shipped_qty: Decimal
    returned_qty: Decimal
    return_rate: Optional[Decimal] = None
    shipped_amount: Decimal
    refund_amount: Decimal
    refund_rate: Optional[Decimal] = None
    shipment_lines_total: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ReturnsRateByChannelResponse(BaseModel):
    group_by: Literal["day", "month"]
    start: str
    end: str
    items: List[ReturnsRateByChannelItem] = Field(default_factory=list)
    unmatched_returns_missing_order_no: int = 0


class ProfitByChannelItem(BaseModel):
    period: str
    channel: Optional[str] = None
    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    refund_amount: Decimal
    returned_qty: Decimal
    net_revenue: Decimal
    net_profit: Decimal
    net_margin: Optional[Decimal] = None
    shipment_lines_total: int = 0
    lines_with_bom_snapshots: int = 0
    lines_missing_costing: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class ProfitByChannelResponse(BaseModel):
    group_by: Literal["day", "month"]
    start: str
    end: str
    total_shipment_lines: int = 0
    lines_with_bom_snapshots: int = 0
    lines_missing_costing: int = 0
    items: List[ProfitByChannelItem] = Field(default_factory=list)
    note: Optional[str] = None


class SalesLineItem(BaseModel):
    shipment_line_id: str
    batch_id: Optional[str] = None
    row_index: Optional[int] = None
    payment_at: Optional[str] = None
    completed_at: Optional[datetime] = None
    channel: Optional[str] = None
    sku_no: Optional[str] = None  # 货品编号（若原始表有）
    sku_name: Optional[str] = None  # 货品名称（若原始表有）
    spec_text: Optional[str] = None
    sku_code: Optional[str] = None  # 货品条码
    sale_unit_price: Optional[Decimal] = None
    qty: Optional[Decimal] = None
    revenue_amount: Optional[Decimal] = None
    cost_unit_price: Optional[Decimal] = None
    cost_amount: Optional[Decimal] = None
    order_no: Optional[str] = None
    product_link_id: Optional[str] = None
    logistics_company: Optional[str] = None
    logistics_no: Optional[str] = None
    mark: Optional[str] = None
    # 套装锚点（用于对账/排查/看板，不做组件拆解）
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    # 套装二级名称（phrase preset 文本，如 "[{}{毛球}][{黄金绒}{雪尼尔}]0*0*0"）
    bundle_preset_phrase: Optional[str] = None

    # 当前生效绑定（用于运营决策/下钻；标准模型或 BundleAsModel）
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None

    bom_snapshot_id: Optional[str] = None
    status: str = "unknown"  # costed | missing_snapshot | missing_costing
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SalesLinesResponse(BaseModel):
    start: str
    end: str
    total: int = 0
    page: int = 1
    page_size: int = 50
    lines_with_bom_snapshots: int = 0
    lines_missing_costing: int = 0
    items: List[SalesLineItem] = Field(default_factory=list)
    note: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SalesProfitDashboardKpis(BaseModel):
    # totals (all shipment lines in range)
    shipped_qty: Decimal = Decimal("0")
    revenue_amount: Decimal = Decimal("0")
    shipment_lines_total: int = 0
    # cost coverage (only lines with known costing)
    costed_revenue_amount: Decimal = Decimal("0")
    costed_lines: int = 0
    lines_missing_costing: int = 0
    costed_revenue_rate: Optional[Decimal] = None
    # profitability (computed only on costed lines)
    cost_amount: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    gross_margin: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SalesProfitDashboardSeriesItem(BaseModel):
    period: str
    shipped_qty: Decimal
    revenue_amount: Decimal
    costed_revenue_amount: Decimal
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    shipment_lines_total: int = 0
    costed_lines: int = 0
    lines_missing_costing: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SalesProfitDashboardTopSkuItem(BaseModel):
    sku_code: str
    spec_text: Optional[str] = None
    # 绑定/归属（运营视角：该 SKU 当前对应的模型/套装）
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    # Optional bundle (BundleAsModel) display helpers
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    bundle_preset_phrase: Optional[str] = None
    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    shipment_lines_total: int = 0
    costed_lines: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SalesProfitDashboardTopModelItem(BaseModel):
    model_code: str
    model_name: Optional[str] = None
    # Optional bundle (BundleAsModel) display helpers
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    bundle_preset_phrase: Optional[str] = None
    shipped_qty: Decimal
    revenue_amount: Decimal
    cost_amount: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    shipment_lines_total: int = 0
    costed_lines: int = 0

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SalesProfitDashboardResponse(BaseModel):
    group_by: Literal["week", "month"]
    start: str
    end: str
    channel: Optional[str] = None
    top_n: int = 12
    kpis: SalesProfitDashboardKpis
    series: List[SalesProfitDashboardSeriesItem] = Field(default_factory=list)
    top_skus_profit: List[SalesProfitDashboardTopSkuItem] = Field(default_factory=list)
    top_skus_loss: List[SalesProfitDashboardTopSkuItem] = Field(default_factory=list)
    top_models_profit: List[SalesProfitDashboardTopModelItem] = Field(default_factory=list)
    top_models_loss: List[SalesProfitDashboardTopModelItem] = Field(default_factory=list)
    note: Optional[str] = None


class SkuMasterRead(BaseModel):
    id: str
    erp_sku_barcode: str
    platform_product_id: Optional[str] = None
    platform_sku_id: Optional[str] = None
    # 商家编码 / 网店规格编码：2026 新规则的“预置锚点”（模型码/套装码等）
    shop_spec_code: Optional[str] = None
    # 套装模板绑定（Phase0：存储在 sku_master.metadata_json，作为“商家编码锚点”的人工兜底入口）
    bundle_template_id: Optional[str] = None
    bundle_template_code: Optional[str] = None
    # 套装模板二级（phrase preset selector，如 AA/AB/...；第二级才是最终绑定目标）
    bundle_preset_selector: Optional[str] = None
    # 套装模板发布版本（口径稳定：发布版本 → 套装模型版本）
    bundle_template_version_id: Optional[str] = None
    bundle_template_version_label: Optional[str] = None
    bundle_model_version_id: Optional[str] = None
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
    # Pre-parse cache / manual audit (stored in metadata_json; for acceleration & preview only)
    preparse_spec_text: Optional[str] = None
    preparse_spec_hash: Optional[str] = None
    preparse_parser_version: Optional[str] = None
    preparse_dimensions: Dict[str, Any] = Field(default_factory=dict)
    preparse_tokens: List[str] = Field(default_factory=list)
    preparse_has_dims: Optional[bool] = None
    preparse_saved_at: Optional[str] = None
    preparse_saved_by: Optional[str] = None
    spec_mismatch: bool = False
    spec_mismatch_at: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class ShopSkuMappingRead(BaseModel):
    id: str
    channel: Optional[str] = None
    platform_product_id: Optional[str] = None
    platform_sku_id: str
    erp_sku_barcode: Optional[str] = None
    shop_spec_code: Optional[str] = None
    production_process: Optional[str] = None
    match_status: Optional[str] = None
    match_method: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class SkuMasterScanResponse(BaseModel):
    sku_master: SkuMasterRead
    shop_skus: List[ShopSkuMappingRead] = Field(default_factory=list)


class PaginatedSkuMasterResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[SkuMasterRead]


class SkuMasterSpecPreparseSaveRequest(BaseModel):
    spec_text: str
    # Optional manual overrides (cm); if omitted, use parser outputs.
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    diameter_cm: Optional[Decimal] = None
    requested_by: Optional[str] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SkuMasterSpecPreparseSaveResponse(BaseModel):
    sku_id: str
    preparse_spec_hash: str
    preparse_dimensions: Dict[str, Any] = Field(default_factory=dict)
    preparse_tokens: List[str] = Field(default_factory=list)
    preparse_saved_at: Optional[str] = None
    preparse_saved_by: Optional[str] = None


class SkuMasterSpecPreparseBulkRequest(BaseModel):
    # only process bound SKUs in bulk
    limit: int = Field(200, ge=1, le=5000)
    # filters (same as list_sku_master)
    search: Optional[str] = None
    channel: Optional[str] = None
    match_status: Optional[str] = None
    # target kind: model|bundle|any
    target_kind: Optional[str] = None
    # bundle anchor filters (from sku_master.metadata_json)
    bundle_bound_state: Optional[str] = None
    bundle_template_id: Optional[str] = None
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    include_terms: Optional[str] = None
    exclude_terms: Optional[str] = None
    match_scope: Optional[str] = None
    # optional: only process SKUs bound to a specific model/version
    bound_model_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_version_id: Optional[str] = None
    # optional state filter: parsed/unparsed
    preparse_state: Optional[str] = None
    # cursor for stable scanning (recommended for huge datasets)
    cursor_id: Optional[str] = None
    # cross-page exclude list (implicit select-all UX)
    excluded_sku_ids: List[str] = Field(default_factory=list)
    # behavior
    skip_if_same_hash: bool = True
    requested_by: Optional[str] = None


class SkuMasterSpecPreparseBulkResponse(BaseModel):
    scanned: int
    saved: int
    skipped_same_hash: int
    skipped_empty_spec: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    # loop/run-all hints
    batch_candidates: int = 0
    has_more: bool = False
    # cursor-based run-all support
    next_cursor_id: Optional[str] = None
    mode: Optional[str] = None


class SkuMasterSpecPreparsePreviewItem(BaseModel):
    sku_id: str
    erp_sku_barcode: str
    channel: Optional[str] = None
    # for table display (same as sku master list)
    product_name: Optional[str] = None
    product_code: Optional[str] = None
    spec_text: Optional[str] = None
    # bundle anchor (from sku_master.metadata_json)
    bundle_template_id: Optional[str] = None
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_model_name: Optional[str] = None
    bound_version_label: Optional[str] = None
    spec_text_used: str
    spec_hash: str
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    diameter_cm: Optional[Decimal] = None
    area_m2: Optional[Decimal] = None
    perimeter_m: Optional[Decimal] = None

    class Config:
        json_encoders = {Decimal: _decimal_to_str}


class SkuMasterSpecPreparsePreviewRequest(BaseModel):
    limit: int = Field(200, ge=1, le=5000)
    search: Optional[str] = None
    channel: Optional[str] = None
    match_status: Optional[str] = None
    target_kind: Optional[str] = None
    bundle_bound_state: Optional[str] = None
    bundle_template_id: Optional[str] = None
    bundle_template_code: Optional[str] = None
    bundle_preset_selector: Optional[str] = None
    include_terms: Optional[str] = None
    exclude_terms: Optional[str] = None
    match_scope: Optional[str] = None
    bound_model_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_version_id: Optional[str] = None
    preparse_state: Optional[str] = None


class SkuMasterSpecPreparsePreviewResponse(BaseModel):
    scanned: int
    skipped_empty_spec: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    items: List[SkuMasterSpecPreparsePreviewItem] = Field(default_factory=list)


class SkuMasterSpecPreparseExecuteRequest(BaseModel):
    sku_ids: List[str] = Field(default_factory=list)
    skip_if_same_hash: bool = True
    requested_by: Optional[str] = None


class SkuMasterSpecPreparseExecuteResponse(BaseModel):
    scanned: int
    saved: int
    skipped_same_hash: int
    skipped_empty_spec: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)


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
    # if true, rebind even when SKU already has an active binding
    allow_rebind: bool = False


class SkuMasterBindByModelResponse(BaseModel):
    total_selected: int
    bound_count: int
    skipped_already_bound: int
    skipped_missing_barcode: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class SkuMasterUnbindRequest(BaseModel):
    sku_master_ids: List[str] = Field(default_factory=list)
    requested_by: Optional[str] = None


class SkuMasterUnbindResponse(BaseModel):
    total_selected: int
    unbound_count: int
    skipped_missing_barcode: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class SkuMasterGeneratePreparseAndSnapshotsRequest(BaseModel):
    sku_master_ids: List[str] = Field(default_factory=list)
    operator_id: Optional[str] = None
    # Safety defaults: only fill missing snapshots (never overwrite) and cap per SKU.
    limit_per_sku: int = Field(50, ge=1, le=500)
    overwrite: bool = False  # 高风险：覆盖重算（默认关闭）


class SkuMasterGeneratePreparseAndSnapshotsResponse(BaseModel):
    total_selected: int
    parsed_count: int
    created_snapshots: int
    recomputed_snapshots: int
    skipped_snapshots: int
    failed_snapshots: int
    skipped_missing_barcode: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class SkuMasterBindByModelBulkRequest(BaseModel):
    """
    Bind all *unbound* SKU masters matched by current filters, in batches (server-side paging).
    Used by UI "人工审核：按筛选条件一键跑完（跨页）" where the table is implicitly "select all".
    """

    model_id: str
    requested_by: Optional[str] = None
    limit: int = Field(200, ge=1, le=2000)
    # default behavior is to bind unbound only (same as before).
    # for spec-matching rebind use case: set bound_state="bound" and allow_rebind=true.
    bound_state: Literal["unbound", "bound", "all"] = "unbound"
    allow_rebind: bool = False

    # Filters (same semantics as list endpoint)
    search: Optional[str] = None
    channel: Optional[str] = None
    match_status: Optional[str] = None
    spec_mismatch: Optional[bool] = None
    preparse_state: Optional[str] = None
    include_terms: Optional[str] = None
    exclude_terms: Optional[str] = None
    match_scope: Optional[str] = None
    # Optional: further restrict by current active binding (safe for "rebind version" use case)
    bound_model_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_version_id: Optional[str] = None

    # Exclusions: user can uncheck a few rows; we skip them.
    excluded_sku_master_ids: List[str] = Field(default_factory=list)


class SkuMasterBindByModelBulkResponse(BaseModel):
    batch_candidates: int
    bound_count: int
    skipped_already_bound: int
    skipped_missing_barcode: int
    skipped_excluded: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    has_more: bool


class SkuMasterBindByBundleTemplateRequest(BaseModel):
    template_id: str
    preset_selector: Optional[str] = None
    sku_master_ids: List[str] = Field(default_factory=list)
    requested_by: Optional[str] = None
    # if true, overwrite existing bundle_template binding
    allow_rebind: bool = False


class SkuMasterBindByBundleTemplateResponse(BaseModel):
    total_selected: int
    bound_count: int
    skipped_already_bound: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class SkuMasterBindByBundleTemplateBulkRequest(BaseModel):
    """
    Bind bundle_template to SKU masters matched by current filters (server-side).
    Used by UI "人工审核：按筛选条件一键跑完（跨页）" for bundle bindings.
    """

    template_id: str
    preset_selector: Optional[str] = None
    requested_by: Optional[str] = None
    limit: int = Field(200, ge=1, le=2000)
    bound_state: Literal["unbound", "bound", "all"] = "unbound"
    allow_rebind: bool = False

    # Filters (same semantics as list endpoint)
    search: Optional[str] = None
    channel: Optional[str] = None
    match_status: Optional[str] = None
    spec_mismatch: Optional[bool] = None
    preparse_state: Optional[str] = None
    include_terms: Optional[str] = None
    exclude_terms: Optional[str] = None
    match_scope: Optional[str] = None
    bound_model_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_version_id: Optional[str] = None

    excluded_sku_master_ids: List[str] = Field(default_factory=list)


class SkuMasterBindByBundleTemplateBulkResponse(BaseModel):
    batch_candidates: int
    bound_count: int
    skipped_already_bound: int
    skipped_excluded: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    has_more: bool


class SkuMasterBindPreviewItem(BaseModel):
    sku_master_id: str
    sku_code: Optional[str] = None
    channel: Optional[str] = None
    # shipment sample (latest)
    sample_shipment_line_id: Optional[str] = None
    sample_completed_at: Optional[datetime] = None
    sample_spec_text: Optional[str] = None
    sample_spec_text_norm: Optional[str] = None

    # can_bind: hard-validated OK
    # skip_*: not an error, but will not be bound (e.g. already bound)
    # hard_error: validation failed; binding must be blocked for this item
    status: Literal["can_bind", "skip_already_bound", "skip_missing_barcode", "hard_error"]
    hard_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # lightweight preview signals (optional)
    model_version_id: Optional[str] = None
    cost_total: Optional[Decimal] = None
    inventory_line_count: Optional[int] = None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {Decimal: _decimal_to_str}


class SkuMasterBindPreviewResponse(BaseModel):
    total_selected: int
    can_bind: int
    skip_already_bound: int
    skip_missing_barcode: int
    hard_errors: int
    items: List[SkuMasterBindPreviewItem] = Field(default_factory=list)


class SkuMasterBindPreviewBulkRequest(BaseModel):
    """
    Preview binding eligibility for all SKU masters matched by current filters (server-side paging),
    consistent with *bulk bind* semantics.
    """

    limit: int = Field(200, ge=1, le=2000)
    bound_state: Literal["unbound", "bound", "all"] = "unbound"
    allow_rebind: bool = False

    # Filters (same semantics as list endpoint)
    search: Optional[str] = None
    channel: Optional[str] = None
    match_status: Optional[str] = None
    spec_mismatch: Optional[bool] = None
    preparse_state: Optional[str] = None
    include_terms: Optional[str] = None
    exclude_terms: Optional[str] = None
    match_scope: Optional[str] = None
    bound_model_id: Optional[str] = None
    bound_model_code: Optional[str] = None
    bound_version_id: Optional[str] = None

    excluded_sku_master_ids: List[str] = Field(default_factory=list)
    requested_by: Optional[str] = None


class SkuMasterBindPreviewBulkResponse(BaseModel):
    batch_candidates: int
    can_bind: int
    skip_already_bound: int
    skip_missing_barcode: int
    hard_errors: int
    skipped_excluded: int
    has_more: bool
    items: List[SkuMasterBindPreviewItem] = Field(default_factory=list)


class SkuMasterAutoBindPreviewRequest(BaseModel):
    limit: int = Field(200, ge=1, le=2000)
    # max rows to scan among unbound sku masters (server-side filter) to find candidates
    scan_limit: int = Field(50000, ge=100, le=500000)


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
