# Equipment-from-Inspections — Plan

Inspection PDFs already capture rich equipment detail (3 filter pumps with make/model/HP, jet pump, recirc, booster, filter, DE filter, 2 sanitizers, main drain, equalizer, skimmer count) into `inspection_equipment` rows. Today only `pool_capacity_gallons` propagates to the property's primary WaterFeature; everything else stays unsynced. Result: the client profile under-reports actual equipment installed at the site.

This is the build that closes that gap by auto-creating `equipment_items` from inspection data, with a learning loop so matches improve over time.

## Why (DNA alignment)

- **Less work for the USER**: today, a tech reading an inspection PDF would have to manually re-key every pump/filter into the property profile. After this build: it's already there when they open the page.
- **Every agent learns**: the catalog-matching step uses an `equipment_resolver` agent that's already declared in `AgentLearningService` (`AGENT_EQUIPMENT_RESOLVER` constant, never wired up). Build wires it.
- **Data capture is king**: the data is already extracted into `inspection_equipment`. Not surfacing it on the property profile means inspection data degrades from "operationally useful" to "audit-only artifact."
- **Build for the 1,000th customer**: every QP customer who uses inspections (any pool service in any jurisdiction with online reports) gets richer property profiles for free.

## Design decisions

### 1. Auto-apply, not proposal queue
Equipment items are internal records, not customer-facing — so DNA rule #5 ("AI never commits to the customer") doesn't gate this. Auto-apply is fine.

But we still want the learning loop: every auto-create logs an `acceptance` correction; user edits/deletes log `edit`/`rejection`. No `agent_proposals` row needed for v1. (If we later see low accuracy, can graduate to proposal-queue pattern without schema breaks.)

### 2. Trigger: post-parse, automatic
Runs as the last step of `sync_equipment_to_bow` (already called when an InspectionEquipment row is created/updated). No new endpoint, no manual button needed for v1. The Inspection detail page can show what was created via the property's WF view.

### 3. Catalog-matching strategy
For each (brand, model) tuple from the InspectionEquipment record:
1. **Pre-filter** with rapidfuzz: top 3 candidates from `equipment_catalog` by `brand + model_number` similarity (≥0.6 threshold).
2. **Resolve** with Claude Haiku: pass `(brand_text, model_text, hp_text, candidates[], past_corrections[])` → returns `{catalog_equipment_id | null, confidence, reasoning}`.
3. **High confidence (≥0.8)** → link `catalog_equipment_id`. **Low confidence (<0.8)** → create without catalog link, just raw brand/model strings.
4. AgentLearningService injects past corrections (per org) into the resolver prompt.

### 4. Field mapping (InspectionEquipment → EquipmentItem)
| InspectionEquipment fields | equipment_type | system_group | notes |
|---|---|---|---|
| `filter_pump_{1,2,3}_*` | `pump` | `filter` | position from index |
| `jet_pump_1_*` | `pump` | `jet` | |
| `rp_*` (recirc) | `pump` | `recirc` | |
| `bp_*` (booster) | `pump` | `booster` | |
| `filter_1_*` | `filter` | — | `filter_1_type` → notes |
| `df_*` | `filter` | — | notes: "DE filter" |
| `sanitizer_{1,2}_*` | `sanitizer` | — | type+details → notes |
| `main_drain_*` | `drain` | — | install_date → install_date |
| `equalizer_*` | `drain` | `equalizer` | |

### 5. Idempotence + dedup
Add nullable FK `equipment_items.source_inspection_id` (refs `inspections.id`). On re-parse:
- If existing item with same `source_inspection_id` + `system_group` + position-in-group → update fields in place (no dup).
- If existing item from MANUAL entry (no `source_inspection_id`) with same brand+model → skip auto-create (manual is authoritative).
- If existing item from a DIFFERENT inspection with same brand+model → keep both? No — same physical equipment shouldn't dup across inspections. Match on brand+model+serial; if any exact match exists, skip.

### 6. UI surface
- **Property/WF detail**: existing equipment list gets a small "from inspection" badge on items where `source_inspection_id IS NOT NULL`.
- **Inspection detail**: existing equipment summary gets a "→ View on property" link if synced.
- **No new pages, no new dialogs.**

## Scope

### Backend
- Migration: add `equipment_items.source_inspection_id` FK + index.
- New service `app/src/services/equipment/resolver.py`:
  - `EquipmentResolverService.match(brand, model, hp, org_id) → (catalog_id | None, confidence)`.
  - rapidfuzz pre-filter + Claude Haiku resolver + `AgentLearningService` integration.
- Extend `app/src/services/inspection/service.py:sync_equipment_to_bow`:
  - After pool-spec sync, iterate InspectionEquipment fields → call resolver per (brand, model) → upsert EquipmentItem rows.
  - Emit `equipment.synced_from_inspection` realtime event per CLAUDE.md realtime rules.
- Wire `AgentLearningService.record_correction` calls into:
  - `EquipmentItem` PATCH endpoint → log `edit` if `source_inspection_id` not null.
  - `EquipmentItem` DELETE endpoint → log `rejection` if `source_inspection_id` not null.

### Frontend
- `EquipmentItemRow` component: add "from inspection" badge when source FK is set; clicking navigates to inspection.
- Inspection detail equipment summary: add "View on property" link.

### Tests (mandatory per CLAUDE.md)
- `tests/services/test_equipment_resolver.py` — fuzzy matching + Claude integration mocked.
- `tests/services/test_inspection_equipment_sync.py` — full pipeline: InspectionEquipment with 3 pumps + filter + 2 sanitizers → asserts 6 EquipmentItem rows created with correct types/groups, idempotent on re-run.
- `frontend/components/equipment/equipment-item-row.test.tsx` — badge renders when source set.

## Definition of Done
1. Migration applied, `equipment_items.source_inspection_id` exists.
2. New `EquipmentResolverService` with rapidfuzz + Claude Haiku + AgentLearningService corrections injection.
3. `sync_equipment_to_bow` extended to create/update equipment_items per the field mapping table.
4. `equipment_resolver` agent registered in AgentLearningService and corrections logged on edit/delete.
5. UI badge "from inspection" rendered on auto-created items.
6. Backend test asserting full pipeline shipping ≥6 items from a multi-pump InspectionEquipment fixture, idempotent on re-run.
7. Frontend test asserting badge presence.
8. Backfill script `app/scripts/backfill_equipment_from_inspections.py` runs once per org to import historical InspectionEquipment data into equipment_items. Sapphire dogfood org first.
9. Deployed via `scripts/deploy.sh`. Sapphire's properties show inspection-sourced equipment in the UI within minutes.
10. R7 audit pass — no `.draft_response` access regressions, no orphan code, doc index updated.

## Out of scope (explicit)
- **Proposal-queue pattern** for low-confidence matches. Auto-apply with learning loop is sufficient for v1; graduate later if accuracy demands.
- **Manual "Re-sync equipment from inspection" button.** Re-running the inspection PDF parse already triggers re-sync.
- **Equipment lifecycle inference** (warranty expiration, replace-by date based on inspection-noted install dates) — that's a separate downstream feature.
- **Alternate-source equipment ingestion** (manufacturer manuals, vendor invoices, photo OCR) — Phase 2 if ever.
- **Per-WF position-aware visualization** ("this is the filter pump for spa 1") — current model is flat list per WF.

## Doc index update
Add to CLAUDE.md Documentation Index → "Build Plans (forward-looking)" → this file. Remove on completion.
