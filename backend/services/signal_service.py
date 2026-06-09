"""
Signal generation — 5-component weighted model.
  Technical (35%) + SMC (25%) + ML (20%) + News (10%) + Economic (10%)
SL/TP placed at structural swing levels; ATR used as fallback.
"""
from __future__ import annotations

import logging
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import settings
from services.indicator_service import compute_snapshot, build_ml_features
from services import smc_service

log = logging.getLogger(__name__)

_W_TECH = 0.35
_W_SMC  = 0.25
_W_ML   = 0.20
_W_NEWS = 0.10
_W_ECON = 0.10

_FEATURE_NAMES = [
    "rsi", "macd", "macd_signal", "macd_hist",
    "ema_20_dist", "ema_50_dist", "ema_200_dist",
    "atr_pct", "bb_position",
    "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "volume_ratio", "smc_score",
]


# ── structural levels ─────────────────────────────────────────────────────────

def _swing_highs(candles: List[Dict], lookback: int = 3) -> List[float]:
    result = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        h = float(candles[i]["high"])
        if (all(h >= float(candles[j]["high"]) for j in range(i - lookback, i)) and
                all(h >= float(candles[j]["high"]) for j in range(i + 1, i + lookback + 1))):
            result.append(h)
    return sorted(set(result))


def _swing_lows(candles: List[Dict], lookback: int = 3) -> List[float]:
    result = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        lo = float(candles[i]["low"])
        if (all(lo <= float(candles[j]["low"]) for j in range(i - lookback, i)) and
                all(lo <= float(candles[j]["low"]) for j in range(i + 1, i + lookback + 1))):
            result.append(lo)
    return sorted(set(result))


def _calc_atr(candles: List[Dict], n: int = 14) -> float:
    if len(candles) < n + 1:
        return float(candles[-1]["close"]) * 0.005
    trs = [
        max(
            float(c["high"]) - float(c["low"]),
            abs(float(c["high"]) - float(candles[i - 1]["close"])),
            abs(float(c["low"])  - float(candles[i - 1]["close"])),
        )
        for i, c in enumerate(candles) if i > 0
    ]
    v = sum(trs[:n]) / n
    for tr in trs[n:]:
        v = (v * (n - 1) + tr) / n
    return v


def _compute_sl_tp(
    signal_type: str,
    entry: float,
    candles: List[Dict],
    atr_val: float,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    if signal_type == "NEUTRAL":
        return None, None, None, None

    window = candles[-60:]
    lows  = _swing_lows(window)
    highs = _swing_highs(window)
    max_sl = 2.5 * atr_val

    if signal_type == "BUY":
        sl_cands = [l for l in reversed(lows) if l < entry]
        if sl_cands:
            sl = sl_cands[0]
            if (entry - sl) > max_sl:
                sl = entry - max_sl
        else:
            sl = entry - 1.5 * atr_val

        tp_cands = [h for h in highs if h > entry * 1.0003]
        tp1 = tp_cands[0] if len(tp_cands) > 0 else entry + 1.0 * atr_val
        tp2 = tp_cands[1] if len(tp_cands) > 1 else entry + 2.0 * atr_val
        tp3 = tp_cands[2] if len(tp_cands) > 2 else entry + 3.0 * atr_val

    else:  # SELL
        sl_cands = [h for h in highs if h > entry]
        if sl_cands:
            sl = sl_cands[0]
            if (sl - entry) > max_sl:
                sl = entry + max_sl
        else:
            sl = entry + 1.5 * atr_val

        tp_cands = [l for l in reversed(lows) if l < entry * 0.9997]
        tp1 = tp_cands[0] if len(tp_cands) > 0 else entry - 1.0 * atr_val
        tp2 = tp_cands[1] if len(tp_cands) > 1 else entry - 2.0 * atr_val
        tp3 = tp_cands[2] if len(tp_cands) > 2 else entry - 3.0 * atr_val

    return (
        round(sl,  4),
        round(tp1, 4),
        round(tp2, 4),
        round(tp3, 4),
    )


# ── score components ──────────────────────────────────────────────────────────

def _technical_score(snap: Dict, candles: List[Dict]) -> Tuple[float, List[str]]:
    bull = 0.0
    bear = 0.0
    parts: List[str] = []

    rsi = snap.get("rsi") or 50.0
    if rsi < 30:
        bull += 30; parts.append(f"RSI {rsi:.1f} oversold")
    elif rsi < 45:
        bull += 15; parts.append(f"RSI {rsi:.1f} weak")
    elif rsi > 70:
        bear += 30; parts.append(f"RSI {rsi:.1f} overbought")
    elif rsi > 55:
        bear += 15; parts.append(f"RSI {rsi:.1f} strong")

    macd     = snap.get("macd")
    macd_sig = snap.get("macd_signal")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig:
            bull += 25; parts.append("MACD bullish cross")
        else:
            bear += 25; parts.append("MACD bearish cross")
        bull += 5 if macd > 0 else 0
        bear += 5 if macd < 0 else 0

    close  = float(candles[-1]["close"])
    ema200 = snap.get("ema_200")
    if ema200:
        if close > ema200:
            bull += 25; parts.append("Above EMA200")
        else:
            bear += 25; parts.append("Below EMA200")

    bb_upper = snap.get("bb_upper")
    bb_lower = snap.get("bb_lower")
    if bb_lower and close < bb_lower:
        bull += 15; parts.append("Below BB lower")
    elif bb_upper and close > bb_upper:
        bear += 15; parts.append("Above BB upper")

    score = round(bull / (bull + bear + 1e-9) * 100, 1)
    return score, parts


def _smc_score(candles: List[Dict]) -> Tuple[float, List[str]]:
    val = float(smc_service.score(candles).get("score", 50))
    parts = [f"SMC {'bull' if val > 60 else 'bear' if val < 40 else 'neutral'} {val:.0f}"]
    return val, parts


def _ml_score(symbol: str, timeframe: str, candles: List[Dict]) -> Tuple[float, List[str]]:
    path = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")
    if not os.path.exists(path):
        return 50.0, ["No ML model"]
    try:
        with open(path, "rb") as f:
            model_data = pickle.load(f)
    except Exception:
        return 50.0, ["ML load error"]

    smc_val = smc_service.score(candles[-100:]).get("score", 50) if len(candles) >= 100 else 50.0
    feats   = build_ml_features(candles, smc_score=smc_val)
    if not feats:
        return 50.0, ["ML features unavailable"]

    x     = np.array([[feats.get(k, 0.0) for k in _FEATURE_NAMES]])
    model = model_data["model"]
    proba = model.predict_proba(x)[0]
    pct   = {int(cls): float(p) * 100 for cls, p in zip(model.classes_, proba)}
    buy_p  = pct.get(1,  0.0)
    sell_p = pct.get(-1, 0.0)

    # buy=100% → score=100; sell=100% → score=0; equal → 50
    score = round(max(0.0, min(100.0, 50 + (buy_p - sell_p) / 2)), 1)
    acc   = round(model_data.get("accuracy", 0) * 100, 1)
    parts = [f"ML buy {buy_p:.0f}% sell {sell_p:.0f}% (acc {acc:.0f}%)"]
    return score, parts


# ── public API ────────────────────────────────────────────────────────────────

def generate_signal(
    candles: List[Dict[str, Any]],
    symbol: str = "XAUUSD",
    timeframe: str = "60",
    news_score: float = 50.0,
    economic_score: float = 50.0,
    news_parts: Optional[List[str]] = None,
    econ_parts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if len(candles) < 50:
        return _empty_signal(symbol, timeframe)

    snap    = compute_snapshot(candles)
    close   = float(candles[-1]["close"])
    atr_val = snap.get("atr") or _calc_atr(candles)

    tech_score, tech_parts = _technical_score(snap, candles)
    smc_s,      smc_parts  = _smc_score(candles)
    ml_s,       ml_parts   = _ml_score(symbol, timeframe, candles)

    combined = round(
        _W_TECH * tech_score +
        _W_SMC  * smc_s +
        _W_ML   * ml_s +
        _W_NEWS * news_score +
        _W_ECON * economic_score,
        1,
    )

    if combined >= 62:
        signal_type = "BUY"
    elif combined <= 38:
        signal_type = "SELL"
    else:
        signal_type = "NEUTRAL"

    confidence = round(min(abs(combined - 50) * 3.33, 100), 1)

    stop_loss, tp1, take_profit, tp3 = _compute_sl_tp(signal_type, close, candles, atr_val)

    if stop_loss and take_profit and signal_type != "NEUTRAL":
        rr = round(abs(take_profit - close) / (abs(close - stop_loss) + 1e-9), 2)
    else:
        rr = None

    all_parts = (tech_parts + smc_parts + ml_parts +
                 (news_parts or []) + (econ_parts or []))
    reasoning = " | ".join(all_parts[:6]) if all_parts else None

    return {
        "symbol":          symbol,
        "timeframe":       timeframe,
        "signal_type":     signal_type,
        "entry":           round(close, 4),
        "stop_loss":       stop_loss,
        "take_profit":     take_profit,
        "tp1":             tp1,
        "tp3":             tp3,
        "rr":              rr,
        "confidence":      confidence,
        "technical_score": tech_score,
        "smc_score":       round(smc_s, 1),
        "ml_score":        round(ml_s, 1),
        "news_score":      round(news_score, 1),
        "economic_score":  round(economic_score, 1),
        "combined_score":  combined,
        "reasoning":       reasoning,
        "created_at":      datetime.utcnow(),
    }


def enrich_signal(result: Dict[str, Any], account_balance: float = 10000.0) -> Dict[str, Any]:
    """
    Adds lot_size, risk_amount_usd, distance fields, plain_explanation, signal_emoji.
    Mutates and returns result.
    """
    import sys
    import os as _os
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", ".."))
    from src.risk_management.calculator import risk_calculator

    signal_type = result.get("signal_type", "NEUTRAL")
    entry       = result.get("entry")
    stop_loss   = result.get("stop_loss")
    tp1         = result.get("tp1")
    take_profit = result.get("take_profit")  # tp2
    tp3         = result.get("tp3")
    confidence  = result.get("confidence", 0.0) or 0.0
    reasoning   = result.get("reasoning") or ""

    emoji = "🟢" if signal_type == "BUY" else ("🔴" if signal_type == "SELL" else "⚪")
    result["signal_emoji"] = emoji

    if signal_type == "NEUTRAL" or entry is None or stop_loss is None:
        result["lot_size"]         = None
        result["risk_amount_usd"]  = None
        result["sl_distance_pct"]  = None
        result["tp1_distance_pct"] = None
        result["tp2_distance_pct"] = None
        result["tp3_distance_pct"] = None
        result["plain_explanation"] = (
            "⚪ NEUTRAL — Bozor noaniq. Savdo qilmang.\n"
            "⚪ NEUTRAL — Market unclear. Do not trade."
        )
        return result

    sizing    = risk_calculator.position_size(account_balance, entry, stop_loss, symbol=result.get("symbol", "XAUUSD"))
    lot_size  = sizing["lots"]
    risk_usd  = sizing["risk_amount"]
    sl_dist   = abs(entry - stop_loss)
    sl_pct    = round(sl_dist / entry * 100, 3) if entry else 0.0

    def _dist(tp_price):
        return abs(tp_price - entry) if tp_price else 0.0
    def _pct(tp_price):
        return round(abs(tp_price - entry) / entry * 100, 3) if tp_price and entry else 0.0

    result["lot_size"]         = lot_size
    result["risk_amount_usd"]  = risk_usd
    result["sl_distance_pct"]  = sl_pct
    result["tp1_distance_pct"] = _pct(tp1)
    result["tp2_distance_pct"] = _pct(take_profit)
    result["tp3_distance_pct"] = _pct(tp3)

    def _f(v): return f"{v:.2f}" if v is not None else "—"
    tp1_dist = _dist(tp1)
    tp2_dist = _dist(take_profit)
    tp3_dist = _dist(tp3)

    uz_type = "BUY" if signal_type == "BUY" else "SELL"
    en_type = uz_type

    result["plain_explanation"] = (
        f"{emoji} {uz_type} — Ishonch: {confidence:.0f}%\n"
        f"   Kirish: ${_f(entry)}\n"
        f"   Stop Loss: ${_f(stop_loss)} (−{_f(sl_dist)} | −{sl_pct}%)\n"
        f"   Take Profit 1: ${_f(tp1)} (+{_f(tp1_dist)}) ← 50% yoping\n"
        f"   Take Profit 2: ${_f(take_profit)} (+{_f(tp2_dist)}) ← 30% yoping\n"
        f"   Take Profit 3: ${_f(tp3)} (+{_f(tp3_dist)}) ← qolgan 20%\n"
        f"   Lot hajmi: {lot_size} lot (Hisob: ${account_balance:.0f} | Risk: ${risk_usd:.2f})\n"
        f"   Sabab: {reasoning}\n"
        f"\n"
        f"{emoji} {en_type} — Confidence: {confidence:.0f}%\n"
        f"   Entry: ${_f(entry)}\n"
        f"   Stop Loss: ${_f(stop_loss)} (−{_f(sl_dist)} | −{sl_pct}%)\n"
        f"   Take Profit 1: ${_f(tp1)} (+{_f(tp1_dist)}) ← close 50%\n"
        f"   Take Profit 2: ${_f(take_profit)} (+{_f(tp2_dist)}) ← close 30%\n"
        f"   Take Profit 3: ${_f(tp3)} (+{_f(tp3_dist)}) ← close remaining 20%\n"
        f"   Lot size: {lot_size} lots (Balance: ${account_balance:.0f} | Risk: ${risk_usd:.2f})\n"
        f"   Reason: {reasoning}"
    )
    return result


def _empty_signal(symbol: str, timeframe: str) -> Dict[str, Any]:
    return {
        "symbol": symbol, "timeframe": timeframe,
        "signal_type": "NEUTRAL",
        "entry": None, "stop_loss": None, "take_profit": None,
        "tp1": None, "tp3": None, "rr": None,
        "confidence": 0.0,
        "technical_score": 50.0, "smc_score": 50.0, "ml_score": 50.0,
        "news_score": 50.0, "economic_score": 50.0,
        "reasoning": "Not enough candle data",
        "created_at": datetime.utcnow(),
    }
