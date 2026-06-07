"""Tests for backtesting engine and metrics."""
import pytest
from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import BacktestMetrics


@pytest.fixture()
def metrics():
    return BacktestMetrics()


@pytest.fixture()
def engine():
    return BacktestEngine()


@pytest.fixture()
def sample_trades():
    return [
        {"pnl": 150.0, "rr": 2.5, "opened_at": "2024-01-15T10:00:00", "closed_at": "2024-01-15T12:00:00"},
        {"pnl": -75.0, "rr": -1.0, "opened_at": "2024-01-16T09:00:00", "closed_at": "2024-01-16T11:00:00"},
        {"pnl": 200.0, "rr": 3.0, "opened_at": "2024-02-01T10:00:00", "closed_at": "2024-02-01T14:00:00"},
        {"pnl": -50.0, "rr": -1.0, "opened_at": "2024-02-05T09:00:00", "closed_at": "2024-02-05T10:00:00"},
        {"pnl": 175.0, "rr": 2.0, "opened_at": "2024-02-10T10:00:00", "closed_at": "2024-02-10T13:00:00"},
    ]


class TestBacktestMetrics:
    def test_empty_trades(self, metrics):
        r = metrics.calculate([])
        assert r["total_trades"] == 0
        assert r["win_rate"] == 0

    def test_win_rate(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        assert r["win_rate"] == pytest.approx(60.0, rel=0.01)

    def test_profit_factor(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        assert r["profit_factor"] > 1  # net positive

    def test_total_pnl(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        expected = sum(t["pnl"] for t in sample_trades)
        assert r["total_pnl"] == pytest.approx(expected, rel=0.01)

    def test_max_drawdown_range(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        assert 0 <= r["max_drawdown_pct"] <= 100

    def test_monthly_returns(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        assert "2024-01" in r["monthly_returns"]
        assert "2024-02" in r["monthly_returns"]

    def test_sharpe_finite(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        import math
        assert not math.isinf(r["sharpe_ratio"])

    def test_avg_rr_positive(self, metrics, sample_trades):
        r = metrics.calculate(sample_trades)
        assert r["avg_rr"] > 0


class TestBacktestEngine:
    def _make_candles(self, n=300):
        import random
        random.seed(123)
        out = []
        price = 2000.0
        for _ in range(n):
            change = random.gauss(0, 6)
            o = price
            c = price + change
            out.append({
                "open": o, "high": max(o, c) + 1, "low": min(o, c) - 1,
                "close": c, "volume": 100, "timestamp": f"2024-01-01T00:0{min(_ % 10, 9)}:00"
            })
            price = c
        return out

    def test_run_returns_dict(self, engine):
        candles = self._make_candles(200)
        result = engine.run(candles, window=80, step=10, account_balance=10000)
        assert isinstance(result, dict)

    def test_run_insufficient_data_returns_error(self, engine):
        candles = self._make_candles(20)
        result = engine.run(candles, window=50)
        assert "error" in result

    def test_run_has_metrics(self, engine):
        candles = self._make_candles(300)
        result = engine.run(candles, window=80, step=20, account_balance=10000)
        if "error" not in result:
            assert "metrics" in result
            assert "equity_curve" in result

    def test_equity_curve_starts_at_balance(self, engine):
        candles = self._make_candles(300)
        result = engine.run(candles, window=80, step=20, account_balance=10000)
        if "error" not in result and result.get("equity_curve"):
            assert result["equity_curve"][0] == 10000
