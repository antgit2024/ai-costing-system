from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models


_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # avoid 0/O/1/I


def _gen_code(n: int = 4) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def create_template(
    db: Session,
    *,
    name: Optional[str],
    components: List[Dict[str, Any]],
    metadata: Dict[str, Any],
) -> models.BundleTemplate:
    # components can be empty in the new workflow:
    # actual generation rows may live under metadata.phrase_presets[*].components (selected by B:CODE:A/B/...)
    components = list(components or [])

    # try a few times to avoid rare collisions
    for _ in range(20):
        # New: 4-char CODE (with selector appended externally, e.g. B-XXXXA)
        code = _gen_code(4)
        exists = db.query(models.BundleTemplate).filter(models.BundleTemplate.code == code).first()
        if exists:
            continue
        t = models.BundleTemplate(
            code=code,
            name=name,
            components_json=components,
            metadata_json=metadata or {},
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return t
    raise ValueError("生成套装编码失败（请重试）")


def get_by_code(db: Session, code: str) -> models.BundleTemplate:
    c = (code or "").strip().upper()
    if not c:
        raise ValueError("code 不能为空")
    t = (
        db.query(models.BundleTemplate)
        .filter(models.BundleTemplate.code == c, models.BundleTemplate.is_archived.is_(False))
        .first()
    )
    if not t:
        raise ValueError(f"未找到套装模板：{c}")
    return t


class BundleTemplateFilters:
    def __init__(
        self,
        *,
        search: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        include_archived: bool = False,
    ):
        self.search = search
        self.category = category
        self.tag = tag
        self.include_archived = include_archived


def list_templates(
    db: Session,
    *,
    filters: BundleTemplateFilters,
    page: int,
    page_size: int,
) -> Tuple[int, Sequence[models.BundleTemplate]]:
    query = db.query(models.BundleTemplate)
    if not filters.include_archived:
        query = query.filter(models.BundleTemplate.is_archived.is_(False))

    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        query = query.filter(or_(models.BundleTemplate.code.ilike(pattern), models.BundleTemplate.name.ilike(pattern)))

    # metadata tags/category are stored in JSON; use Python filtering for DB compatibility.
    items_all = query.order_by(models.BundleTemplate.updated_at.desc()).all()

    cat = (filters.category or "").strip() or None
    tag = (filters.tag or "").strip() or None

    def _tags(meta: Dict[str, Any]) -> List[str]:
        raw = (meta or {}).get("tags") or []
        return [str(x) for x in raw] if isinstance(raw, list) else []

    def _category(meta: Dict[str, Any]) -> Optional[str]:
        v = (meta or {}).get("category")
        return str(v).strip() if v is not None and str(v).strip() else None

    filtered: List[models.BundleTemplate] = []
    for t in items_all:
        meta = getattr(t, "metadata_json", {}) or {}
        if cat and _category(meta) != cat:
            continue
        if tag and tag not in _tags(meta):
            continue
        filtered.append(t)

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    return total, filtered[start:end]


def get_template(db: Session, template_id: str, *, include_archived: bool = False) -> Optional[models.BundleTemplate]:
    q = db.query(models.BundleTemplate).filter(models.BundleTemplate.id == template_id)
    if not include_archived:
        q = q.filter(models.BundleTemplate.is_archived.is_(False))
    return q.one_or_none()


def update_template(
    db: Session,
    *,
    template_id: str,
    name: Optional[str] = None,
    components: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> models.BundleTemplate:
    t = get_template(db, template_id, include_archived=True)
    if not t:
        raise ValueError("套装模板不存在")
    if name is not None:
        t.name = name
    if components is not None:
        t.components_json = list(components or [])
    if metadata is not None:
        t.metadata_json = metadata
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def archive_template(db: Session, template_id: str) -> None:
    t = get_template(db, template_id, include_archived=True)
    if not t:
        raise ValueError("套装模板不存在")
    t.is_archived = True
    db.add(t)
    db.commit()


def clone_template(db: Session, *, template_id: str, name: Optional[str] = None) -> models.BundleTemplate:
    src = get_template(db, template_id, include_archived=True)
    if not src:
        raise ValueError("套装模板不存在")
    clone_name = name if (name is not None and name.strip()) else (f"{src.name or src.code}（复制）")
    return create_template(
        db,
        name=clone_name,
        components=list(src.components_json or []),
        metadata=dict(src.metadata_json or {}),
    )


