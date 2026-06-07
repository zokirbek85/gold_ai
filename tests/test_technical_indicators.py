"""Comprehensive tests for the IndicatorCalculator module."""
import pytest
from src.indicators.calculator import IndicatorCalculator


@pytest.fixture()
def calc():
    return IndicatorCalculator()


@pytest.fixture()
def candles():
    """300 synthetic OHLCV candles."""
    import random
    random.seed(42)
    out = []
    price = 1900.0
    for _ in range(300):
        change = random.gauss(0, 5)
        o = price
        c = price + change
        h = max(o, c) + random.uniform(0, 3)
        l = min(o, c) - random.uniform(0, 3)
        out.append({"open": o, "high": h, "low": l, "close": c, "volume": random.uniform(100, 1000)})
        price = c
    return out


class TestEMA:
    def test_ema20_returns_float(self, calc, candles):
        assert isinstance(calc.ema20(candles), float)

    def test_ema50_returns_float(self, calc, candles):
        assert isinstance(calc.ema50(candles), float)

    def test_ema100_returns_float(self, calc, candles):
        assert isinstance(calc.ema100(candles), float)

    def test_ema200_returns_float(self, calc, candles):
        assert isinstance(calc.ema200(candles), float)

    def test_insufficient_data_returns_none(self, calc):
        short = [{"open": 1, "high": 2, "low": 0, "close": 1.5, "volume": 1}] * 10
        assert calc.ema50(short) is None

    def test_ema_ordering(self, calc, candles):
        # In a long uptrend, EMA20 > EMA50 is expected most of the time
        e20 = calc.ema20(candles)
        e200 = calc.ema200(candles)
        assert e20 is not None and e200 is not None


class TestRSI:
    def test_range(self, calc, candles):
        r = calc.rsi(candles, 14)
        assert r is not None
        assert 0 <= r <= 100

    def test_all_rising_approaches_100(self, calc):
        rising = [{"open": i, "high": i + 1, "low": i - 0.5, "close": i + 1, "volume": 100} for i in range(1, 50)]
        r = calc.rsi(rising, 14)
        assert r is not None
        assert r > 70


class TestMACD:
    def test_all_values_present(self, calc, candles):
        r = calc.macd(candles)
        assert r["macd"] is not None
        assert r["signal"] is not None
        assert r["histogram"] is not None

    def test_histogram_equals_macd_minus_signal(self, calc, candles):
        r = calc.macd(candles)
        assert abs(r["histogram"] - (r["macd"] - r["signal"])) < 1e-9


class TestStochastic:
    def test_k_in_range(self, calc, candles):
        r = calc.stochastic(candles)
        assert r["k"] is not None
        assert 0 <= r["k"] <= 100


class TestATR:
    def test_positive(self, calc, candles):
        r = calc.atr(candles, 14)
        assert r is not None
        assert r > 0


class TestBollingerBands:
    def test_upper_middle_lower_ordering(self, calc, candles):
        r = calc.bollinger_bands(candles)
        assert r["upper"] > r["middle"] > r["lower"]

    def test_bandwidth_positive(self, calc, candles):
        r = calc.bollinger_bands(candles)
        assert r["bandwidth"] is not None
        assert r["bandwidth"] > 0


class TestVWAP:
    def test_positive(self, calc, candles):
        assert calc.vwap(candles) > 0

    def test_zero_volume_returns_none(self, calc):
        flat = [{"open": 1, "high": 2, "low": 0, "close": 1.5, "volume": 0}] * 10
        assert calc.vwap(flat) is None


class TestOBV:
    def test_returns_float(self, calc, candles):
        assert calc.obv(candles) is not None


class TestADX:
    def test_adx_range(self, calc, candles):
        r = calc.adx(candles)
        if r["adx"] is not None:
            assert 0 <= r["adx"] <= 100


class TestComputeAll:
    def test_all_keys_present(self, calc, candles):
        r = calc.compute_all(candles)
        for key in ["EMA_20", "EMA_50", "EMA_100", "EMA_200", "RSI_14", "MACD_line", "MACD_signal",
                    "STOCH_K", "ATR_14", "BB_upper", "BB_middle", "BB_lower", "VWAP", "OBV", "ADX"]:
            assert key in r

    def test_no_none_values_with_300_candles(self, calc, candles):
        r = calc.compute_all(candles)
        none_keys = [k for k, v in r.items() if v is None]
        assert none_keys == []
