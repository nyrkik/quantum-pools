# SaaS Foundation Build - Master To-Do List

**Created:** 2025-10-26
**Status:** Phase 0 - Documentation
**Critical:** This foundation MUST be complete before building additional features

---

## CONTEXT FOR RESUMPTION

**Background:**
- Started as personal route optimization tool for Brian's pool service
- Pivoted to SaaS product during development
- Discovered critical design flaws: no multi-tenancy, billing in wrong tables, no auth, no map provider abstraction
- Decision: Fix foundation NOW before building more features on bad architecture

**Key Decisions Made:**
1. Build SaaS-first architecture with multi-tenancy from day one
2. Add organization_id to ALL tables for data isolation
3. Implement auth/RBAC before Phase 4 (water features)
4. Abstract map provider layer (OpenStreetMap → Google Maps transition)
5. Normalize billing (separate service_plans, payment_methods tables)
6. API versioning (/api/v1/) from start
7. AI features planned for competitive differentiation (EMD scraping, chemical intelligence, predictive maintenance)

**What Was Already Built (Pre-Foundation):**
- Customer management (CRUD, geocoding, CSV import)
- Driver management
- Route optimization (Google OR-Tools VRP)
- Basic route visualization (Leaflet.js)
- PDF export
- Routes/route_stops saved to database

**What Needs Fixing:**
- Billing fields incorrectly added to customers table (need rollback)
- No multi-tenancy (no organizations, users, org_users)
- No authentication
- Direct geocoding calls (need provider abstraction)
- Water features schema designed but not implemented (needs organization_id from start)
- API has no versioning

---

## PHASE 0: DOCUMENTATION ⏳

**Status:** In Progress
**Goal:** Create comprehensive documentation before touching code

### Create 4 New Documents

- [ ] **1. DESIGN_REVIEW.md** - All current design flaws + enterprise fixes
  - Document: billing in customers, no multi-tenancy, no auth, no map abstraction
  - Rate severity (Critical/High/Medium/Low)
  - Business impact + technical debt
  - Enterprise solutions
  - Implementation priority
  - Migration strategy

- [ ] **2. SAAS_ARCHITECTURE.md** - Complete multi-tenant design
  - Multi-tenancy (organizations, users, org_users)
  - Data isolation (organization_id pattern)
  - Auth & authorization flow
  - JWT structure (user_id, org_id, role)
  - Subdomain routing (brians.poolscoutpro.com)
  - Organization context middleware
  - RBAC (owner, admin, manager, tech, readonly)
  - Subscription tiers
  - Feature flags per org
  - Usage tracking

- [ ] **3. MAP_PROVIDER_STRATEGY.md** - Geocoding abstraction + migration
  - GeocodingProvider interface
  - OpenStreetMap implementation
  - Google Maps implementation
  - Per-org provider selection
  - Geocoding cache
  - Migration: OSM → Google Maps
  - DB fields (geocoding_provider, geocoded_by, geocoded_at)
  - API key management per org
  - Cost comparison

- [ ] **4. MIGRATION_PLAN.md** - Step-by-step DB migration guide
  - Migration sequence
  - Rollback strategy per migration
  - Data preservation (existing customers/drivers/routes)
  - Testing plan
  - Downtime estimates
  - Code changes required
  - Risk assessment

### Update 6 Existing Documents

- [ ] **5. ARCHITECTURE.md**
  - Add "Multi-Tenancy Architecture" section
  - Document organization_id pattern
  - Auth middleware flow diagram
  - Map provider abstraction layer
  - Update API endpoints to /api/v1/
  - Subdomain routing strategy
  - New tables in schema section
  - Security headers & CORS
  - Error handling standards
  - Caching strategy

- [ ] **6. DATABASE_SCHEMA.md**
  - Add: organizations, users, organization_users
  - Add: organization_subscriptions, usage_tracking
  - Add organization_id to ALL tables
  - Remove billing fields from customers
  - Add: service_plans, customer_service_agreements, payment_methods
  - Fix water features: visit_features junction
  - Fix water features: normalize JSONB
  - Add geocoding fields
  - Add indexes for organization_id
  - Document FK cascade rules

- [ ] **7. ROADMAP.md**
  - Insert Phase 0: SaaS Foundation (before Phase 2)
  - Update Phase 4 with organization_id from start
  - Add Phase X: AI Features
  - Renumber phases
  - Update dependencies

- [ ] **8. EXPANSION_PLAN.md**
  - Add "SaaS Business Model" section
  - Subscription tiers & pricing
  - Multi-tenancy isolation strategy
  - Add organization_id to all tables
  - AI Features section (12 opportunities)
  - Update Enhanced Customer Management
  - Update PSP Integration with multi-org
  - Add SaaS Metrics & Analytics

- [ ] **9. FEATURES.md**
  - Move auth from "limitations" to "foundation in progress"
  - Add "Multi-Tenancy" section
  - Add "Map Provider Abstraction" section
  - Update known limitations
  - Add "API Versioning"

- [ ] **10. PROJECT_STATUS.md**
  - Replace template with SaaS phase tracking
  - Track foundation progress
  - Define success criteria

---

## PHASE 1: DATABASE FOUNDATION ⏳

**Status:** Not Started
**Prerequisites:** Phase 0 complete, documentation reviewed together

### Rollback Bad Migration

- [ ] **11. Rollback billing fields migration**
  - Run: `alembic downgrade -1`
  - Verify customers table cleanup
  - Revert app/models/customer.py
  - Revert app/schemas/customer.py
  - Test app still runs

### Create Core SaaS Tables

- [ ] **12. organizations table**
  - Model: app/models/organization.py
  - Schema: app/schemas/organization.py
  - Fields: id, name, slug, subdomain, plan_tier, subscription_status, trial_ends_at, billing_email, stripe_customer_id, max_users, max_customers, max_techs, features_enabled (JSONB), default_map_provider, google_maps_api_key, created_at, updated_at
  - Migration: `alembic revision --autogenerate -m "Add organizations table"`
  - Apply: `alembic upgrade head`

- [ ] **13. users table**
  - Model: app/models/user.py
  - Schema: app/schemas/user.py
  - Fields: id, email (unique), password_hash, first_name, last_name, is_active, email_verified_at, last_login_at, created_at, updated_at
  - Migration + apply

- [ ] **14. organization_users junction**
  - Model: app/models/organization_user.py
  - Schema: app/schemas/organization_user.py
  - Fields: id, organization_id (FK), user_id (FK), role, is_primary_org, created_at
  - Unique: (organization_id, user_id)
  - Migration + apply

### Add organization_id to Existing Tables

- [ ] **15. customers.organization_id**
  - Update model + schema
  - Add index
  - Migration must create default org and assign all existing
  - Apply

- [ ] **16. drivers.organization_id**
- [ ] **17. routes.organization_id**
- [ ] **18. route_stops.organization_id**

### Create Normalized Billing Tables

- [ ] **19. service_plans**
  - Fields: id, organization_id (FK, NULL=global), name, description, base_rate, billing_frequency, is_active, created_at, updated_at

- [ ] **20. customer_service_agreements**
  - Fields: id, organization_id, customer_id, service_plan_id, custom_rate, effective_date, end_date (NULL=current), rate_notes, created_at

- [ ] **21. payment_methods**
  - Fields: id, organization_id, customer_id, payment_type, is_primary, is_active, stripe_payment_method_id, last_four, brand, created_at, updated_at

### Create SaaS Subscription Tables

- [ ] **22. organization_subscriptions**
  - Fields: id, organization_id, stripe_subscription_id, plan_tier, monthly_price, status, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at

- [ ] **23. usage_tracking**
  - Fields: id, organization_id, metric, quantity, recorded_at
  - Indexes: (organization_id, metric, recorded_at)

### Fix Water Features Schema

- [ ] **24-25. Add organization_id to water features tables**
  - water_features, equipment, equipment_maintenance_log, emd_inspections, chemical_logs, service_visits, visit_photos, visit_tasks

- [ ] **26. visit_features junction table**
  - Replaces feature_id on service_visits
  - Many-to-many: visits ↔ features

- [ ] **27. Normalize JSONB fields**
  - Extract queryable fields from JSONB
  - Keep JSONB for flexible data only

### Add Map Provider Fields

- [ ] **28. Geocoding fields on customers**
  - Add: geocoding_provider, geocoded_by, geocoded_at

- [ ] **29. Geocoding fields on drivers**

---

## PHASE 2: CODE STRUCTURE CHANGES ⏳

**Status:** Not Started
**Prerequisites:** Phase 1 complete

### Authentication & Multi-Tenancy

- [ ] **30. Auth dependencies**
  - Add: python-jose[cryptography], passlib[bcrypt], python-multipart
  - `pip install -r requirements.txt`

- [ ] **31. Authentication service**
  - app/services/auth.py
  - create_access_token(), verify_token(), hash_password(), verify_password()

- [ ] **32. Organization context middleware**
  - app/middleware/organization_context.py
  - Extract org from JWT/subdomain
  - Attach to request.state.organization

- [ ] **33. Database session scoping**
  - Update app/database.py
  - Auto-filter by organization_id

- [ ] **34. RBAC**
  - app/middleware/rbac.py
  - @require_role(), @require_permission()

### Map Provider Abstraction

- [ ] **35. GeocodingProvider interface**
  - app/services/geocoding/interface.py
  - Abstract: geocode(), reverse_geocode(), calculate_route()

- [ ] **36. OpenStreetMap provider**
  - app/services/geocoding/openstreetmap.py

- [ ] **37. Google Maps provider**
  - app/services/geocoding/google_maps.py

- [ ] **38. Geocoding factory**
  - app/services/geocoding/factory.py
  - get_geocoding_provider(organization)

- [ ] **39. Update existing geocoding service**
  - Refactor to use factory
  - Track provider metadata

### API Versioning

- [ ] **40. v1 API router**
  - app/api/v1/
  - Move existing routers

- [ ] **41. Update endpoints**
  - Prefix /v1/
  - Update frontend calls

### Error Handling

- [ ] **42. Standardized errors**
  - app/models/error.py
  - Global exception handler

- [ ] **43. Request ID tracking**
- [ ] **44. Structured logging**

### Configuration

- [ ] **45. Expand config**
  - Geocoding settings
  - Feature flags
  - JWT settings

### Security

- [ ] **46. Security headers**
- [ ] **47. CORS configuration**

---

## PHASE 3: BOOTSTRAP ⏳

- [ ] **48. Seed script**
  - Create "Demo" organization
  - Create admin user
  - Assign existing data

- [ ] **49. Test multi-tenancy**
  - Create second org
  - Verify isolation

---

## PHASE 4: FRONTEND UPDATES ⏳

- [ ] **50. Update API client**
  - Call /api/v1/
  - Add JWT to requests

- [ ] **51. Basic auth UI**
  - Login page
  - Token storage

---

## PHASE 5: VALIDATION ⏳

- [ ] **52. Update ARCHITECTURE.md with implementation**
- [ ] **53. Test all migrations**
- [ ] **54. Migration rollback guide**

---

## PHASE 6: ROUTING DEVELOPMENT ✅

**Status:** Ready after Phase 0-5 complete
**Goal:** Build routing features on solid foundation with no more schema changes

---

## CRITICAL SUCCESS CRITERIA

**Foundation is complete when:**
1. ✅ All documentation exists and is consistent
2. ✅ All database migrations applied successfully
3. ✅ organization_id on ALL tables
4. ✅ Auth middleware working
5. ✅ Map provider abstraction implemented
6. ✅ API versioned (/api/v1/)
7. ✅ Existing customers/drivers/routes work in default org
8. ✅ Can create second org with full data isolation
9. ✅ All tests pass
10. ✅ Schema locked - no changes during routing development

**Estimated Timeline:**
- Phase 0 (Docs): 1-2 days
- Phase 1 (Database): 1-2 days
- Phase 2 (Code): 2-3 days
- Phase 3-5 (Bootstrap/Test): 1 day
- **Total: ~1 week**

---

## NOTES FOR RESUMPTION AFTER COMPACTION

**If you're reading this after context compaction:**

1. Read this entire file first
2. Check current phase in PROJECT_STATUS.md
3. Review all docs/ files to understand decisions
4. DO NOT proceed to next phase without completing current phase
5. DO NOT make schema changes without checking MIGRATION_PLAN.md
6. DO NOT add features without confirming foundation is complete

**Key Files to Review:**
- This file (master to-do)
- DESIGN_REVIEW.md (why we're doing this)
- SAAS_ARCHITECTURE.md (what we're building)
- MAP_PROVIDER_STRATEGY.md (geocoding abstraction)
- MIGRATION_PLAN.md (how to execute)
- DATABASE_SCHEMA.md (target schema)
- ROADMAP.md (phase order)

**Rules:**
1. Foundation MUST be complete before routing development
2. Schema changes ONLY during Phase 1
3. No shortcuts - enterprise-grade from day one
4. Multi-tenancy is non-negotiable
5. Auth is foundation, not feature
6. Map provider must be abstracted
7. Billing must be normalized
8. Water features get organization_id from start

**Current User Context:**
- Brian - building for own pool service first
- Plans to sell as SaaS to other pool companies
- Needs working routing ASAP but wants solid foundation
- Has existing customers/drivers/routes that must be preserved
