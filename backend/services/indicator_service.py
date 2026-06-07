"""
Technical indicator calculations — pure Python, no external TA library.
Covers all indicators required by the frontend API contract.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _closes(c: list) -> List[float]:
    return [float(x["close"]) for x in c]

def _highs(c: list) -> List[float]:
    return [float(x["high"]) for x in c]

def _lows(c: list) -> List[float]:
    return [float(x["low"]) for x in c]

def _volumes(c: list) -> List[float]:
    return [float(x.get("volume") or 0) for x in c]

def _safe(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    except Exception:
        return None


# ── core math ─────────────────────────────────────────────────────────────────

def _ema(values: List[float], n: int) -> Optional[float]:
    if len(values) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def _ema_series(values: List[float], n: int) -> List[Optional[float]]:
    """Full EMA series, None until enough data."""
    result: List[Optional[float]] = [None] * (n - 1)
    if len(values) < n:
        return [None] * len(values)
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    result.append(e)
    for v in values[n:]:
        e = v * k + e * (1 - k)
        result.append(e)
    return result


def _rsi(values: List[float], n: int = 14) -> Optional[float]:
    if len(values) <= n:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = values[i] - values[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)


def _macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
    if len(values) < slow + signal:
        return {"macd": None, "macd_signal": None}
    macd_series: List[float] = []
    for i in range(slow - 1, len(values)):
        w = values[:i + 1]
        f = _ema(w, fast)
        s = _ema(w, slow)
        if f is not None and s is not None:
            macd_series.append(f - s)
    if len(macd_series) < signal:
        return {"macd": None, "macd_signal": None}
    sig_line = _ema(macd_series, signal)
    return {"macd": macd_series[-1], "macd_signal": sig_line}


def _atr(c: list, n: int = 14) -> Optional[float]:
    h, l, cl = _highs(c), _lows(c), _closes(c)
    if len(c) < n + 1:
        return None
    trs = [max(h[i] - l[i], abs(h[i] - cl[i - 1]), abs(l[i] - cl[i - 1])) for i in range(1, len(c))]
    v = sum(trs[:n]) / n
    for tr in trs[n:]:
        v = (v * (n - 1) + tr) / n
    return v


def _bbands(values: List[float], n: int = 20, k: float = 2.0) -> Dict[str, Optional[float]]:
    if len(values) < n:
        return {"bb_upper": None, "bb_mid": None, "bb_lower": None}
    w = values[-n:]
    mid = sum(w) / n
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / n)
    return {"bb_upper": mid + k * std, "bb_mid": mid, "bb_lower": mid - k * std}


# ── public API ────────────────────────────────────────────────────────────────

def compute_snapshot(candles: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Compute all indicators for the latest candle. Returns frontend-contract field names."""
    if len(candles) < 26:
        return {}

    window = candles[-500:]
    closes = _closes(window)

    rsi = _rsi(closes)
    macd_data = _macd(closes)
    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50)
    e200 = _ema(closes, 200)
    atr = _atr(window)
    bb = _bbands(closes)

    return {
        "rsi": _safe(rsi),
        "macd": _safe(macd_data["macd"]),
        "macd_signal": _safe(macd_data["macd_signal"]),
        "ema_20": _safe(e20),
        "ema_50": _safe(e50),
        "ema_200": _safe(e200),
        "atr": _safe(atr),
        "bb_upper": _safe(bb["bb_upper"]),
        "bb_lower": _safe(bb["bb_lower"]),
        "bb_mid": _safe(bb["bb_mid"]),
    }


def compute_series(candles: List[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    """Compute indicators for each of the last `limit` candles."""
    if len(candles) < 26:
        return []

    window = candles[-500:]
    closes = _closes(window)

    ema20_s = _ema_series(closes, 20)
    ema50_s = _ema_series(closes, 50)
    ema200_s = _ema_series(closes, 200)

    start = max(0, len(window) - limit)
    result = []
    for i in range(start, len(window)):
        sub = window[:i + 1]
        sub_closes = closes[:i + 1]
        ts = sub[-1].get("timestamp")
        rsi = _safe(_rsi(sub_closes))
        macd_d = _macd(sub_closes)
        atr = _safe(_atr(sub))
        bb = _bbands(sub_closes)
        result.append({
            "timestamp": ts,
            "rsi": rsi,
            "macd": _safe(macd_d["macd"]),
            "macd_signal": _safe(macd_d["macd_signal"]),
            "ema_20": _safe(ema20_s[i]),
            "ema_50": _safe(ema50_s[i]),
            "ema_200": _safe(ema200_s[i]),
            "atr": atr,
            "bb_upper": _safe(bb["bb_upper"]),
            "bb_lower": _safe(bb["bb_lower"]),
            "bb_mid": _safe(bb["bb_mid"]),
        })
    return result


def build_ml_features(candles: List[Dict[str, Any]], smc_score: float = 50.0) -> Dict[str, float]:
    """Build the ML feature vector from candle data."""
    if len(candles) < 50:
        return {}

    snap = compute_snapshot(candles)
    c = candles[-1]
    close = float(c["close"])

    body = abs(float(c["close"]) - float(c["open"]))
    rng = float(c["high"]) - float(c["low"])
    upper_wick = float(c["high"]) - max(float(c["open"]), float(c["close"]))
    lower_wick = min(float(c["open"]), float(c["close"])) - float(c["low"])

    vols = _volumes(candles[-20:])
    avg_vol = sum(vols) / len(vols) if vols else 1.0
    vol_ratio = float(c.get("volume") or 0) / (avg_vol + 1e-9)

    e20 = snap.get("ema_20") or close
    e50 = snap.get("ema_50") or close
    e200 = snap.get("ema_200") or close
    bb_upper = snap.get("bb_upper") or close
    bb_lower = snap.get("bb_lower") or close
    bb_pos = (close - bb_lower) / (bb_upper - bb_lower + 1e-9)

    return {
        "rsi": snap.get("rsi") or 50.0,
        "macd": snap.get("macd") or 0.0,
        "macd_signal": snap.get("macd_signal") or 0.0,
        "macd_hist": (snap.get("macd") or 0) - (snap.get("macd_signal") or 0),
        "ema_20_dist": (close - e20) / (e20 + 1e-9) * 100,
        "ema_50_dist": (close - e50) / (e50 + 1e-9) * 100,
        "ema_200_dist": (close - e200) / (e200 + 1e-9) * 100,
        "atr_pct": ((snap.get("atr") or 0) / (close + 1e-9)) * 100,
        "bb_position": bb_pos,
        "candle_body_ratio": body / (rng + 1e-9),
        "upper_wick_ratio": upper_wick / (rng + 1e-9),
        "lower_wick_ratio": lower_wick / (rng + 1e-9),
        "volume_ratio": vol_ratio,
        "smc_score": smc_score,
    }
