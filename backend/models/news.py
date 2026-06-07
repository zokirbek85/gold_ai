from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base


class NewsArticle(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    source = Column(String(200), nullable=False)
    url = Column(String(1000), nullable=True)
    sentiment = Column(String(20), default="neutral")
    impact_score = Column(Float, default=5.0)
    published_at = Column(DateTime, index=True, nullable=False)
    duration = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
