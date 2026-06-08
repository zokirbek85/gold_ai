"""
ML Feedback API Endpointlari
GET  /api/v1/ml/feedback/accuracy       — Aniqlik statistikasi
GET  /api/v1/ml/feedback/error-patterns — Xato sharoitlar
POST /api/v1/ml/feedback/retrain        — Qo'lda retrain
GET  /api/v1/ml/feedback/history        — Prediction tarixi
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException

router = APIRouter(prefix="/ml/feedback", tags=["ml-feedback"])


def _get_db():
    try:
        from database import SessionLocal
    except ImportError:
        from src.database.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/accuracy")
def get_ml_accuracy(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    last_n: int = Query(100, ge=10, le=1000),
    db=Depends(_get_db),
):
    from src.machine_learning.outcome_checker import outcome_checker
    return outcome_checker.get_recent_accuracy(db, symbol, timeframe, last_n)


@router.get("/error-patterns")
def get_error_patterns(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    min_occurrences: int = Query(3, ge=1),
    db=Depends(_get_db),
):
    from src.machine_learning.outcome_checker import outcome_checker
    patterns = outcome_checker.get_error_patterns_summary(
        db, symbol, timeframe, min_occurrences
    )
    return {"symbol": symbol, "timeframe": timeframe, "patterns": patterns}


@router.post("/retrain")
def trigger_retrain(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    db=Depends(_get_db),
):
    try:
        from src.database.models import Candle
        rows = (
            db.query(Candle)
            .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.asc())
            .limit(500)
            .all()
        )
        candles = [
            {"open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume, "timestamp": r.timestamp}
            for r in rows
        ]
        from src.machine_learning.incremental_trainer import incremental_trainer
        return incremental_trainer.maybe_retrain(
            db, symbol, timeframe, candles, force=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def get_prediction_history(
    symbol: str = Query("XAUUSD"),
    timeframe: str = Query("60"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(_get_db),
):
    try:
        from src.machine_learning.feedback_models import PredictionResult
        rows = (
            db.query(PredictionResult)
            .filter(
                PredictionResult.symbol == symbol,
                PredictionResult.timeframe == timeframe,
            )
            .order_by(PredictionResult.resolved_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = (
            db.query(PredictionResult)
            .filter(
                PredictionResult.symbol == symbol,
                PredictionResult.timeframe == timeframe,
            )
            .count()
        )
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "total": total,
            "results": [
                {
                    "id": r.id,
                    "predicted_at": r.predicted_at.isoformat() if r.predicted_at else None,
                    "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                    "predicted_dir": r.predicted_dir,
                    "actual_dir": r.actual_dir,
                    "price_change_pct": r.price_change_pct,
                    "was_correct": r.was_correct,
                    "rsi_at_signal": r.rsi_at_signal,
                    "trend_strength": r.trend_strength,
                    "session": r.session,
                }
                for r in rows
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
