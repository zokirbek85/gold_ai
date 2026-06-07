from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db
from src.machine_learning.features import feature_engineer
from src.machine_learning.predictor import ml_predictor
from src.machine_learning.trainer import ml_trainer

router = APIRouter()


class TrainIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"
    lookahead: int = 1


class PredictIn(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "60"


@router.post("/train", response_model=Dict[str, Any])
def train_model(
    payload: TrainIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin")),
):
    rows = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == payload.symbol, models.Candle.timeframe == payload.timeframe)
        .order_by(models.Candle.timestamp.asc())
        .limit(2000)
        .all()
    )
    if len(rows) < 50:
        raise HTTPException(status_code=422, detail="Not enough candle data for training")

    candles = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
    dataset = feature_engineer.build_dataset(candles, lookahead=payload.lookahead)
    result = ml_trainer.train(dataset)
    return result


@router.post("/predict", response_model=Dict[str, Any])
def predict(
    payload: PredictIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.Candle)
        .filter(models.Candle.symbol == payload.symbol, models.Candle.timeframe == payload.timeframe)
        .order_by(models.Candle.timestamp.asc())
        .limit(300)
        .all()
    )
    if len(rows) < 30:
        raise HTTPException(status_code=422, detail="Not enough candle data for prediction")

    candles = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
    features = feature_engineer.build_features(candles)
    if not features:
        raise HTTPException(status_code=422, detail="Could not build feature vector")

    return ml_predictor.predict(features)


@router.post("/reload", response_model=Dict[str, Any])
def reload_models(
    current_user: models.User = Depends(require_role("Admin")),
):
    loaded = ml_predictor.load_latest()
    return {"loaded": loaded}
