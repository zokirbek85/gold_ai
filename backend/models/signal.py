from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
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
    # Outcome tracking (migration 0007) — filled by services.signal_outcomes
    outcome            = Column(String(24), nullable=True)   # TP|SL|SL_GAP|SL_AMBIGUOUS|TIME|EXPIRED|ENTRY_ZONE_MISSED|OPENED_BEYOND_LEVELS|NO_DATA
    outcome_r          = Column(Float, nullable=True)        # after costs; NULL when never filled
    mfe_r              = Column(Float, nullable=True)
    mae_r              = Column(Float, nullable=True)
    tp1_hit            = Column(Boolean, nullable=True)      # MFE reached TP1 before exit
    fill_price         = Column(Float, nullable=True)
    fill_time          = Column(DateTime, nullable=True)
    exit_price         = Column(Float, nullable=True)
    exit_time          = Column(DateTime, nullable=True)
    resolved_at        = Column(DateTime, nullable=True)
    resolution_tf      = Column(String(10), nullable=True)   # bar timeframe used to walk the path ("5"/"60"/"paper")
    data_gap           = Column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_signal_symbol_tf_created", "symbol", "timeframe", "created_at"),
    )
