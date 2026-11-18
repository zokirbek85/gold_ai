"""
Signal outcome tracking: every stored BUY/SELL signal gets a measured result.

Before this module every signal stayed ``status="active"`` forever, so signal
accuracy was never known. Resolution uses the SAME fill/exit rules as the
backtester and the paper broker (``paper.broker.process``):

  * entry: first closed bar opening after the signal was stored, whose open is
    inside the entry zone and not beyond SL/TP; otherwise the signal is "not
    filled" (EXPIRED / ENTRY_ZONE_MISSED / OPENED_BEYOND_LEVELS);
  * exit: gap through SL, SL (SL first when SL and TP are inside one bar), TP,
    or time exit after ``MAX_HOLD_BARS`` bars of the signal's timeframe;
  * costs: default ``RiskConfig`` spread + slippage; R is after costs.

Signals that became a paper trade copy that trade's result (exact parity).
Other signals do not store the entry zone / expiry, so these are approximated:
zone = entry ± ZONE_FRAC × risk, expiry = EXPIRY_BARS bars of the signal TF.

Bars: M5 when the stored M5 series covers the signal, else H1 (coarser — the
row records ``resolution_tf`` so statistics can be filtered by it).
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from models.signal import Signal

log = logging.getLogger(__name__)

ZONE_FRAC = 0.25          # entry zone half-width as a fraction of the SL distance
EXPIRY_BARS = 2           # same as StrategyConfig.expiry_bars
MIN_EXPIRY_MIN = 30
MAX_HOLD_BARS = 48        # same as StrategyConfig.max_hold_bars
NO_DATA_AFTER = timedelta(days=21)   # unresolvable after this → outcome NO_DATA
FETCH_WINDOW = timedelta(days=15)    # Twelvedata returns ≤5000 M5 bars (~17 days)

STATUS_BY_OUTCOME = {
    "TP": "tp_hit", "SL": "sl_hit", "SL_GAP": "sl_hit", "SL_AMBIGUOUS": "sl_hit",
    "TIME": "time_exit", "EXPIRED": "not_filled", "ENTRY_ZONE_MISSED": "not_filled",
    "OPENED_BEYOND_LEVELS": "not_filled", "NO_DATA": "no_data", "INVALID": "invalid",
}
RESOLUTIONS = (("5", 5, timedelta(minutes=30)), ("60", 60, timedelta(hours=3)))


def _naive(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


def _tf_minutes(tf: str) -> int:
    try:
        return max(1, int(tf))
    except (TypeError, ValueError):
        return 60


def _valid_levels(s: Signal) -> bool:
    if s.entry is None or s.stop_loss is None or s.take_profit is None:
        return False
    if s.signal_type == "BUY":
        return s.stop_loss < s.entry < s.take_profit
    return s.take_profit < s.entry < s.stop_loss


def _finish(s: Signal, outcome: str, now: datetime, resolution_tf: str, **fields: Any) -> None:
    s.outcome = outcome
    s.status = STATUS_BY_OUTCOME.get(outcome, "closed")
    s.resolved_at = now
    s.resolution_tf = resolution_tf
    for k, v in fields.items():
        setattr(s, k, v)
    if s.tp1 is not None and s.mfe_r is not None and s.fill_price is not None:
        risk = abs(s.entry - s.stop_loss)
        s.tp1_hit = bool(risk and s.mfe_r >= abs(s.tp1 - s.entry) / risk)


def _load_bars(db: Session, symbol: str, tf: str, start: datetime, now: datetime) -> List[Dict[str, Any]]:
    from models.candle import Candle
    from strategy.data_quality import clean_candles
    rows = (db.query(Candle).filter(Candle.symbol == symbol, Candle.timeframe == tf, Candle.timestamp >= start)
            .order_by(Candle.timestamp.asc()).all())
    raw = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close,
            "volume": r.volume, "timestamp": r.timestamp} for r in rows]
    df, _ = clean_candles(raw, _tf_minutes(tf), now)
    return df.to_dict("records") if not df.empty else []


def _covers(bars: List[Dict[str, Any]], t: datetime, max_gap: timedelta) -> bool:
    """True when the series has a bar starting within ``max_gap`` after ``t``."""
    import bisect
    times = [b["timestamp"] for b in bars]
    i = bisect.bisect_left(times, t)
    return i < len(times) and times[i] - t <= max_gap


def _simulate(s: Signal, bars: List[Dict[str, Any]], bar_min: int, max_gap: timedelta):
    from paper.broker import Position, process
    from strategy.config import RiskConfig

    tf_min = _tf_minutes(s.timeframe)
    t0 = _naive(s.created_at)
    risk = abs(s.entry - s.stop_loss)
    half = ZONE_FRAC * risk
    pos = Position(direction=s.signal_type, status="PENDING", signal_time=t0,
                   expires_at=t0 + timedelta(minutes=max(EXPIRY_BARS * tf_min, MIN_EXPIRY_MIN)),
                   entry_ref=s.entry, zone_low=s.entry - half, zone_high=s.entry + half,
                   stop_loss=s.stop_loss, take_profit=s.take_profit, risk_per_oz=risk, lots=0.01)
    return process(pos, bars, RiskConfig(), bar_min,
                   timedelta(minutes=MAX_HOLD_BARS * tf_min), max_gap=max_gap)


def _from_paper(s: Signal, t: Any, now: datetime) -> bool:
    if t.status not in ("CLOSED", "CANCELLED"):
        return False
    _finish(s, t.exit_reason or "INVALID", now, "paper",
            outcome_r=t.r_multiple if t.status == "CLOSED" else None,
            mfe_r=t.mfe_r if t.fill_price is not None else None,
            mae_r=t.mae_r if t.fill_price is not None else None,
            fill_price=t.fill_price, fill_time=t.fill_time, exit_price=t.exit_price,
            exit_time=t.exit_time, data_gap=bool(t.data_gap))
    return True


def resolve_pending(db: Session, now: Optional[datetime] = None, fetch: bool = True,
                    fetch_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Resolve every BUY/SELL signal that has no outcome yet. Idempotent."""
    from models.paper import PaperTrade

    now = _naive(now or datetime.now(timezone.utc))
    pending: List[Signal] = (db.query(Signal)
                             .filter(Signal.signal_type.in_(["BUY", "SELL"]), Signal.outcome.is_(None))
                             .order_by(Signal.created_at.asc()).all())
    if not pending:
        return {"status": "idle", "resolved": 0, "pending": 0}

    paper_by_signal = {t.signal_id: t for t in db.query(PaperTrade)
                       .filter(PaperTrade.signal_id.in_([s.id for s in pending])).all()}

    if fetch:
        recent = [s for s in pending if s.id not in paper_by_signal
                  and _naive(s.created_at) >= now - FETCH_WINDOW]
        if recent:
            if fetch_fn is None:
                from services.market_service import fetch_and_store as fetch_fn
            oldest = min(_naive(s.created_at) for s in recent)
            limit = min(5000, int((now - oldest).total_seconds() // 300) + 50)
            for sym in {s.symbol for s in recent}:
                try:
                    fetch_fn(db, sym, "5", limit=limit)
                except Exception:
                    db.rollback()
                    log.warning("signal outcomes: M5 fetch failed for %s", sym)

    bars_cache: Dict[tuple, List[Dict[str, Any]]] = {}

    def bars_for(sym: str, tf: str) -> List[Dict[str, Any]]:
        key = (sym, tf)
        if key not in bars_cache:
            start = min(_naive(s.created_at) for s in pending if s.symbol == sym) - timedelta(hours=1)
            bars_cache[key] = _load_bars(db, sym, tf, start, now)
        return bars_cache[key]

    counts: Dict[str, int] = defaultdict(int)
    for s in pending:
        if not _valid_levels(s):
            _finish(s, "INVALID", now, "-")
            counts["INVALID"] += 1
            continue
        t = paper_by_signal.get(s.id)
        if t is not None:
            if _from_paper(s, t, now):
                counts[s.outcome] += 1
            continue

        t0 = _naive(s.created_at)
        # Finest resolution whose path is complete wins. Stored M5 has holes (it is only
        # fetched while something is open), so a gapped/unfinished M5 path falls back to H1.
        done = gapped = None
        any_cover = still_open = False
        for tf, bar_min, max_gap in RESOLUTIONS:
            bars = bars_for(s.symbol, tf)
            if not _covers(bars, t0, max_gap):
                continue
            any_cover = True
            pos = _simulate(s, bars, bar_min, max_gap)
            if pos.status not in ("CLOSED", "CANCELLED"):
                if now - t0 <= FETCH_WINDOW:  # finer bars are still arriving → wait for them
                    still_open = True
                    break
                continue
            if not pos.data_gap:
                done = (tf, pos)
                break
            gapped = gapped or (tf, pos)
        pick = done or (None if still_open else gapped)
        if pick:
            tf, pos = pick
            filled = pos.fill_price is not None
            _finish(s, pos.exit_reason, now, tf,
                    outcome_r=pos.r_multiple, mfe_r=round(pos.mfe_r, 3) if filled else None,
                    mae_r=round(pos.mae_r, 3) if filled else None, fill_price=pos.fill_price,
                    fill_time=pos.fill_time, exit_price=pos.exit_price, exit_time=pos.exit_time,
                    data_gap=pos.data_gap)
            counts[s.outcome] += 1
        elif not any_cover and now - t0 > NO_DATA_AFTER:
            _finish(s, "NO_DATA", now, "-")
            counts["NO_DATA"] += 1
    db.commit()
    resolved = sum(counts.values())
    left = len(pending) - resolved
    if resolved:
        log.info("Signal outcomes: resolved %d (%s), %d still open", resolved, dict(counts), left)
    return {"status": "ok", "resolved": resolved, "by_outcome": dict(counts), "pending": left}


# ── Performance statistics ────────────────────────────────────────────────────

CONF_BUCKETS = ((0, 50), (50, 60), (60, 70), (70, 80), (80, 101))


def session_of(hour: int) -> str:
    if 21 <= hour or hour < 0:
        return "rollover"
    if hour < 7:
        return "asia"
    if hour < 12:
        return "london"
    if hour < 16:
        return "london_ny_overlap"
    return "new_york"


def summarize(rs: Iterable[float], mfe: Iterable[Optional[float]] = (), tp1: Iterable[Optional[bool]] = ()) -> Dict[str, Any]:
    rs = [float(r) for r in rs]
    n = len(rs)
    out: Dict[str, Any] = {"trades": n}
    if not n:
        return out
    mean = sum(rs) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 1 else None
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    eq = peak = dd = 0.0
    streak = max_streak = 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        streak = streak + 1 if r <= 0 else 0
        max_streak = max(max_streak, streak)
    mfe = [m for m in mfe if m is not None]
    tp1 = [x for x in tp1 if x is not None]
    out.update({
        "win_rate": round(len(wins) / n * 100, 1),
        "expectancy_r": round(mean, 3),
        "ci95_r": [round(mean - 1.96 * se, 3), round(mean + 1.96 * se, 3)] if se else None,
        "total_r": round(sum(rs), 2),
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
        "avg_win_r": round(sum(wins) / len(wins), 3) if wins else None,
        "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else None,
        "max_drawdown_r": round(dd, 2),
        "max_consecutive_losses": max_streak,
        "avg_mfe_r": round(sum(mfe) / len(mfe), 3) if mfe else None,
        "tp1_hit_rate": round(sum(tp1) / len(tp1) * 100, 1) if tp1 else None,
        "reliable": n >= 30 and se is not None and (mean - 1.96 * se) > 0,
    })
    return out


def _group(rows: List[Signal], key: Callable[[Signal], Any]) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Signal]] = defaultdict(list)
    for s in rows:
        g[str(key(s))].append(s)
    return {k: summarize([s.outcome_r for s in v], [s.mfe_r for s in v], [s.tp1_hit for s in v])
            for k, v in sorted(g.items())}


def _conf_bucket(c: Optional[float]) -> str:
    c = c or 0.0
    for lo, hi in CONF_BUCKETS:
        if lo <= c < hi:
            return f"{lo}-{min(hi, 100)}"
    return "100"


def performance(db: Session, symbol: Optional[str] = None, days: Optional[int] = None,
                timeframe: Optional[str] = None) -> Dict[str, Any]:
    q = db.query(Signal).filter(Signal.signal_type.in_(["BUY", "SELL"]))
    if symbol:
        q = q.filter(Signal.symbol == symbol)
    if timeframe:
        q = q.filter(Signal.timeframe == timeframe)
    if days:
        q = q.filter(Signal.created_at >= datetime.utcnow() - timedelta(days=days))
    rows: List[Signal] = q.order_by(Signal.created_at.asc()).all()

    outcomes: Dict[str, int] = defaultdict(int)
    for s in rows:
        outcomes[s.outcome or "PENDING"] += 1
    filled = [s for s in rows if s.outcome_r is not None]
    filled.sort(key=lambda s: s.exit_time or s.created_at)

    calibration = []
    for k, v in _group(filled, lambda s: _conf_bucket(s.confidence)).items():
        calibration.append({"bucket": k, "trades": v["trades"], "win_rate": v.get("win_rate"),
                            "expectancy_r": v.get("expectancy_r")})

    eq, curve = 0.0, []
    for s in filled:
        eq += s.outcome_r
        curve.append({"time": (s.exit_time or s.created_at).isoformat(), "cum_r": round(eq, 3),
                      "r": round(s.outcome_r, 3), "id": s.id, "timeframe": s.timeframe, "side": s.signal_type})

    overall = summarize([s.outcome_r for s in filled], [s.mfe_r for s in filled], [s.tp1_hit for s in filled])
    notes = []
    if overall["trades"] < 30:
        notes.append(f"Faqat {overall['trades']} ta bajarilgan signal — statistik xulosa uchun kamida 30 ta kerak")
    elif not overall.get("reliable"):
        notes.append("Expectancy CI95 pastki chegarasi ≤ 0 — ustunlik (edge) tasdiqlanmagan")
    coarse = sum(1 for s in filled if s.resolution_tf == "60" and _tf_minutes(s.timeframe) < 60)
    if coarse:
        notes.append(f"{coarse} ta kichik-TF signal H1 shamlarida baholandi (taxminiy, SL-birinchi qoidasi tufayli pessimistik)")

    return {
        "signals": len(rows),
        "outcomes": dict(outcomes),
        "fill_rate": round(len(filled) / max(1, sum(v for k, v in outcomes.items() if k not in ("PENDING", "INVALID", "NO_DATA"))) * 100, 1),
        "overall": overall,
        "by_timeframe": _group(filled, lambda s: s.timeframe),
        "by_side": _group(filled, lambda s: s.signal_type),
        "by_session": _group(filled, lambda s: session_of(_naive(s.created_at).hour)),
        "by_month": _group(filled, lambda s: _naive(s.created_at).strftime("%Y-%m")),
        "by_resolution": _group(filled, lambda s: s.resolution_tf),
        "confidence_calibration": calibration,
        "equity_curve": curve,
        "notes": notes,
        "method": {"zone_frac_of_risk": ZONE_FRAC, "expiry_bars": EXPIRY_BARS, "max_hold_bars": MAX_HOLD_BARS,
                   "costs": "RiskConfig default spread + slippage; R after costs",
                   "same_bar_sl_tp": "SL first (conservative)"},
    }
