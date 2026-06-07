from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import models
from src.database.session import get_db
from src.smc.engine import smc_engine

router = APIRouter()


def _load_candles(db: Session, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
    rows = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == symbol, models.Candle.timeframe == timeframe)
        .order_by(models.Candle.timestamp.asc())
        .limit(limit)
        .all()
    )
    return [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]


@router.get("/analyze", response_model=Dict[str, Any])
def smc_analyze(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _load_candles(db, symbol, timeframe)
    return smc_engine.analyze(candles)


@router.get("/score", response_model=Dict[str, Any])
def smc_score(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _load_candles(db, symbol, timeframe)
    return smc_engine.score(candles)


@router.get("/market-structure", response_model=List[Dict[str, Any]])
def market_structure(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _load_candles(db, symbol, timeframe)
    return smc_engine.market_structure(candles)


@router.get("/order-blocks", response_model=List[Dict[str, Any]])
def order_blocks(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _load_candles(db, symbol, timeframe)
    return smc_engine.order_blocks(candles)


@router.get("/fvg", response_model=List[Dict[str, Any]])
def fair_value_gaps(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _load_candles(db, symbol, timeframe)
    return smc_engine.fair_value_gaps(candles)


@router.get("/premium-discount", response_model=Dict[str, Any])
def premium_discount(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    candles = _load_candles(db, symbol, timeframe)
    return smc_engine.premium_discount(candles)
