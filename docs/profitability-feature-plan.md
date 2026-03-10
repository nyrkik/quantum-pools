# Profitability Analysis Feature — Full Plan

## Overview
New feature for Phase 3b: per-account profitability analysis with difficulty scoring, bather load calculations, cost breakdown, and AI pricing recommendations. No competitor offers this level of analysis.

## Database Changes

### New Table: `org_cost_settings`
One row per org. Fields:
- `burdened_labor_rate` (Float, default 35.0) — $/hour fully burdened
- `vehicle_cost_per_mile` (Float, default 0.655) — IRS standard rate
- `chemical_cost_per_gallon` (Float, default 3.50)
- `monthly_overhead` (Float, default 2000.0)
- `target_margin_pct` (Float, default 35.0)

### New Table: `property_difficulties`
One row per property, org-scoped. Two categories of fields:

#### Measured Fields (auto-calculated or entered as actual values)
- `pool_gallons` (from property)
- `pool_sqft` (from property)
- `shallow_sqft` (nullable — estimated if not provided)
- `deep_sqft` (nullable — estimated if not provided)
- `has_deep_end` (boolean)
- `has_spa` (boolean)
- `spa_sqft` (nullable)
- `diving_board_count` (Integer, default 0)
- `pump_flow_gpm` (nullable — estimated from pump specs or turnover calc if not provided)
- `is_indoor` (boolean, default false)
- `pool_type` (enum: commercial, residential)
- `filter_type` (string, nullable)
- `pump_specs` (string, nullable)
- `equipment_age_years` (Integer, nullable)
- `shade_exposure` (enum: full_sun, partial_shade, full_shade, nullable)
- `tree_debris_level` (enum: none, low, moderate, heavy, nullable)
- `enclosure_type` (enum: open, screened, indoor, nullable)
- `chem_feeder_type` (string, nullable — tablet, liquid, salt, etc.)

#### Scored Fields (user rates 1-5)
- `access_difficulty_score` (Float, default 1.0) — locked gates, narrow paths, stairs
- `customer_demands_score` (Float, default 1.0) — frequent calls, complaints, special requests
- `chemical_demand_score` (Float, default 1.0) — chronic algae, unstable chemistry
- `callback_frequency_score` (Float, default 1.0) — rework rate

#### Computed (not stored, calculated in service layer)
- `composite_difficulty_score` (1.0 - 5.0, weighted formula)
- `max_bather_load` (from jurisdiction calculator)
- `estimated_service_time` (from difficulty + pool characteristics)

#### Override
- `override_composite` (Float, nullable) — manual override of computed composite
- `notes` (Text, nullable)

### New Table: `bather_load_jurisdictions`
Lookup table for calculation methods:
- `id` (PK)
- `name` (e.g., "California", "ISPSC", "Texas", "Florida", etc.)
- `method_key` (enum used in code: california, ispsc, mahc, texas, florida, arizona, new_york, georgia, north_carolina, illinois)
- `shallow_sqft_per_bather` (Float)
- `deep_sqft_per_bather` (Float)
- `spa_sqft_per_bather` (Float)
- `diving_sqft_per_board` (Float, default 300)
- `has_deck_bonus` (Boolean)
- `deck_sqft_per_bather` (Float, nullable — 50 for ISPSC)
- `has_flow_rate_test` (Boolean — true for Florida)
- `flow_gpm_per_bather` (Float, nullable — 5 for Florida)
- `has_indoor_multiplier` (Boolean — true for MAHC)
- `indoor_multiplier` (Float, nullable — 1.15 for MAHC)
- `has_limited_use_multiplier` (Boolean — true for MAHC)
- `limited_use_multiplier` (Float, nullable — 1.33 for MAHC)
- `depth_based` (Boolean — whether shallow/deep split matters)
- `depth_break_ft` (Float, default 5.0 — depth threshold for shallow vs deep)
- `notes` (Text)

### New Table: `property_jurisdictions`
Links properties to their bather load jurisdiction:
- `property_id` (FK)
- `jurisdiction_id` (FK to bather_load_jurisdictions)
- `organization_id` (FK)

### Alterations to `Property` model
Add relationships:
- `difficulty` → PropertyDifficulty (one-to-one)
- `jurisdiction` → via property_jurisdictions

## Estimation Chain (when data is missing)

When user doesn't know a value, estimate from what they do know:

1. **Don't know sqft but know gallons** → `sqft = gallons / (avg_depth × 7.48)`
   - Shallow-only pool: avg_depth = 4.0 ft
   - Pool with deep end: avg_depth = 5.5 ft
2. **Don't know shallow/deep split** → Estimate from total sqft + has_deep_end
   - No deep end: 100% shallow
   - Has deep end: 60% shallow / 40% deep
3. **Don't know flow rate (GPM)** → Estimate from pump specs or turnover
   - From pump specs: parse GPM from specs string if available
   - From volume: `GPM = gallons / 360` (6-hour commercial turnover)
4. **Don't know diving boards** → Default 0
5. **Don't know indoor/outdoor** → Default outdoor

Each estimated value tagged with `is_estimated: true` in the UI. User can override with actual value anytime.

## Difficulty Score Weights

| Factor | Weight | Source |
|---|---|---|
| Pool size (gallons) | 10% | Measured |
| Surface area (sqft) | 5% | Measured |
| Water features (spa, fountain) | 8% | Measured |
| Equipment age | 7% | Measured |
| Shade/debris load | 5% | Measured |
| Enclosure type | 5% | Measured |
| Chemical demand pattern | 12% | Scored (1-5) |
| Average service time | 18% | Computed from visits |
| Distance from route cluster | 10% | Computed from route data |
| Access difficulty | 8% | Scored (1-5) |
| Customer demands | 7% | Scored (1-5) |
| Callback frequency | 5% | Scored (1-5) or computed from visits |

Measured factors auto-score based on ranges (e.g., gallons: <10k=1, 10-20k=2, 20-30k=3, 30-40k=4, >40k=5).

## Bather Load Jurisdictions (seed data)

| Jurisdiction | Shallow | Deep | Spa | Depth-Based | Special |
|---|---|---|---|---|---|
| California | 20 | 20 | 10 | No | Flat rate, simplest |
| ISPSC | 20 | 25 | 10 | Yes (5ft) | +1 per 50sqft excess deck |
| MAHC/CDC | 20 | 20 | 10 | No | Volume formula, indoor/limited-use multipliers |
| Texas | 15 | 20 | 10 | Yes (5ft) | Variable via chart |
| Florida | 20 | 20 | 10 | No | Dual test: also 1 per 5 GPM (lesser wins) |
| Arizona (Maricopa) | 10 | 24 | 9 | Swimmer vs non-swimmer | Most permissive shallow |
| New York | 15 | 25 | 10 | Yes (5ft) | Staffing rules at 3400+ sqft |
| Georgia | 18 | 20 | — | Yes | ISPSC with amendments |
| North Carolina | 15 | 24 | — | Yes (5ft) | — |
| Illinois | 15 | 25 | — | Yes (5ft) | — |

## Profitability Calculations

### Per Account Monthly
```
chemical_cost = gallons × cost_per_gallon × difficulty_multiplier
labor_cost = (avg_service_minutes / 60) × burdened_labor_rate × visits_per_month × difficulty_multiplier
travel_cost = (drive_minutes / 60 × burdened_rate) + (miles × vehicle_cost_per_mile)
overhead = monthly_overhead / total_accounts
total_cost = chemical + labor + travel + overhead
margin = (revenue - total_cost) / revenue
suggested_rate = total_cost / (1 - target_margin)
rate_gap = suggested_rate - current_rate
```

### Difficulty to Multiplier
`multiplier = 0.8 + (score - 1.0) × 0.2` → range 0.8x to 1.6x

## API Endpoints

```
GET  /api/v1/profitability/overview          — all accounts with profitability metrics
GET  /api/v1/profitability/account/{id}      — detailed cost breakdown
GET  /api/v1/profitability/whale-curve       — whale curve chart data
GET  /api/v1/profitability/suggestions       — AI pricing recommendations
GET  /api/v1/profitability/settings          — org cost settings
PUT  /api/v1/profitability/settings          — update cost settings (owner/admin)
GET  /api/v1/profitability/properties/{id}/difficulty   — get difficulty
PUT  /api/v1/profitability/properties/{id}/difficulty   — update difficulty (owner/admin/manager)
GET  /api/v1/profitability/jurisdictions     — list all bather load methods
PUT  /api/v1/profitability/properties/{id}/jurisdiction — assign jurisdiction
POST /api/v1/profitability/bulk-jurisdiction  — assign jurisdiction to all commercial properties in a locality
GET  /api/v1/profitability/properties/{id}/bather-load  — calculate bather load for property
```

## Frontend Pages

### `/profitability` — Main Dashboard
- Summary cards: total accounts, avg margin, accounts below target, monthly revenue vs cost
- Whale curve chart (Recharts LineChart)
- Profitability quadrant scatter (Recharts ScatterChart): revenue vs margin %, dot size by difficulty
- Sortable/filterable account table ranked by margin
- Filters: tech, route day, margin range, difficulty score range
- Click row → drilldown

### `/profitability/[customerId]` — Account Detail
- Cost waterfall chart (Recharts BarChart)
- Difficulty score breakdown with editable factors (sliders for scored, inputs for measured)
- Estimated vs actual indicators on each field
- Bather load calculation result with jurisdiction selector
- Current rate vs suggested rate with rate gap highlight
- Historical margin trend (future, once time-series exists)

### `/profitability/settings` — Org Configuration
- Cost settings form (5 inputs)
- Default jurisdiction selector for new commercial properties
- Owner/admin only

### `/profitability/bather-load` — Bather Load Calculator (standalone tool)
- Select jurisdiction method
- Input pool characteristics (with estimation fallbacks)
- See calculated max bather load
- Option to apply to property
- Bulk assign jurisdiction to properties by city/zip

### Map Integration
- Profitability overlay on existing Leaflet maps
- Green/yellow/red circle markers by margin threshold
- Toggle on routes page or standalone on profitability page

## Visualizations (all Recharts, already in project)
1. **Whale curve** — cumulative profitability, top 20% generate 150-300% of profit
2. **Profitability quadrant** — scatter: Stars, Investigate, Grow, Drop/Raise
3. **Cost waterfall** — Revenue → Labor → Chems → Travel → Overhead → Profit
4. **Difficulty vs Rate scatter** — regression line, dots below = underpriced
5. **Route map overlay** — green/yellow/red by margin

## RBAC
- Owner/Admin: full CRUD on settings, difficulty, jurisdictions; view all accounts
- Manager: view all accounts, edit difficulty scores
- Technician: view own accounts only
- Readonly: view only

## Satellite Image Analysis Pipeline

### Overview
Automated detection of pool size, vegetation, and environmental factors from satellite imagery. No competitor in the pool service space does this — everyone manually measures in Google Earth.

### Pipeline Architecture
```
Address → Geocode (lat/lng) → Fetch Satellite Image → Multi-Pass Analysis → Cache Results
```

### Image Source
- **Primary**: Google Maps Static API, zoom 20, scale=2 (1280×1280px, ~0.19m/pixel)
- **Cost**: ~$0.002 per property ($2/1000 requests)
- At zoom 20, a typical commercial pool (1000+ sqft) occupies 500+ pixels — clearly measurable

### Analysis Passes (all from same image, OpenCV)

#### Pass 1: Pool Detection
- HSV blue/cyan color segmentation (H: 90-130, S: 40-255, V: 40-255)
- Morphological operations (erode/dilate) to clean noise
- Contour detection, filter by minimum area (~50px = ~2 sqm)
- Largest qualifying contour = pool
- Calculate sqft: `pixel_area × meters_per_pixel² × 10.764`
- **Accuracy**: ±15-20% (OpenCV only), ±5-10% (with SAM refinement later)

#### Pass 2: Vegetation/Tree Detection
- HSV green segmentation within buffer zone around detected pool (20ft radius)
- **Canopy coverage %**: green pixels overlapping or adjacent to pool contour
- **Overhang detection**: green pixels directly over pool area = debris source
- **Vegetation density**: total green area in buffer / total buffer area
- Auto-populate: `shade_exposure` and `tree_debris_level` on difficulty model

#### Pass 3: Shadow Analysis
- Detect dark/shadow regions using value channel thresholding
- Shadow shape/direction indicates structures and tree positions
- **Critical for winter imagery**: bare deciduous trees still cast shadows, revealing canopy size even without leaves
- Shadow length + sun angle (from image metadata or date/location) estimates tree height

#### Pass 4: Hardscape Analysis
- Gray/brown segmentation around pool area
- Ratio of hardscape vs landscape = general debris risk profile
- Large deck areas relevant for ISPSC bather load calculation (deck bonus)

### Seasonal Challenges & Mitigations

| Challenge | Impact | Mitigation |
|---|---|---|
| **Deciduous trees in winter** | No green pixels, misses canopy | Shadow analysis estimates canopy size from bare branches; trunk/branch texture detection |
| **Pool covers (winterized)** | No blue pixels, misses pool | Cache previous detection; pool shape doesn't change; flag for manual review |
| **Algae bloom (green pool)** | Green instead of blue | Expand color range; use shape analysis (rectangular/kidney shapes); flag for review |
| **Shadow angle varies by season** | Shadow length differs summer vs winter | Calculate expected shadow from lat/lng + estimated image date; normalize |
| **Snow cover** | Everything white | Detect and flag; fall back to cached or manual data |
| **Stale imagery** | Google images can be 6mo-3yr old | Trees may have been removed/planted; flag image date if available; allow manual override |
| **False positives** | Blue tarps, blue roofs, blue cars | Filter by contour shape (pools are rectangular/oval, not irregular); minimum size threshold; location context (backyard vs front yard) |

### Multi-Source Strategy (future enhancement)
- **Google Street View**: ground-level tree identification, more recent imagery
- **Google Earth historical imagery**: multiple dates to cross-reference (API doesn't expose this easily — potential future integration)
- **User-uploaded photos**: highest accuracy, supplement automated detection

### Output Per Property
```json
{
  "pool_detected": true,
  "pool_sqft": 842.5,
  "pool_confidence": 0.87,
  "pool_contour": [[x,y], ...],
  "vegetation": {
    "canopy_coverage_pct": 45,
    "overhang_pct": 22,
    "shade_exposure": "partial_shade",
    "tree_debris_level": "moderate",
    "vegetation_density": 0.38
  },
  "hardscape_ratio": 0.55,
  "analysis_date": "2026-03-10",
  "image_source": "google_static_maps",
  "estimated_fields": ["pool_sqft", "canopy_coverage_pct"]
}
```

### Data Flow
- Results auto-populate `property_difficulties` fields: `shade_exposure`, `tree_debris_level`
- Pool sqft feeds into bather load calculator and profitability calculations
- Confidence score determines if result is trusted or flagged for manual review
- All auto-detected values tagged as estimated — user can override anytime

### Frontend Integration
- Satellite image displayed with overlays: pool outline (blue), tree canopy (green), overhang zones (orange)
- Confidence badge on each detected value
- "Re-analyze" button to re-run detection
- Manual measurement fallback tool (draw polygon on satellite image)
- Bulk analysis: "Analyze all properties" button processes entire portfolio

### API Endpoints
```
POST /api/v1/properties/{id}/detect-pool        — analyze single property
POST /api/v1/properties/bulk-detect              — analyze multiple properties
GET  /api/v1/properties/{id}/satellite-analysis  — get cached analysis results
```

### Dependencies
- `opencv-python-headless` (backend, no GUI needed)
- Google Maps Static API key (may already have for geocoding)
- Future: `segment-geospatial` (SAM) for precision refinement (requires GPU)

### Cost at Scale
| Properties | Image API Cost | Compute | Total |
|---|---|---|---|
| 50 | $0.10 | negligible | ~$0.10 |
| 500 | $1.00 | negligible | ~$1.00 |
| 5,000 | $10.00 | negligible | ~$10.00 |

Results are cached — one-time cost per property.

## Build Order
1. Models + Alembic migration (property_difficulties, org_cost_settings, bather_load_jurisdictions, property_jurisdictions)
2. Register models in `__init__.py`
3. Seed bather load jurisdictions
4. Pydantic schemas
5. ProfitabilityService (calculation engine)
6. BatherLoadService (jurisdiction-based calculator with estimation chain)
7. SatelliteAnalysisService (pool detection + vegetation analysis)
8. API routes + register in router
9. Frontend types
10. Settings page (validates API)
11. Bather load calculator page
12. Main profitability dashboard
13. Account detail drilldown
14. Satellite analysis UI (image with overlays, manual override)
15. Sidebar nav update
16. Map profitability overlay

## Competitor Gap Summary
No competitor has any of these features:
- Account health scoring
- AI pricing recommendations
- Profitability on map overlay
- Predictive profitability trending
- Price increase impact modeling
- Jurisdiction-aware bather load calculator
- Difficulty scoring with estimation chain
- Automated pool detection from satellite imagery
- Automated vegetation/shade analysis from satellite imagery
