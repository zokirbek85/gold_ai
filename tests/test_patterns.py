"""Tests for pattern detection (candlestick + chart)."""
import pytest
from src.patterns.candlestick import CandlestickDetector
from src.patterns.chart import ChartPatternDetector


@pytest.fixture()
def cs():
    return CandlestickDetector()


@pytest.fixture()
def cd():
    return ChartPatternDetector()


def _candle(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": 100}


class TestCandlestick:
    def test_hammer_detection(self, cs):
        # Long lower shadow (90->100), small body (100->100.3), minimal upper shadow
        hammer = _candle(open_=100, high=100.3, low=90, close=100.3)
        result = cs.hammer([hammer])
        assert result is not None
        assert result["name"] == "Hammer"
        assert 0 < result["confidence"] <= 1

    def test_doji_detection(self, cs):
        doji = _candle(open_=100, high=103, low=97, close=100.05)
        result = cs.doji([doji])
        assert result is not None
        assert result["direction"] == "neutral"

    def test_bullish_engulfing(self, cs):
        prev = _candle(open_=102, high=103, low=99, close=100)  # bearish
        curr = _candle(open_=99, high=105, low=98, close=104)   # bullish engulfing
        result = cs.engulfing([prev, curr])
        assert result is not None
        assert "Bullish" in result["name"]

    def test_bearish_engulfing(self, cs):
        prev = _candle(open_=99, high=104, low=98, close=103)   # bullish
        curr = _candle(open_=104, high=105, low=97, close=98)   # bearish engulfing
        result = cs.engulfing([prev, curr])
        assert result is not None
        assert "Bearish" in result["name"]

    def test_morning_star(self, cs):
        c1 = _candle(open_=110, high=111, low=99, close=100)  # bearish
        c2 = _candle(open_=100, high=102, low=99, close=101)  # small
        c3 = _candle(open_=101, high=113, low=100, close=112)  # bullish
        result = cs.morning_star([c1, c2, c3])
        assert result is not None
        assert result["direction"] == "bullish"

    def test_shooting_star(self, cs):
        ss = _candle(open_=100, high=115, low=99, close=101)
        result = cs.shooting_star([ss])
        assert result is not None
        assert result["direction"] == "bearish"

    def test_detect_all_returns_list(self, cs):
        candles = [_candle(100, 110, 90, 105)] * 10
        result = cs.detect_all(candles)
        assert isinstance(result, list)


class TestChartPatterns:
    def _double_top_candles(self):
        """Create a simple double top pattern."""
        candles = []
        prices = [100, 102, 105, 108, 110, 107, 104, 103, 107, 109, 110.1, 107, 103, 100]
        for p in prices:
            candles.append({"open": p - 0.5, "high": p + 1, "low": p - 1.5, "close": p, "volume": 100})
        return candles

    def test_chart_detect_all_returns_list(self, cd):
        candles = [{"open": i, "high": i + 1, "low": i - 1, "close": i + 0.5, "volume": 100} for i in range(50)]
        result = cd.detect_all(candles)
        assert isinstance(result, list)

    def test_ascending_triangle(self, cd):
        # Flat highs, rising lows
        candles = []
        for i in range(20):
            h = 110.0  # flat high
            l = 100 + i * 0.3  # rising low
            candles.append({"open": l + 1, "high": h, "low": l, "close": l + 2, "volume": 100})
        result = cd.ascending_triangle(candles)
        assert result is not None
        assert result["direction"] == "bullish"

    def test_descending_triangle(self, cd):
        # Flat lows, falling highs
        candles = []
        for i in range(20):
            l = 90.0  # flat low
            h = 110 - i * 0.5  # falling high
            candles.append({"open": h - 1, "high": h, "low": l, "close": l + 1, "volume": 100})
        result = cd.descending_triangle(candles)
        assert result is not None
        assert result["direction"] == "bearish"

    def test_insufficient_data_returns_none(self, cd):
        candles = [{"open": 1, "high": 2, "low": 0, "close": 1.5, "volume": 100}] * 5
        assert cd.double_top(candles) is None
        assert cd.head_and_shoulders(candles) is None
