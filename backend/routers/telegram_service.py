from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.signal import Signal
from services.telegram_service import (
    alert_signal,
    get_filter_stats,
    send_daily_summary,
    get_registered_chats,
)

router = APIRouter()


class FilterStatsOut(BaseModel):
    sent_today:    int
    blocked_today: int
    last_signal:   Optional[Dict[str, Any]] = None


@router.get("/filter-stats", response_model=FilterStatsOut)
def filter_stats() -> FilterStatsOut:
    """
    Return today's Telegram alert filter statistics.
    Counters reset at midnight (Redis TTL = 86400s).
    """
    stats = get_filter_stats()
    return FilterStatsOut(
        sent_today=stats["sent_today"],
        blocked_today=stats["blocked_today"],
        last_signal=stats["last_signal"],
    )


@router.post("/daily-summary")
def trigger_daily_summary(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Broadcast a daily signal digest to all registered Telegram chats.
    Fetches the last 24h of signals from the database.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)
    rows   = (
        db.query(Signal)
        .filter(Signal.created_at >= cutoff)
        .order_by(Signal.created_at.desc())
        .all()
    )
    signals = [
        {
            "symbol":      r.symbol,
            "signal_type": r.signal_type,
            "confidence":  r.confidence,
        }
        for r in rows
    ]
    delivered = send_daily_summary(signals)
    return {
        "signals_included": len(signals),
        "chats_notified":   delivered,
    }


@router.get("/registered-chats")
def registered_chats() -> Dict[str, Any]:
    """Return the list of chat IDs currently registered for alerts."""
    chats = get_registered_chats()
    return {"count": len(chats), "chat_ids": chats}


@router.post("/send-signal/{signal_id}")
def send_signal_alert(
    signal_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger a Telegram alert for an existing signal (bypasses filter)."""
    sig = db.query(Signal).filter(Signal.id == signal_id).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    signal_data = {
        "symbol":          sig.symbol,
        "signal_type":     sig.signal_type,
        "timeframe":       sig.timeframe,
        "entry":           sig.entry,
        "stop_loss":       sig.stop_loss,
        "take_profit":     sig.take_profit,
        "rr":              sig.rr,
        "confidence":      sig.confidence or 0,
        "technical_score": sig.technical_score or 50,
        "smc_score":       sig.smc_score or 50,
        "ml_score":        sig.ml_score or 50,
        "news_score":      sig.news_score or 50,
        "reasoning":       sig.reasoning,
    }
    delivered = alert_signal(signal_data)
    return {"signal_id": signal_id, "chats_notified": delivered}
