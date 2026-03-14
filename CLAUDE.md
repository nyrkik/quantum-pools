# QuantumPools - Claude Code Context

**Repo**: `git@github.com:nyrkik/quantum-pools.git`

## Project Overview
Enterprise pool service management platform consolidating:
- **BarkurrRX** (architecture reference): FastAPI + Next.js 16 + React 19 + TypeScript + Tailwind 4 + shadcn/ui
- **Quantum Pools (NAS)**: OR-Tools VRP route optimization, Leaflet maps, customer/tech management, multi-tenancy
- **Pool Scout Pro**: EMD inspection scraping, PDF extraction, violation analysis, AI summarization

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
| File uploads | Local disk (`./uploads/`), DO Spaces for prod |

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
│       │   └── emd/                   # EMD-specific services
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
│       └── auth-context.tsx           # AuthProvider + useAuth
├── docs/
├── docker-compose.yml
├── .do/app.yaml
└── CLAUDE.md
```

## Dev Environment Notes

- **Python venv**: `/home/brian/00_MyProjects/QuantumPools/venv` (NOT inside `app/`)
- **Alembic**: Run from `app/` dir using full path: `/home/brian/00_MyProjects/QuantumPools/venv/bin/alembic`
- **Backend**: systemd `quantumpools-backend.service` (uvicorn on 7061)
- **Frontend**: systemd `quantumpools-frontend.service` (next start production on 7060)
- **Restart**: `sudo systemctl restart quantumpools-backend` / `quantumpools-frontend`
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

## Critical Reference Files

- `/home/brian/00_MyProjects/BarkurrRX/app/src/core/database.py` — migration-only DB init pattern
- `/home/brian/00_MyProjects/BarkurrRX/app/src/api/deps.py` — auth dependency chain
- `/home/brian/00_MyProjects/BarkurrRX/app/app.py` — app factory with lifespan, Sentry, middleware
- `/home/brian/00_MyProjects/BarkurrRX/frontend/lib/api.ts` — API client with cookie auth
- `/home/brian/00_MyProjects/BarkurrRX/frontend/lib/auth-context.tsx` — auth context pattern

## RBAC Roles

| Role | Customers | Properties | Routes | Visits | Invoices | Techs | EMD | Settings |
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

## Key Relationships

```
Organization 1──* OrganizationUser *──1 User
Organization 1──* Customer 1──* Property
Organization 1──* Tech
Organization 1──1 OrgCostSettings
Customer 1──1 BillingSchedule
Customer 1──* Invoice 1──* InvoiceLineItem
Customer 1──* Payment
Customer 1──1 PortalUser
Customer 1──* ServiceRequest
Property 1──* BodyOfWater (pool, spa, fountain, etc.)
Property 1──* Visit *──1 Tech
Property 1──* ChemicalReading ──? BodyOfWater
Property 1──1 PropertyDifficulty ──? BodyOfWater
Property 1──1 PropertyJurisdiction ──1 BatherLoadJurisdiction
Property 1──1 SatelliteAnalysis
Property 1──* PoolMeasurement ──? BodyOfWater
Visit 1──* ChemicalReading
Visit *──* Service (through VisitService)
Tech 1──* Route 1──* RouteStop ──1 Property
EMDFacility 1──* EMDInspectionReport 1──* EMDViolation
```

## Phase Status

- [x] Phase 0: Foundation (Auth + skeleton end-to-end)
- [x] Phase 1: Core Business Operations (customers, properties, techs, visits, chemical readings)
- [x] Phase 2: Route Optimization & Maps (Leaflet, OR-Tools VRP, drag-drop)
- [x] Phase 3a: Invoicing CRUD (invoices, payments — missing email/PDF/Stripe/worker)
- [x] Phase 3b: Profitability Analysis (models, difficulty scoring, cost breakdown, bather load calculator, frontend dashboard, satellite detection)
- [x] Pool Measurement: Ground-truth dimensions via tech photos + Claude Vision (upload, analyze, apply to property)
- [x] BodyOfWater: Multi-body support (pool, spa, fountain per property) — model, migration, CRUD, services, frontend
- [ ] Phase 3c: Complete Invoicing (email, PDF, Stripe, AutoPay, background worker)
- [ ] Phase 3d: Core Pool Ops (LSI/dosing, workflows)
- [ ] Phase 4: Customer Portal (customer-facing login, service history, invoices)
- [ ] Phase 5: EMD Inspection Intelligence (Playwright scraping, PDF extraction, AI summaries)
- [ ] Phase 6: Advanced Features (Stripe, equipment tracking, SMS, PWA)
