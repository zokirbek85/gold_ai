"""Tests for the News Intelligence Engine."""
import pytest
from src.news_engine.analyzer import NewsAnalyzer


@pytest.fixture()
def analyzer():
    return NewsAnalyzer()


class TestNewsAnalyzer:
    def test_bullish_classification(self, analyzer):
        result = analyzer.classify("Gold surges as rate cut expectations rise, dollar weakens")
        assert result["direction"] == "bullish"
        assert result["confidence"] > 50
        assert 1 <= result["impact_score"] <= 10

    def test_bearish_classification(self, analyzer):
        result = analyzer.classify("Gold falls sharply as dollar strengthens after NFP beat expectations")
        assert result["direction"] == "bearish"
        assert result["confidence"] > 50

    def test_neutral_classification(self, analyzer):
        result = analyzer.classify("Market closes flat ahead of holiday weekend")
        assert result["direction"] == "neutral"

    def test_impact_score_range(self, analyzer):
        result = analyzer.classify("FOMC raises interest rates by 50bps, hawkish guidance")
        assert 1 <= result["impact_score"] <= 10

    def test_duration_fomc(self, analyzer):
        result = analyzer.classify("FOMC meeting decision: rates unchanged")
        assert result["expected_duration"] == "1 Week"

    def test_duration_cpi(self, analyzer):
        result = analyzer.classify("CPI inflation data released above forecast")
        assert "Day" in result["expected_duration"]

    def test_summary_generation(self, analyzer):
        title = "Gold rises to 3-month high"
        content = "Gold prices climbed as investors sought safe haven assets. The dollar weakened."
        summary = analyzer.generate_summary(title, content)
        assert len(summary) > 0
        assert len(summary) <= 305  # max_len + some tolerance

    def test_analyze_article(self, analyzer):
        article = {"title": "Gold jumps as Fed signals dovish pivot", "content": "Prices rose significantly"}
        result = analyzer.analyze_article(article)
        assert "direction" in result
        assert "impact_score" in result
        assert "summary" in result

    def test_aggregate_sentiment_bullish(self, analyzer):
        articles = [{"direction": "bullish", "impact_score": 8, "confidence": 80}] * 7 + \
                   [{"direction": "bearish", "impact_score": 5, "confidence": 60}] * 3
        result = analyzer.aggregate_sentiment(articles)
        assert result["direction"] == "bullish"
        assert result["score"] > 55

    def test_aggregate_sentiment_empty(self, analyzer):
        result = analyzer.aggregate_sentiment([])
        assert result["direction"] == "neutral"
        assert result["score"] == 50.0

    def test_analyze_batch(self, analyzer):
        articles = [
            {"title": "Gold rises", "content": "safe haven demand"},
            {"title": "Gold falls", "content": "dollar strengthens"},
        ]
        results = analyzer.analyze_batch(articles)
        assert len(results) == 2
        assert all("direction" in r for r in results)
