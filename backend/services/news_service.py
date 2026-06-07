"""
News service — fetches real gold/forex/macro news from free RSS feeds.
Sentiment is detected from headline keywords.
Returns empty list if all RSS sources fail — no fake/generated articles.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from models.news import NewsArticle

log = logging.getLogger(__name__)

# Free public RSS feeds covering gold, forex, macro
_RSS_FEEDS = [
    "https://www.fxstreet.com/rss/news?c=metals",           # gold/metals news
    "https://www.fxstreet.com/rss/news?c=forex",            # forex news
    "https://feeds.reuters.com/reuters/businessNews",        # Reuters business
    "https://feeds.marketwatch.com/marketwatch/topstories/", # MarketWatch
    "https://finance.yahoo.com/rss/topfinstories",           # Yahoo Finance
]

# Keywords to filter for gold/forex relevance
_RELEVANT_KEYWORDS = {
    "gold", "xauusd", "xau", "bullion", "precious", "commodity",
    "fed", "fomc", "inflation", "cpi", "rate hike", "rate cut",
    "dollar", "dxy", "yields", "treasury", "silver", "metal",
    "forex", "currency", "crude", "oil", "gdp", "nfp", "payroll",
}

_BULLISH_WORDS = {
    "surge", "surges", "surging", "rise", "rises", "rising", "gain", "gains",
    "rally", "rallied", "rallying", "bullish", "upward", "record", "higher",
    "soar", "soaring", "advance", "buy", "support", "boost", "strong", "strength",
    "positive", "recover", "recovery", "outperform", "breakout", "peak",
}

_BEARISH_WORDS = {
    "fall", "falls", "falling", "drop", "drops", "dropping", "decline",
    "declining", "bear", "bearish", "downward", "lower", "sell", "selling",
    "weak", "weakness", "pressure", "risk", "plunge", "plunging", "sink",
    "retreat", "correction", "loss", "losses", "hawkish", "tighten", "tightening",
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _is_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in _RELEVANT_KEYWORDS)


def _detect_sentiment(text: str) -> str:
    words = set(re.findall(r"\b\w+\b", text.lower()))
    bull_score = len(words & _BULLISH_WORDS)
    bear_score = len(words & _BEARISH_WORDS)
    if bull_score > bear_score:
        return "bullish"
    if bear_score > bull_score:
        return "bearish"
    return "neutral"


def _impact_score(text: str) -> float:
    words = re.findall(r"\b\w+\b", text.lower())
    hits = sum(1 for w in words if w in _BULLISH_WORDS | _BEARISH_WORDS)
    return round(min(9.9, 4.0 + hits * 0.3), 1)


def _parse_pubdate(raw: str) -> datetime:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _fetch_rss(url: str) -> List[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 GoldAI/1.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
    except Exception as exc:
        log.debug("RSS fetch error (%s): %s", url, exc)
        return []

    channel = root.find("channel")
    items_el = (channel or root).findall("item") or root.findall(".//item")
    source = url.split("/")[2].replace("www.", "").replace("feeds.", "")

    results = []
    for item in items_el[:20]:
        title = _strip_html(item.findtext("title", ""))
        desc = _strip_html(item.findtext("description", ""))
        link = item.findtext("link", "") or item.findtext("guid", "") or ""
        pub = item.findtext("pubDate", "")

        if not title or not _is_relevant(title, desc):
            continue

        text = f"{title} {desc}"
        results.append({
            "title": title[:300],
            "source": source,
            "url": link[:500] if link else f"https://{source}",
            "sentiment": _detect_sentiment(text),
            "impact_score": _impact_score(text),
            "published_at": _parse_pubdate(pub),
            "duration": "intraday",
        })
    return results


def _fetch_all_news(max_per_feed: int = 15) -> List[Dict[str, Any]]:
    """Fetch from all feeds, deduplicate by title prefix, sort newest-first."""
    all_items: List[Dict[str, Any]] = []
    seen: set = set()
    for feed_url in _RSS_FEEDS:
        for item in _fetch_rss(feed_url)[:max_per_feed]:
            key = item["title"][:60].lower()
            if key not in seen:
                seen.add(key)
                all_items.append(item)
    return sorted(all_items, key=lambda x: x["published_at"], reverse=True)


def get_or_generate_news(db: Session, smc_score: float = 50.0, limit: int = 50) -> List[Dict[str, Any]]:
    """Return news from DB (last 24h cache) or fetch fresh from RSS."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    rows = (
        db.query(NewsArticle)
        .filter(NewsArticle.published_at >= cutoff)
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
        .all()
    )
    if len(rows) >= 5:
        return [
            {
                "id": r.id, "title": r.title, "source": r.source, "url": r.url,
                "sentiment": r.sentiment, "impact_score": r.impact_score,
                "published_at": r.published_at, "duration": r.duration,
            }
            for r in rows
        ]

    items = _fetch_all_news()
    log.info("Fetched %d news articles from RSS", len(items))
    db_items = []
    for item in items[:50]:
        n = NewsArticle(
            title=item["title"], source=item["source"], url=item["url"],
            sentiment=item["sentiment"], impact_score=item["impact_score"],
            published_at=item["published_at"], duration=item["duration"],
        )
        db.add(n)
        db.flush()
        db_items.append({"id": n.id, **item})
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Failed to save news to DB")
    return db_items[:limit]


def get_sentiment_summary(db: Session, hours: int = 24) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = db.query(NewsArticle).filter(NewsArticle.published_at >= cutoff).all()
    if not rows:
        return {"direction": "neutral", "score": 50.0,
                "bullish_count": 0, "bearish_count": 0, "neutral_count": 0}

    total = len(rows)
    bullish = sum(1 for r in rows if r.sentiment == "bullish")
    bearish = sum(1 for r in rows if r.sentiment == "bearish")
    neutral = total - bullish - bearish
    score = round(50.0 + (bullish - bearish) / total * 40, 1)

    return {
        "direction": (
            "bullish" if bullish / total > 0.55 else
            "bearish" if bearish / total > 0.55 else
            "neutral"
        ),
        "score": score,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
    }


def refresh_news(db: Session) -> None:
    try:
        items = _fetch_all_news()
        for item in items[:30]:
            db.add(NewsArticle(
                title=item["title"], source=item["source"], url=item["url"],
                sentiment=item["sentiment"], impact_score=item["impact_score"],
                published_at=item["published_at"], duration=item["duration"],
            ))
        db.commit()
        log.info("News refreshed: %d articles from RSS", len(items))
    except Exception:
        log.exception("Failed to refresh news")
        db.rollback()
