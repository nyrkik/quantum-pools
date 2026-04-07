"""WebSocket gateway — real-time event delivery to authenticated clients.

Architecture:
  1. Client connects to /api/v1/ws with JWT cookie
  2. Server authenticates, resolves org membership
  3. Server subscribes to Redis Pub/Sub channel for that org
  4. Events are fanned out to the client as JSON messages
  5. On reconnect, client sends last_stream_id to replay missed events

Connection registry is in-memory (per-process). Multi-server scaling
would add a Redis SET of connected users, but single-server is fine for now.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import get_session_maker
from src.core.events import CHANNEL_PREFIX, EventType, get_missed_events
from src.core.redis_client import get_redis
from src.core.security import decode_token, verify_token_type
from src.core.exceptions import AuthenticationError
from src.models.user import User
from src.models.organization_user import OrganizationUser

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory connection registry: org_id -> set of (user_id, websocket)
_connections: dict[str, set[tuple[str, WebSocket]]] = {}

HEARTBEAT_INTERVAL = 30  # seconds


def _register(org_id: str, user_id: str, ws: WebSocket):
    if org_id not in _connections:
        _connections[org_id] = set()
    _connections[org_id].add((user_id, ws))
    logger.info("WS connected: user=%s org=%s (total=%d)", user_id[:8], org_id[:8], len(_connections[org_id]))


def _unregister(org_id: str, user_id: str, ws: WebSocket):
    if org_id in _connections:
        _connections[org_id].discard((user_id, ws))
        if not _connections[org_id]:
            del _connections[org_id]
    logger.info("WS disconnected: user=%s org=%s", user_id[:8], org_id[:8])


async def _authenticate_ws(ws: WebSocket) -> Optional[tuple[str, str]]:
    """Authenticate WebSocket from cookie. Returns (user_id, org_id) or None."""
    token = ws.cookies.get("access_token")
    if not token:
        # Also check query param (fallback for clients that can't send cookies on WS)
        token = ws.query_params.get("token")
    if not token:
        return None

    try:
        payload = decode_token(token)
        verify_token_type(payload, "access")
        user_id = payload.get("sub")
        if not user_id:
            return None
    except (AuthenticationError, Exception):
        return None

    # Look up org membership
    async with get_session_maker()() as db:
        result = await db.execute(
            select(OrganizationUser)
            .options(joinedload(OrganizationUser.organization))
            .where(
                OrganizationUser.user_id == user_id,
                OrganizationUser.is_active == True,
            )
            .limit(1)
        )
        org_user = result.scalar_one_or_none()
        if not org_user:
            return None

        return user_id, str(org_user.organization_id)


async def _redis_listener(ws: WebSocket, org_id: str, user_id: str, stop_event: asyncio.Event):
    """Subscribe to Redis Pub/Sub and forward events to the WebSocket client."""
    r = await get_redis()
    if not r:
        logger.warning("Redis unavailable — WS will rely on heartbeat only")
        await stop_event.wait()
        return

    pubsub = r.pubsub()
    channel = f"{CHANNEL_PREFIX}{org_id}"

    try:
        await pubsub.subscribe(channel)

        while not stop_event.is_set():
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                continue

            if message and message["type"] == "message":
                try:
                    event = json.loads(message["data"])

                    # Filter: if event has a target user_id, only send to that user
                    target_user = event.get("user_id")
                    if target_user and target_user != user_id:
                        continue

                    await ws.send_json(event)
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug("Failed to forward event: %s", e)
                    continue

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("Redis listener error: %s", e)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass


async def _heartbeat(ws: WebSocket, stop_event: asyncio.Event):
    """Send periodic pings to keep the connection alive through proxies."""
    while not stop_event.is_set():
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if not stop_event.is_set():
                await ws.send_json({"type": "ping", "timestamp": time.time()})
        except Exception:
            break


async def _client_receiver(ws: WebSocket, stop_event: asyncio.Event):
    """Receive messages from the client (pong, etc). Detects disconnection."""
    try:
        while not stop_event.is_set():
            data = await ws.receive_json()
            # Client can send pong or other messages — we just consume them
            if data.get("type") == "pong":
                continue
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        stop_event.set()


@router.websocket("/api/v1/ws")
async def websocket_endpoint(ws: WebSocket):
    """Main WebSocket endpoint for real-time event delivery."""
    auth = await _authenticate_ws(ws)
    if not auth:
        await ws.close(code=4001, reason="Unauthorized")
        return

    user_id, org_id = auth
    await ws.accept()
    _register(org_id, user_id, ws)

    # Replay missed events if client provides last_stream_id
    last_stream_id = ws.query_params.get("last_stream_id")
    if last_stream_id:
        try:
            missed = await get_missed_events(org_id, last_event_id=last_stream_id)
            if missed:
                await ws.send_json({"type": "replay", "events": missed})
        except Exception as e:
            logger.warning("Failed to replay events: %s", e)

    # Send connected confirmation
    await ws.send_json({
        "type": "connected",
        "user_id": user_id,
        "org_id": org_id,
        "timestamp": time.time(),
    })

    stop_event = asyncio.Event()

    # Run Redis listener, heartbeat, and client receiver concurrently
    tasks = [
        asyncio.create_task(_redis_listener(ws, org_id, user_id, stop_event)),
        asyncio.create_task(_heartbeat(ws, stop_event)),
        asyncio.create_task(_client_receiver(ws, stop_event)),
    ]

    try:
        # Wait for any task to finish (usually client disconnect)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop_event.set()
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        stop_event.set()
    finally:
        _unregister(org_id, user_id, ws)
        try:
            await ws.close()
        except Exception:
            pass
