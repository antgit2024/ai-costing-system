from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from sqlalchemy import String, func, or_
from sqlalchemy.orm import Query, Session

from .. import models


class MaterialFilters:
    def __init__(
        self,
        *,
        search: Optional[str] = None,
        material_type: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        is_bom_material: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ):
        self.search = search
        self.material_type = material_type
        self.category = category
        self.status = status
        self.is_bom_material = is_bom_material
        self.is_active = is_active


def apply_material_filters(query: Query, filters: MaterialFilters) -> Query:
    query = query.filter(models.Material.is_archived.is_(False))
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        query = query.filter(
            or_(
                models.Material.material_code.ilike(pattern),
                models.Material.material_name.ilike(pattern),
            )
        )
    if filters.material_type:
        query = query.filter(models.Material.material_type == filters.material_type)
    if filters.category:
        # Category values come from external sync and may contain leading/trailing spaces.
        # Use TRIM on DB side + strip on input so UI taxonomy values match reliably.
        query = query.filter(func.trim(models.Material.category) == filters.category.strip())
    if filters.status:
        query = query.filter(models.Material.status == filters.status)
    if filters.is_bom_material is not None:
        # IMPORTANT:
        # Frontend historically inferred "BOM 物料" from YiDa raw form field (`radioField_lxo4jeon`)
        # even when DB column `is_bom_material` wasn't explicitly maintained.
        # To make filters reliable (especially for the material picker), treat either source as BOM.
        if filters.is_bom_material is True:
            tokens = ("1", "true", "yes", "y", "启用", "激活", "active", "是")
            dialect = ""
            try:
                if query.session is not None and query.session.get_bind() is not None:
                    dialect = str(query.session.get_bind().dialect.name or "")
            except Exception:  # noqa: BLE001
                dialect = ""

            inferred_expr = None
            if dialect.startswith("sqlite"):
                # json_extract returns scalar types; cast to string and compare normalized tokens.
                raw = func.coalesce(
                    func.json_extract(models.Material.metadata_json, "$.raw_form_data.radioField_lxo4jeon"),
                    func.json_extract(models.Material.metadata_json, "$.bom_material_flag"),
                )
                inferred_expr = func.lower(func.trim(func.cast(raw, String))).in_(tokens)

            # Fallback: if dialect unsupported, only rely on the explicit column.
            if inferred_expr is not None:
                query = query.filter(or_(models.Material.is_bom_material.is_(True), inferred_expr))
            else:
                query = query.filter(models.Material.is_bom_material.is_(True))
        else:
            query = query.filter(models.Material.is_bom_material == filters.is_bom_material)
    if filters.is_active is not None:
        query = query.filter(models.Material.is_active == filters.is_active)
    return query


def list_materials(
    db: Session,
    *,
    filters: MaterialFilters,
    page: int,
    page_size: int,
) -> Tuple[int, Sequence[models.Material]]:
    query = apply_material_filters(db.query(models.Material), filters)
    total = query.count()
    items = (
        query.order_by(models.Material.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def fetch_materials_for_export(
    db: Session,
    *,
    filters: MaterialFilters,
    limit: Optional[int] = None,
) -> Iterable[models.Material]:
    query = apply_material_filters(db.query(models.Material), filters).order_by(
        models.Material.material_code.asc()
    )
    if limit:
        query = query.limit(limit)
    return query.all()

