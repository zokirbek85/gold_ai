"""
Prediction Feedback Models — DB jadvallari
==========================================
PredictionLog    — Har bir prediction saqlanadi (hali natija noma'lum)
PredictionResult — look_ahead bar o'tgach natija yoziladi (to'g'ri/xato)
ErrorPattern     — Xato bo'lgan paytdagi bozor holati (kelajakda qochish uchun)
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean, Text, Index
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PredictionLog(Base):
    """
    Har bir ML prediction bu yerga yoziladi.
    look_ahead bar o'tgach OutcomeChecker bu yozuvni topib natijani hisoblaydi.
    """
    __tablename__ = "prediction_log"

    id              = Column(Integer, primary_key=True)
    symbol          = Column(String(20), nullable=False, index=True)
    timeframe       = Column(String(10), nullable=False)
    predicted_at    = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    candle_time     = Column(DateTime, nullable=False)
    current_price   = Column(Float, nullable=False)
    predicted_dir   = Column(String(10), nullable=False)   # "bullish" | "bearish" | "neutral"
    buy_pct         = Column(Float)
    sell_pct        = Column(Float)
    neutral_pct     = Column(Float)
    confidence      = Column(Float)
    look_ahead      = Column(Integer, default=12)
    features_json   = Column(Text)
    outcome_checked = Column(Boolean, default=False, index=True)

    __table_args__ = (
        Index("ix_predlog_sym_tf_checked", "symbol", "timeframe", "outcome_checked"),
    )


class PredictionResult(Base):
    """Prediction natijasi — to'g'ri yoki xato."""
    __tablename__ = "prediction_result"

    id               = Column(Integer, primary_key=True)
    prediction_id    = Column(Integer, nullable=False, index=True)
    symbol           = Column(String(20), nullable=False, index=True)
    timeframe        = Column(String(10), nullable=False)
    predicted_at     = Column(DateTime, nullable=False)
    resolved_at      = Column(DateTime, default=datetime.utcnow)
    predicted_dir    = Column(String(10), nullable=False)
    actual_dir       = Column(String(10), nullable=False)
    entry_price      = Column(Float, nullable=False)
    exit_price       = Column(Float, nullable=False)
    price_change_pct = Column(Float, nullable=False)
    was_correct      = Column(Boolean, nullable=False, index=True)
    market_volatility= Column(Float)
    trend_strength   = Column(Float)
    rsi_at_signal    = Column(Float)
    session          = Column(String(20))   # "london" | "newyork" | "asian"
    notes            = Column(Text)

    __table_args__ = (
        Index("ix_predresult_sym_tf", "symbol", "timeframe"),
        Index("ix_predresult_correct", "was_correct"),
    )


class ErrorPattern(Base):
    """
    Xato predictionlar tahlili.
    MLTrainer bu jadvaldan o'rganib penalty qo'llaydi.
    """
    __tablename__ = "error_pattern"

    id               = Column(Integer, primary_key=True)
    symbol           = Column(String(20), nullable=False, index=True)
    timeframe        = Column(String(10), nullable=False)
    detected_at      = Column(DateTime, default=datetime.utcnow)
    pattern_type     = Column(String(50), nullable=False, index=True)
    rsi_range_low    = Column(Float)
    rsi_range_high   = Column(Float)
    adx_range_low    = Column(Float)
    adx_range_high   = Column(Float)
    volatility_low   = Column(Float)
    volatility_high  = Column(Float)
    session          = Column(String(20))
    was_predicted    = Column(String(10))
    correct_was      = Column(String(10))
    occurrence_count = Column(Integer, default=1)
    error_rate       = Column(Float)
    weight_penalty   = Column(Float, default=0.1)
    description      = Column(Text)

    __table_args__ = (
        Index("ix_errpat_sym_type", "symbol", "pattern_type"),
    )
