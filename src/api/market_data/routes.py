from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db
from src.market_data.scheduler import ingest_market_data, scheduler

router = APIRouter()


class CandleOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TickOut(BaseModel):
    id: int
    symbol: str
    timestamp: datetime
    price: float
    volume: float


class MarketDataOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@router.get("/candles", response_model=List[CandleOut])
def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    records = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == symbol)
        .filter(models.Candle.timeframe == timeframe)
        .order_by(models.Candle.timestamp.desc())
        .limit(limit)
        .all()
    )
    return records


@router.get("/ticks", response_model=List[TickOut])
def get_ticks(
    symbol: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    records = (
        db.query(models.Tick)
        .filter(models.Tick.symbol == symbol)
        .order_by(models.Tick.timestamp.desc())
        .limit(limit)
        .all()
    )
    return records


class SchedulerStatusOut(BaseModel):
    enabled: bool
    job_count: int
    next_run: Optional[datetime] = None


@router.get("/market-data", response_model=List[MarketDataOut])
def get_market_data(
    symbol: str,
    timeframe: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    records = (
        db.query(models.MarketData)
        .filter(models.MarketData.symbol == symbol)
        .filter(models.MarketData.timeframe == timeframe)
        .order_by(models.MarketData.timestamp.desc())
        .limit(limit)
        .all()
    )
    return records


@router.post("/ingest", response_model=dict)
def manual_ingest(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin", "Trader")),
):
    ingest_market_data()
    return {"status": "ingestion triggered"}


@router.get("/scheduler", response_model=SchedulerStatusOut)
def scheduler_status(current_user: models.User = Depends(require_role("Admin"))):
    status = bool(scheduler and scheduler.running)
    jobs = scheduler.get_jobs() if scheduler else []
    next_run = jobs[0].next_run_time if jobs else None
    return {
        "enabled": status,
        "job_count": len(jobs),
        "next_run": next_run,
    }
