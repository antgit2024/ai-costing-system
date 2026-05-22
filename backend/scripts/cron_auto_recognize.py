#!/usr/bin/env python3
"""Nightly auto-recognize cron — driven by systemd user timer.

Usage:
    python -m scripts.cron_auto_recognize [--max-bind N] [--max-preparse N]
                                          [--bind-scan-limit N]

Behavior:
- Runs ``sku_master_service.run_auto_recognize_nightly`` which orchestrates
  ``auto_bind_execute`` (bind unbound SKUs whose shop_spec_code resolves to a
  published model) then ``bulk_save_spec_preparse`` (preparse spec_text for
  bound-but-not-preparsed SKUs).
- Result is persisted to ``integration_sync_runs`` table for UI / journalctl
  inspection (source_system='internal_auto_recognize',
  sync_type='auto_recognize_nightly'). The "夜间自动识别" status card on
  ``/costing/sku-master`` reads from there.
- Returns exit code 0 on success / partial-success (status='success'), 1 on
  hard failure (status='failed' — both steps errored out and zero items
  processed), so the systemd unit's status reflects reality and
  ``journalctl -u auto-recognize-nightly`` surfaces failures.

NOT FOR HUMAN INVOCATION OUTSIDE OF THE TIMER. Operators who want to do an
ad-hoc run should use the UI's 「立刻跑一次」 button (which gives them real-time
result + last-N history), not this script.
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
from src.planner.services import sku_master_service  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cron entry for nightly auto-recognize (auto_bind + preparse).")
    p.add_argument(
        "--max-bind", type=int, default=2000,
        help="Max SKUs to auto-bind in this run (default=2000, hard cap 2000).",
    )
    p.add_argument(
        "--bind-scan-limit", type=int, default=200000,
        help="Max unbound SKUs to scan when looking for bind candidates (default=200000, cap 500000).",
    )
    p.add_argument(
        "--max-preparse", type=int, default=2000,
        help="Max bound SKUs to preparse in this run (default=2000, cap 5000).",
    )
    p.add_argument(
        "--no-skip-same-hash", action="store_true",
        help="Force preparse even if spec_text hash unchanged (default: skip for speed).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    configure_engine()

    db = SessionLocal()
    t0 = time.time()
    log_tag = "cron-auto-recognize"
    try:
        result = sku_master_service.run_auto_recognize_nightly(
            db,
            triggered_by="cron",
            max_bind=int(args.max_bind),
            bind_scan_limit=int(args.bind_scan_limit),
            max_preparse=int(args.max_preparse),
            skip_if_same_hash=not bool(args.no_skip_same_hash),
        )
        elapsed = time.time() - t0
        status = result.get("status") or "unknown"
        bind = result.get("bind") or {}
        preparse = result.get("preparse") or {}
        # One-line summary for `journalctl -u auto-recognize-nightly -n 1`
        print(
            f"[{log_tag}] status={status} "
            f"bind_ok={bind.get('bound_count', 0)} "
            f"bind_skip={bind.get('skipped_already_bound', 0)} "
            f"bind_err={len(bind.get('errors') or [])} "
            f"preparse_ok={preparse.get('saved', 0)} "
            f"preparse_scan={preparse.get('scanned', 0)} "
            f"preparse_skip_hash={preparse.get('skipped_same_hash', 0)} "
            f"preparse_err={len(preparse.get('errors') or [])} "
            f"sync_run_id={result.get('sync_run_id')} "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
        # Exit 1 only on hard failure so monitoring sees a real problem.
        # status='success' includes partial-success runs (bind 0 / preparse N or vice versa).
        return 0 if status == "success" else 1
    except Exception as exc:  # noqa: BLE001
        # Unexpected (DB connection lost, OOM, etc.). Log and exit 1.
        print(f"[{log_tag}] FATAL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
