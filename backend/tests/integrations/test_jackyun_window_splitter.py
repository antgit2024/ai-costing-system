"""Pin-down tests for the 24h-window splitter inside ``sync_jobs``.

Why this matters:
- Jackyun's ``wms.order.query-info.page`` rejects any
  ``startModifyTime ~ endModifyTime`` window wider than 24 hours
  (sub-code ``0050030002``).
- Callers (cron jobs, manual triggers, watermark-resume) must NOT have to
  think about this — sync_jobs has to chop wide ranges into <=24h slices
  and call upstream once per slice.
- Off-by-one errors here either drop records (gap) or double-fetch them
  (overlap). Both are bad, so the boundaries are nailed down explicitly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.integrations.jackyun.sync_jobs import (
    _MAX_WINDOW_SECONDS,
    _iter_24h_windows,
)
from src.integrations.jackyun import sync_jobs as jackyun_sync_jobs
from src.integrations.base.client import ClientResponse
from src.integrations.jackyun import client as jackyun_client_mod
from src.planner import models


SH = timezone(timedelta(hours=8))


def _windows(start, end):
    return list(_iter_24h_windows(start, end))


class TestIter24hWindows:
    def test_no_bounds_yields_single_unbounded_window(self):
        # When the caller has neither a start nor a watermark, we let the
        # upstream apply its own defaults — so the splitter passes through
        # exactly one (None, None) tuple, not zero windows (which would
        # silently skip the run).
        ws = _windows(None, None)
        assert ws == [(None, None)]

    def test_window_within_24h_is_passed_through_untouched(self):
        ws = _windows("2026-05-06 00:00:00", "2026-05-06 23:59:59")
        assert ws == [("2026-05-06 00:00:00", "2026-05-06 23:59:59")]

    def test_window_exactly_at_24h_minus_1s_is_one_slice(self):
        # _MAX_WINDOW_SECONDS == 24h-1s; if start+max == end, no split.
        start_dt = datetime(2026, 5, 1, 0, 0, 0, tzinfo=SH)
        end_dt = start_dt + timedelta(seconds=_MAX_WINDOW_SECONDS)
        ws = _windows(
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        )
        assert len(ws) == 1
        assert ws[0] == (
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def test_two_day_range_splits_into_two_windows_with_no_gap_no_overlap(self):
        ws = _windows("2026-05-01 00:00:00", "2026-05-02 23:59:59")
        # Expect two slices that together cover the whole range with neither
        # gaps nor overlaps. The splitter advances by ``max+1s`` between
        # slices, so the second slice's start MUST be exactly 1s after the
        # first slice's end.
        assert len(ws) == 2
        first_start, first_end = ws[0]
        second_start, second_end = ws[1]

        first_start_dt = datetime.strptime(first_start, "%Y-%m-%d %H:%M:%S")
        first_end_dt = datetime.strptime(first_end, "%Y-%m-%d %H:%M:%S")
        second_start_dt = datetime.strptime(second_start, "%Y-%m-%d %H:%M:%S")
        second_end_dt = datetime.strptime(second_end, "%Y-%m-%d %H:%M:%S")

        assert first_start_dt == datetime(2026, 5, 1, 0, 0, 0)
        assert second_end_dt == datetime(2026, 5, 2, 23, 59, 59)
        # Each slice within upstream's hard cap.
        assert (first_end_dt - first_start_dt).total_seconds() <= _MAX_WINDOW_SECONDS
        assert (second_end_dt - second_start_dt).total_seconds() <= _MAX_WINDOW_SECONDS
        # Continuous: second.start == first.end + 1s. No overlap, no gap.
        assert second_start_dt == first_end_dt + timedelta(seconds=1)

    def test_seven_day_range_splits_into_seven_or_eight_windows(self):
        ws = _windows("2026-04-30 00:00:00", "2026-05-06 23:59:59")
        # 7 calendar days — splitter uses 23:59:59 windows + 1s step, so we
        # expect 7 slices when the range fits cleanly, never more than 8.
        assert 7 <= len(ws) <= 8
        # Final slice must end at the requested upper bound.
        assert ws[-1][1] == "2026-05-06 23:59:59"
        # First slice must start at the requested lower bound.
        assert ws[0][0] == "2026-04-30 00:00:00"
        # Strictly monotonic, no overlaps.
        for prev, nxt in zip(ws, ws[1:]):
            prev_end = datetime.strptime(prev[1], "%Y-%m-%d %H:%M:%S")
            nxt_start = datetime.strptime(nxt[0], "%Y-%m-%d %H:%M:%S")
            assert nxt_start > prev_end, f"overlap detected: {prev} → {nxt}"

    def test_start_only_extends_forward_until_today_end(self):
        # When we have a watermark (start) but no explicit end, the splitter
        # should extend forward up to today-23:59:59 in Shanghai time. We
        # don't pin the exact count (it depends on "today") but we DO pin
        # the boundary semantics so the run never overshoots the present.
        ws = _windows("2026-05-06 00:00:00", None)
        assert ws, "splitter must emit at least one window when start is set"
        first_start = ws[0][0]
        last_end_dt = datetime.strptime(ws[-1][1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH)
        today_eod = datetime.now(SH).replace(hour=23, minute=59, second=59, microsecond=0)
        assert first_start == "2026-05-06 00:00:00"
        # Last slice should land at today-23:59:59 (or before, never after).
        assert last_end_dt <= today_eod

    def test_end_before_start_yields_no_windows(self):
        # Defensive: if the caller passes a reversed range, we should NOT
        # silently call upstream with a bogus window — emit zero windows
        # and let the run finish as a no-op.
        ws = _windows("2026-05-06 12:00:00", "2026-05-01 00:00:00")
        assert ws == []

    @pytest.mark.parametrize("start,end", [
        ("2026-05-01 00:00:00", "2026-05-03 23:59:59"),  # 3 days
        ("2026-05-01 06:00:00", "2026-05-04 18:00:00"),  # 3.5 days, off-grid
        ("2026-05-01 00:00:00", "2026-05-08 12:00:00"),  # 7.5 days
    ])
    def test_every_emitted_window_respects_24h_cap(self, start, end):
        for win_start, win_end in _windows(start, end):
            s = datetime.strptime(win_start, "%Y-%m-%d %H:%M:%S")
            e = datetime.strptime(win_end, "%Y-%m-%d %H:%M:%S")
            span = (e - s).total_seconds()
            assert 0 <= span <= _MAX_WINDOW_SECONDS, (
                f"window {win_start} ~ {win_end} spans {span}s, "
                f"violating Jackyun's 24h cap"
            )


class TestSyncShipmentsStartFallback:
    """Sync_jobs MUST never let a bare request (no start, no watermark) reach
    the upstream — it would always be rejected with sub-code ``0050030002``.

    Defense in depth: even if the HTTP route forgot its today-default, or a
    cron job / CLI calls into the function directly, the resolver inside
    sync_shipments has to substitute "today 00:00 Shanghai" so we never
    issue a bare request to Jackyun.
    """

    def _stub_call_capturing(self, monkeypatch):
        captured = []

        def fake(self, api_method, biz_content, *, sync_run_id=None, db=None):
            captured.append(dict(biz_content))
            return ClientResponse(
                success=True, biz_code="200", biz_sub_code=None, message="ok",
                data=[],
                raw={"code": 200, "result": {"contextId": "ctx", "data": [],
                                              "pageInfo": {"total": 0}}},
                http_status=200, context_id="ctx",
            )

        monkeypatch.setattr(jackyun_client_mod.JackyunClient, "call", fake)
        return captured

    def _fake_client(self):
        c = jackyun_client_mod.JackyunClient.__new__(jackyun_client_mod.JackyunClient)
        c.source_system = "jackyun"
        return c

    def test_no_start_no_watermark_falls_back_to_today_not_a_bare_request(
        self, db_session, monkeypatch
    ):
        # Precondition: empty watermark table.
        assert (
            db_session.query(models.IntegrationSyncWatermark)
            .filter_by(source_system="jackyun", sync_type=jackyun_sync_jobs.SHIPMENT_SYNC_TYPE)
            .count() == 0
        )

        captured = self._stub_call_capturing(monkeypatch)

        run_id = jackyun_sync_jobs.sync_shipments(
            db_session, page_size=10, client=self._fake_client(),
            triggered_by="defense-in-depth", use_watermark=True,
        )
        db_session.commit()

        assert captured, (
            "sync_shipments must reach upstream — if it short-circuits with "
            "'no start' the upstream will be left in an unknown state."
        )
        first = captured[0]
        # The critical assertion: a startModifyTime MUST be present, formatted
        # as Jackyun expects, otherwise the live gateway will reject the call
        # with sub-code 0050030002.
        assert "startModifyTime" in first, (
            f"upstream call missing startModifyTime — biz body was {first}"
        )
        assert first["startModifyTime"].endswith(" 00:00:00")
        # Run should be recorded as succeeded (empty result is still success).
        run = (
            db_session.query(models.IntegrationSyncRun)
            .filter_by(id=run_id).one()
        )
        assert run.status == "succeeded"
        # request_params_json should expose how the start was resolved for ops.
        assert "default-today" in (run.request_params_json or {}).get("start_resolution", "")
