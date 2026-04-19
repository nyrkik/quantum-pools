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
  "ask": "<1-sentence question or need>",            // null if thread is informational-only
  "state": "<1-sentence status>",                    // never null; e.g., "awaiting parts ETA from vendor"
  "open_items": ["string", ...],                     // actionable TODOs; empty array if none
  "red_flags": ["string", ...],                      // urgency markers, complaints, legal risk; empty ok
  "linked_refs": [                                   // entity pointers Sonar + UI can chase
    {"type": "customer", "id": "..."},
    {"type": "case", "id": "...", "case_number": "SC-25-0042"},
    {"type": "invoice", "id": "...", "invoice_number": "INV-25-0101"}
  ],
  "confidence": 0.0,                                 // 0..1; drives "short-thread → skip summary" logic
  "proposal_ids": ["...", ...]                       // agent_proposals staged by this summary run
}
```

Shape chosen to work across residential-heavy (ad-hoc requests), commercial-heavy (contracts + disputes), and dispatch orgs (appointment coordination). `ask` captures "what do they want"; `state` captures "what's happening right now"; `open_items` is the actionable list. Red flags are the scan-fast urgency vector.

## 5. Trigger design

### 5.1 Inbound-message hook (primary)

Wire into `inbound_email_service.py` — after a new `AgentMessage` lands on a thread, schedule a summarizer run for that thread if `org.inbox_v2_enabled`.

Debounce: 30 seconds. Back-to-back replies within 30 s coalesce into one regenerate. Implementation: per-thread timestamp on `agent_threads.ai_summary_debounce_until`; the actual run fires via a small APScheduler `interval` job that scans for threads whose `ai_summary_debounce_until < NOW()` and which have inbound messages newer than `ai_summary_generated_at`.

This is cheaper than Redis-backed debounce and keeps the summarizer single-path (APScheduler job, like every other Phase 1/2 async work).

### 5.2 Stale-sweep (secondary)

Daily APScheduler job at 05:30 UTC: regenerate summaries older than 7 days on threads that aren't closed/archived. Picks up new learning corrections without requiring a new inbound message. Same rate-limit rules.

### 5.3 Short-thread heuristic

A thread gets NO summary (payload stays null) when:
- `message_count < 2` AND `body_length_total < 500 chars`, OR
- `confidence < 0.4` on the first run

Frontend detects null payload → falls back to the snippet. No stub summary ever renders. Prevents uncanny-valley summaries on "thanks!" replies.

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
- `ask`: one sentence, in the voice of what the CUSTOMER wants. Null if purely informational.
- `state`: one sentence, what WE need to do next.
- `open_items`: short imperative phrases.
- `red_flags`: only real concerns — legal, threatening tone, 3rd escalation, lost revenue.
- Propose actions via the proposals section when an action is clearly indicated. Don't propose speculatively.
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

New component `InboxRowV2` replaces `InboxRow` when `org.inbox_v2_enabled = true`.

Layout:
```
┌───────────────────────────────────────────────────────────┐
│ [avatar] Customer Name / Subject         │  Summary card  │
│ <badges: sender tag | category | status> │  Ask: ...      │
│ 2 msgs • 4h ago                          │  State: ...    │
│                                          │  Open: ...     │
│                                          │  [proposal ×2] │
│                                          │  [Accept All]  │
└───────────────────────────────────────────────────────────┘
```

Compact mode: single-line collapsed (ask + customer + time), expand on click.

### 8.2 Inline `ProposalCardMini`

A compact variant of `ProposalCard` used in the row. Shows entity_type badge + one-line summary + the 3 action buttons. No header, no confidence pill. Full `ProposalCard` opens when the user expands the row.

### 8.3 "Accept All" button

Only visible when every staged proposal in the row has an enabled Accept path (no edit required). Fires `acceptProposal` for each in parallel. On partial failure, shows which succeeded + which need attention.

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

1. `agent_threads.ai_summary_payload` populated for every inbound-triggered thread on Sapphire within 60 s of message arrival (excluding short-thread skips).
2. Stale-sweep runs daily at 05:30 UTC; regenerates ≥1 thread on a day with aged summaries (verified by journal).
3. Summarizer outputs conform to the schema in §4; invalid JSON → no cached payload, `agent.error` event, retry on next trigger.
4. `case_link` entity_type registered + tested; creator idempotent when target case already linked.
5. Learning wiring: `AgentLearningService.build_lessons_prompt` called with `agent_type="inbox_summarizer"` on every run. Every proposal resolution writes an `agent_corrections` row via the existing `ProposalService` path.
6. `inbox_v2_enabled` flag exists on orgs; admin endpoint toggles it; frontend honors it (new layout if true, legacy if false).
7. `InboxRowV2` renders summary + inline `ProposalCardMini` + Accept All. Compact-mode toggle swaps between tall + single-line layouts.
8. `thread.summarized` event emits per run (including failed runs, with error field).
9. R1 enforcer passes: `case_link` and `thread.summarized` referenced in taxonomy; all new emits documented.
10. Vitest covers `InboxRowV2` rendering (3 state matrix: null-payload → snippet, full summary with proposals, summary without proposals).
11. After 1 week Sapphire dogfood: `thread.summarized` count > 0, `proposal.staged` count (agent_type=inbox_summarizer) > 0, no Sentry errors from the agent path.

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
