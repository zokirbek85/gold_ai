"""
Smart Money Concepts engine.
Detects: Market Structure (BOS/CHOCH), Liquidity, Order Blocks, FVG, Premium/Discount zones.
All methods accept a list of OHLC dicts (oldest → newest).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _highs(c: List[Dict[str, Any]]) -> List[float]:
    return [float(x["high"]) for x in c]


def _lows(c: List[Dict[str, Any]]) -> List[float]:
    return [float(x["low"]) for x in c]


def _closes(c: List[Dict[str, Any]]) -> List[float]:
    return [float(x["close"]) for x in c]


def _opens(c: List[Dict[str, Any]]) -> List[float]:
    return [float(x["open"]) for x in c]


class SMCEngine:
    """Detect Smart Money Concepts events from OHLC candle sequences."""

    # ------------------------------------------------------------------ Market Structure
    def market_structure(self, candles: List[Dict[str, Any]], swing_len: int = 5) -> List[Dict[str, Any]]:
        """
        Detect BOS (Break of Structure) and CHOCH (Change of Character).
        swing_len: number of bars each side for local swing identification.
        """
        if len(candles) < swing_len * 3:
            return []
        highs = _highs(candles)
        lows = _lows(candles)
        closes = _closes(candles)
        events: List[Dict[str, Any]] = []

        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []

        for i in range(swing_len, len(candles) - swing_len):
            if highs[i] == max(highs[i - swing_len : i + swing_len + 1]):
                swing_highs.append((i, highs[i]))
            if lows[i] == min(lows[i - swing_len : i + swing_len + 1]):
                swing_lows.append((i, lows[i]))

        # BOS Bullish: close above last swing high
        if swing_highs:
            last_sh_idx, last_sh_val = swing_highs[-1]
            for i in range(last_sh_idx + 1, len(candles)):
                if closes[i] > last_sh_val:
                    # Determine if it's a CHOCH or BOS
                    # CHOCH: prior trend was bearish (last swing low broken)
                    event_type = "BOS"
                    if len(swing_lows) >= 2 and swing_lows[-1][1] < swing_lows[-2][1]:
                        event_type = "CHOCH"
                    events.append({
                        "type": event_type,
                        "direction": "bullish",
                        "broken_level": last_sh_val,
                        "bar_index": i,
                        "description": f"{event_type} — close above swing high {last_sh_val:.2f}",
                    })
                    break

        # BOS Bearish: close below last swing low
        if swing_lows:
            last_sl_idx, last_sl_val = swing_lows[-1]
            for i in range(last_sl_idx + 1, len(candles)):
                if closes[i] < last_sl_val:
                    event_type = "BOS"
                    if len(swing_highs) >= 2 and swing_highs[-1][1] > swing_highs[-2][1]:
                        event_type = "CHOCH"
                    events.append({
                        "type": event_type,
                        "direction": "bearish",
                        "broken_level": last_sl_val,
                        "bar_index": i,
                        "description": f"{event_type} — close below swing low {last_sl_val:.2f}",
                    })
                    break

        return events

    # ------------------------------------------------------------------ Liquidity Levels
    def liquidity_levels(
        self, candles: List[Dict[str, Any]], lookback: int = 20, tolerance: float = 0.001
    ) -> List[Dict[str, Any]]:
        """Detect Equal Highs (EQH) and Equal Lows (EQL) — liquidity pools."""
        if len(candles) < lookback:
            return []
        highs = _highs(candles)
        lows = _lows(candles)
        events: List[Dict[str, Any]] = []

        # Equal Highs
        recent_highs = highs[-lookback:]
        max_h = max(recent_highs)
        near_equal = [h for h in recent_highs if abs(h - max_h) / max_h < tolerance]
        if len(near_equal) >= 2:
            events.append({
                "type": "Equal Highs",
                "direction": "bearish",
                "level": max_h,
                "count": len(near_equal),
                "description": f"Equal Highs liquidity pool at {max_h:.2f} — stop hunt likely",
            })

        # Equal Lows
        recent_lows = lows[-lookback:]
        min_l = min(recent_lows)
        near_equal_l = [l for l in recent_lows if abs(l - min_l) / (abs(min_l) + 1e-9) < tolerance]
        if len(near_equal_l) >= 2:
            events.append({
                "type": "Equal Lows",
                "direction": "bullish",
                "level": min_l,
                "count": len(near_equal_l),
                "description": f"Equal Lows liquidity pool at {min_l:.2f} — stop hunt likely",
            })

        return events

    def liquidity_sweep(
        self, candles: List[Dict[str, Any]], lookback: int = 20, tolerance: float = 0.001
    ) -> List[Dict[str, Any]]:
        """Detect a wick that swept below/above a liquidity level then reversed."""
        if len(candles) < lookback + 2:
            return []
        highs = _highs(candles)
        lows = _lows(candles)
        closes = _closes(candles)
        events: List[Dict[str, Any]] = []

        prior_high = max(highs[-lookback - 1 : -1])
        prior_low = min(lows[-lookback - 1 : -1])
        last = candles[-1]

        # Bearish sweep: wick above prior high but closes below it
        if float(last["high"]) > prior_high and float(last["close"]) < prior_high:
            events.append({
                "type": "Liquidity Sweep",
                "direction": "bearish",
                "swept_level": prior_high,
                "description": f"Wick swept above {prior_high:.2f} then rejected — bearish",
            })

        # Bullish sweep: wick below prior low but closes above it
        if float(last["low"]) < prior_low and float(last["close"]) > prior_low:
            events.append({
                "type": "Liquidity Sweep",
                "direction": "bullish",
                "swept_level": prior_low,
                "description": f"Wick swept below {prior_low:.2f} then rejected — bullish",
            })

        return events

    # ------------------------------------------------------------------ Order Blocks
    def order_blocks(
        self, candles: List[Dict[str, Any]], lookback: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Bullish OB: last bearish candle before a strong bullish BOS.
        Bearish OB: last bullish candle before a strong bearish BOS.
        """
        if len(candles) < 10:
            return []
        opens = _opens(candles)
        closes = _closes(candles)
        highs = _highs(candles)
        lows = _lows(candles)
        events: List[Dict[str, Any]] = []
        window = candles[-lookback:] if len(candles) >= lookback else candles

        for i in range(2, len(window) - 2):
            c = window[i]
            o_c, c_c = float(c["open"]), float(c["close"])
            # Potential Bullish OB: bearish candle followed by strong bullish move
            if c_c < o_c:  # bearish candle
                subsequent_closes = [float(window[j]["close"]) for j in range(i + 1, min(i + 5, len(window)))]
                if subsequent_closes and max(subsequent_closes) > float(c["high"]) * 1.002:
                    events.append({
                        "type": "Bullish Order Block",
                        "direction": "bullish",
                        "ob_high": float(c["high"]),
                        "ob_low": float(c["low"]),
                        "ob_open": o_c,
                        "ob_close": c_c,
                        "bar_index": i,
                        "description": f"Bullish OB: zone {float(c['low']):.2f}–{float(c['high']):.2f}",
                    })
            # Potential Bearish OB: bullish candle followed by strong bearish move
            if c_c > o_c:  # bullish candle
                subsequent_closes = [float(window[j]["close"]) for j in range(i + 1, min(i + 5, len(window)))]
                if subsequent_closes and min(subsequent_closes) < float(c["low"]) * 0.998:
                    events.append({
                        "type": "Bearish Order Block",
                        "direction": "bearish",
                        "ob_high": float(c["high"]),
                        "ob_low": float(c["low"]),
                        "ob_open": o_c,
                        "ob_close": c_c,
                        "bar_index": i,
                        "description": f"Bearish OB: zone {float(c['low']):.2f}–{float(c['high']):.2f}",
                    })

        # Return only the most recent OBs (avoid flooding)
        return events[-4:]

    # ------------------------------------------------------------------ Fair Value Gaps
    def fair_value_gaps(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bullish FVG: gap between candle[i-2] high and candle[i] low (3-candle pattern).
        Bearish FVG: gap between candle[i-2] low and candle[i] high.
        """
        if len(candles) < 3:
            return []
        events: List[Dict[str, Any]] = []
        highs = _highs(candles)
        lows = _lows(candles)

        for i in range(2, len(candles)):
            # Bullish FVG
            if lows[i] > highs[i - 2]:
                events.append({
                    "type": "Bullish FVG",
                    "direction": "bullish",
                    "fvg_high": lows[i],
                    "fvg_low": highs[i - 2],
                    "bar_index": i,
                    "description": f"Bullish FVG: imbalance {highs[i-2]:.2f}–{lows[i]:.2f}",
                })
            # Bearish FVG
            if highs[i] < lows[i - 2]:
                events.append({
                    "type": "Bearish FVG",
                    "direction": "bearish",
                    "fvg_high": lows[i - 2],
                    "fvg_low": highs[i],
                    "bar_index": i,
                    "description": f"Bearish FVG: imbalance {highs[i]:.2f}–{lows[i-2]:.2f}",
                })

        return events[-6:]

    # ------------------------------------------------------------------ Premium / Discount
    def premium_discount(self, candles: List[Dict[str, Any]], lookback: int = 50) -> Dict[str, Any]:
        """
        Divide the recent swing range into Premium (above 50%), Discount (below 50%), Equilibrium.
        """
        if len(candles) < lookback:
            lookback = len(candles)
        window = candles[-lookback:]
        highs = _highs(window)
        lows = _lows(window)
        swing_high = max(highs)
        swing_low = min(lows)
        equilibrium = (swing_high + swing_low) / 2
        current_price = float(candles[-1]["close"])
        zone = "premium" if current_price > equilibrium else "discount"
        pct = (current_price - swing_low) / (swing_high - swing_low + 1e-9) * 100

        return {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "equilibrium": equilibrium,
            "current_price": current_price,
            "zone": zone,
            "pct_of_range": round(pct, 1),
            "description": f"Price at {pct:.1f}% of range — {zone} zone",
        }

    # ------------------------------------------------------------------ Full analysis
    def analyze(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "market_structure": self.market_structure(candles),
            "liquidity_levels": self.liquidity_levels(candles),
            "liquidity_sweeps": self.liquidity_sweep(candles),
            "order_blocks": self.order_blocks(candles),
            "fair_value_gaps": self.fair_value_gaps(candles),
            "premium_discount": self.premium_discount(candles),
        }

    def score(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate SMC signals into a single directional score 0-100.
        Returns: {"direction": "bullish"|"bearish"|"neutral", "score": float, "events": int}
        """
        analysis = self.analyze(candles)
        bullish_signals = 0
        bearish_signals = 0
        total = 0

        for ms in analysis["market_structure"]:
            total += 1
            if ms["direction"] == "bullish":
                bullish_signals += 2
            else:
                bearish_signals += 2

        for ll in analysis["liquidity_levels"]:
            total += 1
            if ll["direction"] == "bullish":
                bullish_signals += 1
            else:
                bearish_signals += 1

        for sw in analysis["liquidity_sweeps"]:
            total += 1
            if sw["direction"] == "bullish":
                bullish_signals += 2
            else:
                bearish_signals += 2

        for ob in analysis["order_blocks"]:
            total += 1
            if ob["direction"] == "bullish":
                bullish_signals += 1.5
            else:
                bearish_signals += 1.5

        for fvg in analysis["fair_value_gaps"]:
            total += 1
            if fvg["direction"] == "bullish":
                bullish_signals += 1
            else:
                bearish_signals += 1

        pd = analysis["premium_discount"]
        if pd["zone"] == "discount":
            bullish_signals += 1
        else:
            bearish_signals += 1
        total += 1

        total_weight = bullish_signals + bearish_signals
        if total_weight == 0:
            return {"direction": "neutral", "score": 50.0, "events": total}

        bull_pct = bullish_signals / total_weight * 100
        if bull_pct > 55:
            direction = "bullish"
            score = bull_pct
        elif bull_pct < 45:
            direction = "bearish"
            score = 100 - bull_pct
        else:
            direction = "neutral"
            score = 50.0

        return {"direction": direction, "score": round(score, 1), "events": total}


smc_engine = SMCEngine()
