"""AI model configuration — reads from platform_settings table, cached in Redis.

Usage:
    from src.core.ai_models import get_model
    model = await get_model("fast")  # Returns current model ID
"""

import logging
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes
_CACHE_PREFIX = "ai_model:"

# Fallbacks if DB and Redis are both unavailable
_DEFAULTS = {
    "fast": "claude-haiku-4-5-20251001",
    "standard": "claude-sonnet-4-6",
    "advanced": "claude-opus-4-6",
}


async def get_model(tier: str = "fast") -> str:
    """Get the current model ID for a tier. Checks Redis cache, then DB, then env, then hardcoded default."""
    key = f"ai_model_{tier}"
    cache_key = f"{_CACHE_PREFIX}{tier}"

    # 1. Redis cache
    redis = await get_redis()
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached
        except Exception:
            pass

    # 2. DB lookup
    try:
        from src.core.database import get_engine
        from sqlalchemy import text
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT value FROM platform_settings WHERE key = :key"),
                {"key": key},
            )
            row = result.first()
            if row:
                model_id = row[0]
                # Cache it
                if redis:
                    try:
                        await redis.set(cache_key, model_id, ex=_CACHE_TTL)
                    except Exception:
                        pass
                return model_id
    except Exception as e:
        logger.debug(f"DB lookup for {key} failed: {e}")

    # 3. Env var fallback
    import os
    env_val = os.environ.get(key.upper())
    if env_val:
        return env_val

    # 4. Hardcoded default
    return _DEFAULTS.get(tier, _DEFAULTS["fast"])


async def set_model(tier: str, model_id: str) -> None:
    """Update a model tier. Writes to DB and invalidates cache."""
    key = f"ai_model_{tier}"

    from src.core.database import get_engine
    from sqlalchemy import text
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO platform_settings (key, value, updated_at)
                VALUES (:key, :value, now())
                ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = now()
            """),
            {"key": key, "value": model_id},
        )

    # Invalidate cache
    redis = await get_redis()
    if redis:
        try:
            await redis.delete(f"{_CACHE_PREFIX}{tier}")
        except Exception:
            pass


async def get_all_models() -> dict[str, str]:
    """Get all model tiers."""
    return {
        "fast": await get_model("fast"),
        "standard": await get_model("standard"),
        "advanced": await get_model("advanced"),
    }
