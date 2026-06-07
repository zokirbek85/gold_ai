from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.indicator_service import compute_snapshot, compute_series
from services.market_service import fetch_candles, fetch_and_store_by_range, upsert_candles, RANGE_CONFIG

router = APIRouter()

@router.get("/snapshot")
def indicator_snapshot(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    range_key: Optional[str] = Query(None, alias="range"),
    db: Session = Depends(get_db),
) -> Dict[str, Optional[float]]:
    normalized_range = range_key.lower() if range_key else None
    if normalized_range and normalized_range in RANGE_CONFIG:
        rows, timeframe = fetch_and_store_by_range(db, symbol, normalized_range)
        candles = [
            {"open": r["open"], "high": r["high"], "low": r["low"],
             "close": r["close"], "volume": r["volume"], "timestamp": r["timestamp"]}
            for r in rows
        ]
    else:
        rows = fetch_candles(symbol, timeframe, 500)
        if rows:
            upsert_candles(db, symbol, timeframe, rows)
        candles = [
            {"open": r["open"], "high": r["high"], "low": r["low"],
             "close": r["close"], "volume": r["volume"], "timestamp": r["timestamp"]}
            for r in rows
        ]

    if len(candles) < 26:
        raise HTTPException(
            status_code=422,
            detail="Not enough fresh historical data. Check TWELVEDATA_API_KEY or try a longer range.",
        )
    return compute_snapshot(candles)


@router.get("/latest")
def indicator_series(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    limit: int = Query(50, le=200),
    range_key: Optional[str] = Query(None, alias="range"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    normalized_range = range_key.lower() if range_key else None
    if normalized_range and normalized_range in RANGE_CONFIG:
        rows, timeframe = fetch_and_store_by_range(db, symbol, normalized_range)
        candles = [
            {"open": r["open"], "high": r["high"], "low": r["low"],
             "close": r["close"], "volume": r["volume"], "timestamp": r["timestamp"]}
            for r in rows
        ]
    else:
        rows = fetch_candles(symbol, timeframe, max(limit, 200))
        if rows:
            upsert_candles(db, symbol, timeframe, rows)
        candles = [
            {"open": r["open"], "high": r["high"], "low": r["low"],
             "close": r["close"], "volume": r["volume"], "timestamp": r["timestamp"]}
            for r in rows
        ]

    if len(candles) < 26:
        return []
    return compute_series(candles, limit=limit)
