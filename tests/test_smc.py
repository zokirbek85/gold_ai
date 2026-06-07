"""Tests for Smart Money Concepts engine."""
import pytest
from src.smc.engine import SMCEngine


@pytest.fixture()
def engine():
    return SMCEngine()


@pytest.fixture()
def candles():
    """200 synthetic candles with some structure."""
    import random
    random.seed(7)
    out = []
    price = 2000.0
    for _ in range(200):
        change = random.gauss(0, 8)
        o = price
        c = price + change
        out.append({"open": o, "high": max(o, c) + 2, "low": min(o, c) - 2, "close": c, "volume": 100})
        price = c
    return out


def test_market_structure_returns_list(engine, candles):
    result = engine.market_structure(candles)
    assert isinstance(result, list)


def test_market_structure_event_keys(engine, candles):
    events = engine.market_structure(candles)
    for e in events:
        assert "type" in e
        assert e["type"] in ("BOS", "CHOCH")
        assert "direction" in e
        assert e["direction"] in ("bullish", "bearish")


def test_liquidity_levels_returns_list(engine, candles):
    result = engine.liquidity_levels(candles)
    assert isinstance(result, list)


def test_order_blocks_returns_list(engine, candles):
    result = engine.order_blocks(candles)
    assert isinstance(result, list)


def test_order_block_keys(engine, candles):
    obs = engine.order_blocks(candles)
    for ob in obs:
        assert "ob_high" in ob
        assert "ob_low" in ob
        assert ob["ob_high"] >= ob["ob_low"]


def test_fvg_returns_list(engine, candles):
    result = engine.fair_value_gaps(candles)
    assert isinstance(result, list)


def test_premium_discount_returns_dict(engine, candles):
    result = engine.premium_discount(candles)
    assert "zone" in result
    assert result["zone"] in ("premium", "discount")
    assert "pct_of_range" in result
    assert 0 <= result["pct_of_range"] <= 100


def test_analyze_returns_full_dict(engine, candles):
    result = engine.analyze(candles)
    assert "market_structure" in result
    assert "order_blocks" in result
    assert "fair_value_gaps" in result
    assert "premium_discount" in result
    assert "liquidity_levels" in result


def test_score_returns_direction_and_score(engine, candles):
    result = engine.score(candles)
    assert result["direction"] in ("bullish", "bearish", "neutral")
    assert 0 <= result["score"] <= 100
    assert "events" in result


def test_insufficient_data_returns_empty(engine):
    short = [{"open": 1, "high": 2, "low": 0, "close": 1.5, "volume": 100}] * 3
    assert engine.market_structure(short) == []
    assert engine.order_blocks(short) == []
