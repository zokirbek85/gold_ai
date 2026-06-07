"""
Pattern detection router — candlestick and chart patterns.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.candle import Candle

router = APIRouter()

_CANDLESTICK_PATTERNS = [
    ("Doji", "neutral", 0.65),
    ("Hammer", "bullish", 0.72),
    ("Shooting Star", "bearish", 0.70),
    ("Bullish Engulfing", "bullish", 0.78),
    ("Bearish Engulfing", "bearish", 0.75),
    ("Morning Star", "bullish", 0.80),
    ("Evening Star", "bearish", 0.79),
    ("Pin Bar Bullish", "bullish", 0.74),
    ("Pin Bar Bearish", "bearish", 0.73),
]

_CHART_PATTERNS = [
    ("Double Bottom", "bullish", 0.76, "Price tested support twice, reversal likely"),
    ("Double Top", "bearish", 0.74, "Price tested resistance twice, reversal likely"),
    ("Bull Flag", "bullish", 0.71, "Consolidation after strong move, continuation expected"),
    ("Bear Flag", "bearish", 0.69, "Consolidation after strong drop, continuation expected"),
    ("Head and Shoulders", "bearish", 0.77, "Classic reversal pattern at key resistance"),
    ("Inverse Head and Shoulders", "bullish", 0.78, "Classic reversal pattern at key support"),
    ("Ascending Triangle", "bullish", 0.72, "Higher lows into flat resistance, breakout expected"),
    ("Descending Triangle", "bearish", 0.71, "Lower highs into flat support, breakdown expected"),
]


def _detect_patterns_from_candles(candles: list) -> List[Dict[str, Any]]:
    """Detect patterns using simple heuristics on actual OHLC data."""
    if len(candles) < 5:
        return []

    results = []
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    last = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else last

    # Doji
    body = abs(float(last["close"]) - float(last["open"]))
    rng = float(last["high"]) - float(last["low"])
    if rng > 0 and body / rng < 0.1:
        results.append({"name": "Doji", "direction": "neutral", "confidence": 0.65, "description": "Open ≈ Close — indecision"})

    # Hammer
    lower_wick = min(float(last["open"]), float(last["close"])) - float(last["low"])
    upper_wick = float(last["high"]) - max(float(last["open"]), float(last["close"]))
    if rng > 0 and lower_wick > 2 * body and upper_wick < body:
        results.append({"name": "Hammer", "direction": "bullish", "confidence": 0.72, "description": "Long lower wick — potential bullish reversal"})

    # Shooting Star
    if rng > 0 and upper_wick > 2 * body and lower_wick < body:
        results.append({"name": "Shooting Star", "direction": "bearish", "confidence": 0.70, "description": "Long upper wick — potential bearish reversal"})

    # Engulfing
    prev_body = abs(float(prev["close"]) - float(prev["open"]))
    curr_body = body
    if len(candles) >= 2 and curr_body > prev_body:
        if float(prev["close"]) < float(prev["open"]) and float(last["close"]) > float(last["open"]):
            if float(last["open"]) < float(prev["close"]) and float(last["close"]) > float(prev["open"]):
                results.append({"name": "Bullish Engulfing", "direction": "bullish", "confidence": 0.78, "description": "Bull candle engulfs prior bear candle"})
        elif float(prev["close"]) > float(prev["open"]) and float(last["close"]) < float(last["open"]):
            if float(last["open"]) > float(prev["close"]) and float(last["close"]) < float(prev["open"]):
                results.append({"name": "Bearish Engulfing", "direction": "bearish", "confidence": 0.75, "description": "Bear candle engulfs prior bull candle"})

    # Double Bottom (simplified — two similar lows)
    if len(candles) >= 20:
        recent_lows = lows[-20:]
        min_low = min(recent_lows)
        near_lows = [l for l in recent_lows if abs(l - min_low) / (min_low + 1e-9) < 0.002]
        if len(near_lows) >= 2 and closes[-1] > min_low * 1.005:
            results.append({"name": "Double Bottom", "direction": "bullish", "confidence": 0.76, "description": f"Double bottom at {min_low:.2f}"})

    # Double Top
    if len(candles) >= 20:
        recent_highs = highs[-20:]
        max_high = max(recent_highs)
        near_highs = [h for h in recent_highs if abs(h - max_high) / (max_high + 1e-9) < 0.002]
        if len(near_highs) >= 2 and closes[-1] < max_high * 0.995:
            results.append({"name": "Double Top", "direction": "bearish", "confidence": 0.74, "description": f"Double top at {max_high:.2f}"})

    return results


def _load_candles(db: Session, symbol: str, timeframe: str, limit: int = 100) -> list:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.asc())
        .limit(limit)
        .all()
    )
    return [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]


@router.get("/all")
def all_patterns(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    candles = _load_candles(db, symbol, timeframe)
    return _detect_patterns_from_candles(candles)


@router.get("/candlestick")
def candlestick_patterns(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    candles = _load_candles(db, symbol, timeframe)
    all_pats = _detect_patterns_from_candles(candles)
    return [p for p in all_pats if p["name"] in {p[0] for p in _CANDLESTICK_PATTERNS}]


@router.get("/chart")
def chart_patterns(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    candles = _load_candles(db, symbol, timeframe)
    all_pats = _detect_patterns_from_candles(candles)
    return [p for p in all_pats if p["name"] in {p[0] for p in _CHART_PATTERNS}]
