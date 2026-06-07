from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.ai_analysis.analyst import ai_analyst
from src.api.deps import get_current_user, require_role
from src.database import models
from src.database.session import get_db

router = APIRouter()


class AnalyzeSignalIn(BaseModel):
    signal_id: int


class DailyBiasIn(BaseModel):
    candle_summary: str = ""
    news_summary: str = ""
    econ_summary: str = ""


@router.post("/analyze-signal", response_model=Dict[str, Any])
def analyze_signal(
    payload: AnalyzeSignalIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    signal = db.query(models.Signal).filter(models.Signal.id == payload.signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_data = {
        "id": signal.id,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "signal_type": signal.signal_type,
        "confidence": signal.confidence or 0,
        "technical_score": signal.technical_score or 50,
        "smc_score": signal.smc_score or 50,
        "ml_score": signal.ml_score or 50,
        "news_score": signal.news_score or 50,
        "economic_score": signal.economic_score or 50,
        "composite_score": (
            (signal.technical_score or 50) * 0.35
            + (signal.smc_score or 50) * 0.25
            + (signal.ml_score or 50) * 0.20
            + (signal.news_score or 50) * 0.10
            + (signal.economic_score or 50) * 0.10
        ),
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "risk_reward": signal.rr,
        "reasoning": signal.reasoning,
    }

    result = ai_analyst.analyze_signal(signal_data)

    # Persist AI analysis
    ai_record = models.AIAnalysis(
        signal_id=signal.id,
        model_version=result.get("model", "unknown"),
        prompt=f"Signal {signal.id} analysis",
        response=result.get("analysis", ""),
        score=signal.confidence,
    )
    db.add(ai_record)
    db.commit()

    return result


@router.post("/daily-bias", response_model=Dict[str, Any])
def daily_bias(
    payload: DailyBiasIn,
    current_user: models.User = Depends(get_current_user),
):
    analysis = ai_analyst.daily_bias(
        candle_summary=payload.candle_summary,
        news_summary=payload.news_summary,
        econ_summary=payload.econ_summary,
    )
    return {
        "analysis": analysis,
        "model": ai_analyst._get_model_name(),
        "created_at": datetime.utcnow().isoformat(),
    }
