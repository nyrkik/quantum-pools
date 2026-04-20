# QuantumPools - Claude Code Context

**Repo**: `git@github.com:nyrkik/quantum-pools.git`

## Business Context (CRITICAL — read before making any infrastructure decisions)

**Quantum Pools** is a SaaS product. It is the codebase in this repo. It will become a standalone LLC (currently under VVG LLC, transition planned). Its domain is `quantumpoolspro.com`. Its email infrastructure (sales@, support@, billing@) is QP's own concern.

**Sapphire Pool Service** is a pool service business — a DBA under BESC Enterprises Inc. (a ROBS C Corp with restrictive terms). Sapphire's domain is `sapphire-pools.com`. **Sapphire is a CUSTOMER of Quantum Pools**, not part of QP. It's the dogfood account because Brian owns both, but they are separate entities with separate concerns.

### The conflation rule (mandatory)

For every email/DNS/infra/billing/customer-facing decision, ask: "Is this a QP concern or a Sapphire concern?" and "Would a different customer configure this the same way?" If Sapphire diverges because Brian owns both, that's wrong — Sapphire is a customer.

**Past mistake (2026-04-09):** Set up Cloudflare Workers + Postmark managed mode for Sapphire. Sapphire belongs on Google Workspace. See `docs/sapphire-recovery-plan.md`.

## Product DNA (NON-NEGOTIABLE)

These are product-level rules. They override "easier to build" reasoning every single time. If a proposed design conflicts with any of these, the design is wrong — redesign, don't rationalize.

1. **Build for the 1,000th customer, not the 1st.** Sapphire is the dogfood customer, not the target. Every architecture/UX/data decision is evaluated as if a customer we haven't met will configure it. If a design only makes sense because Brian owns both businesses, it's wrong. See `feedback_building_for_market_not_sapphire.md`.

2. **Every AI agent learns — no static agents.** Any feature with AI output that a human reviews MUST be wired into `AgentLearningService` — inject lessons before generation, record every acceptance/edit/rejection after. Design the common UX path against the week-3+ accuracy assumption (85-95%+), not the week-1 assumption. The competitive moat is continuous domain-specific learning per org/customer/category — static AI features are commoditized. See `feedback_every_agent_learns.md` and `agent-learning-system.md`.

3. **The product learns the org, not just the agents.** Beyond per-agent accuracy, QP observes each org's behavior patterns (what modes they actually use, what defaults they repeatedly set, what they auto-do vs. manually do) and proposes org-level configuration, workflow, and default changes through the same `agent_proposals` system. Every feature must answer: "What's its efficiency ceiling after 6 months of use?" Config UIs are a last resort — auto-detect the right mode from behavior first. When config is unavoidable, plain-language opinionated choices with recommendations, never engineer-vocabulary enums. See `feedback_product_learns_the_org.md`.

4. **Never optimize for ease of build.** "Zero new UI," "reuses existing screens," "fastest to ship," and "minimal code" are NOT pros. Options are judged on user outcome, architectural soundness, and fit with DNA rules — never on implementation cost. If the right answer requires rebuilding existing code or inventing a seventh option, do it. See `feedback_never_optimize_for_ease.md`.

5. **AI never commits to the customer.** AI drafts; humans send. This applies to email (`feedback_no_auto_send.md`) AND to every AI-suggested action pill in the product (`feedback_action_pills_no_customer_commit.md`). Action pills open drafts or navigate. Internal-only actions (archive, snooze, assign) can be one-click with undo.

6. **Less work for the USER, not the engineer.** Engineering work is never the constraint. Every feature must reduce customer-facing user effort. If a feature adds clicks/approvals/review steps without a corresponding reduction elsewhere, it's wrong. See `feedback_less_work.md`.

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
| Email | Multi-mode: Gmail API (OAuth) + Postmark (outbound fallback) + Cloudflare Workers (managed mode inbound). Fernet-encrypted tokens. Folders (Inbox/Sent/Spam + custom). Sender tags with auto-folder routing. HTML rendering in sandboxed iframe. AI drafts every reply; humans always send via one-click approve (no auto-send). Postmark delivery webhooks. Gmail read/unread sync. CC support on compose. File attachments via Gmail MIME + Postmark API. See `docs/email-pipeline.md` |
| Payments | Stripe Checkout (test mode), webhook for confirmation, verify-on-return fallback |
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

- **Cards**: `<Card>` gets `shadow-sm`. View-mode sub-tiles `bg-muted/50` (no shadow). In edit mode: parent `bg-muted/50`, child edit tiles `bg-background`.
- **Tables**: header `bg-slate-100 dark:bg-slate-800`, text `text-xs font-medium uppercase tracking-wide`. Rows `hover:bg-blue-50 dark:hover:bg-blue-950`, odd rows `bg-slate-50 dark:bg-slate-900`.
- **Section headers**: `bg-primary text-primary-foreground px-4 py-2.5` with icon + title + count (icon/count `opacity-70`).
- **Status badges**: Active `variant="default"`; Inactive `variant="secondary"`; Pending `variant="outline" className="border-amber-400 text-amber-600"`; One-time `variant="outline" className="border-blue-400 text-blue-600"`.
- **Enums**: never raw. Title-case with `.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())`. CSS `capitalize` is insufficient.
- **General**: no gradients/heavy shadows/heavy rounded corners. Color is informational. Secondary text = `text-muted-foreground`, never full black.

## Network

See `~/.claude/CLAUDE.md` for full network topology, port registry, and Tailscale ACL.

## Project Structure

- **Backend** (`app/`): `app.py` factory, `worker.py` (APScheduler), `src/{api,core,middleware,models,schemas,services,seeds,utils}`. Services are grouped by domain: `agents/`, `deepblue/`, `inspection/`, `gmail/`, `parts/`, plus top-level `billing_service.py`, `thread_action_service.py`, `thread_ai_service.py`, `estimate_workflow_service.py`, `stripe_service.py`.
- **Frontend** (`frontend/`): Next.js App Router under `app/` (with `portal/` for customers), domain components under `components/{domain}/`, shared libs in `lib/` (`api.ts`, `auth-context.tsx`, `ws.tsx`, `permissions.ts`, `dev-mode.tsx`).
- **Docs**: `docs/` — see Documentation Index below.

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

### Database Backups
Nightly pg_dump + weekly restore-verification via Brian's crontab; ntfy on failure/staleness and on verify success. Runbook: `docs/backup-and-restore.md`.

### Testing

**Backend (pytest):**
- **Runner**: `pytest` from `app/` dir. Async via pytest-asyncio (auto mode, session-scoped event loop).
- **Test DB**: `quantumpools_test` on port 7062; drops + recreates schema on each session start (`DROP SCHEMA public CASCADE` + `create_all`) so model changes never drift. TRUNCATE CASCADE between tests. Safety rail: DB name must contain "test".
- **Run**: `cd /srv/quantumpools/app && /home/brian/00_MyProjects/QuantumPools/venv/bin/pytest tests/ -W ignore::DeprecationWarning`
- **Fixtures** (`tests/conftest.py`): `db_session`, `org_a`, `org_b`, `event_recorder` (re-exported from `tests/fixtures/event_recorder.py` for platform-events assertions).
- **When to add**: new security gate (auth/org filter), new send path, new shared failure-handling helper, new emit path. Red-test-first for bug fixes.

**Frontend (vitest + React Testing Library):**
- **Runner**: `vitest` with jsdom. Added 2026-04-18 as Step 7b of the AI Platform rollout.
- **Run**: `cd /srv/quantumpools/frontend && npm run test` (one-shot) or `npm run test:watch` (live).
- **Setup**: `tests/setup.ts` installs `@testing-library/jest-dom` matchers + auto-cleanup. Path aliases (`@/*`) via Vite's native tsconfigPaths resolution.
- **Test file convention**: `*.test.tsx` co-located with the component (e.g., `components/events/page-emitter.test.tsx`).
- **When to add**: new components with lifecycle / state logic worth verifying (effect ordering, event emission, conditional rendering). Component rendering smoke isn't enough — test the observable behavior that matters.
- **Npm install quirk**: use `--legacy-peer-deps` for dev-dependency installs (React 19 vs. `@emoji-mart/react`'s older peer range — project-wide).

### Documentation Alignment (MANDATORY)

Every create/rename/delete of a `docs/*.md` file must update the Documentation Index below **in the same commit**. `/cpu` verifies: `ls docs/*.md` ⇄ the index — any drift (orphan doc, or index entry missing file) is an error. Also grep cross-references for broken paths. CLAUDE.md is the single entry point; every doc must be reachable from here.

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
- **Inbox information architecture (2026-04-14)**: Email integrations live at `/inbox/integrations` (moved from `/settings/email`; 308 redirect in `next.config.ts`). Rules at `/inbox/rules`. Compose button at top of the inbox folder sidebar (`InboxFolderSidebar`), NOT in `PageLayout` header or app sidebar. Inbox filter chips: Clients (customer-matched threads), Handled (archive view), plus ops chips (Failed / Auto-Handled / Stale, owner+admin only). Thread row badges in fixed order: Sender tag → Category → Status → Stale.
- **Case ownership**: `manager_name` = coordinator (set at creation, reassignable via inline popover). `current_actor_name` = derived from open job assignees → pending thread assignees → "Awaiting customer" → manager fallback. Recomputed by `update_status_from_children()` on every job/thread mutation. 7 boolean flags auto-set from child state. Cases support `billing_name` for non-DB customers.
- **Properties inherit client info**: address/access fields default from Customer; "Different info for this property" toggle reveals per-property overrides.
- **Multi-day service**: `preferred_day` stores comma-separated days (e.g. `"Mon,Wed,Fri"`).
- **Pool measurement**: `?bow={id}` scopes to a specific WaterFeature. Default scale reference is depth marker tile (6×6); residential falls back to yardstick.
- **File uploads**: Served via FastAPI StaticFiles mount at `/uploads`. Photos stored in `./uploads/measurements/{property_id}/`. Uploads bypass the Next.js rewrite proxy (body size limits) and go directly to the backend on port 7061. Photos are resized client-side to max 1600px before upload. CORS allows Tailscale + LAN origins.
- **WaterFeature (WF)**: Each Property has 1+ WaterFeature records (pool, spa, hot_tub, wading_pool, fountain, water_feature). One is `is_primary=True`. Pool dimensions, equipment, gallons, service minutes all live on WF. Property still has the old columns for backward compat during transition. Profitability, route optimization, measurements, and chemical readings all aggregate from WFs. Table: `water_features`. API: `/api/v1/bodies-of-water/property/{id}` (list/create), `/api/v1/bodies-of-water/{id}` (get/update/delete).
- **Inspection Intelligence**: Playwright scraper (`app/src/services/inspection/`) + PyMuPDF PDF extractor. Tier-gated (`my_inspections`/`full_research`/`single_lookup`). PDFs at `./uploads/inspection/<year>/<id>.pdf`. Rate-limit 8s via `InspectionScraper._request()` — never call `page.goto()` directly. Sacramento is the only CA county with online reports; `PLACER_PLACEHOLDER` is aspirational. Multi-building facilities use `(facility_id, program_identifier)` unique index. QC: `scripts/audit_inspections.py`, `scripts/qc_inspections.py`.
- **À La Carte Subscriptions**: `require_feature()` dep in `deps.py` gates 9 routers (routes, invoices, payments, profitability, satellite, measurements, inspections, chemical-costs, deepblue). `FeatureService` checks subscriptions/base features/trials. `/v1/auth/me` returns `features[]` + `inspection_tier`. Frontend merges role + feature via `usePermissions()`; gate UI with `FeatureGate` + `UpgradePrompt`. Existing org grandfathered.
- **Satellite analysis per-WF**: Pool WFs only (spas/fountains use measurement). 1:1 via `water_feature_id` on `satellite_analyses`. `SatelliteImage` stays property-keyed. API under `/v1/satellite/`. Frontend: `/satellite?bow={id}`.

## RBAC Roles

| Role | Customers | Properties | Routes | Visits | Invoices | Techs | Inspections | Settings |
|------|-----------|------------|--------|--------|----------|-------|-----|----------|
| owner | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD |
| admin | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | Read |
| manager | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | CRUD | - |
| technician | Read | Read | Read own | CRUD own | - | Read | Read | - |
| readonly | Read | Read | Read | Read | Read | Read | Read | - |

### Role-Based UI Visibility

Frontend views are filtered by role via `usePermissions()` (`frontend/lib/permissions.ts`). Source of truth for which sections each role sees — check the hook, don't restate the matrix here.

## Architecture Principles (MANDATORY)

### Charts & Visualization
- **Simple bar charts**: use pure HTML/CSS divs. Full control over hover, click, selection — no library fighting us. The invoice monthly chart is a good example.
- **Complex charts** (scatter plots, line charts, multi-series, whale curves): use Recharts. It handles axis scaling, legends, and data density well.
- **Rule of thumb**: if you need per-bar click/hover interaction, don't use a charting library. If you need mathematical axis scaling across dozens of data points, use Recharts.

### Single Exit Points — one function per operation type.
Every operation that has side effects MUST go through a single service method. No inline implementations in routers.
- **Outbound customer email**: ALL paths go through `EmailService.send_agent_reply()` — signature, from-name, subject prefix, HTML body handled there. Never call `send_email()` directly for customer-facing email. Provider auto-falls back from Postmark to SMTP on failure.
- **Thread status**: after ANY message creation or modification, call `update_thread_status(thread_id)`. Never manually set thread.message_count, thread.status, etc.
- **Outbound threads are invisible**: Threads where `last_direction == "outbound"` (broadcasts, sent emails without replies) are excluded from the default inbox view and the unread count. They reappear when a customer replies. Never mark outbound-only threads as unread.
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

### Notifications
Notification type strings centralized in `src/core/notification_types.py` — never use string literals. Job assignment/completion/auto-close and thread assignment all trigger notifications.

## Data Architecture Rules (MANDATORY)

**Single Source of Truth — never duplicate data between tables.**
- **Customer data** (name, address, phone): always read from `customers` table via FK. Agent tables (`agent_threads`, `agent_actions`, `agent_messages`) have `customer_name` as a FALLBACK for unmatched records only — when `customer_id`/`matched_customer_id` exists, join to Customer table for display.
- **Equipment**: read from `equipment_items` table (linked to `equipment_catalog` via `catalog_equipment_id`). Legacy flat strings on WaterFeature (`pump_type`, `filter_type`, etc.) are DEPRECATED — kept for backward compat but never read for display or business logic.
- **Pool dimensions** (gallons, sqft, shape, depth): read from `water_features` table. Legacy pool fields on `properties` table are DEPRECATED fallbacks — only used when WaterFeature records don't exist.
- **Outbound customer recipient addresses** (estimate / invoice send): resolve from `customer_contacts` filtered by `receives_estimates` / `receives_invoices` (primary first). `customers.email` is a legacy fallback used only when no matching contacts exist. `EstimateWorkflowService._resolve_recipients` and `send_invoice` in `app/src/api/v1/invoices.py` are the canonical implementations — mirror them for any new outbound-to-customer path.
- **New features**: NEVER copy data from one table to another. Always FK to the source table and join at read time.

## Key Relationships

> Full model reference: `docs/data-model.md`. Core hubs:

- **Organization** → Customer, Tech, EmailIntegration, InboxRule, InboxFolder, OrgCostSettings
- **Customer** → Property, Invoice (→ LineItem), Payment
- **Property** → WaterFeature (pool/spa/fountain), Visit, EquipmentItem
- **WaterFeature** → SatelliteAnalysis (pools 1:1), PoolMeasurement, ChemicalReading (via Visit)
- **ServiceCase** (hub) → AgentThread, AgentAction (jobs), DeepBlueConversation, Invoice
- **AgentThread** → AgentMessage, AgentAction, InboxFolder
- **InspectionFacility** → Inspection → InspectionViolation; matched to Property by address

## Phase Status

Completed phases + full roadmap: see `docs/build-plan.md`. In-flight work:
- [~] Phase 3c: Invoicing — webhook PARTIAL; email/PDF/Stripe Checkout/pay page/non-client invoices/AutoPay DONE.
- [~] Phase 3d: Core Pool Ops — dosing engine + checklists PARTIAL; guided workflows NOT STARTED.
- [~] Phase 5b: Email Integrations — managed mode + Gmail API OAuth DONE (Sapphire connected). No auto-send (see `memory/feedback_no_auto_send.md`). Unified `inbox_rules` JSONB; `InboxRulesService` is the sole matcher. Gmail spam bidirectional sync + 30-day retention. MS Graph/forwarding PLANNED. See `docs/email-strategy.md` + `docs/email-pipeline.md`.
- [ ] Phase 4: Customer Portal.
- [ ] Phase 6: Platform Admin (tenant management, subscriptions).
- [ ] Phases 7-10: `docs/build-plan.md`.

### Systems Built Outside Original Phases
- **Email/Agent Pipeline**: AI inbox — triage, classification, drafting, customer matching, thread management.
- **DeepBlue**: conversational AI assistant with 29 domain tools, eval suite, usage tracking.
- **Service Cases**: hub linking threads/jobs/invoices/internal threads/DeepBlue. Manager + derived actor; 7 attention flags; inline reassign; non-DB customer support. All `case_id` writes through `ServiceCaseService.set_entity_case()`. Linking a thread to a case cascades to its jobs (so orchestrator-created caseless jobs inherit a case the moment the thread gets linked). Closing a case cascades open jobs to `done`/`cancelled` with `closed_by_case_cascade=true`; reopening prompts the user to selectively reopen the cascade-closed jobs. Auto-closes when jobs done + invoice sent; closed is terminal. Jobs may only exist inside a case — `ThreadAIService.create_job_from_thread` rejects caseless threads, `AgentActionService.create_action` no longer swallows case-creation failures.
- **Internal Messaging**: staff↔staff threads with notifications + case linking. Inline compose + reply from case detail view. Emoji picker + clipboard paste for images. Case-linked threads (`thread.case_id != null`) auto-expand `participant_ids` on reply — anyone on the case who engages becomes a participant so they get notifications and see the thread in their own inbox. Private DMs (no case_id) stay scoped to the original participants.
- **Real-Time Events**: Redis Pub/Sub + WebSocket gateway.
- **Equipment & Parts**: catalog (114) + items per property + parts (434) + vendor tracking.
- **Granular Permissions**: 60-slug system with presets, custom roles, per-user overrides.
- **À La Carte Subscriptions**: feature gating with tiers, trial support, Stripe customer IDs.
- **Feedback System**: in-app feedback with screenshots + resolution tracking.

## Documentation Index (SOURCE OF TRUTH)

This is the canonical index of all project documentation. **Whenever you create a new doc, add it here in the same commit.** Whenever `/cpu` runs, it must verify this index matches the actual contents of `/docs` and flag any drift.

### Strategy & Vision
| Doc | Purpose |
|-----|---------|
| `docs/email-strategy.md` | Email-aware customer system (not email server); multi-mode integration + decision log |
| `docs/competitive-research.md` | Market audit + differentiators |

### Build Plans (forward-looking, with checkboxes)
| Doc | Purpose |
|-----|---------|
| `docs/build-plan.md` | Master phase roadmap with completion status. Phases 0-10, all sub-phases. |
| `docs/email-integrations-plan.md` | Detailed Phase 5b plan: 9 sub-phases for multi-mode email support |
| `docs/profitability-feature-plan.md` | Phase 3b spec (scoring weights, jurisdiction formulas) |
| `docs/ai-agents-plan.md` | 10 planned AI agents (product roadmap), current implementation status |
| `docs/inbox-folders-plan.md` | 3-phase inbox folders: folders + filter rules + Gmail label sync. **Remove when complete.** |
| `docs/entity-connections-plan.md` | 5-phase plan to unify entity linking via ServiceCase hub, line-item case attribution, physical-work connections, equipment axis, discovery. Phase 1 shipped 2026-04-14. **Remove when complete.** |
| `docs/ai-platform-plan.md` | 8-phase plan to rebuild QP around a unified AI platform: event instrumentation, agent_proposals, inbox summarizer, post-creation handlers, workflow_observer, and Sonar (dev-facing intelligence). Every phase has a "Why" block. **Remove when complete.** |
| `docs/event-taxonomy.md` | Canonical catalog of event types for `platform_events`. Every new event added to code requires updating this doc in the same PR. Phase 0 of ai-platform-plan. **Lives as long as platform_events does** (not a "remove when complete" doc — permanent reference). |
| `docs/ai-platform-phase-1.md` | Phase 1 implementation spec — event instrumentation foundation. DDL, service interface, middleware, frontend client, backfill, purge, completeness audit, 13-step rollout, 11-item DoD. **Remove when Phase 1 shipped.** |
| `docs/ai-platform-phase-3.md` | Phase 3 implementation spec — inbox summarizer + V2 inbox redesign. Payload schema, debounce + stale triggers, prompt rules, frontend row/hover/mobile-popover design, linked_ref UUID resolver, flag-flip backfill, 11-item DoD. Shipped on Sapphire 2026-04-19; keep while Sapphire is the sole dogfood org. **Remove when Phase 3 GA'd to all orgs.** |

### Architecture Reference (current state, factual)
| Doc | Purpose |
|-----|---------|
| `docs/data-model.md` | All models by domain, relationships, deprecated fields |
| `docs/email-pipeline.md` | Managed-mode email architecture (Cloudflare Workers + Postmark) |
| `docs/realtime-events.md` | WebSocket + Redis Pub/Sub event types + frontend hooks |
| `docs/deepblue-architecture.md` | DeepBlue engine, tools, eval, quota |

### Operational / One-Off Plans
| Doc | Purpose |
|-----|---------|
| `docs/sapphire-recovery-plan.md` | Plan to revert Sapphire from managed mode back to Google Workspace (Sapphire is a customer, not QP infra) |
| `docs/sapphire-gmail-migration.md` | Step-by-step DNS/MX migration to make Gmail the canonical store for all `*@sapphire-pools.com` mail. **Remove when complete.** |
| `docs/billing-dormant.md` | Inventory of the billing/Stripe code that's built but intentionally disabled. **Do NOT re-enable scheduler without explicit approval.** Includes Stripe Connect concern for multi-tenant. **Remove when billing is live + stable.** |
| `docs/audit-2026-04-07.md` | Code health audit findings |
| `docs/inbox-security-audit-2026-04-13.md` | **HIGH PRIORITY** — security audit found 3 CRITICAL + 4 HIGH + 4 MEDIUM issues in inbox/email subsystem (cross-org leakage, unsigned webhooks, unauth attachment access). Each item has file:line + status. **Remove when every CRITICAL/HIGH is closed.** |
| `docs/backup-and-restore.md` | DB backup + restore-verification runbook. Cron schedule, retention (GFS 7d/4w/12m), restore commands with safety snapshots, ntfy signaling, follow-up gaps (off-host, off-site, WAL archiving). |

> Maintenance rules for this index are defined above under **Documentation Alignment**.
