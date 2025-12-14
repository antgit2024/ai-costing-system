#!/usr/bin/env python3
"""YiDa materials sync CLI helper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401
from src.config import settings
from src.database import SessionLocal, configure_engine
from src.planner.services.yida_sync import MaterialSyncService, YidaConfig, YidaFormClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync YiDa materials into the costing database.")
    parser.add_argument("--config", type=str, help="Path to YiDa config JSON (defaults to env)")
    parser.add_argument("--limit", type=int, help="Limit number of rows fetched")
    parser.add_argument("--dry-run", action="store_true", help="Run without committing changes")
    parser.add_argument("--dump", type=str, help="Dump raw YiDa response to the provided path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_engine()  # ensure SessionLocal is initialized with current env

    config_path = Path(args.config) if args.config else Path(settings.yida_materials_config_path)
    config = YidaConfig.from_file(config_path)
    client = YidaFormClient(config)

    dump_path = Path(args.dump) if args.dump else None

    with SessionLocal() as session:  # type: ignore[misc]
        result = run_sync(session, client, limit=args.limit, dry_run=args.dry_run, dump_path=dump_path)
        print(json.dumps(result.dict(), ensure_ascii=False, indent=2))


def run_sync(
    session: Session,
    client: YidaFormClient,
    *,
    limit: int | None,
    dry_run: bool,
    dump_path: Path | None,
):
    service = MaterialSyncService(session, client)
    return service.sync_materials(limit=limit, dry_run=dry_run, dump_path=dump_path)


if __name__ == "__main__":
    main()

