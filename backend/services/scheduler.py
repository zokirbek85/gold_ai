"""
APScheduler background tasks:
- Every 5 min: fetch latest XAUUSD candles
- Every 30 min: refresh news
- Every 1 hour: refresh economic calendar
- Every 24 hours: retrain ML model
"""
from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _refresh_candles() -> None:
    from database import SessionLocal
    from services.market_service import fetch_and_store
    db = SessionLocal()
    try:
        fetch_and_store(db, "XAUUSD", "60", limit=10)
        fetch_and_store(db, "XAUUSD", "1440", limit=10)
        log.debug("Candle refresh complete")
    except Exception:
        log.exception("Candle refresh failed")
    finally:
        db.close()


def _refresh_news() -> None:
    from database import SessionLocal
    from services.news_service import refresh_news
    db = SessionLocal()
    try:
        refresh_news(db)
    except Exception:
        log.exception("News refresh failed")
    finally:
        db.close()


def _refresh_calendar() -> None:
    from database import SessionLocal
    from services.calendar_service import refresh_calendar
    db = SessionLocal()
    try:
        refresh_calendar(db)
    except Exception:
        log.exception("Calendar refresh failed")
    finally:
        db.close()


def _retrain_ml() -> None:
    from database import SessionLocal
    from models.candle import Candle
    from models.ml_model import MLModel
    from services import ml_service
    from datetime import datetime
    db = SessionLocal()
    try:
        rows = (
            db.query(Candle)
            .filter(Candle.symbol == "XAUUSD", Candle.timeframe == "60")
            .order_by(Candle.timestamp.asc())
            .limit(1000)
            .all()
        )
        if len(rows) < 200:
            return
        candles = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
        result = ml_service.train("XAUUSD", "60", candles)
        if result.get("status") == "ok":
            record = MLModel(
                symbol="XAUUSD",
                timeframe="60",
                accuracy=result["accuracy"],
                samples=result["samples"],
                trained_at=datetime.utcnow(),
                model_path=f"/app/models/xauusd_60.pkl",
            )
            db.add(record)
            db.commit()
        log.info("ML retrain: %s", result)
    except Exception:
        log.exception("ML retrain failed")
    finally:
        db.close()


def init_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_refresh_candles, IntervalTrigger(minutes=5), id="candles", max_instances=1, replace_existing=True)
    _scheduler.add_job(_refresh_news, IntervalTrigger(minutes=30), id="news", max_instances=1, replace_existing=True)
    _scheduler.add_job(_refresh_calendar, IntervalTrigger(hours=1), id="calendar", max_instances=1, replace_existing=True)
    _scheduler.add_job(_retrain_ml, IntervalTrigger(hours=24), id="ml_train", max_instances=1, replace_existing=True)
    _scheduler.start()
    log.info("Scheduler started")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("Scheduler stopped")
