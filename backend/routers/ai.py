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


def _load_candles(db: Session, symbol: str, timeframe: str) -> list:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.asc())
        .limit(200)
        .all()
    )
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
    candle_summary = payload.candle_summary or "price is consolidating"
    news_summary = payload.news_summary or "mixed news sentiment"
    econ_summary = payload.econ_summary or "upcoming high-impact events"

    bullish_signals = sum(
        1 for word in ["bullish", "above", "rising", "broke above", "uptrend", "buy"]
        if word in (candle_summary + news_summary + econ_summary).lower()
    )
    bearish_signals = sum(
        1 for word in ["bearish", "below", "falling", "broke below", "downtrend", "sell"]
        if word in (candle_summary + news_summary + econ_summary).lower()
    )

    if bullish_signals > bearish_signals:
        direction = "bullish"
        bias = "LONG"
        confidence = min(60 + bullish_signals * 5, 85)
        reasoning = f"Analysis of candle structure ({candle_summary}), news ({news_summary}), and economics ({econ_summary}) shows bullish momentum."
    elif bearish_signals > bullish_signals:
        direction = "bearish"
        bias = "SHORT"
        confidence = min(60 + bearish_signals * 5, 85)
        reasoning = f"Analysis of candle structure ({candle_summary}), news ({news_summary}), and economics ({econ_summary}) shows bearish pressure."
    else:
        direction = "neutral"
        bias = "NEUTRAL"
        confidence = 45
        reasoning = f"Mixed signals from candle structure ({candle_summary}), news ({news_summary}), and economics ({econ_summary}). Wait for clarity."

    return {
        "bias": bias,
        "direction": direction,
        "confidence": confidence,
        "reasoning": reasoning,
        "key_levels": [],
    }
