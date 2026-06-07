import asyncio
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.candle import Candle
from services.market_service import (
    fetch_and_store, fetch_and_store_by_range, get_latest_tick, RANGE_CONFIG,
)
from services import twelvedata_service

router = APIRouter()


class CandleOut(BaseModel):
    id: int
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TickOut(BaseModel):
    symbol: str
    price: float
    bid: float
    ask: float
    time: str
    volume: Optional[float] = None
    source: Optional[str] = None


def _latest_db_price(db: Session, symbol: str) -> Optional[dict]:
    c = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == "60")
        .order_by(Candle.timestamp.desc())
        .first()
    )
    if not c:
        return None
    spread = c.close * 0.0002
    return {
        "symbol": symbol,
        "price": round(c.close, 4),
        "bid": round(c.close - spread / 2, 4),
        "ask": round(c.close + spread / 2, 4),
        "time": c.timestamp.isoformat(),
        "source": "db_candle",
    }


@router.get("/candles", response_model=List[CandleOut])
def get_candles(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    limit: int = Query(200, le=5000),
    range_key: Optional[str] = Query(None, alias="range"),
    db: Session = Depends(get_db),
):
    """
    Fetch OHLCV candles.
    - Use `range` (1h|4h|1d|1w|1m|3m) to auto-select timeframe and fetch from Twelvedata.
    - Or use `timeframe` + `limit` for manual control.
    """
    if range_key and range_key in RANGE_CONFIG:
        rows, _tf = fetch_and_store_by_range(db, symbol, range_key)
    else:
        rows_raw = fetch_and_store(db, symbol, timeframe, limit)
        rows = []
        for r in rows_raw:
            if isinstance(r, dict):
                rows.append(r)
            else:
                rows.append({
                    "id": r.id, "timestamp": r.timestamp,
                    "open": r.open, "high": r.high, "low": r.low,
                    "close": r.close, "volume": r.volume,
                })

    result = []
    for r in rows:
        if isinstance(r, dict):
            result.append(CandleOut(
                id=r.get("id", 0),
                timestamp=r["timestamp"],
                open=r["open"], high=r["high"], low=r["low"],
                close=r["close"], volume=r["volume"],
            ))
        else:
            result.append(CandleOut(
                id=r.id, timestamp=r.timestamp,
                open=r.open, high=r.high, low=r.low,
                close=r.close, volume=r.volume,
            ))
    return result


@router.get("/ticks", response_model=List[TickOut])
def get_ticks(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Recent H1 candle closes as price history."""
    candles = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == "60")
        .order_by(Candle.timestamp.desc())
        .limit(limit)
        .all()
    )
    if candles:
        return [
            TickOut(
                symbol=symbol,
                price=c.close,
                bid=round(c.close * 0.9999, 4),
                ask=round(c.close * 1.0001, 4),
                time=c.timestamp.isoformat(),
                volume=c.volume,
                source="db",
            )
            for c in candles
        ]
    tick = get_latest_tick(symbol)
    return [TickOut(**{**tick, "volume": None})]


@router.get("/price")
def get_price(
    symbol: str = Query("XAUUSD"),
    db: Session = Depends(get_db),
):
    """Current price: Twelvedata WS cache → yfinance → latest DB candle."""
    td = twelvedata_service.get_price(symbol)
    if td:
        return td

    tick = get_latest_tick(symbol)
    if tick.get("price", 0) > 0 and tick.get("source") != "unavailable":
        return tick

    db_price = _latest_db_price(db, symbol)
    if db_price:
        return db_price

    return tick


@router.get("/stream")
async def stream_price(symbol: str = Query("XAUUSD")):
    """SSE: pushes current price every 2s (Twelvedata) or 5s (fallback)."""

    async def generator():
        while True:
            try:
                td = twelvedata_service.get_price(symbol)
                if td:
                    yield f"data: {json.dumps(td)}\n\n"
                else:
                    tick = await run_in_threadpool(get_latest_tick, symbol)
                    if tick.get("price", 0) > 0:
                        yield f"data: {json.dumps(tick)}\n\n"
            except Exception:
                pass
            await asyncio.sleep(2 if twelvedata_service.is_connected() else 5)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
