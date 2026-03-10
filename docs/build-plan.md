# QuantumPools — Production Build Plan

## Current State (as of 2026-03-10)
- Phases 0-2 complete (auth, RBAC, customers, properties, techs, visits, routes, maps, OR-Tools)
- Phase 3 partially complete (invoices/payments CRUD — missing email, PDF, Stripe webhooks, background worker)
- 16 database models, 43 API endpoints, 8 frontend pages
- No tests, no CI/CD, no platform admin
- DigitalOcean `.do/app.yaml` exists but not yet deployed
- Production readiness: ~65%

## Target State
Enterprise SaaS deployed on DigitalOcean, marketable to pool service companies nationwide. Two admin layers (org admin + platform admin). Profitability analysis and Pool Scout as key differentiators.

---

## Feature Priority Tiers

### CRITICAL (must have for launch)
These are table stakes or core differentiators — can't launch without them.

- Profitability analysis (differentiator, needed for own business)
- LSI calculator + dosing recommendations (table stakes for pool software)
- Multiple bodies of water per property (table stakes — every pool competitor has this)
- AutoPay / recurring billing with auto-retry (table stakes — customers expect this)
- Service email reports ("digital door hanger" — readings, photos, checklist)
- Email service (invoices, reminders, password reset)
- PDF generation (invoices)
- Stripe payment integration
- Background worker (overdue detection, reminders, recurring invoices)
- Guided workflows / service checklists with enforcement
- Customer portal (self-service invoices, history, service requests)
- Platform admin (tenant management, subscriptions, feature flags)
- Satellite pool/vegetation detection (differentiator — nobody else has this)

### RECOMMENDED (strong competitive advantage, build before or shortly after launch)
- Technician scorecards (performance accountability)
- Filter/salt cell auto-scheduling (prevents forgotten maintenance)
- Good-better-best proposals (proven 25-40% ticket increase)
- Equipment tracking with warranty/serial/lifecycle
- Photo documentation per visit
- Customer feedback / review collection (Google review requests)
- Broadcast email / marketing campaigns (seasonal upsells)
- E-signatures on quotes/contracts
- Quote/invoice view tracking (opened/viewed)
- Custom alerts (out-of-range chemicals, time overruns)
- SMS notifications (Twilio — visit reminders, overdue alerts)

### NICE TO HAVE (post-launch, user-feedback driven)
- LaMotte Spin Touch integration (small user base, most use vials/strips)
- Consumer financing (Sunbit/GreenSky — valuable but complex integration)
- AI voice receptionist (emerging, not expected yet)
- AI website chatbot (lead qualification)
- Online customer booking (self-service scheduling)
- Time clock / timesheet with GPS verification
- Fleet tracking / dashcam
- Barcode scanner for inventory
- Supply house integration (Heritage Pool Supply)
- Surcharging (CC fee pass-through)
- Website builder
- Driver performance scoring

---

## PHASE 3b: Profitability Analysis (START HERE)
_Priority: CRITICAL — needed for own business operations, key differentiator_
_Detailed spec: [profitability-feature-plan.md](profitability-feature-plan.md)_

### 3b.1 Database & Models
- [ ] Create `OrgCostSettings` model (burdened labor rate, vehicle $/mile, chemical $/gal, overhead, target margin)
- [ ] Create `PropertyDifficulty` model (measured fields + scored fields + overrides)
- [ ] Create `BatherLoadJurisdiction` model (10 jurisdiction calculation methods)
- [ ] Create `PropertyJurisdiction` model (links properties to jurisdiction)
- [ ] Add relationships to `Property` model (difficulty, jurisdiction)
- [ ] Alembic migration for all new tables
- [ ] Register models in `__init__.py`
- [ ] Seed bather load jurisdictions (CA, ISPSC, MAHC, TX, FL, AZ, NY, GA, NC, IL)

### 3b.2 Schemas & Services
- [ ] Pydantic schemas: cost settings, difficulty, profitability responses, whale curve, pricing suggestions, bather load
- [ ] `ProfitabilityService` — core calculation engine
  - [ ] Difficulty score computation (weighted composite from measured + scored fields)
  - [ ] Difficulty-to-multiplier mapping (0.8x to 1.6x)
  - [ ] Per-account cost breakdown (chemical, labor, travel, overhead)
  - [ ] Margin and suggested rate calculation
  - [ ] Overview aggregation with filters (tech, route day, margin range, difficulty)
  - [ ] Whale curve data generation
  - [ ] Pricing suggestions (accounts below target, sorted by rate gap)
- [ ] `BatherLoadService` — jurisdiction-aware calculator
  - [ ] Calculation method per jurisdiction (depth-based, flat, dual-test, volume-based)
  - [ ] Estimation chain (gallons→sqft, sqft→depth split, volume→GPM)
  - [ ] Bulk jurisdiction assignment by city/zip
- [ ] `SatelliteAnalysisService` — automated pool detection
  - [ ] Google Static Maps API integration (fetch satellite image by lat/lng)
  - [ ] OpenCV pool detection (HSV blue segmentation, contour analysis, sqft calculation)
  - [ ] Vegetation/canopy detection (HSV green segmentation in buffer zone)
  - [ ] Overhang detection (green pixels overlapping pool contour)
  - [ ] Shadow analysis (value channel thresholding for seasonal compensation)
  - [ ] Hardscape ratio calculation
  - [ ] Confidence scoring and estimated field tagging
  - [ ] Result caching (one-time per property)

### 3b.3 API Endpoints
- [ ] `GET /profitability/overview` — all accounts with metrics, filterable
- [ ] `GET /profitability/account/{id}` — single account cost breakdown
- [ ] `GET /profitability/whale-curve` — chart data
- [ ] `GET /profitability/suggestions` — pricing recommendations
- [ ] `GET/PUT /profitability/settings` — org cost config (owner/admin)
- [ ] `GET/PUT /profitability/properties/{id}/difficulty` — difficulty factors
- [ ] `GET /profitability/jurisdictions` — list bather load methods
- [ ] `PUT /profitability/properties/{id}/jurisdiction` — assign jurisdiction
- [ ] `POST /profitability/bulk-jurisdiction` — bulk assign by locality
- [ ] `GET /profitability/properties/{id}/bather-load` — calculate bather load
- [ ] `POST /properties/{id}/detect-pool` — satellite analysis (single)
- [ ] `POST /properties/bulk-detect` — satellite analysis (batch)
- [ ] `GET /properties/{id}/satellite-analysis` — cached analysis results
- [ ] Register all routes in `router.py`

### 3b.4 Frontend
- [ ] TypeScript types for all profitability/difficulty/bather load responses
- [ ] `/profitability` — main dashboard
  - [ ] Summary cards (total accounts, avg margin, below target count, revenue vs cost)
  - [ ] Whale curve chart (Recharts LineChart)
  - [ ] Profitability quadrant scatter (Recharts ScatterChart, dot size by difficulty)
  - [ ] Sortable/filterable account table ranked by margin
  - [ ] Filter bar (tech, route day, margin range, difficulty range)
- [ ] `/profitability/[customerId]` — account detail drilldown
  - [ ] Cost waterfall chart (Recharts BarChart)
  - [ ] Difficulty score breakdown (sliders for scored, inputs for measured)
  - [ ] Estimated vs actual indicators on each field
  - [ ] Bather load result with jurisdiction selector
  - [ ] Current rate vs suggested rate with rate gap
  - [ ] Satellite image with overlays (pool blue, canopy green, overhang orange)
  - [ ] "Re-analyze" and manual override controls
- [ ] `/profitability/settings` — org cost configuration (owner/admin only)
- [ ] `/profitability/bather-load` — standalone calculator tool
  - [ ] Jurisdiction selector
  - [ ] Pool characteristics inputs with estimation fallbacks
  - [ ] Calculated max bather load display
  - [ ] Bulk assign by city/zip
- [ ] Sidebar nav: add "Profitability" with TrendingUp icon
- [ ] Map profitability overlay component (green/yellow/red markers by margin)
- [ ] Add `opencv-python-headless` to backend requirements

---

## PHASE 3c: Complete Invoicing & Billing
_Priority: CRITICAL — can't charge customers without this_

### 3c.1 AutoPay & Recurring Billing
- [ ] `AutoPaySettings` on Customer model (enabled, payment_method_id, schedule)
- [ ] Stripe customer creation and payment method storage (SetupIntent flow)
- [ ] Auto-charge on billing schedule (1st of month, 15th, custom)
- [ ] Auto-retry on declined cards (retry after 3 days, then 7 days, then notify)
- [ ] Failed payment notification emails
- [ ] Customer self-service AutoPay management (in portal)

### 3c.2 Email Service
- [ ] Create `EmailService` using aiosmtplib (already in requirements)
- [ ] HTML email templates (invoice sent, payment received, overdue reminder, password reset)
- [ ] Template rendering engine (Jinja2)
- [ ] Wire invoice "send" endpoint to actually email the customer
- [ ] Email delivery tracking (sent_at, opened_at if using tracking pixel)

### 3c.3 Service Email Reports ("Digital Door Hanger")
- [ ] Auto-generate post-visit email per customer
- [ ] Include: chemical readings, dosages applied, service checklist status, tech notes
- [ ] Include: visit photos (before/after)
- [ ] Configurable per org (enable/disable, customize template)
- [ ] Customer can reply to report (creates service request)

### 3c.4 PDF Generation
- [ ] Create `PDFService` using reportlab (already in requirements)
- [ ] Invoice PDF template (company branding, line items, totals, payment terms)
- [ ] PDF storage (DigitalOcean Spaces / S3-compatible — BarkurrRX pattern)
- [ ] `GET /invoices/{id}/pdf` endpoint to generate/download
- [ ] Attach PDF to invoice emails

### 3c.5 Stripe Integration
- [ ] Stripe webhook endpoint (`POST /webhooks/stripe`)
- [ ] Payment intent creation for invoice payment
- [ ] Checkout session flow
- [ ] Webhook handlers: payment_intent.succeeded, charge.refunded, etc.
- [ ] Auto-update invoice status on successful payment
- [ ] Stripe customer sync (create Stripe customer on first invoice)

### 3c.6 Background Worker
- [ ] Create `worker.py` with APScheduler (async, matches BarkurrRX pattern)
- [ ] Scheduled jobs:
  - [ ] Overdue invoice detection (daily — mark sent invoices past due date)
  - [ ] Payment reminder emails (configurable: 3 days before due, on due date, 7 days overdue)
  - [ ] Recurring invoice generation (monthly for customers on billing schedules)
  - [ ] AutoPay charge execution
  - [ ] AutoPay retry on failed payments
  - [ ] Filter/salt cell maintenance reminders (Phase 3d)
- [ ] Add worker to `docker-compose.yml` and `.do/app.yaml`

---

## PHASE 3d: Core Pool Operations Enhancements
_Priority: CRITICAL — table stakes features missing from current build_

### 3d.1 Multiple Bodies of Water
- [ ] `BodyOfWater` model (property_id FK, type: pool/spa/wading/fountain, name, gallons, sqft, equipment, chemical settings)
- [ ] Migrate existing property pool fields to body_of_water records
- [ ] Chemical readings linked to body_of_water (not just property)
- [ ] Visits can service multiple bodies per property
- [ ] Separate billing rates per body of water
- [ ] Separate equipment tracking per body
- [ ] Update all existing endpoints to support body_of_water context
- [ ] Frontend: property detail shows bodies of water as sub-sections

### 3d.2 LSI Calculator & Dosing Engine
- [ ] `DosingService` — water chemistry calculation engine
  - [ ] Langelier Saturation Index (LSI) calculation from readings (pH, temp, calcium hardness, total alkalinity, TDS/CYA)
  - [ ] Target ranges by pool type (residential, commercial, spa)
  - [ ] Dosing recommendations: what chemical, how much, for given pool volume
  - [ ] Chemical products database (chlorine types, acid, soda ash, calcium chloride, CYA, etc.)
  - [ ] Dose calculation per product (oz/lbs needed based on current vs target reading and gallons)
- [ ] `GET /chemistry/{body_of_water_id}/lsi` — current LSI with interpretation
- [ ] `GET /chemistry/{body_of_water_id}/dosing` — recommended dosing from latest readings
- [ ] Frontend: LSI gauge visualization (corrosive ↔ scaling range)
- [ ] Frontend: dosing recommendation cards after entering readings
- [ ] Mobile-friendly: tech enters readings in field → instant dosing guidance

### 3d.3 Guided Workflows & Service Checklists
- [ ] `WorkflowTemplate` model (org-scoped, name, steps as ordered JSON)
- [ ] `WorkflowStep` — step type (reading, checkbox, photo, note, dosing), required flag, order
- [ ] `VisitWorkflow` — instance of workflow for a specific visit, tracks completion per step
- [ ] Assign workflow templates to service types or individual properties
- [ ] Enforce step order (can't skip required steps)
- [ ] Required photos at specific steps
- [ ] Auto-log chemical readings from workflow steps into chemical_readings table
- [ ] Frontend: workflow builder (drag-drop steps, set requirements)
- [ ] Frontend: tech visit view follows guided workflow step-by-step

### 3d.4 Filter/Salt Cell Auto-Scheduling
- [ ] Maintenance schedule settings per body of water (filter clean every X weeks, salt cell clean every Y weeks)
- [ ] Background worker auto-creates one-time jobs/visits when maintenance is due
- [ ] Notification to tech and/or office when upcoming
- [ ] Track last completed date, next due date
- [ ] Dashboard widget: upcoming maintenance across all properties

---

## PHASE 4: Customer Portal
_Priority: CRITICAL — required for self-service and reducing admin workload_

### 4.1 Portal Auth
- [ ] `PortalUser` model (linked to Customer, separate from internal User)
- [ ] Portal login/registration endpoints (`/api/v1/portal/auth/...`)
- [ ] Portal JWT scope (limited permissions, can't access admin routes)
- [ ] Portal invitation flow (admin sends invite email → customer creates account)
- [ ] Password reset for portal users

### 4.2 Portal API
- [ ] `GET /portal/profile` — customer info
- [ ] `GET /portal/properties` — customer's properties with bodies of water
- [ ] `GET /portal/invoices` — customer's invoices with payment status
- [ ] `POST /portal/invoices/{id}/pay` — initiate Stripe payment
- [ ] `GET /portal/visits` — service history for customer's properties
- [ ] `GET /portal/chemical-readings` — water quality history with LSI
- [ ] `POST /portal/service-requests` — submit service request
- [ ] `GET /portal/service-requests` — view request status
- [ ] `PUT /portal/autopay` — manage AutoPay settings

### 4.3 Portal Frontend
- [ ] `/portal` route group (separate layout from admin dashboard)
- [ ] Portal login page
- [ ] Portal dashboard (upcoming visits, recent invoices, account balance)
- [ ] Invoice list with "Pay Now" button (Stripe checkout)
- [ ] AutoPay enrollment/management
- [ ] Service history timeline
- [ ] Chemical readings chart (water quality over time, LSI trend)
- [ ] Service request form
- [ ] Mobile-first design (customers will use phones)

---

## PHASE 5: EMD Inspection Intelligence (Pool Scout)
_Priority: CRITICAL differentiator — Sacramento regional moat_

### 5.1 Scraping Infrastructure
- [ ] Playwright service setup (headless browser for EMD site)
- [ ] EMD facility search and scraping logic
- [ ] Rate limiting and retry logic for scraping
- [ ] Scheduled scraping jobs (APScheduler — weekly/configurable)

### 5.2 Data Extraction
- [ ] `EMDFacility` model (name, address, permit info, geocoded location)
- [ ] `EMDInspectionReport` model (date, inspector, result, pdf_url)
- [ ] `EMDViolation` model (code, description, severity, status)
- [ ] PDF extraction service (parse inspection report PDFs for structured data)
- [ ] Alembic migration for EMD tables

### 5.3 AI Analysis
- [ ] Claude API integration for violation summarization
- [ ] Risk scoring per facility (frequency, severity, patterns)
- [ ] Trend analysis (improving vs declining facilities)
- [ ] Actionable recommendations generation

### 5.4 EMD Frontend
- [ ] `/emd` dashboard (replace placeholder)
  - [ ] Facility search and map view
  - [ ] Inspection history timeline per facility
  - [ ] Violation breakdown charts
  - [ ] AI-generated summaries and risk scores
  - [ ] Export/report generation
- [ ] Map overlay showing EMD facilities with risk coloring

---

## PHASE 6: Platform Admin
_Priority: CRITICAL — required before onboarding external customers_

### 6.1 Platform Admin Backend
- [ ] `is_platform_admin` flag on User model (or separate PlatformAdmin model)
- [ ] Platform admin auth guard (`get_current_platform_admin` dependency)
- [ ] Admin API endpoints:
  - [ ] `GET /admin/organizations` — list all orgs with stats (users, customers, properties, revenue)
  - [ ] `GET /admin/organizations/{id}` — org detail with usage metrics
  - [ ] `PUT /admin/organizations/{id}` — update org (activate/deactivate, plan tier, feature flags)
  - [ ] `GET /admin/users` — list all users across orgs
  - [ ] `PUT /admin/users/{id}` — manage user (activate/deactivate, reset password, impersonate)
  - [ ] `GET /admin/stats` — platform-wide metrics (total orgs, users, API calls, revenue)
  - [ ] `GET /admin/system-health` — service status, DB metrics, Redis stats, queue depth
  - [ ] `GET /admin/audit-log` — system-wide audit trail
  - [ ] `POST /admin/feature-flags` — enable/disable features per org or globally
  - [ ] `GET /admin/billing` — subscription status, MRR, churn metrics

### 6.2 Platform Admin Frontend
- [ ] `/admin` route group (separate from org dashboard, platform admin only)
- [ ] Organization management page (list, detail, activate/deactivate)
- [ ] User management page (cross-org, with impersonation)
- [ ] Platform dashboard (MRR, active orgs, user growth, system health)
- [ ] Feature flag management
- [ ] Audit log viewer
- [ ] System health monitoring dashboard

### 6.3 Subscription & Plan Management
- [ ] Plan tiers model (free/starter/professional/enterprise with feature limits)
- [ ] Feature flag system (per-org feature enablement)
- [ ] Usage tracking (API calls, properties, users per org)
- [ ] Plan enforcement middleware (check limits on relevant endpoints)
- [ ] Stripe subscription integration (separate from invoice payments)
  - [ ] Subscription creation/modification
  - [ ] Billing portal link generation
  - [ ] Webhook handlers for subscription events

### 6.4 Audit & Compliance
- [ ] `AuditLog` model (who, what, when, before/after values)
- [ ] Audit middleware (auto-log all write operations)
- [ ] Data retention policies
- [ ] GDPR/privacy compliance (data export, account deletion)

---

## PHASE 7: Production Hardening
_Priority: CRITICAL — must complete before public launch_

### 7.1 Testing
- [ ] pytest setup with async fixtures (pytest-asyncio)
- [ ] Test database configuration (separate test DB or transactions)
- [ ] Unit tests for all services (profitability, bather load, difficulty, dosing, LSI)
- [ ] Integration tests for API endpoints (auth flow, CRUD, org scoping)
- [ ] Frontend component tests (React Testing Library)
- [ ] E2E tests for critical flows (Playwright — login, create customer, generate invoice, pay)
- [ ] Test coverage target: 80%+ on services, 60%+ overall

### 7.2 CI/CD Pipeline
- [ ] GitHub Actions workflow:
  - [ ] On PR: lint (ruff/eslint), type check (mypy/tsc), run tests
  - [ ] On merge to master: build, test, deploy to staging
  - [ ] Manual promotion: staging → production
- [ ] Pre-commit hooks (ruff, eslint, prettier)
- [ ] Branch protection rules on master

### 7.3 Logging & Monitoring
- [ ] Structured logging (structlog or python-json-logger)
- [ ] Log levels: ERROR→Sentry, WARN+INFO→log aggregation
- [ ] Request/response logging middleware (sanitized — no secrets)
- [ ] Performance monitoring (response time tracking per endpoint)
- [ ] Uptime monitoring (external health check service)
- [ ] Alert rules (error rate spike, response time degradation, disk/memory)

### 7.4 Security Hardening
- [ ] Security headers audit (CSP, HSTS, etc.)
- [ ] Input validation audit (all endpoints)
- [ ] SQL injection protection audit (parameterized queries — covered by SQLAlchemy)
- [ ] XSS protection audit (frontend)
- [ ] CORS configuration tightening for production domain
- [ ] Rate limiting tuning per endpoint (auth endpoints stricter)
- [ ] API key rotation strategy
- [ ] Secrets management (DigitalOcean encrypted env vars)
- [ ] Dependency vulnerability scanning (pip-audit, npm audit)

### 7.5 Performance
- [ ] Database query optimization (N+1 detection, proper eager loading)
- [ ] Redis caching strategy (geocoding already cached — add profitability, satellite, dosing)
- [ ] Database connection pooling tuning
- [ ] Frontend bundle analysis and optimization
- [ ] Image/asset optimization (Next.js Image component)
- [ ] API response pagination audit (all list endpoints)

### 7.6 Data & Backup
- [ ] DigitalOcean managed DB backups (automatic daily, 7-day retention)
- [ ] Point-in-time recovery testing
- [ ] Data migration scripts for onboarding (import from spreadsheet, other software)
- [ ] Database seeding for demo/staging environments

---

## PHASE 8: Deployment & Launch
_Priority: Final gate before going live_

### 8.1 DigitalOcean Infrastructure
- [ ] Production environment setup (matches BarkurrRX pattern):
  - [ ] API service (FastAPI, professional-xs or higher)
  - [ ] Web service (Next.js, professional-xs or higher)
  - [ ] Background worker service (APScheduler)
  - [ ] PostgreSQL 15 managed database (production tier)
  - [ ] Redis managed database (for caching + job queues)
  - [ ] DigitalOcean Spaces (S3-compatible — invoice PDFs, satellite images)
- [ ] Domain setup: quantumpools.com (DNS, SSL auto via DO)
- [ ] CDN configuration for static assets
- [ ] Auto-scaling rules (if traffic warrants)

### 8.2 Environment Configuration
- [ ] Production environment variables (all secrets via DO encrypted env)
- [ ] Staging environment (separate app on DO, separate DB)
- [ ] Pre-deploy job: `alembic upgrade head` (matches BarkurrRX)
- [ ] Health check endpoints verified (API + frontend)
- [ ] CORS origins configured for production domain

### 8.3 Monitoring & Alerting
- [ ] Sentry projects: backend + frontend (already have DSN config)
- [ ] Uptime monitoring (UptimeRobot or similar)
- [ ] Error rate alerting
- [ ] Performance baseline established
- [ ] On-call runbook (common issues, rollback procedure)

### 8.4 Launch Checklist
- [ ] All critical features functional
- [ ] Security audit passed
- [ ] Performance tested under load
- [ ] Backup/restore tested
- [ ] Onboarding flow tested (new org signup → first customer → first invoice)
- [ ] Demo data available for sales
- [ ] Terms of service / privacy policy
- [ ] Support channel established

---

## PHASE 9: Recommended Features (Post-Launch Priority)
_Priority: Strong competitive advantage, build shortly after launch_

### 9.1 Technician Scorecards
- [ ] Performance metrics per tech: satisfaction ratings, chemical cost per stop, avg time per stop, callback rate
- [ ] Comparison views (tech vs tech, tech vs org average)
- [ ] Trend charts (improving/declining performance)
- [ ] Exportable reports for performance reviews

### 9.2 Good-Better-Best Proposals
- [ ] `Proposal` model with multiple options (tiers)
- [ ] Visual presentation layouts (list, stacked, side-by-side)
- [ ] Customer-facing proposal view with online approval
- [ ] E-signatures on approved proposals
- [ ] Auto-convert approved proposal to job/invoice
- [ ] Proposal view tracking (opened, time spent viewing)

### 9.3 Equipment Tracking & Lifecycle
- [ ] Equipment records per body of water (type, manufacturer, model, serial, install date, warranty expiry)
- [ ] Warranty expiration alerts
- [ ] Maintenance history per equipment
- [ ] Replacement recommendations (age-based, performance-based)
- [ ] Equipment photo documentation

### 9.4 Photo Documentation
- [ ] Per-visit photo upload (before/after, equipment condition, issues found)
- [ ] Photos attached to workflow steps
- [ ] Photos included in service email reports
- [ ] Photo gallery per property (historical visual record)
- [ ] Photo annotation (mark issues on image)

### 9.5 Customer Feedback & Reviews
- [ ] One-click feedback from service email (thumbs up/down + optional comment)
- [ ] Auto-route negative feedback to office before public review
- [ ] Auto-request Google review on positive feedback (timed delay)
- [ ] Feedback dashboard: NPS-style metrics per tech and org-wide

### 9.6 Marketing & Communication
- [ ] Broadcast email with segmentation (by tag, service day, tech, property type)
- [ ] Seasonal campaign templates (winterization, spring opening, heater install)
- [ ] SMS notifications (Twilio — visit reminders, overdue alerts, appointment confirmations)
- [ ] Quote/invoice view tracking (opened/viewed timestamp)

### 9.7 Custom Alerts
- [ ] Configurable alert rules (chemical out of range, service time exceeded, cost overrun)
- [ ] Alert delivery: in-app notification, email, SMS
- [ ] Alert dashboard for office staff
- [ ] Auto-create service request from critical alerts

---

## PHASE 10: Nice-to-Have Features (User-Feedback Driven)
_Priority: Build only when users request or market demands_

### 10.1 Hardware Integrations
- [ ] LaMotte Spin Touch Bluetooth integration (auto-sync chemical readings)
- [ ] Other water tester integrations as market demands

### 10.2 Financial Integrations
- [ ] Consumer financing (Sunbit or GreenSky — 0% APR, high approval)
- [ ] QuickBooks Online two-way sync (invoices, payments, customers)
- [ ] Surcharging (credit card fee pass-through option)

### 10.3 AI & Automation
- [ ] AI voice receptionist (after-hours call handling, lead qualification)
- [ ] AI website chatbot (24/7 lead capture)
- [ ] Predictive profitability trending
- [ ] Price increase impact modeling
- [ ] Customer churn prediction
- [ ] Seasonal demand forecasting
- [ ] Chemical usage anomaly detection

### 10.4 Operations
- [ ] Online customer booking (self-service scheduling)
- [ ] Time clock / timesheet with GPS verification
- [ ] Fleet tracking (vehicle location, idle time, driving behavior)
- [ ] Barcode scanner for inventory
- [ ] Supply house integration (Heritage Pool Supply — real-time cost sync)
- [ ] Google Calendar sync (tech schedules)
- [ ] Zapier/webhook integration (custom automations)

### 10.5 Platform & Market Expansion
- [ ] Public API with API keys for third-party integrations
- [ ] PWA support (mobile app experience without app store)
- [ ] Additional bather load jurisdictions as users request
- [ ] Pool Scout expansion beyond Sacramento (per-region scraping)
- [ ] Localization for seasonal differences (year-round vs seasonal markets)
- [ ] Canadian market support (metric units, provincial regulations)
- [ ] QuantumTax sync (tax preparation integration)

---

## Build Priority Summary

| Order | Phase | What | Why |
|---|---|---|---|
| 1 | **3b** | Profitability Analysis | Need it now for own business; key differentiator |
| 2 | **3c** | Complete Invoicing + AutoPay | Can't run a business without billing |
| 3 | **3d** | Core Pool Ops (bodies of water, LSI/dosing, workflows, auto-scheduling) | Table stakes — every competitor has these |
| 4 | **4** | Customer Portal | Self-service reduces admin workload |
| 5 | **6** | Platform Admin + Subscriptions | Must exist before onboarding external customers |
| 6 | **7** | Production Hardening | Tests, CI/CD, security — required for enterprise |
| 7 | **8** | Deployment & Launch | Go live |
| 8 | **5** | Pool Scout (EMD) | Regional differentiator, post-launch |
| 9 | **9** | Recommended Features | Scorecards, proposals, equipment, photos, marketing |
| 10 | **10** | Nice-to-Have | User-feedback driven |

_Plan is flexible — can jump between phases as needed. Each step is independent enough to pick up and put down._
