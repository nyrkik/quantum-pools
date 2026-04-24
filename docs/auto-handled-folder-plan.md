# Auto-Handled Folder + Thread-Status Cleanup Plan

> **Removal note:** Delete this doc and its CLAUDE.md index entry when the cleanup is shipped and verified. Persistent facts (new `thread.status` contract, `auto_handled_at` semantics, `ai_review` folder) get merged into `docs/data-model.md` and `docs/email-pipeline.md` in the ship commit.

## 1. Purpose

An email from Google Workspace (legitimate, informational) was auto-handled by the classifier and became invisible in the main Inbox — reachable only via the admin-only `Auto` segmented filter or the `All Mail` escape hatch. The user reported this as a real miss risk: "doesn't show up with the All filter. we need to assess this process. seems like a real potential to miss important emails."

Root cause is a data-model conflation in `thread_manager.update_thread_status` (`app/src/services/agents/thread_manager.py:134`):

```python
thread.status = "pending" if has_pending else ("handled" if has_sent else "ignored")
```

`has_sent` only checks for outbound `sent`/`auto_sent` messages. When the classifier auto-handles an inbound message *without* sending a reply (informational mail: billing notices, Workspace alerts, marketing), no outbound exists → thread gets `status="ignored"` → the default Inbox query filters it out via `exclude_ignored=true`.

`thread.status` today encodes two questions in one field:
1. "Does this need human attention?" (pending vs. done)
2. "Did we send a reply?" (handled vs. ignored)

Those are orthogonal. This plan splits them.

**DNA alignment:**
- **Rule 2 — every agent learns:** the `auto_handled_feedback_at` ack loop already exists; this plan surfaces it where humans will actually use it, making the classifier's correction signal work in practice.
- **Rule 3 — product learns the org:** `ai_review` folder's badge count is itself a behavioral signal. A steadily growing badge → the classifier is auto-handling too aggressively for this org's mail mix.
- **Rule 6 — less work for the USER:** fixes the missed-email risk without adding clicks. Folder + badge is a persistent peripheral signal; admins don't have to remember to click a segment.

## 2. Environment facts (verified 2026-04-24)

- `AgentThread.auto_handled_feedback_at` column **already exists** (`app/src/models/agent_thread.py:48`) for the human-ack side of AI auto-closes. The write-side timestamp (`auto_handled_at`) does not.
- System folders use `inbox_folder.system_key` per `docs/inbox-folders-plan.md` Phase 1 (shipped). Current keys: `inbox`, `sent`, `spam`, `outbox`, `all_mail`, `historical`. Virtual folders (Sent, Outbox, All Mail) have no rows; folder views are query-shaped.
- Auto segment today: `status="auto_handled"` API param, translated in `agent_thread_service.py:179-188` to `status IN ("ignored", "handled") AND has_pending=False AND no auto_sent`. Admin-only via `canManageInbox` / `inbox.manage` gate.
- Default Inbox query (`agent_thread_service.py:222-235`): applies `status != "archived"` + `(last_direction=inbound OR has_pending)` + `exclude_ignored` → `status != "ignored"` + `exclude_spam` → `category NOT IN ("spam","auto_reply")`.
- Orchestrator auto-handle paths: (a) `category="general"` + no draft + not customer (`orchestrator.py:584-613`), (b) `category IN ("spam","auto_reply","no_response","thank_you")` after first-contact guardrail (`orchestrator.py:615-703`). Both write `AgentMessage.status="handled"` and then call `update_thread_status`.
- Spam/auto_reply auto-handle also moves the thread's `folder_id` to the Spam system folder (`orchestrator.py:687-701`). Those are findable in Spam; they're not the visibility risk. The risk is `no_response` / `thank_you` / "general-no-draft" auto-handles that stay in Inbox folder but get `thread.status="ignored"`.

## 3. What this plan ships

- **DDL:** new column `agent_threads.auto_handled_at TIMESTAMP NULL`, indexed.
- **Service rewrite:** `update_thread_status` derivation changes so auto-handled inbound yields `thread.status="handled"` (not `"ignored"`).
- **Orchestrator write:** every auto-handle code path sets `thread.auto_handled_at = now()` at the moment of auto-close.
- **Query audit + fixes:** every site that filters on `status="ignored"` or uses `exclude_ignored` — audited, adjusted to the new semantics.
- **Migration:** backfill existing `thread.status="ignored"` rows that were actually AI auto-closes → set `status="handled"` + `auto_handled_at`. Rows that are genuinely user-archived stay as-is (separated via heuristic; see §6).
- **New virtual folder `ai_review`:** sidebar folder for owner+admin that shows unreviewed AI auto-closes. Amber badge. Virtual (query-shaped), like Sent / Outbox.
- **Drop the Auto segment** from `InboxFilters`. The segmented control becomes `[All | Pending | Handled]` for everyone. "AI Review" moves to the sidebar folder.
- **Non-admins see auto-handled threads in the regular Handled segment** (their first-ever visibility into AI's work). No ack flow for non-admins; they're read-only on AI decisions.
- **Event:** `thread.auto_handled` (new) — emitted on each auto-close so the Phase-1 AI platform pipeline can aggregate "how often is this org auto-handling" signal. Document in `docs/event-taxonomy.md` in the same commit.
- **Tests:** pytest for `update_thread_status` under all four paths (auto-handled inbound / human-replied / still-pending / user-archived); Vitest for `InboxFolderSidebar` rendering the `ai_review` folder with a badge; integration test for the orchestrator's auto-handle → thread-status flow.

## 4. Data model

### 4.1 DDL

```sql
ALTER TABLE agent_threads
  ADD COLUMN auto_handled_at TIMESTAMP WITH TIME ZONE NULL;

CREATE INDEX ix_agent_threads_auto_handled_at
  ON agent_threads (auto_handled_at)
  WHERE auto_handled_at IS NOT NULL;
```

Partial index: the `ai_review` folder query only cares about non-null values.

### 4.2 New derivation in `update_thread_status`

```python
has_pending   = any(m.status == "pending" for m in msgs)
has_sent      = any(m.status in ("sent", "auto_sent") for m in msgs)
has_inbound_handled = any(
    m.direction == "inbound" and m.status == "handled" for m in msgs
)
has_outcome   = has_sent or has_inbound_handled

if has_pending:
    thread.status = "pending"
elif has_outcome:
    thread.status = "handled"
else:
    thread.status = "archived"  # fallback — shouldn't be reachable in normal flow
```

`ignored` is no longer a derived state. It becomes reachable only via explicit user action (see §5.2).

`thread.auto_handled_at` is **not** set here. It's set at the orchestrator's auto-handle decision point, which is the only place with visibility into "AI made this call without human input." Once set, it never clears; the ack loop uses `auto_handled_feedback_at` as the separate "human reviewed it" axis.

### 4.3 The new two-axis model

| `status` | `auto_handled_at` | `auto_handled_feedback_at` | Where it shows |
|----------|-------------------|-----------------------------|----------------|
| `pending` | NULL | NULL | Inbox (default + Pending segment) |
| `handled` | NULL | n/a | Inbox Handled segment (human-handled) |
| `handled` | set | NULL | **AI Review folder** + Handled segment |
| `handled` | set | set | Handled segment only (ack'd) |
| `archived` | any | any | All Mail only |

## 5. Service layer

### 5.1 Orchestrator — all auto-handle write sites

`app/src/services/agents/orchestrator.py` has two auto-handle branches:

1. **General + no draft + not customer** (`orchestrator.py:584-613`) — write `thread.auto_handled_at = now()` before commit.
2. **Spam / auto_reply / no_response / thank_you** (`orchestrator.py:615-703`) — same: set `auto_handled_at` on the thread. Spam/auto_reply branch still moves `folder_id` to Spam folder (unchanged). For these, the AI Review folder is a secondary view that *also* matches them (query is purely by `auto_handled_at IS NOT NULL`); they surface in both Spam and AI Review until ack'd. Admin can ack from either surface.

Also emit `thread.auto_handled` event (new, document in `event-taxonomy.md`) with payload `{thread_id, category, matched_customer_id, classifier_confidence}`. Non-blocking; wrapped in try/except per the project's event discipline.

### 5.2 `list_threads` audit

Every branch in `agent_thread_service.list_threads` (`app/src/services/agent_thread_service.py`):

| Line | Current | After |
|------|---------|-------|
| L114 (escape-hatch branches: `historical`, `all_mail`, `all`) | No status filter | Unchanged — escape hatches still show everything |
| L171 (`status="stale"`, `status="pending"`) | `has_pending=True` | Unchanged |
| L179-188 (`status="auto_handled"`) | `status IN ("ignored","handled") + has_pending=False + no auto_sent` | **Rewrite:** `auto_handled_at IS NOT NULL AND auto_handled_feedback_at IS NULL`. Now the `ai_review` folder's query. |
| L216 (`status="handled"`) | `status = "handled"` | Unchanged — after the derivation fix, this naturally includes auto-handled + human-handled. Non-admin's path to seeing AI's work. |
| L218 (`status="ignored"`) | `status = "ignored"` | **Narrows:** only returns explicitly-user-archived threads. After migration, expected near-empty set. Kept for API compat. |
| L221 (`status="archived"`) | `status = "archived"` | Unchanged |
| L222-229 (default inbox shape) | `status != "archived" + (inbound OR has_pending)` | Unchanged. After derivation fix, auto-handled threads have `status="handled"` and no longer hit `has_pending=True`, so they naturally drop out of the default view. Good. |
| L234 (`exclude_ignored`) | `status != "ignored"` | **Remove callers.** The default Inbox no longer needs this — derivation fix makes auto-handled naturally absent. `exclude_ignored` query param stays for backward compat but becomes a no-op in practice. |

### 5.3 `get_thread_stats`

`auto_handled_today` count (`agent_thread_service.py:483`) gets rewritten:

```python
auto_handled_today = (await self.db.execute(
    select(func.count(AgentThread.id)).where(
        AgentThread.organization_id == org_id,
        AgentThread.is_historical == False,
        AgentThread.auto_handled_at.isnot(None),
        AgentThread.auto_handled_feedback_at.is_(None),
        AgentThread.auto_handled_at >= (now - 24h),
    )
)).scalar()
```

Add a new stat `ai_review_count` = **total** unreviewed auto-handled (not time-scoped) — this is the folder's badge count.

### 5.4 Folder listing (`inbox_folder_service.list_folders`)

The `ai_review` folder is virtual. Either:

- **Option A (preferred):** treat it like Sent/Outbox — the folder-listing endpoint synthesizes an `ai_review` entry for owner+admin users only, with count derived from the stats query above. No DB row.
- **Option B:** seed an actual `inbox_folders` row with `system_key="ai_review"` for backward symmetry. More consistent with existing system folders. Costs a one-line seed migration. Recommend this for simplicity.

Go with B. Seed `system_key="ai_review"`, icon `bot` or `brain-circuit`, sort_order after Inbox. The listing query joins through `auto_handled_at` instead of through `folder_id` when returning the count for this folder.

## 6. Migration

One-shot script `app/scripts/migrate_auto_handled_status.py` (not an Alembic migration — data backfill, idempotent, can be re-run):

```python
# Reclassify threads that were AI auto-handled but got stuck as "ignored"
# Heuristic: any inbound AgentMessage with status="handled" + no outbound ever sent
# + not historical → reclassify thread status + set auto_handled_at from the
# inbound message's received_at.

UPDATE agent_threads t
SET status = 'handled',
    auto_handled_at = (
      SELECT MIN(m.received_at) FROM agent_messages m
      WHERE m.thread_id = t.id AND m.direction = 'inbound' AND m.status = 'handled'
    )
WHERE t.status = 'ignored'
  AND t.is_historical = FALSE
  AND EXISTS (
    SELECT 1 FROM agent_messages m
    WHERE m.thread_id = t.id AND m.direction = 'inbound' AND m.status = 'handled'
  )
  AND NOT EXISTS (
    SELECT 1 FROM agent_messages m
    WHERE m.thread_id = t.id AND m.direction = 'outbound' AND m.status IN ('sent','auto_sent')
  );
```

Rows that don't match (genuine user-archives, spam manually routed) keep `status="ignored"`.

Backfill does **not** set `auto_handled_feedback_at` — all backfilled threads appear in the AI Review folder. Gives the admin a one-time catch-up pass. Acceptable; the folder will settle once ack'd.

Dry-run mode (`--dry-run`) prints counts without writing.

Sapphire baseline expectation: the AI Review folder will have a large initial count (every historical informational auto-handle). Document this in the rollout communication so it's not alarming.

## 7. Frontend

### 7.1 Sidebar

`frontend/src/components/inbox/inbox-folder-sidebar.tsx` (or wherever the folder list renders) — add `ai_review` to the system-folder section, conditionally on `perms.can("inbox.manage")`. Badge count from `stats.ai_review_count`, amber (`text-amber-600 bg-amber-50`) to distinguish from Outbox red and Inbox navy.

Icon: lucide `Bot` or `BrainCircuit`. Pick one consistent with the sender-tag set already in use.

### 7.2 `InboxFilters` rewrite

`frontend/src/components/inbox/inbox-filters.tsx`:

- Remove `Auto` option entirely from the `StatusSegmented` options array.
- Remove `autoHandledTodayCount` prop and `canManageInbox` prop from `InboxFilters` (still needed elsewhere; just not in the filter row).
- Segmented control becomes `[All | Pending | Handled]` for every role.

`frontend/src/app/(dashboard)/inbox/page.tsx`:
- Drop the `statusFilter === "auto_handled"` branch in `loadThreads` (line 224). Replaced by the folder-path.
- Drop the `exclude_ignored=true` param from the default Inbox request — now a no-op server-side after derivation fix, but cleaner to stop sending it.

### 7.3 Folder page

Clicking `ai_review` folder in the sidebar sets `selectedFolderKey = "ai_review"`. Backend `list_threads` with `folder=ai_review` returns threads matching the new query (`auto_handled_at IS NOT NULL AND auto_handled_feedback_at IS NULL`). The reading pane's existing Yes/No ack banner stays — clicking Yes sets `auto_handled_feedback_at`, thread drops from folder.

### 7.4 Handled segment row pill

In Handled segment, auto-handled threads get a small muted "AI" pill in the badge row (spec: after Status badge, before Stale). Non-admins see it too — informational only, no action. Uses the existing badge-order rule from CLAUDE.md: Sender tag → Category → Status → **AI** → Stale.

## 8. Rollout

1. DDL migration (Alembic) — add `auto_handled_at` column + index.
2. Data migration (one-shot script) — dry-run first, report counts, then commit.
3. Seed `ai_review` system folder for every org.
4. Ship `update_thread_status` derivation fix + orchestrator write sites + `list_threads` audit + stats endpoint update. Single backend deploy.
5. Ship frontend: sidebar folder render + filter row simplification + page.tsx branch removal. Single frontend deploy.
6. Verify on Sapphire: AI Review folder populated, badge shows count, clicking a thread + ack'ing decrements, Handled segment includes auto-handled threads for non-admins (test via dev-mode view-as technician — now actually works after the 2026-04-24 dev-mode perms fix).
7. Document new `thread.auto_handled` event in `docs/event-taxonomy.md`. Merge new thread-status contract + `auto_handled_at` + `ai_review` folder into `docs/data-model.md` + `docs/email-pipeline.md`. Delete this plan doc + its CLAUDE.md index entry in the same commit per the Documentation Alignment rule.

## 9. Definition of Done

- [ ] DDL applied, column indexed.
- [ ] `update_thread_status` uses new derivation; `ignored` is no longer derived.
- [ ] All three orchestrator auto-handle write sites set `thread.auto_handled_at`.
- [ ] `thread.auto_handled` event emitted and documented in `event-taxonomy.md`.
- [ ] Backfill script ran clean on Sapphire (dry-run report reviewed, commit applied, row counts reconciled).
- [ ] `ai_review` system folder seeded for every org.
- [ ] Folder listing endpoint returns `ai_review` with correct count; owner+admin only.
- [ ] `list_threads` audit complete; every `status="ignored"` / `exclude_ignored` call site checked and left correct.
- [ ] `get_thread_stats` returns new `ai_review_count`; `auto_handled_today` reworked to new predicate.
- [ ] Frontend: sidebar renders AI Review folder with amber badge (admin only); `InboxFilters` segmented control has 3 options for every role; `page.tsx` no longer references `auto_handled` status.
- [ ] Handled-segment rows render the "AI" pill for auto-handled threads.
- [ ] Tests: pytest for derivation (all four paths), pytest for orchestrator auto-handle → `auto_handled_at` set, Vitest for sidebar folder render + badge, integration test for the ack-flow drop-out.
- [ ] `docs/data-model.md` + `docs/email-pipeline.md` updated with new contract; this plan doc + CLAUDE.md index entry removed in the ship commit.
- [ ] Dogfood window (3-5 days) on Sapphire before declaring shipped — watch for regressions in Handled segment counts and AI Review badge drift.

## 10. Risks + mitigations

- **Blast radius on `thread.status` contract.** Every query that references `thread.status` was written against the old semantics. Mitigation: `list_threads` audit table in §5.2; grep for `.status == "ignored"` and `thread.status` in all services to catch anything missed. Run full pytest suite pre-merge.
- **Backfill misclassifies a user-archived thread as auto-handled.** Heuristic relies on the inbound message's own status. A user who manually marked `status="ignored"` on a thread whose inbound message happened to also be `"handled"` (unusual but possible) would get their archive reclassified. Mitigation: dry-run report includes a sample of candidate rows for manual review; if the sample looks off, add an extra predicate (e.g. presence of a user-archive event) before committing.
- **AI Review folder becomes a graveyard.** Admin never acks; folder grows indefinitely. Mitigation: not this plan's problem to solve. If observed, add a time-based auto-ack (30 days → `auto_handled_feedback_at = auto_handled_at + 30d` silent ack) in a follow-up. Don't pre-build.
- **Non-admin seeing auto-handled in Handled creates noise.** A technician's Handled view now includes AI auto-closes they had no part in. Mitigation: the "AI" pill makes the source legible at a glance; `Mine` toggle (already in the filter row) narrows to their own assignments for technicians who find it noisy.
- **Spam/auto_reply threads now surface in both Spam folder + AI Review.** Arguably correct (they're both spam *and* AI auto-closed) but double-reporting could confuse. Mitigation: document in §5.1; if reported as confusing after dogfood, scope AI Review query to `folder_id != spam_folder_id` to deduplicate. Start permissive.

## 11. Scope — what this plan is *not*

- Not a classifier accuracy improvement. If the classifier is mis-handling Workspace notifications as "no_response," that's a separate data-collection + learning problem (tracked via R5 paydowns, `AgentLearningService`).
- Not a review-window feature ("show auto-handled in Inbox for 7 days"). Considered during design, deferred — folder + badge is the less-intrusive equivalent signal.
- Not a rename of `status="archived"` or any cleanup to the outbound path. Scope is strictly the inbound auto-handle visibility gap.
- Not the promised `final_response` denormalization cleanup (separate future project per session state 2026-04-24).
