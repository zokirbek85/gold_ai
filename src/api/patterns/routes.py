from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import models
from src.database.session import get_db
from src.patterns.candlestick import candlestick_detector
from src.patterns.chart import chart_detector

router = APIRouter()


class PatternOut(BaseModel):
    name: str
    direction: str
    confidence: float
    description: str
    extra: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


def _candles_from_db(db: Session, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
    rows = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == symbol, models.Candle.timeframe == timeframe)
        .order_by(models.Candle.timestamp.asc())
        .limit(limit)
        .all()
    )
    return [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]


@router.get("/candlestick", response_model=List[PatternOut])
def detect_candlestick(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _candles_from_db(db, symbol, timeframe, limit=20)
    raw = candlestick_detector.detect_all(candles)
    return [
        PatternOut(
            name=p["name"],
            direction=p["direction"],
            confidence=p["confidence"],
            description=p["description"],
        )
        for p in raw
    ]


@router.get("/chart", response_model=List[PatternOut])
def detect_chart(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _candles_from_db(db, symbol, timeframe, limit=100)
    raw = chart_detector.detect_all(candles)
    return [
        PatternOut(
            name=p["name"],
            direction=p["direction"],
            confidence=p["confidence"],
            description=p["description"],
            extra={k: v for k, v in p.items() if k not in ("name", "direction", "confidence", "description")},
        )
        for p in raw
    ]


@router.get("/all", response_model=List[PatternOut])
def detect_all_patterns(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles_short = _candles_from_db(db, symbol, timeframe, limit=20)
    candles_long = _candles_from_db(db, symbol, timeframe, limit=100)
    all_patterns = []
    for p in candlestick_detector.detect_all(candles_short):
        all_patterns.append(PatternOut(name=p["name"], direction=p["direction"], confidence=p["confidence"], description=p["description"]))
    for p in chart_detector.detect_all(candles_long):
        all_patterns.append(PatternOut(
            name=p["name"],
            direction=p["direction"],
            confidence=p["confidence"],
            description=p["description"],
            extra={k: v for k, v in p.items() if k not in ("name", "direction", "confidence", "description")},
        ))
    return sorted(all_patterns, key=lambda x: x.confidence, reverse=True)
