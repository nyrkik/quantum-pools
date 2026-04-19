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
| `id` | uuid, pk | Server-generated. Never trust client-supplied ids. |
| `organization_id` | varchar(36), indexed, **nullable** | Null for platform-scoped events (login attempts pre-auth, signup flow, etc.) |
| `actor_user_id` | varchar(36), nullable | Who's actually logged in. Null for system/agent actions. |
| `acting_as_user_id` | varchar(36), nullable | When a user is impersonating or viewing-as another user (dev mode, future support impersonation). Null in the normal case. |
| `view_as_role` | varchar(30), nullable | When `X-View-As-Role` header is set (dev mode role testing). Null in the normal case. |
| `actor_type` | enum | `user` / `system` / `agent` |
| `actor_agent_type` | varchar(50), nullable | When `actor_type=agent`, which agent (e.g., `email_drafter`) |
| `event_type` | varchar(100), indexed | Dotted naming — see §3 |
| `level` | enum | `user_action` / `system_action` / `agent_action` / `error` |
| `entity_refs` | jsonb | Polymorphic map of `{entity_name: id}` — see §5 |
| `payload` | jsonb | Event-specific fields. Hard-capped at 8KB in the emit helper — see §6. |
| `request_id` | varchar(36), nullable | Backend HTTP request ID — links backend events within one request |
| `session_id` | varchar(36), nullable | Frontend tab-scoped session — links frontend events within one tab |
| `job_run_id` | varchar(36), nullable | Background job / worker run ID — links events from one scheduled-task invocation (email poll, nightly billing, summary regeneration). Mutually exclusive with `request_id` in practice. |
| `client_emit_id` | varchar(36), nullable | Idempotency key generated at the emit call site (frontend OR backend). Unique with `organization_id` when non-null — prevents duplicate inserts on retry. |
| `created_at` | timestamptz, indexed | **Server time always.** Never trust client clocks. Set on insert server-side. |

**Indexes:**
- Primary: `(id)`
- `(organization_id, created_at desc)` — most common query
- `(event_type, created_at desc)` — system-wide analytics
- GIN on `entity_refs` — entity timeline queries
- `UNIQUE (organization_id, client_emit_id) WHERE client_emit_id IS NOT NULL` — idempotency
- Additional indexes added only when query patterns demonstrate need

**Partitioning:**
Monthly declarative partitions (`platform_events_2026_04`, `platform_events_2026_05`, ...). Partition management is a pgcron job that creates next month's partition ahead of time.

**Retention policy:**

| Org type | Retention | Rationale |
|---|---|---|
| Dogfood / dev / internal orgs | 10 years | Long-horizon data for Sonar + product development; under our own privacy control |
| Paying customer org — default | **3 years** (1,095 days) | Captures 2 full seasonal cycles + prior-year comparison; balances analytical value vs. privacy liability |
| Paying customer org — configurable at signup | 1 year / **3 years (default)** / 5 years / 7 years | Different customers have different risk profiles; no "forever" option offered (no documented bound = CCPA liability) |

- Retention config lives on the `organizations` table as `event_retention_days` (int, default 1095 for customer orgs).
- Daily background job deletes `platform_events` rows where `created_at < NOW() - org.event_retention_days * interval '1 day'`.
- **Purge-on-request flow**: `POST /v1/admin/users/{id}/purge-events` (platform-admin gated) nulls `actor_user_id` + `acting_as_user_id` and strips user-identifying keys from `entity_refs`. Preserves the event shell for aggregate analytics but removes identifying links — the CCPA "right to deletion" contract.
- Privacy policy must state the retention period and deletion path before we take a paying customer.

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

**Also forbidden in payloads: user identifiers (`user_id`, `assignee_id`, `manager_id`, any key whose value is a QP user's id).**
User IDs live ONLY in these three canonical locations, and the purge-on-request endpoint (§11 / Step 11) relies on this:
1. `actor_user_id` column
2. `acting_as_user_id` column
3. `entity_refs` values (under any key — the purge scrubs by value, not by key, so `entity_refs.user_id` / `entity_refs.prior_assignee_user_id` / `entity_refs.prior_manager_user_id` are all legal and all purgeable)

If an event needs both "current" and "prior" user-id slots (e.g., `case.manager_changed`, `job.assigned`), BOTH go into `entity_refs` under distinct keys. The payload stays user-ID-free and may carry display-only denorm fields (`prior_manager_name`, etc.) that are text, not identifiers.

Allowed in payloads:
- IDs that are NOT user-ids (invoice_id in unusual cases, etc. — prefer `entity_refs`)
- Enum values (status strings, category strings)
- Numeric dimensions (durations, counts, percentages, confidence scores)
- Boolean flags
- Short `reason` strings from a whitelisted set (e.g., `rejection_reason: "wrong_part"`)
- Display-only name strings (denorm caches: `prior_manager_name`, etc. — NOT user IDs)

**Exception — `error.*` events** may include a truncated error message (≤200 chars) for debugging. Never raw user text inside the error message — strip before logging.

**Hard payload size cap: 8 KB.** Enforced in `PlatformEventService.emit()`. Over-size payloads are truncated and logged as a `platform_event.oversized_payload` error. This prevents accidentally logging large blobs (thread bodies, base64 images, full Stripe payloads) that would silently bloat the table. 8 KB is generous for structured event metadata; anything bigger is a design smell.

## 7. Request / session / job correlation

- **Backend HTTP requests**: middleware generates a UUID4 per incoming HTTP request, attached to `request.state.request_id`. All events emitted during that request inherit it automatically via the `PlatformEventService.emit()` helper.
- **Frontend**: tab-scoped `session_id` generated once per tab via sessionStorage. Emitted with every frontend event.
- **Background jobs / workers**: every invocation of a scheduled job (email poller run, nightly billing sweep, summary regeneration, backup, etc.) generates a `job_run_id` (UUID4) at the top of the run. All events emitted during that run inherit it. Lets you query "everything that happened in the 2026-04-18 nightly billing run." `request_id` and `job_run_id` are mutually exclusive in practice — the same event won't have both.
- **Idempotency**: every emit call generates a `client_emit_id`. On retry, the unique constraint `(organization_id, client_emit_id)` silently dedupes. Frontend emit batch retries + backend transient-failure retries both become safe.
- **Clock source**: server time (`created_at`) is authoritative. Frontend-sent events carry no timestamp of their own — the server records when it received them. Clock skew + client-clock spoofing ruled out by policy.
- **Cross-surface correlation**: backend events caused by a frontend action are NOT cross-correlated in v1 (no `client_event_id` passed through API calls). If this analysis need arises, add in a future phase.

## 8. Event catalog

Organized by subsystem. Each event specifies level and minimum expected `entity_refs`. Payload schema is given only when non-obvious.

### 8.1 Inbox / Email

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `thread.opened` | user_action | thread_id | User opened a thread in the inbox. |
| `thread.closed` | user_action | thread_id | User navigated away. Payload: `{duration_ms}`. |
| `thread.archived` | user_action | thread_id | Payload: `{prior_status}`. |
| `thread.deleted` | user_action | thread_id | Destructive — thread + all messages removed. Owner-only action. Payload: `{message_count, status_at_delete}`. Emitted BEFORE the delete so the audit trail survives. |
| `thread.snoozed` | user_action | thread_id | Payload: `{until_date}`. |
| `thread.unsnoozed` | system_action | thread_id | Background wake. |
| `thread.assigned` | user_action | thread_id, user_id, prior_assignee_user_id? | `user_id` = new assignee (may be null when unassigning). `prior_assignee_user_id` present when the thread had a prior assignee. Payload: `{}` (both user ids go in entity_refs per §6). |
| `thread.status_changed` | user_action \| system_action | thread_id | Payload: `{from, to, reason}`. |
| `thread.category_changed` | user_action | thread_id | Payload: `{from, to}`. User override of AI classification. |
| `thread.summarized` | agent_action | thread_id | Inbox summarizer wrote/refreshed summary. Payload: `{tokens_in, tokens_out, duration_ms, confidence, proposals_staged}`. |
| `thread.linked_to_case` | user_action \| system_action | thread_id, case_id | |
| `thread.unlinked_from_case` | user_action | thread_id, case_id | |
| `thread.resolved` | user_action \| system_action | thread_id | Thread reached a done state (handled/archived/closed). Payload: `{handled_by: ai_only \| ai_drafted_human_sent \| human_only, time_to_resolve_minutes}`. `handled_by` correctly attributes AI deflection — the core AI ROI metric for the inbox. |
| `thread.reopened` | user_action \| system_action | thread_id | Thread came back after being resolved. Quality KPI — catches "resolved too fast" failure mode. Payload: `{days_since_resolved, trigger: customer_reply \| manual}`. |
| `thread.sla_breached` | system_action | thread_id | SLA target exceeded. Payload: `{sla_class: priority \| standard \| vip, minutes_over, breach_point: first_response \| resolution}`. Enables pre-breach alerting. |
| `thread.first_response_sent` | user_action \| agent_action | thread_id, agent_message_id | First reply to the thread. Payload: `{response_time_minutes, by: human \| ai_approved}`. Foundational FRT metric. |
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
| `agent.output_edited` | user_action | varies | User edited an AI output before accepting. Payload: `{agent_type, edit_distance, chars_added, chars_removed, rounds_of_regeneration}`. Edit distance (Levenshtein or token-diff) is the quality signal — boolean edit/no-edit is not granular enough. |
| `agent.output_regenerated` | user_action | varies | User rejected an AI output and asked for another. Stronger dissatisfaction signal than accept-with-edits. Payload: `{agent_type, round_number, from_proposal_id?}`. |
| `agent.wrong_tool_selected` | user_action \| system_action | varies | DeepBlue / Sonar / tool-use agent picked a tool the user's action signals was wrong. Payload: `{agent_type, tool_called, user_recovery_action?}`. |
| `agent.context_truncated` | agent_action | varies | Input hit the Claude context window; content was chopped before the call. Silent quality killer otherwise invisible. Payload: `{agent_type, model, attempted_tokens, actual_tokens, truncation_target: prompt\|messages\|tools}`. |

### 8.4 Jobs (agent_actions table)

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `job.created` | user_action \| system_action \| agent_action | job_id, case_id?, thread_id? | Payload: `{job_type, source}` where source ∈ (manual, thread_ai, case_auto, proposal_accepted, deepblue_tool). |
| `job.status_changed` | user_action \| system_action | job_id | Payload: `{from, to, reason?}`. |
| `job.assigned` | user_action | job_id, user_id, prior_assignee_user_id? | `user_id` = new assignee. `prior_assignee_user_id` present when job had a prior assignee. Payload: `{}` (user ids live in entity_refs per §6). |
| `job.scheduled` | user_action \| system_action | job_id | Payload: `{scheduled_date, prior_date?}`. |
| `job.completed` | user_action | job_id, visit_id? | Payload: `{duration_days_since_created}`. |
| `job.cancelled` | user_action | job_id | Payload: `{reason?}`. |

### 8.5 Cases (service_cases)

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `case.created` | user_action \| system_action | case_id, customer_id? | Payload: `{source, linked_thread_count, linked_job_count}`. |
| `case.closed` | user_action \| system_action | case_id | Payload: `{reason, auto_closed: bool, cascade_jobs_closed}`. |
| `case.reopened` | user_action | case_id | Payload: `{cascade_jobs_reopened}`. |
| `case.manager_changed` | user_action | case_id, user_id?, prior_manager_user_id? | `user_id` ref = new manager's id (null when setting unassigned or when the manager isn't a QP user yet, e.g. just a name). `prior_manager_user_id` present iff the prior manager had a user id. Payload: `{prior_manager_name, new_manager_name}` — display-only denorm; user IDs stay in entity_refs per §6. |

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
| `estimate.conversion_funnel` | system_action (rollup) | — | Periodic rollup event capturing funnel conversion: sent → viewed → approved → converted-to-invoice, per org per week. Payload: `{week_start, sent, viewed, approved, converted, approval_rate_pct, median_time_to_approval_hours}`. |
| `invoice.days_to_paid` | system_action | invoice_id | Emitted on `invoice.paid`. Payload: `{days_to_paid, document_type, auto_pay}`. Derivable but emitting as a discrete event makes A/R trend analysis cheap. |

### 8.7 Visits / Chemistry

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `visit.started` | user_action | visit_id, property_id, user_id | Legacy "started" event — prefer the richer triple below for utilization metrics. |
| `visit.en_route.start` | user_action | visit_id, user_id | Tech heads to the property. First of three timestamps that let you compute drive time vs. wrench time. Payload: `{source: manual \| auto_geolocation}`. |
| `visit.on_site.start` | user_action | visit_id, property_id, user_id | Tech arrived on site. Payload: `{source: manual \| geo_match \| qr_scan, within_scheduled_window: bool}`. Coarse geotag only (on-site/off-site boolean, not continuous GPS) — see §6 privacy. |
| `visit.on_site.end` | user_action | visit_id, property_id, user_id | Tech left site. Payload: `{duration_minutes_on_site}`. Pair with `on_site.start` to compute wrench time. |
| `visit.completed` | user_action | visit_id, property_id | Payload: `{duration_minutes, tasks_completed, photos, readings, first_visit_resolution: bool}`. `first_visit_resolution=true` means no callback within N days was needed — derivable but emit explicitly for fast KPI queries. |
| `visit.cancelled` | user_action | visit_id | Payload: `{reason?}`. |
| `visit.revisit_required` | system_action \| user_action | visit_id, property_id | A follow-up visit was booked within N days of a completed visit for the same issue — "truck-roll waste" counter. Payload: `{days_since_prior_visit, prior_visit_id, reason_category?}`. |
| `chemical_reading.logged` | user_action \| agent_action | chemical_reading_id, water_feature_id, visit_id? | Payload: `{source: manual \| test_strip_vision \| deepblue}`. No chemistry values in payload (those are on the reading row). |
| `chemistry.reading.out_of_range` | agent_action \| system_action | chemical_reading_id, water_feature_id | A parameter (FC, CC, pH, TA, CYA, calcium, etc.) fell outside MAHC / CA Title 22 thresholds. Compliance event + anomaly signal. Payload: `{parameter, severity: warning\|critical\|closure_required, threshold_source: mahc\|title22\|custom}`. Values themselves live on the reading row, not the event. |
| `chemistry.dose.applied` | user_action | chemical_reading_id, water_feature_id, visit_id? | A chemical dose was applied. Payload: `{chemical_type, expected_delta_ppm, prior_reading_id?}`. Pair with next reading to compute actual-vs-expected delta (→ tech dosing accuracy + SWG/cell health). |
| `chemistry.dose.expected_vs_actual` | system_action | chemical_reading_id, water_feature_id, user_id? | Periodic rollup — after the next reading is logged, compute expected-vs-actual delta. `user_id` ref = the tech who dosed (null if unknown). Payload: `{chemical_type, expected_delta, actual_delta, prior_dose_event_id}`. Training signal for dosing agent + QC flag. User id moved to entity_refs per §6. |
| `photo.uploaded` | user_action | property_id, visit_id?, water_feature_id? | Payload: `{purpose: measurement \| before_after \| issue_report \| test_strip, size_kb}`. |

### 8.8 Customers / Properties / Equipment

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `customer.created` | user_action \| system_action \| agent_action | customer_id | Payload: `{source}`. |
| `customer.edited` | user_action | customer_id | Payload: `{fields_changed: [...]}`. Field names only, no values. |
| `customer.status_changed` | user_action | customer_id | Payload: `{from, to}`. |
| `customer.cancelled` | user_action | customer_id | Customer relationship ended. Payload: `{reason_code: price \| moved \| dissatisfaction \| sold_property \| seasonal \| other, notes?: short_whitelist}`. Structured reason codes are non-negotiable — churn analysis is impossible without them. |
| `customer.recurring_service_paused` | user_action | customer_id | Distinct from cancellation. Seasonality (pool closure in winter) is a major pool-industry factor. Payload: `{expected_resume_date?, reason?}`. |
| `customer.recurring_service_resumed` | user_action | customer_id | Pair with `paused` to measure seasonal pause durations per segment. |
| `customer.recurring_service_skipped` | user_action | customer_id | One-off skip (vs. multi-visit pause). Payload: `{visit_date_skipped, reason?}`. |
| `customer_contact.created` | user_action | customer_id | Payload: `{role?, is_primary}`. |
| `customer_contact.edited` | user_action | customer_id | Payload: `{fields_changed: [...]}`. |
| `property.created` | user_action | property_id, customer_id | |
| `property.edited` | user_action | property_id | Payload: `{fields_changed: [...]}`. |
| `water_feature.created` | user_action | water_feature_id, property_id | Payload: `{water_type}` — matches the `water_features.water_type` column (pool \| spa \| hot_tub \| wading_pool \| fountain \| water_feature). QP does not track a primary-water-feature column; if added later, emit `{water_type, is_primary}`. |
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
| `platform_event.oversized_payload` | error | — | Emit helper truncated an over-8KB payload. Payload: `{original_event_type, attempted_size_bytes, truncated: true}`. Flags taxonomy violations so we find them. |

### 8.12b Meta / platform lifecycle

Events emitted by the platform itself about its own housekeeping. Rare but useful for ops monitoring.

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `system.partition.created` | system_action | — | APScheduler's partition_manager created next month's `platform_events_YYYY_MM` partition. Payload: `{partition_name, range_start, range_end}`. `organization_id` is null (platform-level). |
| `system.retention_purge.completed` | system_action | — | Daily retention-purge run finished. Payload: `{orgs_processed, rows_purged_total, duration_ms}`. `organization_id` is null (aggregated across orgs). |

### 8.13 Activation funnel (org-scoped milestones)

The SaaS "time-to-value" funnel. Each event fires once per org, first time the milestone is hit. Rollups feed onboarding dashboards and TTV measurement.

| Event | Level | Expected entity_refs | Notes |
|---|---|---|---|
| `activation.account_created` | user_action | user_id | First user registered for the org. Payload: `{signup_method, referrer?, minutes_from_landing}`. |
| `activation.first_customer_added` | user_action | customer_id, user_id | Payload: `{minutes_since_account_created, source: manual \| import}`. |
| `activation.first_visit_completed` | user_action | visit_id, user_id | Payload: `{minutes_since_first_customer, tech_user_id}`. |
| `activation.first_invoice_sent` | user_action | invoice_id, user_id | Payload: `{minutes_since_first_visit, document_type}`. |
| `activation.first_payment_received` | user_action \| system_action | invoice_id | Payload: `{minutes_since_first_invoice_sent, method}`. |
| `activation.first_ai_proposal_accepted` | user_action | agent_proposal_id, user_id | First time the org accepts an AI suggestion — the "aha moment" for the AI pillar specifically. |

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

## 13. Relationship to `agent_corrections`

After Phase 2 ships, two tables will record AI outcomes: `platform_events` (via `proposal.accepted` / `.edited_and_accepted` / `.rejected`) and the existing `agent_corrections` (AgentLearningService's per-agent correction rows). These are **not duplicates**. They serve different consumers:

- `platform_events` — raw event stream, org-wide analytics, Sonar queries, timeline reconstruction, debugging. Retention-bounded per the retention policy. Read by many consumers.
- `agent_corrections` — specialized projection for the learning-prompt builder (`AgentLearningService.build_lessons_prompt`). Optimized query shape: `WHERE agent_type = ? AND customer_id = ? ORDER BY created_at DESC LIMIT 10`. Retained longer (learning improves with long tail). Read by the agent runtime on every generation.

Both rows are written atomically on proposal resolution — same transaction. Do NOT consolidate them. They answer different questions with different access patterns.

## 14. Backfill of historical data (Phase 1 one-time migration)

On Phase 1 launch, we run a one-time migration that derives `platform_events` rows from existing tables. This gives workflow-observer and Sonar a running start instead of a multi-week data silence.

**Entities to backfill:**

| Source table | Derived events | Timestamp source |
|---|---|---|
| `agent_actions` (jobs) | `job.created` | `created_at` |
| `agent_actions` status history | `job.status_changed` | best effort; may be coarse if no history table |
| `visits` | `visit.started`, `visit.completed`, `visit.cancelled` | respective columns |
| `invoices` | `invoice.created`, `invoice.sent`, `invoice.paid`, `invoice.voided` | respective columns |
| `invoices` (estimates) | `estimate.approved`, `estimate.declined` | if approval records exist |
| `agent_threads` | `agent_message.received`, `thread.status_changed` (derived) | first message + status transitions |
| `agent_messages` | `agent_message.sent` (outbound), `agent_message.received` (inbound) | `created_at` + direction |
| `customers` | `customer.created`, `customer.cancelled` (if inactive) | `created_at` / status change |
| `service_cases` | `case.created`, `case.closed` (if closed) | respective columns |
| `chemical_readings` | `chemical_reading.logged` | `created_at` |
| `agent_corrections` | `agent.output_edited` / `.rejected` (derived) | `created_at` |
| `feedback_items` | `feedback.submitted` (add to catalog if not present) | `created_at` |

**Fidelity notes:**
- Backfilled events carry `actor_type: 'system'`, `actor_user_id: null`, `source: 'backfill'` in payload, `client_emit_id: null` (not subject to dedup).
- Where the original action's actor is recorded on the source row (e.g., `created_by`), we populate `actor_user_id` if we can resolve it.
- Payloads are sparse — we reconstruct what we can, not what we want.
- `visit.en_route.start` / `on_site.start` / `on_site.end` are NOT backfilled (we didn't track them before). The backfilled `visit.started` / `.completed` approximate.

**Backfill is idempotent**: the script checks for existing backfilled events (by `source: 'backfill'` + entity_refs) and skips duplicates. Safe to re-run if the first run crashed partway.

Script lives in `app/scripts/backfill_platform_events.py`. Runs once at Phase 1 cutover. Update the Phase 1 spec with the cutover procedure.

## 15. Test strategy for instrumentation

Phase 1 done means this testing pattern exists AND at least 5 subsystems have integration tests using it.

**Unit tests:**
- `PlatformEventService` has unit tests for emit (happy path, oversized payload truncation, idempotency on duplicate `client_emit_id`, buffered-path behavior when DB is unavailable).

**Fixtures:**
- `tests/fixtures/event_recorder.py` — pytest fixture that captures all events emitted during a test into an in-memory list. Provides assertions like `event_recorder.assert_emitted("thread.archived", entity_refs={"thread_id": "..."})`.

**Integration tests (minimum 5 subsystems):**
- Inbox: receive inbound email → assert `agent_message.received`, `thread.summarized`, `agent_message.classified`, `agent_message.customer_matched` events all present with expected refs.
- Job lifecycle: create job from thread → assign → complete → assert `job.created`, `job.assigned`, `job.completed`, plus `visit.*` subset if a visit was created.
- Estimate: draft estimate → send → customer approves → convert to invoice → assert the full funnel event sequence.
- Chemistry: log reading with out-of-range value → assert `chemical_reading.logged` + `chemistry.reading.out_of_range`.
- Auth: successful login → failed login → password reset → assert the three-event sequence.

**CI enforcement:**
- A lint-style test asserts that every mutation method in `src/services/` calls `PlatformEventService.emit()` at least once (or is explicitly allowlisted). Prevents silent regressions where new code doesn't instrument.

## 16. Phase 1 Definition of Done

Phase 1 is done when ALL of the following are true:

1. `platform_events` table exists with monthly partitioning; next-month partition automation running.
2. `organizations.event_retention_days` column exists and defaults are set (dogfood 10y, paying 3y).
3. `PlatformEventService.emit()` implemented with: idempotency check, 8KB payload cap, fail-soft error handling, buffered-fallback pattern.
4. Backend middleware emits `request_id` and propagates it via `request.state`.
5. Frontend `lib/events.ts` batching client implemented.
6. Backfill migration script (`backfill_platform_events.py`) written, tested on a copy of dogfood data, and run at cutover.
7. Daily retention-purge job implemented.
8. Purge-on-request endpoint (`POST /v1/admin/users/{id}/purge-events`) implemented + tested.
9. Every subsystem listed in §10 is emitting its documented events — verified by the CI lint test + manual walk of 10 real workflows.
10. Integration tests exist for at least 5 subsystems using `event_recorder` fixture.
11. Query `SELECT count(*), event_type FROM platform_events WHERE organization_id = :sapphire GROUP BY event_type` returns a distribution consistent with a day of normal Sapphire usage (not a suspiciously thin or missing category).

## 17. Open items (not blocking Phase 1, revisit at scale)

- Event sampling policy for high-volume event types (page views) once one org crosses 1M events/month.
- Cross-correlation between frontend and backend events (frontend `client_event_id` passed through API headers, backend includes it in emitted events).
- Shipping platform_events data to a warehouse (BigQuery/Snowflake) when multi-year analytics queries become slow on operational Postgres.
- Auto-derived events: Sonar asks "when did the user first use feature X" — could be a derived view rather than an emitted event.
- Event versioning (`event_version` field): if we ever need breaking payload changes. Avoid by staying additive-only.

These are deliberately deferred. Document now, implement later.
