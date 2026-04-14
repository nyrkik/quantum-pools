"""Real-time event bus using Redis Pub/Sub + Streams.

Any service publishes events after mutations. The WebSocket gateway subscribes
to Redis channels and fans events out to connected clients.

Redis Streams provide a short replay buffer so clients that reconnect can
catch up on missed events (XADD/XREAD with TTL-based trimming).

Graceful degradation: if Redis is unavailable, publish() is a no-op.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional

import redis.asyncio as aioredis

from src.core.redis_client import get_redis, reset_redis

logger = logging.getLogger(__name__)

# Stream retention: trim events older than this (approximate, via MAXLEN)
STREAM_MAX_LEN = 1000  # ~5 min of high-traffic events
STREAM_KEY_PREFIX = "events:stream:"
CHANNEL_PREFIX = "events:channel:"


class EventType(str, Enum):
    """All event types the system can emit."""

    # Email / threads
    THREAD_NEW = "thread.new"
    THREAD_UPDATED = "thread.updated"
    THREAD_READ = "thread.read"

    # Messages (agent messages within threads)
    THREAD_MESSAGE_NEW = "thread.message.new"

    # Internal messages (staff-to-staff)
    MESSAGE_NEW = "message.new"
    MESSAGE_READ = "message.read"

    # Notifications
    NOTIFICATION_NEW = "notification.new"

    # Visits
    VISIT_STARTED = "visit.started"
    VISIT_COMPLETED = "visit.completed"

    # Cases
    CASE_UPDATED = "case.updated"

    # Generic data refresh (fallback for bulk operations)
    DATA_CHANGED = "data.changed"


@dataclass
class Event:
    """An event to be published."""

    type: EventType
    org_id: str
    data: dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None  # target user (for user-specific events)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.event_id,
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


async def publish(
    event_type: EventType,
    org_id: str,
    data: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> Optional[str]:
    """Publish an event to Redis (Pub/Sub channel + Stream for replay).

    Returns the event ID on success, None if Redis is unavailable.
    """
    r = await get_redis()
    if not r:
        return None

    event = Event(type=event_type, org_id=org_id, data=data or {}, user_id=user_id)

    try:
        channel = f"{CHANNEL_PREFIX}{org_id}"
        stream = f"{STREAM_KEY_PREFIX}{org_id}"

        pipe = r.pipeline()

        # Pub/Sub for instant delivery to connected WebSocket clients
        pipe.publish(channel, event.to_json())

        # Stream for replay buffer (reconnecting clients)
        pipe.xadd(
            stream,
            {"event": event.to_json()},
            maxlen=STREAM_MAX_LEN,
            approximate=True,
        )

        await pipe.execute()
        logger.debug("Event published: %s org=%s", event_type.value, org_id[:8])
        return event.event_id

    except Exception:
        logger.warning("Failed to publish event %s — resetting Redis client", event_type.value, exc_info=True)
        # Reset so the next call retries the connection. Without this, a
        # mid-runtime Redis death leaves a stale cached client forever.
        await reset_redis()
        return None


async def get_missed_events(
    org_id: str,
    last_event_id: str | None = None,
    since_timestamp: float | None = None,
) -> list[dict]:
    """Replay events from the Redis Stream that a client missed.

    Args:
        org_id: Organization channel to read from.
        last_event_id: Resume after this stream entry ID (e.g. "1712345678901-0").
        since_timestamp: Fallback — get events after this Unix timestamp.

    Returns:
        List of event dicts, ordered oldest-first.
    """
    r = await get_redis()
    if not r:
        return []

    stream = f"{STREAM_KEY_PREFIX}{org_id}"

    try:
        # Determine start position
        if last_event_id:
            start = last_event_id
        elif since_timestamp:
            # Redis stream IDs are millisecond timestamps
            start = f"{int(since_timestamp * 1000)}-0"
        else:
            # Default: last 60 seconds
            start = f"{int((time.time() - 60) * 1000)}-0"

        entries = await r.xrange(stream, min=start, count=200)

        events = []
        for entry_id, fields in entries:
            # Skip the exact last_event_id (client already has it)
            if last_event_id and entry_id == last_event_id:
                continue
            raw = fields.get("event", "{}")
            evt = json.loads(raw)
            evt["stream_id"] = entry_id  # Client uses this for next reconnect
            events.append(evt)

        return events

    except Exception:
        logger.warning("Failed to read event stream for org %s — resetting Redis client", org_id[:8], exc_info=True)
        await reset_redis()
        return []


async def subscribe(org_id: str) -> AsyncIterator[tuple[str, dict]]:
    """Subscribe to real-time events for an org via Redis Pub/Sub.

    Yields (channel_name, event_dict) tuples. Used by the WebSocket gateway.
    """
    r = await get_redis()
    if not r:
        return

    pubsub = r.pubsub()
    channel = f"{CHANNEL_PREFIX}{org_id}"

    try:
        await pubsub.subscribe(channel)
        logger.debug("Subscribed to %s", channel)

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    yield channel, data
                except json.JSONDecodeError:
                    continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
