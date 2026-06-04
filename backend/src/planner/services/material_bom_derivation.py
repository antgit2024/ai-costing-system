from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ...database import SessionLocal
from .. import models
from ..services import material_service
from .material_price_resolver import resolve_material_price

logger = logging.getLogger(__name__)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _derive_bom_unit_price(
    material: models.Material,
    *,
    as_of_date: Optional[date] = None,
) -> Optional[Decimal]:
    """
    BOM 单价推导口径（Stage 2 接入版）：

    - 老口径：``BOM 单价 = unit_price ÷ conversion_purchase_to_bom``，每次重推不沿用快照
    - Stage 2 增强（2026-05-10）：走 ``material_price_resolver`` 拿
      "含税还原 + 生效期取价"后的不含税价；回填到 ``metadata_json.bom_unit_price``
      让下游无需感知 Stage 2 字段。
    - 缺关键输入（unit / purchase_unit / unit_price / conversion 任一缺失或<=0）一律不推导，
      避免"看起来有值但口径不明"。
    """

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

    quote = resolve_material_price(material, as_of_date=as_of_date)
    if quote.bom_unit_price_exclusive is not None:
        return quote.bom_unit_price_exclusive

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


