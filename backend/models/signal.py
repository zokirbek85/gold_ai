from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy import event
from database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Signal(Base):
    __tablename__ = "signals"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    symbol         = Column(String(20), nullable=False)
    timeframe      = Column(String(10), nullable=False)
    signal_type    = Column(String(10), nullable=False)
    entry          = Column(Float, nullable=True)
    stop_loss      = Column(Float, nullable=True)
    take_profit    = Column(Float, nullable=True)
    tp1            = Column(Float, nullable=True)
    tp3            = Column(Float, nullable=True)
    rr             = Column(Float, nullable=True)
    confidence     = Column(Float, nullable=True)
    technical_score = Column(Float, nullable=True)
    smc_score      = Column(Float, nullable=True)
    ml_score       = Column(Float, nullable=True)
    news_score     = Column(Float, nullable=True)
    economic_score = Column(Float, nullable=True)
    reasoning      = Column(Text, nullable=True)
    status         = Column(String(20), default="active")
    created_at     = Column(DateTime, default=_utcnow)
    updated_at     = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    # Enrichment fields (migration 0004)
    lot_size           = Column(Float, nullable=True)
    risk_amount_usd    = Column(Float, nullable=True)
    plain_explanation  = Column(Text, nullable=True)
    signal_emoji       = Column(String(4), nullable=True)
    sl_distance_pct    = Column(Float, nullable=True)
    tp1_distance_pct   = Column(Float, nullable=True)
    tp2_distance_pct   = Column(Float, nullable=True)
    tp3_distance_pct   = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_signal_symbol_tf_created", "symbol", "timeframe", "created_at"),
    )
