"""
AI analysis router — template-based analysis (no external LLM required).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.signal import Signal
from models.candle import Candle
from services.indicator_service import compute_snapshot
from services import smc_service

router = APIRouter()


class AnalyzeSignalIn(BaseModel):
    signal_id: int


class DailyBiasIn(BaseModel):
    candle_summary: str = ""
    news_summary: str = ""
    econ_summary: str = ""
    snapshot: Optional[Dict[str, Any]] = None


def _load_candles(db: Session, symbol: str, timeframe: str) -> list:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(200)
        .all()
    )
    rows = list(reversed(rows))
    return [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]


def _analyze_signal_data(sig: Signal, snap: dict, smc: dict) -> Dict[str, Any]:
    confidence = sig.confidence or 0
    direction = "bullish" if sig.signal_type == "BUY" else ("bearish" if sig.signal_type == "SELL" else "neutral")
    strengths: List[str] = []
    risks: List[str] = []

    rsi = snap.get("rsi")
    if rsi:
        if direction == "bullish" and rsi < 40:
            strengths.append(f"RSI oversold at {rsi:.1f} — supports bullish reversal")
        elif direction == "bearish" and rsi > 60:
            strengths.append(f"RSI overbought at {rsi:.1f} — supports bearish reversal")
        else:
            risks.append(f"RSI at {rsi:.1f} not confirming {direction} bias")

    macd = snap.get("macd")
    macd_sig = snap.get("macd_signal")
    if macd is not None and macd_sig is not None:
        if direction == "bullish" and macd > macd_sig:
            strengths.append("MACD bullish crossover confirmed")
        elif direction == "bearish" and macd < macd_sig:
            strengths.append("MACD bearish crossover confirmed")
        else:
            risks.append("MACD not aligned with signal direction")

    ema200 = snap.get("ema_200")
    if ema200 and sig.entry:
        if direction == "bullish" and sig.entry > ema200:
            strengths.append(f"Price above EMA200 ({ema200:.2f}) — uptrend confirmed")
        elif direction == "bearish" and sig.entry < ema200:
            strengths.append(f"Price below EMA200 ({ema200:.2f}) — downtrend confirmed")
        else:
            risks.append("EMA200 trend opposes signal direction")

    smc_score = smc.get("score", 50)
    if direction == "bullish" and smc_score > 60:
        strengths.append(f"SMC score bullish at {smc_score:.0f}/100")
    elif direction == "bearish" and smc_score < 40:
        strengths.append(f"SMC score bearish at {smc_score:.0f}/100")
    else:
        risks.append(f"SMC score neutral ({smc_score:.0f}/100)")

    if sig.rr_ratio:
        if sig.rr_ratio >= 2.0:
            strengths.append(f"Excellent R:R ratio of {sig.rr_ratio:.1f}")
        elif sig.rr_ratio >= 1.5:
            strengths.append(f"Good R:R ratio of {sig.rr_ratio:.1f}")
        else:
            risks.append(f"Low R:R ratio of {sig.rr_ratio:.1f} — consider waiting for better entry")

    if confidence >= 70:
        recommendation = "TAKE TRADE"
    elif confidence >= 50:
        recommendation = "WAIT"
    else:
        recommendation = "SKIP"

    analysis = (
        f"{sig.signal_type} signal on {sig.symbol} {sig.timeframe} with {confidence:.0f}% confidence. "
        f"{len(strengths)} confirming factors and {len(risks)} risk factors identified. "
        f"Recommendation: {recommendation}."
    )

    return {
        "analysis": analysis,
        "strengths": strengths,
        "risks": risks,
        "recommendation": recommendation,
    }


@router.post("/analyze-signal")
def analyze_signal(payload: AnalyzeSignalIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    sig = db.query(Signal).filter(Signal.id == payload.signal_id).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")

    candles = _load_candles(db, sig.symbol, sig.timeframe)
    snap = compute_snapshot(candles) if candles else {}
    smc = smc_service.score(candles) if candles else {}

    return _analyze_signal_data(sig, snap, smc)


@router.post("/daily-bias")
def daily_bias(payload: DailyBiasIn) -> Dict[str, Any]:
    snap = payload.snapshot or {}
    signals: List[Dict[str, Any]] = []

    rsi = snap.get("rsi")
    if rsi is not None:
        if rsi > 70:
            signals.append({"direction": "bearish", "weight": 2,
                             "text": f"RSI {rsi:.1f} — overbought (>70), bearish reversal ehtimoli"})
        elif rsi < 30:
            signals.append({"direction": "bullish", "weight": 2,
                             "text": f"RSI {rsi:.1f} — oversold (<30), bullish reversal ehtimoli"})
        elif rsi > 55:
            signals.append({"direction": "bullish", "weight": 1,
                             "text": f"RSI {rsi:.1f} — bullish zone (50-70)"})
        elif rsi < 45:
            signals.append({"direction": "bearish", "weight": 1,
                             "text": f"RSI {rsi:.1f} — bearish zone (30-50)"})

    macd = snap.get("macd")
    macd_sig = snap.get("macd_signal")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig:
            signals.append({"direction": "bullish", "weight": 2,
                             "text": f"MACD ({macd:.4f}) > Signal ({macd_sig:.4f}) — bullish momentum"})
        else:
            signals.append({"direction": "bearish", "weight": 2,
                             "text": f"MACD ({macd:.4f}) < Signal ({macd_sig:.4f}) — bearish momentum"})

    ema_200 = snap.get("ema_200")
    ema_50  = snap.get("ema_50")
    ema_20  = snap.get("ema_20")
    bb_mid  = snap.get("bb_mid")
    if bb_mid and ema_200:
        price = bb_mid
        if price > ema_200:
            signals.append({"direction": "bullish", "weight": 2,
                             "text": f"Narx EMA200 ({ema_200:.2f}) dan yuqorida — uzoq muddatli bullish trend"})
        else:
            signals.append({"direction": "bearish", "weight": 2,
                             "text": f"Narx EMA200 ({ema_200:.2f}) dan pastda — uzoq muddatli bearish trend"})
        if ema_20 and ema_50:
            if ema_20 > ema_50:
                signals.append({"direction": "bullish", "weight": 1,
                                 "text": f"EMA20 ({ema_20:.2f}) > EMA50 ({ema_50:.2f}) — qisqa muddatli bullish"})
            else:
                signals.append({"direction": "bearish", "weight": 1,
                                 "text": f"EMA20 ({ema_20:.2f}) < EMA50 ({ema_50:.2f}) — qisqa muddatli bearish"})

    bb_upper = snap.get("bb_upper")
    bb_lower = snap.get("bb_lower")
    if bb_mid and bb_upper and bb_lower:
        price = bb_mid
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            pos = (price - bb_lower) / bb_range
            if pos > 0.85:
                signals.append({"direction": "bearish", "weight": 1,
                                 "text": f"Narx Bollinger yuqori bantiga yaqin ({pos*100:.0f}%) — qisqarish ehtimoli"})
            elif pos < 0.15:
                signals.append({"direction": "bullish", "weight": 1,
                                 "text": f"Narx Bollinger quyi bantiga yaqin ({pos*100:.0f}%) — ko'tarilish ehtimoli"})

    atr = snap.get("atr")
    atr_text = f"ATR: {atr:.4f}" if atr else ""

    bull_score = sum(s["weight"] for s in signals if s["direction"] == "bullish")
    bear_score = sum(s["weight"] for s in signals if s["direction"] == "bearish")
    total = bull_score + bear_score or 1

    if bull_score > bear_score:
        direction  = "bullish"
        bias       = "LONG"
        confidence = min(50 + int((bull_score / total) * 40), 88)
    elif bear_score > bull_score:
        direction  = "bearish"
        bias       = "SHORT"
        confidence = min(50 + int((bear_score / total) * 40), 88)
    else:
        direction  = "neutral"
        bias       = "NEUTRAL"
        confidence = 45

    bullish_points = [s["text"] for s in signals if s["direction"] == "bullish"]
    bearish_points = [s["text"] for s in signals if s["direction"] == "bearish"]

    reasoning_parts = []
    if bullish_points:
        reasoning_parts.append("📈 Bullish omillar:\n" + "\n".join(f"  • {t}" for t in bullish_points))
    if bearish_points:
        reasoning_parts.append("📉 Bearish omillar:\n" + "\n".join(f"  • {t}" for t in bearish_points))
    if atr_text:
        reasoning_parts.append(f"📊 Volatillik: {atr_text}")

    reasoning = "\n\n".join(reasoning_parts) or "Indikator ma'lumotlari yetarli emas."

    return {
        "bias":          bias,
        "direction":     direction,
        "confidence":    confidence,
        "reasoning":     reasoning,
        "bull_score":    bull_score,
        "bear_score":    bear_score,
        "signals":       signals,
        "key_levels":    [],
    }
