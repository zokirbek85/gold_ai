"""
Smart Money Concepts analysis service.
Detects Order Blocks, FVG, BOS, and Liquidity Zones.
Returns data shaped for the frontend API contract.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _highs(c: list) -> list:
    return [float(x["high"]) for x in c]


def _lows(c: list) -> list:
    return [float(x["low"]) for x in c]


def _closes(c: list) -> list:
    return [float(x["close"]) for x in c]


def _opens(c: list) -> list:
    return [float(x["open"]) for x in c]


def _atr(candles: list, n: int = 14) -> float:
    if len(candles) < n + 1:
        return 1.0
    h, l, c = _highs(candles), _lows(candles), _closes(candles)
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(candles))]
    val = sum(trs[:n]) / n
    for tr in trs[n:]:
        val = (val * (n - 1) + tr) / n
    return val


def detect_order_blocks(candles: list) -> List[Dict[str, Any]]:
    """Last 5 valid bullish/bearish order blocks."""
    if len(candles) < 10:
        return []

    atr = _atr(candles)
    strong_move = 1.5 * atr
    opens = _opens(candles)
    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)

    obs: List[Dict[str, Any]] = []
    window = candles[-100:]
    opens_w = _opens(window)
    closes_w = _closes(window)
    highs_w = _highs(window)
    lows_w = _lows(window)
    n = len(window)

    for i in range(1, n - 3):
        # Bullish OB: bearish candle before a strong bullish move
        if closes_w[i] < opens_w[i]:
            future_closes = closes_w[i + 1 : min(i + 4, n)]
            if future_closes and (max(future_closes) - closes_w[i]) > strong_move:
                obs.append(
                    {
                        "type": "bullish",
                        "high": round(highs_w[i], 4),
                        "low": round(lows_w[i], 4),
                        "description": f"Bullish OB {lows_w[i]:.2f}–{highs_w[i]:.2f}",
                    }
                )
        # Bearish OB: bullish candle before a strong bearish move
        if closes_w[i] > opens_w[i]:
            future_closes = closes_w[i + 1 : min(i + 4, n)]
            if future_closes and (closes_w[i] - min(future_closes)) > strong_move:
                obs.append(
                    {
                        "type": "bearish",
                        "high": round(highs_w[i], 4),
                        "low": round(lows_w[i], 4),
                        "description": f"Bearish OB {lows_w[i]:.2f}–{highs_w[i]:.2f}",
                    }
                )

    return obs[-5:]


def detect_fvg(candles: list) -> List[Dict[str, Any]]:
    """Unfilled Fair Value Gaps."""
    if len(candles) < 3:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    current_price = closes[-1]
    fvgs: List[Dict[str, Any]] = []

    for i in range(2, len(candles)):
        # Bullish FVG: candle[i].low > candle[i-2].high
        if lows[i] > highs[i - 2]:
            gap_low = highs[i - 2]
            gap_high = lows[i]
            # Only include unfilled (price hasn't returned)
            if current_price > gap_low:
                fvgs.append(
                    {
                        "type": "bullish",
                        "high": round(gap_high, 4),
                        "low": round(gap_low, 4),
                        "filled": current_price < gap_low,
                        "description": f"Bullish FVG {gap_low:.2f}–{gap_high:.2f}",
                    }
                )
        # Bearish FVG: candle[i].high < candle[i-2].low
        if highs[i] < lows[i - 2]:
            gap_high = lows[i - 2]
            gap_low = highs[i]
            if current_price < gap_high:
                fvgs.append(
                    {
                        "type": "bearish",
                        "high": round(gap_high, 4),
                        "low": round(gap_low, 4),
                        "filled": current_price > gap_high,
                        "description": f"Bearish FVG {gap_low:.2f}–{gap_high:.2f}",
                    }
                )

    return fvgs[-8:]


def detect_bos(candles: list, swing_len: int = 5) -> List[Dict[str, Any]]:
    """Break of Structure events (last 3)."""
    if len(candles) < swing_len * 3:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    events: List[Dict[str, Any]] = []

    swing_highs: List[tuple] = []
    swing_lows: List[tuple] = []

    for i in range(swing_len, len(candles) - swing_len):
        if highs[i] == max(highs[i - swing_len : i + swing_len + 1]):
            swing_highs.append((i, highs[i]))
        if lows[i] == min(lows[i - swing_len : i + swing_len + 1]):
            swing_lows.append((i, lows[i]))

    if swing_highs:
        last_sh_idx, last_sh_val = swing_highs[-1]
        for i in range(last_sh_idx + 1, len(candles)):
            if closes[i] > last_sh_val:
                events.append(
                    {
                        "direction": "bullish",
                        "level": round(last_sh_val, 4),
                        "description": f"BOS bullish: broke {last_sh_val:.2f}",
                    }
                )
                break

    if swing_lows:
        last_sl_idx, last_sl_val = swing_lows[-1]
        for i in range(last_sl_idx + 1, len(candles)):
            if closes[i] < last_sl_val:
                events.append(
                    {
                        "direction": "bearish",
                        "level": round(last_sl_val, 4),
                        "description": f"BOS bearish: broke {last_sl_val:.2f}",
                    }
                )
                break

    return events[-3:]


def detect_liquidity_zones(candles: list) -> List[Dict[str, Any]]:
    """Equal highs/lows and psychological round numbers."""
    if len(candles) < 20:
        return []

    highs = _highs(candles[-50:])
    lows = _lows(candles[-50:])
    current = _closes(candles)[-1]
    zones: List[Dict[str, Any]] = []

    max_h = max(highs)
    near_highs = [h for h in highs if abs(h - max_h) / (max_h + 1e-9) < 0.001]
    if len(near_highs) >= 2:
        zones.append(
            {
                "type": "sell_side",
                "level": round(max_h, 2),
                "description": f"Equal Highs sell-side liquidity at {max_h:.2f}",
            }
        )

    min_l = min(lows)
    near_lows = [l for l in lows if abs(l - min_l) / (min_l + 1e-9) < 0.001]
    if len(near_lows) >= 2:
        zones.append(
            {
                "type": "buy_side",
                "level": round(min_l, 2),
                "description": f"Equal Lows buy-side liquidity at {min_l:.2f}",
            }
        )

    # Psychological round number levels
    for rnd in [50, 100]:
        lower = (current // rnd) * rnd
        upper = lower + rnd
        if abs(current - lower) / (lower + 1e-9) < 0.005:
            zones.append({"type": "psychological", "level": round(lower, 2), "description": f"Round {rnd} level at {lower:.2f}"})
        if abs(current - upper) / (upper + 1e-9) < 0.005:
            zones.append({"type": "psychological", "level": round(upper, 2), "description": f"Round {rnd} level at {upper:.2f}"})

    return zones[:5]


def analyze(candles: list) -> Dict[str, Any]:
    """Full SMC analysis shaped for the /smc/analyze endpoint."""
    if not candles:
        return {"direction": "neutral", "bias": "neutral", "order_blocks": [], "fvg": [], "liquidity_zones": [], "bos": []}

    obs = detect_order_blocks(candles)
    fvg = detect_fvg(candles)
    bos = detect_bos(candles)
    liq = detect_liquidity_zones(candles)
    score_data = score(candles)

    # market_structure = BOS events + liquidity zones in a unified list
    market_structure = []
    for b in bos:
        market_structure.append({
            "type": "BOS",
            "direction": b.get("direction", "neutral"),
            "description": b.get("description", ""),
            "level": b.get("level"),
        })
    for lz in liq:
        direction = "bearish" if lz.get("type") == "sell_side" else (
                    "bullish" if lz.get("type") == "buy_side" else "neutral")
        market_structure.append({
            "type": "Liquidity",
            "direction": direction,
            "description": lz.get("description", ""),
            "level": lz.get("level"),
        })

    return {
        "direction": score_data["direction"],
        "bias": score_data["direction"],
        "order_blocks": obs,
        "fvg": fvg,
        "liquidity_zones": liq,
        "bos": bos,
        "market_structure": market_structure,
    }


def score(candles: list) -> Dict[str, Any]:
    """SMC score 0-100, shaped for /smc/score endpoint."""
    if len(candles) < 10:
        return {"direction": "neutral", "score": 50, "events": 0, "components": {"order_block": 50, "fvg": 50, "bos": 50, "liquidity": 50}}

    s = 50.0
    closes = _closes(candles)
    current = closes[-1]
    events = 0

    obs = detect_order_blocks(candles)
    ob_score = 50.0
    for ob in obs:
        if ob["type"] == "bullish" and current > ob["low"]:
            s += 15
            ob_score = min(100, ob_score + 20)
        elif ob["type"] == "bearish" and current < ob["high"]:
            s -= 15
            ob_score = max(0, ob_score - 20)
        events += 1

    fvgs = detect_fvg(candles)
    fvg_score = 50.0
    for fvg in fvgs:
        dist = abs(current - (fvg["high"] + fvg["low"]) / 2) / (current + 1e-9)
        if dist < 0.005:
            if fvg["type"] == "bullish":
                s += 10
                fvg_score = min(100, fvg_score + 15)
            else:
                s -= 10
                fvg_score = max(0, fvg_score - 15)
            events += 1

    bos_list = detect_bos(candles)
    bos_score = 50.0
    for b in bos_list[-5:]:
        if b["direction"] == "bullish":
            s += 10
            bos_score = min(100, bos_score + 15)
        else:
            s -= 10
            bos_score = max(0, bos_score - 15)
        events += 1

    liq_score = 50.0
    liq = detect_liquidity_zones(candles)
    for zone in liq:
        if zone["type"] == "buy_side" and current > zone["level"]:
            s += 5
            liq_score = min(100, liq_score + 10)
        elif zone["type"] == "sell_side" and current < zone["level"]:
            s -= 5
            liq_score = max(0, liq_score - 10)

    s = max(0, min(100, s))
    if s > 55:
        direction = "bullish"
    elif s < 45:
        direction = "bearish"
    else:
        direction = "neutral"

    return {
        "direction": direction,
        "score": round(s, 1),
        "events": events,
        "components": {
            "order_block": round(ob_score, 1),
            "fvg": round(fvg_score, 1),
            "bos": round(bos_score, 1),
            "liquidity": round(liq_score, 1),
        },
    }
