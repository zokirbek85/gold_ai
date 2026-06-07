from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services import smc_service
from services.market_service import fetch_candles, fetch_and_store_by_range, upsert_candles, RANGE_CONFIG

router = APIRouter()


def _rows_to_candles(rows: List[Dict]) -> List[Dict]:
    return [
        {"open": r["open"], "high": r["high"], "low": r["low"],
         "close": r["close"], "volume": r["volume"]}
        for r in rows
    ]


def _fresh_candles(db: Session, symbol: str, timeframe: str, range_key: Optional[str]) -> List[Dict]:
    normalized_range = range_key.lower() if range_key else None
    if normalized_range and normalized_range in RANGE_CONFIG:
        rows, _timeframe = fetch_and_store_by_range(db, symbol, normalized_range)
        return _rows_to_candles(rows)

    rows = fetch_candles(symbol, timeframe, 300)
    if rows:
        upsert_candles(db, symbol, timeframe, rows)
    return _rows_to_candles(rows)


def _ensure_enough(candles: List[Dict], minimum: int = 20) -> None:
    if len(candles) < minimum:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough fresh historical data ({len(candles)} candles). "
                "Check TWELVEDATA_API_KEY or try a longer range."
            ),
        )


@router.get("/analyze")
def smc_analyze(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    range_key: Optional[str] = Query(None, alias="range"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    candles = _fresh_candles(db, symbol, timeframe, range_key)
    _ensure_enough(candles)
    return smc_service.analyze(candles)


@router.get("/score")
def smc_score(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    range_key: Optional[str] = Query(None, alias="range"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    candles = _fresh_candles(db, symbol, timeframe, range_key)
    _ensure_enough(candles)
    return smc_service.score(candles)
