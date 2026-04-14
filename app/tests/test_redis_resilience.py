"""Redis graceful degradation — guards against the cached-stale-client
failure mode.

Pattern: if Redis dies after the first successful ping, the cached client
is broken and never retries. These tests verify that exception handlers
call reset_redis() so the next get_redis() reconnects, and that
publish/subscribe code paths don't crash when Redis is down.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_get_redis_returns_none_when_unavailable(monkeypatch):
    """If Redis can't be reached, get_redis() must return None (not raise)
    so callers can fall back to the no-Redis path."""
    import src.core.redis_client as rc

    # Force a fresh attempt against an unreachable URL.
    await rc.reset_redis()
    monkeypatch.setattr(
        rc.get_settings(), "redis_url", "redis://localhost:65535", raising=False,
    )

    client = await rc.get_redis()
    assert client is None


@pytest.mark.asyncio
async def test_publish_returns_none_when_redis_unavailable(monkeypatch):
    """publish() must be a no-op (return None) when Redis is down — never
    crash the calling request handler."""
    import src.core.redis_client as rc
    from src.core.events import publish, EventType

    await rc.reset_redis()
    monkeypatch.setattr(
        rc.get_settings(), "redis_url", "redis://localhost:65535", raising=False,
    )

    result = await publish(EventType.THREAD_NEW, "test-org", {"foo": "bar"})
    assert result is None  # publish swallowed the failure


@pytest.mark.asyncio
async def test_publish_resets_redis_on_failure(monkeypatch):
    """When a publish hits an exception, the cached Redis client must be
    reset so the next get_redis() retries the connection. Without this,
    a transient Redis blip leaves the cache permanently broken."""
    import src.core.redis_client as rc
    from src.core.events import publish, EventType

    # Inject a fake "broken" Redis client that raises on every op.
    class BrokenRedis:
        def pipeline(self):
            raise ConnectionError("simulated Redis death")

        async def close(self):
            pass

    rc._redis = BrokenRedis()

    # publish should swallow the exception AND clear the cache.
    result = await publish(EventType.THREAD_NEW, "test-org", {})
    assert result is None
    assert rc._redis is None, (
        "publish() must call reset_redis() on failure so the next call "
        "retries the connection. Otherwise a Redis blip leaves the cache "
        "permanently broken."
    )


@pytest.mark.asyncio
async def test_get_missed_events_returns_empty_when_unavailable(monkeypatch):
    """get_missed_events() must return [] when Redis is unavailable."""
    import src.core.redis_client as rc
    from src.core.events import get_missed_events

    await rc.reset_redis()
    monkeypatch.setattr(
        rc.get_settings(), "redis_url", "redis://localhost:65535", raising=False,
    )

    events = await get_missed_events("test-org")
    assert events == []


@pytest.mark.asyncio
async def test_check_redis_resets_on_failure():
    """check_redis() must reset the cached client when the ping fails so
    subsequent get_redis() calls don't reuse the broken connection."""
    import src.core.redis_client as rc

    class BrokenRedis:
        async def ping(self):
            raise ConnectionError("simulated")

        async def close(self):
            pass

    rc._redis = BrokenRedis()

    ok, msg = await rc.check_redis()
    assert ok is False
    assert rc._redis is None
