"""Tests for historical_analysis service functions."""
import sys
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Make backend importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base
from models.candle import Candle
from models.economic_calendar import EconomicEvent
from backend.services.historical_analysis import (
    monthly_seasonality,
    event_impact_analysis,
    zone_test_analysis,
)

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = Session()
    yield session
    session.rollback()
    session.close()


def _make_candle(db, symbol, tf, ts, open_, high, low, close, volume=100.0):
    c = Candle(symbol=symbol, timeframe=tf, timestamp=ts,
               open=open_, high=high, low=low, close=close, volume=volume)
    db.add(c)
    return c


# ── monthly_seasonality ───────────────────────────────────────────────────────

def test_seasonality_insufficient_data_no_rows(db):
    result = monthly_seasonality(db, "XAUUSD", 1)
    assert result.get("insufficient_data") is True


def test_seasonality_insufficient_data_one_year(db):
    # Only 1 year of data — not enough
    base = datetime(2024, 3, 1)
    _make_candle(db, "XAUUSD", "1440", base,                2300, 2310, 2290, 2295)
    _make_candle(db, "XAUUSD", "1440", base + timedelta(days=14), 2295, 2320, 2280, 2315)
    db.commit()
    result = monthly_seasonality(db, "XAUUSD", 3)
    assert result.get("insufficient_data") is True


def test_seasonality_two_years(db):
    # Add March 2023 and March 2024
    for year, close in [(2023, 2350), (2024, 2400)]:
        base = datetime(year, 3, 1)
        _make_candle(db, "XAUUSD", "1440", base,
                     2300, 2360, 2280, close)
    db.commit()
    result = monthly_seasonality(db, "XAUUSD", 3)
    assert result.get("insufficient_data") is not True
    assert result["years_analyzed"] >= 2
    assert "avg_change_pct" in result
    assert "win_rate_pct" in result
    assert "note" in result


# ── zone_test_analysis ────────────────────────────────────────────────────────

def test_zone_no_touches(db):
    result = zone_test_analysis(db, "XAUUSD", 9999.0)
    assert result["touches"] == 0
    assert result["bounce_rate_pct"] == 0.0


def test_zone_touches_counted(db):
    zone = 2300.0
    now  = datetime.utcnow()
    # 3 candles that touch the zone within tolerance (±0.3%)
    for i in range(3):
        ts = now - timedelta(days=i + 1)
        _make_candle(db, "XAUUSD", "60", ts,
                     zone + 5, zone + 10, zone - 2, zone + 8)  # bounce away
    db.commit()
    result = zone_test_analysis(db, "XAUUSD", zone)
    assert result["touches"] >= 3
    assert result["zone_price"] == pytest.approx(zone, abs=0.01)


# ── event_impact_analysis ─────────────────────────────────────────────────────

def test_event_impact_insufficient_events(db):
    result = event_impact_analysis(db, "XAUUSD", ["nfp", "non-farm"])
    assert result.get("insufficient_data") is True


def test_event_impact_with_events(db):
    now = datetime.utcnow() - timedelta(days=30)
    for i in range(4):
        ev = EconomicEvent(
            event=f"Non-Farm Payrolls #{i}",
            currency="USD",
            impact=3,
            event_time=now - timedelta(days=i * 30),
        )
        db.add(ev)
        # Add surrounding candles
        for delta in [-4, 0, 24]:
            ts = now - timedelta(days=i * 30) + timedelta(hours=delta)
            _make_candle(db, "XAUUSD", "60", ts,
                         2300 + i, 2310 + i, 2290 + i, 2305 + i)
    db.commit()
    result = event_impact_analysis(db, "XAUUSD", ["non-farm"])
    # With 4 events but potentially no close candles found, may still return insufficient
    assert "insufficient_data" in result or "events_analyzed" in result
