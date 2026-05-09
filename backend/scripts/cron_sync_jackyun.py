#!/usr/bin/env python3
"""Jackyun nightly shipment sync — driven by systemd user timer.

Usage:
    python -m scripts.cron_sync_jackyun [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                        [--page-size N] [--no-watermark]

Behavior:
- Default mode (no args): increments from the last successful watermark and
  pulls everything new since then. This is the mode the systemd timer uses
  (so the timer is safe to run multiple times a day if needed; the
  watermark prevents re-pulling).
- Returns exit code 0 on success, 1 on hard failure (network / auth) so
  the systemd unit's status reflects reality and `journalctl -u` can
  surface failures.
- Logs a single one-line summary at the end so `journalctl -u
  jackyun-shipment-sync.service -n 1` shows what happened.

NOT FOR HUMAN INVOCATION OUTSIDE OF THE TIMER. Operators who want to do an
ad-hoc sync should use the UI's "立即同步" button (which gives them
real-time progress and dead-letter visibility), not this script.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401,E402
from src.database import SessionLocal, configure_engine  # noqa: E402
from src.integrations.jackyun import sync_jobs as jackyun_sync_jobs  # noqa: E402
from src.planner import models  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cron entry for Jackyun shipment incremental sync.")
    p.add_argument(
        "--start", type=str, default=None,
        help="Override start_modify_time (e.g. '2026-05-07 00:00:00'). "
             "Default = use watermark.",
    )
    p.add_argument(
        "--end", type=str, default=None,
        help="Override end_modify_time. Default = upstream pulls until 'now'.",
    )
    p.add_argument(
        "--page-size", type=int, default=50,
        help="Page size for upstream API (default=50, the upstream cap).",
    )
    p.add_argument(
        "--no-watermark", action="store_true",
        help="Disable watermark resume (force --start to be respected exactly).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    configure_engine()

    db = SessionLocal()
    t0 = time.time()
    sync_run_id: str | None = None
    try:
        sync_run_id = jackyun_sync_jobs.sync_shipments(
            db,
            start_modify_time=args.start,
            end_modify_time=args.end,
            page_size=args.page_size,
            triggered_by="cron-nightly",
            use_watermark=not args.no_watermark,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = int(time.time() - t0)
        print(
            f"[cron-jackyun-sync] FAILED after {elapsed}s: {exc!r}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass

    elapsed = int(time.time() - t0)

    # Re-open a fresh session to read the run row + counts after sync_shipments
    # has committed its IntegrationSyncRun.
    db2 = SessionLocal()
    try:
        run = db2.get(models.IntegrationSyncRun, sync_run_id) if sync_run_id else None
        if run is None:
            print(
                f"[cron-jackyun-sync] OK (run_id={sync_run_id}) but row not found - elapsed={elapsed}s",
                flush=True,
            )
            return 0
        status = getattr(run, "status", "?")
        total = int(getattr(run, "total_rows", 0) or 0)
        inserted = int(getattr(run, "inserted_rows", 0) or 0)
        updated = int(getattr(run, "updated_rows", 0) or 0)
        skipped = int(getattr(run, "skipped_rows", 0) or 0)
        errors = int(getattr(run, "error_rows", 0) or 0)
        cursor_end = getattr(run, "cursor_end", None) or "-"
        print(
            f"[cron-jackyun-sync] {status} run_id={sync_run_id} total={total}"
            f" inserted={inserted} updated={updated} skipped={skipped} errors={errors}"
            f" cursor_end={cursor_end} elapsed={elapsed}s",
            flush=True,
        )
        # Treat partial-success runs (status='partial') as success so the
        # timer doesn't flap; dead-letter rows are visible in the UI.
        return 0 if status in ("succeeded", "partial") else 1
    finally:
        try:
            db2.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
