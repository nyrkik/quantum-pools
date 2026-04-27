# Phase 3d.2 — LSI + Dosing surfacing

> Refinement spec. Master plan: `docs/build-plan.md` → Phase 3d.2 (LSI Calculator & Dosing Engine — PARTIAL). Remove this file when the sub-phase is shipped + archived.

## 1. Purpose

The `dosing_engine.py` module already exists with industry-standard formulas — pure functions, no DB, no AI (intentionally — dosing is safety-critical, never let AI generate amounts). DeepBlue's `_exec_dosing()` tool uses it. What's missing is a **first-class user surface**: REST endpoints + visit-screen UI that puts LSI + dosing recommendations directly in the tech's field of view as they enter readings.

Today the tech enters readings in `visit-readings.tsx` (good range coloring + auto-prefill from previous visit + test-strip vision scan). They don't see what to dose unless they explicitly ask DeepBlue. The fix: render dosing cards inline below the readings panel — calculated client-side from the engine's output every time a reading changes.

## 2. Why now

Phase 3d.2 is the foundation for Phase 3d.3 (guided workflows) and Phase 3d.4 (filter/salt cell scheduling). The visit screen is the highest-traffic surface in the product for any pool service org — every visit, every tech, every day. Strengthening it compounds across the entire customer base.

The AI Platform tax is paid (Phase 5/6). Future hooks (auto-suggest target pH for this customer based on history, learn that this property's pH falls fast on weekends, etc.) wire into AgentLearningService + workflow_observer for free.

## 3. Scope

### In scope
- New API endpoints:
  - `GET /v1/chemistry/water-features/{bow_id}/lsi` — current LSI from latest ChemicalReading (or 404 if no reading)
  - `POST /v1/chemistry/water-features/{bow_id}/dosing` — body: a partial reading set; response: dosing recommendations from the engine. Stateless — caller can run "what if" scenarios as the tech enters readings.
- LSI calculation in `dosing_engine.py` (currently dosing-only — verify; if missing, add the standard Langelier formula).
- Frontend `LSIGauge` component — color-coded radial showing -1.0 (corrosive) to +1.0 (scaling) with the calc'd value pinned. Mobile-first (40% of techs use phones).
- Frontend `DosingCards` component — one card per parameter that needs adjustment, with chemical name, amount in field-friendly units (oz + cups for liquid, lb for granular), and the engine's safety notes.
- Integration into `visit-readings.tsx`: as the tech enters/edits each reading, fire the dosing endpoint (debounced 300ms) and render cards below. LSI gauge above the form.
- A tech's "this is wrong, I dosed X instead" override stamps an `agent_corrections` row with `agent_type="dosing_engine"` for future AI use. **No** AI generates dosing — corrections are pure human-source-of-truth annotations.

### Out of scope (deferred to 3d.2.1+)
- A full standalone `/chemistry/{bow_id}` page. Visit screen integration is the primary surface; standalone page is a v1.x convenience.
- LSI history/trend chart (the build-plan lists it under Phase 4 portal — that's the right home).
- Dosing recommendations reaching past pH/FC into LSI-driven calcium/alkalinity adjustments. Engine handles each parameter independently today; LSI-coupled multi-parameter solving is its own design problem.
- Required-photo enforcement (Phase 3d.3 territory).

## 4. Architecture

### 4.1 LSI math (verify existing or add)

LSI = pH + TF + CF + AF − 12.1
- TF: temperature factor (table lookup, °F)
- CF: calcium hardness factor (log10-based)
- AF: alkalinity factor (log10-based)

If `dosing_engine.py` already has it, expose it as a pure function `calculate_lsi(ph, temp_f, calcium_hardness, alkalinity, cyanuric_acid)`. If not, add it in this phase.

### 4.2 API surface

```python
# app/src/api/v1/chemistry.py — new file
GET /v1/chemistry/water-features/{bow_id}/lsi
  → {value: float, classification: "corrosive" | "balanced" | "scaling",
     based_on: {ph, temp_f, ca, alk, cya}, reading_id: str, taken_at: str}
  → 404 if no readings exist for the BOW

POST /v1/chemistry/water-features/{bow_id}/dosing
  body: {ph?, free_chlorine?, alkalinity?, calcium_hardness?, cya?, combined_chlorine?, phosphates?}
  → {recommendations: [<engine output>], lsi: float | null}
  Stateless. No DB write. Pure passthrough to dosing_engine.calculate_dosing.
```

Both gated by `chemicals.view`. POST is intentionally not `chemicals.create` — it's a calculator, not a write.

### 4.3 Frontend components

```
frontend/src/components/chemistry/
  ├── LSIGauge.tsx         # radial gauge, mobile-friendly
  ├── DosingCards.tsx      # one card per recommendation
  └── chemistry.test.tsx   # unit tests with engine output fixtures
```

`visit-readings.tsx` integrates both above the existing readings form. As readings change, debounced POST fires and updates the cards.

### 4.4 Correction stamping

When a tech logs a dosing amount different from what the engine recommended (current code path: `actual_dose` field on the visit), record an `AgentCorrection`:
- `agent_type = "dosing_engine"`
- `original_output` = engine's recommendation JSON
- `corrected_output` = `{chemical, amount}` the tech actually used
- `correction_type = "edit"`
- `category = parameter` (e.g. `"ph"`)
- `customer_id = visit.customer_id`

**Critical:** the AI consumes corrections, but **never** writes dosing values. The dosing engine is and stays deterministic. Future v1.x AI surfaces (e.g. "this property's pH falls fast — recommend higher target") observe corrections to surface *suggestions to humans*, not auto-doses.

## 5. Rollout steps

1. Verify `calculate_lsi` exists in `dosing_engine.py`; add if missing. Unit tests for the formula against known good values (NSF reference table).
2. New `chemistry.py` API router with the 2 endpoints. Tests for each (happy path + 404 + bad-input).
3. Frontend `LSIGauge` component + visual tests (vitest). Color thresholds: ≤-0.3 red, -0.3..-0.1 amber, -0.1..+0.1 green, +0.1..+0.3 amber, >+0.3 red.
4. Frontend `DosingCards` component + visual tests. Renders engine output verbatim — no client-side reformatting beyond unit display.
5. Wire both into `visit-readings.tsx` with a 300ms debounce on reading changes. Empty state when no readings yet.
6. Correction stamping: on visit save, if `actual_dose` (or equivalent) differs from engine recommendation, stage an AgentCorrection. Tests cover the diff comparator.
7. Update `docs/event-taxonomy.md` if any new events emit (probably none — endpoints are read-only/calculator). Update build-plan.md to mark 3d.2 items checked.
8. Mobile audit: open the visit screen on a phone (320px width), verify gauge readable, cards stack cleanly, debounced calc doesn't lag entry.

## 6. Definition of done

- [ ] `calculate_lsi` exists in `dosing_engine.py` with unit tests covering 6+ reference values from the standard table.
- [ ] `/v1/chemistry/water-features/{bow_id}/lsi` and `/v1/chemistry/water-features/{bow_id}/dosing` registered + tested.
- [ ] `LSIGauge` renders the value with correct color band; vitest covers the 5 thresholds.
- [ ] `DosingCards` renders engine output 1:1; missing-parameter rows show "OK" rather than empty.
- [ ] `visit-readings.tsx` shows gauge + cards reactively; debounce verified.
- [ ] Correction stamping fires on visit save when actual ≠ recommended; AgentCorrection rows visible in `/v1/learning/corrections?agent_type=dosing_engine`.
- [ ] R5 + R7 audits clean.
- [ ] Mobile audit (320px) passes — gauge readable, cards stack, no horizontal scroll.

## 7. Estimated scope

3–5 working days:
- LSI math + tests: 0.5 day (mostly verification; if missing, 1 day)
- 2 API endpoints + tests: 0.5 day
- LSIGauge component + tests: 0.5 day
- DosingCards component + tests: 0.5 day
- visit-readings integration + debounce: 0.5–1 day
- Correction stamping + tests: 0.5 day
- Mobile audit + polish: 0.5 day

## 8. Open questions

- **Where does temp_f come from?** Tech enters water temp on the reading? Auto-pull from a property field? Default 78°F? Spec assumes reading carries `water_temp_f` — verify the model.
- **Does the visit save flow currently capture `actual_dose` per parameter?** If not, that's a small schema addition (likely a JSONB column on `Visit` keyed by parameter). Either Phase 3d.2 or deferred to 3d.3.
- **Should the 5-class LSI gauge use a 3-class color set instead?** Two-amber-bands risks ambiguity. Test in mobile audit.
