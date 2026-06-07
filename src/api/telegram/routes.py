from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.deps import require_role
from src.database import models
from src.database.session import get_db
from src.telegram.bot import telegram_bot

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram webhook updates."""
    update = await request.json()
    telegram_bot.process_webhook(update)
    return {"ok": True}


@router.post("/send-signal/{signal_id}", response_model=Dict[str, Any])
def send_signal_alert(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("Admin", "Trader")),
):
    signal = db.query(models.Signal).filter(models.Signal.id == signal_id).first()
    if not signal:
        return {"sent": False, "reason": "Signal not found"}
    signal_data = {
        "symbol": signal.symbol,
        "signal_type": signal.signal_type,
        "timeframe": signal.timeframe,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "risk_reward": signal.rr,
        "confidence": signal.confidence or 0,
        "technical_score": signal.technical_score or 50,
        "smc_score": signal.smc_score or 50,
        "ml_score": signal.ml_score or 50,
        "news_score": signal.news_score or 50,
        "reasoning": signal.reasoning,
    }
    sent = telegram_bot.send_signal_alert(signal_data)
    return {"sent": sent}


@router.post("/send-status", response_model=Dict[str, Any])
def send_status(
    current_user: models.User = Depends(require_role("Admin")),
):
    sent = telegram_bot.send_status({"online": True, "mt4_connected": False, "last_signal": "N/A", "signals_today": 0, "news_count": 0})
    return {"sent": sent}
