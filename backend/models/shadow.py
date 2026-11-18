"""Shadow (forward-only) signals of candidate strategies: recorded and measured,
never traded, never alerted as trade signals, never mixed into the signals table."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ShadowSignal(Base):
    __tablename__ = "shadow_signals"
    __table_args__ = (UniqueConstraint("strategy", "symbol", "bar_close", name="uq_shadow_strategy_bar"),)

    id = Column(Integer, primary_key=True)
    strategy = Column(String(40), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    signal_type = Column(String(10), nullable=False)        # BUY | SELL
    bar_close = Column(DateTime, nullable=False)            # decision time (close of the signal bar)
    entry = Column(Float, nullable=False)                   # reference = signal bar close
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    atr = Column(Float, nullable=True)
    regime = Column(String(30), nullable=True)
    context_trend = Column(String(10), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    # outcome (same rules as strategy.backtest.simulate: next-bar-open fill, SL first, 48-bar time exit)
    status = Column(String(20), default="open", index=True)   # open | closed | not_filled
    outcome = Column(String(24), nullable=True)
    outcome_r = Column(Float, nullable=True)
    mfe_r = Column(Float, nullable=True)
    mae_r = Column(Float, nullable=True)
    fill_price = Column(Float, nullable=True)
    fill_time = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    data_gap = Column(Boolean, nullable=True)
