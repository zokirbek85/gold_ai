"""
News impact analyzer.
Classifies articles as bullish/bearish/neutral for gold.
Calculates impact score (1–10), confidence (0–100), and expected duration.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Keyword weight maps — positive words increase bullish score, negative increase bearish
_BULLISH_KEYWORDS: List[Tuple[str, float]] = [
    ("gold rises", 3.0), ("gold surges", 3.5), ("gold rally", 3.0),
    ("gold gains", 2.5), ("safe haven", 2.5), ("flight to safety", 3.0),
    ("inflation rises", 2.5), ("inflation surge", 3.0), ("cpi above", 2.5),
    ("rate cut", 3.5), ("dovish", 2.5), ("fed pauses", 3.0),
    ("dollar weakens", 2.5), ("dollar falls", 2.0), ("geopolitical", 2.0),
    ("war", 2.0), ("conflict", 1.5), ("recession fears", 2.0),
    ("gold demand", 2.0), ("central bank buying", 3.0), ("lower yields", 2.5),
    ("gold xau", 2.0), ("precious metals rise", 2.5),
]

_BEARISH_KEYWORDS: List[Tuple[str, float]] = [
    ("gold falls", 3.0), ("gold drops", 3.0), ("gold declines", 2.5),
    ("gold pressure", 2.0), ("rate hike", 3.5), ("hawkish", 2.5),
    ("dollar strengthens", 2.5), ("dollar rises", 2.0), ("risk on", 2.0),
    ("inflation cools", 2.5), ("cpi below", 2.5), ("stronger dollar", 2.5),
    ("gold selloff", 3.5), ("gold outflows", 2.0), ("higher yields", 2.5),
    ("gold etf outflows", 2.5),
]

_DURATION_MAP: Dict[str, str] = {
    "fomc": "1 Week",
    "fed decision": "1 Week",
    "interest rate": "1 Week",
    "gdp": "1 Day",
    "nfp": "1 Day",
    "non-farm": "1 Day",
    "cpi": "1-3 Days",
    "ppi": "1 Day",
    "inflation": "1-3 Days",
    "war": "Long Term",
    "conflict": "Long Term",
    "geopolitical": "Long Term",
    "central bank": "1 Week",
    "rate": "1 Day",
    "default": "Intraday",
}


class NewsAnalyzer:
    def classify(self, text: str) -> Dict[str, Any]:
        """Classify a news article's gold impact."""
        text_lower = text.lower()

        bull_score = sum(weight for kw, weight in _BULLISH_KEYWORDS if kw in text_lower)
        bear_score = sum(weight for kw, weight in _BEARISH_KEYWORDS if kw in text_lower)

        total = bull_score + bear_score
        if total == 0:
            direction = "neutral"
            raw_confidence = 40.0
        elif bull_score > bear_score:
            direction = "bullish"
            raw_confidence = min(95.0, 50.0 + (bull_score - bear_score) / (total + 1e-9) * 50)
        else:
            direction = "bearish"
            raw_confidence = min(95.0, 50.0 + (bear_score - bull_score) / (total + 1e-9) * 50)

        impact_score = min(10, max(1, int(total / 2 + 1)))
        duration = self._estimate_duration(text_lower)

        return {
            "direction": direction,
            "impact_score": impact_score,
            "confidence": round(raw_confidence, 1),
            "expected_duration": duration,
            "bull_score": round(bull_score, 2),
            "bear_score": round(bear_score, 2),
        }

    @staticmethod
    def _estimate_duration(text_lower: str) -> str:
        for keyword, duration in _DURATION_MAP.items():
            if keyword == "default":
                continue
            if keyword in text_lower:
                return duration
        return _DURATION_MAP["default"]

    def generate_summary(self, title: str, content: str, max_len: int = 300) -> str:
        """Produce a short summary (first meaningful sentences, up to max_len chars)."""
        text = (title + ". " + content).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = ""
        for s in sentences:
            if len(summary) + len(s) > max_len:
                break
            summary += s + " "
        return summary.strip() or text[:max_len]

    def analyze_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Full analysis of a single article dict."""
        title = article.get("title", "")
        content = article.get("content", "")
        combined = title + " " + content
        classification = self.classify(combined)
        summary = self.generate_summary(title, content)
        return {
            **article,
            "summary": summary,
            **classification,
        }

    def analyze_batch(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.analyze_article(a) for a in articles]

    def aggregate_sentiment(self, analyzed: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate multiple analyzed articles into a single sentiment score."""
        if not analyzed:
            return {"direction": "neutral", "score": 50.0, "article_count": 0}
        bull = sum(1 for a in analyzed if a.get("direction") == "bullish")
        bear = sum(1 for a in analyzed if a.get("direction") == "bearish")
        total = len(analyzed)
        bull_pct = bull / total * 100
        if bull_pct > 55:
            direction = "bullish"
            score = bull_pct
        elif bull_pct < 45:
            direction = "bearish"
            score = 100 - bull_pct
        else:
            direction = "neutral"
            score = 50.0
        avg_impact = sum(a.get("impact_score", 5) for a in analyzed) / total
        return {
            "direction": direction,
            "score": round(score, 1),
            "avg_impact": round(avg_impact, 1),
            "article_count": total,
            "bullish_count": bull,
            "bearish_count": bear,
        }


news_analyzer = NewsAnalyzer()
