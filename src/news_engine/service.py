"""
News service — orchestrates fetching, analysis, and persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from src.database import models
from src.database.session import SessionLocal
from src.news_engine.analyzer import news_analyzer
from src.news_engine.fetcher import news_fetcher

log = logging.getLogger(__name__)


class NewsService:
    def run_ingest(self) -> int:
        db = SessionLocal()
        try:
            articles = news_fetcher.fetch_all()
            analyzed = news_analyzer.analyze_batch(articles)
            count = 0
            for a in analyzed:
                url_hash = a.get("url_hash", "")
                existing = db.query(models.NewsArticle).filter(models.NewsArticle.url == a.get("url", "")).first()
                if existing:
                    continue
                record = models.NewsArticle(
                    source=a.get("source", ""),
                    title=a.get("title", "")[:500],
                    url=a.get("url", "")[:1000],
                    published_at=a.get("published_at") or datetime.utcnow(),
                    content=a.get("content", "")[:5000],
                    summary=a.get("summary", "")[:1000],
                    impact_score=a.get("impact_score", 5),
                    confidence=a.get("confidence", 50.0) / 100.0,
                    duration=a.get("expected_duration", "Intraday"),
                    reliability=a.get("reliability", 0.5),
                )
                db.add(record)
                count += 1
            db.commit()
            log.info("NewsService: persisted %d new articles", count)
            return count
        except Exception:
            log.exception("NewsService ingest failed")
            db.rollback()
            return 0
        finally:
            db.close()

    def get_sentiment(self, hours: int = 24) -> dict:
        db = SessionLocal()
        try:
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            rows = db.query(models.NewsArticle).filter(models.NewsArticle.published_at >= cutoff).all()
            articles = [
                {
                    "direction": "bullish" if (r.impact_score or 5) > 5 else ("bearish" if (r.impact_score or 5) < 5 else "neutral"),
                    "impact_score": r.impact_score or 5,
                    "confidence": (r.confidence or 0.5) * 100,
                }
                for r in rows
            ]
            return news_analyzer.aggregate_sentiment(articles)
        finally:
            db.close()


news_service = NewsService()
