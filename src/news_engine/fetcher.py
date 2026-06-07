"""
News fetcher — collects articles from RSS feeds and REST APIs.
Sources: Reuters, Kitco, ForexFactory, Investing.com, World Gold Council, FedReserve, ECB.
All sources are polled; duplicate URLs are deduplicated before storage.
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# RSS/API sources with reliability score (0–1)
NEWS_SOURCES: List[Dict[str, Any]] = [
    {
        "name": "Reuters Gold",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "type": "rss",
        "reliability": 0.95,
        "keywords": ["gold", "XAUUSD", "XAU", "precious metals", "Federal Reserve", "inflation"],
    },
    {
        "name": "Kitco News",
        "url": "https://www.kitco.com/rss/news.xml",
        "type": "rss",
        "reliability": 0.90,
        "keywords": ["gold", "silver", "precious metals", "XAU"],
    },
    {
        "name": "ForexFactory News",
        "url": "https://www.forexfactory.com/news",
        "type": "rss",
        "reliability": 0.82,
        "keywords": ["gold", "USD", "Federal Reserve", "inflation", "CPI", "NFP"],
    },
    {
        "name": "Investing.com Gold",
        "url": "https://www.investing.com/rss/news_25.rss",
        "type": "rss",
        "reliability": 0.88,
        "keywords": ["gold", "XAU", "precious metals"],
    },
    {
        "name": "World Gold Council",
        "url": "https://www.gold.org/goldhub/research",
        "type": "scrape",
        "reliability": 0.92,
        "keywords": ["gold", "demand", "supply", "investment"],
    },
]


class NewsFetcher:
    def __init__(self, timeout: int = 15) -> None:
        self._timeout = timeout

    def _fetch_rss(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        try:
            resp = httpx.get(source["url"], timeout=self._timeout, follow_redirects=True, headers={"User-Agent": "GoldAI/1.0"})
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            # Standard RSS
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                url = item.findtext("link", "").strip() or item.findtext("guid", "").strip()
                pub_date_str = item.findtext("pubDate", "").strip()
                description = item.findtext("description", "").strip()
                if not self._is_relevant(title + " " + description, source["keywords"]):
                    continue
                articles.append({
                    "source": source["name"],
                    "title": title,
                    "url": url,
                    "content": description,
                    "published_at": self._parse_date(pub_date_str),
                    "reliability": source["reliability"],
                })
        except Exception as exc:
            log.warning("Failed to fetch RSS from %s: %s", source["url"], exc)
        return articles

    @staticmethod
    def _is_relevant(text: str, keywords: List[str]) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def fetch_all(self) -> List[Dict[str, Any]]:
        all_articles: List[Dict[str, Any]] = []
        seen_hashes: set = set()

        for source in NEWS_SOURCES:
            if source["type"] == "rss":
                articles = self._fetch_rss(source)
            else:
                articles = []  # Scraping sources require a separate implementation

            for article in articles:
                h = self._url_hash(article.get("url", article["title"]))
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    article["url_hash"] = h
                    all_articles.append(article)

        log.info("NewsFetcher: fetched %d unique articles", len(all_articles))
        return all_articles


news_fetcher = NewsFetcher()
