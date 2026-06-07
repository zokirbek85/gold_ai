from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models.candle import Candle
from models.ml_model import MLModel
from services import ml_service
from services.market_service import (
    fetch_candles, fetch_twelvedata, upsert_candles,
    fetch_candles_by_range, RANGE_CONFIG, TF_TO_TD,
)

router = APIRouter()


class PredictIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    range: Optional[str] = None   # "1h"|"1d"|"1w"|"1m" — picks context window


class TrainIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    range: Optional[str] = None   # "1d"|"1w"|"1m" — picks timeframe granularity


def _to_dicts(rows) -> list:
    """Convert ORM rows or dicts to plain OHLCV dicts."""
    result = []
    for r in rows:
        if isinstance(r, dict):
            result.append({
                "open": r["open"], "high": r["high"], "low": r["low"],
                "close": r["close"], "volume": r["volume"],
            })
        else:
            result.append({
                "open": r.open, "high": r.high, "low": r.low,
                "close": r.close, "volume": r.volume,
            })
    return result


def _db_candles_for_tf(db: Session, symbol: str, timeframe: str, limit: int = 1000) -> list:
    """Load candles from DB for a given timeframe."""
    return (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.asc())
        .limit(limit)
        .all()
    )


def _refresh_and_load(db: Session, symbol: str, timeframe: str, limit: int = 1000) -> list:
    """Fetch latest candles from Twelvedata, upsert, return all from DB."""
    interval = TF_TO_TD.get(str(timeframe), "1h")
    fresh = fetch_twelvedata(symbol, interval, min(limit, 500))
    if fresh:
        upsert_candles(db, symbol, timeframe, fresh)
    return _db_candles_for_tf(db, symbol, timeframe, limit)


@router.post("/predict")
def predict(payload: PredictIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    range_key = (payload.range or "").lower() or None

    if range_key and range_key in RANGE_CONFIG:
        # Use range to get a focused context window (recent candles)
        rows, timeframe = fetch_candles_by_range(payload.symbol, range_key)
        if rows:
            upsert_candles(db, payload.symbol, timeframe, rows)
        # If range fetch didn't give enough, supplement from DB
        candles = _to_dicts(rows)
        if len(candles) < 50:
            candles = _to_dicts(_db_candles_for_tf(db, payload.symbol, timeframe, 300))
    else:
        timeframe = payload.timeframe
        rows_db = _refresh_and_load(db, payload.symbol, timeframe, 300)
        candles = _to_dicts(rows_db)

    if len(candles) < 50:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough data ({len(candles)} candles). "
                "Check TWELVEDATA_API_KEY or try a longer range."
            ),
        )

    result = ml_service.predict(payload.symbol, timeframe, candles)
    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result.get("message", "ML prediction failed"))
    return result


@router.post("/train")
def train(payload: TrainIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    range_key = (payload.range or "").lower() or None

    if range_key and range_key in RANGE_CONFIG:
        # range selects the timeframe granularity; use ALL available DB candles for training
        _, timeframe, _ = RANGE_CONFIG[range_key]
    else:
        timeframe = payload.timeframe

    # Refresh from Twelvedata then load all DB candles for this timeframe
    db_rows = _refresh_and_load(db, payload.symbol, timeframe, 1000)
    candles = _to_dicts(db_rows)

    if len(candles) < 100:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Need at least 100 candles to train (got {len(candles)}). "
                "Check TWELVEDATA_API_KEY or try a different range."
            ),
        )

    result = ml_service.train(payload.symbol, timeframe, candles)
    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result.get("message", "ML training failed"))

    if result.get("status") == "ok":
        record = MLModel(
            symbol=payload.symbol,
            timeframe=timeframe,
            accuracy=result.get("accuracy"),
            samples=result.get("samples"),
            trained_at=datetime.utcnow(),
            model_path=f"/app/models/{payload.symbol.lower()}_{timeframe}.pkl",
        )
        db.add(record)
        db.commit()

    return result
