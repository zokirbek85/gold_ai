from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base


class EconomicEvent(Base):
    __tablename__ = "economic_calendar"

    id = Column(Integer, primary_key=True, index=True)
    event = Column(String(200), nullable=False)
    currency = Column(String(10), default="USD")
    impact = Column(Integer, default=1)
    forecast = Column(String(50), nullable=True)
    previous = Column(String(50), nullable=True)
    actual = Column(String(50), nullable=True)
    event_time = Column(DateTime, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
