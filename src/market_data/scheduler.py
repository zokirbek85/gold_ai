import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database import models
from src.database.session import SessionLocal
from src.market_data.mt4_connector import mt4_connector
from src.storage.redis_store import cache_set, publish
from src.indicators.calculator import calculator as _indicator_calc
from src.indicators.repository import IndicatorRepository

log = logging.getLogger(__name__)

scheduler: Optional[BackgroundScheduler] = None


def _parse_list(value: Optional[str], cast_type: Any, default: List[Any]) -> List[Any]:
    if not value:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    result: List[Any] = []
    for item in items:
        try:
            result.append(cast_type(item))
        except ValueError:
            log.warning("Unable to parse '%s' as %s in schedule config", item, cast_type.__name__)
    return result or default


def _get_symbols() -> List[str]:
    return _parse_list(settings.MT4_SYMBOLS, str, ["EURUSD", "USDJPY"])


def _get_timeframes() -> List[int]:
    return _parse_list(settings.MT4_TIMEFRAMES, int, [1, 5, 15])


def _get_ingest_interval() -> int:
    return settings.MT4_INGEST_INTERVAL_SECONDS or 60


def _get_indicator_interval() -> int:
    return settings.INDICATOR_CALC_INTERVAL_SECONDS or 120


def _dt_from_ts(ts: Any) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _session() -> Session:
    return SessionLocal()


def ingest_ticks(db: Session, symbol: str) -> None:
    ticks = mt4_connector.get_ticks(symbol, n=200)
    for tick in ticks:
        timestamp = _dt_from_ts(tick.get("time"))
        price = _to_float(tick.get("last") or tick.get("price") or tick.get("ask") or tick.get("bid"))
        volume = _to_float(tick.get("volume") or tick.get("real_volume"))
        if price <= 0.0 or volume < 0.0:
            continue
        exists = (
            db.query(models.Tick)
            .filter(models.Tick.symbol == symbol)
            .filter(models.Tick.timestamp == timestamp)
            .filter(models.Tick.price == price)
            .first()
        )
        if exists:
            continue
        db.add(models.Tick(symbol=symbol, price=price, volume=volume, timestamp=timestamp))
        cache_set(f"latest:tick:{symbol}", {"symbol": symbol, "price": price, "volume": volume, "timestamp": timestamp.isoformat()})
        publish("market-data-updates", {"type": "tick", "symbol": symbol, "price": price, "volume": volume, "timestamp": timestamp.isoformat()})
        publish(f"market-data-updates:{symbol}", {"type": "tick", "symbol": symbol, "price": price, "volume": volume, "timestamp": timestamp.isoformat()})
    db.commit()


def ingest_candles(db: Session, symbol: str, timeframe: int) -> None:
    candles = mt4_connector.get_candles(symbol, timeframe, count=100)
    for candle in candles:
        timestamp = _dt_from_ts(candle.get("time"))
        open_price = _to_float(candle.get("open"))
        high_price = _to_float(candle.get("high"))
        low_price = _to_float(candle.get("low"))
        close_price = _to_float(candle.get("close"))
        volume = _to_float(candle.get("tick_volume") or candle.get("real_volume") or candle.get("volume"))
        if close_price <= 0.0:
            continue
        timeframe_key = str(timeframe)
        exists = (
            db.query(models.Candle)
            .filter(models.Candle.symbol == symbol)
            .filter(models.Candle.timeframe == timeframe_key)
            .filter(models.Candle.timestamp == timestamp)
            .first()
        )
        if exists:
            continue
        db.add(
            models.Candle(
                symbol=symbol,
                timeframe=timeframe_key,
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
        db.add(
            models.MarketData(
                symbol=symbol,
                timeframe=timeframe_key,
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
        cache_set(
            f"latest:candle:{symbol}:{timeframe_key}",
            {
                "symbol": symbol,
                "timeframe": timeframe_key,
                "timestamp": timestamp.isoformat(),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            },
        )
        publish("market-data-updates", {"type": "candle", "symbol": symbol, "timeframe": timeframe_key, "timestamp": timestamp.isoformat(), "open": open_price, "high": high_price, "low": low_price, "close": close_price, "volume": volume})
        publish(f"market-data-updates:{symbol}", {"type": "candle", "symbol": symbol, "timeframe": timeframe_key, "timestamp": timestamp.isoformat(), "open": open_price, "high": high_price, "low": low_price, "close": close_price, "volume": volume})
    db.commit()


def ingest_market_data() -> None:
    db = _session()
    try:
        if not mt4_connector.connected and not mt4_connector.connect():
            log.warning("MT4 ingestion skipped because connection failed")
            return
        log.info("Starting MT4 ingestion job for symbols=%s", _get_symbols())
        for symbol in _get_symbols():
            ingest_ticks(db, symbol)
            for timeframe in _get_timeframes():
                ingest_candles(db, symbol, timeframe)
    except Exception:
        log.exception("MT4 ingestion job failed")
    finally:
        db.close()


def calculate_indicators() -> None:
    db = _session()
    try:
        log.info("Running indicator calculation for symbols=%s", _get_symbols())
        repo = IndicatorRepository(db)
        for symbol in _get_symbols():
            for timeframe_int in _get_timeframes():
                timeframe_key = str(timeframe_int)
                rows = (
                    db.query(models.Candle)
                    .filter(
                        models.Candle.symbol == symbol,
                        models.Candle.timeframe == timeframe_key,
                    )
                    .order_by(models.Candle.timestamp.asc())
                    .limit(300)
                    .all()
                )
                if len(rows) < 20:
                    continue
                candles_dicts = [
                    {
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume,
                    }
                    for r in rows
                ]
                timestamp = rows[-1].timestamp
                indicators = _indicator_calc.compute_all(candles_dicts)
                repo.bulk_upsert(symbol, timeframe_key, timestamp, indicators)
                # Publish snapshot to Redis
                for name, value in indicators.items():
                    if value is None:
                        continue
                    publish(
                        "indicator-updates",
                        {
                            "symbol": symbol,
                            "timeframe": timeframe_key,
                            "name": name,
                            "value": value,
                            "timestamp": timestamp.isoformat(),
                        },
                    )
                publish(
                    f"indicator-updates:{symbol}",
                    {
                        "symbol": symbol,
                        "timeframe": timeframe_key,
                        "snapshot": {k: v for k, v in indicators.items() if v is not None},
                        "timestamp": timestamp.isoformat(),
                    },
                )
    except Exception:
        log.exception("Indicator calculation job failed")
    finally:
        db.close()


def init_scheduler() -> BackgroundScheduler:
    global scheduler
    if scheduler is not None:
        return scheduler
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        ingest_market_data,
        trigger=IntervalTrigger(seconds=_get_ingest_interval()),
        id="mt4_ingest_job",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        calculate_indicators,
        trigger=IntervalTrigger(seconds=_get_indicator_interval()),
        id="indicator_calculation_job",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    log.info(
        "Scheduler started: ingest every %ss, indicators every %ss",
        _get_ingest_interval(),
        _get_indicator_interval(),
    )
    return scheduler


def shutdown_scheduler() -> None:
    global scheduler
    if scheduler is None:
        return
    scheduler.shutdown(wait=False)
    scheduler = None
    log.info("Scheduler stopped")


def connect_mt4() -> None:
    if mt4_connector.connected:
        return
    if mt4_connector.connect():
        log.info("MT4 connector initialized")
    else:
        log.warning("MT4 connector could not initialize — ZeroMQ EA may not be running")


def disconnect_mt4() -> None:
    mt4_connector.shutdown()
    log.info("MT4 connector shut down")
