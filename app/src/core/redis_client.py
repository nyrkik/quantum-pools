"""Redis connection management."""

import logging
from typing import Optional
import redis.asyncio as redis

from src.core.config import get_settings

logger = logging.getLogger(__name__)
_redis: Optional[redis.Redis] = None


async def get_redis() -> Optional[redis.Redis]:
    global _redis
    if _redis is None:
        try:
            settings = get_settings()
            _redis = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
            await _redis.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e} — caching disabled")
            _redis = None
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Redis connection closed")


async def check_redis() -> tuple[bool, str]:
    try:
        client = await get_redis()
        if client is None:
            return False, "Redis not connected"
        await client.ping()
        return True, "Connected"
    except Exception as e:
        return False, str(e)
