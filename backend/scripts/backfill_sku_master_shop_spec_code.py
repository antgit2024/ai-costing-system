#!/usr/bin/env python3
"""Backfill sku_master.metadata_json.shop_spec_code from existing shipment_lines.

Why
---
The auto-bind engine (`sku_master_service.auto_bind_preview`) treats
"商家编码"（merchant SKU, 吉客云 tradeGoodsno）as the P0 anchor — when present
it deterministically locks a SKU to its model/variant. However, before
this script existed:

- The 吉客云 mapper wrote tradeGoodsno only to ``ShipmentLine.product_link_id``,
  never to ``line.metadata.shop_spec_code``.
- ``ensure_from_shipment`` only persisted shop_spec_code into a nested
  ``shipment_backfill`` sub-dict, while the auto-bind engine reads from
  the top-level ``metadata.shop_spec_code``.

Result: ``sku_master.metadata.shop_spec_code`` was effectively always NULL
for jackyun-sourced SKUs, so auto-bind degraded to spec-text keyword
matching.

What this does
--------------
For every ``sku_master`` row whose ``metadata_json.shop_spec_code`` is
NULL/empty, look up the latest non-empty ``shipment_lines`` row for the
same ``erp_sku_barcode`` and copy the merchant-SKU value (extracted with
the same priority used at runtime: metadata > product_link_id > raw_row).

Conservative defaults
---------------------
- Only fills NULL/empty cells. Any pre-existing value is left intact.
- Does NOT touch SKU bindings; it only seeds the anchor so that the next
  ``auto_bind_preview`` run can use it.
- Idempotent — safe to re-run.

Usage
-----
    PYTHONPATH=. python backend/scripts/backfill_sku_master_shop_spec_code.py --dry-run
    PYTHONPATH=. python backend/scripts/backfill_sku_master_shop_spec_code.py
    PYTHONPATH=. python backend/scripts/backfill_sku_master_shop_spec_code.py --limit 500
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401, E402
from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402
from src.planner.services.shipment_import_service import (  # noqa: E402
    _extract_shop_spec_code_from_line,
)


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()


def _has_top_level_shop_spec(meta: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(meta, dict):
        return False
    v = meta.get("shop_spec_code")
    return bool(str(v).strip()) if v is not None else False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only report counts; don't write")
    parser.add_argument("--limit", type=int, default=0, help="Cap number of SKUs to process (0=all)")
    parser.add_argument(
        "--barcode",
        type=str,
        default=None,
        help="Restrict to a single SKU barcode (debugging)",
    )
    args = parser.parse_args()

    configure_engine()
    db: Session = SessionLocal()

    try:
        q = db.query(models.SkuMaster)
        if args.barcode:
            q = q.filter(models.SkuMaster.erp_sku_barcode == args.barcode.strip())

        sku_rows = q.order_by(models.SkuMaster.id.asc()).all()
        total_sku = len(sku_rows)
        print(f"[scan] sku_master rows considered: {total_sku}")

        skipped_already_filled = 0
        skipped_no_barcode = 0
        skipped_no_line = 0
        skipped_no_value = 0
        to_update: list[tuple[models.SkuMaster, str]] = []

        for sm in sku_rows:
            barcode = (sm.erp_sku_barcode or "").strip()
            if not barcode:
                skipped_no_barcode += 1
                continue
            meta = dict(sm.metadata_json or {})
            if _has_top_level_shop_spec(meta):
                skipped_already_filled += 1
                continue

            # Latest active line for this barcode (by completed_at desc, fallback created_at).
            line = (
                db.query(models.ShipmentLine)
                .filter(
                    models.ShipmentLine.sku_code == barcode,
                    models.ShipmentLine.is_archived.is_(False),
                )
                .order_by(
                    func.coalesce(
                        models.ShipmentLine.completed_at,
                        models.ShipmentLine.created_at,
                    ).desc()
                )
                .first()
            )
            if line is None:
                skipped_no_line += 1
                continue

            shop_code = _extract_shop_spec_code_from_line(line)
            if not shop_code:
                skipped_no_value += 1
                continue

            to_update.append((sm, shop_code))
            if args.limit and len(to_update) >= args.limit:
                break

        print(f"[scan] already_filled={skipped_already_filled}")
        print(f"[scan] no_barcode={skipped_no_barcode}")
        print(f"[scan] no_shipment_line={skipped_no_line}")
        print(f"[scan] line_present_but_no_value={skipped_no_value}")
        print(f"[scan] candidates_to_backfill={len(to_update)}")

        if args.dry_run:
            for sm, code in to_update[:30]:
                print(f"  would set {sm.erp_sku_barcode!r:>24} -> shop_spec_code={code!r}")
            if len(to_update) > 30:
                print(f"  ... ({len(to_update) - 30} more)")
            print("[dry-run] no changes written")
            return 0

        now_iso = _utcnow_iso()
        written = 0
        for sm, code in to_update:
            meta = dict(sm.metadata_json or {})
            meta["shop_spec_code"] = code
            meta["shop_spec_code_source"] = "backfill_from_shipment"
            meta["shop_spec_code_seen_at"] = now_iso
            sm.metadata_json = meta
            flag_modified(sm, "metadata_json")
            written += 1
            if written % 200 == 0:
                db.commit()
                print(f"[commit] {written}/{len(to_update)} written so far")

        db.commit()
        print(f"[done] backfilled shop_spec_code on {written} sku_master rows")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
