"""Broker cost feed: auth, ingestion, swap conversion, calibration report."""
import calendar
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services import broker_costs as bc  # noqa: E402

TOKEN = "t" * 32


def _q(ts, spread=0.25, **kw):
    base = {"broker": "Test Broker Ltd", "server": "Test-Demo", "is_demo": True, "symbol": "XAUUSD",
            "broker_symbol": "GOLD", "ts": calendar.timegm(ts.timetuple()) if isinstance(ts, datetime) else ts,
            "bid": 4000.0, "ask": 4000.0 + spread, "spread_min": spread * 0.8, "spread_avg": spread,
            "spread_max": spread * 1.5, "ticks": 60, "point": 0.01, "digits": 2, "contract_size": 100.0,
            "swap_long": -45.0, "swap_short": 20.0, "swap_type": 0, "swap_3day": 3, "stop_level": 0.0}
    base.update(kw)
    return base


@pytest.fixture()
def token(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "BROKER_FEED_TOKEN", TOKEN)
    return TOKEN


class TestEndpoint:
    def test_disabled_without_token_configured(self, client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "BROKER_FEED_TOKEN", "")
        r = client.post("/api/v1/broker/quotes", json={"quotes": []}, headers={"X-Feed-Token": "x"})
        assert r.status_code == 503

    def test_rejects_bad_token(self, client, token):
        r = client.post("/api/v1/broker/quotes", json={"quotes": [_q(datetime(2026, 3, 4, 10))]},
                        headers={"X-Feed-Token": "wrong"})
        assert r.status_code == 401

    def test_ingest_and_dedup(self, db, token):
        # called directly: the in-memory SQLite test DB is per-thread, the TestClient app runs in another thread
        from routers.broker import QuotesIn, post_quotes
        ts = datetime(2026, 3, 4, 10, 0)
        body = QuotesIn(quotes=[_q(ts), _q(ts + timedelta(minutes=1)), _q(ts, bid=-1)])
        assert post_quotes(body, x_feed_token=TOKEN, db=db) == {"stored": 2, "duplicates": 0, "rejected": 1}
        assert post_quotes(QuotesIn(quotes=[_q(ts)]), x_feed_token=TOKEN, db=db)["duplicates"] == 1


class TestParsing:
    def test_timestamp_formats(self):
        want = datetime(2026, 3, 4, 10, 5)
        assert bc._parse_ts(calendar.timegm(datetime(2026, 3, 4, 10, 5, 42).timetuple())) == want
        assert bc._parse_ts("2026.03.04 10:05") == want
        assert bc._parse_ts("2026-03-04T10:05:59Z") == want

    @pytest.mark.parametrize("value,stype,expected", [
        (-45.0, 0, -0.45),          # points × 0.01
        (-30.0, 1, -0.30),          # USD per lot / 100 oz
        (-2.0, 2, -4000 * 0.02 / 360),
        (-30.0, 3, -0.30),
        (-1.0, -1, None),
    ])
    def test_swap_conversion(self, value, stype, expected):
        got = bc.swap_per_oz(value, stype, 0.01, 100.0, 4000.0)
        assert got == (None if expected is None else pytest.approx(expected))


def test_costs_report_news_and_suggestions(db):
    from models.economic_calendar import EconomicEvent
    now = datetime.utcnow().replace(second=0, microsecond=0)
    base = now - timedelta(days=2)
    base = base.replace(hour=10, minute=0)
    ev = base + timedelta(hours=3, minutes=30)
    db.add(EconomicEvent(event="CPI y/y test", currency="USD", impact=3, event_time=ev))
    db.commit()
    rows = [_q(base + timedelta(minutes=m), spread=0.35, symbol="XCOST") for m in range(0, 300)]
    for r in rows:  # spread spike around the event
        t = datetime.utcfromtimestamp(r["ts"])
        if abs((t - ev).total_seconds()) <= 600:
            r["spread_max"] = 2.0
    bc.ingest(db, rows)
    out = bc.costs(db, symbol="XCOST", days=7)
    assert out["minutes"] == 300 and out["broker_symbol"] == "GOLD"
    assert out["spread"]["normal_hours"]["p50"] == pytest.approx(0.35)
    assert out["spread"]["news_pm15min_max"]["p50"] == pytest.approx(2.0)
    assert out["spec"]["swap_long_per_oz_night"] == pytest.approx(-0.45)
    assert out["suggested_env"]["GOLDAI_SPREAD"] == pytest.approx(0.35)
    assert any("Swap" in n for n in out["notes"])


def test_costs_empty(db):
    out = bc.costs(db, symbol="NOPE")
    assert out["minutes"] == 0 and "EA" in out["note"]
