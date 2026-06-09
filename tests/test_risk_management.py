"""Unit tests for RiskCalculator and DailyRiskTracker."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from src.risk_management.calculator import RiskCalculator, risk_calculator
from core.risk_tracker import DailyRiskTracker


# ── RiskCalculator ────────────────────────────────────────────────────────────

class TestRiskCalculator:
    def setup_method(self):
        self.calc = RiskCalculator()

    def test_position_size_xauusd(self):
        result = self.calc.position_size(10000.0, 2300.0, 2285.0, "XAUUSD")
        assert result["lots"] > 0
        assert result["risk_amount"] == 100.0  # 1% of 10000
        assert result["sl_pips"] > 0

    def test_position_size_min_lot(self):
        """Very large SL should still return ≥ 0.01 lots."""
        result = self.calc.position_size(1000.0, 2300.0, 2000.0, "XAUUSD")
        assert result["lots"] >= 0.01

    def test_position_size_zero_sl(self):
        result = self.calc.position_size(10000.0, 2300.0, 2300.0, "XAUUSD")
        assert result["lots"] == 0.0

    def test_calculate_targets_bullish(self):
        targets = self.calc.calculate_targets(2300.0, 2285.0, "bullish")
        assert len(targets) == 3
        for t in targets:
            assert t["price"] > 2300.0
            assert t["rr"] > 0

    def test_calculate_targets_bearish(self):
        targets = self.calc.calculate_targets(2300.0, 2315.0, "bearish")
        assert len(targets) == 3
        for t in targets:
            assert t["price"] < 2300.0

    def test_passes_risk_filter_valid(self):
        plan = {"entry": 2300.0, "stop_loss": 2285.0,
                "take_profit_1": 2330.0, "risk_reward": 2.0, "lot_size": 0.1}
        result = self.calc.passes_risk_filter(plan)
        assert result["passed"] is True

    def test_passes_risk_filter_low_rr(self):
        plan = {"entry": 2300.0, "stop_loss": 2295.0,
                "take_profit_1": 2305.0, "risk_reward": 1.0, "lot_size": 0.1}
        result = self.calc.passes_risk_filter(plan)
        assert result["passed"] is False
        assert any("R:R" in r for r in result["reasons"])

    def test_atr_calculation(self):
        candles = [
            {"high": 2300 + i, "low": 2290 + i, "close": 2295 + i}
            for i in range(30)
        ]
        atr = self.calc.calculate_atr(candles, period=14)
        assert atr is not None
        assert atr > 0


# ── DailyRiskTracker (no-Redis mode) ─────────────────────────────────────────

class TestDailyRiskTracker:
    def setup_method(self):
        # Use tracker without Redis — all checks should pass (fail-open)
        self.tracker = DailyRiskTracker(redis_client=None)

    def test_can_trade_no_redis(self):
        result = self.tracker.can_trade("test", 10000.0, "XAUUSD")
        assert result["allowed"] is True
        assert result["reasons"] == []

    def test_status_no_redis(self):
        result = self.tracker.status("test", 10000.0)
        assert result["account_id"] == "test"
        assert result["open_trades"] == 0
        assert result["daily_pnl"] == 0.0


# ── Integration: RiskCalculator via module-level singleton ───────────────────

def test_singleton_works():
    result = risk_calculator.position_size(10000.0, 2300.0, 2285.0)
    assert "lots" in result
    assert "risk_amount" in result
