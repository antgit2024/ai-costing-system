from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models


_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # avoid 0/O/1/I


def _gen_code(n: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def create_template(
    db: Session,
    *,
    name: Optional[str],
    components: List[Dict[str, Any]],
    metadata: Dict[str, Any],
) -> models.BundleTemplate:
    if not components:
        raise ValueError("components 不能为空")

    # try a few times to avoid rare collisions
    for _ in range(20):
        code = _gen_code(6)
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


