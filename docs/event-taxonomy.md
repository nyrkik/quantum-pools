# Event Taxonomy

Canonical catalog of event types emitted into `platform_events`. Every new event type added to code MUST be documented here in the same PR. Drift between code and this doc is a bug.

**Status**: Phase 0 of `docs/ai-platform-plan.md`. Locked 2026-04-18. Evolves additively as new events are introduced.

## 1. Purpose

One unified event stream feeds every downstream consumer: agent learning, workflow observation (per-org proposals), Sonar (dev-facing intelligence), debugging, audit, and future analytics. A single canonical taxonomy prevents the failure mode where team A logs `job.created` and team B logs `JOB_CREATED_EVENT` and the analytics layer becomes a janitor forever.

Principle in play: `feedback_data_capture_is_king` — default to capturing more. Storage is cheap; uncaptured data is unrecoverable.

## 2. Schema

Every row in `platform_events`:

| Field | Type | Notes |
|---|---|---|
| `id` | uuid, pk | |
| `organization_id` | varchar(36), indexed, **nullable** | Null for platform-scoped events (login attempts pre-auth, signup flow, etc.) |
| `actor_user_id` | varchar(36), nullable | Null for system/agent actions |
| `actor_type` | enum | `user` / `system` / `agent` |
| `actor_agent_type` | varchar(50), nullable | When `actor_type=agent`, which agent (e.g., `email_drafter`) |
| `event_type` | varchar(100), indexed | Dotted naming — see §3 |
| `level` | enum | `user_action` / `system_action` / `agent_action` / `error` |
| `entity_refs` | jsonb | Polymorphic map of `{entity_name: id}` — see §5 |
| `payload` | jsonb | Event-specific fields — see catalog §8 |
| `request_id` | varchar(36), nullable | Backend HTTP request ID — links backend events within one request |
| `session_id` | varchar(36), nullable | Frontend tab-scoped session — links frontend events within one tab |
| `created_at` | timestamptz, indexed | |

**Indexes:**
- Primary: `(id)`
- `(organization_id, created_at desc)` — most common query
- `(event_type, created_at desc)` — system-wide analytics
- GIN on `entity_refs` — entity timeline queries
- Additional indexes added only when query patterns demonstrate need

**Partitioning:**
Monthly declarative partitions (`platform_events_2026_04`, `platform_events_2026_05`, ...). Partition management is a pgcron job that creates next month's partition ahead of time.

**Retention:**
Permanent for dogfood/dev orgs. Configurable per-org retention policy is a future concern (not in Phase 1).

## 3. Naming convention

`<entity_noun>.<past_tense_verb>`, lowercase, underscores inside segments, dots between.

Rules:
- Past tense always. Events record what happened, not commands. `thread.opened`, not `thread.open`.
- Noun first. The entity being affected leads. `proposal.accepted`, not `accepted.proposal`.
- Composite nouns use underscores. `agent_message.sent`, `water_feature.created`.
- Namespace with care. When an event is subsystem-specific (not entity-specific), use the subsystem as the noun: `compose.draft_generated`, `inbox.filter_changed`.

Rejected alternatives: `CamelCase`, `SCREAMING_SNAKE`, verb-first, present tense.

## 4. Levels

| Level | When |
|---|---|
| `user_action` | A user explicitly did something — clicked, typed, submitted. |
| `system_action` | Backend process did something without direct user input — scheduled job, webhook handler, background sweep. |
| `agent_action` | An AI agent produced output (classification, draft, summary, tool use, proposal stage). **Includes auto-applied classifications** — anything the AI decided. |
| `error` | Something failed. May be user-triggered (level=error with actor_type=user) or system-triggered. |

Usually `level` correlates with `actor_type` but not always: a user click that causes a 500 is `level=error, actor_type=user`.

## 5. Canonical `entity_refs` keys

Any event may reference any of these. An event may add additional keys beyond this list; the canonical keys are enforced for entity-timeline queries to work consistently.

| Key | FK target |
|---|---|
| `user_id` | users.id |
| `customer_id` | customers.id |
| `property_id` | properties.id |
| `water_feature_id` | water_features.id |
| `thread_id` | agent_threads.id |
| `agent_message_id` | agent_messages.id |
| `agent_proposal_id` | agent_proposals.id (future table) |
| `case_id` | service_cases.id |
| `job_id` | agent_actions.id (jobs are stored in agent_actions) |
| `invoice_id` | invoices.id |
| `visit_id` | visits.id |
| `chemical_reading_id` | chemical_readings.id |
| `equipment_item_id` | equipment_items.id |
| `inspection_id` | inspections.id |

## 6. Privacy — what goes in `payload`

**Reference by ID**, never by content. Forbidden in payloads:
- Email addresses, phone numbers, physical addresses
- Customer names, user names
- Message subjects, message bodies
- Notes, description text
- Invoice/estimate amounts
- Photo file contents or recognizable dimensions
- Any raw text the customer authored

Allowed:
- IDs (see §5)
- Enum values (status strings, category strings)
- Numeric dimensions (durations, counts, percentages, confidence scores)
- Boolean flags
- Short `reason` strings from a whitelisted set (e.g., `rejection_reason: "wrong_part"`)

**Exception — `error.*` events** may include a truncated error message (≤200 chars) for debugging. Never raw user text inside the error message — strip before logging.

## 7. Request / session correlation

- **Backend**: middleware generates a UUID4 per incoming HTTP request, attached to `request.state.request_id`. All events emitted during that request inherit it automatically via the `PlatformEventService.emit()` helper.
- **Frontend**: tab-scoped `session_id` generated once per tab via sessionStorage. Emitted with every frontend event.
- Backend events originating from a frontend action are NOT cross-correlated in v1 (no `client_event_id` passed through API calls). If this analysis need arises, add in a future phase.

## 8. Event catalog

Organized by subsystem. Each event specifies level and minimum expected `entity_refs`. Payload schema is given only when non-obvious.

### 8.1 Inbox / Email

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `thread.opened` | user_action | thread_id | User opened a thread in the inbox. |
| `thread.closed` | user_action | thread_id | User navigated away. Payload: `{duration_ms}`. |
| `thread.archived` | user_action | thread_id | Payload: `{prior_status}`. |
| `thread.snoozed` | user_action | thread_id | Payload: `{until_date}`. |
| `thread.unsnoozed` | system_action | thread_id | Background wake. |
| `thread.assigned` | user_action | thread_id, user_id | `user_id` = new assignee. Payload: `{prior_assignee_id}`. |
| `thread.status_changed` | user_action \| system_action | thread_id | Payload: `{from, to, reason}`. |
| `thread.category_changed` | user_action | thread_id | Payload: `{from, to}`. User override of AI classification. |
| `thread.summarized` | agent_action | thread_id | Inbox summarizer wrote/refreshed summary. Payload: `{tokens_in, tokens_out, duration_ms, confidence, proposals_staged}`. |
| `thread.linked_to_case` | user_action \| system_action | thread_id, case_id | |
| `thread.unlinked_from_case` | user_action | thread_id, case_id | |
| `agent_message.received` | system_action | thread_id, agent_message_id | Inbound email landed. Payload: `{provider, had_attachments, has_cc}`. |
| `agent_message.sent` | user_action | thread_id, agent_message_id | User approved outbound send. Payload: `{draft_was_ai_generated, edited_before_send}`. |
| `agent_message.send_failed` | error | thread_id, agent_message_id | Payload: `{provider, error_class, short_error}`. |
| `agent_message.classified` | agent_action | thread_id, agent_message_id | Payload: `{category, urgency, customer_match_confidence}`. |
| `agent_message.customer_matched` | agent_action | agent_message_id, customer_id | Payload: `{confidence, method}`. |
| `agent_message.customer_match_overridden` | user_action | agent_message_id, customer_id | User corrected the match. Payload: `{from_customer_id, reason}`. |
| `compose.opened` | user_action | thread_id, customer_id, case_id | Any of refs may be null. |
| `compose.draft_generated` | agent_action | thread_id, customer_id | AI produced a draft. Payload: `{tokens_in, tokens_out, duration_ms, subject_included}`. |
| `compose.draft_regenerated` | user_action | thread_id | User asked AI to rewrite. Payload: `{rounds}`. |
| `compose.sent` | user_action | thread_id, agent_message_id | Payload: `{edited_from_draft, char_delta_from_draft, cc_added, attachments}`. |
| `compose.discarded` | user_action | thread_id | Payload: `{had_content, duration_ms_open}`. |
| `inbox.filter_changed` | user_action | — | Payload: `{chips_active, view}`. |
| `inbox.folder_viewed` | user_action | — | Payload: `{folder_id \| folder_name}`. |
| `inbox.bulk_action` | user_action | — | Payload: `{action, thread_count}`. |
| `inbox.compact_mode_toggled` | user_action | — | Payload: `{enabled}`. |

### 8.2 Proposals (agent_proposals system — Phase 2)

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `proposal.staged` | agent_action | agent_proposal_id + source entity | Payload: `{agent_type, entity_type, confidence, source_type}`. |
| `proposal.accepted` | user_action | agent_proposal_id, outcome_entity_id | Payload: `{agent_type, entity_type, resolution_ms_since_staged, edited: false}`. |
| `proposal.edited_and_accepted` | user_action | agent_proposal_id, outcome_entity_id | Same as above with `edited: true` plus `delta_keys: [...]` listing which fields changed. |
| `proposal.rejected` | user_action | agent_proposal_id | Payload: `{agent_type, entity_type, permanently: false, reason?}`. |
| `proposal.rejected_permanently` | user_action | agent_proposal_id | Payload: `{agent_type, entity_type, reason?}`. Signals "never again" to the agent. |
| `proposal.expired` | system_action | agent_proposal_id | Background sweep marked stale. Payload: `{age_days}`. |
| `proposal.superseded` | system_action \| agent_action | agent_proposal_id (new), agent_proposal_id (old, in payload) | Payload: `{superseded_id, reason}`. |

### 8.3 Agents (generic)

Applies to any agent call — `email_drafter`, `email_classifier`, `customer_matcher`, `equipment_resolver`, `estimate_generator`, `inbox_summarizer`, `workflow_observer`, `sonar`, `deepblue_responder`, `command_executor`, etc.

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `agent.generated` | agent_action | varies by agent | Produced output. Payload: `{agent_type, tokens_in, tokens_out, duration_ms, model, confidence?}`. |
| `agent.tool_called` | agent_action | varies | DeepBlue / Sonar tool invocation. Payload: `{agent_type, tool_name, arg_keys, duration_ms}`. No arg values (PII risk). |
| `agent.error` | error | varies | Payload: `{agent_type, error_class, short_error}`. |
| `agent.lessons_applied` | agent_action | varies | Learning prompt injection happened. Payload: `{agent_type, lesson_count, customer_scoped: bool}`. |

### 8.4 Jobs (agent_actions table)

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `job.created` | user_action \| system_action \| agent_action | job_id, case_id?, thread_id? | Payload: `{job_type, source}` where source ∈ (manual, thread_ai, case_auto, proposal_accepted, deepblue_tool). |
| `job.status_changed` | user_action \| system_action | job_id | Payload: `{from, to, reason?}`. |
| `job.assigned` | user_action | job_id, user_id | Payload: `{prior_assignee_id}`. |
| `job.scheduled` | user_action \| system_action | job_id | Payload: `{scheduled_date, prior_date?}`. |
| `job.completed` | user_action | job_id, visit_id? | Payload: `{duration_days_since_created}`. |
| `job.cancelled` | user_action | job_id | Payload: `{reason?}`. |

### 8.5 Cases (service_cases)

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `case.created` | user_action \| system_action | case_id, customer_id? | Payload: `{source, linked_thread_count, linked_job_count}`. |
| `case.closed` | user_action \| system_action | case_id | Payload: `{reason, auto_closed: bool, cascade_jobs_closed}`. |
| `case.reopened` | user_action | case_id | Payload: `{cascade_jobs_reopened}`. |
| `case.manager_changed` | user_action | case_id, user_id | Payload: `{prior_manager_id}`. |

### 8.6 Invoices / Estimates

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `invoice.created` | user_action \| system_action \| agent_action | invoice_id, customer_id?, case_id? | Payload: `{document_type: invoice\|estimate, source}`. |
| `invoice.sent` | user_action | invoice_id | Payload: `{document_type, recipient_count, resolver_used: contacts\|customer_fallback}`. |
| `invoice.paid` | user_action \| system_action | invoice_id | Payload: `{method, auto_pay: bool}`. |
| `invoice.voided` | user_action | invoice_id | |
| `invoice.write_off` | user_action | invoice_id | |
| `estimate.approved` | user_action | invoice_id, customer_id | Approved via customer-facing approval link. Payload: `{elapsed_hours_since_sent}`. |
| `estimate.declined` | user_action | invoice_id | Payload: `{reason?}`. |
| `estimate.converted_to_invoice` | user_action \| system_action | invoice_id (estimate), invoice_id (new invoice, in payload) | |

### 8.7 Visits / Chemistry

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `visit.started` | user_action | visit_id, property_id, user_id | |
| `visit.completed` | user_action | visit_id, property_id | Payload: `{duration_minutes, tasks_completed, photos, readings}`. |
| `visit.cancelled` | user_action | visit_id | Payload: `{reason?}`. |
| `chemical_reading.logged` | user_action \| agent_action | chemical_reading_id, water_feature_id, visit_id? | Payload: `{source: manual \| test_strip_vision \| deepblue}`. No chemistry values in payload (those are on the reading row). |
| `photo.uploaded` | user_action | property_id, visit_id?, water_feature_id? | Payload: `{purpose: measurement \| before_after \| issue_report, size_kb}`. |

### 8.8 Customers / Properties / Equipment

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `customer.created` | user_action \| system_action \| agent_action | customer_id | Payload: `{source}`. |
| `customer.edited` | user_action | customer_id | Payload: `{fields_changed: [...]}`. Field names only, no values. |
| `customer.status_changed` | user_action | customer_id | Payload: `{from, to}`. |
| `customer_contact.created` | user_action | customer_id | Payload: `{role?, is_primary}`. |
| `customer_contact.edited` | user_action | customer_id | Payload: `{fields_changed: [...]}`. |
| `property.created` | user_action | property_id, customer_id | |
| `property.edited` | user_action | property_id | Payload: `{fields_changed: [...]}`. |
| `water_feature.created` | user_action | water_feature_id, property_id | Payload: `{type, is_primary}`. |
| `water_feature.edited` | user_action | water_feature_id | Payload: `{fields_changed: [...]}`. |
| `equipment_item.added` | user_action \| agent_action | equipment_item_id, property_id | Payload: `{catalog_equipment_id?, source}`. |
| `equipment_item.removed` | user_action | equipment_item_id | |

### 8.9 Auth / Users

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `user.login` | user_action | user_id | `organization_id` may be null (pre-org selection). Payload: `{method: password \| oauth}`. |
| `user.login_failed` | error | — | `organization_id` null. Payload: `{reason: bad_password \| locked \| inactive \| not_found, email_domain}`. Domain only, not full email. |
| `user.logout` | user_action | user_id | |
| `user.session_expired` | system_action | user_id | |
| `user.password_reset_requested` | user_action | — | `organization_id` null. Payload: `{email_domain}`. |
| `user.password_reset_completed` | user_action | user_id | Payload: `{sessions_invalidated}`. |
| `user.email_recovered` | user_action | — | `organization_id` null. Payload: `{match: bool}`. |
| `user.invited` | user_action | user_id | Payload: `{role}`. |

### 8.10 Settings / Config

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `settings.changed` | user_action | — | Generic. Payload: `{area, fields_changed: [...]}`. Field names only. |
| `feature_flag.toggled` | user_action | — | Payload: `{flag, value}`. |
| `workflow_config.changed` | user_action | user_id | Payload: `{handler_area, from, to, via: manual \| proposal_accepted, proposal_id?}`. |

### 8.11 Navigation

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `page.viewed` | user_action | varies (populated where obvious — e.g., customer_id on /customers/{id}) | Payload: `{path, referrer?, is_auth_page: bool}`. Emitted on every route change. `organization_id` null for unauthenticated routes. |
| `page.exited` | user_action | same as page.viewed | Emitted only for 10 key surfaces (inbox, case detail, customer detail, invoice detail, estimate detail, job detail, settings, profitability dashboard, deepblue, satellite). Payload: `{path, dwell_ms}`. |

### 8.12 Errors

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `error.backend_5xx` | error | request-relevant | Payload: `{path, method, status, error_class, short_error}`. |
| `error.ai_call_failed` | error | varies | Payload: `{agent_type, provider, error_class, short_error, retryable: bool}`. |
| `error.email_send_failed` | error | agent_message_id | Payload: `{provider, error_class, short_error}`. |
| `error.background_job_failed` | error | — | Payload: `{job_name, error_class, short_error}`. |
| `error.external_api_failed` | error | varies | Payload: `{service, endpoint_tag, status, error_class}`. |
| `error.frontend_unhandled` | error | — | Payload: `{route, error_class, short_error, user_agent_class}`. |

## 9. Schema evolution

- **Additive changes to a payload**: free. Old rows lacking the new field are fine. Add the field to this doc in the same PR.
- **Breaking semantic change**: introduce a NEW event type with a different name. Do not repurpose an existing type.
- **Deprecation**: when an event is no longer emitted, mark `**Deprecated**` in this doc with the date. Do not delete the entry. Old data is forever.
- **Renaming**: never rename a live event type. The old name lives in historical data; creating a new type and eventually deprecating the old is the only safe path.

## 10. Instrumentation responsibilities

Owning code paths for each subsystem (authoritative — if an event in §8 isn't emitted from the listed file, it's a bug):

| Subsystem | Where emitted |
|---|---|
| Inbox / Email | `src/services/email_compose_service.py`, `src/services/agents/*`, `src/services/thread_action_service.py`, `src/api/v1/admin_threads.py`, frontend `components/inbox/*`, `components/email/compose-email.tsx` |
| Proposals | `src/services/proposals/proposal_service.py` (Phase 2) |
| Agents | Each agent service under `src/services/agents/` and `src/services/deepblue/*`; wrapped via a decorator or base class so emission is not forgotten |
| Jobs | `src/services/agent_action_service.py`, `src/api/v1/admin_actions.py` (or wherever jobs are touched) |
| Cases | `src/services/service_case_service.py` |
| Invoices | `src/services/invoice_service.py`, `src/services/estimate_workflow_service.py`, `src/api/v1/invoices.py` |
| Visits | `src/services/visit_service.py`, `src/services/visit_experience_service.py` |
| Customers | `src/services/customer_service.py`, `src/api/v1/customers.py`, `src/api/v1/customer_contacts.py` |
| Auth | `src/api/v1/auth.py`, `src/services/auth_service.py` |
| Navigation | Frontend `lib/events.ts` client + route listener |
| Errors | Middleware `src/middleware/error_tracking.py` (backend), global error boundary (frontend) |

A platform rule: new code paths that mutate domain state without emitting a corresponding event are caught in code review. Eventually a lint/test asserts this.

## 11. Common query patterns

Documented here so indexes can be validated against real analytics questions. Each pattern shows the query shape; the index that serves it is noted.

### "Everything that happened for org X last week"
```sql
SELECT event_type, created_at, actor_type, payload
FROM platform_events
WHERE organization_id = $1
  AND created_at >= NOW() - interval '7 days'
ORDER BY created_at DESC;
```
Index: `(organization_id, created_at desc)`.

### "Timeline for a specific thread"
```sql
SELECT event_type, created_at, payload
FROM platform_events
WHERE entity_refs @> '{"thread_id": "..."}'
ORDER BY created_at ASC;
```
Index: GIN on `entity_refs`.

### "Agent X acceptance rate this week"
```sql
SELECT
  COUNT(*) FILTER (WHERE event_type = 'proposal.accepted') * 1.0 /
  NULLIF(COUNT(*) FILTER (WHERE event_type = 'proposal.staged'), 0) AS accept_rate
FROM platform_events
WHERE organization_id = $1
  AND payload->>'agent_type' = 'inbox_summarizer'
  AND created_at >= NOW() - interval '7 days';
```
Index: `(organization_id, created_at desc)` + event_type filter (fast due to low cardinality of event_type in recent window).

### "Funnel: thread opened → compose sent, same session"
```sql
-- Count sessions that opened a thread and sent a compose within 10 minutes
WITH opens AS (
  SELECT session_id, MIN(created_at) AS opened_at
  FROM platform_events
  WHERE event_type = 'thread.opened' AND organization_id = $1
  GROUP BY session_id
),
sends AS (
  SELECT session_id, MIN(created_at) AS sent_at
  FROM platform_events
  WHERE event_type = 'compose.sent' AND organization_id = $1
  GROUP BY session_id
)
SELECT COUNT(*) AS converted
FROM opens o JOIN sends s USING (session_id)
WHERE s.sent_at - o.opened_at < interval '10 minutes';
```
Index: `(organization_id, event_type, created_at desc)` might be warranted if this is hot. Start without; add when Sonar needs it.

### "Error rate by subsystem, last 24h"
```sql
SELECT event_type, COUNT(*)
FROM platform_events
WHERE level = 'error'
  AND created_at >= NOW() - interval '1 day'
GROUP BY event_type
ORDER BY COUNT(*) DESC;
```
Index: `(event_type, created_at desc)`.

## 12. Failure handling (backend)

`PlatformEventService.emit()` contract:
- Non-blocking: wraps body in try/except. Any failure is logged and swallowed.
- Never raises. Never blocks the caller.
- Uses an outbox pattern if DB is under load: events queued to a lightweight buffer (in-memory with Redis fallback), flushed by a background worker.
- On DB outage: buffer events; flush when DB returns. Never lose events to transient outage.

Frontend `emit()`:
- Buffers locally in memory + sessionStorage backup.
- Flushes on 5-second timer OR 20-event buffer OR route change OR tab close (via `navigator.sendBeacon`).
- On 401/403 response: drop the batch (unauthenticated events can't be trusted).
- On 5xx response: retry with exponential backoff; drop after 3 attempts.

## 13. Open items (not blocking Phase 1, revisit at scale)

- Per-org retention policy configuration.
- Event sampling policy for high-volume event types (page views) once one org crosses 1M events/month.
- Cross-correlation between frontend and backend events (frontend `client_event_id` passed through API headers, backend includes it in emitted events).
- Shipping platform_events data to a warehouse (BigQuery/Snowflake) when multi-year analytics queries become slow on operational Postgres.
- Auto-derived events: Sonar asks "when did the user first use feature X" — could be a derived view rather than an emitted event.

These are deliberately deferred. Document now, implement later.
