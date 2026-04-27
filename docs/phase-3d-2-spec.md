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
### Out of scope (deferred to 3d.2.1+ or 3d.3)
- **Tracking what the tech actually dosed (vs. what was recommended).** No `applied_doses` capture exists in the current schema. Correction stamping for `agent_type="dosing_engine"` requires this column + a UI to enter it. Both belong to Phase 3d.3 (guided workflows) — that's where "tech confirms each step" lives. 3d.2 is read-only display: here's what to dose. 3d.3 closes the loop with "here's what I dosed."
- A full standalone `/chemistry/{bow_id}` page. Visit screen integration is the primary surface; standalone page is a v1.x convenience.
- LSI history/trend chart (the build-plan lists it under Phase 4 portal — that's the right home).
- Dosing recommendations reaching past pH/FC into LSI-driven calcium/alkalinity adjustments. Engine handles each parameter independently today; LSI-coupled multi-parameter solving is its own design problem.
- Required-photo enforcement (Phase 3d.3 territory).

## 4. Architecture

### 4.1 LSI math + the temperature constant

LSI = pH + TF + CF + AF − 12.1
- TF: temperature factor (table lookup, °F) — **uses a hardcoded 75°F constant**
- CF: calcium hardness factor (log10-based)
- AF: alkalinity factor (log10-based)

`calculate_lsi(ph, calcium_hardness, alkalinity, cyanuric_acid)` — note no `temp_f` parameter. The function imports `WATER_TEMP_F_DEFAULT = 75.0` from a small config module. The LSI endpoint's `based_on` payload includes `temp_f: 75` so the UI can label it ("temp: 75°F (assumed)") — full transparency, no hidden assumption.

If `chemical_readings.water_temp` is set on a row (legacy column, not currently surfaced as required), the LSI endpoint MAY use it instead of the constant. v1: ignore the column entirely; the constant is the only path. Per `feedback_water_temp_constant.md`: real-time temp isn't worth the UI tax.

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

### 4.4 No dose-tracking column added in this phase

`chemical_readings.recommendations` (existing JSONB) already stores the engine's output at save time — that's all 3d.2 writes. There's no `applied_doses` column for "what the tech actually used"; that's a Phase 3d.3 concern (guided workflows close the loop with apply-and-confirm steps).

**Critical:** the AI consumes future corrections (when 3d.3 wires them), but **never** writes dosing values. The dosing engine is and stays deterministic. Future AI surfaces (e.g. "this property's pH falls fast — recommend higher target") observe corrections to surface *suggestions to humans*, not auto-doses.

## 5. Rollout steps

1. Verify `calculate_lsi(ph, calcium_hardness, alkalinity, cyanuric_acid)` exists in `dosing_engine.py`; add if missing, importing `WATER_TEMP_F_DEFAULT = 75.0` from a tiny config module. Unit tests for the formula against known good values (NSF reference table).
2. New `chemistry.py` API router with the 2 endpoints. Tests for each (happy path + 404 + bad-input). `/lsi` returns `based_on.temp_f = 75` so the UI can label the assumption.
3. Frontend `LSIGauge` component + visual tests (vitest). **3-band coloring**: < -0.3 red (corrosive), -0.3 to +0.3 green (balanced), > +0.3 red (scaling). Renders the value + classification; small caption "temp: 75°F (assumed)" at the bottom for transparency.
4. Frontend `DosingCards` component + visual tests. Renders engine output verbatim — no client-side reformatting beyond unit display.
5. Wire both into `visit-readings.tsx` with a 300ms debounce on reading changes. Empty state when no readings yet.
6. Update build-plan.md to mark 3d.2 items checked. (No new events emit — endpoints are read-only/calculator.)
7. Mobile audit: open the visit screen on a phone (320px width), verify gauge readable, cards stack cleanly, debounced calc doesn't lag entry.

## 6. Definition of done

- [ ] `calculate_lsi(ph, calcium_hardness, alkalinity, cyanuric_acid)` exists in `dosing_engine.py` with unit tests covering 4+ reference values from the standard table at the 75°F constant.
- [ ] `/v1/chemistry/water-features/{bow_id}/lsi` and `/v1/chemistry/water-features/{bow_id}/dosing` registered + tested. `/lsi` payload includes `based_on.temp_f = 75`.
- [ ] `LSIGauge` renders the value with correct 3-band color (red/green/red); vitest covers the 3 thresholds + boundary edges.
- [ ] `DosingCards` renders engine output 1:1; missing-parameter rows show "OK" rather than empty.
- [ ] `visit-readings.tsx` shows gauge + cards reactively; debounce verified.
- [ ] R5 + R7 audits clean.
- [ ] Mobile audit (320px) passes — gauge readable, cards stack, no horizontal scroll.

## 7. Estimated scope

2.5–4 working days (down from 3–5 after deferring correction stamping to 3d.3):
- LSI math + tests: 0.5 day (mostly verification; if missing, 1 day)
- 2 API endpoints + tests: 0.5 day
- LSIGauge component + tests: 0.5 day
- DosingCards component + tests: 0.5 day
- visit-readings integration + debounce: 0.5–1 day
- Mobile audit + polish: 0.5 day

## 8. Resolved decisions (was open questions)

- **Water temp:** hardcoded 75°F constant; no per-reading entry, no per-property override v1. Resolved 2026-04-27 — see `memory/feedback_water_temp_constant.md`. Real-time temp isn't worth the UI tax for the precision a coarsely-banded gauge exposes.
- **Tech-actually-dosed capture:** deferred to Phase 3d.3 (guided workflows). 3d.2 is read-only "here's what to dose"; 3d.3 closes the loop with apply-and-confirm. No `applied_doses` column added in this phase.
- **LSI gauge banding:** 3-band (red/green/red), not 5-band. Industry standard, less ambiguous, and amber-without-different-action is cosmetic.
