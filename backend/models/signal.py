from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from database import Base


class Signal(Base):
    __tablename__ = "signals"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    symbol         = Column(String(20), index=True, nullable=False)
    timeframe      = Column(String(10), index=True, nullable=False)
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
    created_at     = Column(DateTime, default=datetime.utcnow)
