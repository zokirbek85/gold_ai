from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    win_rate = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    avg_rr = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
