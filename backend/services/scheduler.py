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
        fetch_and_store(db, "XAUUSD", "240", limit=10)
        fetch_and_store(db, "XAUUSD", "1440", limit=10)
        log.debug("Candle refresh complete")
    except Exception:
        log.exception("Candle refresh failed")
        raise
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
        raise
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
        raise
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
            .order_by(Candle.timestamp.desc())
            .limit(1000)
            .all()
        )
        rows = list(reversed(rows))
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
        raise
    finally:
        db.close()


def _signal_cycle() -> None:
    """Autonomous v2 decision once per hour (H4 bars close every 4 h; dedup makes reruns harmless)."""
    import os
    from database import SessionLocal
    from services.signal_cycle import run_v2
    from config import settings
    if settings.SIGNAL_ENGINE.lower() == "legacy":
        return  # rollback mode: no autonomous v2 decisions / paper entries
    db = SessionLocal()
    try:
        alerts = os.getenv("SIGNAL_CYCLE_ALERTS", "false").lower() in ("1", "true", "yes")
        r = run_v2(db, "XAUUSD", alert=alerts)
        log.info("Signal cycle: %s %s dup=%s paper=%s", r.get("signal_type"), r.get("reason_codes"),
                 r.get("duplicate"), (r.get("paper") or {}).get("status"))
    except Exception:
        log.exception("Signal cycle failed")
        raise
    finally:
        db.close()


def _paper_tick() -> None:
    from database import SessionLocal
    from paper.service import tick
    db = SessionLocal()
    try:
        r = tick(db)
        if r.get("status") not in ("idle", "disabled"):
            log.info("Paper tick: %s", r)
            from services.notify import notify_paper_changes
            notify_paper_changes(r)
    except Exception:
        log.exception("Paper tick failed")
        raise
    finally:
        db.close()


def _resolve_signal_outcomes() -> None:
    from database import SessionLocal
    from services.signal_outcomes import resolve_pending
    db = SessionLocal()
    try:
        resolve_pending(db)
    except Exception:
        db.rollback()
        log.exception("Signal outcome resolution failed")
        raise
    finally:
        db.close()


def _watchdog() -> None:
    from services.watchdog import run_checks
    run_checks()


def _daily_summary() -> None:
    from database import SessionLocal
    from services.notify import daily_summary_text
    from services.telegram_service import broadcast
    db = SessionLocal()
    try:
        broadcast(daily_summary_text(db))
    except Exception:
        log.exception("Daily summary failed")
        raise
    finally:
        db.close()


def _market_watch() -> None:
    from services.market_watch import run
    run()


def _collect_m5() -> None:
    """Keep the stored M5 series continuous (signal outcomes walk M5 paths).
    Paper ticks only fetch M5 while a trade is open; 40 bars every 3 h overlap safely."""
    from database import SessionLocal
    from services.market_service import fetch_and_store
    db = SessionLocal()
    try:
        fetch_and_store(db, "XAUUSD", "5", limit=40)
    except Exception:
        log.exception("M5 collection failed")
        raise
    finally:
        db.close()


def _tracked(job_id: str, fn):
    """Jobs log their own exceptions and re-raise; this records the outcome for the
    watchdog and swallows the error so APScheduler does not log it a second time."""
    from services.watchdog import record_job_result

    def run() -> None:
        try:
            fn()
        except Exception as exc:
            record_job_result(job_id, False, f"{type(exc).__name__}: {exc}")
            return
        record_job_result(job_id, True)
    run.__name__ = run.__qualname__ = fn.__name__  # readable job names in logs
    return run


def init_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    import os
    from apscheduler.triggers.cron import CronTrigger
    # Twelvedata free tier ≈ 800 requests/day: candles 3×96 + paper M5 ≤288 + cycle 2×24
    # + signal outcomes ≤48 (M5, only while a recent signal is unresolved) + M5 collect 8 ≈ 680/day
    _scheduler.add_job(_tracked("candles", _refresh_candles), IntervalTrigger(minutes=int(os.getenv("CANDLE_REFRESH_MINUTES", "15"))),
                       id="candles", max_instances=1, replace_existing=True)
    if os.getenv("SIGNAL_CYCLE_ENABLED", "true").lower() in ("1", "true", "yes"):
        _scheduler.add_job(_tracked("signal_cycle", _signal_cycle), CronTrigger(minute=3), id="signal_cycle", max_instances=1, replace_existing=True)
    if os.getenv("PAPER_TRADING_ENABLED", "true").lower() in ("1", "true", "yes"):
        _scheduler.add_job(_tracked("paper_tick", _paper_tick), IntervalTrigger(minutes=5), id="paper_tick", max_instances=1, replace_existing=True)
    _scheduler.add_job(_tracked("signal_outcomes", _resolve_signal_outcomes), IntervalTrigger(minutes=30), id="signal_outcomes",
                       max_instances=1, replace_existing=True)
    _scheduler.add_job(_tracked("news", _refresh_news), IntervalTrigger(minutes=30), id="news", max_instances=1, replace_existing=True)
    _scheduler.add_job(_tracked("calendar", _refresh_calendar), IntervalTrigger(hours=1), id="calendar", max_instances=1, replace_existing=True)
    _scheduler.add_job(_tracked("ml_train", _retrain_ml), IntervalTrigger(hours=24), id="ml_train", max_instances=1, replace_existing=True)
    if os.getenv("MARKET_WATCH_ENABLED", "true").lower() in ("1", "true", "yes"):
        _scheduler.add_job(_tracked("market_watch", _market_watch), IntervalTrigger(minutes=1), id="market_watch",
                           max_instances=1, replace_existing=True)
    _scheduler.add_job(_tracked("m5_collect", _collect_m5), IntervalTrigger(hours=3), id="m5_collect",
                       max_instances=1, replace_existing=True)
    _scheduler.add_job(_watchdog, IntervalTrigger(minutes=2), id="watchdog", max_instances=1, replace_existing=True)
    if os.getenv("DAILY_SUMMARY_ENABLED", "true").lower() in ("1", "true", "yes"):
        # after the NY close, Mon–Fri
        _scheduler.add_job(_tracked("daily_summary", _daily_summary),
                           CronTrigger(day_of_week="mon-fri", hour=21, minute=10), id="daily_summary",
                           max_instances=1, replace_existing=True)
    _scheduler.start()
    log.info("Scheduler started")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("Scheduler stopped")
