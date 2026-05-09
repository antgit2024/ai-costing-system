#!/usr/bin/env python3
"""Backfill shipment_lines columns added in migration 0036 from raw_row_json.

Why
---
Migration 0036 added 20 first-class columns mirroring Jackyun
``wms.order.query-info.page.v2`` fields (header + goodsDetail). All
historical rows already store the full upstream payload in
``shipment_lines.raw_row``; this script promotes the relevant subset to
the new columns so the 发货台账 UI / inventory checks can filter on them
without parsing JSON per row.

Excel-imported rows have a different raw shape (Chinese column headers,
no goodsDetail wrapper) — for those rows the script skips silently. They
keep all new columns NULL, which is the correct semantic ("upstream did
not provide this field").

Usage
-----
    PYTHONPATH=. python backend/scripts/backfill_shipment_line_jackyun_fields.py
    PYTHONPATH=. python backend/scripts/backfill_shipment_line_jackyun_fields.py --dry-run
    PYTHONPATH=. python backend/scripts/backfill_shipment_line_jackyun_fields.py --limit 100

Idempotency
-----------
Safe to re-run. By default we only touch rows where AT LEAST ONE of the
new columns is still NULL — already-backfilled rows are skipped so we
avoid pointless UPDATEs and accidental overwrites of any later manual
correction.

Pass ``--force`` to overwrite every row regardless. Useful only after a
mapper bug fix where the raw payload is canonical and DB is stale.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.compat  # noqa: F401, E402
from src.database import SessionLocal, configure_engine  # noqa: E402
from src.planner import models  # noqa: E402

_BEIJING_TZ = timezone(timedelta(hours=8))

# (column_name, jackyun_payload_key, parser_name)
# parser_name is one of: str / int / decimal / dt_beijing / bool01
_HEADER_FIELDS: List[tuple[str, str, str]] = [
    ("order_status_name", "orderStatusName", "str"),
    ("logistic_type_name", "logisticTypeName", "str"),
    # Note upper-camel ``LogisticCode`` per Jackyun v2 spec; some sandboxes
    # have lower-camel — accept both.
    ("logistic_code", "LogisticCode", "str"),
    ("wave_no", "waveNo", "str"),
    ("customer_name", "customerName", "str"),
    ("picker", "picker", "str"),
    ("packer", "packer", "str"),
    ("checker", "checker", "str"),
    ("check_started_at", "checkStartTime", "dt_beijing"),
    ("paid_at", "payTime", "dt_beijing"),
    ("ordered_at", "orderTime", "dt_beijing"),
    ("trade_type", "tradeType", "int"),
    ("trade_type_msg", "tradeTypeMsg", "str"),
]

_DETAIL_FIELDS: List[tuple[str, str, str]] = [
    ("unit_price", "sellPrice", "decimal"),
    ("unit_of_measure", "unit", "str"),
    ("category_name", "cateName", "str"),
    ("goods_name", "goodsName", "str"),
    ("goods_no", "goodsNo", "str"),
    ("is_gift", "isGift", "bool01"),
    ("actual_qty", "actualCount", "decimal"),
]


def _parse_str(v: Any) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip()
    return s or None


def _parse_int(v: Any) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_decimal(v: Any) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def _parse_dt_beijing(v: Any) -> Optional[datetime]:
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=_BEIJING_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _parse_bool01(v: Any) -> Optional[bool]:
    if v in (None, ""):
        return None
    try:
        return bool(int(str(v).strip()))
    except (TypeError, ValueError):
        return bool(v)


_PARSERS = {
    "str": _parse_str,
    "int": _parse_int,
    "decimal": _parse_decimal,
    "dt_beijing": _parse_dt_beijing,
    "bool01": _parse_bool01,
}


def _resolve_value(payload: Dict[str, Any], key: str, kind: str) -> Any:
    parser = _PARSERS[kind]
    raw = payload.get(key)
    # Tolerate the case-variant for LogisticCode.
    if raw in (None, "") and key == "LogisticCode":
        raw = payload.get("logisticCode")
    return parser(raw)


def _row_needs_backfill(line: models.ShipmentLine) -> bool:
    for col, _, _ in _HEADER_FIELDS + _DETAIL_FIELDS:
        if getattr(line, col, None) in (None,):
            return True
    return False


def _apply_to_line(line: models.ShipmentLine, *, force: bool) -> bool:
    raw = getattr(line, "raw_row_json", None) or {}
    if not isinstance(raw, dict):
        return False
    header_payload = raw.get("shipment") or raw.get("payload") or {}
    detail_payload = raw.get("detail") or {}
    if not isinstance(header_payload, dict) or not isinstance(detail_payload, dict):
        return False
    # Excel-imported rows have neither wrapper — bail.
    if not header_payload and not detail_payload:
        return False

    changed = False
    for col, key, kind in _HEADER_FIELDS:
        v = _resolve_value(header_payload, key, kind)
        if v is None:
            continue
        if not force and getattr(line, col, None) not in (None,):
            continue
        setattr(line, col, v)
        changed = True
    for col, key, kind in _DETAIL_FIELDS:
        v = _resolve_value(detail_payload, key, kind)
        if v is None:
            continue
        if not force and getattr(line, col, None) not in (None,):
            continue
        setattr(line, col, v)
        changed = True
    return changed


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill 0036 shipment_line columns from raw_row_json.")
    p.add_argument("--dry-run", action="store_true", help="Print actions, do not commit")
    p.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite columns even if already filled (use after a mapper bug fix)",
    )
    p.add_argument(
        "--source",
        type=str,
        default="jackyun",
        help="Filter by source_system (default: jackyun; pass empty string to process all)",
    )
    return p.parse_args()


def _iter_rows(db, *, source: str) -> Iterable[models.ShipmentLine]:
    q = db.query(models.ShipmentLine).filter(models.ShipmentLine.is_archived.is_(False))
    if source:
        q = q.filter(models.ShipmentLine.source_system == source)
    return q.yield_per(500)


def main() -> int:
    args = parse_args()
    configure_engine()

    scanned = 0
    updated = 0
    skipped_no_payload = 0
    skipped_already_done = 0

    db = SessionLocal()
    try:
        for line in _iter_rows(db, source=args.source.strip()):
            scanned += 1
            if not args.force and not _row_needs_backfill(line):
                skipped_already_done += 1
                continue
            raw = getattr(line, "raw_row_json", None) or {}
            if not isinstance(raw, dict) or not (raw.get("shipment") or raw.get("detail")):
                skipped_no_payload += 1
                continue
            if _apply_to_line(line, force=args.force):
                updated += 1
            if args.limit and scanned >= args.limit:
                break

        if args.dry_run:
            print(
                f"DRY-RUN scanned={scanned} would_update={updated} "
                f"skipped_no_payload={skipped_no_payload} "
                f"skipped_already_done={skipped_already_done}"
            )
            db.rollback()
        else:
            db.commit()
            print(
                f"DONE scanned={scanned} updated={updated} "
                f"skipped_no_payload={skipped_no_payload} "
                f"skipped_already_done={skipped_already_done}"
            )
    finally:
        db.close()

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
