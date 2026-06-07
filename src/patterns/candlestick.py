"""
Candlestick pattern detection engine.
Each detector returns a confidence score (0.0–1.0) and a direction: bullish/bearish/neutral.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class CandlestickDetector:
    """Stateless candlestick pattern detector."""

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _body(c: Dict[str, Any]) -> float:
        return abs(float(c["close"]) - float(c["open"]))

    @staticmethod
    def _range(c: Dict[str, Any]) -> float:
        return float(c["high"]) - float(c["low"])

    @staticmethod
    def _upper_shadow(c: Dict[str, Any]) -> float:
        return float(c["high"]) - max(float(c["open"]), float(c["close"]))

    @staticmethod
    def _lower_shadow(c: Dict[str, Any]) -> float:
        return min(float(c["open"]), float(c["close"])) - float(c["low"])

    @staticmethod
    def _is_bullish(c: Dict[str, Any]) -> bool:
        return float(c["close"]) > float(c["open"])

    @staticmethod
    def _is_bearish(c: Dict[str, Any]) -> bool:
        return float(c["close"]) < float(c["open"])

    # ------------------------------------------------------------------ Hammer / Hanging Man
    def hammer(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Hammer (bullish reversal at bottom) / Hanging Man (bearish at top)."""
        if len(candles) < 1:
            return None
        c = candles[-1]
        body = self._body(c)
        rng = self._range(c)
        if rng == 0:
            return None
        lower_shadow = self._lower_shadow(c)
        upper_shadow = self._upper_shadow(c)
        if lower_shadow < 2 * body:
            return None
        if upper_shadow > body * 0.5:
            return None
        confidence = min(1.0, lower_shadow / (body + 1e-9) / 4)
        direction = "bullish" if self._is_bullish(c) else "bearish"
        return {
            "name": "Hammer",
            "direction": direction,
            "confidence": round(confidence, 3),
            "description": "Long lower shadow indicates potential reversal",
        }

    # ------------------------------------------------------------------ Doji
    def doji(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not candles:
            return None
        c = candles[-1]
        body = self._body(c)
        rng = self._range(c)
        if rng == 0:
            return None
        body_ratio = body / rng
        if body_ratio > 0.1:
            return None
        confidence = round(1.0 - body_ratio * 10, 3)
        return {
            "name": "Doji",
            "direction": "neutral",
            "confidence": confidence,
            "description": "Open and close nearly equal — indecision in the market",
        }

    # ------------------------------------------------------------------ Engulfing
    def engulfing(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(candles) < 2:
            return None
        prev, curr = candles[-2], candles[-1]
        prev_body = self._body(prev)
        curr_body = self._body(curr)
        if curr_body <= prev_body:
            return None
        bullish = self._is_bearish(prev) and self._is_bullish(curr) and float(curr["open"]) < float(prev["close"]) and float(curr["close"]) > float(prev["open"])
        bearish = self._is_bullish(prev) and self._is_bearish(curr) and float(curr["open"]) > float(prev["close"]) and float(curr["close"]) < float(prev["open"])
        if not bullish and not bearish:
            return None
        confidence = round(min(1.0, curr_body / (prev_body + 1e-9) * 0.4), 3)
        return {
            "name": "Bullish Engulfing" if bullish else "Bearish Engulfing",
            "direction": "bullish" if bullish else "bearish",
            "confidence": confidence,
            "description": "Current candle body fully engulfs prior candle body",
        }

    # ------------------------------------------------------------------ Morning Star
    def morning_star(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(candles) < 3:
            return None
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        if not (
            self._is_bearish(c1)
            and self._body(c2) < self._body(c1) * 0.5
            and self._is_bullish(c3)
            and float(c3["close"]) > (float(c1["open"]) + float(c1["close"])) / 2
        ):
            return None
        return {
            "name": "Morning Star",
            "direction": "bullish",
            "confidence": 0.78,
            "description": "Three-candle bullish reversal: bearish, small doji-like, bullish",
        }

    # ------------------------------------------------------------------ Evening Star
    def evening_star(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(candles) < 3:
            return None
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        if not (
            self._is_bullish(c1)
            and self._body(c2) < self._body(c1) * 0.5
            and self._is_bearish(c3)
            and float(c3["close"]) < (float(c1["open"]) + float(c1["close"])) / 2
        ):
            return None
        return {
            "name": "Evening Star",
            "direction": "bearish",
            "confidence": 0.78,
            "description": "Three-candle bearish reversal: bullish, small, then bearish",
        }

    # ------------------------------------------------------------------ Shooting Star
    def shooting_star(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not candles:
            return None
        c = candles[-1]
        body = self._body(c)
        rng = self._range(c)
        if rng == 0:
            return None
        upper = self._upper_shadow(c)
        lower = self._lower_shadow(c)
        if upper < 2 * body or lower > body:
            return None
        confidence = round(min(1.0, upper / (body + 1e-9) / 4), 3)
        return {
            "name": "Shooting Star",
            "direction": "bearish",
            "confidence": confidence,
            "description": "Long upper shadow indicates potential bearish reversal",
        }

    # ------------------------------------------------------------------ detect all
    def detect_all(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for detector in [
            self.hammer,
            self.doji,
            self.engulfing,
            self.morning_star,
            self.evening_star,
            self.shooting_star,
        ]:
            try:
                result = detector(candles)
                if result:
                    results.append(result)
            except Exception:
                pass
        return results


candlestick_detector = CandlestickDetector()
