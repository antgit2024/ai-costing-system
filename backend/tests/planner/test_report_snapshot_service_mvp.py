from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.planner.services import report_snapshot_service


def test_report_snapshot_upsert_handles_decimal_and_datetime(db_session):
    key = report_snapshot_service.snapshot_key("test.decimal", {"range_days": 30, "channel": "x"})
    data = {
        "a": Decimal("12.34"),
        "b": {"t": datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc)},
        "c": [Decimal("0.10"), Decimal("0.20")],
    }
    params = {"range_days": 30, "channel": "x"}

    snap = report_snapshot_service.upsert_snapshot(db_session, key=key, data=data, params=params, operator_id="tester")
    assert snap.key == key

    got = report_snapshot_service.get_snapshot(db_session, key=key)
    assert got is not None
    assert got.key == key
    # values should be JSON-compatible (Decimal converted)
    assert isinstance(got.data.get("a"), (int, float))
    assert isinstance(((got.data.get("b") or {}).get("t")), str)

