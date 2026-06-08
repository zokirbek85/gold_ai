import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.candle import Candle
from models.signal import Signal
from services.signal_service import generate_signal
from services.market_service import fetch_and_store
from services.news_service import get_sentiment_summary, refresh_news
from services.calendar_service import get_aggregate_score, refresh_calendar
from services.telegram_service import alert_signal
from src.signals.scorer import signal_scorer

router = APIRouter()


class SignalOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    signal_type: str
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    tp1: Optional[float] = None
    tp3: Optional[float] = None
    rr: Optional[float] = None
    confidence: Optional[float] = None
    technical_score: Optional[float] = None
    smc_score: Optional[float] = None
    ml_score: Optional[float] = None
    news_score: Optional[float] = None
    economic_score: Optional[float] = None
    reasoning: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GenerateSignalIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    account_balance: float = 10000.0
    # Multi-timeframe confluence timeframes
    timeframe_trend:   str = "240"   # H4 — trend direction
    timeframe_primary: str = "60"    # H1 — signal direction (mirrors timeframe by default)
    timeframe_confirm: str = "15"    # M15 — entry trigger


def _load_candles(db: Session, symbol: str, timeframe: str, limit: int = 300) -> list:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [{"open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume, "timestamp": r.timestamp}
            for r in rows]


def _apply_confluence(
    result: Dict[str, Any],
    candles_h4: list,
    candles_h1: list,
    candles_m15: list,
) -> Dict[str, Any]:
    """
    Compute multi-TF confluence and blend it into the signal result dict.
    Mutates and returns result.
    """
    direction = result.get("direction", "neutral")
    # Use a concrete direction for scoring even when composite is in neutral zone
    conf_dir = direction if direction != "neutral" else (
        "bullish" if result.get("composite_score", 50) > 50 else "bearish"
    )

    confluence = signal_scorer.confluence_score(candles_h4, candles_h1, candles_m15, conf_dir)
    alignment  = confluence["alignment"]

    composite = float(result.get("composite_score", 50.0))
    if alignment == "full":
        composite = min(100.0, composite + 8)
    elif alignment == "partial":
        composite = min(100.0, composite + 3)
    else:  # conflict
        composite = max(0.0, composite - 10)
        if composite < 70 and result.get("signal_type") != "NO TRADE":
            result["signal_type"] = "NO TRADE"
            result["direction"]   = "neutral"
            result["stop_loss"]   = None
            result["take_profit"] = None
            result["tp1"]         = None
            result["risk_reward"] = None

    result["composite_score"] = round(composite, 1)
    result["confluence"]      = confluence
    return result


@router.post("/generate")
def generate(
    payload: GenerateSignalIn,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    # Fetch fresh candles from Twelvedata and upsert; use result directly (not re-query)
    fresh_rows = fetch_and_store(db, payload.symbol, payload.timeframe, limit=300)
    candles = [
        {"open": r.open, "high": r.high, "low": r.low,
         "close": r.close, "volume": r.volume, "timestamp": r.timestamp}
        for r in fresh_rows
    ]

    if len(candles) < 50:
        raise HTTPException(
            status_code=422,
            detail="Insufficient candle data. Try again after data ingestion completes.",
        )

    # Refresh news and economic calendar before scoring so sentiment is current
    try:
        refresh_news(db)
    except Exception:
        pass
    try:
        refresh_calendar(db)
    except Exception:
        pass

    news_data  = get_sentiment_summary(db, hours=24)
    econ_data  = get_aggregate_score(db, hours=48)
    news_score = float(news_data.get("score", 50.0))
    econ_score = float(econ_data.get("score", 50.0))

    news_dir  = news_data.get("direction", "neutral")
    news_bull = news_data.get("bullish_count", 0)
    news_bear = news_data.get("bearish_count", 0)
    news_parts = [f"News {news_dir} ({news_bull}↑/{news_bear}↓)"]
    econ_parts = [f"Econ events: {econ_data.get('event_count', 0)} ({econ_score:.0f})"]

    result = generate_signal(
        candles,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        news_score=news_score,
        economic_score=econ_score,
        news_parts=news_parts,
        econ_parts=econ_parts,
    )

    # ── Multi-timeframe confluence ──────────────────────────────────────────
    # Fetch and refresh confluence timeframes too, then re-query with correct order
    fetch_and_store(db, payload.symbol, payload.timeframe_trend,   limit=300)
    fetch_and_store(db, payload.symbol, payload.timeframe_confirm, limit=300)

    candles_trend   = _load_candles(db, payload.symbol, payload.timeframe_trend)
    candles_primary = _load_candles(db, payload.symbol, payload.timeframe_primary)
    candles_confirm = _load_candles(db, payload.symbol, payload.timeframe_confirm)

    if len(candles_trend) >= 50 and len(candles_primary) >= 50 and len(candles_confirm) >= 50:
        result = _apply_confluence(result, candles_trend, candles_primary, candles_confirm)
    else:
        result.setdefault("confluence", None)

    sig = Signal(
        symbol=result["symbol"],
        timeframe=result["timeframe"],
        signal_type=result["signal_type"],
        entry=result.get("entry"),
        stop_loss=result.get("stop_loss"),
        take_profit=result.get("take_profit"),
        tp1=result.get("tp1"),
        tp3=result.get("tp3"),
        rr=result.get("rr"),
        confidence=result.get("confidence"),
        technical_score=result.get("technical_score"),
        smc_score=result.get("smc_score"),
        ml_score=result.get("ml_score"),
        news_score=result.get("news_score"),
        economic_score=result.get("economic_score"),
        reasoning=result.get("reasoning"),
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)

    result["id"]         = sig.id
    result["created_at"] = sig.created_at

    # Send Telegram alert for BUY/SELL signals (non-blocking)
    threading.Thread(target=alert_signal, args=(result,), daemon=True).start()

    return result


@router.get("", response_model=List[SignalOut])
def list_signals(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
) -> List[Signal]:
    q = db.query(Signal).order_by(Signal.created_at.desc())
    if symbol:
        q = q.filter(Signal.symbol == symbol)
    if timeframe:
        q = q.filter(Signal.timeframe == timeframe)
    return q.limit(limit).all()


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: int, db: Session = Depends(get_db)) -> Signal:
    sig = db.query(Signal).filter(Signal.id == signal_id).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig
