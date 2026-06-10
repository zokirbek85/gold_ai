"""
GOLD_AI Engine — elite 8-step analysis pipeline for XAUUSD.

Steps (executed in strict order):
  1  BLACKOUT CHECK         — suppress all signals near high-impact events
  2  REGIME CLASSIFICATION  — governs all subsequent strategy decisions
  3  MACRO FILTER           — DXY / US10Y / SPX alignment checks
  4  LIQUIDITY SWEEP        — high-priority sweep-and-reverse setups
  5  SESSION QUALITY        — session multiplier per UTC time
  6  ONLINE LEARNING        — suppress setups with poor historical win rate
  7  CONFLUENCE SCORING     — multi-feature score (0-100) per timeframe
  8  SIGNAL CONSTRUCTION    — entry / SL / TP / RR meeting ≥1:2 minimum

Output matches the strict JSON schema defined in the GOLD_AI system prompt.
"""
from __future__ import annotations

import logging
import math
import os
import pickle
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from core.constants import ML_FEATURE_NAMES
from core.regime import MarketRegimeDetector
from config import settings
from models.candle import Candle
from models.economic_calendar import EconomicEvent
from models.news import NewsArticle
from services import smc_service
from services.candle_patterns import detect_pattern, pattern_category
from services.indicator_service import compute_snapshot, build_ml_features, _ema_series
from services.feedback_history import get_feedback_history

log = logging.getLogger(__name__)

_REGIME_DETECTOR = MarketRegimeDetector()

# Timeframe key → human name
_TF_MAP = {
    "1": "M1", "5": "M5", "15": "M15", "30": "M30",
    "60": "H1", "240": "H4", "1440": "D1",
}
_ALL_TFS = list(_TF_MAP.keys())


# ── Session detection ─────────────────────────────────────────────────────────

def _session_info(utc_hour: float) -> Tuple[str, float, str]:
    """Returns (session_name, multiplier, quality)."""
    h = utc_hour
    if 13.0 <= h < 17.0:
        return "london_ny_overlap", 1.30, "high"
    if 7.5 <= h < 9.5:
        return "london_open", 1.25, "high"
    if 12.5 <= h < 14.5:
        return "ny_open", 1.20, "high"
    if 19.0 <= h < 21.0:
        return "ny_close", 0.85, "medium"
    if h >= 23.0 or h < 6.0:
        return "asian_session", 0.70, "low"
    if 21.0 <= h < 23.0:
        return "dead_zone", 0.50, "avoid"
    return "mid_session", 1.00, "medium"


# ── Candle loader ─────────────────────────────────────────────────────────────

def _load_candles(db: Session, symbol: str, timeframe: str, limit: int = 300) -> List[Dict]:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
        .order_by(Candle.timestamp.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [
        {"timestamp": r.timestamp, "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close), "volume": float(r.volume or 0)}
        for r in rows
    ]


# ── ATR helper ────────────────────────────────────────────────────────────────

def _atr(candles: List[Dict], n: int = 14) -> float:
    if len(candles) < n + 1:
        return float(candles[-1]["close"]) * 0.005
    trs = [
        max(float(c["high"]) - float(c["low"]),
            abs(float(c["high"]) - float(candles[i - 1]["close"])),
            abs(float(c["low"])  - float(candles[i - 1]["close"])))
        for i, c in enumerate(candles) if i > 0
    ]
    v = sum(trs[:n]) / n
    for tr in trs[n:]:
        v = (v * (n - 1) + tr) / n
    return v


# ── Swing structure ───────────────────────────────────────────────────────────

def _swing_highs(candles: List[Dict], lookback: int = 3) -> List[float]:
    n = len(candles)
    result = []
    for i in range(lookback, n - lookback):
        h = float(candles[i]["high"])
        if all(h >= float(candles[j]["high"]) for j in range(i - lookback, i + lookback + 1) if j != i):
            result.append(h)
    return sorted(set(result))


def _swing_lows(candles: List[Dict], lookback: int = 3) -> List[float]:
    n = len(candles)
    result = []
    for i in range(lookback, n - lookback):
        lo = float(candles[i]["low"])
        if all(lo <= float(candles[j]["low"]) for j in range(i - lookback, i + lookback + 1) if j != i):
            result.append(lo)
    return sorted(set(result))


# ── ML prediction ─────────────────────────────────────────────────────────────

def _ml_predict(symbol: str, timeframe: str, feats: Dict) -> Dict[str, Any]:
    empty = {"direction": "neutral", "confidence": 0.0, "buy_pct": 0.0,
             "sell_pct": 0.0, "neutral_pct": 100.0, "models_used": 0}
    path = os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl")
    if not os.path.exists(path):
        return empty
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        x = np.array([[feats.get(k, 0.0) for k in ML_FEATURE_NAMES]])
        proba = data["model"].predict_proba(x)[0]
        pct = {int(c): float(p) * 100 for c, p in zip(data["model"].classes_, proba)}
        buy_p  = pct.get(1, 0.0)
        sell_p = pct.get(-1, 0.0)
        neu_p  = pct.get(0, 0.0)
        if buy_p >= sell_p and buy_p >= neu_p:
            direction = "bullish"
            confidence = buy_p
        elif sell_p >= buy_p and sell_p >= neu_p:
            direction = "bearish"
            confidence = sell_p
        else:
            direction = "neutral"
            confidence = neu_p
        return {"direction": direction, "confidence": round(confidence, 1),
                "buy_pct": round(buy_p, 1), "sell_pct": round(sell_p, 1),
                "neutral_pct": round(neu_p, 1), "models_used": 1}
    except Exception as exc:
        log.debug("ML predict failed for %s/%s: %s", symbol, timeframe, exc)
        return empty


# ── News helpers ──────────────────────────────────────────────────────────────

def _news_context(db: Session) -> Dict[str, Any]:
    try:
        rows = (
            db.query(NewsArticle)
            .order_by(NewsArticle.published_at.desc())
            .limit(20)
            .all()
        )
    except Exception:
        db.rollback()
        return {"aggregate_sentiment": "neutral", "sentiment_score": 0.0,
                "recent": [], "high_impact_count_24h": 0}

    recent = []
    bull = bear = 0
    for a in rows:
        sent = (a.sentiment or "neutral").lower()
        impact = float(a.impact_score or 5.0)
        recent.append({
            "headline": a.title or "",
            "sentiment": sent,
            "impact_score": impact,
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "keywords": [],
        })
        if sent == "bullish":
            bull += 1
        elif sent == "bearish":
            bear += 1

    total = bull + bear + 1
    agg_score = round((bull - bear) / total * 100, 1)
    agg_sent = "bullish" if agg_score > 10 else ("bearish" if agg_score < -10 else "neutral")
    return {"aggregate_sentiment": agg_sent, "sentiment_score": agg_score,
            "recent": recent[:5], "high_impact_count_24h": 0}


def _calendar_context(db: Session) -> Dict[str, Any]:
    now_aware = datetime.now(timezone.utc)
    now_naive  = now_aware.replace(tzinfo=None)  # DB stores naive UTC
    try:
        rows = (
            db.query(EconomicEvent)
            .filter(EconomicEvent.event_time >= now_naive)
            .order_by(EconomicEvent.event_time.asc())
            .limit(5)
            .all()
        )
    except Exception:
        db.rollback()
        return {"upcoming_events": [], "active_event": None, "blackout_active": False}

    events = []
    blackout = False
    active = None
    for ev in rows:
        et = ev.event_time
        # Normalise: make both naive for subtraction
        et_naive = et.replace(tzinfo=None) if et.tzinfo is not None else et
        mins = int((et_naive - now_naive).total_seconds() / 60)
        # impact is stored as integer 1/2/3 in EconomicEvent
        impact_val = ev.impact if isinstance(ev.impact, int) else 1
        impact = "high" if impact_val >= 3 else ("medium" if impact_val == 2 else "low")
        events.append({
            "event_name": ev.event or "",
            "scheduled_utc": ev.event_time.isoformat(),
            "minutes_until": mins,
            "impact": impact,
            "forecast": str(ev.forecast or ""),
            "previous": str(ev.previous or ""),
            "actual": ev.actual,
        })
        if impact == "high" and 0 <= mins < 15:
            blackout = True
            active = events[-1]

    return {"upcoming_events": events, "active_event": active, "blackout_active": blackout}


# ── Step 3: Macro filter ──────────────────────────────────────────────────────

def _macro_filter(direction: str, correlations: Dict) -> Tuple[int, str, str, str]:
    """
    Returns (confidence_delta, dxy_alignment, bonds_alignment, macro_summary).
    confidence_delta is negative when macro is unfavorable.
    """
    delta = 0
    dxy_align = "neutral"
    bond_align = "neutral"
    notes = []

    dxy = correlations.get("DXY", {})
    us10y = correlations.get("US10Y", {})
    spx = correlations.get("SPX500", {})
    silver = correlations.get("SILVER", {})

    if direction == "BUY":
        if dxy.get("trend") == "up" and dxy.get("change_1h_pct", 0) > 0.3:
            delta -= 10
            dxy_align = "unfavorable"
            notes.append("DXY rising — headwind for gold")
        elif dxy.get("trend") == "down":
            delta += 5
            dxy_align = "favorable"
            notes.append("DXY falling — tailwind for gold")
        else:
            dxy_align = "neutral"

        if us10y.get("change_1h_bps", 0) > 5:
            delta -= 10
            bond_align = "unfavorable"
            notes.append("10Y yields rising — bearish for gold")
        elif us10y.get("change_1h_bps", 0) < -5:
            delta += 5
            bond_align = "favorable"
            notes.append("10Y yields falling — bullish for gold")
        else:
            bond_align = "neutral"

        if spx.get("trend") == "up":
            delta -= 5
            notes.append("Risk-on equities reduce safe-haven demand")

        if silver.get("trend") == "up":
            delta += 5
            notes.append("Silver confirming precious-metals rally")

    elif direction == "SELL":
        if dxy.get("trend") == "up":
            delta += 5
            dxy_align = "favorable"
            notes.append("DXY rising — confirms gold sell bias")
        elif dxy.get("trend") == "down" and dxy.get("change_1h_pct", 0) < -0.3:
            delta -= 10
            dxy_align = "unfavorable"
            notes.append("DXY falling — headwind for gold sell")
        else:
            dxy_align = "neutral"

        if us10y.get("change_1h_bps", 0) > 5:
            delta += 5
            bond_align = "favorable"
            notes.append("10Y yields rising — confirms gold sell bias")
        elif us10y.get("change_1h_bps", 0) < -5:
            delta -= 10
            bond_align = "unfavorable"
            notes.append("10Y yields falling — headwind for gold sell")
        else:
            bond_align = "neutral"

        if silver.get("trend") == "down":
            delta += 5
            notes.append("Silver falling — confirms metals weakness")

    macro_summary = ". ".join(notes) if notes else "Macro environment neutral for current bias."
    return delta, dxy_align, bond_align, macro_summary


# ── Step 7: Confluence scoring ────────────────────────────────────────────────

def _confluence_score(
    direction: str,
    snap: Dict,
    pattern: Dict,
    smc_data: Dict,
    ml: Dict,
    news: Dict,
    sweep: Dict,
    candles: List[Dict],
) -> Tuple[float, List[str]]:
    """
    Returns (raw_score_0_to_100, [confluence_factor_strings]).
    Session multiplier is applied by the caller.
    """
    score = 0.0
    factors: List[str] = []
    is_buy = direction == "BUY"

    # ── Technical indicators (max 25) ─────────────────────────────────────────
    rsi = snap.get("rsi") or 50.0
    if is_buy:
        if 30 <= rsi <= 45:
            score += 8
            factors.append(f"RSI {rsi:.1f} approaching oversold — buy confluence")
        elif rsi < 30:
            score += 5
            factors.append(f"RSI {rsi:.1f} oversold — buy signal")
    else:
        if 55 <= rsi <= 70:
            score += 8
            factors.append(f"RSI {rsi:.1f} approaching overbought — sell confluence")
        elif rsi > 70:
            score += 5
            factors.append(f"RSI {rsi:.1f} overbought — sell signal")

    macd_hist = snap.get("macd_hist") or 0.0
    macd      = snap.get("macd") or 0.0
    macd_sig  = snap.get("macd_signal") or 0.0
    if is_buy and macd_hist > 0 and macd > macd_sig:
        score += 8
        factors.append("MACD histogram positive — bullish momentum")
    elif not is_buy and macd_hist < 0 and macd < macd_sig:
        score += 8
        factors.append("MACD histogram negative — bearish momentum")

    ema20 = snap.get("ema_20") or 0.0
    ema50 = snap.get("ema_50") or 0.0
    close = float(candles[-1]["close"])
    if ema20 and ema50:
        if is_buy and close > ema20 and close > ema50:
            score += 5
            factors.append(f"Price above EMA20 ({ema20:.2f}) and EMA50 ({ema50:.2f})")
        elif not is_buy and close < ema20 and close < ema50:
            score += 5
            factors.append(f"Price below EMA20 ({ema20:.2f}) and EMA50 ({ema50:.2f})")
        # EMA cross in last 3 candles
        if len(candles) >= 5 and ema20 and ema50:
            # Detect cross using EMA series
            if is_buy and ema20 > ema50:
                score += 4
                factors.append("EMA20 crossed above EMA50 — bullish cross")
            elif not is_buy and ema20 < ema50:
                score += 4
                factors.append("EMA20 crossed below EMA50 — bearish cross")

    # ── Candle pattern (max 20) ───────────────────────────────────────────────
    pat_name     = pattern.get("pattern", "none")
    pat_strength = float(pattern.get("strength", 0.0))
    pat_conf     = pattern.get("confirmed", False)
    cat          = pattern_category(pat_name)

    if pat_name != "none":
        # Direction check: bullish patterns for BUY, bearish for SELL
        is_bull_pat = pat_name in {"engulfing_bull", "pinbar_bull", "hammer",
                                    "morning_star", "three_white_soldiers", "tweezer_bottom"}
        is_bear_pat = pat_name in {"engulfing_bear", "pinbar_bear", "shooting_star",
                                    "evening_star", "three_black_crows", "tweezer_top"}
        neutral_pat = pat_name in {"doji", "inside_bar"}

        aligned = (is_buy and is_bull_pat) or (not is_buy and is_bear_pat) or neutral_pat
        if aligned:
            if cat == "strong":
                raw = 12 if pat_conf else 7
            elif cat == "moderate":
                raw = 8 if pat_conf else 4
            else:  # doji/inside_bar
                raw = 5
            pts = raw * pat_strength
            score += pts
            factors.append(
                f"{'Confirmed' if pat_conf else 'Unconfirmed'} {pat_name} "
                f"(strength {pat_strength:.2f}) at current candle"
            )

    # ── SMC (max 20) ──────────────────────────────────────────────────────────
    obs  = smc_data.get("order_blocks", [])
    fvgs = smc_data.get("fvg_zones", [])
    bos  = smc_data.get("bos_events", [])
    liq  = smc_data.get("liquidity_pools", [])

    for ob in obs:
        ob_type = ob.get("type", "")
        if is_buy and ob_type == "bullish" and ob.get("low", 0) <= close <= ob.get("high", 0) * 1.002:
            score += 10
            factors.append(f"Price inside bullish OB {ob['low']:.2f}–{ob['high']:.2f}")
            break
        elif not is_buy and ob_type == "bearish" and ob.get("low", 0) * 0.998 <= close <= ob.get("high", 0):
            score += 10
            factors.append(f"Price inside bearish OB {ob['low']:.2f}–{ob['high']:.2f}")
            break

    for fvg in fvgs:
        fvg_mid = (fvg.get("high", 0) + fvg.get("low", 0)) / 2.0
        if abs(close - fvg_mid) / (close + 1e-9) < 0.005:
            fvg_type = fvg.get("type", "")
            if (is_buy and fvg_type == "bullish") or (not is_buy and fvg_type == "bearish"):
                score += 7
                factors.append(f"Price at {fvg_type} FVG {fvg['low']:.2f}–{fvg['high']:.2f}")
                break

    for b in bos:
        b_dir = b.get("direction", b.get("type", ""))
        if (is_buy and "bullish" in b_dir) or (not is_buy and "bearish" in b_dir):
            score += 10
            factors.append(f"BOS {b_dir} confirmed at {b.get('level', 0.0):.2f}")
            break

    # Liquidity pool penalty: within 15 pips above entry on BUY = headwind
    atr_val = _atr(candles)
    for pool in liq:
        pool_level = pool.get("level", 0)
        dist_pips = abs(pool_level - close) / 0.1  # approximate pips
        if is_buy and pool.get("type") == "sell_side" and pool_level > close and dist_pips < 15:
            score -= 8
            factors.append(f"Warning: sell-side liquidity at {pool_level:.2f} only {dist_pips:.0f} pips above")

    # Liquidity sweep boost
    if sweep.get("detected") and sweep.get("reversal_forming"):
        sweep_type = sweep.get("type", "none")
        if (is_buy and sweep_type == "buy_side") or (not is_buy and sweep_type == "sell_side"):
            score += 15
            factors.append(f"Liquidity sweep confirmed at {sweep.get('swept_level', 0):.2f} — reversal forming")

    # ── ML ensemble (max 15) ─────────────────────────────────────────────────
    ml_conf = float(ml.get("confidence", 0))
    ml_dir  = ml.get("direction", "neutral")
    ml_aligned = (is_buy and ml_dir == "bullish") or (not is_buy and ml_dir == "bearish")
    if ml_aligned:
        if ml_conf >= 75:
            score += 15
            factors.append(f"ML ensemble {ml_conf:.0f}% confidence — strong alignment")
        elif ml_conf >= 60:
            score += 10
            factors.append(f"ML ensemble {ml_conf:.0f}% confidence — moderate alignment")
        elif ml_conf >= 50:
            score += 5
            factors.append(f"ML ensemble {ml_conf:.0f}% confidence — weak alignment")

    # ── News / Macro (max 10) ────────────────────────────────────────────────
    news_sent   = news.get("aggregate_sentiment", "neutral")
    news_score_v = float(news.get("sentiment_score", 0))
    if (is_buy and news_sent == "bullish") or (not is_buy and news_sent == "bearish"):
        if abs(news_score_v) > 50:
            score += 10
            factors.append(f"News strongly aligned: {news_sent} ({news_score_v:+.0f})")
        else:
            score += 7
            factors.append(f"News sentiment aligned: {news_sent}")
    if news.get("high_impact_count_24h", 0) == 0:
        score += 3
        factors.append("Clean technical environment — no recent high-impact news")

    return round(min(score, 100.0), 1), factors


# ── Step 8: Signal construction ───────────────────────────────────────────────

def _build_signal(
    direction: str,
    candles: List[Dict],
    snap: Dict,
    smc_data: Dict,
    confluence_score: float,
    session_mult: float,
    session_quality: str,
    macro_delta: int,
    ml: Dict,
    sweep: Dict,
    confluence_factors: List[str],
    suppression_reasons: List[str],
    pattern: Dict,
    tf_name: str,
) -> Dict[str, Any]:
    """Construct the full signal dict for one timeframe."""

    final_score = round(min(confluence_score * session_mult + macro_delta, 100.0), 1)
    final_score = max(0.0, final_score)

    close = float(candles[-1]["close"])
    atr   = _atr(candles)

    # Determine status / confidence thresholds
    if final_score >= 75:
        confidence = int(final_score)
        position_note = "full"
    elif final_score >= 55:
        confidence = int(final_score)
        position_note = "half"
    else:
        return _no_trade(tf_name, f"Score {final_score:.0f} < 55 threshold",
                         confluence_score, final_score, ml, session_quality, pattern)

    if len(suppression_reasons) > 0:
        return _suppressed(tf_name, suppression_reasons, confluence_score, final_score,
                           ml, session_quality, pattern)

    # Entry zone
    obs = smc_data.get("order_blocks", [])
    entry_low = entry_high = close
    for ob in obs:
        if direction == "BUY" and ob.get("type") == "bullish":
            entry_low  = min(float(ob["low"]),  close)
            entry_high = max(float(ob["high"]), close)
            break
        elif direction == "SELL" and ob.get("type") == "bearish":
            entry_low  = min(float(ob["low"]),  close)
            entry_high = max(float(ob["high"]), close)
            break

    # SL: behind nearest structural swing, capped at 2.5×ATR
    swing_h = _swing_highs(candles[-50:])
    swing_l = _swing_lows(candles[-50:])
    max_sl  = 2.5 * atr

    if direction == "BUY":
        struct_sl = max([l for l in swing_l if l < close], default=close - max_sl)
        sl_dist   = close - struct_sl
        if sl_dist > max_sl or sl_dist <= 0:
            return _no_trade(tf_name, f"SL distance {sl_dist:.2f} exceeds 2.5×ATR ({max_sl:.2f})",
                             confluence_score, final_score, ml, session_quality, pattern)
        sl = round(struct_sl - atr * 0.1, 4)  # small buffer below structure
    else:
        struct_sl = min([h for h in swing_h if h > close], default=close + max_sl)
        sl_dist   = struct_sl - close
        if sl_dist > max_sl or sl_dist <= 0:
            return _no_trade(tf_name, f"SL distance {sl_dist:.2f} exceeds 2.5×ATR ({max_sl:.2f})",
                             confluence_score, final_score, ml, session_quality, pattern)
        sl = round(struct_sl + atr * 0.1, 4)

    sl_pips = round(abs(close - sl) / 0.1, 1)

    # TPs at minimum RR ratios
    if direction == "BUY":
        tp1 = round(close + sl_dist * 1.5,  4)
        tp2 = round(close + sl_dist * 2.5,  4)
        tp3 = round(close + sl_dist * 4.0,  4)
    else:
        tp1 = round(close - sl_dist * 1.5,  4)
        tp2 = round(close - sl_dist * 2.5,  4)
        tp3 = round(close - sl_dist * 4.0,  4)

    rr1 = round(abs(tp1 - close) / (abs(close - sl) + 1e-9), 2)
    rr2 = round(abs(tp2 - close) / (abs(close - sl) + 1e-9), 2)
    rr3 = round(abs(tp3 - close) / (abs(close - sl) + 1e-9), 2)

    if rr1 < 1.5:
        return _no_trade(tf_name, f"RR1 {rr1:.2f} < 1:1.5 minimum",
                         confluence_score, final_score, ml, session_quality, pattern)

    # Invalidation condition
    invalidation = (
        f"Close {'below' if direction == 'BUY' else 'above'} {sl:.2f} "
        f"or regime shifts to {'VOLATILE' if direction == 'BUY' else 'TRENDING_UP'}"
    )

    ml_conf = float(ml.get("confidence", 0))
    order_flow_bias = "bullish" if ml.get("direction") == "bullish" else (
                      "bearish" if ml.get("direction") == "bearish" else "neutral")

    return {
        "status":             "SIGNAL",
        "direction":          direction,
        "confidence":         confidence,
        "confluence_score":   final_score,
        "entry_zone":         {"low": round(entry_low, 4), "high": round(entry_high, 4)},
        "entry_type":         "limit" if abs(entry_low - close) > atr * 0.05 else "market",
        "sl":                 sl,
        "sl_pips":            sl_pips,
        "tp1": tp1, "tp1_pips": round(abs(tp1 - close) / 0.1, 1), "rr1": rr1,
        "tp2": tp2, "tp2_pips": round(abs(tp2 - close) / 0.1, 1), "rr2": rr2,
        "tp3": tp3, "tp3_pips": round(abs(tp3 - close) / 0.1, 1), "rr3": rr3,
        "invalidation":       invalidation,
        "confluence_factors": confluence_factors,
        "suppression_reasons": [],
        "pattern":            pattern.get("pattern"),
        "ml_confidence":      ml_conf,
        "order_flow_bias":    order_flow_bias,
        "session_quality":    session_quality,
        "no_trade_reason":    None,
    }


def _no_trade(tf, reason, raw_score, final_score, ml, session_quality, pattern) -> Dict:
    return {
        "status": "NO_TRADE", "direction": "NEUTRAL", "confidence": 0,
        "confluence_score": final_score, "entry_zone": {"low": 0.0, "high": 0.0},
        "entry_type": "market", "sl": 0.0, "sl_pips": 0.0,
        "tp1": 0.0, "tp1_pips": 0.0, "rr1": 0.0,
        "tp2": 0.0, "tp2_pips": 0.0, "rr2": 0.0,
        "tp3": 0.0, "tp3_pips": 0.0, "rr3": 0.0,
        "invalidation": "", "confluence_factors": [], "suppression_reasons": [],
        "pattern": pattern.get("pattern"), "ml_confidence": float(ml.get("confidence", 0)),
        "order_flow_bias": "neutral", "session_quality": session_quality,
        "no_trade_reason": reason,
    }


def _suppressed(tf, reasons, raw_score, final_score, ml, session_quality, pattern) -> Dict:
    base = _no_trade(tf, reasons[0] if reasons else "Suppressed", raw_score, final_score,
                     ml, session_quality, pattern)
    base["status"] = "SUPPRESSED_BY_HISTORY"
    base["suppression_reasons"] = reasons
    return base


def _blackout_signal(reason: str) -> Dict:
    return {
        "status": "BLACKOUT", "direction": "NEUTRAL", "confidence": 0,
        "confluence_score": 0.0, "entry_zone": {"low": 0.0, "high": 0.0},
        "entry_type": "market", "sl": 0.0, "sl_pips": 0.0,
        "tp1": 0.0, "tp1_pips": 0.0, "rr1": 0.0,
        "tp2": 0.0, "tp2_pips": 0.0, "rr2": 0.0,
        "tp3": 0.0, "tp3_pips": 0.0, "rr3": 0.0,
        "invalidation": "", "confluence_factors": [], "suppression_reasons": [reason],
        "pattern": None, "ml_confidence": 0.0, "order_flow_bias": "neutral",
        "session_quality": "avoid", "no_trade_reason": reason,
    }


# ── Direction inference ───────────────────────────────────────────────────────

def _infer_direction(regime_name: str, snap: Dict, smc_data: Dict, candles: List[Dict]) -> str:
    """
    Infer the most probable trade direction from regime + indicators + SMC.
    Returns 'BUY' | 'SELL'.
    """
    score_buy = score_sell = 0

    # Regime bias
    if regime_name == "TRENDING_UP":
        score_buy += 3
    elif regime_name == "TRENDING_DOWN":
        score_sell += 3

    # RSI
    rsi = snap.get("rsi") or 50.0
    if rsi < 45:
        score_buy += 2
    elif rsi > 55:
        score_sell += 2

    # EMA alignment
    close = float(candles[-1]["close"])
    ema50 = snap.get("ema_50") or close
    if close > ema50:
        score_buy += 1
    else:
        score_sell += 1

    # MACD
    macd_hist = snap.get("macd_hist") or 0.0
    if macd_hist > 0:
        score_buy += 2
    elif macd_hist < 0:
        score_sell += 2

    # SMC score
    smc_score_val = float(smc_data.get("score", 50))
    if smc_score_val > 60:
        score_buy += 2
    elif smc_score_val < 40:
        score_sell += 2

    return "BUY" if score_buy >= score_sell else "SELL"


# ── Main engine entry point ───────────────────────────────────────────────────

def analyze(db: Session, symbol: str = "XAUUSD") -> Dict[str, Any]:
    """
    Run the full 8-step GOLD_AI pipeline and return the structured JSON output.
    """
    now_utc = datetime.now(timezone.utc)
    now_h   = now_utc.hour + now_utc.minute / 60.0

    # ── Gather shared context ─────────────────────────────────────────────────
    # Correlations (cached)
    try:
        from services.correlation_service import get_correlations
        correlations = get_correlations()
    except Exception:
        correlations = {}

    # News
    news_ctx = _news_context(db)

    # Economic calendar + STEP 1 BLACKOUT CHECK
    cal_ctx = _calendar_context(db)

    # Session
    session_name, session_mult, session_quality = _session_info(now_h)

    # Feedback history (online learning)
    try:
        feedback = get_feedback_history(db, symbol)
    except Exception:
        db.rollback()
        feedback = {"last_50_signals": [], "win_rate_by_regime": {},
                    "win_rate_by_session": {}, "win_rate_by_pattern": {},
                    "avg_rr_achieved": 0.0, "consecutive_losses": 0,
                    "drawdown_pct_today": 0.0}

    consecutive_losses  = feedback.get("consecutive_losses", 0)
    drawdown_today      = feedback.get("drawdown_pct_today", 0.0)

    # ── STEP 1 — BLACKOUT CHECK ───────────────────────────────────────────────
    if cal_ctx.get("blackout_active"):
        ev_name = (cal_ctx.get("active_event") or {}).get("event_name", "High-impact event")
        blackout_reason = f"Blackout: {ev_name} within 15 minutes"
        blackout_sig = _blackout_signal(blackout_reason)
        all_signals = {_TF_MAP[tf]: dict(blackout_sig) for tf in _ALL_TFS}
        return _format_output(
            now_utc, all_signals, "BLACKOUT", 100.0, session_name, session_mult,
            True, blackout_reason, correlations, feedback, cal_ctx,
            drawdown_today, consecutive_losses,
        )

    # Dead zone — very low quality, suppress everything
    if session_quality == "avoid":
        dead_sig = _blackout_signal("Dead zone 21:00–23:00 UTC — no entries")
        all_signals = {_TF_MAP[tf]: dict(dead_sig) for tf in _ALL_TFS}
        return _format_output(
            now_utc, all_signals, "RANGING", 50.0, session_name, session_mult,
            False, None, correlations, feedback, cal_ctx,
            drawdown_today, consecutive_losses,
        )

    # ── STEP 5-L5 — DRAWDOWN CIRCUIT BREAKER ─────────────────────────────────
    if drawdown_today >= 2.0:
        dd_sig = _blackout_signal(f"Daily drawdown {drawdown_today:.1f}% ≥ 2% — circuit breaker")
        all_signals = {_TF_MAP[tf]: dict(dd_sig) for tf in _ALL_TFS}
        all_signals_copy = all_signals.copy()
        for sig in all_signals_copy.values():
            sig["status"] = "DAILY_LIMIT"
        return _format_output(
            now_utc, all_signals, "RANGING", 50.0, session_name, session_mult,
            False, None, correlations, feedback, cal_ctx,
            drawdown_today, consecutive_losses,
        )

    # ── Load H1 candles for regime detection ─────────────────────────────────
    h1_candles = _load_candles(db, symbol, "60", 200)
    if not h1_candles:
        h1_candles = _load_candles(db, symbol, "240", 100)

    # ── STEP 2 — REGIME CLASSIFICATION ───────────────────────────────────────
    regime = _REGIME_DETECTOR.detect(h1_candles or [])
    regime_name     = regime.name
    regime_strength = regime.strength

    # ── STEP 4 — LIQUIDITY SWEEP (H1 context) ────────────────────────────────
    sweep = smc_service.detect_liquidity_sweep(h1_candles) if h1_candles else {
        "detected": False, "type": "none", "swept_level": 0.0, "reversal_forming": False
    }
    sweep_active = sweep.get("detected", False)

    # ── Per-timeframe analysis ────────────────────────────────────────────────
    all_signals: Dict[str, Dict] = {}
    active_signal_count = 0

    for tf in _ALL_TFS:
        tf_name = _TF_MAP[tf]

        if active_signal_count >= 3:
            all_signals[tf_name] = _no_trade(
                tf_name, "Max 3 concurrent signals reached", 0.0, 0.0,
                {}, session_quality, {"pattern": "none"},
            )
            continue

        candles = _load_candles(db, symbol, tf, 300)
        if len(candles) < 30:
            all_signals[tf_name] = _no_trade(
                tf_name, f"Insufficient data ({len(candles)} candles)",
                0.0, 0.0, {}, session_quality, {"pattern": "none"},
            )
            continue

        snap = compute_snapshot(candles)

        # SMC
        try:
            smc_raw   = smc_service.score(candles)
            obs       = smc_service.detect_order_blocks(candles)
            fvgs      = smc_service.detect_fvg(candles)
            bos       = smc_service.detect_bos(candles)
            liq_zones = smc_service.detect_liquidity_zones(candles)
        except Exception:
            smc_raw, obs, fvgs, bos, liq_zones = {"score": 50}, [], [], [], []

        smc_data = {
            "score":          smc_raw.get("score", 50),
            "order_blocks":   obs,
            "fvg_zones":      fvgs,
            "bos_events":     bos,
            "liquidity_pools": liq_zones,
        }

        # Pattern
        pattern = detect_pattern(candles)

        # ML
        try:
            smc_val = float(smc_raw.get("score", 50))
            feats   = build_ml_features(candles, smc_score=smc_val)
            ml      = _ml_predict(symbol, tf, feats)
        except Exception:
            ml = {"direction": "neutral", "confidence": 0.0, "buy_pct": 0.0,
                  "sell_pct": 0.0, "neutral_pct": 100.0, "models_used": 0}

        # Direction inference
        direction = _infer_direction(regime_name, snap, smc_data, candles)

        # ── STEP 3 — MACRO FILTER ─────────────────────────────────────────────
        macro_delta, dxy_align, bond_align, macro_summary = _macro_filter(direction, correlations)

        # ── STEP 6 — ONLINE LEARNING ──────────────────────────────────────────
        suppression_reasons: List[str] = []
        win_by_tf = feedback.get("win_rate_by_session", {})
        sess_wr = win_by_tf.get(session_name, 1.0)
        if sess_wr < 0.40 and sum(1 for s in feedback["last_50_signals"]
                                   if s.get("session_at_entry") == session_name) >= 5:
            suppression_reasons.append(
                f"Historical win rate {sess_wr:.0%} in {session_name} session < 40%"
            )

        if consecutive_losses >= 3:
            macro_delta -= 15  # drawdown protection

        # ── STEP 7 — CONFLUENCE SCORING ───────────────────────────────────────
        raw_score, conf_factors = _confluence_score(
            direction, snap, pattern, smc_data, ml,
            news_ctx, sweep, candles,
        )

        # Sweep active on this TF too? Give boost
        tf_sweep = smc_service.detect_liquidity_sweep(candles)
        if tf_sweep.get("detected") and tf_sweep.get("reversal_forming"):
            sweep_type = tf_sweep.get("type", "")
            if (direction == "BUY" and sweep_type == "buy_side") or \
               (direction == "SELL" and sweep_type == "sell_side"):
                raw_score = min(raw_score + 20, 100.0)
                conf_factors.append(
                    f"TF-level liquidity sweep at {tf_sweep.get('swept_level', 0):.2f}"
                )

        if raw_score < 40:
            all_signals[tf_name] = {
                **_no_trade(tf_name, f"Score {raw_score:.0f} is noise (< 40)",
                            raw_score, raw_score, ml, session_quality, pattern),
                "status": "NOISE",
            }
            continue

        # ── STEP 8 — SIGNAL CONSTRUCTION ──────────────────────────────────────
        sig = _build_signal(
            direction, candles, snap, smc_data, raw_score, session_mult,
            session_quality, macro_delta, ml, sweep, conf_factors,
            suppression_reasons, pattern, tf_name,
        )

        all_signals[tf_name] = sig
        if sig["status"] == "SIGNAL":
            active_signal_count += 1

    # ── Priority signal selection ─────────────────────────────────────────────
    priority = _pick_priority(all_signals)

    # ── Online learning update ────────────────────────────────────────────────
    ol_update = _online_learning_update(feedback, regime_name)

    # ── Risk dashboard ────────────────────────────────────────────────────────
    lot_mult = 0.5 if consecutive_losses >= 3 else 1.0
    max_pos  = 0 if drawdown_today >= 2.0 else (1 if consecutive_losses >= 5 else 3)

    # ── Next event warning ────────────────────────────────────────────────────
    next_ev = None
    nxt_min = None
    for ev in cal_ctx.get("upcoming_events", []):
        if ev.get("impact") == "high":
            next_ev = ev.get("event_name")
            nxt_min = ev.get("minutes_until")
            break

    return _format_output(
        now_utc, all_signals, regime_name, regime_strength, session_name, session_mult,
        False, None, correlations, feedback, cal_ctx, drawdown_today, consecutive_losses,
        priority=priority,
        dxy_align=dxy_align if all_signals else "neutral",
        bond_align=bond_align if all_signals else "neutral",
        macro_summary=macro_summary if all_signals else "No active signals.",
        sweep_active=sweep_active,
        ol_update=ol_update,
        lot_mult=lot_mult,
        max_pos=max_pos,
        next_ev=next_ev,
        nxt_min=nxt_min,
    )


# ── Priority signal selection ─────────────────────────────────────────────────

def _pick_priority(signals: Dict[str, Dict]) -> Dict[str, Any]:
    best_tf = None
    best_score = -1.0
    for tf, sig in signals.items():
        if sig.get("status") == "SIGNAL":
            sc = float(sig.get("confluence_score", 0))
            if sc > best_score:
                best_score = sc
                best_tf = tf

    if best_tf:
        sig = signals[best_tf]
        return {
            "timeframe": best_tf,
            "reason": f"Highest confluence score {best_score:.0f} with {len(sig.get('confluence_factors', []))} factors",
            "urgency": "immediate" if best_score >= 80 else "wait_for_confirmation",
        }
    return {"timeframe": None, "reason": "No valid signals across timeframes", "urgency": "monitor"}


# ── Online learning update ────────────────────────────────────────────────────

def _online_learning_update(feedback: Dict, regime: str) -> Dict[str, Any]:
    wr = feedback.get("win_rate_by_session", {})
    suppressed = ""
    for sess, rate in wr.items():
        if isinstance(rate, float) and rate < 0.40:
            suppressed = f"Session {sess} win rate {rate:.0%} — suppressed"
            break

    return {
        "pattern_reinforced":  f"High-confluence setups in {regime} regime",
        "pattern_suppressed":  suppressed,
        "regime_win_rate_update": feedback.get("win_rate_by_regime", {}),
        "recommended_feature_weight_adjustment": {
            "reason":           "Monitoring feature performance across regimes",
            "feature":          None,
            "suggested_action": None,
        },
    }


# ── Output formatter ──────────────────────────────────────────────────────────

def _format_output(
    now_utc,
    all_signals: Dict,
    regime_name: str,
    regime_strength: float,
    session_name: str,
    session_mult: float,
    blackout: bool,
    blackout_reason,
    correlations: Dict,
    feedback: Dict,
    cal_ctx: Dict,
    drawdown: float,
    cons_losses: int,
    priority: Optional[Dict] = None,
    dxy_align: str = "neutral",
    bond_align: str = "neutral",
    macro_summary: str = "",
    sweep_active: bool = False,
    ol_update: Optional[Dict] = None,
    lot_mult: float = 1.0,
    max_pos: int = 3,
    next_ev: Optional[str] = None,
    nxt_min: Optional[int] = None,
) -> Dict[str, Any]:

    if priority is None:
        priority = {"timeframe": None, "reason": "Pipeline not run", "urgency": "monitor"}
    if ol_update is None:
        ol_update = {"pattern_reinforced": "", "pattern_suppressed": "",
                     "regime_win_rate_update": {},
                     "recommended_feature_weight_adjustment": {
                         "reason": None, "feature": None, "suggested_action": None}}

    # Ensure all 7 TFs present
    for tf_name in _TF_MAP.values():
        if tf_name not in all_signals:
            all_signals[tf_name] = _no_trade(tf_name, "Not analyzed", 0.0, 0.0,
                                              {}, "medium", {"pattern": "none"})

    alert = None
    if cons_losses >= 5:
        alert = "PAUSE: 5 consecutive losses — resume next session"
    elif cons_losses >= 3:
        alert = "CAUTION: 3 consecutive losses — position size reduced 50%"
    elif drawdown >= 3.0:
        alert = "HALT: Daily drawdown ≥ 3% — manual review required"

    next_event_warning: Dict[str, Any] = {
        "event": next_ev,
        "minutes_until": nxt_min,
        "recommendation": (
            f"Close M1/M5 positions {max(5, (nxt_min or 10) - 5)} minutes before {next_ev}"
            if next_ev else None
        ),
    }

    return {
        "agent_version":  "gold_ai_v2",
        "generated_at":   now_utc.isoformat(),
        "market_context": {
            "regime":             regime_name,
            "regime_strength":    regime_strength,
            "session":            session_name,
            "session_multiplier": session_mult,
            "blackout_active":    blackout,
            "blackout_reason":    blackout_reason,
            "macro_summary":      macro_summary,
            "dxy_alignment":      dxy_align,
            "bonds_alignment":    bond_align,
            "liquidity_sweep_active": sweep_active,
        },
        "signals":             all_signals,
        "priority_signal":     priority,
        "online_learning_update": ol_update,
        "risk_dashboard": {
            "consecutive_losses":       cons_losses,
            "drawdown_today_pct":       drawdown,
            "max_new_positions_allowed": max_pos,
            "recommended_lot_multiplier": lot_mult,
            "alert":                    alert,
        },
        "next_event_warning": next_event_warning,
    }
