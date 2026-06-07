"""Tests for Economic Calendar engine."""
import pytest
from src.economic_calendar.engine import EconomicCalendarEngine


@pytest.fixture()
def engine():
    return EconomicCalendarEngine()


class TestEconomicCalendar:
    def test_cpi_above_forecast_bullish(self, engine):
        result = engine.score_event("CPI", actual=4.5, forecast=4.0, previous=4.0)
        assert result["gold_direction"] == "bullish"
        assert result["surprise_index"] > 0

    def test_nfp_above_forecast_bearish(self, engine):
        result = engine.score_event("NFP", actual=300, forecast=200, previous=200)
        assert result["gold_direction"] == "bearish"

    def test_surprise_index_calculation(self, engine):
        result = engine.score_event("CPI", actual=4.0, forecast=3.5, previous=3.5)
        expected_surprise = (4.0 - 3.5) / 3.5 * 100
        assert abs(result["surprise_index"] - expected_surprise) < 0.01

    def test_no_data_returns_neutral(self, engine):
        result = engine.score_event("CPI", actual=None, forecast=None, previous=None)
        assert result["gold_direction"] == "neutral"

    def test_impact_score_range(self, engine):
        result = engine.score_event("FOMC", actual=5.5, forecast=5.25, previous=5.0)
        assert 1 <= result["gold_impact_score"] <= 10

    def test_aggregate_empty_returns_neutral(self, engine):
        result = engine.aggregate_score([])
        assert result["direction"] == "neutral"
        assert result["score"] == 50.0

    def test_aggregate_bullish_majority(self, engine):
        events = [{"gold_direction": "bullish", "gold_impact_score": 8}] * 7 + \
                 [{"gold_direction": "bearish", "gold_impact_score": 5}] * 3
        result = engine.aggregate_score(events)
        assert result["direction"] == "bullish"

    def test_aggregate_bearish_majority(self, engine):
        events = [{"gold_direction": "bearish", "gold_impact_score": 8}] * 8 + \
                 [{"gold_direction": "bullish", "gold_impact_score": 5}] * 2
        result = engine.aggregate_score(events)
        assert result["direction"] == "bearish"

    def test_fomc_base_impact_is_10(self, engine):
        result = engine.score_event("FOMC", actual=None, forecast=None, previous=None)
        assert result["gold_impact_score"] == 10

    def test_unknown_event_does_not_crash(self, engine):
        result = engine.score_event("Random Event XYZ", actual=1.0, forecast=0.8, previous=0.9)
        assert isinstance(result, dict)
        assert "gold_direction" in result
