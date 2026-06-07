from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.database import models

log = logging.getLogger(__name__)


class IndicatorRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert(
        self,
        symbol: str,
        name: str,
        timeframe: str,
        timestamp: datetime,
        value: float,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        existing = (
            self._db.query(models.Indicator)
            .filter(
                models.Indicator.symbol == symbol,
                models.Indicator.name == name,
                models.Indicator.timeframe == timeframe,
                models.Indicator.timestamp == timestamp,
            )
            .first()
        )
        if existing:
            existing.value = value
            existing.params = params
        else:
            self._db.add(
                models.Indicator(
                    symbol=symbol,
                    name=name,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    value=value,
                    params=params,
                )
            )

    def bulk_upsert(
        self,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        indicators: Dict[str, Any],
    ) -> None:
        for name, value in indicators.items():
            if value is None:
                continue
            self.upsert(
                symbol=symbol,
                name=name,
                timeframe=timeframe,
                timestamp=timestamp,
                value=float(value),
                params={"auto": True},
            )
        self._db.commit()

    def get_latest(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 50,
        name: Optional[str] = None,
    ) -> List[models.Indicator]:
        q = self._db.query(models.Indicator).filter(
            models.Indicator.symbol == symbol,
            models.Indicator.timeframe == timeframe,
        )
        if name:
            q = q.filter(models.Indicator.name == name)
        return q.order_by(models.Indicator.timestamp.desc()).limit(limit).all()

    def get_snapshot(self, symbol: str, timeframe: str) -> Dict[str, float]:
        """Return latest value for every indicator name for a given symbol/timeframe."""
        rows = (
            self._db.query(models.Indicator)
            .filter(
                models.Indicator.symbol == symbol,
                models.Indicator.timeframe == timeframe,
            )
            .order_by(models.Indicator.timestamp.desc())
            .all()
        )
        seen: Dict[str, float] = {}
        for row in rows:
            if row.name not in seen:
                seen[row.name] = row.value
        return seen
