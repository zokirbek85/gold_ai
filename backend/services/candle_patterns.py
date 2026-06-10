"""
Candle pattern detector — 14 canonical patterns for GOLD_AI engine.
Returns {pattern, strength, confirmed} for the most recent candle.
strength is 0.0–1.0; confirmed is True when the current candle closed.
"""
from __future__ import annotations
from typing import Any, Dict, List

_STRONG = {"engulfing_bull", "engulfing_bear", "pinbar_bull", "pinbar_bear",
           "morning_star", "evening_star", "three_white_soldiers", "three_black_crows"}
_MODERATE = {"hammer", "shooting_star", "tweezer_top", "tweezer_bottom"}


def detect_pattern(candles: List[Dict]) -> Dict[str, Any]:
    """Identify the dominant pattern on the most recent closed candle."""
    if len(candles) < 3:
        return {"pattern": "none", "strength": 0.0, "confirmed": False}

    c0 = candles[-1]
    c1 = candles[-2]
    c2 = candles[-3]

    o0, h0, l0, cl0 = float(c0["open"]), float(c0["high"]), float(c0["low"]), float(c0["close"])
    o1, h1, l1, cl1 = float(c1["open"]), float(c1["high"]), float(c1["low"]), float(c1["close"])
    o2, h2, l2, cl2 = float(c2["open"]), float(c2["high"]), float(c2["low"]), float(c2["close"])

    rng0 = max(h0 - l0, 1e-9)
    body0 = abs(cl0 - o0)
    uw0 = h0 - max(o0, cl0)  # upper wick
    lw0 = min(o0, cl0) - l0  # lower wick

    rng1 = max(h1 - l1, 1e-9)
    body1 = abs(cl1 - o1)
    uw1 = h1 - max(o1, cl1)
    lw1 = min(o1, cl1) - l1

    # ── Doji ──────────────────────────────────────────────────────────────────
    if body0 / rng0 < 0.10:
        strength = round(1.0 - (body0 / rng0) / 0.10, 2)
        return {"pattern": "doji", "strength": strength, "confirmed": True}

    # ── Engulfing ─────────────────────────────────────────────────────────────
    bull_eng = (cl1 < o1 and cl0 > o0 and o0 <= cl1 and cl0 >= o1)
    bear_eng = (cl1 > o1 and cl0 < o0 and o0 >= cl1 and cl0 <= o1)
    if bull_eng:
        return {"pattern": "engulfing_bull",
                "strength": round(min(1.0, body0 / rng1), 2), "confirmed": True}
    if bear_eng:
        return {"pattern": "engulfing_bear",
                "strength": round(min(1.0, body0 / rng1), 2), "confirmed": True}

    # ── Pinbar ────────────────────────────────────────────────────────────────
    if lw0 > 2.0 * body0 and uw0 < body0 * 0.6 and body0 / rng0 < 0.40:
        return {"pattern": "pinbar_bull",
                "strength": round(min(1.0, lw0 / rng0), 2), "confirmed": True}
    if uw0 > 2.0 * body0 and lw0 < body0 * 0.6 and body0 / rng0 < 0.40:
        return {"pattern": "pinbar_bear",
                "strength": round(min(1.0, uw0 / rng0), 2), "confirmed": True}

    # ── Hammer / Shooting Star (less strict than pinbar) ─────────────────────
    if lw0 >= 2.0 * body0 and uw0 <= 0.15 * rng0 and cl0 > o0:
        return {"pattern": "hammer",
                "strength": round(lw0 / rng0, 2), "confirmed": True}
    if uw0 >= 2.0 * body0 and lw0 <= 0.15 * rng0 and cl0 < o0:
        return {"pattern": "shooting_star",
                "strength": round(uw0 / rng0, 2), "confirmed": True}

    # ── Three white soldiers / three black crows ──────────────────────────────
    if (cl2 > o2 and cl1 > o1 and cl0 > o0 and cl2 < cl1 < cl0
            and body1 > rng1 * 0.50 and body0 > rng0 * 0.50):
        return {"pattern": "three_white_soldiers", "strength": 0.85, "confirmed": True}
    if (cl2 < o2 and cl1 < o1 and cl0 < o0 and cl2 > cl1 > cl0
            and body1 > rng1 * 0.50 and body0 > rng0 * 0.50):
        return {"pattern": "three_black_crows", "strength": 0.85, "confirmed": True}

    # ── Morning star / evening star ───────────────────────────────────────────
    if (cl2 < o2 and body1 / rng1 < 0.30 and cl0 > o0
            and cl0 > (o2 + cl2) / 2.0):
        return {"pattern": "morning_star", "strength": 0.80, "confirmed": True}
    if (cl2 > o2 and body1 / rng1 < 0.30 and cl0 < o0
            and cl0 < (o2 + cl2) / 2.0):
        return {"pattern": "evening_star", "strength": 0.80, "confirmed": True}

    # ── Inside bar ────────────────────────────────────────────────────────────
    if h0 < h1 and l0 > l1:
        compression = 1.0 - (h0 - l0) / (h1 - l1 + 1e-9)
        return {"pattern": "inside_bar",
                "strength": round(max(0.0, compression), 2), "confirmed": False}

    # ── Tweezer top / bottom ──────────────────────────────────────────────────
    if abs(h0 - h1) / (h1 + 1e-9) < 0.0015 and cl1 > o1 and cl0 < o0:
        return {"pattern": "tweezer_top", "strength": 0.70, "confirmed": True}
    if abs(l0 - l1) / (l1 + 1e-9) < 0.0015 and cl1 < o1 and cl0 > o0:
        return {"pattern": "tweezer_bottom", "strength": 0.70, "confirmed": True}

    return {"pattern": "none", "strength": 0.0, "confirmed": False}


def pattern_category(name: str) -> str:
    """'strong' | 'moderate' | 'weak'"""
    if name in _STRONG:
        return "strong"
    if name in _MODERATE:
        return "moderate"
    return "weak"
