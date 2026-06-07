"""
Economic Calendar engine.
Fetches events from ForexFactory/investing.com style feeds,
calculates surprise index, and scores gold impact for each event.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

# Historical gold impact by event type (direction when actual > forecast)
_EVENT_GOLD_IMPACT: Dict[str, Dict[str, Any]] = {
    "CPI":            {"beats_direction": "bullish", "misses_direction": "bearish", "base_impact": 8, "description": "Consumer Price Index"},
    "Core CPI":       {"beats_direction": "bullish", "misses_direction": "bearish", "base_impact": 8, "description": "Core CPI"},
    "PPI":            {"beats_direction": "bullish", "misses_direction": "bearish", "base_impact": 7, "description": "Producer Price Index"},
    "NFP":            {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 9, "description": "Non-Farm Payrolls"},
    "GDP":            {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 7, "description": "Gross Domestic Product"},
    "FOMC":           {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 10, "description": "FOMC Rate Decision"},
    "Interest Rate":  {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 10, "description": "Interest Rate Decision"},
    "Jobless Claims": {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 5, "description": "Initial Jobless Claims"},
    "PMI":            {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 5, "description": "Purchasing Managers Index"},
    "Retail Sales":   {"beats_direction": "bearish", "misses_direction": "bullish", "base_impact": 6, "description": "Retail Sales"},
    "PCE":            {"beats_direction": "bullish", "misses_direction": "bearish", "base_impact": 8, "description": "PCE Price Index"},
}


class EconomicCalendarEngine:
    def __init__(self) -> None:
        self._timeout = 15

    def score_event(
        self,
        event_type: str,
        actual: Optional[float],
        forecast: Optional[float],
        previous: Optional[float],
    ) -> Dict[str, Any]:
        """
        Calculate surprise index and gold impact score for a single event.
        Surprise index: (actual - forecast) / abs(previous) * 100 if previous != 0
        """
        config = _EVENT_GOLD_IMPACT.get(event_type, {
            "beats_direction": "neutral",
            "misses_direction": "neutral",
            "base_impact": 3,
            "description": event_type,
        })

        surprise_index = 0.0
        direction = "neutral"
        gold_impact = config["base_impact"]

        if actual is not None and forecast is not None:
            diff = actual - forecast
            denom = abs(previous) if previous else abs(forecast) if forecast else 1.0
            surprise_index = diff / denom * 100 if denom != 0 else 0.0

            if diff > 0:
                direction = config["beats_direction"]
                gold_impact = min(10, config["base_impact"] + int(abs(surprise_index) / 10))
            elif diff < 0:
                direction = config["misses_direction"]
                gold_impact = min(10, config["base_impact"] + int(abs(surprise_index) / 10))

        return {
            "event_type": event_type,
            "actual": actual,
            "forecast": forecast,
            "previous": previous,
            "surprise_index": round(surprise_index, 2),
            "gold_impact_score": gold_impact,
            "gold_direction": direction,
            "description": config["description"],
        }

    def aggregate_score(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate recent economic events into a single economic score for signals."""
        if not events:
            return {"direction": "neutral", "score": 50.0, "event_count": 0}

        bullish = sum(1 for e in events if e.get("gold_direction") == "bullish")
        bearish = sum(1 for e in events if e.get("gold_direction") == "bearish")
        total = len(events)
        bull_pct = bullish / total * 100 if total else 50

        if bull_pct > 55:
            direction = "bullish"
            score = bull_pct
        elif bull_pct < 45:
            direction = "bearish"
            score = 100 - bull_pct
        else:
            direction = "neutral"
            score = 50.0

        avg_impact = sum(e.get("gold_impact_score", 5) for e in events) / total
        return {
            "direction": direction,
            "score": round(score, 1),
            "avg_impact": round(avg_impact, 1),
            "event_count": total,
        }

    def fetch_forexfactory(self) -> List[Dict[str, Any]]:
        """
        Fetch ForexFactory economic calendar (JSON API).
        Returns list of raw event dicts — caller stores them.
        """
        events: List[Dict[str, Any]] = []
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            resp = httpx.get(url, timeout=self._timeout, headers={"User-Agent": "GoldAI/1.0"})
            resp.raise_for_status()
            data = resp.json()
            for item in data:
                title = item.get("title", "")
                country = item.get("country", "")
                if country not in ("USD", "US", "EUR", "EU"):
                    continue
                events.append({
                    "provider": "ForexFactory",
                    "event_type": title,
                    "country": country,
                    "scheduled_at": self._parse_ff_date(item.get("date", ""), item.get("time", "")),
                    "actual": self._to_float(item.get("actual")),
                    "forecast": self._to_float(item.get("forecast")),
                    "previous": self._to_float(item.get("previous")),
                    "impact": self._impact_int(item.get("impact", "Low")),
                })
        except Exception as exc:
            log.warning("Failed to fetch ForexFactory calendar: %s", exc)
        return events

    @staticmethod
    def _parse_ff_date(date_str: str, time_str: str) -> datetime:
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace("%", "").replace("K", "000").replace("M", "000000").strip())
        except Exception:
            return None

    @staticmethod
    def _impact_int(impact: str) -> int:
        return {"Low": 1, "Medium": 2, "High": 3}.get(impact, 1)


economic_calendar = EconomicCalendarEngine()
