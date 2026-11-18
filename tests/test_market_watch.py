"""Real-time market watcher: decisions, cooldowns, caps, market hours."""
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services import market_watch as mw  # noqa: E402

NOW = datetime(2026, 3, 4, 14, 0)  # Wednesday, market open
CTX = {"atr_h1": 10.0, "atr_h1_median": 9.0, "pdh": 4050.0, "pdl": 3950.0, "pd_date": "2026-03-03"}


@pytest.fixture(autouse=True)
def _clean():
    mw.reset()
    yield
    mw.reset()


def _ticks(start_px, end_px, n=10):
    return [(NOW - timedelta(minutes=14) + timedelta(seconds=90 * i), start_px + (end_px - start_px) * i / (n - 1))
            for i in range(n)]


def keys(alerts):
    return [a[0] for a in alerts]


class TestEvaluate:
    def test_quiet_market(self):
        assert mw.evaluate(NOW, 4001.0, _ticks(4000, 4001), CTX, []) == []

    def test_sharp_move(self):
        a = mw.evaluate(NOW, 4012.0, _ticks(4000, 4012), CTX, [])
        assert keys(a) == ["move_up"] and "1.2×" in a[0][1]
        assert keys(mw.evaluate(NOW, 3988.0, _ticks(4000, 3988), CTX, [])) == ["move_down"]

    def test_volatility_regime(self):
        a = mw.evaluate(NOW, 4001.0, _ticks(4000, 4001), {**CTX, "atr_h1": 20.0}, [])
        assert "volatility" in keys(a)

    def test_levels_once_per_day_key(self):
        a = mw.evaluate(NOW, 4051.0, _ticks(4049, 4051), CTX, [])
        assert keys(a) == ["pdh:2026-03-04"]
        assert keys(mw.evaluate(NOW, 3949.0, _ticks(3951, 3949), CTX, [])) == ["pdl:2026-03-04"]

    def test_old_level_break_is_not_news(self):
        # price has been below PDL for the whole window (e.g. right after a restart)
        assert mw.evaluate(NOW, 3940.0, _ticks(3941, 3940), CTX, []) == []

    def test_news_with_open_trade_warning(self):
        ev = SimpleNamespace(event="CPI m/m", event_time=NOW + timedelta(minutes=20))
        a = mw.evaluate(NOW, 4001.0, _ticks(4000, 4001), CTX, [ev], open_trades=1)
        assert a[0][0].startswith("news:CPI m/m") and "20 daqiqadan" in a[0][1] and "paper savdo" in a[0][1]

    def test_no_atr_no_move_alert(self):
        assert mw.evaluate(NOW, 4050.0, _ticks(4000, 4050), {}, []) == []


class _DB:
    def close(self):
        pass


@pytest.fixture()
def patched(monkeypatch):
    state = {"ctx": dict(CTX), "events": []}
    monkeypatch.setattr(mw, "_context", lambda db, now: state["ctx"])
    monkeypatch.setattr(mw, "_upcoming_events", lambda db, now: state["events"])
    monkeypatch.setattr(mw, "_open_paper_trades", lambda db: 0)
    return state


def _feed(start, end, at=NOW):
    for t, p in _ticks(start, end):
        mw.on_tick("XAUUSD", p, t - NOW + at)


class TestRun:
    def test_cooldown_and_footer(self, patched):
        sent = []
        _feed(4000, 4012)
        assert mw.run(NOW, db_factory=_DB, notify=sent.append)["sent"] == 1
        assert sent[0].endswith(mw.FOOTER)
        _feed(4012, 4025, NOW + timedelta(minutes=20))
        mw.run(NOW + timedelta(minutes=20), db_factory=_DB, notify=sent.append)
        assert len(sent) == 1                      # same direction within 60 min
        _feed(4025, 4040, NOW + timedelta(minutes=70))
        mw.run(NOW + timedelta(minutes=70), db_factory=_DB, notify=sent.append)
        assert len(sent) == 2

    def test_hourly_cap(self, patched):
        sent = []
        patched["events"] = [SimpleNamespace(event=f"E{i}", event_time=NOW + timedelta(minutes=10)) for i in range(10)]
        _feed(4000, 4001)
        mw.run(NOW, db_factory=_DB, notify=sent.append)
        assert len(sent) == mw.MAX_PER_HOUR

    def test_stale_ticks_and_closed_market(self, patched):
        sent = []
        _feed(4000, 4012, NOW - timedelta(minutes=10))
        assert mw.run(NOW, db_factory=_DB, notify=sent.append)["status"] == "no_live_price"
        sat = datetime(2026, 3, 7, 12, 0)
        assert mw.run(sat, db_factory=_DB, notify=sent.append)["status"] == "market_paused"
        assert sent == []

    def test_snapshot(self, patched):
        _feed(4000, 4003)
        mw.run(NOW, db_factory=_DB, notify=lambda m: None)
        snap = mw.snapshot()
        assert snap["price"] == 4003.0 and snap["move_15m"] == 3.0 and snap["atr_h1"] == 10.0


def test_context_from_db(db):
    from models.candle import Candle
    start = datetime(2026, 2, 16)  # Monday
    t, k = start, 0
    while k < 160:
        if t.weekday() < 5:
            px = 4000 + k * 0.1
            db.add(Candle(symbol="XAUUSD", timeframe="60", timestamp=t, open=px, high=px + 5, low=px - 5,
                          close=px, volume=0.0))
            k += 1
        t += timedelta(hours=1)
    db.add(Candle(symbol="XAUUSD", timeframe="1440", timestamp=datetime(2026, 2, 22), open=4000, high=4001,
                  low=3999, close=4000, volume=0.0))  # Sunday session bar — must be skipped
    for d in range(3):
        day = datetime(2026, 2, 23 + d)
        db.add(Candle(symbol="XAUUSD", timeframe="1440", timestamp=day, open=4000, high=4020 + d,
                      low=3980 - d, close=4005, volume=0.0))
    db.commit()
    ctx = mw._context(db, datetime(2026, 2, 25, 12, 0))
    assert ctx["pdh"] == 4021 and ctx["pdl"] == 3979
    assert mw._context(db, datetime(2026, 2, 23, 12, 0)).get("pdh") != 4001  # Monday ignores Sunday bar and ctx["atr_h1"] == pytest.approx(10.0, abs=0.5)
    assert ctx["atr_h1_median"] is not None
