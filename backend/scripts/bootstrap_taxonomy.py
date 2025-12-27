#!/usr/bin/env python3
"""
Bootstrap taxonomy_items from existing DB values (one-time migration helper).

Usage:
  PYTHONPATH=. python backend/scripts/bootstrap_taxonomy.py --dry-run
  PYTHONPATH=. python backend/scripts/bootstrap_taxonomy.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401
from src.database import SessionLocal, configure_engine
from src.planner import models


UNIVERSAL_SCOPE = ["*"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bootstrap taxonomy from existing category fields.")
    p.add_argument("--dry-run", action="store_true", help="Only print actions; do not commit")
    return p.parse_args()


def _distinct_non_empty(values: Iterable[str | None]) -> Set[str]:
    out: Set[str] = set()
    for v in values:
        s = str(v or "").strip()
        if s:
            out.add(s)
    return out


def _ensure_items(
    db: Session,
    *,
    domain: str,
    names: Set[str],
    dry_run: bool,
) -> Tuple[int, int]:
    """Return (created, skipped_existing)."""
    created = 0
    skipped = 0
    existing = {
        n
        for (n,) in db.query(models.TaxonomyItem.name)
        .filter(models.TaxonomyItem.domain == domain, models.TaxonomyItem.is_archived.is_(False))
        .all()
    }
    to_create = sorted(names - existing)
    for name in to_create:
        if dry_run:
            print(f"[dry-run] create taxonomy_item domain={domain} name={name}")
            created += 1
            continue
        db.add(
            models.TaxonomyItem(
                domain=domain,
                name=name,
                scopes_json=list(UNIVERSAL_SCOPE),
                is_active=True,
                sort_order=0,
                source="import",
                metadata_json={"bootstrap": True},
                is_archived=False,
            )
        )
        created += 1
    skipped = len(names & existing)
    return created, skipped


def main() -> None:
    args = parse_args()
    configure_engine()

    with SessionLocal() as db:  # type: ignore[misc]
        # Real materials
        # NOTE: Current production data keeps category in metadata_json.raw_form_data['textField_jacd537']
        # (materials.category column may be empty). Bootstrap both sources.
        material_categories = _distinct_non_empty(
            v for (v,) in db.query(models.Material.category).filter(models.Material.is_archived.is_(False)).all()
        )
        # best-effort: also bootstrap from metadata->raw_form_data->>'textField_jacd537'
        # (PostgreSQL JSON operators)
        try:
            rows = db.execute(
                text(
                    """
                    select distinct trim(coalesce((metadata->'raw_form_data'->>'textField_jacd537'), '')) as c
                    from materials
                    where is_archived = false
                    """
                )
            ).fetchall()
            material_categories |= _distinct_non_empty(r[0] for r in rows)
        except Exception:
            # keep compatible with non-Postgres backends
            pass
        # Virtual materials
        virtual_categories = _distinct_non_empty(
            v
            for (v,) in db.query(models.VirtualMaterial.category).filter(models.VirtualMaterial.is_archived.is_(False)).all()
        )
        # Processes / modules
        process_categories = _distinct_non_empty(
            v for (v,) in db.query(models.Process.category).filter(models.Process.is_archived.is_(False)).all()
        )
        module_categories = _distinct_non_empty(
            v for (v,) in db.query(models.ProcessModule.category).filter(models.ProcessModule.is_archived.is_(False)).all()
        )
        # Teams (班组)
        process_teams = _distinct_non_empty(
            v for (v,) in db.query(models.Process.team_name).filter(models.Process.is_archived.is_(False)).all()
        )
        module_step_teams = _distinct_non_empty(
            v
            for (v,) in db.query(models.ProcessModuleStep.team_name)
            .filter(models.ProcessModuleStep.is_archived.is_(False))
            .all()
        )
        teams = process_teams | module_step_teams
        # Product models
        model_categories = _distinct_non_empty(
            v for (v,) in db.query(models.ProductModel.category).filter(models.ProductModel.is_archived.is_(False)).all()
        )

        plan = [
            ("material_category", material_categories),
            ("virtual_material_category", virtual_categories),
            ("process_category", process_categories),
            ("process_module_category", module_categories),
            ("team", teams),
            ("product_model_category", model_categories),
        ]

        total_created = 0
        for domain, names in plan:
            c, s = _ensure_items(db, domain=domain, names=names, dry_run=args.dry_run)
            print(f"[{domain}] existing={s} create={c} total_source={len(names)}")
            total_created += c

        if args.dry_run:
            print(f"[dry-run] total create={total_created}")
            db.rollback()
            return

        db.commit()
        print(f"[done] total created={total_created}")


if __name__ == "__main__":
    main()


