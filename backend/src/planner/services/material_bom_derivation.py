from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ...database import SessionLocal
from .. import models
from ..services import material_service

logger = logging.getLogger(__name__)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _derive_bom_unit_price(material: models.Material) -> Optional[Decimal]:
    """
    BOM 单价推导口径（与前端/历史逻辑一致）：
    - 每次都按最新“入库单价 + 入库→BOM 换算”重新推导并覆盖（不沿用旧快照）
    - 公式：BOM 单价 = 入库单价(unit_price) ÷ 入库→BOM 换算(conversion_purchase_to_bom)

    说明：
    - 本接口的“推导”是为了把可推导的值落库，作为后续算价/扣库的稳定输入。
    - BOM 单位使用 materials.unit（由用户在“BOM 单位”下拉选择保存）。
    """
    # 为了避免“看起来有值但口径不明”，缺关键输入时一律不推导
    if not (material.unit or "").strip():
        return None
    if not (material.purchase_unit or "").strip():
        return None

    unit_price = _to_decimal(material.unit_price)
    conversion = _to_decimal(material.conversion_purchase_to_bom)
    if unit_price is None or conversion is None:
        return None
    if unit_price <= 0:
        return None
    if conversion <= 0:
        return None
    return unit_price / conversion


def run_material_bom_derivation_job(job_id: str) -> None:
    """
    Background job:
    - Find materials by filters/material_codes
    - Derive and persist metadata_json.bom_unit_price
    - Store job.result_json summary
    """
    session: Session = SessionLocal()
    job: models.MaterialSyncJob | None = None
    try:
        job = session.get(models.MaterialSyncJob, job_id)
        if not job:
            logger.error("Material BOM derivation job %s not found", job_id)
            return

        job.status = "running"
        job.started_at = models.utcnow()
        session.commit()

        payload = job.payload or {}
        codes_value = payload.get("material_codes") or []
        material_codes = {str(c).strip() for c in codes_value if str(c).strip()} if codes_value else None

        filters = material_service.MaterialFilters(
            search=payload.get("search"),
            material_type=payload.get("material_type"),
            category=payload.get("category"),
            status=payload.get("status"),
            is_bom_material=payload.get("is_bom_material"),
            is_active=payload.get("is_active"),
        )

        query = material_service.apply_material_filters(session.query(models.Material), filters)
        if material_codes:
            query = query.filter(models.Material.material_code.in_(sorted(material_codes)))
        total = query.count()
        items = (
            query.order_by(models.Material.updated_at.desc())
            .limit(int(job.limit or 5000))
            .all()
        )

        updated = 0
        cleared = 0
        skipped = 0
        invalid = 0

        for material in items:
            meta = dict(material.metadata_json or {})
            derived = _derive_bom_unit_price(material)
            if derived is None:
                invalid += 1
                # 清理掉无法推导且可能过期的 bom_unit_price，避免“看起来有值但已不正确”
                if "bom_unit_price" in meta:
                    meta.pop("bom_unit_price", None)
                    material.metadata_json = meta
                    cleared += 1
                else:
                    skipped += 1
                continue

            meta["bom_unit_price"] = float(derived)
            material.metadata_json = meta
            updated += 1

        if job.dry_run:
            session.rollback()
        else:
            session.commit()

        job.status = "succeeded"
        job.result_json = {
            "total_matched": total,
            "scanned": len(items),
            "updated": updated,
            "cleared": cleared,
            "invalid": invalid,
            "skipped": skipped,
        }
        job.finished_at = models.utcnow()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if job is None:
            job = session.get(models.MaterialSyncJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = models.utcnow()
            session.commit()
        logger.exception("Material BOM derivation job %s failed", job_id)
    finally:
        session.close()


