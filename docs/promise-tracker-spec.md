# Promise Tracker — refinement spec

> Closes the gap left by the outbound-invisible rule when a customer says "I'll get back to you" and we reply. Builds directly on the `_is_followup_promise()` regex shipped 2026-04-27 alongside the no_response classifier guardrail. Remove this file when v1 is shipped + archived.

## 1. Purpose

When a customer commits to a future reply, the orchestrator already keeps the inbound thread in Pending (the followup-promise guardrail). But once Brian/Kim respond, `last_direction` flips to outbound and the thread is hidden by the outbound-invisible rule. If the customer never actually follows up, the conversation dies in silence.

Real Sapphire example: Kaitlyn (Madison Apartments) said "I have sent the request to my higher-up and will keep you posted." Kim replied. Thread is now hidden. If Kaitlyn never circles back, we lose track.

Phase 1 ships the minimum viable piece: a per-thread "awaiting customer reply" timer that re-surfaces stale-promise threads on a dashboard widget for owner+admin.

## 2. DNA alignment

- **Less work for the user** (rule 6): converts a manual "remember to follow up" into a passive surface.
- **AI never commits to customer** (rule 5): unaffected — this is purely about visibility, not auto-replies. Any nudge still flows through the existing AI-drafts-human-sends path.
- **Build for the 1,000th customer** (rule 1): every B2B pool service has property managers who delay. This is universal, not Sapphire-specific.
- **Every agent learns** (rule 2): minor — observed user actions (resolved vs. extended vs. ignored) feed AgentLearningService for `followup_promise_detector` so the regex can grow over time.

## 3. Scope

### In scope (v1)
- New column `agent_threads.awaiting_reply_until` (timestamptz, nullable). NULL means "not waiting" — the thread behaves exactly as today.
- Orchestrator hook: when an inbound message matches `_is_followup_promise(body)` AND sender_is_customer, set `awaiting_reply_until = NOW() + 7 days`. Idempotent — re-extends if already set.
- Auto-clear hook: when ANY new inbound message lands on a thread with `awaiting_reply_until` set, clear the field. The customer replied; the wait is over.
- API:
  - `GET /v1/inbox/awaiting-reply` — list threads where `awaiting_reply_until` is set, with `is_overdue` flag (true when due ≤ now). Owner+admin only via existing `inbox.manage`.
  - `PUT /v1/admin/agent-threads/{id}/awaiting-reply` — body `{until: iso datetime | null}`. Manual set (set a custom date), extend (snooze), or clear (resolved). Idempotent.
- Frontend: dashboard widget "Awaiting customer reply" — shows up to 5 stale-promise threads (`awaiting_reply_until <= NOW()`) with one-click "Open thread" + "Snooze 7 days" + "Resolved (no reply needed)" actions. Hidden when empty.
- Stale banner integration: the existing inbox stale-banner counts grow to include `stale_promise` count; the banner shows two bullets ("12 stale pending · 3 awaiting customer 7+ days") when both apply.

### Out of scope (deferred)
- Push notification (ntfy) on stale-promise threshold cross. Dashboard widget is sufficient v1; ntfy can subscribe to the `agent_proposal.staged` event family later if needed.
- Per-org configurable window (currently hardcoded 7 days). When the workflow_observer (Phase 6) collects 6+ weeks of data, it can stage a `workflow_config` proposal to adjust per-org.
- AI-suggested nudge drafts for stale-promise threads. The existing email_drafter already handles drafts on inbound; if Brian wants to *initiate* a nudge from this widget, the click would route to `/inbox/{thread_id}?compose=1` and let him draft manually for v1.
- Detection beyond the regex. The regex catches the explicit cases. Subtler "we'll discuss internally" patterns can grow the regex (same fix path as the original guardrail).

## 4. Architecture

### 4.1 Schema

```python
# Migration: add_awaiting_reply_until_to_agent_threads
op.add_column(
    "agent_threads",
    sa.Column("awaiting_reply_until", sa.DateTime(timezone=True), nullable=True),
)
op.create_index(
    "ix_agent_threads_awaiting_reply_until",
    "agent_threads",
    ["awaiting_reply_until"],
)
```

Indexed because the dashboard widget queries `WHERE awaiting_reply_until <= NOW()` and we want it cheap.

### 4.2 Orchestrator hook (set the timer)

In `process_incoming_email`, after the existing classification + customer-match flow, before the auto-handle decision tree, add:

```python
from datetime import timedelta
PROMISE_WINDOW_DAYS = 7

if (
    msg.direction == "inbound"
    and sender_is_customer
    and _is_followup_promise(body or "")
):
    thread.awaiting_reply_until = datetime.now(timezone.utc) + timedelta(days=PROMISE_WINDOW_DAYS)
```

Run this regardless of the classifier's category (a "I'll get back to you" still gets the timer even if classified as `general` or `service_request`).

### 4.3 Auto-clear hook

Same orchestrator function, after the message is created and the thread is identified:

```python
if (
    msg.direction == "inbound"
    and thread.awaiting_reply_until is not None
    and not _is_followup_promise(body or "")  # if THIS message is itself a promise, leave the timer; the new set hook will overwrite it
):
    thread.awaiting_reply_until = None
```

Order: the auto-clear runs FIRST (clear the old wait), then the set hook runs (re-set if the new message is itself a promise). Both can fire on the same message — clear ack of "Got it, ok" then re-set "I have sent the request to my higher-up." But actually since `_is_followup_promise` returns True for the new promise, we don't want to clear it. So the hooks should be: if NEW message is a promise → set/extend (overrides any existing); if NEW message is NOT a promise → clear (customer responded normally).

Cleaner single-pass logic:

```python
if msg.direction == "inbound":
    if _is_followup_promise(body or "") and sender_is_customer:
        thread.awaiting_reply_until = datetime.now(timezone.utc) + timedelta(days=PROMISE_WINDOW_DAYS)
    elif thread.awaiting_reply_until is not None:
        thread.awaiting_reply_until = None  # they responded, wait is over
```

Outbound messages (our replies) don't touch the timer — the customer's promise is still pending.

### 4.4 API

#### `GET /v1/inbox/awaiting-reply`

Owner+admin (gated by `inbox.manage`). Returns:

```json
{
  "items": [
    {
      "thread_id": "...",
      "subject": "Re: The Madison...",
      "contact_email": "madisonmgr@greystar.com",
      "customer_name": "Grey Star",
      "awaiting_reply_until": "2026-05-04T15:00:00Z",
      "is_overdue": false,
      "last_message_at": "2026-04-27T15:00:00Z",
      "last_inbound_snippet": "I have sent the request to my higher-up..."
    }
  ],
  "stale_count": 3
}
```

`stale_count` = items where `awaiting_reply_until <= NOW()`. Used by the dashboard widget to badge the count.

#### `PUT /v1/admin/agent-threads/{id}/awaiting-reply`

Body: `{until: ISO8601 string | null}`. Sets/extends/clears. Owner+admin via `inbox.manage`.

Three semantic shapes:
- `{until: "2026-05-15T..."}` — snooze (extend window)
- `{until: null}` — resolved (clear timer)
- (No need for "set initial" via API — the orchestrator handles auto-set; this endpoint is purely for manual override)

### 4.5 Frontend dashboard widget

`<AwaitingReplyWidget>` component on `/dashboard`, beside the existing widgets. Renders nothing for users without `inbox.manage`. Shows up to 5 stale-promise rows; "View all (N)" link when more.

Each row:
- Customer/sender + subject preview
- Days since promise
- 3 actions: **Open** (link to /inbox?thread=...), **Snooze 7d** (PUT endpoint), **Resolved** (PUT endpoint with null)
- Snooze and Resolved are one-click; no confirmation modal (low-stakes, reversible from the inbox row).

Empty state: hidden entirely (no card shows when no threads are stale).

### 4.6 Inbox surface integration (light touch)

The existing inbox stale banner currently shows "X stale pending" when `stats.stale_pending > 0`. Extend the banner copy to also mention promise-stale count when present:

> "12 stale pending · 3 awaiting customer 7+ days"

Banner stays a single dismissible row. Clicking it switches to the existing stale view; awaiting-reply view is the dashboard widget for now.

Per-row badge in the thread list: optional. Threads where `awaiting_reply_until IS NOT NULL` get a small "⏳" or "Awaiting" pill in the badge order (after Stale, before AI). v1 can ship without the row badge; the dashboard widget covers the high-attention case.

## 5. Decisions made (no questions)

- **Window: 7 calendar days**. Configurable later (per workflow_observer). Hardcoded constant in orchestrator.
- **Permission gate: `inbox.manage`** (existing slug). No new slug needed.
- **No APScheduler job**. The dashboard widget queries on render; no background work required.
- **Auto-clear on any subsequent inbound** (not just non-promise inbound). If they send a follow-up that ALSO contains a promise ("Hi, still waiting on legal — will update next week"), the new set hook overrides correctly via the if/elif structure.
- **No notification v1**. Brian sees stale-promise threads on the dashboard. Push can be added later by wiring `agent_thread.awaiting_reply_set` event → ntfy via existing inbox-rules.
- **Hardcoded regex**, no per-org tuning v1. The regex is in the orchestrator alongside the `_FOLLOWUP_PROMISE_RE` from the no_response guardrail. Both grow together as patterns surface.

## 6. Rollout steps (8)

1. Migration: `awaiting_reply_until` column + index.
2. Model: `AgentThread.awaiting_reply_until` mapped column. Update Phase 4 / inbox queries that select all thread fields.
3. Orchestrator hook: set/clear logic in `process_incoming_email`. Tests using synthetic messages (existing `_is_followup_promise` tests already cover the regex).
4. Service helper: `AwaitingReplyService.list(org_id)` that returns threads with timer set + the `is_overdue` flag.
5. API: `GET /v1/inbox/awaiting-reply` + `PUT /v1/admin/agent-threads/{id}/awaiting-reply`. Tests for happy path, permission gate, idempotency.
6. Frontend: `AwaitingReplyWidget` component on `/dashboard`. Renders with empty/loading/error states. Reuse the existing snooze pattern.
7. Stale banner copy update: integrate `stale_promise` count into the existing stale banner.
8. Backfill: one-shot script that sweeps recent inbound messages, runs `_is_followup_promise()`, and sets `awaiting_reply_until` for matching threads where the most recent message is the promise (so we don't mis-set on threads that already cycled).

## 7. Definition of done

- [ ] Migration applied; column + index visible.
- [ ] `AgentThread.awaiting_reply_until` mapped + serialized in thread responses.
- [ ] Orchestrator hook fires correctly: set on inbound promise, cleared on subsequent inbound.
- [ ] `GET /v1/inbox/awaiting-reply` returns expected shape + permission-gated.
- [ ] `PUT .../awaiting-reply` covers set/snooze/clear; idempotent on re-clear.
- [ ] Dashboard widget renders the 5 most-stale rows; Open/Snooze/Resolved all functional.
- [ ] Stale banner shows promise count when nonzero.
- [ ] Backfill on Sapphire correctly identifies the Madison Apartments + similar threads (verify against the `outbound-last + customer-known + last inbound has promise` query from the audit — should be N>0 threads).
- [ ] Frontend tests pass; backend tests pass; smoke import clean.
- [ ] Memory: `feedback_followup_promise_not_no_response.md` updated with a "promise tracker shipped" note.

## 8. Estimated scope

~2.5–4 working days:
- Migration + model + serializer: 0.5 day
- Orchestrator hook + tests: 0.5 day
- AwaitingReplyService + API + tests: 0.5–1 day
- Dashboard widget + stale banner update: 1 day
- Backfill script + Sapphire pass: 0.5 day

## 9. Open questions (none load-bearing)

- Should "Snooze 7 days" use a per-thread snooze counter to avoid infinite-snooze patterns? V1 says no — Brian can resolve any time. If user behavior shows abuse later, add a counter + auto-resolve at N snoozes.
- Should the backfill script's window be 30 days or all time? Phase 1: last 30 days only. Anything older has gone stale either way; surfacing it would be noise.
