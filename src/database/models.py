import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Float,
    Text,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    role = relationship("Role")


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    description = Column(Text)


class MarketData(Base):
    __tablename__ = "market_data"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10))
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)


class Tick(Base):
    __tablename__ = "ticks"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    price = Column(Float)
    volume = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Candle(Base):
    __tablename__ = "candles"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10), index=True)
    timestamp = Column(DateTime, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)


# Additional Phase 1 tables
from sqlalchemy import JSON


class Indicator(Base):
    __tablename__ = "indicators"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    name = Column(String(100), index=True)
    timeframe = Column(String(10), index=True)
    timestamp = Column(DateTime, index=True)
    value = Column(Float)
    params = Column(JSON, nullable=True)


class Pattern(Base):
    __tablename__ = "patterns"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    name = Column(String(100), index=True)
    timeframe = Column(String(10), index=True)
    timestamp = Column(DateTime, index=True)
    confidence = Column(Float)
    details = Column(Text)


class SMCEvent(Base):
    __tablename__ = "smc_events"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10), index=True)
    event_type = Column(String(100), index=True)
    timestamp = Column(DateTime, index=True)
    details = Column(Text)


class NewsArticle(Base):
    __tablename__ = "news"
    id = Column(Integer, primary_key=True)
    source = Column(String(200), index=True)
    title = Column(String(500))
    url = Column(String(1000))
    published_at = Column(DateTime, index=True)
    content = Column(Text)
    summary = Column(Text)
    impact_score = Column(Integer)
    confidence = Column(Float)
    duration = Column(String(50))
    reliability = Column(Float)


class EconomicEvent(Base):
    __tablename__ = "economic_events"
    id = Column(Integer, primary_key=True)
    provider = Column(String(200))
    event_type = Column(String(200), index=True)
    country = Column(String(100), index=True)
    scheduled_at = Column(DateTime, index=True)
    actual = Column(String(200))
    forecast = Column(String(200))
    previous = Column(String(200))
    surprise = Column(Float)
    impact = Column(Integer)


class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analysis"
    id = Column(Integer, primary_key=True)
    source = Column(String(200))
    score = Column(Float)
    confidence = Column(Float)
    timestamp = Column(DateTime, index=True)
    article_id = Column(Integer, ForeignKey("news.id"), nullable=True)
    article = relationship("NewsArticle")


class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    timeframe = Column(String(10), index=True)
    signal_type = Column(String(20), index=True)  # BUY/SELL/NO_TRADE
    entry = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    rr = Column(Float)
    confidence = Column(Float)
    technical_score = Column(Float)
    smc_score = Column(Float)
    ml_score = Column(Float)
    news_score = Column(Float)
    economic_score = Column(Float)
    reasoning = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    creator = relationship("User")


class SignalHistory(Base):
    __tablename__ = "signal_history"
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signals.id"))
    status = Column(String(50), index=True)
    executed_at = Column(DateTime, index=True)
    result = Column(String(200))
    pnl = Column(Float)
    notes = Column(Text)
    signal = relationship("Signal")


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    size = Column(Float)
    entry_price = Column(Float)
    exit_price = Column(Float)
    profit_loss = Column(Float)
    opened_at = Column(DateTime, index=True)
    closed_at = Column(DateTime, index=True)
    status = Column(String(50), index=True)
    signal = relationship("Signal")
    user = relationship("User")


class TradeNote(Base):
    """Legacy per-trade note (kept for backwards-compat). New journal: TradeJournal."""
    __tablename__ = "trade_notes"
    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey("trades.id"))
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    trade = relationship("Trade")


class TradeJournal(Base):
    __tablename__ = "trade_journal"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, default="XAUUSD", index=True)
    direction = Column(String(10), nullable=False)           # BUY | SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    lot_size = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="open", index=True)  # open | closed | cancelled
    pnl_usd = Column(Float, nullable=True)
    pnl_pips = Column(Float, nullable=True)
    exit_reason = Column(String(50), nullable=True)          # tp_hit | sl_hit | manual | time_exit
    emotion_rating = Column(Integer, nullable=True)          # 1–5
    notes = Column(Text, nullable=True)
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    signal = relationship("Signal")

    @property
    def risk_reward_actual(self) -> Optional[float]:
        if self.exit_price is None or self.entry_price is None or self.stop_loss is None:
            return None
        sl_dist = abs(self.entry_price - self.stop_loss)
        if sl_dist == 0:
            return None
        if self.direction == "BUY":
            return (self.exit_price - self.entry_price) / sl_dist
        # SELL
        return (self.entry_price - self.exit_price) / sl_dist


class Backtest(Base):
    __tablename__ = "backtests"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    parameters = Column(JSON)
    metrics = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIAnalysis(Base):
    __tablename__ = "ai_analysis"
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    model_version = Column(String(200))
    prompt = Column(Text)
    response = Column(Text)
    score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    signal = relationship("Signal")


class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True)
    level = Column(String(20), index=True)
    message = Column(Text)
    context = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    channel = Column(String(50))
    payload = Column(JSON)
    sent_at = Column(DateTime, index=True)
    status = Column(String(50), index=True)
    user = relationship("User")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(200), primary_key=True)
    value = Column(Text)
    description = Column(Text)
