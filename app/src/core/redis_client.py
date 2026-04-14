"""Redis connection management.

Graceful degradation pattern: every Redis op should be wrapped in try/except
by the caller. On exception, call `reset_redis()` so the next `get_redis()`
attempts a fresh connection. A stale cached client (Redis died after first
ping succeeded) will otherwise keep failing forever.

Background recovery: the agent_poller runs `redis_health_check()` every 60s
to detect + reset stale clients proactively, so a Redis blip doesn't require
a user request to hit the failure first.
"""

import logging
from typing import Optional
import redis.asyncio as redis

from src.core.config import get_settings

logger = logging.getLogger(__name__)
_redis: Optional[redis.Redis] = None

# Short timeouts so a dead Redis fails fast instead of hanging request handlers.
# Production Redis is local, so these are generous enough for healthy ops.
_CONNECT_TIMEOUT_S = 2
_OP_TIMEOUT_S = 2


async def get_redis() -> Optional[redis.Redis]:
    """Return a Redis client, or None if Redis is unavailable.

    On first call, establishes the connection. Subsequent calls return the
    cached client. If callers hit an exception they should call `reset_redis()`
    so the next call here will retry the connection.
    """
    global _redis
    if _redis is None:
        try:
            settings = get_settings()
            _redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=_CONNECT_TIMEOUT_S,
                socket_timeout=_OP_TIMEOUT_S,
                retry_on_timeout=False,  # we handle retry at the caller layer
            )
            await _redis.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e} — caching disabled, falling back to no-Redis paths")
            _redis = None
    return _redis


async def reset_redis():
    """Drop the cached Redis client so the next get_redis() retries.

    Call from exception handlers when a Redis op fails. Without this, a
    Redis outage that happens after the first successful ping will leave a
    permanently-broken cached client.

    Best-effort close — never raises.
    """
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None
        logger.info("Redis client reset (will reconnect on next use)")


async def close_redis():
    """Shut down the Redis connection on app shutdown."""
    await reset_redis()


async def check_redis() -> tuple[bool, str]:
    """Health probe: True if Redis is reachable, False otherwise."""
    try:
        client = await get_redis()
        if client is None:
            return False, "Redis not connected"
        await client.ping()
        return True, "Connected"
    except Exception as e:
        # Force reset so the NEXT check (or the next caller) retries.
        await reset_redis()
        return False, str(e)


async def redis_health_check() -> bool:
    """Proactive health check: pings cached client, resets on failure.

    Run periodically (every cycle from agent_poller) so a transient Redis
    outage self-heals instead of waiting for a user-triggered op to fail.

    Returns True if Redis is healthy after the check.
    """
    if _redis is None:
        # Try to establish — get_redis returns None if it can't.
        return await get_redis() is not None
    try:
        await _redis.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis ping failed during health check: {e} — resetting client")
        await reset_redis()
        # Try a fresh connection right away for fast recovery.
        return await get_redis() is not None
