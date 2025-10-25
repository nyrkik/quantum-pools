# Development Roadmap

**Last Updated:** 2025-10-25

## Current State

✅ Core routing engine working
✅ Customer/driver management functional
✅ Basic UI operational
🔄 UI needs redesign for multi-module expansion

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

## Phase 4: Jobs Module

**Goal:** Track actual work performed

See EXPANSION_PLAN.md for details.

### High-Level Tasks

1. Database schema (jobs, job_notes, job_photos tables)
2. API endpoints (/api/jobs)
3. UI for job management
4. Mobile-friendly job completion interface
5. Integration with routes (auto-create jobs from route stops)

**Dependencies:** Phase 3 complete, app framework solid
**Estimated Impact:** 1-2 weeks
**Deliverable:** Working job tracking system

---

## Phase 5: Invoicing Module

**Goal:** Financial management and billing

See EXPANSION_PLAN.md for details.

### High-Level Tasks

1. Database schema (invoices, payments, line_items)
2. API endpoints (/api/invoices, /api/payments)
3. Invoice generation UI
4. Payment tracking UI
5. Integration with jobs module
6. Email delivery

**Dependencies:** Phase 4 complete
**Estimated Impact:** 2-3 weeks
**Deliverable:** Working invoicing system

---

## Phase 6: Estimates Module

**Goal:** Sales process for new work

See EXPANSION_PLAN.md for details.

### High-Level Tasks

1. Database schema (estimates, estimate_line_items)
2. API endpoints (/api/estimates)
3. Estimate creation UI
4. Template library
5. Approval workflow
6. Conversion to jobs

**Dependencies:** Phase 5 complete
**Estimated Impact:** 1-2 weeks
**Deliverable:** Working estimates system

---

## Future Considerations

### Authentication & User Management
- User login system
- Role-based access (admin, tech, customer)
- Session management
- Password reset flow

### Customer Portal
- Customer login
- View service history
- Pay invoices online
- Request service

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

**Phase 1-2 Complete:**
- Professional multi-module interface
- Routing optimized for screen space
- Scales to 20+ techs, 500+ customers
- Mobile responsive

**Phase 3 Complete:**
- Production-ready routing
- No critical bugs
- Performance validated
- Ready for real-world use

**Phases 4-6 Complete:**
- Replaces 3+ separate tools
- Reduces admin time by 50%
- Marketable as product
- Supports 10+ techs, 1000+ customers
