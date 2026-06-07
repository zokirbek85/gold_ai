from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db
from src.indicators.repository import IndicatorRepository
from src.market_data.scheduler import calculate_indicators

router = APIRouter()


class IndicatorIn(BaseModel):
    symbol: str
    name: str
    timeframe: str
    timestamp: Optional[datetime] = None
    value: float
    params: Optional[Dict[str, Any]] = None


class IndicatorOut(BaseModel):
    id: int
    symbol: str
    name: str
    timeframe: str
    timestamp: datetime
    value: float

    class Config:
        from_attributes = True


@router.post("/", response_model=Dict[str, Any])
def create_indicator(
    payload: IndicatorIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Trader", "Admin")),
):
    repo = IndicatorRepository(db)
    repo.upsert(
        symbol=payload.symbol,
        name=payload.name,
        timeframe=payload.timeframe,
        timestamp=payload.timestamp or datetime.utcnow(),
        value=payload.value,
        params=payload.params,
    )
    db.commit()
    return {"status": "ok"}


@router.post("/recalculate", response_model=Dict[str, str])
def recalculate_indicators(
    current_user: models.User = Depends(require_role("Admin")),
):
    calculate_indicators()
    return {"status": "indicator recalculation triggered"}


@router.get("/latest", response_model=List[IndicatorOut])
def latest_indicators(
    symbol: str,
    timeframe: str,
    name: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    repo = IndicatorRepository(db)
    rows = repo.get_latest(symbol=symbol, timeframe=timeframe, limit=limit, name=name)
    return rows


@router.get("/snapshot", response_model=Dict[str, float])
def indicator_snapshot(
    symbol: str,
    timeframe: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return the most recent value of every indicator for a symbol/timeframe pair."""
    repo = IndicatorRepository(db)
    return repo.get_snapshot(symbol=symbol, timeframe=timeframe)
