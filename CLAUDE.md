# QuantumPools - Claude Code Context

**Repo**: `git@github.com:nyrkik/quantum-pools.git`

## Project Overview
Enterprise pool service management platform consolidating:
- **BarkurrRX** (architecture reference): FastAPI + Next.js 16 + React 19 + TypeScript + Tailwind 4 + shadcn/ui
- **Quantum Pools (NAS)**: OR-Tools VRP route optimization, Leaflet maps, customer/tech management, multi-tenancy
- **Pool Scout Pro**: Health inspection scraping, PDF extraction, violation analysis, AI summarization

## Architecture

| Concern | Choice |
|---------|--------|
| Frontend | Next.js 16 + React 19 + TS + Tailwind 4 + shadcn/ui |
| Backend | FastAPI + Python 3.11+ (async throughout) |
| Database | PostgreSQL 15 + SQLAlchemy 2.0 async + Alembic |
| Maps | Leaflet via react-leaflet |
| Scraping | Playwright (replacing Selenium) |
| Auth | JWT HttpOnly cookies (access 24h + refresh 7d) |
| Deployment | DigitalOcean App Platform |
| Monitoring | Sentry (backend + frontend) |
| Background jobs | APScheduler (async) + Redis |
| Route optimization | Google OR-Tools VRP |
| Geocoding | OpenStreetMap primary, Google Maps fallback, DB cache |
| AI | Claude API (anthropic SDK) — Haiku for satellite + pool measurement Vision |
| Real-time | Redis Pub/Sub + WebSocket gateway (`/api/v1/ws`) — see `docs/realtime-events.md` |
| Email | Postmark (primary), SMTP (fallback) — see `docs/email-pipeline.md` |
| File uploads | Local disk (`./uploads/`), DO Spaces for prod |

## UI Standards

### Icon Actions (MANDATORY — never deviate)

All inline action icons use `Button variant="ghost" size="icon"`. No text labels on inline actions.

| Action | Icon | Size | Style |
|--------|------|------|-------|
| Save/confirm | `Check` | h-4 w-4 | `text-muted-foreground hover:text-green-600` |
| Cancel/revert | n/a | n/a | Text button (`variant="ghost" size="sm"` label "Cancel") — revert unsaved changes in a section |
| Close/exit | `X` | h-4 w-4 | `text-muted-foreground hover:text-destructive` — close edit mode, close dialogs |
| Edit (enter edit) | `Pencil` | h-3.5 w-3.5 | ghost button |
| Delete | `Trash2` | h-3.5 w-3.5 | `text-destructive`, always behind AlertDialog |
| Add | `Plus` | h-3.5 w-3.5 | ghost or outline button |
| Back/navigate up | `ArrowLeft` | h-4 w-4 | ghost button, top-left of page |
| Loading spinner | `Loader2` | matches context | `animate-spin` |
| Expand/collapse | `ChevronDown`/`ChevronUp` | h-3.5 w-3.5 | `text-muted-foreground` |

### Edit Mode Pattern

- **No "Edit" in title** — the page title stays the same as view mode
- **Edit mode indicator**: Cards get `border-l-4 border-primary` left border to signal edit state
- **Close edit**: `X` icon in top-right of the name/header tile (not in page header)
- **Section-level saves**: Each section saves independently via its own API endpoint

**Dirty tracking (MANDATORY for all edit modes):**
- Every editable component MUST track `isDirty` by comparing current form state to the original loaded state
- **Save/Cancel buttons**: Only visible when `isDirty === true`. Hidden when form matches original state.
- **Dirty border**: When dirty, card gets `border-l-4 border-amber-400` left border (replaces the `border-primary` edit indicator)
- **Unsaved changes guard**: If user clicks Cancel/X while dirty, show AlertDialog confirming discard
- **Implementation**: Store original state on edit enter (`useRef` or `useState`), compute `isDirty` by deep comparison with current form. Do NOT track dirty as a separate boolean that gets set on every keystroke — derive it from state comparison.
- **Buttons**: Save (`variant="default"`) and Cancel (`variant="ghost"`) use `size="sm"` with text labels — no icon-only save/cancel (too small on mobile)

### Visual Polish (MANDATORY — apply everywhere)

**Cards:**
- All `<Card>` get `shadow-sm` — subtle depth lift
- Inner sub-cards (view mode tiles) use `bg-muted/50` with no shadow
- In edit mode: parent card gets `bg-muted/50`, child edit tiles get `bg-background` (white) — form fields stand out against the shaded parent

**Tables:**
- Table header row: `bg-slate-100 dark:bg-slate-800` — solid gray, clearly distinct from data rows
- Table header text: `text-xs font-medium uppercase tracking-wide`
- Table rows: `hover:bg-blue-50 dark:hover:bg-blue-950` — visible blue tint on hover
- Alternating rows: odd index `bg-slate-50 dark:bg-slate-900` for scanability

**Section headers** (group titles like "Commercial", "Residential"):
- `bg-primary text-primary-foreground px-4 py-2.5` with icon + title + count
- Strong contrast — anchors the section visually
- Icon and count use `opacity-70` for subtle hierarchy within the header

**Status badges:**
- Active: `variant="default"` (filled primary)
- Inactive: `variant="secondary"` (gray)
- Pending: `variant="outline" className="border-amber-400 text-amber-600"`
- One-time: `variant="outline" className="border-blue-400 text-blue-600"`

**Enum/status display:**
- NEVER display raw enum values to users. Always title-case: `.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())`
- CSS `capitalize` is NOT sufficient — it only capitalizes the first letter ("written off" not "Written Off")
- Applies to: status badges, action types, payment methods, categories — any DB enum shown in UI

**General:**
- No gradients, heavy shadows, or heavy rounded corners
- Color is informational, not decorative
- `text-muted-foreground` for secondary information, never full black

## Network

See `~/.claude/CLAUDE.md` for full network topology, port registry, and Tailscale ACL.

## Project Structure

```
QuantumPools/
├── app/                              # FastAPI backend
│   ├── app.py                        # create_app() factory + /uploads static mount
│   ├── worker.py                     # APScheduler background jobs
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/versions/
│   ├── scripts/                       # One-off scripts (reimport, batch geocode)
│   ├── uploads/                       # Local file storage (measurements, etc.)
│   └── src/
│       ├── api/
│       │   ├── deps.py               # Auth deps, RBAC, org scoping
│       │   └── v1/                    # All route modules
│       ├── core/
│       │   ├── config.py             # Pydantic settings
│       │   ├── database.py           # Async engine, migration-only init
│       │   ├── security.py           # JWT, bcrypt, RBAC
│       │   ├── exceptions.py
│       │   ├── redis_client.py
│       │   └── rate_limiter.py
│       ├── middleware/
│       ├── models/                    # SQLAlchemy ORM (one file per model)
│       ├── schemas/                   # Pydantic request/response
│       ├── services/                  # Business logic layer
│       │   ├── agents/                # Email pipeline agents (orchestrator, classifier, matcher, etc.)
│       │   ├── deepblue/              # DeepBlue AI (engine, tools, eval, quota)
│       │   ├── inspection/            # Inspection scraper + PDF extractor
│       │   ├── emd/                   # EMD service (backward-compat aliases)
│       │   └── parts/                 # Parts catalog services
│       ├── seeds/
│       └── utils/
├── frontend/                          # Next.js 16
│   ├── app/                           # App router
│   │   └── portal/                    # Customer portal
│   ├── components/
│   │   ├── ui/                        # shadcn/ui primitives
│   │   ├── layout/                    # Sidebar (responsive) + mobile nav
│   │   ├── maps/                      # Leaflet components
│   │   ├── measurement/              # Pool measurement photo capture + results
│   │   └── {domain}/                  # Domain-specific components
│   └── lib/
│       ├── api.ts                     # API client (cookie auth + FormData upload)
│       ├── auth-context.tsx           # AuthProvider + useAuth
│       ├── ws.tsx                     # WebSocketProvider + useWSEvent/useWSRefetch hooks
│       ├── permissions.ts             # usePermissions hook (role + feature checks)
│       └── dev-mode.tsx               # Dev mode context (view-as-role)
├── docs/                              # Architecture docs (see Documentation section below)
├── docker-compose.yml
├── .do/app.yaml
└── CLAUDE.md
```

## Mandatory Processes

### Feedback Resolution
When fixing a user-submitted feedback item (FB-XXX), you MUST update the record:
```sql
UPDATE feedback_items SET status = 'resolved', resolved_by = 'Claude',
  resolved_at = NOW(), resolution_notes = 'What was done' WHERE feedback_number = X;
```
This is non-negotiable — every fix needs a written summary for audit trail.

### Deployment
After ANY code change, deploy via `/srv/quantumpools/scripts/deploy.sh`. Never restart individual services manually. The script builds frontend, restarts all 3 services (backend, frontend, agent poller), and verifies health.

### Email Code Changes
After touching any email-sending path, send a test email to brian.parrotte@pm.me and verify: (1) email arrives, (2) no 500 in logs, (3) AgentMessage record exists, (4) thread shows in inbox.

## Dev Environment Notes

- **Python venv**: `/home/brian/00_MyProjects/QuantumPools/venv` (NOT inside `app/`)
- **Alembic**: Run from `app/` dir using full path: `/home/brian/00_MyProjects/QuantumPools/venv/bin/alembic`
- **Backend**: systemd `quantumpools-backend.service` (uvicorn on 7061)
- **Frontend**: systemd `quantumpools-frontend.service` (next start production on 7060)
- **Deploy**: `/srv/quantumpools/scripts/deploy.sh` — builds frontend, restarts ALL 3 services, verifies health. Always use this, never restart individual services.
- **Restart** (legacy, do not use): `sudo systemctl restart quantumpools-backend` / `quantumpools-frontend`
- **Logs**: `sudo journalctl -u quantumpools-backend -f`
- **DB defaults are in Python only**: SQLAlchemy model defaults (e.g. `Boolean default=False`, `Integer default=30`) do NOT exist at the PostgreSQL column level. Raw SQL inserts must explicitly provide ALL not-null columns.
- **Org scoping**: Frontend does not send `X-Organization-Id` header. Backend `get_current_org_user` picks the first org for the user via `.limit(1)`. All users currently belong to a single org ("Pool Co").
- **Old app reference**: `/mnt/Projects/quantum-pools` — original single-tenant app. SQL dump with all customer/driver data at `backups/backup_pre_saas.sql`. Migration script at `app/scripts/migrate_from_old.py`.
- **Responsive layout**: Sidebar hidden on mobile, replaced with hamburger menu (Sheet). Main content uses `p-4 sm:p-6` padding, `pt-16` clears mobile top bar.
- **Properties under Customers**: Properties are accessed via Customer detail page (vertical stacked layout, no tabs), not as a top-level nav item. `/properties` route still exists for direct links.
- **Client detail layout**: Vertical stack — client card (with nested contact/billing tiles) → property tiles (with nested BOW tiles) → collapsible invoices accordion. No tabs.
- **BOW progressive disclosure**: BOW tiles have 3 levels — collapsed (name, gallons, minutes, service days), tech quick view (equipment, sanitizer, access, gate/dog), full manager details (dimensions, billing, pool info). Measure tool (Ruler button) is in the BOW header row.
- **Property override toggle**: Properties inherit client address/access info by default. "Different info for this property" toggle reveals address, gate code, access notes, dog, locked to day, notes fields.
- **Client list sorting**: Commercial-first default, then alphabetical. Sort arrows on all columns (Name, Property, Mgmt Company, Pool Type, Rate, Balance, Status). Management company field is dropdown of existing companies + "New company..." option.
- **Multi-day service**: `preferred_day` stores comma-separated days (e.g., "Mon,Wed,Fri"). Toggle buttons in client edit. Displayed as badges in BOW header.
- **Pool measurement per-BOW**: Measure page accepts `?bow={id}` query param, passes `body_of_water_id` in upload FormData, shows/applies to specific BOW.
- **Pool measurement scale reference**: Default is "Depth Marker Tile (6x6)" — standard commercial pool tiles used as scale reference. Claude Vision prompt prioritizes tile detection over placed objects. Residential pools default to yardstick.
- **Dashboard tiles**: Clickable — link to Customers, Properties, Routes, Invoices respectively.
- **File uploads**: Served via FastAPI StaticFiles mount at `/uploads`. Photos stored in `./uploads/measurements/{property_id}/`. Uploads bypass the Next.js rewrite proxy (body size limits) and go directly to the backend on port 7061. Photos are resized client-side to max 1600px before upload. CORS allows Tailscale + LAN origins.
- **BodyOfWater (BOW)**: Each Property has 1+ BodyOfWater records (pool, spa, hot_tub, wading_pool, fountain, water_feature). One is `is_primary=True`. Pool dimensions, equipment, gallons, service minutes all live on BOW. Property still has the old columns for backward compat during transition. Profitability, route optimization, measurements, and chemical readings all aggregate from BOWs. Migration `8c1a65b5a13d` created BOW table and backfilled from properties. API: `/api/v1/bodies-of-water/property/{id}` (list/create), `/api/v1/bodies-of-water/{id}` (get/update/delete).
- **Inspection Intelligence**: Health department inspection data. 5 models: `InspectionFacility`, `Inspection`, `InspectionViolation`, `InspectionEquipment`, `InspectionLookup`. 908 facilities, 1386 inspections, 8505 violations. Playwright scraper at `app/src/services/inspection/scraper.py`. PyMuPDF PDF extractor at `app/src/services/inspection/pdf_extractor.py`. **Tier-gated access**: `my_inspections`, `full_research`, `single_lookup`. API: `/api/v1/inspections/`. Frontend: `/inspections`. PDFs stored in `./uploads/inspection/`.
- **À La Carte Subscriptions**: Feature subscription system. 3 tables: `features` (9 features), `feature_tiers` (3 inspection tiers), `org_subscriptions`. Migration `e2caa91ea93a`. Organizations columns: `stripe_customer_id`, `billing_email`, `trial_ends_at`. `require_feature()` dependency in `deps.py` gates API endpoints. `FeatureService` checks subscriptions, base features, trials. `/v1/auth/me` returns `features: string[]` + `inspection_tier`. Frontend: `usePermissions()` merges role + feature checks. `FeatureGate` + `UpgradePrompt` components. Existing org grandfathered with all features. 8 routers gated: routes, invoices, payments, profitability, satellite, measurements, inspections, chemical-costs. Billing API: `GET /v1/billing/features` (public catalog), `GET /v1/billing/subscription` (owner/admin).
- **Satellite analysis per-BOW**: Each pool BOW gets its own satellite analysis and pin (1:1 via `body_of_water_id` on `satellite_analyses`). Spas/fountains excluded from satellite (use measurement tool). `SatelliteImage` stays property-keyed (one set of overhead photos per yard). API: `/v1/satellite/pool-bows` (list pool BOWs), `/v1/satellite/bows/{bow_id}` (get/pin/analyze). Frontend: `/satellite?bow={id}`. Migration `75f82d5141d5` added column + backfilled 73 analyses.

## Critical Reference Files

- `/home/brian/00_MyProjects/BarkurrRX/app/src/core/database.py` — migration-only DB init pattern
- `/home/brian/00_MyProjects/BarkurrRX/app/src/api/deps.py` — auth dependency chain
- `/home/brian/00_MyProjects/BarkurrRX/app/app.py` — app factory with lifespan, Sentry, middleware
- `/home/brian/00_MyProjects/BarkurrRX/frontend/lib/api.ts` — API client with cookie auth
- `/home/brian/00_MyProjects/BarkurrRX/frontend/lib/auth-context.tsx` — auth context pattern

## RBAC Roles

| Role | Customers | Properties | Routes | Visits | Invoices | Techs | Inspections | Settings |
|------|-----------|------------|--------|--------|----------|-------|-----|----------|
| owner | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD |
| admin | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | Read |
| manager | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | - |
| technician | Read | Read | Read own | CRUD own | - | Read | Read | - |
| readonly | Read | Read | Read | Read | Read | Read | Read | - |

### Role-Based UI Visibility

Frontend views are filtered by role. A `usePermissions()` hook exposes feature flags.

| Section | technician | manager | admin | owner |
|---------|-----------|---------|-------|-------|
| Equipment/sanitizer/access | yes | yes | yes | yes |
| Service schedule | own | all | all | all |
| Chemical readings | own | all | all | all |
| Measurement tool | no | yes | yes | yes |
| Dimensions/gallons | no | yes | yes | yes |
| Difficulty scoring | no | yes | yes | yes |
| Satellite analysis | no | yes | yes | yes |
| Route management | no | yes | yes | yes |
| Customer list (full) | no | yes | yes | yes |
| Rates/billing | no | no | yes | yes |
| Invoices/payments | no | no | yes | yes |
| Profitability | no | no | yes | yes |
| Tech management | no | no | yes | yes |
| Settings/org | no | no | no | yes |

## Architecture Principles (MANDATORY)

### Charts & Visualization
- **Simple bar charts**: use pure HTML/CSS divs. Full control over hover, click, selection — no library fighting us. The invoice monthly chart is a good example.
- **Complex charts** (scatter plots, line charts, multi-series, whale curves): use Recharts. It handles axis scaling, legends, and data density well.
- **Rule of thumb**: if you need per-bar click/hover interaction, don't use a charting library. If you need mathematical axis scaling across dozens of data points, use Recharts.

### Single Exit Points — one function per operation type.
Every operation that has side effects MUST go through a single service method. No inline implementations in routers.
- **Outbound customer email**: ALL paths go through `EmailService.send_agent_reply()` — signature, from-name, subject prefix handled there. Never call `send_email()` directly for customer-facing email.
- **Thread status**: after ANY message creation or modification, call `update_thread_status(thread_id)`. Never manually set thread.message_count, thread.status, etc.
- **Invoice creation**: always through `InvoiceService.create()` for numbering and totals. Agent code uses `InvoiceService` methods, not direct `Invoice()` constructors.
- **Visit completion**: always through `VisitService.complete()` or `VisitExperienceService.complete_visit()` — both calculate duration_minutes.

### Agent Learning — every AI agent gets smarter over time.
All AI agents use `AgentLearningService` to learn from human corrections:
- **Before generating**: call `learner.build_lessons_prompt()` to inject relevant past corrections into the prompt
- **After human action**: call `learner.record_correction()` with type "edit" (modified), "rejection" (dismissed), or "acceptance" (approved unchanged)
- **Agent types**: `email_classifier`, `email_drafter`, `deepblue_responder`, `command_executor`, `job_evaluator`, `estimate_generator`, `customer_matcher`, `equipment_resolver`
- **Relevance**: corrections are matched by agent_type + category + customer_id, limited to 10 most recent from last 90 days
- **Non-blocking**: learning queries are wrapped in try/except — never break the primary operation
- Table: `agent_corrections` — stores input_context, original_output, corrected_output, correction_type

### Real-Time Events — publish after every mutation the UI cares about.
New features that change data visible in the UI MUST publish an event. See `docs/realtime-events.md`.
- **Backend**: `from src.core.events import EventType, publish` → `await publish(EventType.XXX, org_id, {data})`
- **Frontend**: `useWSRefetch(["event.type"], refetchFn)` — triggers targeted refetch on event, debounced
- **Polling is the fallback**, not the primary. Frontend polls at 60s when WS is connected, 15s when disconnected.
- **Never block on publish** — wrap in try/except, events are non-critical

### Notification Consistency
- Notification type strings are centralized in `src/core/notification_types.py` — never use string literals
- Job assignment, completion, and auto-close all trigger notifications
- Thread assignment triggers notification

## Data Architecture Rules (MANDATORY)

**Single Source of Truth — never duplicate data between tables.**
- **Customer data** (name, address, phone): always read from `customers` table via FK. Agent tables (`agent_threads`, `agent_actions`, `agent_messages`) have `customer_name` as a FALLBACK for unmatched records only — when `customer_id`/`matched_customer_id` exists, join to Customer table for display.
- **Equipment**: read from `equipment_items` table (linked to `equipment_catalog` via `catalog_equipment_id`). Legacy flat strings on WaterFeature (`pump_type`, `filter_type`, etc.) are DEPRECATED — kept for backward compat but never read for display or business logic.
- **Pool dimensions** (gallons, sqft, shape, depth): read from `water_features` table. Legacy pool fields on `properties` table are DEPRECATED fallbacks — only used when WaterFeature records don't exist.
- **New features**: NEVER copy data from one table to another. Always FK to the source table and join at read time.

## Key Relationships

> Full model reference: `docs/data-model.md`

```
Organization 1──* OrganizationUser *──1 User
Organization 1──* Customer 1──* Property
Organization 1──* Tech
Organization 1──1 OrgCostSettings
Customer 1──* Invoice 1──* InvoiceLineItem
Customer 1──* Payment
Property 1──* WaterFeature (pool, spa, fountain, etc.)
Property 1──* Visit *──1 Tech
WaterFeature 1──1 SatelliteAnalysis (pools only)
WaterFeature 1──* PoolMeasurement
Visit 1──* ChemicalReading ──? WaterFeature
Visit 1──* VisitCharge
Tech 1──* Route 1──* RouteStop ──1 Property
ServiceCase 1──* AgentAction (jobs)
ServiceCase 1──? AgentThread
AgentThread 1──* AgentMessage
AgentThread 1──* AgentAction (jobs extracted from emails)
AgentAction 1──* AgentActionTask (checklist items)
AgentAction 1──* AgentActionComment
InspectionFacility 1──* Inspection 1──* InspectionViolation
InspectionFacility ──? Property (matched via address)
EquipmentCatalog 1──* EquipmentItem *──1 Property
```

## Phase Status

- [x] Phase 0: Foundation (Auth + skeleton end-to-end)
- [x] Phase 1: Core Business Operations (customers, properties, techs, visits, chemical readings)
- [x] Phase 2: Route Optimization & Maps (Leaflet, OR-Tools VRP, drag-drop)
- [x] Phase 3a: Invoicing CRUD (invoices, payments, estimates, approval workflows)
- [x] Phase 3b: Profitability Analysis (difficulty scoring, cost breakdown, bather load, satellite detection, whale curve)
- [x] Pool Measurement: Ground-truth dimensions via tech photos + Claude Vision
- [x] BodyOfWater: Multi-body support (pool, spa, fountain per property)
- [~] Phase 3c: Invoicing completion — email service (Postmark) DONE, PDF generation DONE, AutoPay/Stripe/recurring NOT STARTED
- [~] Phase 3d: Core Pool Ops — dosing engine PARTIAL, service checklists PARTIAL, guided workflows NOT STARTED
- [ ] Phase 4: Customer Portal (customer-facing login, service history, invoices)
- [x] Phase 5: Inspection Intelligence (Playwright scraping, PDF extraction, 908 facilities, frontend)
- [ ] Phase 6: Platform Admin (tenant management, subscriptions)
- [ ] Phase 7-10: See `docs/build-plan.md` for full roadmap

### Systems Built Outside Original Phases
- Email/Agent Pipeline: AI inbox with triage, classification, auto-drafting, customer matching, thread management
- DeepBlue: Conversational AI assistant with 29 domain tools, eval suite, usage tracking
- Service Cases: Unifying entity linking threads → jobs → invoices per customer issue
- Internal Messaging: Staff-to-staff messaging with threads, notifications, case linking
- Real-Time Events: Redis Pub/Sub + WebSocket gateway for instant UI updates
- Equipment & Parts: Catalog (114 entries), items per property, parts (434), vendor tracking
- Granular Permissions: 60-slug permission system with presets, custom roles, per-user overrides
- À La Carte Subscriptions: Feature gating with tiers, trial support, Stripe customer IDs
- Feedback System: In-app user feedback with screenshots and resolution tracking

## Documentation

Architecture docs live in `docs/`. Read these for system details beyond what CLAUDE.md covers.

| Doc | Covers |
|-----|--------|
| `docs/email-pipeline.md` | Full email flow: inbound → triage → classify → thread → draft → send |
| `docs/realtime-events.md` | WebSocket + Redis Pub/Sub, event types, frontend hooks, how to add events |
| `docs/data-model.md` | All 78 models organized by domain, relationships, conventions, deprecated fields |
| `docs/deepblue-architecture.md` | DeepBlue AI: engine, tools, eval suite, quota, knowledge gaps |
| `docs/ai-agents-plan.md` | 10 planned domain agents (product roadmap), current implementation status |
| `docs/build-plan.md` | Full phase roadmap with completion status, feature priority tiers |
| `docs/profitability-feature-plan.md` | Detailed spec for profitability (scoring weights, jurisdiction formulas) |
| `docs/competitive-research.md` | Market audit, competitor analysis, our differentiators (with build status) |
