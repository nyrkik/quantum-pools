# Development Roadmap

**Last Updated:** 2025-10-26

## Current State

✅ Core routing engine working
✅ Customer/driver management functional
✅ Basic UI operational
🔄 **In Progress:** SaaS Foundation (Phase 0) - Database migrations and architecture
⏳ **Next:** Multi-Module App Framework (Phase 1)

**Critical:** Phase 0 (SaaS Foundation) MUST be completed before Phase 1. We cannot build multi-tenant features on a single-tenant database.

---

## Phase 0: SaaS Foundation (CURRENT PHASE)

**Goal:** Transform single-user application into multi-tenant SaaS product

**Why First:** Without multi-tenancy, authentication, and proper billing infrastructure, we cannot scale to multiple customers. This is foundational work that affects every feature built afterward.

**Status:** 🔄 In Progress - Documentation complete, migrations pending

See [SAAS_FOUNDATION_TODO.md](SAAS_FOUNDATION_TODO.md) for complete implementation plan.

### High-Level Tasks

**0.1 Documentation (IN PROGRESS)**
- ✅ Design review and architecture decisions
- ✅ Complete database schema with SaaS tables
- ✅ Migration plan for all 17 database changes
- ✅ Map provider abstraction strategy
- 🔄 Update project roadmaps and status docs

**0.2 Database Migrations**
- M001: Rollback billing fields from customers table
- M002-M004: Create organizations, users, organization_users tables
- M005: Seed default organization for existing data
- M006-M009: Add organization_id to existing tables (customers, drivers, routes, etc.)
- M010-M012: Create normalized billing tables (service_plans, customer_service_agreements, payment_methods)
- M013-M014: Create subscription and usage tracking tables
- M015-M017: Add geocoding metadata and cache tables

**0.3 Authentication System**
- JWT token generation and validation
- bcrypt password hashing
- User registration endpoint
- Login/logout endpoints
- Password reset flow (planned)

**0.4 Authorization System**
- Organization context middleware (extract org_id from JWT)
- Role-based access control (RBAC) middleware
- Permission decorators for endpoints
- Automatic organization scoping for all queries

**0.5 Map Provider Abstraction**
- GeocodingProvider interface (ABC)
- OpenStreetMapProvider implementation
- GoogleMapsProvider implementation
- Factory pattern for provider selection
- Per-organization provider configuration

**0.6 API Versioning**
- Migrate all endpoints from /api/* to /api/v1/*
- Update frontend to use versioned endpoints
- API version configuration

**0.7 Security Hardening**
- CORS configuration
- Security headers middleware
- Rate limiting (planned)
- Input validation with Pydantic
- SQL injection prevention (parameterized queries)

**0.8 Frontend Updates**
- Login/registration pages
- JWT token storage and refresh
- Organization context in all API calls
- User profile management
- Basic organization settings page

**Dependencies:** None (foundational work)

**Estimated Impact:** 3-4 weeks
- Week 1: Database migrations and data migration
- Week 2: Authentication and authorization
- Week 3: Map provider abstraction and API versioning
- Week 4: Frontend updates and testing

**Deliverable:** Multi-tenant SaaS application with authentication, authorization, and proper data isolation

**Success Criteria:**
- Multiple organizations can use the system simultaneously
- Complete data isolation between organizations
- Secure authentication with JWT
- Role-based permissions working
- All API endpoints use /api/v1/ prefix
- Map provider abstraction allows switching between OpenStreetMap and Google Maps

**See Also:**
- [SAAS_FOUNDATION_TODO.md](SAAS_FOUNDATION_TODO.md) - Complete task list with 60+ subtasks
- [DESIGN_REVIEW.md](DESIGN_REVIEW.md) - Analysis of current design flaws
- [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) - Complete multi-tenancy specification
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - Updated schema with SaaS tables
- [MIGRATION_PLAN.md](MIGRATION_PLAN.md) - Step-by-step migration guide

---

## Phase 1: Multi-Module App Framework

**Goal:** Build foundation for expanding beyond routing

**Why First:** Prevents rework. Routing module will nest properly in app shell.

### Tasks

1. **Design App Shell Structure**
   - HTML/CSS structure for app container
   - Icon sidebar layout (50-60px width)
   - Main content area (dynamic module loading)
   - Mobile collapse behavior
   - Decide: Single-page app routing or multi-page

2. **Implement Icon Sidebar Navigation**
   - Create sidebar component
   - Icons: Dashboard, Team, Clients, Routes, Jobs, Invoicing, Settings
   - Hover tooltips
   - Active state styling
   - Mobile hamburger menu
   - Collapsible behavior

3. **Module Routing System**
   - Show/hide content areas based on nav selection
   - URL hash routing or history API
   - Default to Routes module initially
   - Preserve state when switching modules
   - Loading states

4. **Create Dashboard Placeholder**
   - Basic landing page
   - Placeholder widgets
   - Will populate with metrics later
   - Should be visible on initial load

5. **Mobile Responsive Testing**
   - Test sidebar collapse
   - Touch-friendly nav
   - Content area adapts
   - Test on actual devices

**Dependencies:** None
**Estimated Impact:** 2-3 days work
**Deliverable:** Working app shell, routing module loads in content area

---

## Phase 2: Routing Module Redesign

**Goal:** Optimize routing UI for screen space and scalability

**Why Now:** Once app shell exists, redesign routing to fit properly

### Tasks

1. **Audit Current Routing Code**
   - Map existing UI components
   - Identify what to keep vs rebuild
   - Plan component structure

2. **Implement Horizontal Tech Selector**
   - Replace vertical sidebar
   - Tech chips/pills (horizontal scrollable)
   - Color-coded by driver.color
   - Click to toggle selection
   - "Show All" / "Clear All" buttons
   - Threshold logic (6-8 chips, then dropdown)
   - Touch-friendly (44x44px targets)

3. **Redesign Controls Bar**
   - Optimization mode (radio buttons: Full/Refine)
   - Day reassignment toggle
   - Other settings (horizontal layout)
   - Compact, professional appearance
   - Mobile-responsive stacking

4. **Maximize Map Layout**
   - Remove old sidebar space
   - Map takes full content width
   - Day tabs at top (already exists, may need styling update)
   - Tech selector below day tabs
   - Controls bar below tech selector
   - Map fills remaining space

5. **Update Map Interactions**
   - Ensure markers/routes still work
   - Color coding maintained
   - Click interactions preserved
   - Responsive to container size changes

6. **Scalability Testing**
   - Test with 1 technician
   - Test with 20 technicians
   - Test with 100+ customers
   - Test dropdown overflow behavior
   - Performance validation

**Dependencies:** Phase 1 complete
**Estimated Impact:** 3-4 days work
**Deliverable:** Professional, scalable routing UI in app framework

---

## Phase 3: Routing Module Polish

**Goal:** Refine routing features and fix edge cases

### Tasks

1. **Optimization Enhancements**
   - Implement true cross-day optimization with reassignment
   - Improve time estimates
   - Better constraint handling
   - Progress indicators for long optimizations

2. **PDF Export Improvements**
   - Better formatting
   - Add company branding capability
   - Include map thumbnail
   - Batch export options

3. **Coordinate Validation Enhancement**
   - Bulk re-geocoding tool
   - Better error messages
   - Auto-fix suggestions
   - Validation scheduling (run nightly)

4. **Performance Optimization**
   - Frontend bundle optimization
   - API response caching
   - Database query optimization
   - Large dataset testing (1000+ customers)

5. **Mobile Experience**
   - Test all routing features on mobile
   - Optimize map interactions for touch
   - Ensure forms/modals work on small screens

**Dependencies:** Phase 2 complete
**Estimated Impact:** 2-3 days work
**Deliverable:** Production-ready routing module

---

## Phase 4: Water Features & Pool Management

**Goal:** Foundation for tracking pools, equipment, maintenance, inspections, and service visits

See DATABASE_SCHEMA.md for complete schema documentation.

### High-Level Tasks

1. Database schema (8 tables: water_features, equipment, equipment_maintenance_log, emd_inspections, chemical_logs, service_visits, visit_photos, visit_tasks)
2. SQLAlchemy models for all tables
3. Alembic migrations (sequential)
4. API endpoints (/api/water-features, /api/equipment, /api/inspections, /api/chemical-logs, /api/service-visits)
5. Pydantic schemas for validation
6. Digital Ocean Spaces configuration for photo storage
7. Basic UI for water features management (view/edit)

**Dependencies:** Phase 3 complete, app framework solid
**Estimated Impact:** 2-3 weeks
**Deliverable:** Complete pool/equipment/maintenance tracking foundation

---

## Phase 5: Lead Generation & Scouting Module (CORE DIFFERENTIATOR)

**Goal:** Automated lead generation through EMD inspection report scraping - the competitive advantage that sets this platform apart

**Why This Matters:** This is THE unique selling proposition. While competitors offer pool service management, we identify NEW business opportunities automatically by scraping public EMD (Environmental Management Department) inspection reports to find pools that aren't being serviced by our customers. This transforms the platform from a passive management tool into an active revenue generator.

See DATABASE_SCHEMA.md for complete scouting schema documentation.

### High-Level Tasks

**5.1 Database Schema (4 tables)**
1. `scraped_reports` - Raw EMD inspection data (facility info, inspection results, violations, metadata)
2. `leads` - Identified unserviced pools with scoring and status tracking
3. `research_data` - Management company information, contact details, enrichment data
4. `scraping_jobs` - Job queue and status tracking for scraping operations

**5.2 EMD Report Scraper**
1. Configurable scraper for California EMD websites (county-specific parsers)
2. Extract facility data: address, pool type, size, violations, last inspection date
3. Geocoding integration (reuse existing provider abstraction)
4. Deduplication logic (match against existing customer addresses)
5. Scheduled scraping jobs (weekly/monthly per organization preferences)
6. Error handling and retry logic
7. Rate limiting and respectful scraping practices

**5.3 Lead Identification Engine**
1. Cross-reference scraped facilities against customer database
2. Identify facilities NOT in customer list (unserviced pools)
3. Lead scoring algorithm:
   - Pool type and size (commercial higher value)
   - Violation severity (urgent repairs = hot leads)
   - Last inspection date (compliance urgency)
   - Geographic proximity to existing routes
   - Estimated revenue potential
4. Filter by organization's service area
5. Mark duplicate leads across time periods

**5.4 Management Company Research**
1. Extract management company names from inspection reports
2. Web scraping for contact information (website, email, phone)
3. Integration with business directory APIs (optional paid service)
4. Store enrichment data (company size, properties managed, contact history)
5. Link multiple facilities to same management company

**5.5 CRM Integration & Sales Workflow**
1. Lead dashboard UI (sortable by score, location, company)
2. Lead assignment to sales team members (role: Owner/Admin)
3. Lead status tracking (new, contacted, qualified, won, lost)
4. Contact history and notes
5. Email templates for outreach
6. Conversion tracking (lead → customer)
7. ROI metrics (leads generated, conversion rate, revenue attributed)

**5.6 API Endpoints**
- `/api/v1/scouting/scrape` - Trigger scraping job (manual or scheduled)
- `/api/v1/scouting/reports` - View scraped inspection reports
- `/api/v1/scouting/leads` - List/filter leads with scoring
- `/api/v1/scouting/leads/{id}` - Lead details and research data
- `/api/v1/scouting/leads/{id}/convert` - Convert lead to customer
- `/api/v1/scouting/companies` - Management company directory
- `/api/v1/scouting/jobs` - Scraping job status and history

**5.7 Subscription Tier Integration**
- Starter tier: 50 leads/month
- Professional tier: 200 leads/month
- Enterprise tier: Unlimited leads
- Usage tracking and quota enforcement
- Upgrade prompts when approaching limits

**Dependencies:** Phase 4 complete (water features tables), Phase 0 geocoding abstraction
**Estimated Impact:** 3-4 weeks
**Deliverable:** Automated lead generation engine that identifies new business opportunities from public data

**Success Criteria:**
- Successfully scrape EMD reports from at least 3 California counties
- Identify unserviced pools and score them accurately
- Generate 50+ qualified leads per month for pilot organizations
- Match leads to management companies with contact information
- Provide clear ROI metrics (leads → conversions → revenue)
- Lead-to-customer conversion workflow fully functional
- Zero data privacy violations (public data only)

**Competitive Advantage:**
- No other pool service software actively generates leads from EMD data
- Transforms platform from cost center (management tool) to profit center (revenue generator)
- Creates network effects (more customers = more served addresses = better lead identification)
- High switching cost once sales pipeline depends on lead flow

---

## Phase 6: Jobs Module

**Goal:** Track actual work performed

See EXPANSION_PLAN.md for details.

### High-Level Tasks

1. Database schema (jobs, job_notes tables - photo storage uses visit_photos from Phase 4)
2. API endpoints (/api/jobs)
3. UI for job management
4. Mobile-friendly job completion interface
5. Integration with routes (auto-create jobs from route stops)
6. Integration with service_visits (Phase 4)

**Dependencies:** Phase 5 complete (lead conversion may create jobs)
**Estimated Impact:** 1-2 weeks
**Deliverable:** Working job tracking system

---

## Phase 7: Invoicing Module

**Goal:** Financial management and billing

See EXPANSION_PLAN.md for details.

### High-Level Tasks

1. Database schema (invoices, payments, line_items)
2. API endpoints (/api/invoices, /api/payments)
3. Invoice generation UI
4. Payment tracking UI
5. Integration with jobs module
6. Email delivery

**Dependencies:** Phase 6 complete
**Estimated Impact:** 2-3 weeks
**Deliverable:** Working invoicing system

---

## Phase 8: Estimates Module

**Goal:** Sales process for new work

See EXPANSION_PLAN.md for details.

### High-Level Tasks

1. Database schema (estimates, estimate_line_items)
2. API endpoints (/api/estimates)
3. Estimate creation UI
4. Template library
5. Approval workflow
6. Conversion to jobs
7. Integration with lead conversion (Phase 5) - convert leads to estimates

**Dependencies:** Phase 7 complete
**Estimated Impact:** 1-2 weeks
**Deliverable:** Working estimates system

---

## Future Considerations

### Customer Portal (Phase 9+)
- Customer login
- View service history
- Pay invoices online
- Request service
- View scouting-generated estimates (from Phase 5 leads)

### Mobile App for Techs
- Native or PWA
- Job completion interface
- Route navigation
- Photo upload
- Time tracking

### Advanced Features
- Real-time driver tracking
- SMS notifications
- Email automation
- Advanced reporting
- Inventory management
- AI-powered features (7 features detailed in EXPANSION_PLAN.md)

---

## Decision Points

### Immediate Decisions Needed

**Q:** Single-page app (SPA) or multi-page?
**Recommendation:** Start with hash-based SPA routing (simpler, no build step). Can refactor to React/Vue later if needed.

**Q:** Keep vanilla JS or adopt framework?
**Recommendation:** Vanilla JS for Phase 1-3. Consider framework for Phase 4+ when complexity increases.

**Q:** Separate frontend/backend or keep monolithic?
**Recommendation:** Keep monolithic (FastAPI serves static files) for now. Simpler deployment.

### Future Decisions

- Payment gateway choice (Stripe vs Square)
- Email service provider
- File storage solution (local vs S3)
- Framework migration timing

---

## Success Criteria

**Phase 0 Complete (SaaS Foundation):**
- ✅ Multi-tenant architecture with complete data isolation
- ✅ Authentication and authorization working (JWT, RBAC)
- ✅ All API endpoints use /api/v1/ prefix
- ✅ Map provider abstraction allows provider switching
- ✅ Normalized billing schema ready for subscription management
- ✅ Multiple organizations can use system simultaneously
- 🎯 **Ready for:** first paying customers

**Phases 1-2 Complete (UI Framework):**
- Professional multi-module interface
- Routing optimized for screen space
- Scales to 20+ techs, 500+ customers per organization
- Mobile responsive
- 🎯 **Ready for:** beta testing with multiple organizations

**Phase 3 Complete (Routing Polish):**
- Production-ready routing
- No critical bugs
- Performance validated
- 🎯 **Ready for:** marketing and customer acquisition

**Phases 4-5 Complete (Pool Management & Lead Generation):**
- Complete water features, equipment, and maintenance tracking
- Automated lead generation from EMD inspection reports
- Lead scoring and management company research
- Active revenue generation (not just management)
- 🎯 **Ready for:** beta customers who want scouting features

**Phases 6-8 Complete (Jobs, Invoicing, Estimates):**
- Replaces 3+ separate tools
- End-to-end workflow: leads → estimates → jobs → invoices
- Reduces admin time by 50%
- Feature-complete for pool service companies
- Supports 10+ techs, 1000+ customers per organization
- 🎯 **Ready for:** full commercial launch
