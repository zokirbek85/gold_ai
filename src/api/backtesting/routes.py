from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.backtesting.engine import backtest_engine
from src.database import models
from src.database.session import get_db

router = APIRouter()


class BacktestIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    window: int = 100
    step: int = 5
    account_balance: float = 10000.0
    name: str = "backtest"


class BacktestOut(BaseModel):
    id: int
    name: str
    parameters: Optional[Any] = None
    metrics: Optional[Any] = None
    created_at: Any

    class Config:
        from_attributes = True


@router.post("/run", response_model=Dict[str, Any])
def run_backtest(
    payload: BacktestIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Trader", "Admin")),
):
    rows = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == payload.symbol, models.Candle.timeframe == payload.timeframe)
        .order_by(models.Candle.timestamp.asc())
        .limit(2000)
        .all()
    )
    if len(rows) < payload.window + 10:
        raise HTTPException(status_code=422, detail=f"Need at least {payload.window + 10} candles")

    candles = [
        {"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume, "timestamp": r.timestamp}
        for r in rows
    ]

    result = backtest_engine.run(
        candles=candles,
        window=payload.window,
        step=payload.step,
        account_balance=payload.account_balance,
        name=payload.name,
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    # Persist result
    record = models.Backtest(
        name=payload.name,
        parameters={"symbol": payload.symbol, "timeframe": payload.timeframe, "window": payload.window, "step": payload.step},
        metrics=result["metrics"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result["id"] = record.id
    return result


@router.get("/", response_model=List[BacktestOut])
def list_backtests(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.Backtest).order_by(models.Backtest.created_at.desc()).limit(limit).all()


@router.get("/{backtest_id}", response_model=BacktestOut)
def get_backtest(
    backtest_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    bt = db.query(models.Backtest).filter(models.Backtest.id == backtest_id).first()
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return bt
