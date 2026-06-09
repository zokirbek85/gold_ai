"""Tests for enrich_signal() in signal_service."""
import sys
import os

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from backend.services.signal_service import enrich_signal


def _base_signal(signal_type: str = "BUY") -> dict:
    return {
        "symbol": "XAUUSD",
        "timeframe": "60",
        "signal_type": signal_type,
        "entry": 2350.00,
        "stop_loss": 2330.00,
        "take_profit": 2390.00,
        "tp1": 2370.00,
        "tp3": 2420.00,
        "confidence": 75.0,
        "reasoning": "RSI oversold | MACD bullish | Above EMA200",
    }


def test_enrich_buy_signal_lot_size():
    result = enrich_signal(_base_signal("BUY"), account_balance=10000.0)
    assert result["lot_size"] is not None
    assert result["lot_size"] >= 0.01
    assert result["risk_amount_usd"] == pytest.approx(100.0, abs=0.01)


def test_enrich_buy_signal_distances():
    result = enrich_signal(_base_signal("BUY"), account_balance=10000.0)
    # SL distance: |2350 - 2330| = 20 → pct = 20/2350*100 ≈ 0.851
    assert result["sl_distance_pct"] == pytest.approx(20 / 2350 * 100, abs=0.01)
    # TP1 distance: |2370 - 2350| = 20
    assert result["tp1_distance_pct"] == pytest.approx(20 / 2350 * 100, abs=0.01)


def test_enrich_buy_signal_emoji():
    result = enrich_signal(_base_signal("BUY"))
    assert result["signal_emoji"] == "🟢"


def test_enrich_sell_signal_emoji():
    result = enrich_signal(_base_signal("SELL"))
    assert result["signal_emoji"] == "🔴"


def test_enrich_neutral_signal():
    neutral = {
        "symbol": "XAUUSD", "timeframe": "60",
        "signal_type": "NEUTRAL",
        "entry": None, "stop_loss": None, "take_profit": None,
        "tp1": None, "tp3": None, "confidence": 0.0, "reasoning": "",
    }
    result = enrich_signal(neutral)
    assert result["signal_emoji"] == "⚪"
    assert result["lot_size"] is None
    assert "NEUTRAL" in result["plain_explanation"]
    assert "Savdo qilmang" in result["plain_explanation"]


def test_enrich_plain_explanation_contains_key_fields():
    result = enrich_signal(_base_signal("BUY"), account_balance=10000.0)
    expl = result["plain_explanation"]
    assert "2350.00" in expl
    assert "2330.00" in expl
    assert "2370.00" in expl
    assert "Kirish" in expl
    assert "Entry" in expl
    assert "Lot hajmi" in expl


def test_enrich_minimum_lot_size():
    """Very tight SL still produces minimum 0.01 lot."""
    sig = _base_signal("BUY")
    sig["stop_loss"] = 2349.99  # only 0.01 away
    result = enrich_signal(sig, account_balance=100.0)
    assert result["lot_size"] >= 0.01
