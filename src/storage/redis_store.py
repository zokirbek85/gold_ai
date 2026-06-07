import json
import logging
from typing import Any, Optional

import redis
import redis.asyncio as aioredis

from src.config.settings import settings

log = logging.getLogger(__name__)

redis_sync: redis.Redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
redis_async: aioredis.Redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def cache_set(key: str, value: Any, expire_seconds: Optional[int] = None) -> None:
    try:
        payload = json.dumps(value, default=str)
        if expire_seconds:
            redis_sync.set(key, payload, ex=expire_seconds)
        else:
            redis_sync.set(key, payload)
    except Exception:
        log.exception("Failed to cache Redis key=%s", key)


def cache_get(key: str) -> Any:
    try:
        raw = redis_sync.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        log.exception("Failed to read Redis key=%s", key)
        return None


def publish(channel: str, payload: Any) -> None:
    try:
        redis_sync.publish(channel, json.dumps(payload, default=str))
    except Exception:
        log.exception("Failed to publish Redis channel=%s", channel)


async def publish_async(channel: str, payload: Any) -> None:
    try:
        await redis_async.publish(channel, json.dumps(payload, default=str))
    except Exception:
        log.exception("Failed to publish async Redis channel=%s", channel)
