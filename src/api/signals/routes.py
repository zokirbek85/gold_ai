from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db
from src.economic_calendar.engine import economic_calendar
from src.news_engine.service import news_service
from src.smc.engine import smc_engine
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


def _load_candles(db: Session, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    rows = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == symbol, models.Candle.timeframe == timeframe)
        .order_by(models.Candle.timestamp.asc())
        .limit(limit)
        .all()
    )
    return [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]


@router.post("/generate", response_model=Dict[str, Any])
def generate_signal(
    payload: GenerateSignalIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Trader", "Admin")),
):
    candles = _load_candles(db, payload.symbol, payload.timeframe)
    if len(candles) < 20:
        raise HTTPException(status_code=422, detail="Insufficient candle data for signal generation")

    smc_result = smc_engine.score(candles)
    news_result = news_service.get_sentiment(hours=24)

    # Economic score from last 48h events
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=48)
    econ_rows = db.query(models.EconomicEvent).filter(models.EconomicEvent.scheduled_at >= cutoff).all()
    econ_events = [
        economic_calendar.score_event(r.event_type, float(r.actual) if r.actual else None,
                                       float(r.forecast) if r.forecast else None,
                                       float(r.previous) if r.previous else None)
        for r in econ_rows
    ]
    econ_result = economic_calendar.aggregate_score(econ_events)

    result = signal_scorer.generate(
        candles=candles,
        smc_score=smc_result,
        news_score=news_result,
        economic_score=econ_result,
        account_balance=payload.account_balance,
    )

    # Persist signal
    signal = models.Signal(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        signal_type=result["signal_type"],
        entry=result.get("entry"),
        stop_loss=result.get("stop_loss"),
        take_profit=result.get("take_profit"),
        rr=result.get("risk_reward"),
        confidence=result.get("confidence"),
        technical_score=result.get("technical_score"),
        smc_score=result.get("smc_score"),
        ml_score=result.get("ml_score"),
        news_score=result.get("news_score"),
        economic_score=result.get("economic_score"),
        reasoning=result.get("reasoning"),
        created_by=current_user.id,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    result["id"] = signal.id
    return result


@router.get("/", response_model=List[SignalOut])
def list_signals(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Signal).order_by(models.Signal.created_at.desc())
    if symbol:
        q = q.filter(models.Signal.symbol == symbol)
    if timeframe:
        q = q.filter(models.Signal.timeframe == timeframe)
    return q.limit(limit).all()


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    signal = db.query(models.Signal).filter(models.Signal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal
