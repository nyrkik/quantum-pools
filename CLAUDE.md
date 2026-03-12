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
| AI | Claude API (anthropic SDK) |

## Network

See `~/.claude/CLAUDE.md` for full network topology, port registry, and Tailscale ACL.

## Project Structure

```
QuantumPools/
├── app/                              # FastAPI backend
│   ├── app.py                        # create_app() factory
│   ├── worker.py                     # APScheduler background jobs
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/versions/
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
│   │   ├── layout/                    # Sidebar, header, mobile nav
│   │   ├── maps/                      # Leaflet components
│   │   └── {domain}/                  # Domain-specific components
│   └── lib/
│       ├── api.ts                     # API client (cookie auth)
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
Property 1──* Visit *──1 Tech
Property 1──* ChemicalReading
Property 1──1 PropertyDifficulty
Property 1──1 PropertyJurisdiction ──1 BatherLoadJurisdiction
Property 1──1 SatelliteAnalysis
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
- [ ] Phase 3c: Complete Invoicing (email, PDF, Stripe, AutoPay, background worker)
- [ ] Phase 3d: Core Pool Ops (multiple bodies of water, LSI/dosing, workflows)
- [ ] Phase 4: Customer Portal (customer-facing login, service history, invoices)
- [ ] Phase 5: EMD Inspection Intelligence (Playwright scraping, PDF extraction, AI summaries)
- [ ] Phase 6: Advanced Features (Stripe, equipment tracking, SMS, PWA)
