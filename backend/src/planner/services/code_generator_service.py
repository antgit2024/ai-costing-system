from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from .. import models


def allocate_code(db: Session, *, prefix: str, width: int = 5) -> str:
    """
    Atomically allocate a new code like VM00001 / PR00001 using a counter row.
    Uses row-level locking to avoid duplicates under concurrent requests.
    """
    if not prefix or len(prefix) > 16:
        raise ValueError("prefix is invalid")
    if width < 1 or width > 16:
        raise ValueError("width is invalid")

    # SELECT ... FOR UPDATE
    counter = (
        db.query(models.CodeCounter)
        .filter(models.CodeCounter.prefix == prefix)
        .with_for_update()
        .one_or_none()
    )
    if not counter:
        counter = models.CodeCounter(prefix=prefix, next_value=1, updated_at=datetime.now(timezone.utc))
        db.add(counter)
        db.flush()

    value = int(counter.next_value or 1)
    counter.next_value = value + 1
    counter.updated_at = datetime.now(timezone.utc)
    db.commit()
    return f"{prefix}{value:0{width}d}"


def generate_random_code(
    db: Session,
    *,
    kind: Literal["product_model"],
    length: int = 3,
) -> str:
    """
    Generate a short random code with uniqueness checks.

    For product_model: 3-char code using A-Z + 1-9 (no 0), e.g. K7Q.
    """
    if kind != "product_model":
        raise ValueError("kind is invalid")
    if length < 2 or length > 12:
        raise ValueError("length is invalid")
    alphabet = string.ascii_uppercase + "123456789"
    for _ in range(2000):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        exists = (
            db.query(models.ProductModel)
            .filter(models.ProductModel.model_code == code, models.ProductModel.is_archived.is_(False))
            .count()
        )
        if exists == 0:
            return code
    raise ValueError("Failed to allocate random code, please retry")




