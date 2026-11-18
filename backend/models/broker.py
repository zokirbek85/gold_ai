"""Real broker quotes from the MetaTrader feed EA (mt4/GoldAI_CostFeed.mq4 / mt5/…mq5).

One row per broker × symbol × minute: spread statistics over that minute plus the
symbol's financing/contract specification, so the cost model can be calibrated
from the user's actual broker instead of assumptions."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint

from database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BrokerQuote(Base):
    __tablename__ = "broker_quotes"
    __table_args__ = (UniqueConstraint("broker", "server", "symbol", "ts", name="uq_broker_quote_minute"),)

    id = Column(Integer, primary_key=True)
    broker = Column(String(80), nullable=False)
    server = Column(String(80), nullable=False)
    is_demo = Column(Boolean, nullable=True)
    symbol = Column(String(20), nullable=False, index=True)        # normalised, e.g. XAUUSD
    broker_symbol = Column(String(30), nullable=True)               # as named by the broker, e.g. GOLD
    ts = Column(DateTime, nullable=False, index=True)               # UTC minute start
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    spread_min = Column(Float, nullable=True)                       # price units (ask - bid)
    spread_avg = Column(Float, nullable=True)
    spread_max = Column(Float, nullable=True)
    ticks = Column(Integer, nullable=True)
    point = Column(Float, nullable=True)
    digits = Column(Integer, nullable=True)
    contract_size = Column(Float, nullable=True)
    swap_long = Column(Float, nullable=True)                        # raw broker value
    swap_short = Column(Float, nullable=True)
    swap_type = Column(Integer, nullable=True)                      # MT4: 0 points, 1 base ccy, 2 interest %, 3 margin ccy
    swap_3day = Column(Integer, nullable=True)                      # weekday of triple swap (0=Sun … 6=Sat)
    stop_level = Column(Float, nullable=True)                       # price units
    received_at = Column(DateTime, default=_utcnow)
