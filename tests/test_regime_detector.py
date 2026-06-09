"""Unit tests for MarketRegimeDetector."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import random
import pytest
from core.regime import MarketRegimeDetector, Regime


@pytest.fixture
def detector():
    return MarketRegimeDetector()


def _make_candles(n: int = 60, trend: float = 0.0, noise: float = 5.0, seed: int = 42) -> list:
    """Generate synthetic OHLCV candles."""
    random.seed(seed)
    candles = []
    price = 2000.0
    for _ in range(n):
        change = trend + random.gauss(0, noise)
        o = price
        c = price + change
        h = max(o, c) + random.uniform(0, 2)
        lo = min(o, c) - random.uniform(0, 2)
        candles.append({"open": o, "high": h, "low": lo, "close": c, "volume": 500.0})
        price = c
    return candles


class TestRegimeDetector:
    def test_returns_regime_object(self, detector):
        candles = _make_candles(60)
        result = detector.detect(candles)
        assert isinstance(result, Regime)
        assert result.name in {
            "TRENDING_UP", "TRENDING_DOWN", "RANGING",
            "VOLATILE", "LOW_VOLATILITY", "NEWS_DRIVEN"
        }
        assert 0 <= result.strength <= 100

    def test_news_driven_override(self, detector):
        candles = _make_candles(60)
        result = detector.detect(candles, news_driven=True)
        assert result.name == "NEWS_DRIVEN"
        assert result.strength >= 50

    def test_uptrend_detected(self, detector):
        candles = _make_candles(80, trend=2.0, noise=1.0)
        result = detector.detect(candles)
        assert result.name == "TRENDING_UP"

    def test_downtrend_detected(self, detector):
        candles = _make_candles(80, trend=-2.0, noise=1.0)
        result = detector.detect(candles)
        assert result.name == "TRENDING_DOWN"

    def test_volatile_regime(self, detector):
        candles = _make_candles(80, trend=0.0, noise=25.0)
        result = detector.detect(candles)
        assert result.name == "VOLATILE"

    def test_insufficient_data_returns_ranging(self, detector):
        candles = _make_candles(10)
        result = detector.detect(candles)
        assert result.name == "RANGING"

    def test_signal_weights_sum_to_one(self, detector):
        candles = _make_candles(60)
        regime = detector.detect(candles)
        weights = detector.signal_weights(regime)
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_signal_weights_all_regimes(self, detector):
        for name in ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE",
                     "LOW_VOLATILITY", "NEWS_DRIVEN"]:
            regime = Regime(name=name, strength=75.0, description="test")
            weights = detector.signal_weights(regime)
            total = sum(weights.values())
            assert abs(total - 1.0) < 1e-9, f"Regime {name}: weights sum to {total}"

    def test_adx_method(self, detector):
        candles = _make_candles(60, trend=1.0)
        adx = detector._adx(candles)
        assert 0 <= adx <= 100

    def test_price_slope_positive_for_uptrend(self, detector):
        candles = _make_candles(30, trend=5.0, noise=0.1)
        slope = detector._price_slope(candles)
        assert slope > 0

    def test_price_slope_negative_for_downtrend(self, detector):
        candles = _make_candles(30, trend=-5.0, noise=0.1)
        slope = detector._price_slope(candles)
        assert slope < 0
