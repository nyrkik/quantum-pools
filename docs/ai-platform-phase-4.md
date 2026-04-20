# Phase 4 — Post-creation handlers (per-org configurable)

> Refinement spec produced by the per-phase gate. Master plan: `docs/ai-platform-plan.md` → Phase 4. Remove this file when the phase is shipped + archived.

## 1. Purpose

Phase 3 ships proposal-based job creation in the inbox — one click, job exists. But "job exists" isn't the end of the user's workflow. Some orgs need to schedule it immediately. Some assign it. Some drop it in an unassigned pool for dispatch pickup. Hardcoding one pattern violates DNA rule 1 (build for the 1,000th customer, not for Sapphire).

Phase 4 introduces a **pluggable post-creation handler** abstraction: when a proposal accepts and creates an entity, the backend tells the frontend *what happens next* (render this inline step), and the user completes the workflow without leaving the inbox.

Secondary benefit: handlers are the observable surface workflow-observer (Phase 6) watches. Every `handler.applied` / `handler.abandoned` event is a data point — "this org clicked Accept 47 times and abandoned the schedule picker 46 of them → propose switching their default to unassigned_pool."

**DNA alignment**:
- Rule 1: per-org configurable (not Sapphire-specific).
- Rule 3: observable behavior → proposal system suggests better defaults later.
- Rule 6: less work for the USER — the right step auto-appears based on what the org actually does, no enum-dropdown to hunt through.

## 2. Environment facts (verified 2026-04-19)

- Phase 1 (event instrumentation), Phase 2 (proposals), Phase 3 (inbox summarizer + V2 redesign) all shipped + live on Sapphire.
- `ProposalService.accept()` runs a creator, returns `(proposal, created)` where `created` is the new domain entity (AgentAction for job, Invoice for estimate, etc.). Single transaction, creator failure → rollback.
- `AgentActionService.update_action()` is the canonical path for assigning/status-updating a job.
- `AgentProposal` rows carry `outcome_entity_type` + `outcome_entity_id` — the handler only needs the created entity, not the proposal shape.
- Sapphire has 5 techs + Brian + Kim active in the `organization_users` table. `assign_inline` needs a tech picker; this data exists.
- No `org_workflow_config` table exists today. Defaults are hardcoded in router/service code.
- Settings surfaces exist under `/settings/*` in the frontend (billing, integrations, inbox rules); a new `/settings/workflows` fits the pattern.

## 3. What this phase ships

- **New table** `org_workflow_config` (org-scoped singleton row, created lazily).
- **Backend handler registry** `src/services/workflow/handlers.py` with 3 handlers: `assign_inline`, `unassigned_pool`, `schedule_inline`.
- **Accept-response extension**: `POST /v1/proposals/{id}/accept` now includes `next_step: {kind, initial} | null`.
- **Settings API**: `GET /v1/workflow/config`, `PUT /v1/workflow/config`.
- **Frontend component registry** keyed by `kind` — `AssignInlineStep`, `ScheduleInlineStep`, `UnassignedPoolStep` — rendered inside `ProposalCardMini` / `ProposalCard` after accept succeeds.
- **Settings surface** at `/settings/workflows` with plain-language opinionated options (no enum names, no "advanced" panel).
- **Events**: `workflow_config.changed`, `handler.applied`, `handler.abandoned`.
- **Tests**: handler-registry unit tests, accept-response shape integration test, Vitest for each component's apply/abandon paths.

## 4. Handler architecture

### 4.1 The contract

```python
# src/services/workflow/handlers.py

class WorkflowHandler(Protocol):
    name: ClassVar[str]                       # registry key, e.g. "assign_inline"
    entity_types: ClassVar[tuple[str, ...]]   # entity_types this handler applies to

    async def next_step_for(
        self,
        *,
        created: Any,                         # the entity ProposalService.accept returned
        org_id: str,
        actor: Actor,
        db: AsyncSession,
    ) -> NextStep | None:
        """Return {kind, initial} describing the inline UI step, or None
        if this handler wants to be a no-op for this specific entity."""
```

`NextStep` shape:

```python
class NextStep(BaseModel):
    kind: str              # frontend component key — matches name by convention
    initial: dict          # component-specific initial state
```

Example `AssignInlineHandler.next_step_for()` returns:

```jsonc
{
  "kind": "assign_inline",
  "initial": {
    "entity_type": "job",
    "entity_id": "<uuid>",
    "default_assignee_id": "<uuid-of-last-used>" | null,
    "assignee_options": [
      {"id": "...", "name": "Kim (Manager)"},
      {"id": "...", "name": "Jose (Tech)"},
      ...
    ]
  }
}
```

Backend stays agnostic to rendering. Frontend has a component-registry keyed by `kind`; an unknown `kind` → log a warning, render nothing (forward compatible).

### 4.2 How it's wired

`ProposalService.accept()` signature unchanged — still returns `(proposal, created)`. The handler lookup happens **in the router**, not in the service:

```python
# src/api/v1/proposals.py

@router.post("/proposals/{id}/accept")
async def accept_proposal(...):
    proposal, created = await ProposalService(db).accept(...)
    next_step = await workflow_service.resolve_next_step(
        proposal=proposal, created=created, org_id=ctx.organization_id,
        actor=actor, db=db,
    )
    return {
        "proposal": ProposalPresenter.one(proposal),
        "outcome_entity_id": proposal.outcome_entity_id,
        "outcome_entity_type": proposal.outcome_entity_type,
        "conflict": False,
        "next_step": next_step,  # NEW — may be None
    }
```

Rationale for router-side lookup:
- Keeps `ProposalService` ignorant of workflow config (good separation).
- Failure of `resolve_next_step` does NOT roll back the accept. If handler lookup fails, the entity still exists — worst case the user sees no inline step and proceeds via the entity's normal detail page. (This is important: the creation is the non-refundable bit; the post-step is augmentation.)

### 4.3 The 3 shipping handlers

**`assign_inline`** (default for `job`):
- `next_step` = `{kind: "assign_inline", initial: {entity_id, default_assignee_id, assignee_options}}`.
- Frontend renders `<AssignInlineStep>` — popover with an assignee picker, Save / Skip buttons.
- Save → `PUT /agent-actions/{id}` with `assigned_to=<uid>` + emits `handler.applied`.
- Skip → dismisses + emits `handler.abandoned` with `reason: "skip"`.
- Default assignee: derived from `default_assignee_strategy` on `org_workflow_config` — usually `last_used_by_user` (last assignee the acting user picked).

**`unassigned_pool`** (for dispatch-style orgs):
- `next_step` = `{kind: "unassigned_pool", initial: {entity_id, pool_count}}`.
- Frontend renders a toast/banner: "Added to unassigned pool (N waiting)".
- No user input, no apply step. Emits `handler.applied` immediately on render.

**`schedule_inline`** (for coordinator-driven orgs):
- `next_step` = `{kind: "schedule_inline", initial: {entity_id, default_date, default_assignee_id, assignee_options}}`.
- Frontend renders `<ScheduleInlineStep>` — date picker + assignee picker, Save / Skip.
- Save → `PUT /agent-actions/{id}` with `due_date` + `assigned_to` + emits `handler.applied`.
- Skip → emits `handler.abandoned`.

### 4.4 What happens for entity types without a configured handler

Proposal accepts for `estimate`, `case_link`, `equipment_item`, etc. that have no org-configured handler → `next_step: null`. Frontend shows no inline step. Current behavior unchanged.

Phase 4 does NOT configure handlers for non-`job` entity types. Adding them later is additive — new row in `post_creation_handlers` map + new frontend component.

## 5. Data model

### 5.1 New table

```sql
CREATE TABLE org_workflow_config (
    organization_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    post_creation_handlers JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- e.g. {"job": "assign_inline"}
    default_assignee_strategy JSONB NOT NULL DEFAULT '{"strategy":"last_used_by_user"}'::jsonb,
    -- e.g. {"strategy":"last_used_by_user","fallback_user_id":"<uuid>"}
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by_user_id UUID REFERENCES users(id)
);
```

Row created lazily on first read — orgs without a row fall through to **system defaults** (below), so migration doesn't have to seed every existing org.

### 5.2 System defaults (what a brand-new org sees)

```jsonc
{
  "post_creation_handlers": {
    "job": "assign_inline"
  },
  "default_assignee_strategy": {
    "strategy": "last_used_by_user",
    "fallback_user_id": null
  }
}
```

Chosen because `assign_inline` covers both solo operators (me assigning to me) and small teams (Sapphire-style). `unassigned_pool` and `schedule_inline` are explicit opt-ins via settings.

## 6. Settings UI

Location: `/settings/workflows` (owner + admin only; other roles see read-only or 403).

Layout:
```
How new jobs get handled
─────────────────────────
( ) Schedule right away
    Best for coordinator-driven teams. Pick a date + assignee
    before the job enters the schedule.

(•) Create and assign
    Best for flexible schedules. Job lands immediately; just
    pick who takes it.
    ← Currently selected

( ) Send to unassigned pool
    Best for dispatch-style teams. Dispatcher picks jobs off
    the queue as they're ready.

  Default assignee strategy
  ─────────────────────────
  ( ) Always ask (no default)
  (•) Remember who I last assigned
  ( ) Default to <user picker>
```

**Rules (from the master plan — non-negotiable):**
- NO engineer vocabulary (`assign_inline` etc.) in the UI.
- NO enum dropdowns for the primary choice — radio cards with descriptions.
- NO "advanced" panel — if a setting needs to be hidden, design the choice differently.
- "Based on your activity, [X] is recommended" callout when workflow_observer (Phase 6) has data. Not shipping in Phase 4.

Endpoints:
- `GET /v1/workflow/config` — returns current config (computed w/ system defaults).
- `PUT /v1/workflow/config` — owner/admin only, validates handler names against registry, emits `workflow_config.changed`.

## 7. Events

Adds three entries to `docs/event-taxonomy.md` §8 (workflow subsystem, newly introduced):

| Event | Level | Refs | Payload |
|---|---|---|---|
| `workflow_config.changed` | user_action | — | `{before, after}` — both JSONB snapshots |
| `handler.applied` | user_action | `entity_id`, `entity_type` | `{handler: "<name>", input}` where input is the user's picker values |
| `handler.abandoned` | user_action | `entity_id`, `entity_type` | `{handler: "<name>", reason: "skip" \| "dismiss"}` |

Phase 6 (workflow_observer) reads these three events + `proposal.accepted` to propose config changes. No schema-level reason to reject these event names (verified against §8 slots).

## 8. Rollout sequence

1. **Migration**: `org_workflow_config` table. Nullable FK, default JSONB values. No per-org backfill (lazy read).
2. **Handler registry** `src/services/workflow/handlers.py` with `WorkflowHandler` protocol + `HANDLERS` dict. Ship `assign_inline`, `unassigned_pool`, `schedule_inline` as concrete classes. Unit tests for each handler's `next_step_for` output shape.
3. **Workflow config service** `src/services/workflow/config_service.py`: `get_or_default(org_id)`, `put(org_id, config, actor)` + event emit. Unit tests + org-isolation test.
4. **API**: `GET/PUT /v1/workflow/config` (owner+admin gated). Contract test: unknown handler name → 422 with the registry list.
5. **Accept-response extension**: add `next_step` field to `POST /v1/proposals/{id}/accept` response. `workflow_service.resolve_next_step()` runs after accept, never rolls back accept on failure. Integration test: accept a job proposal → asserts `next_step.kind == "assign_inline"`.
6. **Frontend settings page**: `/settings/workflows` route + component. Radio cards for the 3 options + the default-assignee sub-picker. Vitest: clicking an option dispatches PUT + updates local state.
7. **Frontend step components**: `<AssignInlineStep>`, `<UnassignedPoolStep>`, `<ScheduleInlineStep>`. Each owns its local state, calls its apply endpoint on Save, emits `handler.applied`/`handler.abandoned` via `lib/events`. Vitest for each.
8. **Wire step components into ProposalCard + ProposalCardMini**: on successful accept, look at `next_step.kind`, look it up in the component registry, render it in a popover/inline region below the card. Handle unknown kinds (warn + no-op).
9. **Sapphire dogfood**: flag is off by default → Sapphire gets no behavior change until a row is added to `org_workflow_config`. Turn on with default config (`job → assign_inline`) and iterate on UX.
10. **Measurement**: count `handler.applied` vs `handler.abandoned` after 1 week. If abandoned > applied on any handler, that's signal for Phase 6 to act on later.

## 9. Definition of Done

1. `org_workflow_config` table exists; lazy-read returns system defaults when row missing.
2. Handler registry has 3 concrete handlers; `WorkflowHandler` protocol enforced via unit tests (each handler's `next_step_for` returns a `NextStep`-shaped dict or None).
3. `POST /v1/proposals/{id}/accept` returns `next_step` in the response; absence → null, not missing key.
4. A handler lookup failure does NOT roll back the accept — creation is non-refundable, step is augmentation. Covered by a fault-injection test.
5. `GET/PUT /v1/workflow/config` exists, owner+admin gated; unknown handler name rejected with 422 + registry list.
6. Settings surface at `/settings/workflows` renders the 3 radio cards with plain-language copy; no enum names, no advanced panel; keyboard-navigable; mobile-stackable.
7. `AssignInlineStep`, `UnassignedPoolStep`, `ScheduleInlineStep` all handle Save + Skip, emit the right event, and revert to the card on success.
8. ProposalCard + ProposalCardMini render the `next_step` component from the registry; unknown `kind` logs a warning and renders nothing.
9. R1 enforcer passes: `workflow_config.changed`, `handler.applied`, `handler.abandoned` added to the taxonomy in the same commit as the first emit site.
10. Vitest: at least one happy-path + one abandon test for each step component. Backend pytest: registry dispatch test, accept-response shape test, config endpoint auth test.
11. Sapphire dogfood: flag on, accept a job proposal → assignee picker appears → save → `handler.applied` event visible in `/admin/platform/events`.

## 10. Resolved decisions

1. **Handler wiring site = router, not service.** Keeps `ProposalService` ignorant of workflow config; clean separation. Also means `resolve_next_step` can fail soft without rolling back the entity creation (creation is non-refundable; step is augmentation).
2. **`NextStep` instead of `ui_spec()` + `apply()` on the backend.** Master plan hints at both. In practice every "apply" call already has a canonical service path (`update_action`, `set_assignee`, etc.) — the handler doesn't need to own the mutation, only describe the step. Backend stays lean; frontend component-registry does the rest.
3. **3 handlers in Phase 4, not 5.** `auto_assign_proximity` needs OR-Tools route integration (separate scope); `coordinator_notification` needs notification-design decisions not yet made. Both can ship in Phase 4b after observation data informs the design.
4. **Entity types in Phase 4: `job` only.** `estimate`, `case_link`, `equipment_item` get `next_step: null`. Adding handlers for other types is additive (new row in config map + new component); no backend refactor needed later.
5. **Default = `assign_inline`.** Covers solo + small teams. Sapphire matches. Explicit opt-in for the other two keeps the zero-config new-org path sane.
6. **`default_assignee_strategy` is org-level, not per-user.** Brian prefers last-used-by-user, Kim might prefer always-ask — that's per-user preference, Phase 4b. Phase 4 ships org-level only.
7. **Router-side lookup inside a single DB session.** `resolve_next_step` uses the same `db` as the accept. Keeps handler queries (assignee list, last-used lookup) in-transaction readable.
8. **System defaults live in code, not a seeded row.** Lazy-read `get_or_default` returns the hardcoded shape when row missing. Migration doesn't touch existing orgs; first `PUT` creates the row.
9. **`handler.abandoned` fires on dismiss-without-save, NOT on failed save.** Save failures are `handler.apply_failed` territory — Phase 4 doesn't need this event yet; skip until Phase 6 shows we need it.
10. **Phase 4 scope only covers proposal-acceptance paths.** Manual "Add Job" from case detail, DeepBlue tool-created jobs, scheduler-created jobs — out of scope. Phase 5 (unify existing agents into proposals) carries those paths onto the proposal rails, at which point Phase 4's handler hook covers them automatically.

## 11. Open questions for Brian before coding

1. **Settings surface permission.** Owner-only, or owner+admin? Other QP settings split on this. Manager/tech access = no (they don't touch workflow config).
2. **`unassigned_pool` surface.** If no one views the unassigned pool, does it functionally disappear? Today, unassigned jobs appear in the Cases list but not in a dedicated "queue" view. Phase 4 might need a simple `/jobs?assignee=unassigned` listing, or that may land in Phase 5.
3. **Default-assignee sub-picker scope.** The 3 handlers with an assignee picker all consult `default_assignee_strategy`. Do all 3 share one org-wide strategy, or does each handler carry its own? Simpler answer: one org-wide strategy (shipping).
4. **"Based on your activity, [X] is recommended" callout.** Phase 6 produces this data; Phase 4 ships without the callout. Confirm that's acceptable for Sapphire dogfood.
5. **Rollback scope if Sapphire hates the inline step.** Settings toggle → no behavior change needed (flag off = null `next_step`). No feature flag layer required; config-is-the-flag.

## 12. Scope estimate

Reassessed against Phase 1/2/3:

- Phase 1: 14 steps, ~3 weeks (big — foundation).
- Phase 2: 11 steps, ~1 week (clean abstraction).
- Phase 3: 10 steps, ~1 week backend + ~1 week frontend + ~1 week dogfood-iteration UX polish.
- **Phase 4 estimate: ~4 days backend, ~4 days frontend, ~3 days settings-page UX iteration.** Narrower than Phase 3 — fewer surfaces, but the settings UI is a new pattern (plain-language opinionated radio cards) that'll take an extra revision round to feel right.

Total: ~1.5 weeks elapsed with audit + deploy cycles.

---

Ready to start Step 1 (migration + handler registry scaffold) on Brian's go-ahead. Open questions above (§11) need a thumbs-up or adjustment first.
