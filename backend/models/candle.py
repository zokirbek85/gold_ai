from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, Index
from database import Base


class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_candle_symbol_tf_ts"),
        # Composite index covers all signal/forecast queries that filter on all three columns
        Index("ix_candle_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
        # Covering index for recent-candles query (DESC timestamp)
        Index("ix_candle_symbol_tf_ts_desc", "symbol", "timeframe", "timestamp"),
    )
