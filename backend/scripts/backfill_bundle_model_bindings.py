#!/usr/bin/env python3
"""
Backfill: bundle template binding -> bundle model version binding (single exit).

Why:
- Historical data may have sku_master.metadata_json.bundle_* filled, but no active sku_model_version_mapping.
- This script ensures such SKUs are also bound to the corresponding bundle model version (published).

Usage:
  PYTHONPATH=. python backend/scripts/backfill_bundle_model_bindings.py --dry-run
  PYTHONPATH=. python backend/scripts/backfill_bundle_model_bindings.py --limit 500
  PYTHONPATH=. python backend/scripts/backfill_bundle_model_bindings.py --rebind
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401
from src.database import SessionLocal, configure_engine
from src.planner import models
from src.planner.services import bundle_template_service, product_model_service


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill bundle binding -> bundle model version binding.")
    p.add_argument("--dry-run", action="store_true", help="Only print actions; do not commit")
    p.add_argument("--limit", type=int, default=500, help="Max sku_master rows to scan (ordered by updated_at desc)")
    p.add_argument("--rebind", action="store_true", help="Allow rebinding even if SKU already has an active binding")
    p.add_argument("--operator", type=str, default="system", help="operator id for audit fields")
    return p.parse_args()


def _is_non_empty(v) -> bool:
    return str(v or "").strip() != ""


def _get_meta(row: models.SkuMaster) -> dict:
    meta = getattr(row, "metadata_json", None) or {}
    return meta if isinstance(meta, dict) else {}


def backfill(db: Session, *, limit: int, dry_run: bool, allow_rebind: bool, operator: str) -> None:
    scan = max(min(int(limit or 500), 20000), 1)
    rows = (
        db.query(models.SkuMaster)
        .filter(models.SkuMaster.is_archived.is_(False))
        .order_by(models.SkuMaster.updated_at.desc())
        .limit(scan)
        .all()
    )
    candidates = []
    for r in rows:
        meta = _get_meta(r)
        if not _is_non_empty(meta.get("bundle_template_id")):
            continue
        if not _is_non_empty(meta.get("bundle_preset_selector")):
            continue
        candidates.append(r)

    print(f"[scan] scanned={len(rows)} candidates_with_bundle={len(candidates)}")

    done = 0
    skipped_no_published = 0
    skipped_no_sku = 0
    skipped_already_bound = 0
    errors = 0

    for r in candidates:
        sku = str(r.erp_sku_barcode or "").strip()
        if not sku:
            skipped_no_sku += 1
            continue

        meta = _get_meta(r)
        tid = str(meta.get("bundle_template_id") or "").strip()
        sel = str(meta.get("bundle_preset_selector") or "").strip().upper()
        if not tid or not sel:
            continue

        v = bundle_template_service.get_latest_published_version(db, template_id=tid)
        if not v:
            skipped_no_published += 1
            continue

        try:
            bundle_mv = product_model_service.ensure_bundle_model_version(
                db,
                template_version=v,
                preset_selector=sel,
                requested_by=operator,
            )
            active = product_model_service.get_active_sku_binding(db, sku)
            if active and not allow_rebind:
                skipped_already_bound += 1
                continue
            if active and str(active.model_version_id) == str(bundle_mv.id) and allow_rebind:
                skipped_already_bound += 1
                continue

            if dry_run:
                print(
                    f"[dry-run] bind sku={sku} -> bundle_model_version_id={bundle_mv.id} "
                    f"(template_id={tid} selector={sel} template_version={v.version_label})"
                )
                done += 1
                continue

            product_model_service.bind_sku_to_version(
                db,
                sku_code=sku,
                version_id=bundle_mv.id,
                source_system="bundle_backfill",
                metadata={
                    "requested_by": operator,
                    "sku_master_id": r.id,
                    "binding_method": "bundle_backfill_rebind" if allow_rebind else "bundle_backfill",
                    "skip_prefix_check": True,
                    "bundle_template_id": tid,
                    "bundle_template_code": v.template_code,
                    "bundle_template_version_id": v.id,
                    "bundle_template_version_label": v.version_label,
                    "bundle_preset_selector": sel,
                },
            )
            # Keep sku_master metadata aligned for UI/debugging
            meta2 = dict(meta)
            meta2["bundle_template_version_id"] = v.id
            meta2["bundle_template_version_label"] = v.version_label
            meta2["bundle_model_version_id"] = bundle_mv.id
            r.metadata_json = meta2
            db.add(r)
            db.commit()
            done += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[error] sku={sku} template_id={tid} selector={sel} err={exc}")

    print(
        "[result] "
        f"updated={done} skipped_no_published={skipped_no_published} skipped_no_sku={skipped_no_sku} "
        f"skipped_already_bound={skipped_already_bound} errors={errors}"
    )


def main() -> None:
    args = parse_args()
    configure_engine()
    with SessionLocal() as db:  # type: ignore[misc]
        backfill(
            db,
            limit=args.limit,
            dry_run=bool(args.dry_run),
            allow_rebind=bool(args.rebind),
            operator=str(args.operator or "system"),
        )


if __name__ == "__main__":
    main()

