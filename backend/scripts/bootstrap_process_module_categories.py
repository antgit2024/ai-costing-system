"""
Bootstrap suggested `process_module_category` taxonomy items.

Usage:
  cd backend
  source venv/bin/activate
  python scripts/bootstrap_process_module_categories.py

Notes:
- Safe to run multiple times (domain+name unique).
- Scopes default to ["*"] (通用).
"""

from __future__ import annotations

import sys
from pathlib import Path

from typing import Iterable

from sqlalchemy.orm import Session

# Ensure `backend/src` is importable when running as a script.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.database import SessionLocal  # noqa: E402
from src.planner import models  # noqa: E402


DOMAIN = "process_module_category"


def upsert_items(db: Session, names: Iterable[str]) -> tuple[int, int]:
    created = 0
    existed = 0
    for name in names:
        name = str(name).strip()
        if not name:
            continue
        hit = (
            db.query(models.TaxonomyItem)
            .filter(
                models.TaxonomyItem.domain == DOMAIN,
                models.TaxonomyItem.name == name,
                models.TaxonomyItem.is_archived.is_(False),
            )
            .one_or_none()
        )
        if hit:
            existed += 1
            continue
        item = models.TaxonomyItem(
            domain=DOMAIN,
            name=name,
            scopes_json=["*"],
            is_active=True,
            sort_order=0,
            source="local",
            metadata_json={},
        )
        db.add(item)
        created += 1
    return created, existed


def main() -> None:
    # per user confirmed split
    candidates = [
        "内包装/防护模块",
        "外包装模块",
        # other high-level candidates from current process clustering
        "裁剪/分切模块",
        "包边/缝制模块",
        "喷绘/印刷模块",
        "粘合/复合模块",
        "装配/装框模块",
        "清洁/整饰模块",
        "打孔/开槽/倒角模块",
        "质检/返工模块",
    ]

    db = SessionLocal()
    try:
        created, existed = upsert_items(db, candidates)
        db.commit()
        print(f"[ok] domain={DOMAIN} created={created} existed={existed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()


