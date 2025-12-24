from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from ...database import SessionLocal
from ..models import (
    Material,
    MaterialSyncJob,
    ModelProcess,
    Process,
    ProcessModule,
    ProductModel,
    utcnow,
)

logger = logging.getLogger(__name__)


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any, default: Decimal) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _to_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    true_values = {"1", "true", "yes", "y", "启用", "激活", "active"}
    false_values = {"0", "false", "no", "n", "禁用", "停用", "inactive"}
    if text in true_values:
        return True
    if text in false_values:
        return False
    return default


def _to_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _to_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@dataclass
class YidaConfig:
    app_key: str
    app_secret: str
    system_token: str
    app_type: str
    user_id: str
    form_uuid: str
    page_size: int = 50
    field_mapping: Dict[str, Any] = field(default_factory=dict)
    mock_data_path: Optional[str] = None

    @classmethod
    def from_file(cls, path: str | Path) -> "YidaConfig":
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"YiDa config file not found: {config_path}")
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return cls(**data)


class YidaFormClient:
    """Lightweight client for DingTalk YiDa form APIs."""

    TOKEN_URL = "https://oapi.dingtalk.com/gettoken"
    SEARCH_URL = "https://api.dingtalk.com/v1.0/yida/forms/instances/search"

    def __init__(self, config: YidaConfig, session: Optional[requests.Session] = None):
        self.config = config
        self._session = session or requests.Session()
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0.0
        self._mock_data: Optional[list[Dict[str, Any]]] = None

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expire_at:
            return self._access_token

        params = {"appkey": self.config.app_key, "appsecret": self.config.app_secret}
        resp = self._session.get(self.TOKEN_URL, params=params, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errcode") != 0:
            raise RuntimeError(f"Failed to obtain DingTalk access token: {payload}")

        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 7200)
        # refresh 5 minutes before official expiry
        self._token_expire_at = time.time() + max(0, expires_in - 300)
        return self._access_token

    def fetch_instances(self, limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Yield raw YiDa form instances."""

        if self.config.mock_data_path:
            if self._mock_data is None:
                data_path = Path(self.config.mock_data_path)
                if not data_path.is_absolute():
                    repo_root = Path(__file__).resolve().parents[4]
                    data_path = repo_root / data_path
                if not data_path.exists():
                    raise FileNotFoundError(f"Mock data file not found: {data_path}")
                self._mock_data = json.loads(data_path.read_text(encoding="utf-8"))
            total = 0
            for record in self._mock_data:
                yield record
                total += 1
                if limit and total >= limit:
                    return
            return

        page = 1
        total = 0
        while True:
            token = self._get_access_token()
            headers = {
                "Content-Type": "application/json",
                "x-acs-dingtalk-access-token": token,
            }
            payload = {
                "appType": self.config.app_type,
                "systemToken": self.config.system_token,
                "userId": self.config.user_id,
                "formUuid": self.config.form_uuid,
                "pageSize": self.config.page_size,
                "currentPage": page,
            }
            resp = self._session.post(self.SEARCH_URL, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("data") or data.get("pageList") or data.get("result") or []
            if not records:
                break

            for record in records:
                yield record
                total += 1
                if limit and total >= limit:
                    return

            page += 1


@dataclass
class NormalizedMaterial:
    material_code: str
    material_name: str
    material_type: Optional[str]
    category: Optional[str]
    model_category: Optional[str]
    unit: Optional[str]
    unit_price: Decimal
    currency: Optional[str]
    purchase_unit: Optional[str]
    inventory_unit: Optional[str]
    supplier_code: Optional[str]
    supplier_name: Optional[str]
    status: Optional[str]
    is_active: bool
    source_created_at: Optional[datetime]
    source_updated_at: Optional[datetime]
    usage_scope: Optional[str]
    bom_notes: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class MaterialSyncResult:
    total_fetched: int = 0
    processed: int = 0
    created: int = 0
    updated: int = 0
    disabled: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def dict(self) -> Dict[str, Any]:
        return {
            "total_fetched": self.total_fetched,
            "processed": self.processed,
            "created": self.created,
            "updated": self.updated,
            "disabled": self.disabled,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class YidaMaterialMapper:
    """Maps YiDa form data to NormalizedMaterial records."""

    def __init__(self, field_mapping: Optional[Dict[str, str]] = None):
        self.field_mapping = field_mapping or {}

    def map_record(self, record: Dict[str, Any]) -> Tuple[Optional[NormalizedMaterial], Optional[str]]:
        form_data = record.get("formData") or {}

        material_code = _clean_str(self._get_value(form_data, "material_code"))
        if not material_code:
            return None, "missing material_code"

        material_name = _clean_str(self._get_value(form_data, "material_name")) or material_code
        unit_price = _to_decimal(self._get_value(form_data, "unit_price"), default=Decimal("0"))
        unit = _clean_str(self._get_value(form_data, "unit"))
        currency = _clean_str(self._get_value(form_data, "currency")) or "CNY"
        is_active_raw = self._get_value(form_data, "is_active")
        if is_active_raw is None:
            is_active_raw = self._get_value(form_data, "enabled_flag")
        is_active = _to_bool(is_active_raw, default=True)
        status = _clean_str(self._get_value(form_data, "status")) or (
            "active" if is_active else "inactive"
        )

        metadata: Dict[str, Any] = {
            "source_form_instance_id": record.get("formInstanceId"),
            "raw_form_data": form_data,
        }

        bom_unit_price_raw = self._get_value(form_data, "bom_unit_price")
        if bom_unit_price_raw not in (None, ""):
            metadata["bom_unit_price"] = float(
                _to_decimal(bom_unit_price_raw, default=Decimal("0"))
            )

        cost_formula = _clean_str(self._get_value(form_data, "cost_formula"))
        if cost_formula:
            metadata["cost_formula"] = cost_formula

        # 宜搭新增字段：采购单位/采购单价（仅落库到 metadata_json，避免覆盖本地入库口径字段）
        yida_purchase_unit = _clean_str(self._get_value(form_data, "yida_purchase_unit"))
        if yida_purchase_unit:
            metadata["yida_purchase_unit"] = yida_purchase_unit
        yida_purchase_unit_price_raw = self._get_value(form_data, "yida_purchase_unit_price")
        if yida_purchase_unit_price_raw not in (None, ""):
            metadata["yida_purchase_unit_price"] = float(
                _to_decimal(yida_purchase_unit_price_raw, default=Decimal("0"))
            )

        # 采购转入库公式：宜搭字段（numberField_mjjgsdlq），用于入库口径解释/核对（不参与计算）
        purchase_to_inbound_formula = _clean_str(
            self._get_value(form_data, "purchase_to_inbound_formula")
        )
        if purchase_to_inbound_formula:
            metadata["purchase_to_inbound_formula"] = purchase_to_inbound_formula

        normalized = NormalizedMaterial(
            material_code=material_code,
            material_name=material_name,
            material_type=_clean_str(self._get_value(form_data, "material_type")),
            category=_clean_str(self._get_value(form_data, "category")),
            model_category=_clean_str(self._get_value(form_data, "model_category")),
            unit=unit,
            unit_price=unit_price,
            currency=currency,
            purchase_unit=_clean_str(self._get_value(form_data, "purchase_unit")),
            inventory_unit=_clean_str(self._get_value(form_data, "inventory_unit")),
            supplier_code=_clean_str(self._get_value(form_data, "supplier_code")),
            supplier_name=_clean_str(self._get_value(form_data, "supplier_name")),
            status=status,
            is_active=is_active,
            source_created_at=_to_datetime(self._get_value(form_data, "source_created_at")),
            source_updated_at=_to_datetime(self._get_value(form_data, "source_updated_at")),
            usage_scope=_clean_str(self._get_value(form_data, "usage_scope")),
            bom_notes=_clean_str(self._get_value(form_data, "bom_notes")),
            metadata={k: v for k, v in metadata.items() if v not in (None, "", [])},
        )
        return normalized, None

    def _get_value(self, form_data: Dict[str, Any], key: str) -> Any:
        mapping_entry = self.field_mapping.get(key)
        if not mapping_entry:
            return None
        if isinstance(mapping_entry, dict):
            field_id = mapping_entry.get("id") or mapping_entry.get("field_id")
        else:
            field_id = mapping_entry
        if not field_id:
            return None
        return form_data.get(field_id)

class MaterialSyncService:
    """Synchronizes YiDa materials into the local materials table."""

    def __init__(self, db: Session, client: YidaFormClient):
        self.db = db
        self.client = client
        self.mapper = YidaMaterialMapper(client.config.field_mapping)

    def sync_materials(
        self,
        *,
        limit: Optional[int] = None,
        dry_run: bool = False,
        dump_path: Optional[Path] = None,
    ) -> MaterialSyncResult:
        result = MaterialSyncResult()
        dump_buffer: list[Any] = []

        try:
            for record in self.client.fetch_instances(limit=limit):
                result.total_fetched += 1
                if dump_path is not None:
                    dump_buffer.append(record)

                normalized, error = self.mapper.map_record(record)
                if normalized is None:
                    result.skipped += 1
                    if error:
                        result.errors.append(f"{record.get('formInstanceId', 'unknown')}: {error}")
                    continue

                self._upsert_material(normalized, result)
                result.processed += 1

            if dump_path is not None:
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text(json.dumps(dump_buffer, ensure_ascii=False, indent=2), encoding="utf-8")

            if dry_run:
                self.db.rollback()
            else:
                self.db.commit()

            return result
        except Exception:
            self.db.rollback()
            logger.exception("YiDa material sync failed")
            raise

    def _upsert_material(self, data: NormalizedMaterial, result: MaterialSyncResult) -> None:
        material = (
            self.db.query(Material)
            .filter(Material.material_code == data.material_code)
            .one_or_none()
        )

        if material is None:
            material = Material(
                material_code=data.material_code,
                material_name=data.material_name,
                material_type=data.material_type or "raw",
                category=data.category,
                model_category=data.model_category,
                unit=data.unit,
                unit_price=data.unit_price,
                currency=data.currency or "CNY",
                purchase_unit=data.purchase_unit,
                inventory_unit=data.inventory_unit,
                supplier_code=data.supplier_code,
                supplier_name=data.supplier_name,
                is_active=data.is_active,
                status=data.status or ("active" if data.is_active else "inactive"),
                source_created_at=data.source_created_at,
                source_updated_at=data.source_updated_at,
                usage_scope=data.usage_scope,
                bom_notes=data.bom_notes,
                metadata_json=data.metadata,
            )
            self.db.add(material)
            result.created += 1
        else:
            material.material_name = data.material_name
            material.material_type = data.material_type or material.material_type
            material.category = data.category
            material.model_category = data.model_category
            material.unit = data.unit
            material.unit_price = data.unit_price
            material.currency = data.currency or material.currency
            material.purchase_unit = data.purchase_unit
            material.inventory_unit = data.inventory_unit
            material.supplier_code = data.supplier_code
            material.supplier_name = data.supplier_name
            material.is_active = data.is_active
            material.status = data.status or ("active" if data.is_active else "inactive")
            material.source_created_at = data.source_created_at
            material.source_updated_at = data.source_updated_at
            material.usage_scope = data.usage_scope
            material.bom_notes = data.bom_notes
            existing_meta = material.metadata_json or {}
            existing_meta.update(data.metadata)
            material.metadata_json = existing_meta
            result.updated += 1

        if not data.is_active:
            result.disabled += 1


@dataclass
class NormalizedProcess:
    process_code: str
    process_name: str
    module_code: Optional[str]
    module_name: Optional[str]
    team: Optional[str]
    unit: Optional[str]
    hourly_rate: Optional[Decimal]
    piece_rate: Optional[Decimal]
    fixed_time_minutes: Optional[Decimal]
    status: str
    is_active: bool
    description: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class NormalizedModelProcess:
    model_code: Optional[str]
    model_name: Optional[str]
    sequence_order: int
    notes: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class ProcessSyncResult:
    total_fetched: int = 0
    processes_created: int = 0
    processes_updated: int = 0
    modules_created: int = 0
    models_created: int = 0
    model_links_created: int = 0
    model_links_updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def dict(self) -> Dict[str, Any]:
        return {
            "total_fetched": self.total_fetched,
            "processes_created": self.processes_created,
            "processes_updated": self.processes_updated,
            "modules_created": self.modules_created,
            "models_created": self.models_created,
            "model_links_created": self.model_links_created,
            "model_links_updated": self.model_links_updated,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class YidaProcessMapper:
    def __init__(self, field_mapping: Optional[Dict[str, str]] = None):
        self.field_mapping = field_mapping or {}

    def map_record(
        self, record: Dict[str, Any]
    ) -> Tuple[Optional[NormalizedProcess], Optional[NormalizedModelProcess], Optional[str]]:
        form_data = record.get("formData") or {}

        process_code = _clean_str(self._get_value(form_data, "process_code"))
        if not process_code:
            return None, None, "missing process_code"

        process_name = _clean_str(self._get_value(form_data, "process_name")) or process_code
        module_code = _clean_str(self._get_value(form_data, "module_code"))
        module_name = _clean_str(self._get_value(form_data, "module_name"))
        team = _clean_str(self._get_value(form_data, "team"))
        unit = _clean_str(self._get_value(form_data, "unit"))
        hourly_rate = self._to_optional_decimal(self._get_value(form_data, "hourly_rate"))
        piece_rate = self._to_optional_decimal(self._get_value(form_data, "piece_rate"))
        fixed_time_minutes = self._to_optional_decimal(self._get_value(form_data, "fixed_time_minutes"))
        status = _clean_str(self._get_value(form_data, "status")) or "active"
        is_active = _to_bool(self._get_value(form_data, "is_active"), default=True)
        description = _clean_str(self._get_value(form_data, "description"))
        sequence_order = _to_int(self._get_value(form_data, "sequence_order"), default=0)
        model_code = _clean_str(self._get_value(form_data, "model_code"))
        notes = _clean_str(self._get_value(form_data, "notes"))
        calc_method = _clean_str(self._get_value(form_data, "calculation_method"))
        base_minutes = self._to_optional_decimal(self._get_value(form_data, "base_minutes"))
        square_minutes = self._to_optional_decimal(self._get_value(form_data, "square_minutes"))

        normalized_process = NormalizedProcess(
            process_code=process_code,
            process_name=process_name,
            module_code=module_code,
            module_name=module_name,
            team=team,
            unit=unit,
            hourly_rate=hourly_rate,
            piece_rate=piece_rate,
            fixed_time_minutes=fixed_time_minutes,
            status=status,
            is_active=is_active,
            description=description,
            metadata={
                "form_instance_id": record.get("formInstanceId"),
                "team": team,
                "unit": unit,
            },
        )

        normalized_link = NormalizedModelProcess(
            model_code=model_code,
            model_name=_clean_str(self._get_value(form_data, "model_name")),
            sequence_order=sequence_order,
            notes=notes,
            metadata={
                "calculation_method": calc_method,
                "base_minutes": float(base_minutes) if base_minutes is not None else None,
                "square_minutes": float(square_minutes) if square_minutes is not None else None,
            },
        )

        return normalized_process, normalized_link, None

    def _get_value(self, form_data: Dict[str, Any], key: str) -> Any:
        mapping_entry = self.field_mapping.get(key)
        if not mapping_entry:
            return None
        if isinstance(mapping_entry, dict):
            field_id = mapping_entry.get("id") or mapping_entry.get("field_id")
        else:
            field_id = mapping_entry
        if not field_id:
            return None
        return form_data.get(field_id)

    @staticmethod
    def _to_optional_decimal(value: Any) -> Optional[Decimal]:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None


class ProcessSyncService:
    def __init__(self, db: Session, client: YidaFormClient):
        self.db = db
        self.client = client
        self.mapper = YidaProcessMapper(client.config.field_mapping)

    def sync_processes(
        self,
        *,
        limit: Optional[int] = None,
        dry_run: bool = False,
        dump_path: Optional[Path] = None,
    ) -> ProcessSyncResult:
        result = ProcessSyncResult()
        dump_buffer: list[Any] = []

        try:
            for record in self.client.fetch_instances(limit=limit):
                result.total_fetched += 1
                if dump_path:
                    dump_buffer.append(record)

                normalized_process, normalized_link, error = self.mapper.map_record(record)
                if normalized_process is None:
                    result.skipped += 1
                    if error:
                        result.errors.append(f"{record.get('formInstanceId', 'unknown')}: {error}")
                    continue

                process = self._upsert_process(normalized_process, result)
                if normalized_link and normalized_link.model_code:
                    self._upsert_model_process(process, normalized_link, result)

            if dump_path:
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text(json.dumps(dump_buffer, ensure_ascii=False, indent=2), encoding="utf-8")

            if dry_run:
                self.db.rollback()
            else:
                self.db.commit()

            return result
        except Exception:
            self.db.rollback()
            logger.exception("YiDa process sync failed")
            raise

    def _ensure_module(self, normalized: NormalizedProcess) -> Tuple[Optional[ProcessModule], bool]:
        if not normalized.module_code:
            return None, False
        module = (
            self.db.query(ProcessModule)
            .filter(ProcessModule.module_code == normalized.module_code)
            .one_or_none()
        )
        created = False
        if module is None:
            module = ProcessModule(
                module_code=normalized.module_code,
                module_name=normalized.module_name or normalized.module_code,
                status="active" if normalized.is_active else "inactive",
                metadata_json={k: v for k, v in normalized.metadata.items() if v is not None},
            )
            self.db.add(module)
            created = True
        else:
            module.module_name = normalized.module_name or module.module_name
            module.status = "active" if normalized.is_active else "inactive"
        return module, created

    def _upsert_process(self, normalized: NormalizedProcess, result: ProcessSyncResult) -> Process:
        module, module_created = self._ensure_module(normalized)
        if module_created:
            result.modules_created += 1
        process = (
            self.db.query(Process)
            .filter(Process.process_code == normalized.process_code)
            .one_or_none()
        )
        metadata = {k: v for k, v in normalized.metadata.items() if v is not None}
        if process is None:
            process = Process(
                process_code=normalized.process_code,
                process_name=normalized.process_name,
                description=normalized.description,
                default_module=module,
                fixed_time_minutes=normalized.fixed_time_minutes,
                hourly_rate=normalized.hourly_rate,
                piece_rate=normalized.piece_rate,
                status=normalized.status,
                metadata_json=metadata,
            )
            self.db.add(process)
            self.db.flush()
            result.processes_created += 1
        else:
            process.process_name = normalized.process_name
            process.description = normalized.description
            if module:
                process.default_module = module
            process.fixed_time_minutes = normalized.fixed_time_minutes
            process.hourly_rate = normalized.hourly_rate
            process.piece_rate = normalized.piece_rate
            process.status = normalized.status
            existing_meta = process.metadata_json or {}
            existing_meta.update(metadata)
            process.metadata_json = existing_meta
            result.processes_updated += 1
        return process

    def _upsert_model_process(
        self,
        process: Process,
        normalized_link: NormalizedModelProcess,
        result: ProcessSyncResult,
    ) -> None:
        model = (
            self.db.query(ProductModel)
            .filter(ProductModel.model_code == normalized_link.model_code)
            .one_or_none()
        )
        if model is None and normalized_link.model_code:
            model = ProductModel(
                model_code=normalized_link.model_code,
                model_name=normalized_link.model_name or normalized_link.model_code,
                status="active",
                metadata_json={"source": "yida_sync"},
            )
            self.db.add(model)
            self.db.flush()
            result.models_created += 1
        if model is None:
            result.errors.append(f"model not found for code {normalized_link.model_code}")
            return

        link = (
            self.db.query(ModelProcess)
            .filter(
                ModelProcess.model_id == model.id,
                ModelProcess.process_id == process.id,
            )
            .one_or_none()
        )
        metadata = {k: v for k, v in normalized_link.metadata.items() if v is not None}
        if link is None:
            link = ModelProcess(
                model_id=model.id,
                process_id=process.id,
                sequence_order=normalized_link.sequence_order,
                notes=normalized_link.notes,
                metadata_json=metadata,
            )
            self.db.add(link)
            result.model_links_created += 1
        else:
            link.sequence_order = normalized_link.sequence_order
            link.notes = normalized_link.notes
            existing_meta = link.metadata_json or {}
            existing_meta.update(metadata)
            link.metadata_json = existing_meta
            result.model_links_updated += 1


def run_material_sync_job(job_id: str) -> None:
    session = SessionLocal()
    job = None
    try:
        job = session.get(MaterialSyncJob, job_id)
        if not job:
            logger.error("Material sync job %s not found", job_id)
            return

        job.status = "running"
        job.started_at = utcnow()
        session.commit()

        config = YidaConfig.from_file(job.config_path)
        client = YidaFormClient(config)
        service = MaterialSyncService(session, client)
        payload = job.payload or {}
        dump_value = payload.get("dump_path")
        dump_path = Path(dump_value) if dump_value else None
        result = service.sync_materials(
            limit=job.limit,
            dry_run=job.dry_run,
            dump_path=dump_path,
        )

        job.status = "succeeded"
        job.result_json = result.dict()
        job.finished_at = utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        if job is None:
            job = session.get(MaterialSyncJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utcnow()
            session.commit()
        logger.exception("Material sync job %s failed", job_id)
    finally:
        session.close()

