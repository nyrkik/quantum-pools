# Phase 6 — `workflow_observer` agent

> Refinement spec produced by the per-phase gate. Master plan: `docs/ai-platform-plan.md` → Phase 6. Remove this file when the phase is shipped + archived.

## 1. Purpose

Phase 6 is where the product starts learning the **org**, not just the agents. Phase 1 captured the events. Phase 2 built the proposal primitive. Phases 3–5 made every agent route through proposals. The data we need to observe organizational behavior is now flowing into `platform_events` and `agent_proposals` — but nothing reads it back to propose changes.

Phase 6 introduces a single agent — `workflow_observer` — that runs daily per org, scans the last N days of events + proposal outcomes, and stages **meta-proposals** (proposals that change org defaults/config rather than create customer-facing entities). Admins accept/reject through the same `<ProposalCard>` UI; the observer learns from those accept/reject signals via `AgentLearningService` like every other agent.

**DNA alignment**: rule 3 explicitly ("the product learns the org"). Rule 2 (observer is itself a learning agent — its own meta-proposals feed corrections back). Rule 6 (compounds over time — admin configures less as observer learns more). Rule 5's spirit (meta-proposals never auto-apply — admin must accept).

## 2. Why now (vs. waiting)

- Sapphire has been the dogfood org since the AI Platform rollout started 2026-04-19. Eight days of `platform_events` + `agent_proposals` outcomes exist for a single org. That's not enough volume to draw conclusions, but it's enough to validate detector mechanics.
- Phase 6 detectors fail loudly if data is sparse — they're threshold-gated. Building them now and letting Sapphire's data accumulate produces real meta-proposals naturally as the threshold crosses. We don't have to wait for "more data" to *build*; we have to wait to *trust output*.
- Phase 7 (Sonar — dev-facing intelligence) is structurally similar (a daily-scan agent staging proposals). Phase 6 establishes the pattern; Phase 7 reuses it.

## 3. Scope

### In scope
- New agent `workflow_observer` with one daily APScheduler job per cluster (iterates orgs).
- Five pluggable detectors implementing a common `Detector` protocol.
- Each detector returns 0+ meta-proposal payloads; the agent stages them via `ProposalService` exactly like any other proposal source.
- New entity_type `workflow_config` (handles nested JSONB targets the existing `org_config` creator can't, since `org_config` is whitelisted scalars only).
- Frontend dashboard widget on `/dashboard` listing pending workflow suggestions.
- Two new event types: `observer.scan_complete`, `meta_proposal.staged`.
- `workflow_observer` wired into `AgentLearningService` (its acceptance/rejection rate trains its own threshold tuning).
- Per-org per-detector mute list ("Never suggest this") in `org_workflow_config` JSONB.

### Out of scope (deferred)
- Weekly digest email to owner. Listed in master plan but defer to a follow-up: it's a notification surface, the dashboard widget already gets the work done, and shipping the email needs a template + scheduling cron that's pure additive surface area.
- Auto-applying meta-proposals at high confidence. Master plan explicitly says don't; we don't.
- A "workflow_observer settings" page. Mute list is editable from the proposal card itself ("Never suggest this") — no separate settings UI needed v1.
- Cross-org pattern detection ("orgs that look like Sapphire commonly do X"). That's Phase 8 territory (User-Sonar). v1 is per-org only.

## 4. Schema additions

Two changes, both small.

### 4.1 `org_workflow_config` — two new columns

```python
observer_mutes: Mapped[dict] = mapped_column(
    JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict,
)
# Shape: {"<detector_id>": {"muted_at": "<iso>", "muted_by_user_id": "<uuid>"}}
# Presence of a key = detector is muted for this org.

observer_thresholds: Mapped[dict] = mapped_column(
    JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict,
)
# Shape: {"<detector_id>": <float>}
# Persisted self-tuned thresholds; absent key = use detector's default.
```

Alembic migration: `add_observer_state_to_org_workflow_config`. Idempotent server_default keeps existing rows valid.

### 4.2 `workflow_config` entity_type (new proposal creator)

New file `app/src/services/proposals/creators/workflow_config.py`. Schema:

```python
class WorkflowConfigProposalPayload(BaseModel):
    target: Literal["post_creation_handlers", "default_assignee_strategy"]
    # JSON Patch op applied atomically to the JSONB column.
    op: Literal["set", "merge"]
    value: Any  # validated per-target by the creator
```

The creator dispatches to `OrgWorkflowConfigService.apply_patch(target, op, value)`. We intentionally *don't* extend `org_config` because:
- `org_config` is whitelisted scalars (per its docstring). Bending it for nested JSONB would force every existing call site to handle the new shape.
- Separating the entity_types means the proposal card UI can render workflow_config diffs differently (show before/after JSON) without conditional logic.

## 5. Architecture

### 5.1 Detector protocol

```python
# app/src/services/agents/workflow_observer/detector.py
class DetectorContext(NamedTuple):
    org_id: str
    window_start: datetime  # default: 14 days ago
    window_end: datetime    # default: now
    db: AsyncSession

class Detector(Protocol):
    detector_id: str  # stable; used in mute list
    description: str  # one sentence; surfaces on the proposal card

    async def scan(self, ctx: DetectorContext) -> list[MetaProposal]:
        ...

@dataclass
class MetaProposal:
    detector_id: str
    confidence: float           # 0.0–1.0
    summary: str                # one-sentence human explanation
    evidence: dict              # observed counts/ratios for the proposal card "why"
    payload: dict               # WorkflowConfigProposalPayload-shaped
```

### 5.2 `WorkflowObserverAgent`

```python
# app/src/services/agents/workflow_observer/agent.py
class WorkflowObserverAgent:
    DETECTORS: list[Detector] = [
        DefaultAssigneeDetector(),
        HandlerMismatchDetector(),
        ClassificationOverrideDetector(),
        TimeOfDayDetector(),
        RejectionClusterDetector(),
    ]
    DEFAULT_CONFIDENCE_THRESHOLD = 0.90

    async def scan_org(self, org_id: str, db: AsyncSession) -> ScanResult:
        # 1. Build context (14-day window).
        # 2. Load org's observer_mutes from org_workflow_config.
        # 3. Load last 90d of `workflow_observer` corrections via AgentLearningService
        #    to adjust per-detector thresholds (rejection rate >30% → threshold +0.05).
        # 4. For each unmuted detector: run scan(), filter by threshold, dedupe
        #    against existing `staged` workflow_config proposals (same target+payload).
        # 5. Stage surviving meta-proposals via ProposalService.stage() with
        #    actor_agent_type="workflow_observer".
        # 6. Emit observer.scan_complete with counts; emit meta_proposal.staged
        #    per stage (already emitted by ProposalService — verify, don't double).
```

### 5.3 Daily job

Add to `app.py` lifespan alongside existing jobs:

```python
scheduler.add_job(
    _run_workflow_observer_sweep,
    CronTrigger(hour=6, minute=0, timezone="UTC"),  # ~11pm Pacific
    id="workflow_observer_sweep",
)
```

Sweep iterates `Organization` rows, calls `WorkflowObserverAgent.scan_org(org_id)`. Per-org failures captured to Sentry, never block the next org.

## 6. The five detectors

Each detector keeps its query in a single async method, returns a list of MetaProposals or `[]`. All queries scope by `organization_id` and the time window.

### 6.1 `DefaultAssigneeDetector`
- **Observes**: `agent_proposal.accepted` events for `entity_type=job` over the window.
- **Pattern**: ≥80% of accepts route the resulting job to the same user.
- **Proposal**: `target=default_assignee_strategy`, `op=set`, `value={"strategy": "fixed_user", "user_id": "<uuid>"}`.
- **Confidence**: ratio of dominant assignee × log10(sample_size / 5), capped at 1.0. Requires ≥10 accepts in window.

### 6.2 `HandlerMismatchDetector`
- **Observes**: post-creation handler `next_step` rendered (event from Phase 4) vs. user action within 60s — did they engage the handler UI or navigate away?
- **Pattern**: >70% abandonment rate for a configured handler over ≥20 occurrences.
- **Proposal**: `target=post_creation_handlers`, `op=merge`, `value={"<entity_type>": "none"}` or the abandonment-implied alternative (e.g., user navigated to schedule page → suggest `schedule_inline`).
- **Confidence**: `1 - (engaged_count / total_count)`, gated at ≥20 samples.

### 6.3 `ClassificationOverrideDetector`
- **Observes**: `agent_correction` rows for `agent_type=email_classifier` where user changed category X → category Y.
- **Pattern**: same X→Y override ≥5 times in the window for the same sender_domain or matched_customer.
- **Proposal**: stages a new `inbox_rule` proposal — *not* a workflow_config change.
- **Dependency**: `inbox_rule` proposal creator does not exist yet; build it in this phase. Scope (MVP):
  - Schema: `{conditions: [...], actions: [...]}` matching the existing `inbox_rules` JSONB shape.
  - Creator delegates to `InboxRulesService.create()` on accept — re-uses existing validation, coverage check, and apply_to_existing logic. No re-validation in the creator.
  - Proposal card renders the rule in plain language ("Mail from `@acme.com` → category=billing") via a small renderer; falls back to JSON for shapes the renderer doesn't recognize.
- **Detector emits**: `entity_type="inbox_rule"`. The `Detector` protocol must allow this — `MetaProposal.entity_type` field defaults to `"workflow_config"` but each detector can override.
- **Confidence**: rate × min(1, count/10). Requires ≥5 overrides.

### 6.4 `TimeOfDayDetector`
- **Observes**: `agent_proposal.accepted`, `agent_thread.dismissed`, etc. — any "user did inbox triage work" event — bucketed by hour-of-day.
- **Pattern**: >80% of triage activity in a 4-hour window.
- **Proposal**: `target=post_creation_handlers`, `op=merge`, `value={"_observer": {"focus_window": [start_hour, end_hour]}}`. v1 just records the observation; UI surfaces it on the dashboard ("Brian does inbox triage 6am–10am — should we mute non-urgent notifications outside that window?"). Action ties to v2.
- **Confidence**: bucket density × log(samples).
- **NOTE**: this detector is the lowest-value one for v1 — surfaces an observation but its accept-side change is weak. Consider deferring to v1.5.

### 6.5 `RejectionClusterDetector`
- **Observes**: `agent_proposal.rejected_permanently` events (entity_type=any AI agent's output).
- **Pattern**: ≥3 rejections clustered on the same `actor_agent_type` + same `payload.classification` (or equivalent payload key) in the window.
- **Proposal**: this detector doesn't produce a config change. It produces an **alerting meta-proposal** for the agent owner: "email_drafter rejected on `category=billing` 4 times this week. Likely systemic — review recent corrections." Surfaces on the workflow widget but accept = "Acknowledged" (no entity created), reject = "Not actionable."
- **Confidence**: cluster_size / total_rejections_for_agent.
- **NOTE**: the meta-proposal mechanism here is fuzzy. Specifically: there's no clean entity_type for "alert that doesn't change config." Either:
  - Add an entity_type `observer_alert` with no creator (accept = ack only).
  - Or skip this detector for v1, add when Phase 7 (Sonar) needs the same primitive — Sonar has the same issue and the right design likely emerges there.
  - **v1 decision**: skip. Build in v1.1 with Phase 7's pattern.

### v1 detector roster (after the notes above)
1. ✅ DefaultAssigneeDetector
2. ✅ HandlerMismatchDetector
3. ✅ ClassificationOverrideDetector (emits `inbox_rule`, not workflow_config)
4. ⏸️ TimeOfDayDetector — defer to v1.5
5. ⏸️ RejectionClusterDetector — defer to v1.1 (alongside Phase 7)

Three detectors v1. Conservative is right: master plan explicitly says "Better to miss a valid suggestion than to spam."

## 7. Anti-spam discipline

- **Threshold gate**: 0.90 default; per-detector override allowed.
- **Sample-size gate**: every detector requires a minimum N (≥10 or ≥20 — see each detector). Below N → no proposal regardless of ratio.
- **Dedup**: before staging, query existing `staged` proposals with same detector_id + payload signature; skip if present.
- **Mute list**: "Never suggest this" on a proposal card writes the detector_id to `org_workflow_config.observer_mutes`. Future scans skip the detector for that org. Brian (or the org owner) can clear via the same UI ("Re-enable suggestions").
- **Self-learning** (symmetric): `AgentLearningService` tracks `workflow_observer` corrections per detector_id. Each scan reads the last 30 days of accept/reject/edit signals. If reject rate >30% → bump that detector's threshold +0.05. If accept rate >70% → lower by 0.05. Range capped at [default, 0.99]. Threshold is per-org per-detector and persisted alongside `observer_mutes` on `org_workflow_config`. This is the *only* automatic tuning — never auto-apply.
- **No re-staging within 14 days**: if a meta-proposal was rejected_permanently in the last 14 days, the same payload signature won't re-stage. Prevents nag loops.

## 8. Frontend surfaces

### 8.1 Dashboard widget — "Workflow suggestions"
- Location: `/dashboard`, below existing widgets.
- Shows up to 5 most-recent staged `workflow_config` + `inbox_rule` (when staged by `actor_agent_type=workflow_observer`) proposals.
- Each row uses the existing `<ProposalCard>` (no new component) with the standard Accept / Edit / Reject / Never-suggest controls.
- Empty state: "No workflow suggestions yet. The product learns from your activity over time."
- Gated by new `workflow.review` slug. Reasoning: Phase 6 surface area (default assignees, post-creation handlers, future detectors) is broader than inbox configuration; reusing `inbox.manage` would be a category error. Owner + admin presets get the slug by default. Add to the 60-slug system as slug 61.

### 8.2 No "/settings/workflows" addition
Per `feedback_phase4_workflows_settings_is_vestigial.md`, that page is vestigial. Don't add Phase 6 surfaces there. The dashboard widget is the surface.

### 8.3 Notifications
v1: dashboard widget only. Defer email digest. If owner wants push, the existing event `meta_proposal.staged` already fires — they can wire ntfy via inbox-rules pointed at the event stream once Phase 6 events flow.

## 9. Events

Two new types, register in `event-taxonomy.md`:

| Event | Level | Emitted by | Payload |
|---|---|---|---|
| `observer.scan_complete` | system | `_run_workflow_observer_sweep` per org | `{org_id, detectors_run, proposals_staged, duration_ms}` |
| `meta_proposal.staged` | system | already emitted by `ProposalService.stage` as `agent_proposal.staged` — DO NOT add a new type. Reuse existing event with `actor_agent_type=workflow_observer` as the discriminator. |

**Decision**: drop `meta_proposal.staged` from the master plan. Reusing `agent_proposal.staged` is correct — meta-proposals are proposals, not a separate primitive. Update the master plan to remove this event.

## 10. Rollout steps

1. Alembic migration: `org_workflow_config.observer_mutes` JSONB + `observer_thresholds` JSONB (per-detector tuned thresholds).
2. New entity_type `workflow_config` + creator + ALLOWED_TARGETS whitelist.
3. New entity_type `inbox_rule` MVP creator: payload schema = `{conditions, actions}`; on accept, delegates to `InboxRulesService.create()`. Plain-language renderer for the proposal card with JSON fallback.
4. Permission slug `workflow.review` added to slug registry; owner + admin presets updated.
5. `WorkflowObserverAgent` skeleton + `Detector` protocol (with `MetaProposal.entity_type` field) + scan harness — verify orchestration with empty detector list: `observer.scan_complete` fires, dedup query runs, mute-list filter applies, threshold persistence works.
6. `DefaultAssigneeDetector` + tests (synthetic events, threshold edge cases, sample-size gate).
7. `HandlerMismatchDetector` + tests.
8. `ClassificationOverrideDetector` + tests (verify it emits `inbox_rule` entity_type and the staged proposal accepts cleanly through `InboxRulesService`).
9. Symmetric self-tuning: read 30d corrections via AgentLearningService, compute per-detector accept/reject rate, persist adjusted threshold to `observer_thresholds`. Tests cover both bump and snap-back.
10. Mute-list logic: read mutes in `scan_org`, "Never suggest this" button writes mute, "Re-enable" clears it. No separate settings UI.
11. APScheduler job in `app.py` lifespan (06:00 UTC daily); per-org failures captured to Sentry, never block subsequent orgs.
12. Frontend: dashboard widget gated by `workflow.review`; reuses `<ProposalCard>`; renders both `workflow_config` (JSON diff) and `inbox_rule` (plain-language) proposals.
13. `docs/event-taxonomy.md`: register `observer.scan_complete`. Confirm `agent_proposal.staged` already covers meta_proposal.staged with the `actor_agent_type` discriminator.
14. R5 + R7 audits pass clean. R5 baseline updated if needed.
15. Backfill Sapphire: manually invoke `scan_org(sapphire_org_id)` to see what surfaces given current platform_events. Tune defaults based on output.

## 11. Definition of done

- [ ] Migration applied; `observer_mutes` and `observer_thresholds` columns exist on `org_workflow_config` with `'{}'::jsonb` defaults.
- [ ] `workflow_config` entity_type registered in proposal creators registry; ALLOWED_TARGETS whitelist enforced.
- [ ] `inbox_rule` MVP entity_type creator registered; on accept, delegates to `InboxRulesService.create()`; plain-language renderer renders the existing condition+action shapes for the dashboard widget.
- [ ] `workflow.review` permission slug added to the slug registry and granted to owner + admin presets.
- [ ] Three v1 detectors (`DefaultAssigneeDetector`, `HandlerMismatchDetector`, `ClassificationOverrideDetector`) implemented with unit tests covering: threshold gate, sample-size gate, dedup against existing staged proposals, mute-list skip.
- [ ] AgentLearningService wired: `record_correction` fires on accept/reject/edit of `workflow_observer` proposals; symmetric self-tuning verified by test (both bump on >30% reject and lower on >70% accept; capped at default and 0.99).
- [ ] APScheduler job registered in `app.py` lifespan; logs confirm `Scheduler started` line includes `workflow_observer_sweep`.
- [ ] Manual `scan_org(sapphire_org_id)` produces zero false positives on Sapphire's current data (verify by inspecting staged proposals; reject any nonsense and tune defaults).
- [ ] Dashboard widget renders staged observer proposals; Accept/Reject/Edit/Never-suggest all functional; permission gated by `workflow.review`.
- [ ] `observer.scan_complete` event registered in `docs/event-taxonomy.md` and emitted per scan.
- [ ] No new `meta_proposal.staged` event — confirmed `agent_proposal.staged` is reused with `actor_agent_type=workflow_observer` discriminator.
- [ ] R7 audit + R5 audit pass clean (no `.draft_response` regressions, no event-emit-without-taxonomy drift). R5 baseline updated if needed.
- [ ] Two weeks post-deploy: at least one Sapphire-staged meta-proposal that Brian agrees is correct. (This is observation, not a code DoD — track separately.)

## 12. Open questions

- **`workflow.review` slug or reuse `inbox.manage`?** Spec says reuse to avoid permission sprawl. Confirm in implementation when wiring the gate.
- **Per-detector window override?** Some patterns may need >14 days to surface (e.g., default-assignee on a low-volume org). v1 assumes 14d uniform; if a detector under-fires on Sapphire, allow per-detector override before adding more detectors.
- **What kicks the observer for a brand-new org?** v1: nothing. Daily cron picks them up at the next 06:00 UTC. Acceptable — the observer needs data anyway.
- **Should the dashboard widget show muted detectors anywhere?** v1: no — once muted, gone. If admins regret, they can clear via API or DB. Add UI surface only if requested.

## 13. Estimated scope

~8–12 working days, honest count:
- Migration + schema + workflow_config creator: 1 day
- inbox_rule MVP creator (delegates to InboxRulesService on accept) + plain-language renderer: 1–2 days
- WorkflowObserverAgent harness + Detector protocol + dedup + mute-list logic: 1–2 days
- 3 detectors (DefaultAssignee, HandlerMismatch, ClassificationOverride) + unit tests: 3–4 days
- Symmetric self-tuning thresholds + AgentLearningService wiring + tests: 1 day
- APScheduler job + Sentry per-org failure capture + observer.scan_complete event: 0.5 day
- Dashboard widget + workflow.review slug + permission gating: 1–2 days
- Sapphire backfill + threshold tuning + DoD verification: 1 day

Master plan said ~3 weeks; we're shorter because (a) deferring 2 detectors, (b) skipping the digest email, (c) reusing `<ProposalCard>`. The inbox_rule creator is real new work that the master plan didn't itemize but Phase 6 needs.
