#!/usr/bin/env python3
"""Nightly snapshot sweep — defensive backstop for the bind-time hook.

Why
---
``bind_sku_to_version()`` already triggers ``_trigger_pending_snapshots_for_sku``
on every successful bind, so 95%+ of "newly bound" shipment lines get their
BomSnapshot built immediately. Edge cases that slip through the hook:

  - Bulk bind of one SKU with > 500 historical shipment lines (hook caps at 500
    per SKU; remainder is left for this sweep).
  - Hook silently failed (network blip, transient DB error) — no retry built in.
  - Operator manually cleared ``snapshot_cleared_at`` on legacy lines.
  - Material catalogue updated AFTER bind; original snapshot couldn't compute
    and was rolled back; second attempt would now succeed.
  - Bulk auto-bind paths that bypassed the hook (e.g. early data backfill).

This sweep:

  1. Finds all ShipmentLine rows where:
     - line.sku_code has an active SkuModelVersionMapping (= bound)
     - line has NO BomSnapshot AND NO ShipmentCostingResult (or was cleared)
     - line.completed_at within the last ``--lookback-days`` days
  2. For each, calls ``compute_snapshot_for_shipment_line(overwrite=False)``.
  3. As a side helper, refreshes ``preparse_*`` metadata for SKUs we touched
     (so ``spec_mismatch`` historical false-flags self-heal over time).

Driven by the ``ai-costing-snapshot-sweep.timer`` systemd user timer at 05:30
Asia/Shanghai (after the 02:31 jackyun sync has had ~3h to settle).

Manual invocation (debugging only):
    PYTHONPATH=. .venv/bin/python scripts/cron_snapshot_sweep.py --dry-run
    PYTHONPATH=. .venv/bin/python scripts/cron_snapshot_sweep.py \\
        --lookback-days 30 --limit 1000 --skip-preparse
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401, E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402
from src.planner.services import shipment_import_service  # noqa: E402
from src.planner.services import sku_master_service  # noqa: E402


def _setup_logging() -> logging.Logger:
    log = logging.getLogger("snapshot-sweep")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    log_dir = Path(os.path.expanduser("~/logs/ai-costing"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            str(log_dir / "snapshot-sweep.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=10,
        )
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError as exc:
        log.warning("could not open log file in %s: %s (continuing with stdout only)", log_dir, exc)
    return log


def _refresh_preparse_for_touched_skus(
    db, *, sku_codes: List[str], log: logging.Logger
) -> int:
    """For each SKU we just snapshotted, refresh its SkuMaster preparse cache.
    This naturally resolves stale ``spec_mismatch`` markers (historical
    artifacts from earlier spec_text changes that no longer apply).
    """
    if not sku_codes:
        return 0
    refreshed = 0
    seen: set[str] = set()
    for sku in sku_codes:
        if sku in seen:
            continue
        seen.add(sku)
        try:
            sm = (
                db.query(models.SkuMaster)
                .filter(models.SkuMaster.erp_sku_barcode == sku)
                .first()
            )
            if not sm:
                continue
            spec_text = (sm.spec_text or "").strip()
            if not spec_text:
                continue
            sku_master_service._update_erp_parsed_cache(sm, requested_by="cron:snapshot-sweep")
            flag_modified(sm, "metadata_json")
            refreshed += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("preparse refresh failed for sku=%s: %s", sku, exc)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    if refreshed:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("preparse refresh commit failed: %s", exc)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return 0
    return refreshed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--skip-preparse",
        action="store_true",
        help="Skip the post-sweep preparse refresh (default: run it)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run sweep with limit=0 (no DB writes) to preview the candidate count",
    )
    args = parser.parse_args()

    log = _setup_logging()
    log.info(
        "[start] lookback_days=%d limit=%d preparse=%s dry_run=%s",
        args.lookback_days, args.limit,
        "off" if args.skip_preparse else "on",
        args.dry_run,
    )
    t0 = time.time()

    configure_engine()
    db = SessionLocal()
    try:
        if args.dry_run:
            log.info("[dry-run] sweep skipped; would have used limit=%d", args.limit)
            return 0

        result: Dict[str, Any] = shipment_import_service.sweep_bound_lines_missing_snapshot(
            db,
            lookback_days=args.lookback_days,
            limit=args.limit,
        )
        log.info(
            "[sweep] scanned=%d created=%d recomputed=%d skipped=%d failed=%d duration_ms=%d",
            result.get("scanned", 0),
            result.get("snapshots_created", 0),
            result.get("snapshots_recomputed", 0),
            result.get("skipped_already_done", 0),
            result.get("failed", 0),
            result.get("duration_ms", 0),
        )

        if not args.skip_preparse:
            # Re-derive the touched-SKUs from the sweep result if the function exposes them;
            # otherwise refresh nothing — the sweep return doesn't list SKU codes today,
            # so we go a different route: iterate the lines we MIGHT have touched
            # via a second small query (cap at 500 to keep cron snappy).
            touched_skus: List[str] = []
            try:
                touched_skus = [
                    str(c) for (c,) in (
                        db.query(models.ShipmentLine.sku_code)
                        .join(
                            models.BomSnapshot,
                            models.BomSnapshot.shipment_line_id == models.ShipmentLine.id,
                        )
                        .filter(
                            models.ShipmentLine.is_archived.is_(False),
                            models.BomSnapshot.created_at
                            >= sku_master_service._utcnow().replace(microsecond=0)
                            - __import__("datetime").timedelta(hours=2),
                        )
                        .distinct()
                        .limit(500)
                        .all()
                    )
                    if c
                ]
            except Exception as exc:  # noqa: BLE001
                log.warning("touched-sku discovery failed: %s", exc)

            if touched_skus:
                refreshed = _refresh_preparse_for_touched_skus(
                    db, sku_codes=touched_skus, log=log
                )
                log.info("[preparse] refreshed_skus=%d (from %d touched)", refreshed, len(touched_skus))
            else:
                log.info("[preparse] nothing to refresh (no recent snapshots)")

        elapsed = time.time() - t0
        log.info("[done] elapsed=%.1fs", elapsed)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("[fatal] %s", exc)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
