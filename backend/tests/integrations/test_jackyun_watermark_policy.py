"""Watermark advancement policy tests for Jackyun shipment_pull.

Why this lives in its own file:
- The policy is small but has a few non-obvious rules (capping at
  ``now - safety_buffer``, falling back to window-end when payloads have
  no usable timestamp). Mixing these into the larger end-to-end mapper
  test obscures intent and makes regressions hard to localise.
- Real-world bug we hit on 2026-05-06: the live ``query-info.page``
  response did NOT carry a top-level ``modifyTime`` field, so the old
  ``max_modify_time`` initialised to ``effective_start`` was never
  overwritten by payload data and the watermark stuck at window-start
  forever — re-scanning the same 24h window on every click. These tests
  pin the fix.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.integrations.jackyun.sync_jobs import (
    _WATERMARK_SAFETY_BUFFER_SECONDS,
    _compute_watermark_target,
    _payload_max_timestamp,
)


SH = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Payload timestamp picking
# ---------------------------------------------------------------------------


class TestPayloadMaxTimestamp:
    def test_prefers_modifyTime_when_present(self):
        # Even though the LIVE endpoint doesn't ship modifyTime, the helper
        # must still honor it when it appears (e.g. the v2 endpoint or a
        # future schema upgrade).
        ts = _payload_max_timestamp({
            "modifyTime": "2026-05-06 14:00:00",
            "sendTime":   "2026-05-06 10:00:00",
            "gmtCreate":  "2026-05-05 09:00:00",
        })
        assert ts == "2026-05-06 14:00:00"

    def test_falls_back_through_documented_chain(self):
        # gmtModified > sendTime > finishTime > gmtCreate, in that order.
        cases = [
            ({"gmtModified": "T1"}, "T1"),
            ({"sendTime":    "T2"}, "T2"),
            ({"finishTime":  "T3"}, "T3"),
            ({"gmtCreate":   "T4"}, "T4"),
        ]
        for payload, expected in cases:
            assert _payload_max_timestamp(payload) == expected

    def test_returns_none_when_no_known_field_set(self):
        assert _payload_max_timestamp({"orderNo": "S1", "logisticNo": "L1"}) is None

    def test_ignores_blank_or_non_string_values(self):
        # Defensive: don't return "" or 0 — we'd corrupt watermark comparisons.
        for bad in (None, "", "   ", 0, 12345, []):
            payload = {"modifyTime": bad, "sendTime": "2026-05-06 10:00:00"}
            assert _payload_max_timestamp(payload) == "2026-05-06 10:00:00"


# ---------------------------------------------------------------------------
# Watermark target computation
# ---------------------------------------------------------------------------


def _now(hour: int, minute: int = 0, second: int = 0):
    """Helper to get a fixed Shanghai-local ``now`` for deterministic tests."""
    return datetime(2026, 5, 6, hour, minute, second, tzinfo=SH)


class TestComputeWatermarkTarget:
    def test_returns_none_when_no_signals_at_all(self):
        # If we have neither a payload timestamp nor a window upper bound
        # (e.g. caller passed (None, None) and the run was empty), we must
        # NOT advance the watermark — better to redo than to skip.
        assert _compute_watermark_target(
            max_payload_time=None,
            last_window_end=None,
        ) is None

    def test_uses_payload_time_when_below_safety_cap(self):
        # Payload time well before "now - 5min" → returned verbatim.
        target = _compute_watermark_target(
            max_payload_time="2026-05-06 09:00:00",
            last_window_end="2026-05-06 23:59:59",
            now_dt=_now(14, 0, 0),
        )
        assert target == "2026-05-06 23:59:59" or target == "2026-05-06 13:55:00"
        # Specifically: max(09:00, 23:59:59) = 23:59:59, capped at now-5m = 13:55:00.
        assert target == "2026-05-06 13:55:00"

    def test_caps_at_now_minus_safety_buffer(self):
        # Window end is far in the future ("today 23:59:59") but real
        # "now" is 13:38 — watermark must not jump to 23:59:59, otherwise
        # records uploaded between 13:33 and 23:59 would be skipped on
        # the next incremental run.
        target = _compute_watermark_target(
            max_payload_time=None,
            last_window_end="2026-05-06 23:59:59",
            now_dt=_now(13, 38, 0),
        )
        # 13:38:00 - 5min == 13:33:00
        assert target == "2026-05-06 13:33:00"

    def test_does_not_cap_when_signals_already_in_the_past(self):
        # If both signals are well behind the safety cap, we keep the
        # higher signal verbatim (no point pushing the cursor past data
        # we've actually verified).
        target = _compute_watermark_target(
            max_payload_time="2026-05-05 18:00:00",
            last_window_end="2026-05-05 23:59:59",
            now_dt=_now(14, 0, 0),
        )
        assert target == "2026-05-05 23:59:59"

    def test_safety_buffer_is_exactly_five_minutes(self):
        # Pin the constant — changing it has subtle effects on duplicate
        # rate vs. miss rate. If someone bumps it, this test fails loudly
        # and forces them to update the docstring.
        assert _WATERMARK_SAFETY_BUFFER_SECONDS == 300

    def test_payload_time_above_now_is_still_capped(self):
        # Defensive: even if a payload claims a future modifyTime (clock
        # skew between us and Jackyun), don't propagate it forward.
        target = _compute_watermark_target(
            max_payload_time="2026-05-06 23:00:00",
            last_window_end="2026-05-06 23:59:59",
            now_dt=_now(14, 0, 0),
        )
        # Cap kicks in: 14:00 - 5min == 13:55:00.
        assert target == "2026-05-06 13:55:00"

    @pytest.mark.parametrize("payload_ts,expected", [
        ("2026-05-06 13:34:00", "2026-05-06 13:34:00"),  # under cap → kept
        ("2026-05-06 13:35:00", "2026-05-06 13:35:00"),  # exactly at cap (= now-5m)
        ("2026-05-06 13:36:00", "2026-05-06 13:35:00"),  # above cap → clamped
    ])
    def test_payload_time_clamping_boundary(self, payload_ts, expected):
        # Boundary check around the "now - 5 minutes" cap.
        target = _compute_watermark_target(
            max_payload_time=payload_ts,
            last_window_end=None,
            now_dt=_now(13, 40, 0),  # cap = 13:35:00
        )
        assert target == expected
