"""Shadow (forward-only) tracking: storage, de-duplication, one-at-a-time, backtest-parity resolution."""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.candle import Candle  # noqa: E402
from models.shadow import ShadowSignal  # noqa: E402
from services import shadow  # noqa: E402
from strategy import vol_lab  # noqa: E402

START = datetime(2026, 6, 1)  # Monday


def _weekday_hours(start, n, step_h):
    t, out = start, []
    while len(out) < n:
        if t.weekday() < 5:
            out.append(t)
        t += timedelta(hours=step_h)
    return out


@pytest.fixture(scope="module")
def seeded(TestingSessionLocal):
    db = TestingSessionLocal()
    h1 = _weekday_hours(START, 420, 1)
    for k, t in enumerate(h1):
        px = 4000 + 0.01 * k
        db.add(Candle(symbol="XAUUSD", timeframe="60", timestamp=t, open=px, high=px + 2, low=px - 2, close=px, volume=0))
    for k, t in enumerate(_weekday_hours(START - timedelta(days=40), 330, 4)):
        db.add(Candle(symbol="XAUUSD", timeframe="240", timestamp=t, open=4000, high=4004, low=3996, close=4000, volume=0))
    db.commit()
    db.close()
    return h1


@pytest.fixture()
def buy_decider(monkeypatch):
    def build(p, cfg, rc):
        return lambda i: {"action": "BUY", "entry": float(p["close"].iloc[i]), "stop_loss": float(p["close"].iloc[i]) - 10,
                          "take_profit": float(p["close"].iloc[i]) + 25, "regime": "TEST"}
    monkeypatch.setitem(vol_lab.CANDIDATES, "squeeze_trend", ("H1", build))


def test_run_stores_dedups_and_one_at_a_time(db, seeded, buy_decider):
    now = seeded[-1] + timedelta(hours=1, minutes=2)
    r = shadow.run(db, now=now, fetch=False)
    assert r["status"] == "ok" and r["strategies"]["squeeze_trend"]["action"] == "BUY"
    row = db.query(ShadowSignal).filter_by(id=r["strategies"]["squeeze_trend"]["id"]).one()
    assert row.bar_close == seeded[-1] + timedelta(hours=1) and row.status == "open"
    again = shadow.run(db, now=now, fetch=False)["strategies"]["squeeze_trend"]
    assert "skipped" in again or again.get("duplicate")


def test_stale_data_is_not_decided(db, seeded, buy_decider):
    r = shadow.run(db, now=seeded[-1] + timedelta(hours=5), fetch=False)
    assert r["status"] == "stale_data"


def test_resolve_with_backtest_rules_then_performance(db, seeded):
    row = db.query(ShadowSignal).filter_by(strategy="squeeze_trend", status="open").one()
    t0, e = row.bar_close, row.entry
    # next bar opens at entry (fill), the one after runs through TP
    db.add(Candle(symbol="XAUUSD", timeframe="60", timestamp=t0, open=e, high=e + 1, low=e - 1, close=e, volume=0))
    db.add(Candle(symbol="XAUUSD", timeframe="60", timestamp=t0 + timedelta(hours=1), open=e, high=e + 30, low=e - 1,
                  close=e + 26, volume=0))
    db.commit()
    r = shadow.resolve(db, now=t0 + timedelta(hours=3))
    assert r["resolved"] == 1
    db.refresh(row)
    assert row.status == "closed" and row.outcome == "TP" and 2.3 < row.outcome_r < 2.5
    perf = shadow.performance(db, "squeeze_trend")
    assert perf["forward"]["trades"] == 1 and perf["acceptance"]["progress"] == "1/30"
    assert perf["acceptance"]["passed"] is False


def test_open_beyond_sl_is_not_filled(db):
    t0 = datetime(2026, 7, 6, 10)
    row = ShadowSignal(strategy="squeeze_trend", symbol="XAUUSD", timeframe="60", signal_type="BUY", bar_close=t0,
                       entry=4100.0, stop_loss=4090.0, take_profit=4125.0, status="open")
    db.add(row)
    db.add(Candle(symbol="XAUUSD", timeframe="60", timestamp=t0, open=4085, high=4086, low=4080, close=4082, volume=0))
    db.commit()
    shadow.resolve(db, now=t0 + timedelta(hours=2))
    db.refresh(row)
    assert row.status == "not_filled" and row.outcome == "OPENED_BEYOND_LEVELS" and row.outcome_r is None
