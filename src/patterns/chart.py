"""
Chart pattern detection engine.
Operates on a list of OHLC candle dicts ordered oldest→newest.
Returns confidence score (0–1) and pattern metadata.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _highs(candles: List[Dict[str, Any]]) -> List[float]:
    return [float(c["high"]) for c in candles]


def _lows(candles: List[Dict[str, Any]]) -> List[float]:
    return [float(c["low"]) for c in candles]


def _closes(candles: List[Dict[str, Any]]) -> List[float]:
    return [float(c["close"]) for c in candles]


def _local_maxima(values: List[float], window: int = 3) -> List[int]:
    peaks = []
    for i in range(window, len(values) - window):
        if values[i] == max(values[i - window : i + window + 1]):
            peaks.append(i)
    return peaks


def _local_minima(values: List[float], window: int = 3) -> List[int]:
    troughs = []
    for i in range(window, len(values) - window):
        if values[i] == min(values[i - window : i + window + 1]):
            troughs.append(i)
    return troughs


class ChartPatternDetector:
    """Detect multi-bar chart patterns on OHLC candle sequences."""

    def double_top(self, candles: List[Dict[str, Any]], tolerance: float = 0.003) -> Optional[Dict[str, Any]]:
        if len(candles) < 20:
            return None
        highs = _highs(candles)
        peaks = _local_maxima(highs, window=3)
        if len(peaks) < 2:
            return None
        p1, p2 = peaks[-2], peaks[-1]
        h1, h2 = highs[p1], highs[p2]
        if abs(h1 - h2) / max(h1, h2) > tolerance:
            return None
        trough_idx = min(range(p1, p2 + 1), key=lambda i: highs[i])
        trough = min(_lows(candles)[p1:p2])
        neckline = trough
        confidence = round(1.0 - abs(h1 - h2) / max(h1, h2) / tolerance, 3)
        return {
            "name": "Double Top",
            "direction": "bearish",
            "confidence": min(confidence, 0.85),
            "neckline": neckline,
            "peak1_idx": p1,
            "peak2_idx": p2,
            "description": "Two nearly equal highs — bearish reversal signal",
        }

    def double_bottom(self, candles: List[Dict[str, Any]], tolerance: float = 0.003) -> Optional[Dict[str, Any]]:
        if len(candles) < 20:
            return None
        lows = _lows(candles)
        troughs = _local_minima(lows, window=3)
        if len(troughs) < 2:
            return None
        t1, t2 = troughs[-2], troughs[-1]
        l1, l2 = lows[t1], lows[t2]
        if abs(l1 - l2) / min(l1, l2) > tolerance:
            return None
        neckline = max(_highs(candles)[t1:t2])
        confidence = round(1.0 - abs(l1 - l2) / min(l1, l2) / tolerance, 3)
        return {
            "name": "Double Bottom",
            "direction": "bullish",
            "confidence": min(confidence, 0.85),
            "neckline": neckline,
            "trough1_idx": t1,
            "trough2_idx": t2,
            "description": "Two nearly equal lows — bullish reversal signal",
        }

    def head_and_shoulders(self, candles: List[Dict[str, Any]], tolerance: float = 0.005) -> Optional[Dict[str, Any]]:
        if len(candles) < 30:
            return None
        highs = _highs(candles)
        peaks = _local_maxima(highs, window=3)
        if len(peaks) < 3:
            return None
        left, head, right = peaks[-3], peaks[-2], peaks[-1]
        h_left, h_head, h_right = highs[left], highs[head], highs[right]
        if h_head <= h_left or h_head <= h_right:
            return None
        if abs(h_left - h_right) / h_head > tolerance * 3:
            return None
        lows = _lows(candles)
        neckline = (min(lows[left:head]) + min(lows[head:right])) / 2
        confidence = round(min(0.88, (h_head - max(h_left, h_right)) / h_head * 10), 3)
        return {
            "name": "Head and Shoulders",
            "direction": "bearish",
            "confidence": confidence,
            "neckline": neckline,
            "description": "Classic bearish reversal — head higher than two shoulders",
        }

    def inverse_head_and_shoulders(self, candles: List[Dict[str, Any]], tolerance: float = 0.005) -> Optional[Dict[str, Any]]:
        if len(candles) < 30:
            return None
        lows = _lows(candles)
        troughs = _local_minima(lows, window=3)
        if len(troughs) < 3:
            return None
        left, head, right = troughs[-3], troughs[-2], troughs[-1]
        l_left, l_head, l_right = lows[left], lows[head], lows[right]
        if l_head >= l_left or l_head >= l_right:
            return None
        if abs(l_left - l_right) / abs(l_head) > tolerance * 3:
            return None
        highs = _highs(candles)
        neckline = (max(highs[left:head]) + max(highs[head:right])) / 2
        confidence = round(min(0.88, (min(l_left, l_right) - l_head) / abs(l_head + 1e-9) * 10), 3)
        return {
            "name": "Inverse Head and Shoulders",
            "direction": "bullish",
            "confidence": confidence,
            "neckline": neckline,
            "description": "Classic bullish reversal — head lower than two shoulders",
        }

    def ascending_triangle(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(candles) < 20:
            return None
        highs = _highs(candles)
        lows = _lows(candles)
        recent_highs = highs[-15:]
        recent_lows = lows[-15:]
        max_h = max(recent_highs)
        high_range = max(recent_highs) - min(recent_highs)
        if high_range / max_h > 0.015:
            return None
        low_slope = recent_lows[-1] - recent_lows[0]
        if low_slope <= 0:
            return None
        return {
            "name": "Ascending Triangle",
            "direction": "bullish",
            "confidence": 0.72,
            "resistance": max_h,
            "description": "Flat resistance + rising lows — bullish breakout expected",
        }

    def descending_triangle(self, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(candles) < 20:
            return None
        highs = _highs(candles)
        lows = _lows(candles)
        recent_highs = highs[-15:]
        recent_lows = lows[-15:]
        min_l = min(recent_lows)
        low_range = max(recent_lows) - min(recent_lows)
        if low_range / (abs(min_l) + 1e-9) > 0.015:
            return None
        high_slope = recent_highs[-1] - recent_highs[0]
        if high_slope >= 0:
            return None
        return {
            "name": "Descending Triangle",
            "direction": "bearish",
            "confidence": 0.72,
            "support": min_l,
            "description": "Flat support + falling highs — bearish breakout expected",
        }

    def w_pattern(self, candles: List[Dict[str, Any]], tolerance: float = 0.004) -> Optional[Dict[str, Any]]:
        """W pattern (Double Bottom variant with momentum confirmation)."""
        result = self.double_bottom(candles, tolerance)
        if result is None:
            return None
        closes = _closes(candles)
        if closes[-1] > result["neckline"]:
            result["name"] = "W Pattern"
            result["confidence"] = min(result["confidence"] + 0.05, 0.92)
            result["description"] = "W breakout above neckline confirmed"
            return result
        return None

    def m_pattern(self, candles: List[Dict[str, Any]], tolerance: float = 0.004) -> Optional[Dict[str, Any]]:
        """M pattern (Double Top variant with momentum confirmation)."""
        result = self.double_top(candles, tolerance)
        if result is None:
            return None
        closes = _closes(candles)
        if closes[-1] < result["neckline"]:
            result["name"] = "M Pattern"
            result["confidence"] = min(result["confidence"] + 0.05, 0.92)
            result["description"] = "M breakdown below neckline confirmed"
            return result
        return None

    def detect_all(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for detector in [
            self.double_top,
            self.double_bottom,
            self.head_and_shoulders,
            self.inverse_head_and_shoulders,
            self.ascending_triangle,
            self.descending_triangle,
            self.w_pattern,
            self.m_pattern,
        ]:
            try:
                result = detector(candles)
                if result:
                    results.append(result)
            except Exception:
                pass
        return results


chart_detector = ChartPatternDetector()
