"""
Forecast service — computes all chart overlay layers for the forecast page.
Returns structured data consumed by lightweight-charts on the frontend.
"""
from __future__ import annotations

import math
import os
import pickle
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from config import settings
from models.candle import Candle
from models.signal import Signal
from services.indicator_service import _ema_series, build_ml_features
from services.smc_service import detect_order_blocks, detect_fvg
from services import smc_service
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

TF_MINUTES = {"1": 1, "5": 5, "15": 15, "60": 60, "240": 240, "1440": 1440}

_ML_FEATURES = [
    "rsi", "macd", "macd_signal", "macd_hist",
    "ema_20_dist", "ema_50_dist", "ema_200_dist",
    "atr_pct", "bb_position",
    "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "volume_ratio", "smc_score",
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _ts(dt) -> int:
    if isinstance(dt, (int, float)):
        return int(dt)
    return int(dt.timestamp())


def _closes(c): return [float(x["close"]) for x in c]
def _highs(c):  return [float(x["high"])  for x in c]
def _lows(c):   return [float(x["low"])   for x in c]


def _atr(candles: List[Dict], n: int = 14) -> float:
    if len(candles) < n + 1:
        return float(candles[-1]["close"]) * 0.005
    trs = [
        max(float(candles[i]["high"]) - float(candles[i]["low"]),
            abs(float(candles[i]["high"]) - float(candles[i-1]["close"])),
            abs(float(candles[i]["low"])  - float(candles[i-1]["close"])))
        for i in range(1, len(candles))
    ]
    v = sum(trs[:n]) / n
    for tr in trs[n:]:
        v = (v * (n - 1) + tr) / n
    return v


# ── indicator series ──────────────────────────────────────────────────────────

def _ema_line(candles: List[Dict], n: int) -> List[Dict]:
    vals   = _closes(candles)
    series = _ema_series(vals, n)
    return [
        {"time": _ts(candles[i]["timestamp"]), "value": round(v, 4)}
        for i, v in enumerate(series) if v is not None
    ]


def _bb_lines(candles: List[Dict], n: int = 20, k: float = 2.0) -> Dict[str, List[Dict]]:
    closes = _closes(candles)
    upper, middle, lower = [], [], []
    for i in range(n - 1, len(candles)):
        w   = closes[i - n + 1: i + 1]
        mid = sum(w) / n
        std = math.sqrt(sum((x - mid) ** 2 for x in w) / n)
        ts  = _ts(candles[i]["timestamp"])
        upper.append({"time": ts, "value": round(mid + k * std, 4)})
        middle.append({"time": ts, "value": round(mid, 4)})
        lower.append({"time": ts, "value": round(mid - k * std, 4)})
    return {"upper": upper, "middle": middle, "lower": lower}


def _rsi_line(candles: List[Dict], n: int = 14) -> List[Dict]:
    closes = _closes(candles)
    if len(closes) <= n:
        return []
    result = []
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d > 0: gains += d
        else: losses -= d
    ag, al = gains / n, losses / n
    rsi = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    result.append({"time": _ts(candles[n]["timestamp"]), "value": round(rsi, 2)})
    for i in range(n + 1, len(candles)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        rsi = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
        result.append({"time": _ts(candles[i]["timestamp"]), "value": round(rsi, 2)})
    return result


# ── overlay calculations ──────────────────────────────────────────────────────

def _support_resistance(candles: List[Dict], lookback: int = 3) -> List[Dict]:
    n      = len(candles)
    levels = []
    close  = float(candles[-1]["close"])

    for i in range(lookback, n - lookback):
        h  = float(candles[i]["high"])
        lo = float(candles[i]["low"])
        if (all(h  >= float(candles[j]["high"]) for j in range(i - lookback, i)) and
                all(h  >= float(candles[j]["high"]) for j in range(i + 1, i + lookback + 1))):
            levels.append({"level": round(h, 4), "type": "resistance"})
        if (all(lo <= float(candles[j]["low"])  for j in range(i - lookback, i)) and
                all(lo <= float(candles[j]["low"])  for j in range(i + 1, i + lookback + 1))):
            levels.append({"level": round(lo, 4), "type": "support"})

    # Deduplicate close levels (within 0.4%)
    unique: List[Dict] = []
    for lv in sorted(levels, key=lambda x: abs(x["level"] - close)):
        if not any(abs(lv["level"] - u["level"]) / (close + 1e-9) < 0.004 for u in unique):
            unique.append(lv)
    return unique[:8]


def _fibonacci(candles: List[Dict]) -> Dict[str, Any]:
    if len(candles) < 20:
        return {}
    w    = candles[-80:]
    high = max(_highs(w))
    low  = min(_lows(w))
    rng  = high - low
    if rng < 0.001:
        return {}
    close = float(candles[-1]["close"])
    return {
        "swing_high": round(high, 4),
        "swing_low":  round(low, 4),
        "trend": "up" if close > (high + low) / 2 else "down",
        "levels": {
            str(r): round(high - rng * r, 4)
            for r in [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        },
    }


def _order_blocks_with_time(candles: List[Dict]) -> List[Dict]:
    """OBs with start_time added (index of the originating candle)."""
    from services.smc_service import _atr as smc_atr, _opens, _closes as _sc, _highs as _sh, _lows as _sl
    if len(candles) < 10:
        return []

    raw_atr = _atr(candles)
    strong  = 1.5 * raw_atr
    window  = candles[-100:]
    n       = len(window)
    opens   = [float(c["open"])  for c in window]
    closes  = [float(c["close"]) for c in window]
    highs   = [float(c["high"])  for c in window]
    lows    = [float(c["low"])   for c in window]

    obs: List[Dict] = []
    for i in range(1, n - 3):
        future = closes[i + 1: min(i + 4, n)]
        # Bullish OB
        if closes[i] < opens[i]:
            if future and (max(future) - closes[i]) > strong:
                obs.append({
                    "type": "bullish",
                    "high": round(highs[i], 4),
                    "low":  round(lows[i], 4),
                    "start_time": _ts(window[i]["timestamp"]),
                    "end_time":   _ts(window[-1]["timestamp"]),
                })
        # Bearish OB
        if closes[i] > opens[i]:
            if future and (closes[i] - min(future)) > strong:
                obs.append({
                    "type": "bearish",
                    "high": round(highs[i], 4),
                    "low":  round(lows[i], 4),
                    "start_time": _ts(window[i]["timestamp"]),
                    "end_time":   _ts(window[-1]["timestamp"]),
                })
    return obs[-6:]


def _fvg_with_time(candles: List[Dict]) -> List[Dict]:
    """FVG zones with start_time."""
    if len(candles) < 3:
        return []
    window  = candles[-60:]
    highs   = [float(c["high"])  for c in window]
    lows    = [float(c["low"])   for c in window]
    closes  = [float(c["close"]) for c in window]
    current = closes[-1]
    fvgs    = []
    for i in range(2, len(window)):
        if lows[i] > highs[i - 2]:
            fvgs.append({
                "type": "bullish",
                "high": round(lows[i], 4),
                "low":  round(highs[i - 2], 4),
                "start_time": _ts(window[i]["timestamp"]),
                "end_time":   _ts(window[-1]["timestamp"]),
            })
        if highs[i] < lows[i - 2]:
            fvgs.append({
                "type": "bearish",
                "high": round(lows[i - 2], 4),
                "low":  round(highs[i], 4),
                "start_time": _ts(window[i]["timestamp"]),
                "end_time":   _ts(window[-1]["timestamp"]),
            })
    return fvgs[-6:]


# ── ML forecast projection ────────────────────────────────────────────────────

def _ml_projection(symbol: str, timeframe: str, candles: List[Dict]) -> Dict[str, Any]:
    path = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")
    empty = {"direction": "neutral", "confidence": 0, "buy_pct": 0, "sell_pct": 0, "projection": []}

    if not os.path.exists(path):
        return empty
    try:
        with open(path, "rb") as f:
            model_data = pickle.load(f)
    except Exception:
        return empty

    smc_val = smc_service.score(candles[-100:]).get("score", 50) if len(candles) >= 100 else 50.0
    feats   = build_ml_features(candles, smc_score=smc_val)
    if not feats:
        return empty

    x     = np.array([[feats.get(k, 0.0) for k in _ML_FEATURES]])
    proba = model_data["model"].predict_proba(x)[0]
    pct   = {int(cls): float(p) * 100 for cls, p in zip(model_data["model"].classes_, proba)}
    buy_p = pct.get(1, 0.0)
    sel_p = pct.get(-1, 0.0)

    if buy_p > sel_p and buy_p > 38:
        direction, strength = "bullish", buy_p / 100
    elif sel_p > buy_p and sel_p > 38:
        direction, strength = "bearish", sel_p / 100
    else:
        direction, strength = "neutral", 0.1

    atr_val = _atr(candles)
    last_ts = _ts(candles[-1]["timestamp"])
    last_px = float(candles[-1]["close"])
    tf_sec  = TF_MINUTES.get(str(timeframe), 60) * 60
    sign    = 1 if direction == "bullish" else (-1 if direction == "bearish" else 0)
    step    = atr_val * strength * 0.45

    projection = [{"time": last_ts, "value": round(last_px, 4)}]
    price = last_px
    for i in range(1, 8):
        taper  = max(0.25, 1.0 - i * 0.1)
        price += sign * step * taper
        projection.append({"time": last_ts + tf_sec * i, "value": round(price, 4)})

    return {
        "direction": direction,
        "confidence": round(max(buy_p, sel_p), 1),
        "buy_pct":  round(buy_p, 1),
        "sell_pct": round(sel_p, 1),
        "projection": projection,
    }


# ── main entry ────────────────────────────────────────────────────────────────

def generate_forecast(db: Session, symbol: str, timeframe: str) -> Dict[str, Any]:
    from services.market_service import fetch_twelvedata, upsert_candles, TF_TO_TD

    # Refresh candles from Twelvedata
    interval = TF_TO_TD.get(str(timeframe), "1h")
    fresh = fetch_twelvedata(symbol, interval, 300)
    if fresh:
        upsert_candles(db, symbol, timeframe, fresh)

    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(300)
        .all()
    )
    rows = list(reversed(rows))
    if not rows:
        return {"error": "No candle data available"}

    candles = [
        {"timestamp": r.timestamp, "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close), "volume": float(r.volume or 0)}
        for r in rows
    ]

    # OHLCV for lightweight-charts (time must be integer Unix seconds)
    chart_candles = [
        {"time": _ts(c["timestamp"]), "open": c["open"], "high": c["high"],
         "low": c["low"], "close": c["close"]}
        for c in candles
    ]

    # Volume histogram
    volume_data = [
        {"time": _ts(c["timestamp"]), "value": c["volume"],
         "color": "rgba(38,166,154,0.4)" if c["close"] >= c["open"] else "rgba(239,83,80,0.4)"}
        for c in candles
    ]

    # Indicator series
    bb = _bb_lines(candles)
    indicators = {
        "ema_20":   _ema_line(candles, 20),
        "ema_50":   _ema_line(candles, 50),
        "ema_200":  _ema_line(candles, 200),
        "bb_upper": bb["upper"],
        "bb_middle": bb["middle"],
        "bb_lower": bb["lower"],
        "rsi":      _rsi_line(candles),
    }

    # Overlays
    obs  = _order_blocks_with_time(candles)
    fvgs = _fvg_with_time(candles)
    sr   = _support_resistance(candles[-100:])
    fib  = _fibonacci(candles)

    # Signal markers from DB
    db_sigs = (
        db.query(Signal)
        .filter(Signal.symbol == symbol, Signal.signal_type.in_(["BUY", "SELL"]))
        .order_by(Signal.created_at.desc())
        .limit(15)
        .all()
    )
    signal_markers = [
        {"time": _ts(s.created_at), "type": s.signal_type,
         "price": s.entry, "sl": s.stop_loss, "tp": s.take_profit, "confidence": s.confidence}
        for s in db_sigs if s.entry
    ]

    latest_sig = db_sigs[0] if db_sigs else None
    latest_signal = {
        "type": latest_sig.signal_type, "entry": latest_sig.entry,
        "sl": latest_sig.stop_loss, "tp": latest_sig.take_profit,
        "confidence": latest_sig.confidence, "rr": latest_sig.rr,
    } if latest_sig else None

    ml = _ml_projection(symbol, timeframe, candles)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": chart_candles,
        "volume": volume_data,
        "indicators": indicators,
        "overlays": {
            "order_blocks": obs,
            "fvg": fvgs,
            "support_resistance": sr,
            "fibonacci": fib,
            "signals": signal_markers,
        },
        "latest_signal": latest_signal,
        "ml_forecast": ml,
        "generated_at": datetime.utcnow().isoformat(),
    }
