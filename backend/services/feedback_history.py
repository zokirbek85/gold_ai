"""
Feedback history aggregator for GOLD_AI online learning.
Queries the Signal table and computes win rates by timeframe/session/status.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from models.signal import Signal

log = logging.getLogger(__name__)

_SESSION_HOURS = {
    "london_open":       (7, 10),    # 07:00-10:00 UTC
    "ny_open":           (12, 15),   # 12:00-15:00 UTC
    "london_ny_overlap": (13, 17),   # 13:00-17:00 UTC
    "ny_close":          (19, 21),   # 19:00-21:00 UTC
    "asian_session":     (23, 6),    # 23:00-06:00 UTC  (wraps midnight)
    "dead_zone":         (21, 23),   # 21:00-23:00 UTC
}


def _session_for_hour(h: int) -> str:
    if 7 <= h < 10:
        return "london_open"
    if 13 <= h < 17:
        return "london_ny_overlap"
    if 12 <= h < 15:
        return "ny_open"
    if 19 <= h < 21:
        return "ny_close"
    if 21 <= h < 23:
        return "dead_zone"
    if h >= 23 or h < 6:
        return "asian_session"
    return "other"


def _is_win(status: str) -> bool:
    s = (status or "").lower()
    return "tp" in s or s in ("closed_profit", "profit", "won")


def _is_loss(status: str) -> bool:
    s = (status or "").lower()
    return "sl" in s or s in ("closed_loss", "loss", "lost")


def get_feedback_history(db: Session, symbol: str, limit: int = 50) -> Dict[str, Any]:
    """
    Returns the full feedback_history object expected by the GOLD_AI engine.
    """
    try:
        rows = (
            db.query(Signal)
            .filter(Signal.symbol == symbol)
            .order_by(Signal.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception as exc:
        log.warning("feedback_history query failed: %s", exc)
        db.rollback()
        return _empty()

    last_50: List[Dict] = []
    by_tf:      Dict[str, List[bool]] = defaultdict(list)
    by_session: Dict[str, List[bool]] = defaultdict(list)

    consecutive_losses = 0
    current_streak_loss = 0
    drawdown_pips_today = 0.0
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    for sig in rows:
        status = sig.status or "active"
        won = _is_win(status)
        lost = _is_loss(status)

        # Session from created_at hour
        created_h = sig.created_at.hour if sig.created_at else 12
        sess = _session_for_hour(created_h)

        last_50.append({
            "signal_id": str(sig.id),
            "timeframe": sig.timeframe,
            "direction": sig.signal_type,
            "entry": float(sig.entry or 0),
            "sl": float(sig.stop_loss or 0),
            "tp1": float(sig.tp1 or sig.take_profit or 0),
            "outcome": ("tp1_hit" if won else ("sl_hit" if lost else "pending")),
            "pnl_pips": 0.0,
            "regime_at_entry": "unknown",
            "pattern_at_entry": "unknown",
            "news_sentiment_at_entry": "neutral",
            "session_at_entry": sess,
            "error_class": "none",
        })

        if won or lost:
            by_tf[sig.timeframe].append(won)
            by_session[sess].append(won)

        # Today's drawdown (count sl_hits today)
        if lost and sig.created_at:
            created_utc = sig.created_at.replace(tzinfo=timezone.utc) if sig.created_at.tzinfo is None else sig.created_at
            if created_utc >= today_start:
                # Approximate: 1 sl_hit = ~1% drawdown
                drawdown_pips_today += 1.0

    # Consecutive losses (from most recent)
    for entry in last_50:
        if entry["outcome"] == "sl_hit":
            current_streak_loss += 1
        elif entry["outcome"] == "tp1_hit":
            break
        else:
            break
    consecutive_losses = current_streak_loss

    win_rate_by_tf      = {tf: round(sum(v) / len(v), 2) for tf, v in by_tf.items() if v}
    win_rate_by_session = {s: round(sum(v) / len(v), 2) for s, v in by_session.items() if v}

    return {
        "last_50_signals":     last_50,
        "win_rate_by_regime":  {},
        "win_rate_by_session": win_rate_by_session,
        "win_rate_by_pattern": {},
        "avg_rr_achieved":     0.0,
        "consecutive_losses":  consecutive_losses,
        "drawdown_pct_today":  round(min(drawdown_pips_today * 0.5, 10.0), 2),
    }


def _empty() -> Dict[str, Any]:
    return {
        "last_50_signals": [], "win_rate_by_regime": {}, "win_rate_by_session": {},
        "win_rate_by_pattern": {}, "avg_rr_achieved": 0.0,
        "consecutive_losses": 0, "drawdown_pct_today": 0.0,
    }
