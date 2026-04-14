# Real-Time Events System

## Overview

QuantumPools uses a WebSocket-based real-time event system to push server-side mutations to connected clients instantly. This replaced 30-second polling intervals across the inbox, messages, notifications, visits, and cases UI.

**How it works:** Backend services call `publish()` after mutations. Redis Pub/Sub delivers events instantly to the WebSocket gateway, which fans them out to authenticated clients. Redis Streams provide a replay buffer so reconnecting clients catch up on missed events.

**Graceful degradation + auto-recovery:** If Redis is unavailable, `publish()` is a silent no-op (returns None). On any Redis exception the cached client is reset (`reset_redis()`), so the next op retries the connection — without this, a Redis blip after first successful ping would leave the cached client permanently broken until backend restart. Connection has 2s socket timeouts so failures are fast, not hanging. `agent_poller` runs a Redis health probe every 60s for proactive recovery; ntfy alert fires after 3 consecutive failed probes. Frontend falls back to existing data-fetching patterns (SWR/manual refetch) when WS is disconnected, polling every 60s.

## Architecture

```
 Backend Service            Redis                 WS Gateway              Browser
 +--------------+     +----------------+     +------------------+     +-------------+
 | CustomerSvc  |     |                |     |                  |     |             |
 | VisitSvc     |---->| Pub/Sub Channel|---->| _redis_listener  |---->| WSManager   |
 | EmailSvc     |     | (instant)      |     | (per connection) |     | (singleton) |
 | CaseSvc      |     |                |     |                  |     |             |
 +--------------+     | Stream Buffer  |     | _heartbeat (30s) |     | useWSEvent  |
       |              | (replay, ~1000 |     | _client_receiver |     | useWSRefetch|
       |              |  entries)       |     |                  |     | useWSStatus |
       v              +----------------+     +------------------+     +-------------+
  publish(event_type,        ^                       |
          org_id,            |                       |
          data)         XADD + PUBLISH          On reconnect:
                        (pipelined)             XRANGE replay
```

Key points:
- One Redis Pub/Sub channel per org: `events:channel:{org_id}`
- One Redis Stream per org: `events:stream:{org_id}` (capped at ~1000 entries)
- Both written in a single pipelined call for consistency
- WebSocket gateway authenticates via JWT cookie (or `?token=` query param fallback)
- User-targeted events (e.g. `user_id` set) are filtered server-side — only delivered to that user

## Backend Components

### Event Bus (`src/core/events.py`)

| Export | Purpose |
|--------|---------|
| `EventType` enum | All event type strings |
| `Event` dataclass | Event structure: type, org_id, data, user_id, event_id, timestamp |
| `publish()` | Publish to Redis Pub/Sub + Stream. Returns event_id or None. |
| `get_missed_events()` | Read Stream entries after a given stream ID or timestamp. |
| `subscribe()` | AsyncIterator for Pub/Sub messages (used internally by WS gateway). |

Constants: `STREAM_MAX_LEN = 1000`, `STREAM_KEY_PREFIX = "events:stream:"`, `CHANNEL_PREFIX = "events:channel:"`

### WebSocket Gateway (`src/api/v1/ws.py`)

Endpoint: `ws://host/api/v1/ws` (or `wss://` in production)

Three concurrent async tasks per connection:

| Task | Purpose |
|------|---------|
| `_redis_listener` | Subscribes to org's Pub/Sub channel, forwards events to client. Filters user-targeted events. |
| `_heartbeat` | Sends `{"type": "ping"}` every 30 seconds to keep connection alive through proxies. |
| `_client_receiver` | Reads client messages (pong responses). Detects disconnect and sets stop_event. |

### Connection Registry

In-memory dict: `org_id -> set of (user_id, WebSocket)`. Tracks active connections per process. Used for logging/debugging, not for message routing (Redis handles fan-out).

## Event Types

| EventType | Value | Description |
|-----------|-------|-------------|
| `THREAD_NEW` | `thread.new` | New email thread created (inbound email from customer) |
| `THREAD_UPDATED` | `thread.updated` | Thread status, assignment, or metadata changed |
| `THREAD_READ` | `thread.read` | Thread marked as read |
| `THREAD_MESSAGE_NEW` | `thread.message.new` | New message added to an email thread |
| `MESSAGE_NEW` | `message.new` | New internal staff-to-staff message |
| `MESSAGE_READ` | `message.read` | Internal message marked as read |
| `NOTIFICATION_NEW` | `notification.new` | New notification for a user (always has `user_id` set) |
| `VISIT_STARTED` | `visit.started` | Tech started a visit |
| `VISIT_COMPLETED` | `visit.completed` | Visit completed |
| `CASE_UPDATED` | `case.updated` | Service case status or details changed |
| `DATA_CHANGED` | `data.changed` | Generic fallback for bulk operations that don't fit a specific type |

## Publishing Events

Call `publish()` from any service after a successful mutation. Import and call:

```python
from src.core.events import publish, EventType

# In a service method, after the DB commit:
await publish(
    EventType.THREAD_MESSAGE_NEW,
    org_id=str(thread.organization_id),
    data={"thread_id": str(thread.id), "message_id": str(message.id)},
)

# User-targeted event (only delivered to one user):
await publish(
    EventType.NOTIFICATION_NEW,
    org_id=str(org_id),
    data={"notification_id": str(notif.id), "title": notif.title},
    user_id=str(target_user_id),
)
```

Rules:
- Always publish **after** the DB transaction commits (not inside a transaction that might roll back).
- Keep `data` small — IDs and minimal metadata. Clients refetch full objects via API.
- `publish()` never raises. If Redis is down, it returns `None` silently.
- `user_id` is optional. When set, the WS gateway only forwards to that specific user. When omitted, all org members receive the event.

## Frontend Hooks

All hooks require `<WebSocketProvider>` in the component tree (already in the app layout).

### `useWSEvent(eventTypes, handler, deps?)`

Subscribe to specific event types and run a callback:

```tsx
import { useWSEvent } from "@/lib/ws";

// Single event type
useWSEvent("thread.new", (event) => {
  toast.info(`New email from ${event.data?.from}`);
});

// Multiple event types
useWSEvent(["thread.new", "thread.updated"], (event) => {
  setThreads((prev) => /* merge update */);
});
```

### `useWSRefetch(eventTypes, refetchFn, debounceMs?)`

Trigger a data refetch on events. Debounces rapid-fire events (default 500ms):

```tsx
import { useWSRefetch } from "@/lib/ws";

const { data, mutate } = useSWR("/api/v1/threads", fetcher);

// Refetch thread list when any thread event fires
useWSRefetch(["thread.new", "thread.updated", "thread.read"], () => mutate());
```

### `useWSStatus()`

Get connection status for UI indicators:

```tsx
import { useWSStatus } from "@/lib/ws";

const { isConnected } = useWSStatus();
// Show a "reconnecting..." badge when isConnected is false
```

## Connection Flow

1. **Connect:** Client opens `ws://backend:7061/api/v1/ws`. If reconnecting, appends `?last_stream_id=...`.
2. **Authenticate:** Server reads `access_token` cookie (or `?token=` query param). Decodes JWT, looks up org membership. Rejects with close code `4001` if invalid.
3. **Replay:** If `last_stream_id` provided, server reads Redis Stream via `XRANGE` and sends `{"type": "replay", "events": [...]}`. Client emits each replayed event to its listeners individually.
4. **Connected:** Server sends `{"type": "connected", "user_id": "...", "org_id": "...", "timestamp": ...}`.
5. **Steady state:** Server forwards Redis Pub/Sub events as JSON. Sends `{"type": "ping"}` every 30s. Client sends `{"type": "pong"}` every 25s.
6. **Disconnect:** Client receiver detects `WebSocketDisconnect`, sets stop_event, all tasks wind down, connection is unregistered.
7. **Reconnect:** Client uses exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s. Up to 20 attempts. On reconnect, sends `last_stream_id` for replay. Does **not** reconnect on `4001` (auth failure).

## Scaling Considerations

**Current (single server):**
- Connection registry is in-memory per-process. Works fine since we run one uvicorn process.
- Redis Pub/Sub inherently broadcasts to all subscribers, so even with multiple WS gateway processes on the same server, it works.

**Multi-server (future):**
- The event bus already works across servers — Redis Pub/Sub is the transport, not in-memory.
- Connection registry would need a Redis SET per org to track which servers hold which users (for admin tooling/presence features).
- Stream replay works unchanged — all servers read from the same Redis Stream.
- Consider sticky sessions or a dedicated WS gateway service if connection churn becomes an issue.
- No code changes needed for basic multi-server fan-out. Only the connection registry and any presence features would need Redis backing.

## Adding a New Event Type

1. **Add the enum value** in `src/core/events.py`:
   ```python
   class EventType(str, Enum):
       # ...existing...
       INVOICE_CREATED = "invoice.created"
   ```

2. **Add the TypeScript type** in `frontend/src/lib/ws.tsx`:
   ```typescript
   export type WSEventType =
     | // ...existing...
     | "invoice.created";
   ```

3. **Publish from your service** after the DB commit:
   ```python
   from src.core.events import publish, EventType

   async def create_invoice(self, ...):
       # ... create invoice, commit ...
       await publish(
           EventType.INVOICE_CREATED,
           org_id=str(invoice.organization_id),
           data={"invoice_id": str(invoice.id), "customer_id": str(invoice.customer_id)},
       )
   ```

4. **Subscribe in the frontend** wherever you need to react:
   ```tsx
   useWSRefetch("invoice.created", () => mutate());
   // or
   useWSEvent("invoice.created", (event) => {
     toast.success("New invoice created");
   });
   ```

That's it. No gateway changes, no routing config, no middleware. The Pub/Sub channel is per-org, so all events flow through the same pipe and get filtered client-side by type.
