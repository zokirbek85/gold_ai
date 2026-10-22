"""Paper-trading ledger. Virtual money only — no broker connection exists."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Boolean

from database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    mode = Column(String(10), nullable=False, default="paper")  # only "paper" is valid
    start_balance = Column(Float, nullable=False)
    balance = Column(Float, nullable=False)
    peak_balance = Column(Float, nullable=False)
    halted = Column(Boolean, default=False)
    halt_reason = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False, index=True)
    signal_key = Column(String(120), nullable=False)
    signal_id = Column(Integer, nullable=True)
    strategy = Column(String(40), nullable=False)
    strategy_version = Column(String(20), nullable=False)
    config_hash = Column(String(20), nullable=False)
    direction = Column(String(4), nullable=False)
    status = Column(String(12), nullable=False, index=True)  # PENDING|OPEN|CLOSED|CANCELLED
    regime = Column(String(30), nullable=True)
    signal_time = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    entry_ref = Column(Float, nullable=False)
    zone_low = Column(Float, nullable=False)
    zone_high = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    risk_per_oz = Column(Float, nullable=False)
    lots = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    slippage = Column(Float, nullable=False)
    fill_price = Column(Float, nullable=True)
    fill_time = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(30), nullable=True)
    r_multiple = Column(Float, nullable=True)
    pnl_usd = Column(Float, nullable=True)
    costs_usd = Column(Float, nullable=True)
    mfe_r = Column(Float, default=0.0)
    mae_r = Column(Float, default=0.0)
    bars_processed = Column(Integer, default=0)
    open_minutes = Column(Integer, default=0)
    last_bar = Column(DateTime, nullable=True)
    data_gap = Column(Boolean, default=False)
    reasons = Column(Text, nullable=True)  # JSON: signal reasons + score components
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("account_id", "signal_key", name="uq_paper_signal"),)
