"""Watchdog transitions, scheduler job tracking and owner notifications."""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services import notify, watchdog  # noqa: E402
from services import twelvedata_service as td  # noqa: E402

WED = datetime(2026, 3, 4, 12, 0)   # market open
SAT = datetime(2026, 3, 7, 12, 0)   # market closed


@pytest.fixture(autouse=True)
def _clean():
    watchdog.reset()
    td._prices.clear()
    yield
    watchdog.reset()
    td._prices.clear()


def _tick(ts):
    td._prices["XAUUSD"] = {"symbol": "XAUUSD", "price": 4000.0,
                            "time": ts.replace(tzinfo=timezone.utc).isoformat()}


class _DB:
    def __init__(self, last):
        self.last = last

    def query(self, *_):
        return self

    def filter(self, *_):
        return self

    def order_by(self, *_):
        return self

    def first(self):
        return (self.last,) if self.last else None

    def close(self):
        pass


def _run(now, last_h1, sent):
    return watchdog.run_checks(now=now, db_factory=lambda: _DB(last_h1), notify=sent.append)


class TestWatchdog:
    def test_alerts_once_then_recovers(self):
        sent = []
        _tick(WED - timedelta(minutes=30))
        _run(WED, WED - timedelta(hours=1), sent)
        _run(WED + timedelta(minutes=2), WED - timedelta(hours=1), sent)
        assert len(sent) == 1 and "Real vaqt narxi" in sent[0]
        _tick(WED + timedelta(minutes=4))
        st = _run(WED + timedelta(minutes=4), WED - timedelta(hours=1), sent)
        assert len(sent) == 2 and sent[1].startswith("✅") and st["ok"]

    def test_stale_candles(self):
        sent = []
        _tick(WED)
        _run(WED, WED - timedelta(hours=5), sent)
        assert any("H1 shamlar" in m for m in sent)

    def test_quiet_when_market_closed(self):
        sent = []
        st = _run(SAT, SAT - timedelta(days=1), sent)
        assert sent == [] and st["market_paused"]

    def test_quiet_right_after_reopen(self):
        sent = []
        sunday_open = datetime(2026, 3, 8, 23, 0)  # opened 22:00
        _run(sunday_open, datetime(2026, 3, 6, 20, 0), sent)
        assert sent == []

    def test_job_failures_escape_markdown(self):
        sent = []
        _tick(WED)
        for _ in range(3):
            watchdog.record_job_result("signal_cycle", False, "boom_x")
        _run(WED, WED - timedelta(hours=1), sent)
        assert len(sent) == 1 and "signal\\_cycle" in sent[0] and "boom\\_x" in sent[0]
        watchdog.record_job_result("signal_cycle", True)
        _run(WED + timedelta(minutes=2), WED - timedelta(hours=1), sent)
        assert sent[-1].startswith("✅")


class TestTracked:
    def test_wrapper_records_and_swallows(self):
        from services.scheduler import _tracked

        def boom():
            raise RuntimeError("x")
        for _ in range(3):
            _tracked("j", boom)()
        assert watchdog.status()["job_consecutive_failures"]["j"] == 3
        _tracked("j", lambda: None)()
        assert watchdog.status()["job_consecutive_failures"]["j"] == 0


class TestPaperMessages:
    base = {"id": 7, "direction": "BUY", "fill_price": 4000.0, "stop_loss": 3990.0, "take_profit": 4025.0,
            "lots": 0.1, "exit_price": None, "exit_reason": None, "r": None, "pnl_usd": None}

    def test_transitions(self):
        msgs = notify.paper_event_messages([
            {**self.base, "prev_status": "PENDING", "status": "OPEN"},
            {**self.base, "prev_status": "OPEN", "status": "CLOSED", "exit_reason": "TP", "exit_price": 4025.0,
             "r": 2.46, "pnl_usd": 246.0},
            {**self.base, "prev_status": "PENDING", "status": "CANCELLED", "exit_reason": "ENTRY_ZONE_MISSED"},
            {**self.base, "prev_status": "OPEN", "status": "OPEN"},
        ])
        assert len(msgs) == 3
        assert "kirildi" in msgs[0] and "Take Profit" in msgs[1] and "+2.46R" in msgs[1]
        assert "kirilmadi" in msgs[2]

    def test_notify_uses_sender(self):
        sent = []
        n = notify.notify_paper_changes({"trades": [{**self.base, "prev_status": "PENDING", "status": "OPEN"}]},
                                        send=sent.append)
        assert n == 1 and len(sent) == 1


def test_daily_summary_text(db):
    text = notify.daily_summary_text(db, now=datetime(2026, 3, 4, 21, 10))
    assert "kunlik hisobot" in text and "Paper hisob" in text and "Tizim" in text
