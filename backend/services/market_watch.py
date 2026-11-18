"""
Real-time market watcher: "pay attention" messages, NOT trade signals.

Runs every minute on the Twelvedata WebSocket ticks plus stored H1/D1 bars:
  * sharp move  — price moved ≥ MOVE_ATR × ATR(H1) within the last 15 minutes
  * volatility  — current H1 ATR ≥ VOL_RATIO × its 100-bar median (regime change)
  * key levels  — first break of the previous day's high / low today
  * news        — high-impact USD event starts within NEWS_LEAD minutes

Why these are notices, not signals: in the 2021–26 study the high-volatility
regime had a NEGATIVE average forward move and trading the first move after
NFP/CPI/FOMC lost money after costs (docs/GOLD_AI_LAB_2026-10.md §6). The
watcher tells the owner WHEN to look; trade decisions stay with the validated
strategy.

WS ticks are sparse (a few per minute, minute-rounded timestamps), so the
watcher uses arrival time and never writes tick-built bars to the database.
"""
from __future__ import annotations

import logging
import os
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

from services.watchdog import market_paused, md

log = logging.getLogger(__name__)

SYMBOL = "XAUUSD"
WINDOW = timedelta(minutes=15)
MOVE_ATR = float(os.getenv("WATCH_MOVE_ATR", "1.0"))
VOL_RATIO = float(os.getenv("WATCH_VOL_RATIO", "1.8"))
NEWS_LEAD = timedelta(minutes=int(os.getenv("WATCH_NEWS_LEAD_MIN", "30")))
NEWS_MIN_IMPACT = 3
MAX_TICK_AGE = timedelta(minutes=3)
MAX_PER_HOUR = 6
COOLDOWN = {"move_up": timedelta(minutes=60), "move_down": timedelta(minutes=60),
            "volatility": timedelta(hours=6)}
FOOTER = "\n_Kuzatuv xabari — savdo signali emas._"

_lock = threading.Lock()
_ticks: Dict[str, Deque[Tuple[datetime, float]]] = {}
_sent: Dict[str, datetime] = {}           # alert key → last sent
_sent_times: Deque[datetime] = deque(maxlen=MAX_PER_HOUR)
_last: Dict[str, Any] = {}               # last computed snapshot (for the API)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── tick feed (called from the WebSocket thread) ─────────────────────────────

def on_tick(symbol: str, price: float, at: Optional[datetime] = None) -> None:
    at = at or _now()
    with _lock:
        dq = _ticks.setdefault(symbol, deque(maxlen=5000))
        dq.append((at, float(price)))


def recent_ticks(symbol: str, since: datetime) -> List[Tuple[datetime, float]]:
    with _lock:
        return [t for t in _ticks.get(symbol, ()) if t[0] >= since]


# ── context from stored bars ─────────────────────────────────────────────────

def _context(db, now: datetime) -> Dict[str, Any]:
    from models.candle import Candle
    from strategy.data_quality import clean_candles
    from strategy.indicators import atr, rolling_median

    def load(tf: str, n: int):
        rows = (db.query(Candle).filter(Candle.symbol == SYMBOL, Candle.timeframe == tf)
                .order_by(Candle.timestamp.desc()).limit(n).all())
        raw = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume,
                "timestamp": r.timestamp} for r in reversed(rows)]
        df, _ = clean_candles(raw, int(tf), now)
        return df

    ctx: Dict[str, Any] = {}
    h1 = load("60", 200)
    if len(h1) >= 30:
        a = atr(h1["high"].to_numpy(), h1["low"].to_numpy(), h1["close"].to_numpy(), 14)
        med = rolling_median(a, 100)
        ctx["atr_h1"] = float(a[-1]) if np.isfinite(a[-1]) else None
        ctx["atr_h1_median"] = float(med[-1]) if np.isfinite(med[-1]) else None
    d1 = load("1440", 7)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # previous TRADING day: the short Sunday-evening session bar is not a "day"
    prev = d1[(d1["timestamp"] < today) & (d1["timestamp"].dt.weekday < 5)] if len(d1) else d1
    if len(prev):
        ctx["pdh"], ctx["pdl"] = float(prev["high"].iloc[-1]), float(prev["low"].iloc[-1])
        ctx["pd_date"] = prev["timestamp"].iloc[-1].strftime("%Y-%m-%d")
    return ctx


def _upcoming_events(db, now: datetime) -> List[Any]:
    from models.economic_calendar import EconomicEvent
    return (db.query(EconomicEvent)
            .filter(EconomicEvent.currency == "USD", EconomicEvent.impact >= NEWS_MIN_IMPACT,
                    EconomicEvent.event_time > now, EconomicEvent.event_time <= now + NEWS_LEAD)
            .order_by(EconomicEvent.event_time.asc()).all())


def _open_paper_trades(db) -> int:
    try:
        from models.paper import PaperTrade
        return db.query(PaperTrade).filter(PaperTrade.status.in_(["PENDING", "OPEN"])).count()
    except Exception:
        db.rollback()
        return 0


# ── evaluation ───────────────────────────────────────────────────────────────

def evaluate(now: datetime, price: float, ticks: List[Tuple[datetime, float]], ctx: Dict[str, Any],
             events: List[Any], open_trades: int = 0) -> List[Tuple[str, str, Optional[timedelta]]]:
    """Pure decision step → [(key, message, cooldown or None=once per key)]."""
    out: List[Tuple[str, str, Optional[timedelta]]] = []
    atr_h1 = ctx.get("atr_h1")

    if atr_h1 and ticks:
        first = ticks[0][1]
        move = price - first
        if abs(move) >= MOVE_ATR * atr_h1:
            key = "move_up" if move > 0 else "move_down"
            arrow = "📈" if move > 0 else "📉"
            out.append((key, f"{arrow} *Keskin harakat*: XAUUSD {move:+.2f}$ so'nggi 15 daqiqada "
                             f"({abs(move) / atr_h1:.1f}× H1 ATR = {atr_h1:.2f}$)\nNarx: {price:.2f}", COOLDOWN[key]))

    med = ctx.get("atr_h1_median")
    if atr_h1 and med and atr_h1 >= VOL_RATIO * med:
        out.append(("volatility", f"🌪 *Volatillik yuqori*: H1 ATR {atr_h1:.2f}$ — odatdagidan {atr_h1 / med:.1f}× katta "
                                  f"(100 shamlik median {med:.2f}$).\nSpread kengayishi va keskin qaytishlar ehtimoli yuqori.",
                    COOLDOWN["volatility"]))

    # only a FRESH break (crossed inside the 15-min window) — after a restart, a level
    # broken hours ago must not be reported as news
    day = now.strftime("%Y-%m-%d")
    pdh, pdl = ctx.get("pdh"), ctx.get("pdl")
    start = ticks[0][1] if ticks else price
    if pdh and start <= pdh < price:
        out.append((f"pdh:{day}", f"⬆️ *Kechagi maksimum yorildi*: narx {price:.2f} > PDH {pdh:.2f} ({ctx.get('pd_date')})", None))
    if pdl and start >= pdl > price:
        out.append((f"pdl:{day}", f"⬇️ *Kechagi minimum yorildi*: narx {price:.2f} < PDL {pdl:.2f} ({ctx.get('pd_date')})", None))

    for e in events:
        mins = max(0, int((e.event_time - now).total_seconds() // 60))
        warn = f"\n⚠️ {open_trades} ta ochiq/kutilayotgan paper savdo bor." if open_trades else ""
        out.append((f"news:{e.event}:{e.event_time.isoformat()}",
                    f"📰 *{mins} daqiqadan keyin*: {md(e.event)} (USD, yuqori ta'sir) — {e.event_time:%H:%M} UTC\n"
                    f"Tarixan CPI/NFP/FOMC atrofida 15 daqiqalik diapazon ~5× kengayadi.{warn}", None))
    return out


def run(now: Optional[datetime] = None, db_factory: Optional[Callable] = None,
        notify: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    now = now or _now()
    if market_paused(now):
        return {"status": "market_paused"}
    if db_factory is None:
        from database import SessionLocal as db_factory
    if notify is None:
        from services.telegram_service import broadcast as notify

    ticks = recent_ticks(SYMBOL, now - WINDOW)
    if not ticks or now - ticks[-1][0] > MAX_TICK_AGE:
        return {"status": "no_live_price"}
    price = ticks[-1][1]

    db = db_factory()
    try:
        ctx = _context(db, now)
        events = _upcoming_events(db, now)
        open_trades = _open_paper_trades(db) if events else 0
    finally:
        db.close()

    alerts = evaluate(now, price, ticks, ctx, events, open_trades)
    sent = []
    with _lock:
        while _sent_times and now - _sent_times[0] > timedelta(hours=1):
            _sent_times.popleft()
        for key, msg, cooldown in alerts:
            last = _sent.get(key)
            if last and (cooldown is None or now - last < cooldown):
                continue
            if len(_sent_times) >= MAX_PER_HOUR:
                log.info("Market watch: hourly cap reached, dropping %s", key)
                break
            _sent[key] = now
            _sent_times.append(now)
            sent.append(msg + FOOTER)
        # forget once-per-key entries from previous days
        for k in [k for k, t in _sent.items() if now - t > timedelta(days=2)]:
            _sent.pop(k, None)
        _last.clear()
        _last.update({"time": now.isoformat(), "price": price, "ticks_15m": len(ticks),
                      "move_15m": round(price - ticks[0][1], 2), **ctx,
                      "upcoming_events": [{"event": e.event, "time": e.event_time.isoformat()} for e in events]})
    for m in sent:
        try:
            notify(m)
        except Exception:
            log.exception("Market watch notify failed")
    return {"status": "ok", "sent": len(sent), "candidates": [a[0] for a in alerts]}


def snapshot() -> Dict[str, Any]:
    with _lock:
        return dict(_last)


def reset() -> None:  # tests
    with _lock:
        _ticks.clear()
        _sent.clear()
        _sent_times.clear()
        _last.clear()
