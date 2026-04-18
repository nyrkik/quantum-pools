# Phase 1 — Event Instrumentation Foundation (implementation spec)

**Parent plan**: `docs/ai-platform-plan.md` — Phase 1
**Taxonomy reference**: `docs/event-taxonomy.md` — authoritative catalog of event types
**Status**: Refinement spec (written before any code)
**Remove this doc** when Phase 1 is shipped — the master plan tracks status; the taxonomy doc is permanent reference.

---

## 1. Purpose

This phase builds the `platform_events` instrumentation layer end-to-end: table + partitioning, backend emit service + middleware, frontend batching client, backfill migration, retention purge, purge-on-request endpoint, and subsystem instrumentation.

**Why now / why blocking**: nothing in Phases 2-7 works without this. Workflow-observer has nothing to observe. Sonar has nothing to analyze. Rule 3 (product learns the org) is impossible. Even basic debugging ("how did this customer get into this state?") degrades. See `feedback_data_capture_is_king` — uncaptured data is unrecoverable.

## 2. Environment facts (verified 2026-04-18)

- PostgreSQL 15.17 — supports declarative partitioning natively
- Installed extensions: `pg_trgm`, `plpgsql` only. No `pg_cron`, no `pg_partman`. Partition management therefore happens from the application via APScheduler.
- APScheduler is already wired in `app.py`; we add jobs there.
- Existing orgs table doesn't have `event_retention_days` yet.

## 3. What this phase ships

1. **Database**
   - `platform_events` table (partitioned by month, global — single table, all orgs)
   - Initial partitions: current month + next 3 months
   - `organizations.event_retention_days` column
   - Indexes per §5 of the taxonomy
   - `data_deletion_requests` audit table (for CCPA purge-on-request logging)

2. **Backend service layer**
   - `src/services/events/platform_event_service.py` — `PlatformEventService.emit(...)`
   - `src/middleware/request_id.py` — generates/propagates `request_id`
   - `src/services/events/job_run_context.py` — context manager for background-job `job_run_id`
   - `src/services/events/partition_manager.py` — APScheduler job: creates next-month partition
   - `src/services/events/retention_purge.py` — APScheduler job: daily row delete per org retention
   - `src/api/v1/admin_events.py` — purge-on-request endpoint + admin read-only query endpoint

3. **Frontend client**
   - `frontend/src/lib/events.ts` — batching emit client
   - `frontend/src/lib/session-id.ts` — tab-scoped session_id
   - Hook wiring: `useEventEmit()` for components, route-change listener for `page.viewed`

4. **Backfill**
   - `app/scripts/backfill_platform_events.py` — one-time migration deriving events from existing tables

5. **Instrumentation**
   - Emit calls added to every service listed in taxonomy §10
   - Frontend emit calls added to every instrumented UI surface per taxonomy §8

6. **Testing**
   - `tests/fixtures/event_recorder.py` — pytest fixture
   - Unit tests for `PlatformEventService`
   - Integration tests for 5 subsystems (inbox, job lifecycle, estimate funnel, chemistry, auth)
   - CI lint test asserting every mutation method emits

7. **CI / ops**
   - Completeness audit script (`app/scripts/audit_instrumentation.py`) + CI integration
   - ntfy alert on emit failure spike

---

## 4. Database

### 4.1 Migration: create `platform_events` and infrastructure

```sql
-- 4.1.a: retention config on orgs
ALTER TABLE organizations
  ADD COLUMN event_retention_days INTEGER NOT NULL DEFAULT 1095;  -- 3 years

-- Existing orgs: set dogfood retention (10 years) for Sapphire; default 3y for others
UPDATE organizations SET event_retention_days = 3650 WHERE slug = 'sapphire-pool-service';

-- 4.1.b: main partitioned table
CREATE TABLE platform_events (
    id VARCHAR(36) NOT NULL,
    organization_id VARCHAR(36),
    actor_user_id VARCHAR(36),
    acting_as_user_id VARCHAR(36),
    view_as_role VARCHAR(30),
    actor_type VARCHAR(10) NOT NULL,        -- user | system | agent
    actor_agent_type VARCHAR(50),
    event_type VARCHAR(100) NOT NULL,
    level VARCHAR(20) NOT NULL,             -- user_action | system_action | agent_action | error
    entity_refs JSONB NOT NULL DEFAULT '{}',
    payload JSONB NOT NULL DEFAULT '{}',
    request_id VARCHAR(36),
    session_id VARCHAR(36),
    job_run_id VARCHAR(36),
    client_emit_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)            -- composite PK because we partition on created_at
) PARTITION BY RANGE (created_at);

-- 4.1.c: indexes (defined on the parent; propagate to partitions automatically)
CREATE INDEX idx_platform_events_org_created
    ON platform_events (organization_id, created_at DESC);
CREATE INDEX idx_platform_events_type_created
    ON platform_events (event_type, created_at DESC);
CREATE INDEX idx_platform_events_entity_refs
    ON platform_events USING GIN (entity_refs);

-- Idempotency lookup — NON-UNIQUE. Postgres requires unique indexes on
-- partitioned tables to include the partition key; a composite unique
-- on (organization_id, client_emit_id, created_at) doesn't give us the
-- semantics we want because retries get a new server-time created_at.
-- Solution: app-level check-then-insert in PlatformEventService.emit()
-- (see §5.1). Index here serves the lookup; uniqueness enforced in code.
CREATE INDEX idx_platform_events_client_emit_id
    ON platform_events (organization_id, client_emit_id)
    WHERE client_emit_id IS NOT NULL;

-- Error path — partial index keeps errors (rare) fast to query.
-- Level column omitted from key columns because WHERE clause already
-- constrains to level='error'; saves disk.
CREATE INDEX idx_platform_events_error_created
    ON platform_events (created_at DESC)
    WHERE level = 'error';

-- 4.1.d: initial partitions — current + 3 future months
-- Written as a DO block for the migration; partition_manager.py handles subsequent months.
DO $$
DECLARE
    start_date DATE := DATE_TRUNC('month', NOW())::DATE;
    partition_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..3 LOOP
        partition_date := start_date + (i || ' months')::INTERVAL;
        partition_name := 'platform_events_' || TO_CHAR(partition_date, 'YYYY_MM');
        EXECUTE FORMAT(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF platform_events
             FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + INTERVAL '1 month'
        );
    END LOOP;
END $$;

-- 4.1.e: data deletion audit log (separate from platform_events — never put purge records
-- back into the same table whose rows we're purging; that defeats the CCPA contract)
CREATE TABLE data_deletion_requests (
    id VARCHAR(36) PRIMARY KEY,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_by_user_id VARCHAR(36),       -- who requested (may be platform admin acting on behalf)
    target_user_id VARCHAR(36) NOT NULL,    -- whose data
    target_type VARCHAR(30) NOT NULL,       -- 'user' | 'customer' | 'org'
    scope JSONB NOT NULL,                   -- what was purged (tables, counts)
    completed_at TIMESTAMPTZ,
    completed_rows_affected INTEGER,
    note TEXT
);
CREATE INDEX idx_ddr_target ON data_deletion_requests (target_user_id, requested_at DESC);
```

Alembic migration file: `app/migrations/versions/<hash>_platform_events_phase1.py`.

### 4.2 Partition management (APScheduler)

- New job in `app.py` alongside existing ones:
  ```python
  scheduler.add_job(
      _ensure_next_partition,
      CronTrigger(day=25, hour=2, minute=0),   # 25th of each month, 2am
      id="platform_events_partition"
  )
  ```
- Implementation in `src/services/events/partition_manager.py`:
  - Computes next month's date range
  - `CREATE TABLE IF NOT EXISTS` the partition if missing
  - Logs result, emits `system.partition.created` event (meta)
- Runs on the 25th so there's a buffer before month-end.

### 4.3 Retention purge (APScheduler)

- New job:
  ```python
  scheduler.add_job(
      _purge_expired_events,
      CronTrigger(hour=3, minute=15),         # daily at 3:15am local
      id="platform_events_retention"
  )
  ```
- Implementation in `src/services/events/retention_purge.py`:
  - For each organization: `DELETE FROM platform_events WHERE organization_id = :id AND created_at < NOW() - (:retention_days || ' days')::INTERVAL`
  - Batched (e.g., 50,000 rows per DELETE) to avoid long transactions
  - Logs total rows purged per org
  - Emits a single `system.retention_purge.completed` meta-event per run (the purge itself is silent; the summary is the event)
- Per-partition drop (cleaner than row-level delete) is a v2 optimization — requires org-specific partitioning, which we're not doing for v1.

### 4.4 Purge-on-request endpoint

Endpoint: `POST /api/v1/admin/users/{user_id}/purge-events`. Platform-admin gated (not customer-admin — this is a CCPA data-subject request and only we can execute it).

Behavior:
1. Records a `data_deletion_requests` row (status: in-progress).
2. Executes in one transaction:
   - `UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :uid`
   - `UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :uid`
   - `UPDATE platform_events SET entity_refs = entity_refs - 'user_id' WHERE entity_refs @> jsonb_build_object('user_id', :uid)`
3. Marks `data_deletion_requests` row completed with row counts.
4. Does NOT emit a `platform_events` row for the purge — logged only to the audit table.

Response: `{request_id, rows_affected, completed_at}`.

### 4.5 Admin read-only event query endpoint

`GET /api/v1/admin/events` — platform-admin gated. Filter params: `org_id`, `event_type`, `from`, `to`, `entity_ref`, `limit`. For Sonar and for Brian's ad-hoc debugging.

---

## 5. Backend service layer

### 5.1 `PlatformEventService.emit()`

File: `app/src/services/events/platform_event_service.py`

```python
from dataclasses import dataclass
from typing import Optional, Literal
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

PAYLOAD_MAX_BYTES = 8 * 1024

@dataclass
class Actor:
    user_id: Optional[str] = None
    acting_as_user_id: Optional[str] = None
    view_as_role: Optional[str] = None
    actor_type: Literal["user", "system", "agent"] = "user"
    actor_agent_type: Optional[str] = None

class PlatformEventService:
    """Primary emission surface. All events flow through here."""

    @staticmethod
    async def emit(
        db: AsyncSession,
        event_type: str,
        level: Literal["user_action", "system_action", "agent_action", "error"],
        actor: Actor,
        organization_id: Optional[str] = None,
        entity_refs: Optional[dict] = None,
        payload: Optional[dict] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        job_run_id: Optional[str] = None,
        client_emit_id: Optional[str] = None,
    ) -> None:
        """
        Fail-soft emission. Writes inline inside the caller's transaction.
        Never raises; never blocks the caller.
        """
        try:
            # 1. Size cap + truncation
            payload_obj = payload or {}
            serialized = json.dumps(payload_obj).encode("utf-8")
            if len(serialized) > PAYLOAD_MAX_BYTES:
                # Emit an oversized marker instead of the real payload,
                # and separately log a platform_event.oversized_payload error event.
                await _emit_oversized_marker(db, event_type, len(serialized))
                payload_obj = {"__oversized__": True, "original_size_bytes": len(serialized)}

            # 2. Context propagation: if request_id/session_id/job_run_id not passed,
            # pull from contextvars (set by middleware / JobRunContext).
            request_id = request_id or _current_request_id()
            session_id = session_id or _current_session_id()
            job_run_id = job_run_id or _current_job_run_id()

            # 3. Idempotency: app-level check-then-insert. We can't use
            # ON CONFLICT because partitioned tables require unique indexes
            # to include the partition key — see §4.1.c.
            # Small race window (two concurrent emits with identical
            # client_emit_id) is acceptable per the "rare duplicates OK"
            # philosophy; same client_emit_id means same emit call, not
            # a true concurrent race in practice.
            if client_emit_id:
                existing = await db.execute(
                    text("""
                        SELECT 1 FROM platform_events
                        WHERE organization_id = :org AND client_emit_id = :cid
                        LIMIT 1
                    """),
                    {"org": organization_id, "cid": client_emit_id},
                )
                if existing.first() is not None:
                    return  # duplicate — silently skip

            # 4. Insert
            await db.execute(
                text("""
                    INSERT INTO platform_events
                    (id, organization_id, actor_user_id, acting_as_user_id, view_as_role,
                     actor_type, actor_agent_type, event_type, level, entity_refs, payload,
                     request_id, session_id, job_run_id, client_emit_id, created_at)
                    VALUES (:id, :org, :actor, :acting, :role, :atype, :aagent,
                            :etype, :level, :refs, :payload, :rid, :sid, :jid, :cid, NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "org": organization_id,
                    "actor": actor.user_id,
                    "acting": actor.acting_as_user_id,
                    "role": actor.view_as_role,
                    "atype": actor.actor_type,
                    "aagent": actor.actor_agent_type,
                    "etype": event_type,
                    "level": level,
                    "refs": json.dumps(entity_refs or {}),
                    "payload": json.dumps(payload_obj),
                    "rid": request_id,
                    "sid": session_id,
                    "jid": job_run_id,
                    "cid": client_emit_id,
                },
            )
        except Exception as e:
            # Never raise. Log and swallow.
            logger.error("platform_event.emit failed", extra={
                "event_type": event_type, "error": str(e)[:200]
            })
```

**Transactional semantics**: `emit()` writes in the caller's session. If the caller's transaction rolls back, the event rolls back too. This is correct — don't record actions that didn't commit.

**Out-of-band variant** (future; not in Phase 1 unless a specific case demands it): `PlatformEventService.emit_out_of_band(...)` which opens its own connection. Useful when you need to record a fact even if the business transaction rolled back (e.g., a specific error case). Not building now; easy to add.

### 5.2 Request ID middleware

File: `app/src/middleware/request_id.py`

```python
from contextvars import ContextVar
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

_current_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _current_request_id_var.set(rid)
        request.state.request_id = rid
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            _current_request_id_var.reset(token)

def _current_request_id() -> Optional[str]:
    return _current_request_id_var.get()
```

Registered in `app.py`'s middleware list. Accepts incoming `X-Request-ID` from frontend for future cross-correlation (v1 doesn't use it yet; harmless to propagate).

### 5.3 Job run context

File: `app/src/services/events/job_run_context.py`

```python
from contextvars import ContextVar
import uuid
from contextlib import asynccontextmanager

_current_job_run_var: ContextVar[Optional[str]] = ContextVar("job_run_id", default=None)

@asynccontextmanager
async def job_run_context(job_name: str):
    """Wrap any scheduled job body so events inside inherit a job_run_id."""
    jid = str(uuid.uuid4())
    token = _current_job_run_var.set(jid)
    try:
        yield jid
    finally:
        _current_job_run_var.reset(token)

def _current_job_run_id() -> Optional[str]:
    return _current_job_run_var.get()
```

All APScheduler jobs wrapped: `async with job_run_context("retention_purge"): ...`

### 5.4 Where `emit()` gets called from

**Pattern**: service methods that mutate state call `PlatformEventService.emit()` inline. They pass the current session (so the emit shares the transaction), the org_id, and the actor.

Actor construction helper — centralized so everyone does it right:

```python
# src/services/events/actor_factory.py
def actor_from_org_user(ctx: OrgUserContext) -> Actor:
    return Actor(
        user_id=ctx.user.id,
        acting_as_user_id=_acting_as_from_headers(ctx),   # None in normal case
        view_as_role=_view_as_from_headers(ctx),
        actor_type="user",
    )

def actor_system() -> Actor:
    return Actor(actor_type="system")

def actor_agent(agent_type: str) -> Actor:
    return Actor(actor_type="agent", actor_agent_type=agent_type)
```

---

## 6. Subsystem instrumentation

For each subsystem listed in taxonomy §10, the specific instrumentation work.

### 6.1 Inbox / Email (`src/services/agents/*`, `thread_action_service.py`, `email_compose_service.py`, `admin_threads.py`)

| File | Method | Event to emit |
|---|---|---|
| `thread_action_service.py` | `archive_thread()` | `thread.archived` |
| `thread_action_service.py` | `snooze_thread()` | `thread.snoozed` |
| `thread_action_service.py` | `assign_thread()` | `thread.assigned` |
| `thread_action_service.py` | `update_thread_status()` | `thread.status_changed` |
| `thread_action_service.py` | `update_thread_category()` | `thread.category_changed` |
| `admin_threads.py` | GET `/threads/{id}` | `thread.opened` (user_action) |
| `email_compose_service.py` | `compose_and_send()` | `compose.sent`, `agent_message.sent` |
| `email_compose_service.py` | `generate_draft()` | `compose.draft_generated`, `agent.generated` |
| `inbound_email_service.py` | `receive_webhook()` | `agent_message.received` |
| `agents/email_classifier.py` | `classify()` | `agent_message.classified`, `agent.generated` |
| `agents/customer_matcher.py` | `match()` | `agent_message.customer_matched`, `agent.generated` |
| `send_failure.py` | `record_outbound_send_failure()` | `agent_message.send_failed`, `error.email_send_failed` |

### 6.2 Proposals (deferred to Phase 2)

Instrumentation happens in Phase 2 when the proposals system is built. Phase 1 reserves the event names.

### 6.3 Agents (base class wrapper — proactive emission)

Create `src/services/agents/base.py` with a base class or decorator that all agents wrap their Claude calls in. The base emits `agent.generated` + error + context-truncation + lessons-applied events automatically. Ensures emission never forgotten when adding new agents.

```python
class BaseAgent:
    agent_type: str   # override

    async def _call_claude(self, db, org_id, actor, **kwargs):
        # Wrap api call; emit agent.generated, agent.error, agent.context_truncated
        ...
```

### 6.4 Jobs (`src/services/agent_action_service.py`, `src/api/v1/admin_actions.py`)

| File | Method | Event |
|---|---|---|
| `agent_action_service.py` | `create_action()` | `job.created` |
| `admin_actions.py` / service | `update_action_status()` | `job.status_changed`, `job.completed` when status→done, `job.cancelled` when status→cancelled |
| `admin_actions.py` / service | `assign_action()` | `job.assigned` |

### 6.5 Cases (`src/services/service_case_service.py`)

`case.created`, `case.closed`, `case.reopened`, `case.manager_changed` — emit in the respective service methods.

### 6.6 Invoices (`src/services/invoice_service.py`, `estimate_workflow_service.py`, `src/api/v1/invoices.py`)

| Method | Event |
|---|---|
| `InvoiceService.create()` | `invoice.created` |
| `InvoiceService.send()` | `invoice.sent` |
| `InvoiceService.void()` | `invoice.voided` |
| `InvoiceService.write_off()` | `invoice.write_off` |
| Payment handler | `invoice.paid`, `invoice.days_to_paid` |
| Estimate approval flow | `estimate.approved`, `estimate.declined` |

### 6.7 Visits / Chemistry (`visit_service.py`, `visit_experience_service.py`, measurement services)

- `visit.started`, `visit.en_route.start`, `visit.on_site.start`, `visit.on_site.end`, `visit.completed`, `visit.cancelled`, `visit.revisit_required` (derived on start if prior completion within N days)
- `chemical_reading.logged` on reading creation
- `chemistry.reading.out_of_range` — emitted by a check function called on every reading.logged that compares against MAHC/Title-22 thresholds. Threshold table seeded.
- `chemistry.dose.applied` — emit when a dose is recorded
- `chemistry.dose.expected_vs_actual` — emit in a follow-up handler that runs when the NEXT reading is logged against the same water feature
- `photo.uploaded` — emit on upload

### 6.8 Customers / Properties / Equipment

CRUD events + lifecycle (`customer.cancelled`, `customer.recurring_service_paused|resumed|skipped`) on the appropriate service methods.

### 6.9 Auth (`src/api/v1/auth.py`, `auth_service.py`)

`user.login`, `user.login_failed`, `user.logout`, `user.session_expired`, `user.password_reset_requested`, `user.password_reset_completed`, `user.email_recovered`.

### 6.10 Settings / Config

`settings.changed`, `feature_flag.toggled`, `workflow_config.changed` (Phase 4 will add the workflow handler events).

### 6.11 Errors (global middleware + error tracking)

`error.backend_5xx` emitted from `src/middleware/error_tracking.py`. Other `error.*` events emitted from the specific failure handlers.

### 6.12 Activation funnel

Emitted by a small derived-event writer: `src/services/events/activation_tracker.py`. Called from the relevant milestones (first customer created, first visit completed, etc.). Checks "has this org emitted this activation event yet?" before emitting — one-per-org-ever semantics.

---

## 7. Frontend client

### 7.1 `lib/session-id.ts`

```ts
const KEY = "qp_session_id";

export function getSessionId(): string {
  let sid = sessionStorage.getItem(KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    sessionStorage.setItem(KEY, sid);
  }
  return sid;
}
```

### 7.2 `lib/events.ts`

```ts
import { getSessionId } from "./session-id";

type EmitPayload = {
  event_type: string;
  level: "user_action" | "error";  // frontend-origin can't be system/agent
  entity_refs?: Record<string, string>;
  payload?: Record<string, unknown>;
};

const BATCH_LIMIT = 20;
const FLUSH_MS = 5000;
const BUFFER_KEY = "qp_events_buffer";

class EventClient {
  private buffer: (EmitPayload & { client_emit_id: string; created_at: string })[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    // Restore unflushed buffer from prior tab session
    const restored = sessionStorage.getItem(BUFFER_KEY);
    if (restored) {
      try { this.buffer = JSON.parse(restored); } catch { /* ignore */ }
      sessionStorage.removeItem(BUFFER_KEY);
    }
    // Attach tab-close handler
    if (typeof window !== "undefined") {
      window.addEventListener("pagehide", () => this._flushOnUnload());
    }
  }

  emit(payload: EmitPayload) {
    this.buffer.push({
      ...payload,
      client_emit_id: crypto.randomUUID(),
      created_at: new Date().toISOString(),   // client timestamp; server rewrites
    });
    sessionStorage.setItem(BUFFER_KEY, JSON.stringify(this.buffer));

    if (this.buffer.length >= BATCH_LIMIT) {
      this.flush();
    } else if (!this.timer) {
      this.timer = setTimeout(() => this.flush(), FLUSH_MS);
    }
  }

  async flush() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (this.buffer.length === 0) return;
    const batch = this.buffer.splice(0);
    sessionStorage.setItem(BUFFER_KEY, JSON.stringify(this.buffer));

    try {
      const res = await fetch("/api/v1/events", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Session-Id": getSessionId(),
        },
        body: JSON.stringify({ events: batch }),
      });
      if (res.status === 401 || res.status === 403) {
        return;  // drop — unauthenticated events can't be trusted
      }
      if (!res.ok) {
        // Put back with exponential backoff; drop after 3 retries
        this._retryOrDrop(batch);
      }
    } catch {
      this._retryOrDrop(batch);
    }
  }

  private _flushOnUnload() {
    if (this.buffer.length === 0) return;
    const payload = JSON.stringify({ events: this.buffer });
    // sendBeacon because fetch() is not reliable in pagehide/unload
    navigator.sendBeacon("/api/v1/events", new Blob([payload], { type: "application/json" }));
    // Don't clear buffer — if beacon fails, next session restores it from sessionStorage
  }

  private _retryOrDrop(batch: Array<unknown>) {
    // v1: simple — put back once, retry on next tick; drop if it keeps failing.
    // v2: exponential backoff with jitter.
    // Details in implementation — omitted here for brevity.
  }
}

export const events = new EventClient();
```

### 7.3 Route-change emission

`frontend/src/app/layout.tsx` (or a top-level provider) uses `usePathname()` with `useEffect` to emit `page.viewed` on every navigation. Dwell-time tracking on the 10 key surfaces uses a custom hook `useDwellTime()` that captures entry time and emits `page.exited` on unmount.

### 7.4 Backend receiver

`POST /api/v1/events`:
- Rate-limited (slowapi) — 100 events / minute / session_id
- Validates each event in batch (event_type in allowlist, payload size < 8KB, level ∈ frontend-allowed set)
- Calls `PlatformEventService.emit()` for each
- Returns `{accepted: N}` — never 500 on individual bad events (drops the bad ones, accepts the rest, logs the drops)

---

## 8. Backfill migration script

File: `app/scripts/backfill_platform_events.py`

**Usage**: `./venv/bin/python app/scripts/backfill_platform_events.py [--dry-run] [--since YYYY-MM-DD] [--org-id UUID]`

**Flow:**
1. For each entity type listed in taxonomy §14, run a query that SELECTs existing rows and derives events.
2. Insert events with `actor_type = 'system'`, `payload.source = 'backfill'`, `client_emit_id = 'backfill:<entity_type>:<entity_id>'` (deterministic so re-runs are idempotent).
3. Batch inserts (1,000 rows per transaction).
4. Progress logging every 1,000 rows.
5. Summary emitted at end: total events created per entity type.

**Example — jobs backfill:**

```python
async def backfill_jobs(db: AsyncSession):
    result = await db.execute(
        select(AgentAction).where(AgentAction.created_at.isnot(None))
    )
    count = 0
    for row in result.scalars():
        await PlatformEventService.emit(
            db=db,
            event_type="job.created",
            level="system_action",
            actor=actor_system(),
            organization_id=row.organization_id,
            entity_refs={"job_id": row.id, "case_id": row.case_id, "customer_id": row.customer_id},
            payload={
                "job_type": row.action_type,
                "source": "backfill",
                "original_created_at": row.created_at.isoformat(),
            },
            client_emit_id=f"backfill:job.created:{row.id}",
        )
        count += 1
        if count % 1000 == 0:
            await db.commit()
            logger.info(f"Backfilled {count} job.created events")
    await db.commit()
    return count
```

**Cutover procedure:**
1. Deploy code with `PlatformEventService` + middleware + frontend client + instrumentation (NOT the scheduler jobs yet).
2. Run backfill script against production DB. ~1-2 minutes expected.
3. Enable APScheduler jobs (partition manager, retention purge) on next deploy.
4. Monitor emit error rate for 24h.

---

## 9. Purge-on-request endpoint details

`POST /api/v1/admin/users/{user_id}/purge-events`

```python
@router.post("/users/{user_id}/purge-events")
async def purge_events(
    user_id: str,
    note: Optional[str] = Body(None),
    ctx: PlatformAdminContext = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    request_id = str(uuid.uuid4())

    # 1. Record the request
    await db.execute(text("""
        INSERT INTO data_deletion_requests (id, requested_by_user_id, target_user_id, target_type, scope, note)
        VALUES (:rid, :req_by, :tgt, 'user', :scope, :note)
    """), {...})

    # 2. Execute the purge in a single transaction
    result1 = await db.execute(text("""
        UPDATE platform_events SET actor_user_id = NULL WHERE actor_user_id = :uid
    """), {"uid": user_id})
    result2 = await db.execute(text("""
        UPDATE platform_events SET acting_as_user_id = NULL WHERE acting_as_user_id = :uid
    """), {"uid": user_id})
    result3 = await db.execute(text("""
        UPDATE platform_events SET entity_refs = entity_refs - 'user_id'
        WHERE entity_refs @> jsonb_build_object('user_id', :uid)
    """), {"uid": user_id})

    total = result1.rowcount + result2.rowcount + result3.rowcount

    # 3. Mark the request complete
    await db.execute(text("""
        UPDATE data_deletion_requests
        SET completed_at = NOW(), completed_rows_affected = :n
        WHERE id = :rid
    """), {"rid": request_id, "n": total})

    await db.commit()
    return {"request_id": request_id, "rows_affected": total}
```

---

## 10. Completeness audit script

File: `app/scripts/audit_instrumentation.py`

**Goal**: automatically detect service methods that mutate state without emitting events.

**Approach:**
1. Parse all `.py` files under `app/src/services/` with the `ast` module.
2. For each function, check: does it call `db.add(...)`, `db.execute(insert|update|delete)`, etc.?
3. If yes: does the function (or its immediate callees) call `PlatformEventService.emit(...)`?
4. If no: report the function as a candidate offender.
5. Compare against an allowlist in `app/scripts/instrumentation_allowlist.yml` — functions that legitimately don't emit (e.g., pure reads mislabeled; partial writes wrapped in larger operations that DO emit).
6. Exit non-zero if any new non-allowlisted offender exists.

**CI integration:**
```yaml
- name: Instrumentation completeness audit
  run: ./venv/bin/python app/scripts/audit_instrumentation.py --strict
```

Allowlist is expected to shrink over time, not grow. PRs that add to the allowlist require justification in the PR description.

---

## 11. Test plan

### 11.1 Unit tests (`tests/services/events/`)

- `test_platform_event_service.py`:
  - `test_emit_basic()` — happy path, row inserted correctly
  - `test_emit_oversized_payload_truncates()`
  - `test_emit_idempotent_on_duplicate_client_emit_id()`
  - `test_emit_never_raises_on_db_error()` — mocks DB to raise, asserts no exception propagates
  - `test_emit_with_null_org_for_auth_events()`
  - `test_emit_reads_request_id_from_contextvar()`

- `test_request_id_middleware.py` — integration style, verifies header round-trip and contextvar set.

- `test_retention_purge.py` — seeds events at various ages, runs purge, asserts correct rows removed.

- `test_partition_manager.py` — calls ensure_next_partition, asserts the partition exists in pg_tables.

### 11.2 `event_recorder` fixture (`tests/fixtures/event_recorder.py`)

```python
@pytest.fixture
async def event_recorder(db_session):
    """Captures all platform_events emitted during a test."""
    class Recorder:
        async def get_all(self) -> list[dict]:
            result = await db_session.execute(
                text("SELECT * FROM platform_events ORDER BY created_at ASC")
            )
            return [dict(row) for row in result.mappings()]

        async def assert_emitted(self, event_type: str, **entity_ref_filters):
            events = await self.get_all()
            matches = [
                e for e in events
                if e["event_type"] == event_type
                and all(e["entity_refs"].get(k) == v for k, v in entity_ref_filters.items())
            ]
            assert matches, f"No {event_type} event found with refs {entity_ref_filters}. All events: {[e['event_type'] for e in events]}"
            return matches

    return Recorder()
```

### 11.3 Integration tests (required 5 subsystems)

1. `tests/integration/test_inbox_instrumentation.py` — simulate inbound webhook → assert `agent_message.received`, `thread.summarized` (stubbed), `agent_message.classified`, `agent_message.customer_matched`.
2. `tests/integration/test_job_lifecycle_instrumentation.py` — create job → assign → complete → assert `job.created`, `job.assigned`, `job.completed`.
3. `tests/integration/test_estimate_funnel_instrumentation.py` — draft estimate → send → approve (simulated) → convert → full funnel events present.
4. `tests/integration/test_chemistry_instrumentation.py` — log reading with bad pH → assert `chemical_reading.logged` + `chemistry.reading.out_of_range`.
5. `tests/integration/test_auth_instrumentation.py` — login success + failure + password reset request + completion → events in order.

### 11.4 CI configuration

Added to existing pytest suite. CLAUDE.md's testing runner:
```
cd app && venv/bin/pytest tests/ -W ignore::DeprecationWarning
```

---

## 12. Rollout sequence

Ordered commits, each independently deployable and verifiable:

1. **Migration + table + orgs column** — `platform_events` exists, empty. Verify: migration applies cleanly, indexes present, initial partitions exist.
2. **`PlatformEventService.emit()` + unit tests + middleware + `request_id` propagation** — service exists, no callers yet.
3. **Frontend `lib/events.ts` + `POST /v1/events` backend receiver** — frontend can emit but nothing does yet. Verify: manual POST via curl lands an event.
4. **Inbox subsystem instrumentation + integration test** — inbox emits events for real operations. Verify: Sapphire inbox actions show up in the table.
5. **Job + Case + Invoice + Visit subsystems** (one PR per subsystem; each shippable independently).
6. **Chemistry subsystem** — out-of-range check + threshold seeds + dose tracking.
7. **Frontend event emission hookup** — route-change emitter, inbox/compose/case action emitters.
8. **Activation funnel tracker** — one-per-org-ever guard + milestone checkpoints.
9. **Backfill script + cutover** — run against production.
10. **APScheduler jobs: partition manager + retention purge** — enable.
11. **Purge-on-request endpoint** — `POST /v1/admin/users/{id}/purge-events`. Writes to the `data_deletion_requests` audit table (already created in Step 1). Updates `platform_events` to null identifiers.
12. **Admin read-only event query endpoint** — `GET /v1/admin/events` for ad-hoc debugging + future Sonar consumption. Filter params: `org_id`, `event_type`, `from`, `to`, `entity_ref`, `limit`. Platform-admin gated.
13. **Completeness audit script + CI integration** — fails build if undocumented mutations.
14. **Phase 1 DoD verification** — 11-item checklist from taxonomy §16 walked through and confirmed.

Each step gets its own commit message + deploy via `scripts/deploy.sh`. After each step, verify via a targeted query (e.g., after step 4: `SELECT count(*), event_type FROM platform_events WHERE event_type LIKE 'thread.%' GROUP BY event_type`).

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Emission failures silently lose data | Structured logging + ntfy alert when `platform_events.emit failed` log exceeds N/min. Backend unit test asserts emit never raises. |
| Backfill script produces wrong events | Dry-run mode required. Run against a restored prod backup first. Validate counts against source tables before cutover. |
| Retention purge accidentally deletes too much | Soft-delete-first pattern: in v1, retention purge ONLY deletes events where `created_at < now - retention_days`. Guard assertion: never delete more than X% of org's events in one run; alert instead. |
| Partition creation job fails silently | Partition manager emits `error.background_job_failed` on failure + ntfy alert. Weekly check: verify next 2 months of partitions exist. |
| Frontend buffer loss on browser crash | sessionStorage backup restores on next session. Beacon-on-unload last-gasp. Acceptable v1 loss: rare crashes during 5s buffer window. |
| Event volume exceeds Postgres I/O | Query-pattern monitoring; if p99 insert latency rises, switch to async buffer+flush pattern (design allows swap without interface change). |
| CCPA deletion request arrives while event partition is being rotated | Single transaction for purge updates. Partition rotation is append-only (creates new, doesn't touch existing). Non-conflict. |
| Completeness audit becomes an allowlist dumpster fire | Allowlist entries require justification in PR. Weekly audit report (manual for now) lists top N allowlisted items to review. |
| Dev/test databases accumulate events endlessly | Test fixtures TRUNCATE `platform_events` between tests (already standard for other tables in the suite). |
| Backfill creates duplicates on re-run | Deterministic `client_emit_id` (`backfill:<type>:<id>`) + unique constraint = idempotent. |
| Privacy regression: PII sneaks into a payload | Code review + a pattern-match test in CI that scans event_type + payload combinations against known PII field names (email, phone, address, name). |

---

## 14. Phase 1 Definition of Done

(Repeated from taxonomy §16 so this spec stands alone.)

1. `platform_events` table exists with monthly partitioning; next-month partition automation running.
2. `organizations.event_retention_days` column exists and defaults are set (dogfood 10y, paying 3y).
3. `PlatformEventService.emit()` implemented with: idempotency check, 8KB payload cap, fail-soft error handling, outbox/buffered-fallback pattern designed (even if not activated).
4. Backend middleware emits `request_id` and propagates it via `request.state`.
5. Frontend `lib/events.ts` batching client implemented + route-change emitter.
6. Backfill migration script written, tested on a copy of dogfood data, and run at cutover.
7. Daily retention-purge job implemented + enabled.
8. Purge-on-request endpoint + `data_deletion_requests` audit table implemented + tested.
9. Every subsystem listed in taxonomy §10 emits its documented events — verified by the CI completeness audit + manual walk of 10 real workflows.
10. Integration tests exist for at least 5 subsystems using `event_recorder` fixture.
11. Query `SELECT count(*), event_type FROM platform_events WHERE organization_id = :sapphire GROUP BY event_type` returns a distribution consistent with a day of normal Sapphire usage (no suspiciously thin or missing categories).

Phase 1 ships when all 11 are green. Master plan status flips to "Shipped YYYY-MM-DD" on completion.

---

## 15. Open decisions to resolve before code starts

1. **Actor-from-request middleware** — do we want a separate middleware that builds the `Actor` from request context and attaches to `request.state.actor`? Or keep the `actor_from_org_user(ctx)` helper and call it at each emit site? (I lean toward middleware for DRY; flag for your call.)
2. **Event type allowlist on frontend receiver** — do we enumerate every `event_type` the frontend is allowed to send, or accept any well-formed type? (I lean allowlist — prevents frontend from inventing types outside the taxonomy.)
3. **Rate limit on `POST /v1/events`** — I spec'd 100/min/session. Reasonable? Too loose?
4. **Sapphire dogfood retention** — I set 10 years. You mentioned keeping forever might be desired for dev work. Confirm 10 vs. something else.
5. **Oversized-payload event itself** — when we truncate an 8KB+ payload, we emit `platform_event.oversized_payload`. That's itself an event that could theoretically itself be oversized. Protection: the oversized marker has a fixed small shape so recursion is bounded. Fine as-is.
6. **Backfill ordering** — dependencies matter (customer before property before water_feature before visit). I have an order in mind; confirm it when you review the backfill script before running.

Your call on each; confirm and I start Step 1 of the rollout sequence.
