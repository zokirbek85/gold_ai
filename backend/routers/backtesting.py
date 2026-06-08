from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.candle import Candle
from models.backtest import BacktestResult
from services.signal_service import generate_signal

router = APIRouter()


class BacktestIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    window: int = 100


class BacktestOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None
    avg_rr: Optional[float] = None
    max_drawdown: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


def _run_backtest(candles: list, window: int) -> Dict[str, Any]:
    """Walk-forward backtest over candle window."""
    if len(candles) < window + 5:
        return {"error": f"Need at least {window + 5} candles"}

    trades: List[Dict[str, float]] = []
    start = max(50, len(candles) - window)

    for i in range(start, len(candles) - 5):
        window_candles = candles[:i + 1]
        sig = generate_signal(window_candles)

        if sig["signal_type"] not in ("BUY", "SELL"):
            continue

        entry = sig.get("entry")
        sl    = sig.get("stop_loss")
        tp2   = sig.get("take_profit")

        if not entry or not sl or not tp2:
            continue

        future = candles[i + 1 : i + 6]
        future_highs = [float(c["high"]) for c in future]
        future_lows = [float(c["low"]) for c in future]

        if sig["signal_type"] == "BUY":
            hit_tp = any(h >= tp2 for h in future_highs)
            hit_sl = any(l <= sl for l in future_lows)
            if hit_tp and not hit_sl:
                rr = abs(tp2 - entry) / (abs(entry - sl) + 1e-9)
                trades.append({"win": True, "rr": rr})
            elif hit_sl:
                trades.append({"win": False, "rr": 1.0})
        else:
            hit_tp = any(l <= tp2 for l in future_lows)
            hit_sl = any(h >= sl for h in future_highs)
            if hit_tp and not hit_sl:
                rr = abs(tp2 - entry) / (abs(entry - sl) + 1e-9)
                trades.append({"win": True, "rr": rr})
            elif hit_sl:
                trades.append({"win": False, "rr": 1.0})

    if not trades:
        return {"error": "No completed trades in backtest window"}

    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    win_rate = len(wins) / len(trades)
    total_win_r = sum(t["rr"] for t in wins)
    total_loss_r = len(losses)
    profit_factor = total_win_r / (total_loss_r + 1e-9)
    avg_rr = sum(t["rr"] for t in wins) / (len(wins) + 1e-9)

    # Max drawdown (consecutive losses)
    max_dd = 0
    current_dd = 0
    for t in trades:
        if not t["win"]:
            current_dd += 1
            max_dd = max(max_dd, current_dd)
        else:
            current_dd = 0

    return {
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 2),
        "total_trades": len(trades),
        "avg_rr": round(avg_rr, 2),
        "max_drawdown": max_dd,
    }


@router.post("/run")
def run_backtest(payload: BacktestIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = (
        db.query(Candle)
        .filter(Candle.symbol == payload.symbol, Candle.timeframe == str(payload.timeframe))
        .order_by(Candle.timestamp.desc())
        .limit(payload.window + 100)
        .all()
    )
    rows = list(reversed(rows))

    if len(rows) < payload.window + 5:
        raise HTTPException(status_code=422, detail=f"Need at least {payload.window + 5} candles. Only {len(rows)} available.")

    candles = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
    result = _run_backtest(candles, payload.window)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    record = BacktestResult(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        win_rate=result["win_rate"],
        profit_factor=result["profit_factor"],
        total_trades=result["total_trades"],
        avg_rr=result["avg_rr"],
        max_drawdown=result["max_drawdown"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    result["id"] = record.id
    return result


@router.get("", response_model=List[BacktestOut])
def list_backtests(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
) -> List[BacktestResult]:
    return db.query(BacktestResult).order_by(BacktestResult.created_at.desc()).limit(limit).all()
