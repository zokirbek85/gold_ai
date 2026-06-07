"""Tests for the Signal Engine and Risk Management."""
import pytest
from src.signals.scorer import SignalScorer
from src.risk_management.calculator import RiskCalculator


@pytest.fixture()
def scorer():
    return SignalScorer()


@pytest.fixture()
def risk():
    return RiskCalculator()


@pytest.fixture()
def candles():
    import random
    random.seed(99)
    out = []
    price = 2000.0
    for _ in range(200):
        change = random.gauss(0, 5)
        o = price
        c = price + change
        out.append({"open": o, "high": max(o, c) + 1.5, "low": min(o, c) - 1.5, "close": c, "volume": 100})
        price = c
    return out


class TestRiskCalculator:
    def test_atr_positive(self, risk, candles):
        atr = risk.calculate_atr(candles)
        assert atr is not None
        assert atr > 0

    def test_position_size(self, risk):
        result = risk.position_size(account_balance=10000, entry=2000, stop_loss=1995)
        assert result["lots"] > 0
        assert result["risk_amount"] == pytest.approx(100, rel=0.01)

    def test_build_trade_plan_bullish(self, risk, candles):
        plan = risk.build_trade_plan(candles, direction="bullish", account_balance=10000)
        assert plan["direction"] == "bullish"
        assert plan["stop_loss"] < plan["entry"]
        assert plan["take_profit_1"] > plan["entry"]
        assert plan["risk_reward"] >= 1.5

    def test_build_trade_plan_bearish(self, risk, candles):
        plan = risk.build_trade_plan(candles, direction="bearish", account_balance=10000)
        assert plan["direction"] == "bearish"
        assert plan["stop_loss"] > plan["entry"]
        assert plan["take_profit_1"] < plan["entry"]

    def test_risk_filter_passes(self, risk, candles):
        plan = risk.build_trade_plan(candles, direction="bullish", account_balance=10000)
        check = risk.passes_risk_filter(plan)
        assert isinstance(check["passed"], bool)
        assert isinstance(check["reasons"], list)

    def test_risk_filter_fails_on_low_rr(self, risk):
        plan = {"entry": 2000, "stop_loss": 1990, "take_profit_1": 2010, "risk_reward": 1.0, "lot_size": 0.01}
        check = risk.passes_risk_filter(plan)
        assert check["passed"] is False
        assert len(check["reasons"]) > 0


class TestSignalScorer:
    def test_generate_returns_dict(self, scorer, candles):
        result = scorer.generate(candles)
        assert isinstance(result, dict)

    def test_signal_type_valid(self, scorer, candles):
        result = scorer.generate(candles)
        assert result["signal_type"] in ("BUY", "SELL", "NO TRADE")

    def test_composite_score_range(self, scorer, candles):
        result = scorer.generate(candles)
        assert 0 <= result["composite_score"] <= 100

    def test_confidence_range(self, scorer, candles):
        result = scorer.generate(candles)
        assert 0 <= result["confidence"] <= 100

    def test_reasoning_is_string(self, scorer, candles):
        result = scorer.generate(candles)
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 10

    def test_with_external_scores(self, scorer, candles):
        result = scorer.generate(
            candles,
            smc_score={"direction": "bullish", "score": 75},
            news_score={"direction": "bullish", "score": 80},
            economic_score={"direction": "bullish", "score": 70},
        )
        assert result["composite_score"] > 55  # should lean bullish

    def test_insufficient_data_returns_no_trade(self, scorer):
        short = [{"open": 1, "high": 2, "low": 0, "close": 1.5, "volume": 100}] * 5
        result = scorer.generate(short)
        assert result["signal_type"] == "NO TRADE"
