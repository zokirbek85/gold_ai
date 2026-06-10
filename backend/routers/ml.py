import glob
import json
import os
import threading
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from config import settings
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


def _db_candles_for_tf(db: Session, symbol: str, timeframe: str, limit: int = 20_000) -> list:
    """Load candles from DB for a given timeframe."""
    return (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
        .order_by(Candle.timestamp.asc())
        .limit(limit)
        .all()
    )


def _refresh_and_load(db: Session, symbol: str, timeframe: str, limit: int = 20_000) -> list:
    """Fetch latest candles from Twelvedata, upsert, return all from DB."""
    interval = TF_TO_TD.get(str(timeframe), "1h")
    # Twelvedata API caps at 5000 per request; fetch the most recent batch only
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
    db_rows = _refresh_and_load(db, payload.symbol, timeframe, 20_000)
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


# ── Redis helpers ─────────────────────────────────────────────────────────────

def _redis_client():
    try:
        import redis
        r = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        r.ping()
        return r
    except Exception:
        return None


def _set_job(job_id: str, data: Dict[str, Any]) -> None:
    r = _redis_client()
    if r:
        try:
            r.set(f"ml:training:{job_id}", json.dumps(data, default=str), ex=3600)
        except Exception:
            pass


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    r = _redis_client()
    if not r:
        return None
    try:
        raw = r.get(f"ml:training:{job_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ── Background training task ──────────────────────────────────────────────────

def _run_training_job(job_id: str, symbol: str, timeframe: str, days: int) -> None:
    from database import SessionLocal
    _set_job(job_id, {
        "status": "running", "started_at": datetime.utcnow().isoformat(),
        "symbol": symbol, "timeframe": timeframe,
    })
    db = SessionLocal()
    try:
        rows = _refresh_and_load(db, symbol, timeframe, days * 24)
        candles = _to_dicts(rows)
        if len(candles) < 100:
            _set_job(job_id, {
                "status": "failed",
                "reason": f"Only {len(candles)} candles available",
                "symbol": symbol, "timeframe": timeframe,
            })
            return
        result = ml_service.train(symbol, timeframe, candles)
        if result.get("status") == "ok":
            record = MLModel(
                symbol=symbol, timeframe=timeframe,
                accuracy=result.get("accuracy"), samples=result.get("samples"),
                trained_at=datetime.utcnow(),
                model_path=os.path.join(settings.ML_MODEL_DIR, f"{symbol.lower()}_{timeframe}.pkl"),
            )
            db.add(record)
            db.commit()
        _set_job(job_id, {
            "status": "done", "completed_at": datetime.utcnow().isoformat(),
            "symbol": symbol, "timeframe": timeframe,
            "accuracy": result.get("accuracy"),
            "samples":  result.get("samples"),
        })
    except Exception as exc:
        _set_job(job_id, {
            "status": "failed", "error": str(exc),
            "symbol": symbol, "timeframe": timeframe,
        })
    finally:
        db.close()


# ── Async train + status + models endpoints ───────────────────────────────────

@router.post("/train/async")
def train_async(
    symbol: str = "XAUUSD",
    timeframe: str = "60",
    days: int = 730,
) -> Dict[str, Any]:
    """Triggers ML training as a background thread. Returns job_id for status polling."""
    job_id = str(uuid.uuid4())
    _set_job(job_id, {
        "status": "queued", "queued_at": datetime.utcnow().isoformat(),
        "symbol": symbol, "timeframe": timeframe,
    })
    threading.Thread(
        target=_run_training_job,
        args=(job_id, symbol, timeframe, days),
        daemon=True,
    ).start()
    return {"job_id": job_id, "status": "queued", "symbol": symbol, "timeframe": timeframe}


@router.get("/status/{job_id}")
def training_status(job_id: str) -> Dict[str, Any]:
    """Check the status of a background training job."""
    data = _get_job(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return data


@router.get("/models")
def list_models(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """List all trained ML models with accuracy and training date."""
    records = (
        db.query(MLModel)
        .order_by(MLModel.trained_at.desc())
        .limit(50)
        .all()
    )
    result = []
    for r in records:
        result.append({
            "symbol":      r.symbol,
            "timeframe":   r.timeframe,
            "accuracy":    r.accuracy,
            "samples":     r.samples,
            "trained_at":  r.trained_at.isoformat() if r.trained_at else None,
            "model_path":  r.model_path,
            "file_exists": os.path.exists(r.model_path) if r.model_path else False,
        })

    # Also scan ML_MODEL_DIR for pkl files not yet in DB
    pkl_files = glob.glob(os.path.join(settings.ML_MODEL_DIR, "*.pkl"))
    tracked_paths = {r["model_path"] for r in result}
    for fp in pkl_files:
        if fp not in tracked_paths:
            mtime = datetime.utcfromtimestamp(os.path.getmtime(fp))
            result.append({
                "symbol":      os.path.basename(fp).replace(".pkl", ""),
                "timeframe":   None,
                "accuracy":    None,
                "samples":     None,
                "trained_at":  mtime.isoformat(),
                "model_path":  fp,
                "file_exists": True,
            })

    return result
