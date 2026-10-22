"""
One v2 signal cycle: refresh data → decide → de-duplicate → store → (alert, paper).

Shared by POST /signals/generate and the scheduler, so a manual request and an
automatic run can never create two rows / two alerts / two paper positions for
the same closed bar.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models.candle import Candle
from models.economic_calendar import EconomicEvent
from models.signal import Signal

log = logging.getLogger(__name__)


def load_candles(db: Session, symbol: str, timeframe: str, limit: int) -> list:
    rows = (db.query(Candle).filter(Candle.symbol == symbol, Candle.timeframe == str(timeframe))
            .order_by(Candle.timestamp.desc()).limit(limit).all())
    return [{"open": r.open, "high": r.high, "low": r.low, "close": r.close,
             "volume": r.volume, "timestamp": r.timestamp} for r in reversed(rows)]


def live_price(symbol: str, now: datetime, max_age_s: float = 120.0):
    """Twelvedata WS price if fresh. Its bid/ask are synthetic and are not used."""
    from services.twelvedata_service import get_price
    tick = get_price(symbol)
    if not tick or not tick.get("price"):
        return None, None
    try:
        ts = datetime.fromisoformat(str(tick.get("time")).replace("Z", "+00:00"))
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        if (now - ts).total_seconds() > max_age_s:
            return None, "twelvedata_ws_stale"
    except ValueError:
        return None, "twelvedata_ws_bad_time"
    return float(tick["price"]), "twelvedata_ws"


def _naive(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


def run_v2(db: Session, symbol: str = "XAUUSD", account_balance: float = 10000.0,
           now: Optional[datetime] = None, fetch: bool = True, alert: bool = True,
           requested_tf: Optional[str] = None,
           fetch_fn=None, calendar_fn=None, alert_fn=None) -> Dict[str, Any]:
    from strategy import registry
    from strategy.live import generate as live_generate, legacy_view
    from paper import service as paper

    if fetch_fn is None:
        from services.market_service import fetch_and_store as fetch_fn
    if calendar_fn is None:
        from services.calendar_service import refresh_calendar as calendar_fn
    if alert_fn is None:
        from services.telegram_service import alert_signal as alert_fn

    cfg = registry.active_config()
    tf_p, tf_c = str(cfg.primary_tf), str(cfg.context_tf)
    if fetch:
        for tf, limit in ((tf_p, 500), (tf_c, 300)):
            try:
                fetch_fn(db, symbol, tf, limit=limit)
            except Exception:
                db.rollback()  # provider down → decide on stored data; staleness check catches it
        try:
            calendar_fn(db)
        except Exception:
            db.rollback()

    now = _naive(now or datetime.now(timezone.utc))
    events = [{"event": e.event, "currency": e.currency, "impact": e.impact, "event_time": e.event_time}
              for e in db.query(EconomicEvent).filter(EconomicEvent.event_time >= now - timedelta(hours=2),
                                                      EconomicEvent.event_time <= now + timedelta(hours=2)).all()]
    price, price_src = live_price(symbol, now)
    health = paper.health(db)

    sig = live_generate(load_candles(db, symbol, tf_p, 1500), load_candles(db, symbol, tf_c, 400),
                        symbol=symbol, now=now, events=events, live_price=price,
                        live_price_source=price_src, account_balance=account_balance,
                        cfg=cfg, health=health)
    view = legacy_view(sig)
    if requested_tf and requested_tf != tf_p:
        sig["note"] = f"So'ralgan timeframe {requested_tf} e'tiborsiz qoldirildi: faqat tasdiqlangan {tf_p} ishlaydi"

    last = (db.query(Signal).filter(Signal.symbol == symbol, Signal.timeframe == tf_p)
            .order_by(Signal.created_at.desc()).first())
    bar_close = datetime.fromisoformat(view["bar_close"]) if view.get("bar_close") else None
    duplicate = bool(
        last and bar_close and last.signal_type == view["signal_type"]
        and _naive(last.created_at) >= bar_close
        and (view["signal_type"] == "NO TRADE" or (last.entry == view["entry"] and last.stop_loss == view["stop_loss"])))
    if duplicate:
        sig_id, created = last.id, last.created_at
    else:
        cols = {c.name for c in Signal.__table__.columns}
        row = Signal(**{k: v for k, v in view.items() if k in cols and k not in ("id", "created_at")})
        db.add(row)
        db.commit()
        db.refresh(row)
        sig_id, created = row.id, row.created_at

    result = {**sig, **view, "id": sig_id, "created_at": created, "duplicate": duplicate}
    if view["signal_type"] in ("BUY", "SELL") and not duplicate:
        result["paper"] = paper.submit_signal(db, result)
        if alert:
            threading.Thread(target=alert_fn, args=(result,), daemon=True).start()
    return result
