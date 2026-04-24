# Phase 5 — Unify existing agents into the proposal system

> Refinement spec produced by the per-phase gate. Master plan: `docs/ai-platform-plan.md` → Phase 5. Remove this file when the phase is shipped + archived.

## Status (2026-04-23)

- [x] **Step 1: estimate_generator pilot** — shipped + dogfood-verified on Sapphire. `draft_estimate_from_thread` stages an `estimate` proposal; case detail renders `<ProposalCard>` in "Pending AI Drafts"; Accept materializes Invoice + job link atomically; Edit/Save records `agent_corrections` edit rows.
- [x] **Step 2: email_drafter migration** — shipped + dogfood-verified. Orchestrator flag-gated via `EMAIL_DRAFTER_USE_PROPOSALS` (on for Sapphire). When on: inbound mail stages `email_reply` proposals, inbox reading pane renders `<ProposalCard>` in place of the legacy `draft_response` block, Accept/Edit/Reject flow via the canonical `ProposalService` path.
- [x] **Step 3: customer_matcher extension** — shipped. Low-confidence verifier drops now stage `customer_match_suggestion` proposals; review queue at `/inbox/matches` (owner+admin visibility). High-confidence trusted methods still auto-apply unchanged.
- [x] **Step 4: Historical port** — shipped + verified on Sapphire (150 `draft_response` rows → 150 `agent_proposals` + 144 `agent_corrections`, parity asserted). `classifier.get_correction_history` deleted; `classify_and_draft` now injects corrections via `build_lessons_prompt(AGENT_EMAIL_DRAFTER)` + past-conversation context via a fresh query on outbound `AgentMessage.body`. `thread_action_service.approve_thread` + `POST /agent-threads/{id}/approve` + the `save-draft` endpoint + the legacy draft block in `thread-detail-sheet.tsx` + the editable `DraftReplyBlock` in `action-detail-content.tsx` all deleted — every draft now flows through `ProposalService.accept`.
- [ ] **Step 5: Audit enforcement + closeout** — REMAINING. R1 enforcer grep against `draft_response` (non-zero hits remain in `admin_messages.py`, `admin_threads.py`, `agent_thread_service.py`, `orchestrator.py`, `action_presenter.py`, `equipment_agent.py`, `thread_ai_service.py` — mostly reads for historical display), taxonomy doc update, master plan closeout.

## 1. Purpose

Phases 2-4 built the platform. Phase 5 **migrates the remaining ad-hoc AI paths onto it**. Today three agents still bypass `agent_proposals`, `ProposalService`, and the correction-recording pipeline:

- `estimate_generator` (`thread_ai_service.draft_estimate_from_thread`) — creates a draft estimate directly via `InvoiceService.create`. The proposal creator for `entity_type="estimate"` already exists; the drafter just doesn't use it.
- `email_drafter` (embedded in `agents/classifier.py`) — writes `draft_response` onto `AgentMessage`. The whole approve/edit/reject cycle runs on that column via `thread_action_service`, never touches `agent_proposals`.
- `customer_matcher` (`agents/customer_matcher.match_customer`) — auto-applies matches at high confidence, silently discards low-confidence candidates. No human-in-the-loop path exists for the low-confidence bucket.

Leaving these on the old rails violates DNA rule 4 (never optimize for ease of build) — two parallel AI-output systems forever is exactly the half-finished architecture the rule prohibits. It also caps the competitive moat from DNA rule 2 (every agent learns): every correction recorded on `AgentMessage.draft_response` is a correction that doesn't flow through `AgentLearningService.record_correction` via `ProposalService`, so Phase 3's summarizer and Phase 6's workflow-observer don't see it.

**DNA alignment:**
- Rule 2: every agent learns via the same canonical path (`ProposalService.resolve_*` → `agent_corrections` → lesson injection).
- Rule 4: one proposal system, zero exceptions. `grep -r "requires_confirmation" src/` stays at zero; add a symmetric audit for `AgentMessage.draft_response` writes.
- Rule 5: AI never commits to the customer — `email_reply` proposals enforce this structurally. Today the guardrail is policy (classifier's `needs_approval` heuristic); after Phase 5 it's a data model.

## 2. Environment facts (verified 2026-04-23)

- **Proposal scaffold from Phase 2 is complete.** `proposals/proposal_service.py` implements `stage`, `accept`, `edit_and_accept`, `reject`, `supersede`, `expire_stale`. Registry at `proposals/registry.py`. Creators exist for: `broadcast_email`, `case_link`, `case`, `chemical_reading`, `customer_email`, `customer_note_update`, `equipment_item`, `estimate`, `job`, `org_config`.
- **`grep -r "requires_confirmation" /srv/quantumpools/app/src/ --include="*.py"` → zero hits.** Phase 2 already retired that axis.
- **`estimate` creator exists and is production-ready** (`proposals/creators/estimate.py`, delegates to `InvoiceService.create(document_type="estimate")`). Frontend renderer exists (`proposals/renderers/EstimateProposalBody.tsx`). The drafter currently ignores both.
- **No `email_reply` creator or renderer exists.** The closest analog is `customer_email` (used by DeepBlue's `draft_customer_email` tool — one-off email to a customer, not a threaded reply). Reply-to-thread semantics are different enough that this needs a new entity type, not a repurpose.
- **`customer_matcher.match_customer` returns a dict with `method`, `confidence`, `customer_id`**. `_TRUSTED_METHODS` (`email`, `contact_email`, `previous_match`, `sender_name`) skip verification. Everything else goes through `_verify_match` which calls Claude with a body context window. There's no current "low-confidence → human review" branch; low-confidence matches just don't get applied.
- **`thread_action_service.send_draft_reply`** is the current "approve the draft" endpoint. Reads `msg.draft_response`, records a correction via `AgentLearningService` if edited, sends via `EmailService.send_agent_reply`, appends to thread.
- **Phase 4 handler registry** (`workflow/handlers.py`, `workflow/config_service.py`) is live. Post-accept `next_step` extension on `POST /v1/proposals/{id}/accept` already flows for `job` entity_type. Phase 5 automatically picks up whatever handlers orgs configure for `estimate`, `email_reply`, `customer_match_suggestion` later — no new plumbing needed.
- **Frontend proposal UI**: `ProposalCard` + `ProposalCardMini` in `frontend/src/components/proposals/`. 4 body renderers (`Equipment`, `Estimate`, `Job`, `OrgConfig`). The inbox reading pane today renders drafts via the legacy `thread-detail-sheet.tsx` surface, NOT via `ProposalCard`.

## 3. What this phase ships

Three agent migrations, sequenced smallest-to-largest to de-risk the pattern:

1. **`estimate_generator` pilot** — rewire `thread_ai_service.draft_estimate_from_thread` to call `ProposalService.stage(entity_type="estimate", ...)` instead of `InvoiceService.create(...)` directly. No new creator (exists). No new renderer (exists). Surface: estimate-draft banner on case detail consumes `ProposalCard`.
2. **`email_drafter` migration** — new `entity_type="email_reply"` creator (delegates to `EmailService.send_agent_reply`). New renderer `EmailReplyProposalBody.tsx`. Classifier's `draft_response` output gets staged as a proposal on inbound-message ingest instead of writing to `AgentMessage.draft_response`. Inbox reading pane swaps `draft_response` rendering for `ProposalCard`.
3. **`customer_matcher` low-confidence branch** — new `entity_type="customer_match_suggestion"` creator (applies `agent_threads.matched_customer_id` on accept). New renderer. New review queue at `/inbox/matches` (filter = `staged` proposals of this type), surfaced via a filter chip.

Plus:

- **Audit enforcer** — add `grep -r "AgentMessage\.draft_response\s*=" src/` check to the R1 enforcer. After migration the only remaining write path should be the proposal's `accept` → `EmailService.send_agent_reply`, which doesn't touch `draft_response`. Post-port, the legacy read path in `classifier.get_correction_history` is also removed — single correction source.
- **Historical port script** — one-shot migration that reads every `AgentMessage` with non-null `draft_response` and synthesizes matching `agent_proposals` + `agent_corrections` rows. Runs as the last backend step before the R1 enforcer tightens. After port, `classifier.get_correction_history` (legacy path) is deleted; `build_lessons_prompt` reads only from `agent_corrections`.
- **`AgentMessage.draft_response` column remains structurally** — the drop is Phase 5b, after a grace period for any external readers (analytics exports, etc.). Phase 5 removes every *code* reference to it in the active read/write path, so 5b is purely schema cleanup.
- **Events**: no new top-level events — `proposal.staged` / `proposal.accepted` / `proposal.edited` / `proposal.rejected` (from Phase 2) cover all three agents. Add entries to `docs/event-taxonomy.md` showing which `entity_type` values ship in this phase.
- **Tests**: for each agent — unit test for the new staging path, integration test for the full stage → accept → entity-exists cycle, Vitest for the new renderer. Port script gets a row-count parity test (pre-count of `draft_response IS NOT NULL` === post-count of `agent_proposals` with `agent_type in (email_drafter)` from backfill).

Out of scope:

- DeepBlue `command_executor` proposals — already migrated in Phase 2.
- `job_evaluator`, `email_classifier` — both are classification agents (label-only, no state mutation). They stay on the existing correction flow via `AgentLearningService.record_correction` directly. Classification isn't a proposal by the Phase 2 definition.
- `deepblue_responder` — conversational, not a proposal producer.
- `equipment_resolver` — covered by Phase 2's DeepBlue migration.
- Dropping the `AgentMessage.draft_response` column itself — Phase 5b, after a grace period. Phase 5 removes all code references.

## 4. Per-agent migration specs

### 4.1 `estimate_generator` (pilot)

**Current path:**
```
User clicks "Generate Estimate" on a thread
  → POST /v1/admin/agent-threads/{id}/draft-estimate
  → ThreadAIService.draft_estimate_from_thread(org_id, thread_id, created_by)
      → Claude call with conversation + labor rate
      → InvoiceService.create(..., document_type="estimate", status="draft")
      → link_job_invoice(...) or create new bid job
  → frontend redirects to /invoices/{id}
```

**Target path:**
```
User clicks "Generate Estimate" on a thread
  → POST /v1/admin/agent-threads/{id}/draft-estimate
  → ThreadAIService.draft_estimate_from_thread(...)
      → Claude call with conversation + labor rate
      → ProposalService(db).stage(
            agent_type="estimate_generator",
            entity_type="estimate",
            data={customer_id, subject, line_items, case_id, ...},
            source={kind: "thread", id: thread_id},
            actor=actor_agent("estimate_generator"),
            org_id=org_id,
        )
  → returns {proposal_id}
  → frontend navigates to the case detail or renders ProposalCard inline
  → user clicks Accept on ProposalCard
  → POST /v1/proposals/{proposal_id}/accept
  → existing estimate creator runs (proposals/creators/estimate.py)
  → Phase 4's next_step lookup runs (currently null for estimate, future additive)
```

**Consumer UI changes:**
- Case detail page: the `estimate-draft` banner (currently a bespoke component) becomes `<ProposalCard proposalId={...} />`. The existing `EstimateProposalBody.tsx` renderer already handles the body — just wire `ProposalCard` as the shell.
- Customer detail page: if it has an "AI Draft Estimate" callout, same swap.
- **Post-accept behavior: stay on the case page.** Fire a success toast with a "View invoice →" link pointing at `/invoices/{outcome_entity_id}`. No automatic redirect. Matches Phase 3's inline-step philosophy — accepts happen in context, user doesn't lose their place mid-conversation-review. The `outcome_entity_id` is already in the accept response, so the toast can be built client-side.

**Deletions:**
- `InvoiceService.create` call + `link_job_invoice` call + bid-job-creation block in `draft_estimate_from_thread` (lines ~330-410) move wholesale into the creator. Actually they already exist there — the migration is literally deleting the direct-create block and replacing with a `stage(...)` call.
- `case_id` needs to flow through `proposal.data.case_id` so the creator still links the estimate to the case.

**Learning signal:** `estimate_generator` agent_type already has entries in `AgentLearningService` constants (`AGENT_ESTIMATE_GENERATOR`). Today the drafter calls `build_lessons_prompt(..., AGENT_ESTIMATE_GENERATOR)` before Claude. Post-migration, corrections flow via `ProposalService.edit_and_accept` / `reject` instead of wherever they flow today (spot-check: confirm they flow anywhere at all — if not, this migration is a net-new learning signal, good).

**DoD (estimate_generator):**
- `ThreadAIService.draft_estimate_from_thread` returns `{proposal_id, status: "staged"}` instead of `{invoice_id, invoice_number}`.
- No direct call to `InvoiceService.create` in that method path.
- Accepting the proposal creates exactly one estimate (idempotency: re-accept on already-accepted proposal → 409, not a second estimate).
- Existing "already has estimate linked" short-circuit preserved: drafter checks for an existing estimate before staging, returns the existing one if present.
- Case linking preserved: proposal's `data.case_id` flows through creator → `InvoiceService.create(case_id=...)`.
- Vitest: the estimate-draft surface renders `ProposalCard` when a staged proposal exists.
- Pytest: stage → accept cycle creates the Invoice row, links to the right job (thread-job or customer-job preference preserved), emits `proposal.staged` + `proposal.accepted` events.

### 4.2 `email_drafter` (main migration)

**Current path:**
```
Inbound email arrives → orchestrator
  → classifier.classify_and_draft(...) → Claude returns {category, urgency, draft_response, needs_approval, ...}
  → orchestrator writes msg.draft_response = draft, msg.status = "pending"
  → user opens thread in inbox reading pane
  → UI reads msg.draft_response, shows it inline with Approve/Edit/Dismiss buttons
  → User clicks Approve → POST /v1/admin/agent-threads/{id}/send-draft-reply
  → thread_action_service.send_draft_reply(...)
      → if edited, record_correction(type="edit", ...)
      → EmailService.send_agent_reply(...)
      → create outbound AgentMessage status="sent"
      → update_thread_status(...)
```

**Target path:**
```
Inbound email arrives → orchestrator
  → classifier.classify_and_draft(...) → same output shape as today
  → orchestrator writes classification fields to AgentMessage (category, urgency — those are classification, not proposals)
  → orchestrator calls ProposalService.stage(
        agent_type="email_drafter",
        entity_type="email_reply",
        data={thread_id, reply_to_message_id, to, subject, body, customer_id},
        source={kind: "message", id: inbound_msg.id},
        actor=actor_agent("email_drafter"),
        org_id=org_id,
    )
  → msg.draft_response stays NULL for new inbound from this point forward
  → user opens thread in inbox reading pane
  → UI fetches proposals for this thread (GET /v1/proposals?entity_type=email_reply&source_id={msg_id}&status=staged)
  → renders <ProposalCard proposalId={...} /> in place of the old inline draft
  → user clicks Accept → POST /v1/proposals/{id}/accept
  → new creator (proposals/creators/email_reply.py) runs:
      → validate thread/message still accessible to org
      → call EmailService.send_agent_reply(...) — same canonical path
      → outbound AgentMessage gets created inside send_agent_reply
      → update_thread_status on the enclosing thread
  → Phase 4 next_step for email_reply: null in Phase 5 (future: "mark-handled" or "snooze")
```

**New creator (`proposals/creators/email_reply.py`):**

```python
class EmailReplyProposalPayload(BaseModel):
    thread_id: str
    reply_to_message_id: str                 # the inbound we're replying to
    to: str                                  # recipient email
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    customer_id: Optional[str] = None        # matched customer at time of stage
    cc: Optional[list[str]] = None

@register("email_reply", schema=EmailReplyProposalPayload)
async def create_email_reply_from_proposal(payload, org_id, actor, db):
    # Load thread — confirm org ownership (defense-in-depth; proposal already org-scoped)
    thread = (await db.execute(
        select(AgentThread).where(
            AgentThread.id == payload["thread_id"],
            AgentThread.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if thread is None:
        raise NotFoundError(f"Thread {payload['thread_id']} not in org {org_id}")

    # Delegate to canonical outbound path
    result = await EmailService(db).send_agent_reply(
        org_id=org_id,
        thread_id=payload["thread_id"],
        to=payload["to"],
        subject=payload["subject"],
        body_text=payload["body"],
        cc=payload.get("cc"),
        in_reply_to=payload["reply_to_message_id"],
    )
    return result
```

**New renderer (`proposals/renderers/EmailReplyProposalBody.tsx`):**

Renders:
- Recipient (To / Cc), read-only in card mode, editable in edit mode
- Subject (editable)
- Body (editable textarea, plain text — HTML rendering is a separate concern handled at send time)
- Footer: "Sending as {agent_from_email}" so the sender identity is explicit

Accept button label: "Reply to {customer_name or recipient_email}". Describes what the click actually does (this is threaded reply, not a fresh send) while still naming the recipient so the commit is informed-consent at click-time. DNA rule 5 (AI never commits to the customer) is enforced structurally by the proposal boundary itself — the draft can't leave QP until a human clicks; the exact verb is less load-bearing than the gating.

Note: `customer_email` (DeepBlue's fresh-email tool) keeps "Send to {name}" because that *is* a fresh send, not a reply. Different verbs for different actions is the honest framing.

**Inbox reading-pane swap:**

`thread-detail-sheet.tsx` (and mobile equivalents) currently renders `msg.draft_response` in an inline block with custom Approve/Edit/Cancel buttons. Swap to: if there's a staged proposal for this thread on this inbound message, render `<ProposalCard proposalId={proposal.id} />` in that slot. Fall back to `draft_response` rendering ONLY for historical messages with `draft_response != null` (read-only — can't approve, since approve would be a post-migration path).

**Orchestrator changes:**

```python
# Before (conceptually):
msg.draft_response = classification["draft_response"]
msg.status = "pending"
await db.commit()

# After:
msg.status = "pending"
await db.commit()
if classification.get("draft_response"):
    await ProposalService(db).stage(
        agent_type="email_drafter",
        entity_type="email_reply",
        data={
            "thread_id": thread.id,
            "reply_to_message_id": msg.id,
            "to": msg.from_email,
            "subject": _reply_subject(msg.subject),
            "body": classification["draft_response"],
            "customer_id": thread.matched_customer_id,
        },
        source={"kind": "message", "id": msg.id},
        actor=actor_agent("email_drafter"),
        org_id=org_id,
    )
```

**Deletions:**
- After the historical port lands, `thread_action_service.send_draft_reply` is deleted entirely — every draft (new and historical) flows through `ProposalService.accept`. Intermediate state (between email_drafter rollout and port completion) keeps `send_draft_reply` for historical drafts only; the endpoint routes new drafts to the proposal path based on whether a staged proposal exists for the message.

**Learning signal:**
- `build_lessons_prompt(..., "email_drafter")` is already called by the classifier before Claude (`classifier.py:105+`).
- Post-migration, corrections flow: `ProposalService.edit_and_accept` → `agent_corrections` row with `correction_type="edit"` → next `build_lessons_prompt` call picks them up. Same mechanism, cleaner data path.

**DoD (email_drafter):**
- Every new inbound message that produces a non-null `draft_response` creates exactly one staged proposal with `entity_type="email_reply"`.
- `AgentMessage.draft_response` is NOT written for new inbound after rollout. R1 enforcer includes an audit for this.
- Inbox reading pane renders `ProposalCard` for staged email replies; old messages with legacy `draft_response` render read-only.
- Accept → `EmailService.send_agent_reply` runs exactly once; outbound `AgentMessage` created; thread status updated.
- Edit-and-accept → `agent_corrections` row with the diff (not just the edited value — the patch).
- Reject → `agent_corrections` row with correction_type=`rejection`; message status stays `pending` (user can manually reply or dismiss thread).
- Historical `draft_response` rows ported into `agent_proposals` + `agent_corrections`; `classifier.get_correction_history` legacy read path deleted; `build_lessons_prompt` reads only from `agent_corrections`.
- Pytest: end-to-end inbound → stage → accept → outbound. Burst detection not tripped under single-message test.
- Pytest: port script on a fixture DB produces exactly one `agent_proposals` row per non-null `draft_response` row, with correction_type derived from `(draft_response, final_response)` mapping (edited/accepted/rejected).
- Vitest: `EmailReplyProposalBody` renders, accept dispatches POST, edit → patch flows through.

### 4.3 `customer_matcher` low-confidence branch (extension, not migration)

**Current path:**
```
Inbound message → match_customer(from_email, subject, body, org_id, thread_id)
  → try trusted methods (email match, contact_email, previous_match, sender_name)
  → if found: return {customer_id, method, confidence: "high"}
  → orchestrator sets thread.matched_customer_id = customer_id
  → if not found, call _verify_match with Claude using body context
  → if Claude returns low-confidence: no-op, thread.matched_customer_id stays null
  → thread sits in inbox unmatched (correct outcome today, but we're throwing away data)
```

**Target path (additive):**
```
Same as today for high-confidence. For low-confidence:
  → orchestrator calls ProposalService(db).stage(
        agent_type="customer_matcher",
        entity_type="customer_match_suggestion",
        data={thread_id, candidate_customer_id, reason, confidence},
        source={kind: "thread", id: thread_id},
        actor=actor_agent("customer_matcher"),
        org_id=org_id,
    )
  → thread.matched_customer_id stays null (NO auto-apply — proposal must accept)
  → thread shows up in a new review queue at /inbox/matches
  → user reviews the candidate, accepts → creator sets thread.matched_customer_id
  → Phase 4 next_step for customer_match_suggestion: null in Phase 5 (future: "apply same match to past threads from this sender")
```

**New creator (`proposals/creators/customer_match_suggestion.py`):**

```python
class CustomerMatchSuggestionPayload(BaseModel):
    thread_id: str
    candidate_customer_id: str
    reason: str                              # "claude_body_match" | "fuzzy_name" | etc.
    confidence: Literal["low", "medium"]     # high never proposes; it auto-applies

@register("customer_match_suggestion", schema=CustomerMatchSuggestionPayload)
async def create_customer_match_from_proposal(payload, org_id, actor, db):
    # Validate candidate is in the org
    cust = (await db.execute(
        select(Customer).where(
            Customer.id == payload["candidate_customer_id"],
            Customer.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if cust is None:
        raise NotFoundError("Candidate customer not in org")

    # Apply the match
    thread = await db.get(AgentThread, payload["thread_id"])
    if thread is None or thread.organization_id != org_id:
        raise NotFoundError("Thread not in org")
    thread.matched_customer_id = cust.id
    thread.customer_name = cust.display_name  # display cache
    await db.commit()
    return thread
```

**New renderer (`proposals/renderers/CustomerMatchProposalBody.tsx`):**

Shows:
- The inbound message's from/subject/first-few-lines
- The candidate customer: display name, email on file, property address
- Reason ("Matched via email body mention") + confidence badge
- Accept button: "Match thread to {candidate_name}"
- Reject button: "Not a match"

**New surface — review queue:**

`/inbox/matches` route. Filter = staged proposals where `entity_type="customer_match_suggestion"`. One list, one card per proposal. Accepts flip the thread match and remove the card from the queue. Rejected candidates don't come back (the orchestrator won't re-stage for the same (thread, candidate) pair — idempotency via `ProposalService.stage`'s dedup on `source` + entity signature).

Access: inbox filter chip "Unmatched" (in the owner+admin ops row, same pattern as "Auto-Handled"). Shows count = staged customer_match_suggestion proposals.

**DoD (customer_matcher):**
- High-confidence matches unchanged — still auto-apply.
- Low-confidence Claude verifications now stage a proposal instead of discarding.
- Review queue at `/inbox/matches` lists staged proposals; accept applies the match; reject records the correction.
- Idempotency: re-running orchestrator on the same message doesn't create duplicate suggestions for the same candidate.
- Pytest: low-confidence verify → stage proposal. Accept → thread's matched_customer_id updated. Reject → thread stays unmatched, correction recorded.
- Vitest: review queue page renders list, empty state, accept/reject flows.

## 5. Data model

**No schema changes.**

The `agent_proposals` table from Phase 2 already supports arbitrary `entity_type`. Phase 5 adds three string values (`email_reply`, `customer_match_suggestion` — `estimate` already in use). The JSONB `data` column carries per-entity payloads.

**Historical port script** (`app/scripts/port_draft_response_to_proposals.py`) — one-shot, idempotent. For every `AgentMessage` with `draft_response IS NOT NULL`:
- Synthesize an `agent_proposals` row with `agent_type="email_drafter"`, `entity_type="email_reply"`, `data={body: draft_response, ...}`, `source={kind: "message", id: msg.id}`.
- Derive final `status` from the pair `(draft_response, final_response)`:
  - `final_response IS NULL AND msg.status IN ('rejected','ignored','dismissed')` → proposal `status=rejected`, record `agent_corrections` row with `correction_type=rejection`.
  - `final_response = draft_response` → proposal `status=accepted`, `agent_corrections` with `correction_type=acceptance`.
  - `final_response != draft_response AND NOT NULL` → proposal `status=accepted` with edit patch, `agent_corrections` with `correction_type=edit` + patch diff.
  - Any other state → proposal `status=expired` (rare — historical-pending drafts that never resolved).
- Idempotent via `source.id` uniqueness: re-running the script skips rows already ported.
- Row-count parity assertion at end: `COUNT(draft_response IS NOT NULL) === COUNT(agent_proposals WHERE agent_type='email_drafter' FROM backfill)`.

**No column drops in Phase 5.** `AgentMessage.draft_response` and `AgentMessage.final_response` remain structurally but every code reference is removed post-port. Phase 5b drops them after grace period.

## 6. Frontend consumption points

**Proposal fetch:**
- `GET /v1/proposals?entity_type={type}&source.kind={kind}&source.id={id}&status=staged` — already exists from Phase 2.
- `GET /v1/proposals?entity_type=customer_match_suggestion&status=staged` — for the review queue.

**Component map:**

| Entity type | Renderer body | Surface |
|---|---|---|
| `estimate` | `EstimateProposalBody.tsx` (exists) | Case detail, customer detail, standalone detail |
| `email_reply` | `EmailReplyProposalBody.tsx` (new) | Inbox reading pane (replaces legacy `draft_response` inline block) |
| `customer_match_suggestion` | `CustomerMatchProposalBody.tsx` (new) | `/inbox/matches` review queue + inbox row hover panel |

**ProposalCard shell** (`proposals/ProposalCard.tsx`) is entity-type agnostic — keyed by `entity_type` it picks the right renderer. The shell already handles Accept / Edit / Reject + `next_step` consumption from Phase 4.

## 7. Rollout sequence

Order matters. Small-to-large to validate the pattern cheap:

1. **estimate_generator (pilot, ~3 days)**
   1. Add pytest: stage+accept an estimate proposal via the existing creator, verify Invoice row + job link.
   2. Rewrite `ThreadAIService.draft_estimate_from_thread` to call `ProposalService.stage` instead of `InvoiceService.create`.
   3. Update the `/v1/admin/agent-threads/{id}/draft-estimate` endpoint response to return `{proposal_id, status: "staged"}`.
   4. Swap case-detail estimate-draft banner to render `<ProposalCard>`.
   5. Vitest on the swapped surface.
   6. Dogfood on Sapphire: draft an estimate, accept it, verify Invoice created + linked to case.
   7. Check correction flow: edit the line items on the proposal, accept, verify `agent_corrections` row exists.

2. **email_drafter (main, ~1 week)**
   1. Create `proposals/creators/email_reply.py` + Pydantic schema + register. Unit test.
   2. Create `proposals/renderers/EmailReplyProposalBody.tsx`. Vitest for render + action dispatches.
   3. Add classifier→orchestrator integration: on classifier result with non-null draft_response, call `ProposalService.stage(entity_type="email_reply", ...)` instead of writing `msg.draft_response`. Flag-gated via env var `EMAIL_DRAFTER_USE_PROPOSALS` initially (off by default so rollout is controlled).
   4. Inbox reading pane (`thread-detail-sheet.tsx`): when a staged email_reply proposal exists for the visible inbound message, render `<ProposalCard>` instead of the legacy draft block. Legacy `draft_response` still renders for historical messages.
   5. Mobile equivalent (`inbox-mobile-list.tsx` or wherever the drafts render on small screens) — same swap.
   6. Pytest: inbound → stage → accept full cycle.
   7. Pytest: edit-and-accept → correction recorded with patch.
   8. Flip `EMAIL_DRAFTER_USE_PROPOSALS=true` on Sapphire. Watch inbox for 3-5 days.
   9. Observe: how many proposals staged, accepted, edited, rejected? Correction rate per category compared to pre-migration baseline?
   10. After 5 clean days on Sapphire, flag defaults to on; env-var removed in a follow-up commit.

3. **customer_matcher (extension, ~3 days)**
   1. Create creator + renderer + review-queue page.
   2. Add orchestrator branch: on low-confidence verify result, stage proposal instead of no-op.
   3. Add inbox filter chip "Unmatched" (owner+admin only) + route `/inbox/matches`.
   4. Pytest: low-confidence → stage → accept → thread matched.
   5. Dogfood on Sapphire — will only produce signal once a real low-confidence candidate arrives; may need a synthetic test.

4. **Historical port (~1 day)**
   1. Write `app/scripts/port_draft_response_to_proposals.py` per §5. Idempotent, row-count-parity assertion.
   2. Dry run on Sapphire DB: print counts by derived-status, spot-check 5 random rows for correctness.
   3. Full run. Verify parity assertion passes.
   4. Delete `classifier.get_correction_history` — no more legacy read path. Confirm `build_lessons_prompt` still returns the same lesson set (now sourced from `agent_corrections` alone).
   5. Delete `thread_action_service.send_draft_reply` — every draft path now flows through `ProposalService`.
   6. Pytest: port script on fixture DB produces expected row counts + correction types per scenario.

5. **Audit enforcement (~half day)**
   1. Add grep check to R1 enforcer: `grep -rE "\.draft_response" /srv/quantumpools/app/src/` — after port, this should return zero hits outside the port script itself (which stays in `app/scripts/` as historical reference, but can be excluded from the enforcer via a pathspec).
   2. Update `docs/event-taxonomy.md` §N with the new `entity_type` values.
   3. Audit `ai-platform-plan.md` Phase 5 acceptance criteria — mark all three agents done.

## 8. Definition of Done

1. `estimate_generator`, `email_drafter`, `customer_matcher` all stage proposals instead of (or in addition to) direct DB writes.
2. `proposals/creators/` contains `email_reply.py` and `customer_match_suggestion.py` alongside existing `estimate.py`.
3. `proposals/renderers/` contains `EmailReplyProposalBody.tsx` and `CustomerMatchProposalBody.tsx` alongside existing `EstimateProposalBody.tsx`.
4. Inbox reading pane renders staged email-reply proposals via `ProposalCard`. Legacy `draft_response` still readable for historical messages (read-only).
5. Case detail estimate-draft surface renders via `ProposalCard`.
6. `/inbox/matches` review queue exists, gated by owner+admin visibility, filter chip present on inbox filter rail.
7. No new `AgentMessage.draft_response` writes for freshly classified inbound messages on the rollout org. R1 audit passes.
8. Accept on any Phase 5 proposal → entity exists, event emitted, `agent_corrections` row written on edit/reject.
9. Idempotent re-stage: orchestrator re-running on the same inbound doesn't create duplicate proposals for the same (thread, inbound_message) pair.
10. Flag-controlled rollout for email_drafter: env var allows instant rollback if classifier-output-shape assumptions break.
11. Historical port complete: every pre-Phase-5 `draft_response IS NOT NULL` row has a matching `agent_proposals` row with correct derived status + `agent_corrections` row with correct correction_type. Row-count parity assertion passes.
12. `classifier.get_correction_history` and `thread_action_service.send_draft_reply` deleted. `build_lessons_prompt` reads only from `agent_corrections`. R1 grep for `draft_response` in `/srv/quantumpools/app/src/` returns zero hits (port script in `app/scripts/` allowed).
13. Sapphire dogfood complete: all three agents observed producing + resolving proposals, at least one edit and one reject correction recorded per agent.
14. `ai-platform-plan.md` Phase 5 section updated with completion date + link to this doc.
15. This doc deleted from `docs/` + removed from CLAUDE.md Documentation Index in the same commit as the completion mark.

## 9. Resolved decisions

1. **Pilot order: estimate → email → match.** Rationale above (§Purpose + §1 of message history). Smallest surface first to validate the pattern on production load; biggest-value surface second with pattern proven; extension last.
2. **Port historical `draft_response` rows into `agent_proposals` in Phase 5; drop the column in Phase 5b.** Original lean was "defer the port to 5b" — rejected as optimize-for-ease (DNA rule 4 violation). Leaving two correction-source paths in `build_lessons_prompt` (legacy `get_correction_history` + new `agent_corrections`) for the gap between phases is exactly the half-finished architecture the rule prohibits. Port + delete-legacy-reader lands in Phase 5. Column drop stays in 5b purely for grace-period safety (external readers like analytics exports).
3. **`email_drafter` staging happens in orchestrator, not classifier.** Classifier stays a pure function `input → classification JSON`. Staging is a side effect — lives at the call site (orchestrator) where the transaction boundary is clear.
4. **`customer_matcher` high-confidence stays auto-apply.** Adding a proposal for every trusted-method match would flood the queue with one-click-accepts. Rule 6 (less work for user) wins over rule 5 here — high-confidence matches aren't AI committing to the customer, they're deterministic join logic.
5. **No `edit_and_accept` for `email_reply` on the initial compose** — it sends. Editing the subject/body IS the edit-and-accept action in one click. The renderer's Save button calls `edit_and_accept` directly; there's no two-step "save edits" then "send."
6. **Phase 4 `next_step` for all three entity types: null in Phase 5.** Future handlers (mark-handled, snooze, assign-follow-up, apply-to-past-threads) are additive — new entries in `org_workflow_config.post_creation_handlers`, new frontend components, no new plumbing.
7. **Flag-gating only for email_drafter.** Highest-blast-radius migration of the three (every inbound email). Estimate and matcher are lower volume — rollout by shipping, no flag layer.
8. **Burst-detection stays at Phase 2 default** (200 stages per (agent_type, org) per hour). email_drafter on Sapphire averages ~30-50 inbound/day — orders of magnitude below threshold. Revisit if burst alerts fire in production.
9. **Historical migration out of scope.** Pre-Phase-5 messages with `draft_response != null` stay as legacy read-only. A one-time script porting them into `agent_proposals` could exist but only if Phase 5b decides to drop the column.
10. **R1 enforcer update is a DoD item, not a follow-up.** Every other DoD slips without it. Ship the enforcer rule in the same commit that flips the final agent.

11. **`/inbox/matches` review queue: owner + admin visibility only.** Matches the other ops-chip pattern (Auto-Handled, Stale, Outbox). Technicians and readonly roles don't see it. Managers can be granted via the per-user permission-override system if needed (Kim specifically) — shipping narrow by default because it's cheaper to broaden than to narrow without disrupting users.

12. **Email-reply accept button copy: "Reply to {name}"**. Accurate verb (this is threaded reply, not a fresh send). `customer_email` (DeepBlue's fresh-send tool) keeps "Send to {name}". Different verbs for different actions — honest framing beats forced consistency. DNA rule 5's structural enforcement lives at the proposal boundary, not at the button word.

13. **Estimate accept stays on the case page with a success toast.** "View invoice →" link in the toast for users who want to navigate. No automatic redirect. Matches Phase 3's inline-step philosophy; preserves context for mid-case-review accepts. Old auto-redirect behavior is intentionally broken — any muscle memory is retrained in one cycle.

## 10. Open questions

None — all resolved at the 2026-04-23 gate closeout. See §9 items 11-13.

## 11. Scope estimate

- estimate_generator pilot: ~3 days (backend ~1, frontend ~1, dogfood ~1)
- email_drafter migration: ~1 week (backend ~2, frontend ~2, rollout + observation ~3)
- customer_matcher extension: ~3 days (backend ~1, new queue page ~1, dogfood ~1)
- historical port script + legacy-reader deletion: ~1 day
- audit enforcement + taxonomy updates: ~half day
- doc updates + ai-platform-plan.md closeout: ~half day

**Total: ~2.5 weeks elapsed.** Slightly above the master plan's ~2-week estimate because the port-now decision adds a day of work that would otherwise have slipped to Phase 5b.

---

Ready to start Step 1 (estimate_generator pilot) on sign-off. Open questions in §10 need a thumbs-up or adjustment first.
