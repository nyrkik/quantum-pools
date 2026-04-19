# Phase 2 — `agent_proposals` system

> Detailed spec produced by the per-phase refinement gate. Master plan section: `docs/ai-platform-plan.md` → Phase 2. Remove this file when the phase is shipped + archived (like `docs/ai-platform-phase-1.md` will be).

## 1. Purpose

Every AI suggestion in QP — a drafted email reply, a proposed job, an estimate line-item set, an org-config recommendation, a DeepBlue tool-use confirmation — becomes a first-class record in one table (`agent_proposals`) managed by one service (`ProposalService`) and surfaced through one UI component (`ProposalCard`).

This is the structural enforcement of DNA rule 2 ("every agent learns") and rule 5 ("AI never commits to customer"). When learning + staged-action discipline moves from "remember to call the thing" to "it's impossible to bypass," the accuracy moat compounds.

Phase 1 built the nervous system (events). Phase 2 builds the decision surface (proposals). Phases 3-7 plug into both.

## 2. Environment facts (verified 2026-04-19)

- Phase 1 shipped. `platform_events` stream is live. 7 new `proposal.*` event types are documented in `docs/event-taxonomy.md` §8.9 already (Phase 1 wrote the taxonomy ahead).
- `AgentLearningService.record_correction()` exists and works. Phase 2 inserts into `agent_corrections` via this service (not direct DB writes).
- 8 DeepBlue `requires_confirmation` sites exist in 5 tool files: `tools_customer.py`, `tools_chemistry.py`, `tools_operations.py`, `tools_communication.py`, `tools_equipment.py`. Engine prompt + UI cards consume these.
- `AgentActionService.add_job()` and `InvoiceService.create()` are canonical entity creators usable from Phase 2's registry.
- The Step 13 enforcer (`app/scripts/audit_event_discipline.py`) blocks any proposal-related emit that skips the taxonomy.

## 3. What this phase ships

- **New table** `agent_proposals` (schema in §4).
- **`ProposalService`** with `stage / accept / edit_and_accept / reject / expire_stale / supersede`.
- **Entity-type registry** mapping `entity_type` strings → creator functions, living in a single file per entity_type (not a mega-dict).
- **Learning bridge**: every resolve atomically writes `agent_corrections` via `AgentLearningService`.
- **Event emission**: all 7 `proposal.*` event types wired via `PlatformEventService.emit`.
- **DeepBlue migration**: 8 tool sites convert from `requires_confirmation` payloads to `ProposalService.stage()`.
- **Frontend `ProposalCard`**: generic card with entity-type dispatch for rendering + actions.
- **APScheduler job**: daily `expire_stale(age_days=30)` sweep.
- **Admin endpoint**: `GET /v1/admin/platform/proposals` for triage + audit (cross-org, platform-admin gated, mirroring events endpoint).
- **Tests**: service-level + one frontend test + integration test for one end-to-end flow (DeepBlue add_equipment → proposal → accept → entity exists).

## 4. Database

### 4.1 Migration

```sql
CREATE TABLE agent_proposals (
  id            VARCHAR(36) PRIMARY KEY,
  organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  agent_type    VARCHAR(50) NOT NULL,        -- "inbox_summarizer" | "workflow_observer" | "deepblue" | etc.
  entity_type   VARCHAR(50) NOT NULL,        -- "job" | "estimate" | "equipment_item" | "org_config" | etc.
  source_type   VARCHAR(50) NOT NULL,        -- "agent_thread" | "visit" | "observation_batch" | etc.
  source_id     VARCHAR(36),                 -- reference to source_type's table; nullable for org-wide proposals
  proposed_payload JSONB NOT NULL,           -- fields that would commit
  confidence    REAL,                        -- 0..1, agent self-report
  status        VARCHAR(20) NOT NULL DEFAULT 'staged',  -- staged | accepted | edited | rejected | expired | superseded
  rejected_permanently BOOLEAN NOT NULL DEFAULT false,
  superseded_by_id VARCHAR(36) REFERENCES agent_proposals(id),
  outcome_entity_type VARCHAR(50),           -- filled on accept/edit
  outcome_entity_id   VARCHAR(36),
  user_delta    JSONB,                       -- diff if edited_and_accepted
  resolved_at   TIMESTAMPTZ,
  resolved_by_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
  resolution_note TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_agent_proposals_org_status_created
  ON agent_proposals (organization_id, status, created_at DESC);
CREATE INDEX ix_agent_proposals_source
  ON agent_proposals (source_type, source_id);
CREATE INDEX ix_agent_proposals_agent_status
  ON agent_proposals (agent_type, status);
```

**Not partitioned** — proposals are low-cardinality relative to events (expect ≤100/day/org at peak). Partitioning would be premature.

### 4.2 Why not `updated_at` / `outcome_entity` on FK?
`outcome_entity_id` references many tables (`agent_actions`, `invoices`, `equipment_items`, etc.) so it can't be a single-target FK. We store the (type, id) pair and validate at write time.

## 5. Service layer — `ProposalService`

### 5.1 File & class

`app/src/services/proposals/proposal_service.py`:

```python
class ProposalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def stage(
        self,
        *,
        org_id: str,
        agent_type: str,                  # must match an AgentLearningService constant
        entity_type: str,                 # must be in ENTITY_REGISTRY
        source_type: str,
        source_id: str | None,
        proposed_payload: dict,
        confidence: float | None = None,
        input_context: str | None = None, # for learning record
    ) -> AgentProposal: ...

    async def accept(
        self, *, proposal_id: str, actor: Actor,
    ) -> tuple[AgentProposal, Any]: ...

    async def edit_and_accept(
        self, *, proposal_id: str, actor: Actor,
        edited_payload: dict, note: str | None = None,
    ) -> tuple[AgentProposal, Any]: ...

    async def reject(
        self, *, proposal_id: str, actor: Actor,
        permanently: bool = False, note: str | None = None,
    ) -> AgentProposal: ...

    async def supersede(
        self, *, old_proposal_id: str, new_payload: dict,
        new_confidence: float | None = None,
    ) -> AgentProposal: ...

    async def expire_stale(self, age_days: int = 30) -> int: ...
```

### 5.2 Contract details

**`stage`**:
1. Validate `entity_type` against `ENTITY_REGISTRY` keys. Unknown → `ValueError` (caller bug; no graceful fallback — taxonomy discipline).
2. Validate `proposed_payload` against the entity_type's schema (Pydantic model per entity type).
3. Insert proposal row with `status=staged`.
4. Emit `proposal.staged` event. `entity_refs = {proposal_id, source_id?, customer_id?}`. Payload: `{agent_type, entity_type, confidence, source_type}`.
5. Fail-soft on emit (event stream is authoritative but not blocking).

**`accept`** (atomically, single transaction):
1. Load proposal; 400 if not `staged`.
2. Look up creator via `ENTITY_REGISTRY[entity_type]`.
3. Call creator with `proposed_payload` + org_id + actor.
4. Update proposal: `status=accepted`, `outcome_entity_type/id`, `resolved_at/_by`.
5. Via `AgentLearningService.record_correction(correction_type="acceptance", ...)`.
6. Emit `proposal.accepted`.
7. If creator raises → rollback entire transaction (proposal stays `staged`), log error, emit `agent.error`.

**`edit_and_accept`**: same as accept but:
- Caller passes `edited_payload`.
- Service computes `user_delta` — a **JSON patch** (RFC 6902) between `proposed_payload` and `edited_payload`. Not a deep-equality diff; the patch format is what Sonar actually wants.
- `status=edited`, `user_delta=<patch>`.
- Learning record uses `correction_type="edit"`, `original_output=json(proposed_payload)`, `corrected_output=json(edited_payload)`.
- Emit `proposal.edited`.

**`reject`**:
- `status=rejected`, `rejected_permanently` set if requested.
- Learning record: `correction_type="rejection"`. If permanent, stamp `input_context` so similar future proposals can be scored down.
- Emit `proposal.rejected` (default) or `proposal.rejected_permanently`.

**`supersede`**:
- Creates NEW proposal for the same source + entity_type.
- Old proposal: `status=superseded`, `superseded_by_id=new.id`.
- Old's learning record: skipped (no user action).
- Emit `proposal.superseded` referencing both.

**`expire_stale`**:
- Marks proposals older than `age_days` where `status=staged`.
- Learning record per-expired: `correction_type="rejection"`, `note="auto_expired"`.
- Emits `proposal.expired` per row.
- Single APScheduler job at 04:00 UTC daily.

### 5.3 `rejected_permanently` semantics

Ambiguous in the master plan. Resolution: "permanent rejection" scopes by `(agent_type, entity_type, input_context)`. On next stage from the same agent with same input_context, `ProposalService.stage` does NOT block — that's a different architectural layer. Instead, the learning lesson includes "user permanently rejected proposal <N> for this context" so the agent's next prompt incorporates that signal. Blocking would be brittle (input_context text changes slightly → bypass); leaving it as a strong lesson is robust.

### 5.4 Conflict with live user edits

When `accept` tries to create a job but the target entity already exists (e.g., thread has a manually-created job in the meantime):
- Entity creator returns a "conflict" signal.
- Proposal marked `status=rejected`, `resolution_note="superseded_by_user_action"`.
- Emit `proposal.rejected` with `payload.reason="user_created_already"`.

## 6. Entity-type registry

### 6.1 Shape

Not a dict in the service file — a module per entity_type, each exposing a `create_from_proposal(payload, org_id, actor, db) -> entity`. Registration via import side-effect in `src/services/proposals/creators/__init__.py`:

```python
# src/services/proposals/creators/__init__.py
from . import job, estimate, equipment_item, org_config  # noqa

# src/services/proposals/registry.py
_REGISTRY: dict[str, Callable] = {}

def register(entity_type: str):
    def decorator(fn):
        _REGISTRY[entity_type] = fn
        return fn
    return decorator

def get_creator(entity_type: str) -> Callable:
    if entity_type not in _REGISTRY:
        raise ValueError(f"No creator registered for entity_type={entity_type!r}")
    return _REGISTRY[entity_type]
```

```python
# src/services/proposals/creators/job.py
@register("job")
async def create_job_from_proposal(payload: dict, org_id: str, actor: Actor, db):
    return await AgentActionService(db).add_job(
        org_id=org_id, actor=actor, source="proposal_accepted",
        action_type=payload["action_type"],
        description=payload["description"],
        ...,
    )
```

**Why per-file:** easier to add new entity types, each creator has its own schema-validation logic locally, imports stay minimal.

### 6.2 Payload schemas

Per entity_type, a Pydantic model in the same file. `stage()` validates against it before insert. Invalid payload → `ValidationError` at stage time, not accept time (catches agent bugs early).

### 6.3 Phase 2 scope: 4 entity types
1. `job` — via `AgentActionService.add_job()`
2. `estimate` — via `InvoiceService.create(..., document_type="estimate")`
3. `equipment_item` — via new canonical `EquipmentService.add_item()` (verify exists; if not, add minimal version)
4. `org_config` — via new `OrgConfigService.apply()` (new; needed for Phase 4 post-creation handlers)

Additional entity types (inbox summary, product_recommendation, customer_field_update, broadcast_email, chemical_reading, customer_note) come in later phases or as part of the DeepBlue migration.

## 7. DeepBlue migration

### 7.1 Scope
8 call sites across 5 files. Each returns a dict with `"requires_confirmation": True`. Migration:

1. At each call site, swap the return for:
   ```python
   proposal = await ProposalService(db).stage(
       org_id=ctx.organization_id,
       agent_type="deepblue",
       entity_type=<mapped>,
       source_type="deepblue_conversation",
       source_id=conv.id,
       proposed_payload=<the preview dict>,
       confidence=None,
   )
   return {"action": <action>, "proposal_id": proposal.id}
   ```

2. Frontend DeepBlue tool card: swap `requires_confirmation` check for `proposal_id` presence; render via `ProposalCard` with `entity_type` dispatch.

3. Remove the engine prompt block warning about `requires_confirmation` — the concept is gone.

### 7.2 Mapping table (tools → entity_types)

| Tool site | entity_type |
|---|---|
| `tools_equipment.add_equipment_to_pool` | `equipment_item` |
| `tools_communication.draft_broadcast_email` (3 variants) | `broadcast_email` (new) |
| `tools_communication` (fourth) | `broadcast_email` |
| `tools_chemistry.log_chemical_reading` | `chemical_reading` (new) |
| `tools_customer.update_customer_note` | `customer_note_update` (new) |
| `tools_operations` | TBD — inspect the 8th site |

"New" entity_types need their own creator file — count +5 beyond the scope-4 listed above. Adjusted scope: ~9 entity types for Phase 2, plus the migration.

## 8. Frontend

### 8.1 `ProposalCard` component

```tsx
<ProposalCard
  proposal={p}
  onAccept={...}
  onEditAndAccept={(edited) => ...}
  onReject={(permanent, note) => ...}
/>
```

Body renders via registry dispatch:
```tsx
const RENDERERS: Record<string, React.FC<{payload}>> = {
  job: JobProposalBody,
  estimate: EstimateProposalBody,
  equipment_item: EquipmentProposalBody,
  org_config: OrgConfigDiffBody,
  broadcast_email: BroadcastProposalBody,
  ...
};
```

Every renderer in its own file under `frontend/components/proposals/`.

### 8.2 "Edit & accept" flow

Not a per-entity inline editor. Instead, open the corresponding full editor (e.g., existing job editor, existing invoice editor) pre-populated with `proposed_payload` and a banner "Editing an AI proposal — accept when done." On save, the editor calls `edit_and_accept` instead of the normal create endpoint.

Rationale: rebuild no editors. Reuse what exists. Proposals aren't a UX island.

## 9. Events + taxonomy

All 7 `proposal.*` event types are already documented in `docs/event-taxonomy.md` §8.9. No taxonomy edits needed. Step 13 enforcer (R1) ensures emit matches doc.

## 10. Test plan

### Service-level (pytest)
- `test_proposal_service.py`:
  - stage: happy path + unknown entity_type raises + invalid payload raises
  - accept: creates target entity, writes agent_corrections, emits event
  - edit_and_accept: computes JSON patch correctly, learning record has both payloads
  - reject permanently: learning record stamped
  - supersede: old marked superseded, new created, old learning record NOT written
  - expire_stale: background sweep only affects `staged` older than N
  - creator raises → full rollback, proposal stays staged, `agent.error` emitted

### Integration
- `test_proposal_deepblue_e2e.py`: `add_equipment_to_pool` tool → proposal staged → accept via service → `equipment_item` row exists + proposal status=accepted + `proposal.accepted` event.

### Frontend (vitest)
- `ProposalCard.test.tsx`: renders correct body per entity_type, fires callbacks correctly, disables actions when resolved.

## 11. Rollout sequence

Each step commits + deploys independently. Step 13 enforcer gates every deploy.
**Audit discipline from Phase 1 applies**: after each step ships, run a live E2E verification + taxonomy-conformance check before moving on.

1. **Migration + `agent_proposals` table + model.** Enforcer unaffected.
2. **`ProposalService` skeleton + registry infra + JSON-patch helper.** No callers yet.
3. **Creators: job + estimate + equipment_item + org_config (scalar)** — each file + Pydantic schema + unit tests.
4. **Events: wire `proposal.*` emits into the service.** Taxonomy entries exist; R1 passes.
5. **⭐ Dogfood: migrate `add_equipment_to_pool` DeepBlue tool to the new flow.** Simplest tool (1 DB write, no side effects) tests the full chain end-to-end: DeepBlue tool → stage → accept → entity → events → learning. Any contract bug surfaces here while the service is still small, before 7 more tools depend on it.
6. **Expire-stale APScheduler job.** Daily 04:00 UTC.
7. **Admin endpoint** `GET /v1/admin/platform/proposals` — mirrors events endpoint shape.
8. **Frontend: `ProposalCard` + 4 initial renderers (job, estimate, equipment, org_config).** The equipment renderer replaces the DeepBlue add-equipment card that step 5 wired up.
9. **DeepBlue migration — remaining 7 tool sites** (tools_chemistry, tools_customer, tools_operations, tools_communication) each with a `ProposalCard` renderer (broadcast_email renderer surfaces "Send to N customers" per §14.4).
10. **Remove `requires_confirmation` from DeepBlue engine prompt + ad-hoc UI card code.** Net code reduction.
11. **Extend Step 13 enforcer with R6**: no `requires_confirmation` strings in `app/src/` outside explicitly deprecated code.
12. **Phase 2 DoD verification.**

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Entity creator raises mid-accept; proposal state diverges from reality | Single transaction — creator failure rolls back proposal update. Enforced by wrapping creator in the same `db` session, committing only at the end. |
| DeepBlue migration skips a tool file, leaving a `requires_confirmation` vestige | Step 13 enforcer already greps — add R6: "no `requires_confirmation` string in app/src outside deprecated code" (to add at the end of phase 2). |
| `rejected_permanently` is abused (user clicks reject-permanently by accident) | UI requires confirmation AlertDialog with clear wording. Backend stores `resolved_by_user_id` for audit. |
| JSON-patch diff is noisy for shallow edits | Use `jsonpatch` lib's `make_patch` which produces minimal patches. Accept some noise for correctness. |
| Proposal volume spikes (bad summarizer run stages 1k proposals) | Per-`(agent_type, org_id)` rate limit at `stage()`: max 50 staged proposals per hour per agent. Exceed → 429 + log + ntfy alert. |
| Conflict: proposal for a job that was manually created | Creator returns "conflict" signal → proposal auto-rejected with reason `user_created_already`. |
| Accepting a stale proposal (source state changed) | Service checks `source_id` still resolves to a valid entity; if not, reject with `reason=source_gone`. |

## 13. Phase 2 Definition of Done

Phase 2 ships when ALL true:

1. `agent_proposals` table exists with the §4.1 schema and 3 indexes.
2. `ProposalService` implements all 6 methods with unit test coverage.
3. 4 creators (job, estimate, equipment_item, org_config) registered and unit-tested, each with Pydantic payload schema.
4. Every resolve path atomically writes an `agent_corrections` row.
5. All 7 `proposal.*` events emit via `PlatformEventService.emit`.
6. APScheduler `expire_stale` job running daily at 04:00 UTC.
7. Admin endpoint `GET /v1/admin/platform/proposals` responds with cursor pagination + filters (agent_type, entity_type, status).
8. Frontend `ProposalCard` implemented with renderer dispatch + 4 initial renderers.
9. All 8 DeepBlue `requires_confirmation` call sites migrated to `ProposalService.stage()`.
10. DeepBlue engine prompt + UI no longer reference `requires_confirmation`.
11. Step 13 enforcer expanded with R6 (no stale `requires_confirmation` strings).
12. Test query: `SELECT entity_type, status, count(*) FROM agent_proposals GROUP BY 1,2` returns rows across ≥3 entity_types on Sapphire within a week of cutover.

## 14. Resolved decisions (2026-04-19 — Brian deferred to Claude's judgment, DNA-grounded)

1. **`org_config` scope**: Scalar only in Phase 2. Creator accepts `{key, value}` pairs for org-level scalar settings (`agent_enabled`, `event_retention_days`, etc.). Nested/structured config ships in Phase 4 when post-creation-handler requirements are understood. Rationale: speculative structure gets rewritten; build the registry plumbing now, let Phase 4 teach the schema.

2. **Edit & Accept UX**: Reuse existing full editors. Job editor + invoice editor + equipment editor open pre-populated with `proposed_payload`, banner reads "Editing an AI proposal — accept when done." On save, the editor calls `edit_and_accept` instead of the normal create endpoint. No inline proposal-specific forms. Preserves single-canonical-path + no new mental model.

3. **Rate limiting**: No hard block. Service emits ntfy alert (`QP proposal burst` priority=high, cooldown 1h) when a single agent stages >200 proposals for a single org within a rolling 1-hour window. Burst detection, not throttling.

4. **`broadcast_email` second confirm**: No modal. Instead, the `broadcast_email` `ProposalCard` renderer displays recipient count + subject prominently in the header, and the primary action button reads **"Send to {N} customers"** (not generic "Accept"). Informed consent at click-time. Matches "AI never commits to customer" without adding friction.

5. **Rollout order**: Migrate `add_equipment_to_pool` (simplest tool, 1 DB write, no side effects) as step 5 — dogfood the full chain (DeepBlue tool → stage → accept → entity → events → learning) before migrating the other 7 sites. Rest of DeepBlue migration stays at steps 8-9. Updated §11.

6. **Scope**: ~10 working days heads-down + audit-fix cycles ≈ **2 weeks elapsed** realistic. Audit-after-each-step discipline from Phase 1 applies.
