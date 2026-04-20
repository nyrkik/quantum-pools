# Phase 3 — Inbox summarizer (first real proposal producer)

> Detailed spec produced by the per-phase refinement gate. Master plan: `docs/ai-platform-plan.md` → Phase 3. Remove this file when the phase is shipped + archived.

## 1. Purpose

Ship the redesigned inbox. Every thread that matters gets an AI-generated summary + zero-or-more staged proposals, rendered as a card-per-row so the inbox becomes triage-at-a-glance instead of open-each-thread. The summarizer is the first real `agent_proposals` consumer — if the abstraction is wrong, Phase 3 is where it breaks.

**DNA**: rule 6 (less work for user — 1-click triage over 5-click), rule 2 (the agent learns every acceptance/edit/rejection), rule 5 (proposals are drafts, humans commit).

## 2. Environment facts (verified 2026-04-19)

- Phase 1 event stream + Phase 2 proposals both live in production.
- `ProposalService` + registry support 9 entity types; `job` and `estimate` creators exist and are what the summarizer will stage most often.
- `AgentThread` + `AgentMessage` tables hold the source material. `agent_threads.category` already stores thread classification.
- Frontend has `ProposalCard` + 4 renderers. Phase 3 adds inline/compact variants.
- Feature-flag mechanism exists via `FeatureService` — QP already has `require_feature()` subscription gating. Phase 3 uses an `Organization.inbox_v2_enabled` boolean (simpler than a full feature slug, since this is a UX rollout flag not a paywall).

## 3. What this phase ships

- **New table columns** on `agent_threads`: `ai_summary_payload jsonb`, `ai_summary_generated_at timestamptz`, `ai_summary_version int`.
- **Feature flag**: `organizations.inbox_v2_enabled bool default false`. Toggle via platform-admin endpoint (no customer-admin UI this phase).
- **New agent module** `src/services/agents/inbox_summarizer.py` — builds prompt, calls Claude Haiku, validates + caches output, stages any proposals.
- **New entity_type + creator** `case_link` — stages "link this thread to case X" without creating anything new. Source reference for Sonar.
- **Trigger wiring** — inbound-message hook + APScheduler stale-sweep.
- **Events** — `thread.summarized`, `inbox.proposal_inline_accepted`, `inbox.row.expanded`, `inbox.compact_mode_toggled` (already in taxonomy §8.9, Phase 3 wires emits).
- **Frontend** — new two-column inbox row, `InboxSummaryCard`, `InlineProposalCard` compact renderer, compact-mode toggle.
- **Per-org opt-in** — `inbox_v2_enabled` gates both the UI and the backend trigger. An org with the flag off pays no Claude costs.
- **Tests** — unit tests for the summarizer (prompt construction + output validation), integration test for trigger → summary → proposal-staged, Vitest for inbox row + compact mode.

## 4. Summary shape

```jsonc
{
  "version": 1,
  "ask": "<1-sentence question or need>",            // null unless customer is asking
  "state": "<1-sentence status> | null",             // null in most cases — bullets carry the content
  "open_items": ["<thing> — <status>", ...],         // PRIMARY display field: 3-5 terse bullets
  "red_flags": ["string", ...],                      // GENUINE escalation only — legal/threats/3rd-escalation/lost revenue
  "linked_refs": [                                   // entity pointers; server validates UUIDs exist in org
    {"type": "customer", "id": "<uuid>"},
    {"type": "case", "id": "<uuid>", "label": "SC-25-0042"},
    {"type": "invoice", "id": "<uuid>", "label": "INV-25-0101"}
  ],
  "confidence": 0.0,                                 // 0..1; below CONFIDENCE_FLOOR (0.4) → don't cache
  "proposal_ids": ["...", ...]                       // agent_proposals staged by this summary run
}
```

Shape chosen to work across residential-heavy (ad-hoc requests), commercial-heavy (contracts + disputes), and dispatch orgs (appointment coordination). `open_items` is the primary display field (the row shows them as bullets); `ask` is the explicit customer question when one exists; `state` is an optional fallback line for informational-only threads with no discrete items. Red flags are reserved for genuine escalation signals only — routine AR/overdue invoices go to `open_items`, not red flags.

**Linked-ref resolution**: `InboxSummarizerService._resolve_linked_refs` validates every ref against the DB in the thread's org *after* parsing. Case/invoice refs resolve UUID-first, then fall back to case_number/invoice_number lookup (the model tends to emit the number verbatim). Unresolvable refs and `job`-type refs are dropped — `job` has no standalone page, so a link would 404 even with a real id. The prompt also surfaces real UUIDs (`id=<uuid>`) in the context lines so the model can copy them verbatim.

## 5. Trigger design

### 5.1 Inbound-message hook (primary)

Wire into `inbound_email_service.py` — after a new `AgentMessage` lands on a thread, schedule a summarizer run for that thread if `org.inbox_v2_enabled`.

Debounce: 30 seconds. Back-to-back replies within 30 s coalesce into one regenerate. Implementation: per-thread timestamp on `agent_threads.ai_summary_debounce_until`; the actual run fires via a small APScheduler `interval` job that scans for threads whose `ai_summary_debounce_until < NOW()` and which have inbound messages newer than `ai_summary_generated_at`.

This is cheaper than Redis-backed debounce and keeps the summarizer single-path (APScheduler job, like every other Phase 1/2 async work).

### 5.2 Stale-sweep (secondary)

Daily APScheduler job at 05:30 UTC: regenerate summaries older than 7 days on threads that aren't closed/archived. Picks up new learning corrections without requiring a new inbound message. Same rate-limit rules.

### 5.3 Skip heuristic

A thread gets NO cached summary (payload stays null) only when:
- `confidence < CONFIDENCE_FLOOR` (0.4) on the run

**Every thread summarizes**, including single-message / under-500-char threads. Rationale: consistency beats saving a few Haiku tokens. A one-liner "Thanks!" reply becomes `open_items: ["Thanks acknowledgment — Received"]`, which keeps the inbox visually uniform (no mixed bullet/raw-snippet rows). Original short-thread skip was removed in dogfood after the mixed presentation was worse than the marginal summary-quality risk.

### 5.4 Flag-flip backfill

`POST /v1/admin/platform/orgs/{id}/inbox-v2` with `enabled: true` queues every thread in the org that has no cached summary by setting `ai_summary_debounce_until = NOW()`. The bounded sweep (~80/min) drains the backlog without spiking Anthropic rate limits. Without this, newly-opted-in orgs would sit on empty bullets until each thread received a new inbound message.

## 6. Prompt + model

**Model**: Claude Haiku (speed + cost). Measurement criterion: if Haiku's `confidence >= 0.4` rate drops below 60% on Sapphire after 1 week, upgrade to Sonnet for threads with `message_count >= 5` only.

**Prompt skeleton** (in code as a template):

```
You are summarizing a pool service email thread for the business owner.
Output a JSON object matching this exact schema:
{schema snippet}

Context:
- Customer: {customer display name + company if any}
- Org: {org name}
- Thread subject: {subject}
- Message count: {n}
- Conversation:
{message history, inbound vs outbound prefix, 800 chars each max}

Related state:
- Open cases for this customer: {case_numbers + titles}
- Open jobs for this customer: {count + types}
- Outstanding invoices: {count + balance}

Lessons from prior corrections:
{AgentLearningService.build_lessons_prompt output}

Rules:
- The UI ALREADY shows customer name, contact person, and property address — NEVER repeat them in any summary field.
- `ask`: null unless the customer is posing a direct question we owe an answer on.
- `state`: null in most cases. Only populate when the thread has no discrete items to enumerate.
- `open_items` is the PRIMARY display field: 3-5 terse bullets in `<thing> — <status/action>` form, ≤55 chars each, no names, no addresses.
  - Good: "Filter cleaning — Approved", "Invoice 4412 — Paid in full", "Pump quote — Follow up (6 days silent)"
  - Bad: "Marty Reed approved filter cleaning", "Yes", "Customer responded with thanks"
- `red_flags`: GENUINE escalation only — explicit legal/attorney mention; chargeback/BBB/public-review threats; 3rd+ escalation; material lost-revenue or safety risk; hostile/abusive language. Routine overdue AR → `open_items`, never `red_flags`.
- `linked_refs`: only for entities the prompt context lists as open_cases or outstanding_invoices. Copy the exact `id=<uuid>` verbatim; never invent or substitute the number.
- Propose actions via `proposals` only when clearly indicated.
- `confidence` reflects your certainty in the summary, not the proposals.

Proposals to stage (if any — otherwise empty):
- To suggest a job: {entity_type: "job", payload: {...JobProposalPayload...}}
- To suggest an estimate: {entity_type: "estimate", payload: {...}}
- To suggest linking to a case: {entity_type: "case_link", payload: {...}}
```

Learning wiring: `AgentLearningService` with agent_type `inbox_summarizer` (new constant). Pre-generation prompt injection; post-user-action `record_correction` via `ProposalService` resolve paths (already wired — every accept/edit/reject already writes a correction).

## 7. `case_link` entity_type (new creator)

Phase 3 needs this because the summarizer can propose "this thread belongs to existing case X" without creating a new case.

```python
# src/services/proposals/creators/case_link.py
class CaseLinkProposalPayload(BaseModel):
    thread_id: str
    case_id: str

@register("case_link", schema=CaseLinkProposalPayload)
async def create_case_link_from_proposal(payload, org_id, actor, db):
    # Use ServiceCaseService.set_entity_case — the canonical linking path.
    svc = ServiceCaseService(db)
    return await svc.set_entity_case(
        org_id=org_id, entity_type="thread",
        entity_id=payload["thread_id"], case_id=payload["case_id"],
    )
```

Idempotent — if thread is already linked to the target case, creator returns a no-op result and the proposal resolves as `accepted` without double-linking.

## 8. Frontend

### 8.1 Inbox row redesign

`InboxThreadListV2` replaces `InboxThreadTable` when `org.inbox_v2_enabled = true`. Rendered on all screen sizes (mobile collapses the two-column grid to a single stacked column; `InboxMobileList` is skipped entirely under V2).

Layout (desktop):
```
┌──────────────────────┬──────────────────────────────────┐
│ Customer Name        │ • Filter cleaning — Approved     │  12:34p
│ Property Address     │ • Pool sweep tail — Approved     │
│ [Client][Cat][Status]│ • $450 quote — Awaiting sign-off │
└──────────────────────┴──────────────────────────────────┘
```

Mobile: single column stack (customer → address → badges → bullets → time), plus an Info (ⓘ) tap-target that opens `InboxRowHoverPanel` in a click-triggered Popover.

Left border priority (mutually exclusive): selected (primary) > pending (amber) > unread (blue).

**Grouping**: `groupByClient` prop groups rows by `customer_name || contact_email` with a primary-colored header bar per group; pending-bearing groups sort first, then alphabetical.

### 8.2 `InboxRowHoverPanel` (desktop hover + mobile tap)

Email-chrome–styled detail panel, used by both the desktop `HoverCard` (opens on hover) and the mobile `Popover` (opens on Info-button click). `(hover: none)` media query gates which one is rendered — touch devices never mount the `HoverCard` so the two popouts can't stack.

Sections (uniform skeleton; absent sections collapse):
- Header: ✉ customer name + labeled From / Address / Subject / Date rows
- Summary: bullets (`open_items`) or `state` fallback line
- Customer asks: `ask` in a muted pill
- Red flags: amber banner
- Linked: clickable chips routing to `/customers/:id`, `/cases/:id`, `/invoices/:id`
- Proposals: inline `ProposalCardMini` list with Accept/Reject

### 8.3 `ProposalCardMini`

A compact variant of `ProposalCard` used in the hover panel. Shows entity_type badge + one-line summary + Accept/Reject icon buttons. No header, no confidence pill. Full `ProposalCard` is used elsewhere (e.g., DeepBlue tool cards, proposal admin).

### 8.4 Per-org feature flag UI

None this phase. Platform-admin endpoint toggles it. Customer-admin UI for this flag can come in Phase 3b once the design is validated on Sapphire.

## 9. Cost + rate limits

Sapphire baseline: ~20-40 inbound threads/day. Haiku ~$0.001/summary ≈ $0.04/day/org. Trivial.

Runaway protection: reuse the proposal-burst detector from Phase 2 (`BURST_THRESHOLD = 200/agent/org/hour`). `inbox_summarizer` is an agent, so staging too many proposals in a single run already triggers the ntfy alert.

Per-org monthly cap: none this phase. Phase 6 (workflow_observer) adds this when the org-level picture is clearer.

## 10. Rollout sequence

1. Migration: `agent_threads` summary columns + `organizations.inbox_v2_enabled`.
2. `case_link` entity_type + creator + test.
3. `InboxSummarizerService` + prompt template + output validator + unit test.
4. Trigger wiring: inbound-message hook + APScheduler stale-sweep + debounce infra.
5. Admin endpoint `POST /v1/admin/platform/orgs/{id}/inbox-v2` to toggle the flag (platform-admin gated, mirrors existing patterns).
6. Frontend: `InlineProposalCard` (compact variant) + tests.
7. Frontend: `InboxSummaryCard` component + per-field renderers (ask, state, open_items, red_flags, linked_refs chips).
8. Frontend: `InboxRowV2` + compact-mode toggle + feature-flag gated mount.
9. Enable flag on Sapphire → live dogfood.
10. Measurement: `thread.summarized` events + existing inbox.* events → triage-latency metric.
11. Phase 3 DoD verification.

## 11. Definition of Done

1. `agent_threads.ai_summary_payload` populated for every inbound-triggered thread on Sapphire within 60 s of message arrival (confidence-floor skips excluded).
2. Stale-sweep runs daily at 05:30 UTC; regenerates ≥1 thread on a day with aged summaries (verified by journal).
3. Summarizer outputs conform to the schema in §4; invalid JSON → no cached payload, `agent.error` event, retry on next trigger.
4. `case_link` entity_type registered + tested; creator idempotent when target case already linked.
5. Learning wiring: `AgentLearningService.build_lessons_prompt` called with `agent_type="inbox_summarizer"` on every run. Every proposal resolution writes an `agent_corrections` row via the existing `ProposalService` path.
6. `inbox_v2_enabled` flag exists on orgs; admin endpoint toggles it, queues a backfill sweep on false→true; frontend honors it (V2 list if true, legacy table if false).
7. `InboxThreadListV2` renders identity/address/bullets/badges in the two-column card; desktop hover + mobile Info-button popover both show the email-chrome `InboxRowHoverPanel`; `groupByClient` wires through.
8. `thread.summarized` event emits per run (including skipped + failed runs, with `skipped_reason` or error field).
9. R1 enforcer passes: `case_link` and `thread.summarized` referenced in taxonomy; all new emits documented.
10. `mark_thread_read` publishes `thread.read`; inbox page refetches stats + folder counts on the event.
11. Linked-ref UUID resolver strips hallucinated ids and rewrites case_number/invoice_number to real UUIDs before caching.
12. Vitest covers `InboxThreadListV2` rendering (bullets priority, state/ask fallbacks, v99 unsupported-version fallback, address rendering, bullet cap, hover panel routing).
13. After 1 week Sapphire dogfood: `thread.summarized` count > 0, `proposal.staged` count (agent_type=inbox_summarizer) > 0, no Sentry errors from the agent path.

## 12. Resolved decisions (§14 equivalent — DNA-grounded judgment calls)

1. **Feature flag shape**: `Organization.inbox_v2_enabled` boolean column, not a `FeatureService` slug. Rationale: this is a per-org UX rollout, not a paywall. Building a subscription feature would be speculative complexity; a boolean is the right shape for "try this on a few orgs, enable for all when proven."

2. **Debounce = 30 s**: tuned for the "burst of quick replies" pattern common in email threads. Too-short wastes Haiku calls; too-long leaves the inbox feeling stale. Re-tune after 1 week of data if needed.

3. **Stale threshold = 7 days**: matches master plan. Picks up new learning corrections without churning constantly.

4. **Model = Haiku only**: measurement-gated upgrade to Sonnet. Prevents paying Sonnet prices for summaries that Haiku does fine on.

5. **"Accept All" only when no edits needed**: preserves "AI never commits" — one-click is fine when the user already reviewed the inline card; edits require going through the full editor (same as standalone ProposalCard).

6. **No customer-admin UI for the flag in Phase 3**: ships later when the design is validated. Platform-admin toggle is enough for Sapphire dogfood.

7. **`case_link` reuses `ServiceCaseService.set_entity_case`**: canonical linking path; avoids duplicating "attach thread to case" logic. Idempotent creator means re-accepting a superseded proposal does the right thing.

8. **Scope estimate**: ~2 weeks elapsed including audit cycles. Backend ~5 days, frontend ~6 days, measurement + tuning ~2 days. Longer than Phase 2 (simpler abstraction, but frontend is heavier).

## 13. Open questions

None blocking. The summary field shape is the most likely thing to evolve in the first week of Sapphire dogfood; the `version` field is there specifically to allow schema iteration without data loss.

---

Ready to start Step 1 (migration + feature flag column).
