"""
Watchdog: notices when the background system silently stops working and tells
the owner on Telegram — once when a problem starts, once when it recovers.

Checks (skipped while spot gold is closed: Fri 21:00 → Sun 22:00 UTC, and the
daily 21:00–22:00 UTC maintenance break):
  * live_price  — Twelvedata WebSocket XAUUSD tick is older than PRICE_MAX_AGE
  * candles_h1  — newest stored H1 bar closed more than CANDLE_MAX_AGE ago
  * jobs        — a scheduler job failed JOB_FAIL_LIMIT times in a row

State is in memory: a restart re-alerts an ongoing problem once, which is the
desired behaviour after a crash.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

PRICE_MAX_AGE = timedelta(minutes=10)
CANDLE_MAX_AGE = timedelta(hours=2, minutes=30)
REOPEN_GRACE = timedelta(hours=3)     # after the weekend/daily break, data needs time to resume
JOB_FAIL_LIMIT = 3

_lock = threading.Lock()
_state: Dict[str, Dict[str, Any]] = {}      # check → {"ok", "detail", "since"}
_job_fails: Dict[str, int] = {}
_job_last_error: Dict[str, str] = {}

LABEL = {"live_price": "Real vaqt narxi (WebSocket)", "candles_h1": "H1 shamlar",
         "jobs": "Fon vazifalari (scheduler)"}


def md(text: Any) -> str:
    """Escape Telegram legacy-Markdown specials (broadcast uses parse_mode=Markdown)."""
    text = str(text)
    for ch in "_*`[":
        text = text.replace(ch, "\\" + ch)
    return text


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def market_paused(ts: datetime) -> bool:
    from strategy.data_quality import is_market_closed
    return is_market_closed(ts) or ts.hour == 21


def _recently_reopened(ts: datetime) -> bool:
    return any(market_paused(ts - timedelta(minutes=m)) for m in range(0, int(REOPEN_GRACE.total_seconds() // 60), 30))


# ── scheduler listener ───────────────────────────────────────────────────────

def on_job_event(event: Any) -> None:
    """APScheduler EVENT_JOB_EXECUTED | EVENT_JOB_ERROR listener."""
    job = getattr(event, "job_id", "?")
    with _lock:
        if getattr(event, "exception", None) is not None:
            _job_fails[job] = _job_fails.get(job, 0) + 1
            _job_last_error[job] = f"{type(event.exception).__name__}: {event.exception}"[:200]
        else:
            _job_fails[job] = 0


def record_job_result(job: str, ok: bool, error: str = "") -> None:
    """For jobs that catch their own exceptions (they never reach the listener)."""
    with _lock:
        _job_fails[job] = 0 if ok else _job_fails.get(job, 0) + 1
        if not ok:
            _job_last_error[job] = error[:200]


# ── checks ───────────────────────────────────────────────────────────────────

def _check_price(now: datetime) -> Optional[str]:
    from services.twelvedata_service import get_price, is_connected
    tick = get_price("XAUUSD")
    if not tick:
        return "WebSocket'dan XAUUSD narxi hali kelmagan" + ("" if is_connected() else " (ulanish yo'q)")
    try:
        ts = datetime.fromisoformat(str(tick.get("time")).replace("Z", "+00:00"))
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts
    except ValueError:
        return f"Narx vaqti noto'g'ri: {tick.get('time')}"
    age = now - ts
    if age > PRICE_MAX_AGE:
        return f"Oxirgi narx {int(age.total_seconds() // 60)} daqiqa oldin keldi"
    return None


def _check_candles(now: datetime, db_factory: Callable) -> Optional[str]:
    from models.candle import Candle
    db = db_factory()
    try:
        last = (db.query(Candle.timestamp).filter(Candle.symbol == "XAUUSD", Candle.timeframe == "60")
                .order_by(Candle.timestamp.desc()).first())
    finally:
        db.close()
    if not last:
        return "Bazada H1 sham yo'q"
    age = now - (last[0] + timedelta(hours=1))
    if age > CANDLE_MAX_AGE:
        return f"Oxirgi H1 sham {age.total_seconds() / 3600:.1f} soat oldin yopilgan"
    return None


def _check_jobs() -> Optional[str]:
    with _lock:
        bad = {j: n for j, n in _job_fails.items() if n >= JOB_FAIL_LIMIT}
        errs = dict(_job_last_error)
    if not bad:
        return None
    return "; ".join(f"{j}: {n} marta ketma-ket xato ({errs.get(j, '')})" for j, n in sorted(bad.items()))


def run_checks(now: Optional[datetime] = None, db_factory: Optional[Callable] = None,
               notify: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    now = now or _now()
    if db_factory is None:
        from database import SessionLocal as db_factory
    if notify is None:
        from services.telegram_service import broadcast as notify

    paused = market_paused(now) or _recently_reopened(now)
    results: Dict[str, Optional[str]] = {"jobs": _check_jobs()}
    if not paused:
        for name, fn in (("live_price", lambda: _check_price(now)), ("candles_h1", lambda: _check_candles(now, db_factory))):
            try:
                results[name] = fn()
            except Exception as exc:  # a broken check is itself a problem worth reporting
                results[name] = f"Tekshiruv xatosi: {type(exc).__name__}: {exc}"[:200]

    messages = []
    with _lock:
        for name, problem in results.items():
            prev = _state.get(name, {"ok": True})
            if problem and prev["ok"]:
                _state[name] = {"ok": False, "detail": problem, "since": now.isoformat()}
                messages.append(f"⚠️ *Gold AI muammo*: {LABEL[name]}\n{md(problem)}")
            elif problem:
                _state[name] = {**prev, "detail": problem}
            elif not prev["ok"]:
                since = datetime.fromisoformat(prev["since"])
                mins = int((now - since).total_seconds() // 60)
                _state[name] = {"ok": True, "detail": None, "since": now.isoformat()}
                messages.append(f"✅ *Tiklandi*: {LABEL[name]} ({mins} daqiqa davom etdi)")
            else:
                _state[name] = {"ok": True, "detail": None, "since": prev.get("since") or now.isoformat()}
    for m in messages:
        log.warning("Watchdog: %s", m.replace("\n", " "))
        try:
            notify(m)
        except Exception:
            log.exception("Watchdog notify failed")
    return status(now, paused)


def status(now: Optional[datetime] = None, paused: Optional[bool] = None) -> Dict[str, Any]:
    now = now or _now()
    with _lock:
        checks = {k: dict(v) for k, v in _state.items()}
        jobs = dict(_job_fails)
    return {
        "time": now.isoformat(),
        "market_paused": market_paused(now) if paused is None else paused,
        "ok": all(v.get("ok", True) for v in checks.values()),
        "checks": checks,
        "job_consecutive_failures": jobs,
    }


def reset() -> None:  # tests
    with _lock:
        _state.clear()
        _job_fails.clear()
        _job_last_error.clear()
