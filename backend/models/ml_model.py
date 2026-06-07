from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base


class MLModel(Base):
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    accuracy = Column(Float, nullable=True)
    samples = Column(Integer, nullable=True)
    trained_at = Column(DateTime, default=datetime.utcnow)
    model_path = Column(String(500), nullable=True)
