#!/usr/bin/env python3
"""
Backfill materials.category / materials.model_category from YiDa raw_form_data.

Why:
- Historical sync may have persisted raw YiDa payload to materials.metadata_json.raw_form_data
  but didn't reliably write category columns.
- UI filtering relies on materials.category, so we backfill from the durable raw snapshot.

Usage:
  cd /home/admin/ai-costing-system
  PYTHONPATH=. python backend/scripts/backfill_material_categories.py --dry-run --limit 50
  PYTHONPATH=. python backend/scripts/backfill_material_categories.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401
from src.database import SessionLocal, configure_engine
from src.planner import models


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill Material.category from metadata_json.raw_form_data.")
    p.add_argument("--dry-run", action="store_true", help="Only print actions; do not commit")
    p.add_argument("--limit", type=int, default=None, help="Limit number of rows to update")
    return p.parse_args()


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    # YiDa sometimes stores select/radio as dict/list; stringify best-effort.
    try:
        return str(v)
    except Exception:  # noqa: BLE001
        return ""


def _pick_raw_value(raw: dict, keys: list[str]) -> Optional[str]:
    for k in keys:
        if k not in raw:
            continue
        s = _to_str(raw.get(k)).strip()
        if s:
            return s
    return None


def main() -> None:
    args = parse_args()
    configure_engine()

    # Known production raw field ids (see backend/config/yida_materials.json + docs)
    category_keys = [
        "textField_jacd537",  # 分类（生产常见）
        "radioField_loo2c67p",  # 有些历史表单把分类做成单选
        "category",  # fallback if someone wrote logical key into raw_form_data
    ]
    model_category_keys = [
        "radioField_loo2c67p",  # 模型类目（映射配置里就是它）
        "model_category",
    ]

    updated_cat = 0
    updated_model_cat = 0
    scanned = 0

    with SessionLocal() as db:  # type: ignore[misc]
        q = (
            db.query(models.Material)
            .filter(models.Material.is_archived.is_(False))
            .order_by(models.Material.updated_at.desc())
        )
        for m in q.yield_per(200):
            scanned += 1
            meta = dict(m.metadata_json or {})
            raw = meta.get("raw_form_data") or {}
            if not isinstance(raw, dict):
                raw = {}

            changed = False

            if not (m.category or "").strip():
                v = _pick_raw_value(raw, category_keys)
                if v:
                    if args.dry_run:
                        print(f"[dry-run] set category material_code={m.material_code} category={v}")
                    else:
                        m.category = v
                    updated_cat += 1
                    changed = True

            if not (m.model_category or "").strip():
                v = _pick_raw_value(raw, model_category_keys)
                if v:
                    if args.dry_run:
                        print(f"[dry-run] set model_category material_code={m.material_code} model_category={v}")
                    else:
                        m.model_category = v
                    updated_model_cat += 1
                    changed = True

            if changed and args.limit and (updated_cat + updated_model_cat) >= args.limit:
                break

        if args.dry_run:
            db.rollback()
            print(f"[dry-run] scanned={scanned} updated_category={updated_cat} updated_model_category={updated_model_cat}")
            return

        db.commit()
        print(f"[ok] scanned={scanned} updated_category={updated_cat} updated_model_category={updated_model_cat}")


if __name__ == "__main__":
    main()


