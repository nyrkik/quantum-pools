# Entity Connections Plan

**Status:** Phase 1 shipped 2026-04-14. Phase 2 not started.
**Goal:** Make every meaningful work artifact connectable to the ServiceCase hub, with manual link/unlink UI, line-item-level revenue attribution, physical-work connections, equipment axis, and discovery. Remove when phases 1-5 are complete.

## Problem

Today ServiceCase is the intended hub: jobs, threads, invoices, internal messages, and DeepBlue conversations all have a nullable `case_id` FK. But:

1. **No UI can attach or detach anything after creation.** The backend endpoint `POST /v1/cases/{id}/link` is live for jobs/threads/invoices but zero frontend code calls it. Internal messages and DeepBlue convos have no link endpoint at all.
2. **Physical work (visits, inspections, equipment, measurements) is disconnected from cases.** Visits link to property only — the actual work of the case never reaches the case timeline.
3. **Revenue attribution is forced 1:1 per invoice.** An invoice that consolidates work from two cases can't attribute revenue correctly, breaking per-case profitability, AR, and collections reports.
4. **There are no peer relationships.** Job↔Job dependencies, Case↔Case siblings, Case↔Equipment warranty trails are all tracked informally in descriptions and comments.

Result: users can't "assign that estimate to the Pinebrook pool motor case" — and when the app *does* connect things silently, users don't know they can override or inspect the connection. Profitability dashboards silently overcount when any invoice spans cases.

## Non-Goals

- Not adding connection UI for comments, tasks, checklist entries, notifications, payments. Those are strictly owned by their parent and would be noise if exposed.
- Not refactoring existing auto-links (AI job extraction, job_invoices M2M). Those stay.
- Not rebuilding the case detail page — we extend it.
- Not M2M-ing estimates or threads or jobs to cases. An estimate/thread/job has one dominant subject; forcing multi-case attribution is premature complexity. Only invoices need M2M, because a bill is a financial event that can legitimately span concerns.

## Architecture

### Relationship model (cardinality per entity)

| Entity | To Case | Notes |
|---|---|---|
| AgentThread | N:1 | thread has one case |
| AgentAction (job) | N:1 | job has one case |
| Invoice (primary) | N:1 via `invoice.case_id` | primary case, drives display + "back to case" nav |
| InvoiceLineItem | N:1 via `invoice_line_items.case_id` | **line-level attribution** for revenue rollups |
| InternalThread | N:1 | staff conversation has one case |
| DeepBlueConversation | N:1 | AI convo has one case |
| Visit | N:1 | physical event has one case |
| Inspection | N:1 via `inspection.case_id` | optional whole-report link (passing re-inspections, bulk convenience) |
| InspectionViolation | N:1 via `violation.case_id` | **authoritative** attribution for case work |
| AgentAction (job) → Violation | N:1 via `agent_actions.violation_id` | Phase 3: job formally references the finding it remediates |
| AgentAction (job) → Visit | N:1 via `agent_actions.visit_id` | Phase 3: the visit on which this job was completed |

For invoices: `invoice.case_id` is the primary/display case. Line items can individually attribute to different cases. A case's revenue is `SUM(line_items.amount WHERE case_id = $case AND invoice NOT voided)`.

### Unified link service

Backend has a single service method per direction:

```
link_entity(case_id, type, entity_id, linked_by) -> {linked: true}
unlink_entity(case_id, type, entity_id) -> {unlinked: true}
```

Supported types (post-plan): `job`, `thread`, `invoice`, `internal_thread`, `deepblue_conversation`, `visit`, `inspection`.

Invoice attachment specifically: linking an invoice to a case sets `invoice.case_id` AND backfills `invoice_line_items.case_id = case_id` for any line items that are currently NULL. Pre-attributed lines aren't overwritten.

### Allocation rules (single source of truth)

One helper function drives every case-level financial rollup:

```python
case_allocation(invoice_id, case_id) -> float  # 0.0..1.0, share of invoice attributable to this case
```

Implementation: `SUM(line_items.amount WHERE case_id = $case) / SUM(all line_items.amount)`.

Applies pro-rata to:

- **Payments** — a payment against an invoice contributes `payment.amount * allocation` to each attributed case.
- **Invoice-level discounts** — discount reduces each case's revenue pro-rata.
- **Write-offs** — same.
- **Refunds / credit memos** — same.

**Tax is excluded from case revenue.** Tax is pass-through; a 10% sales tax on $1,000 of work is not $100 of revenue to any case.

Never allow manual override on payment-to-case allocation — it's the road to reconciliation chaos. The rule is deterministic: line totals drive everything.

### Denormalized counts + totals on ServiceCase

Extend `update_counts(case_id)` to maintain:

- `job_count`, `thread_count`, `invoice_count` (existing)
- `internal_thread_count`, `deepblue_conversation_count` (Phase 1)
- `visit_count`, `inspection_count` (Phase 3)
- `total_revenue` = `SUM(matching line_items.amount)` where invoice not voided
- `total_paid` = `SUM(payment.amount * allocation(invoice, case))`
- `total_outstanding` = total_revenue - total_paid - total_written_off

### Secondary axes (not hub-and-spoke)

These don't go through ServiceCase because they're about *equipment* and *dependencies*, not case aggregation:

- `ServiceCase.equipment_item_id` (nullable) — the specific piece of equipment this case is about. Enables per-equipment failure history, warranty, repeat-issue detection.
- `AgentAction.equipment_item_id` — same for jobs that touch specific equipment.
- `AgentAction` blocks / depends-on — join table `job_dependencies`. Sequential work chains.
- `ServiceCase.parent_case_id` (nullable) — sub-cases. `case_relations` join table — sibling cases.

### UI pattern (DRY, one component)

One `<LinkCasePicker>` component that:
1. Takes an entity type and id, and the scope hints it has (customer_id, property_id).
2. Opens a popover with: (a) an "Open cases for this customer" list, (b) a search box for other cases, (c) a "Create new case from this" option.
3. Calls the correct link endpoint.

Mirrors the drop-down pattern used in case reassignment. Used on: invoice detail, thread detail, job detail, visit detail, internal thread, DeepBlue conversation.

Case detail page gets the inverse: an "Attach…" button per section (Jobs / Threads / Invoices / Visits / Internal / DeepBlue) that opens the same picker filtered to unattached entities for this customer.

### Line-item case picker (Phase 2)

Invoice edit UI gets a per-line "Case" column. Default: inherit invoice's primary case (`invoice.case_id`). When a line item has a case different from the invoice's primary case, the line row shows a subtle chip indicating split. Create-invoice form doesn't show the column by default — it appears when the user clicks "split across cases" at the invoice level.

Soft consistency warning: if a line's `case_id` differs from its linked job's `case_id` (via `job_invoices`), UI shows a yellow "this line is attributed to case X but its linked job is on case Y — is that right?" banner. Not a DB constraint; just training behavior.

### Case detail invoice display

Invoices section shows one row per attached invoice. Displayed amount is the *case-attributed* amount, with invoice total as context:

> **INV-26010** · $300 of $500 total *(other $200 on Case #24)*

Payments column shows pro-rata payment contributions to this case. Total balance per case sums only attributed lines.

### Permissions

**Rule: if you can edit an entity, you can link/unlink it.** No new permission slugs, no separate matrix.

- Reuses existing authorization checks via `can_link_entity(user, entity) := can_edit_entity(user, entity)`.
- Tech-with-own-visit can link their own visit (good for data quality — they did the work).
- Case-detail "Attach…" (inverse direction) uses case-edit permission (owner/admin/manager), matching case reassignment.
- No stricter gate on financial links. Managers can already void invoices, discount, write off — re-linking a case is strictly less powerful than what they already have.

Safety is carried by the activity log (who linked/unlinked what, when), soft divergence warnings (line↔job, thread↔case customer mismatch), and real-time `case.updated` events so concurrent viewers see changes immediately.

### Discovery

Three affordances so connections aren't invisible:

1. **Case timeline unification** — existing timeline extended to include visits, inspection violations, equipment events.
2. **Smart suggestion chips** — when a new thread/invoice/job lands for a customer who has an open case, surface a chip: *"This may be about Case #123: Pool motor"* → one click to attach. Uses subject keyword + recency + customer match.
3. **Orphaned items view on customer detail** — list of threads/invoices/jobs not attached to any case, with a batch-attach flow.

## Phases

### Phase 1 — Manual link/unlink UI for existing linkables (ships the Sierra Oaks use case) — SHIPPED 2026-04-14

- [x] Extend `POST /v1/cases/{id}/link` and `DELETE /v1/cases/{id}/link` to handle `internal_thread` and `deepblue_conversation`.
- [x] Extend `update_counts(case_id)` to include `internal_thread_count`, `deepblue_conversation_count` on ServiceCase (new columns + migration `6ca65f3faef6`).
- [x] Centralized `ServiceCaseService.set_entity_case()` — sole write path for `entity.case_id` mutations, handles counts + activity + events.
- [x] Build `<LinkCasePicker>` component — searches cases, scoped to customer_id if known, falls back to global search. Includes "Create new case from this entity" option.
- [x] Wire it in on: invoice detail header, thread detail sheet, job detail content, internal thread page. (DeepBlue conversation card: deferred — attach from case detail covers the inverse.)
- [x] Case detail page: `<AttachExistingDialog>` in timeline header — inverse picker with per-row eye icon for email thread preview before committing.
- [x] Unit tests: link/unlink is idempotent, cross-org mutation is blocked, counts update correctly (9 tests in `tests/test_case_link_service.py`, suite 53/53 green).
- [x] Activity log entry on link/unlink via system comment on a host job.
- [x] Real-time `case.updated` event on every link/unlink (shipped in Phase 1 per implementation invariant, not deferred to Phase 5).
- [x] **Thread→jobs cascade in `set_entity_case`** — linking a thread to a case auto-attaches every job on that thread, so orchestrator-created caseless jobs inherit a case the moment a human links the thread. (Added 2026-04-14 alongside the case-as-hub enforcement work; closes the going-forward gap for the email orchestrator path.)
- [x] **Jobs-must-live-in-cases invariant enforced** — `ThreadAIService.create_job_from_thread` returns 400 `no_case` if `thread.case_id` is null; `AgentActionService.create_action` raises (no longer swallows) on case-creation failure; `estimate_workflow_service.approve_estimate` sets `case_id=invoice.case_id` on auto-created jobs. UI: "Add Job" button hidden on caseless threads (LinkCasePicker is the only pre-job affordance).
- [x] **Close/reopen cascade** — closing a case sets every non-terminal job to `done`/`cancelled` with `closed_by_case_cascade=true`; reopening surfaces a dialog listing only the cascade-closed jobs so the user can selectively reopen them. Human-completed jobs are immutable through this path. (`ServiceCaseService.close_open_jobs` + `reopen_cascade_jobs`.)

**Exit criterion:** Brian can attach EST-26005 to any existing Pinebrook case and detach it if wrong. All five entity types can be attached/detached from any entry point. **Met.**

### Phase 2 — Line-item case attribution (Option B accounting correctness)

- [ ] Migration: `invoice_line_items.case_id` nullable FK, `ON DELETE SET NULL`. Backfill all existing rows with parent `invoice.case_id`.
- [ ] Backend: `case_allocation(invoice_id, case_id)` helper. Single implementation used by profitability, revenue rollups, collections, AR.
- [ ] Update ServiceCase denormalized totals: `total_revenue`, `total_paid`, `total_outstanding` using allocation rule (migration + backfill job).
- [ ] Update payment posting: `process_payment()` distributes `amount * allocation` to each attributed case's `total_paid`.
- [ ] Update discounts, write-offs, refunds to use the same allocation helper.
- [ ] **Tax excluded from case revenue** — enforce in helper; tax_amount never hits case totals.
- [ ] Invoice edit UI: per-line "Case" picker (shown when user clicks "split across cases"). Defaults inherit from invoice.case_id.
- [ ] Case detail invoices section: show attributed amount with invoice total as context.
- [ ] Estimate approval snapshot: include `case_id` per line item in `snapshot_json`. Convert-to-invoice preserves line-item case_ids.
- [ ] Soft warning: yellow banner when line's case_id ≠ linked job's case_id.
- [ ] Recurring service invoices: explicit default `line_items.case_id = NULL` (service isn't case-bound).
- [ ] Existing profitability service: migrate from property/WF-keyed revenue to case-keyed where applicable; keep WF view as its own lens.
- [ ] Tests: multi-case invoice payment allocation, write-off allocation, refund allocation, tax exclusion, estimate conversion preserves line case_ids.

**Exit criterion:** A $500 invoice with $300 on Case A and $200 on Case B correctly reports $300 / $200 revenue per case, a $100 payment correctly posts $60 / $40, and profitability dashboards reconcile to the penny against the invoice ledger.

### Phase 3 — Physical work connects to cases (full traceability chain)

Mirrors the leaf-attribution pattern established in Phase 2: leaf-level (violation) is authoritative, container (inspection) is optional convenience. Plus first-class job↔physical-work FKs to close the audit trail *violation → case → job → visit → invoice → payment*.

**Case ↔ physical work:**

- [ ] Migration: `visits.case_id` nullable FK, `ON DELETE SET NULL`.
- [ ] Migration: `inspections.case_id` nullable FK — for passing re-inspections (zero violations) and whole-report bulk-linking.
- [ ] Migration: `inspection_violations.case_id` nullable FK — authoritative attribution for case work.
- [ ] Link service handles `visit`, `inspection`, `violation` types. Linking an inspection cascades `case_id` to its unlinked violations by default; user can opt into advanced splitting.
- [ ] Unlink rules: unlinking an inspection leaves violations alone (might be attributed differently).

**Job ↔ physical work (the "trivial additions"):**

- [ ] Migration: `agent_actions.violation_id` nullable FK to `inspection_violations`, `ON DELETE SET NULL`. One violation can have multiple remediation jobs; one job addresses at most one violation.
- [ ] Migration: `agent_actions.visit_id` nullable FK to `visits`, `ON DELETE SET NULL`. The visit where the job was physically completed. (Visit is when the tech was there; job is what they did.)
- [ ] Job create flow: accept `violation_id` and `visit_id` (URL params + API body). Inspection violation UI gets "Create remediation job" action that pre-fills.
- [ ] Job detail: "Linked violation" chip (if set), "Completed on visit" chip (if set). Click-through to each.
- [ ] Violation detail: list of remediation jobs with status (open / done).
- [ ] Visit detail: list of jobs completed on this visit.

**UI:**

- [ ] Inspection detail: header "Link inspection to case…" + per-violation row link icon.
- [ ] Visit detail: "Case" picker.
- [ ] Case detail: new "Visits" section (photos + measurements pulled through visit_id), new "Inspections" section showing inspection rows with attributed violations listed underneath (non-attributed violations greyed).
- [ ] Case timeline: visually thread violation → job → visit → invoice when all four exist for the same work.

**Counts + AI:**

- [ ] `update_counts` gets `visit_count`, `inspection_count`, `violation_count`.
- [ ] AI hook: when a thread is matched to a customer with an open inspection violation, suggest linking to that violation's case.
- [ ] Report query: `days_to_remediate(violation_id)` = days from `violation.created_at` to linked job's `completed_at`. Powers compliance dashboards.

**Exit criterion:** Opening a case shows the full chain for each attributed violation: violation found on date X → job created on date Y → completed on visit Z → invoiced on INV-N → paid on date P. Every link navigates cleanly. A compliance report for a facility returns accurate days-to-remediate per violation.

### Phase 4 — Secondary axes (equipment, job chains, case siblings)

- [ ] Migration: `service_cases.equipment_item_id`, `agent_actions.equipment_item_id`, `service_cases.parent_case_id`, `case_relations` join table, `job_dependencies` join table.
- [ ] Equipment picker component on case create/edit + job create/edit.
- [ ] Job detail: "Blocks" / "Blocked by" section with dependency picker. Visual chain when dependencies exist.
- [ ] Case detail: "Parent case" chip, "Related cases" sidebar section.
- [ ] Equipment detail page: "Cases about this equipment" list — unlocks failure-pattern / warranty analytics.
- [ ] AI hook: job description mentions "blocked waiting for parts" → DeepBlue tool suggests creating the parts job and linking as dependency.

**Exit criterion:** "Show me every case about the Pinebrook Pentair pump" returns a complete history. "What's blocking the Coventry install?" answered visually.

### Phase 5 — Discovery polish

- [ ] Smart suggestion chips on new entities (thread/invoice/job) when a matching case exists.
- [ ] Customer detail page: "Orphaned items" section listing unlinked threads/invoices/jobs with batch-attach.
- [ ] Global search: typing a case number anywhere surfaces attach action.
- [ ] DeepBlue tool: `link_entity_to_case(type, id, case_id)` — lets the AI attach on the user's behalf.
- [ ] Real-time event: `case.linked` / `case.unlinked` publishes so any open window updates.
- [ ] Activity log surfaces linking history on case detail.

**Exit criterion:** A new user with no training ends up with connected data by default, not by vigilance.

## Open Decisions

- ~~**Link permissions.**~~ **Resolved 2026-04-14:** "if you can edit it, you can link it." See Permissions section above.
- ~~**Inspection granularity.**~~ **Resolved 2026-04-14:** leaf-level (violation) is authoritative; inspection-level link is optional convenience. Mirrors Phase 2's invoice/line-item pattern.
- **Auto-link defaults.** When AI extracts a job from a thread, the job gets the thread's case_id. Good. When a user creates a new invoice from a case detail page, it should auto-attach. Confirm all create-from-case paths carry case_id forward during Phase 1.

## Implementation Invariants (must hold across every phase)

Things that are easy to get wrong and hard to unwind — flagged up front so each phase's PR is audited against them.

- **All `case_id` writes go through a single service method** (e.g., `ServiceCaseService.set_entity_case(type, id, case_id)`). Direct `entity.case_id = X` assignments outside this method cause denormalized counts/totals to drift. Extend this rule to AI extraction paths, not just manual link endpoints.
- **Every link/unlink endpoint org-filters the entity lookup.** Inherited risk from `docs/inbox-security-audit-2026-04-13.md` C2: a missing `AND organization_id = ctx.organization_id` lets a user mutate another org's data. Every new linkable type gets this check in review, not as an afterthought.
- **All new `case_id` columns get an index.** Read paths filter by case_id constantly (case detail, reports). Non-indexed FKs tank at scale.
- **`case.updated` real-time event publishes on every link/unlink** from Phase 1, not deferred to Phase 5. Otherwise every viewer's open window silently shows stale state.
- **Soft divergence warnings** apply uniformly: line_item.case_id ≠ linked job's case_id, thread.case_id ≠ case's customer_id, violation's facility ≠ case's customer-property chain. Not hard constraints; UI banners that train the behavior.
- **Downstream aggregation audit (Phase 2).** Revenue is aggregated in more places than just profitability: invoice stats, customer detail totals, AR aging, collections dashboards. Each one gets a line-item-attribution pass in Phase 2 — flag any that still read `invoice.case_id` alone as a migration item.
- **Create-from-case paths propagate case_id.** Every "New invoice" / "New job" / "New estimate" button launched from a case detail page passes case_id in the creation body. Audit in Phase 1.

## Migration / Risk

- All FK additions are nullable with `ON DELETE SET NULL` — zero downtime.
- New join tables are additive.
- Denormalized counts: backfill job runs once after each migration, then `update_counts` keeps them in sync.
- Line-item backfill (Phase 2) is one-shot: `UPDATE invoice_line_items li SET case_id = i.case_id FROM invoices i WHERE li.invoice_id = i.id AND li.case_id IS NULL`. Instant on existing data volumes.
- Phased so each phase ships independently — Phase 1 ~1-2 days, Phase 2 ~2-3 days, Phase 3 ~3 days, Phase 4 ~3 days, Phase 5 ~2 days.

## Cross-References

- `docs/data-model.md` — will be updated per phase with new FKs and tables.
- `docs/realtime-events.md` — add `case.linked` / `case.unlinked` event types in Phase 5.
- `docs/profitability-feature-plan.md` — revenue attribution revision per Phase 2.
- `CLAUDE.md` "Data Architecture Rules" — reinforced by this plan (FK + join, never copy).
