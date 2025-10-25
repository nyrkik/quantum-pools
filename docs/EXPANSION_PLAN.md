# Expansion Plan: Comprehensive Pool Service Platform

**Last Updated:** 2025-10-25

## Vision

Transform from route optimization tool into complete pool service business management platform covering:
- Route optimization (current)
- Invoicing & billing
- Job tracking & work orders
- Customer management (enhanced)
- Team management (enhanced)
- Estimates & proposals
- Inventory tracking (potential)
- Customer portal (potential)

**Philosophy:** Build with enterprise scalability from day one. Every module production-ready, no shortcuts.

## Current State

**Implemented:**
- Route optimization engine
- Customer management
- Driver/team management
- Basic scheduling

**Immediate Focus:**
- Routing module (refine UI)
- Build foundation for multi-module app

## Future Modules

### 1. Jobs & Work Orders

**Purpose:** Track actual work performed beyond just routes

**Core Features:**
- Job creation from route stops
- Job status (scheduled, in-progress, completed, on-hold)
- Service notes and photos
- Chemical readings/adjustments
- Equipment maintenance logs
- Problem tracking (green pool, equipment failure, etc.)
- Job completion sign-off

**Database Changes:**
- `jobs` table (links to customer, route_stop, assigned_tech)
- `job_notes` table
- `job_photos` table
- Job status tracking

**Integration:**
- Jobs auto-created from saved routes
- Update from mobile (tech in field)
- Feeds into invoicing

### 2. Invoicing & Billing

**Purpose:** Financial management and customer billing

**Core Features:**
- Invoice generation from completed jobs
- Recurring invoices (weekly/monthly service plans)
- One-time invoices (repairs, equipment)
- Payment tracking (paid, partial, overdue)
- Payment methods (check, credit card, ACH)
- Late fees and payment terms
- Invoice templates and customization
- Email delivery
- Payment reminders

**Database Changes:**
- `invoices` table
- `invoice_line_items` table
- `payments` table
- `billing_cycles` table
- Customer billing preferences

**Integration:**
- Pull from completed jobs
- Link to customer records
- Generate from service plans
- Track customer balances

### 3. Estimates & Proposals

**Purpose:** Sales process for new work

**Core Features:**
- Create service estimates
- Equipment installation quotes
- Repair estimates
- Template library (common services)
- Photo attachments
- Expiration dates
- Approval tracking
- Convert estimate → job → invoice

**Database Changes:**
- `estimates` table
- `estimate_line_items` table
- `estimate_templates` table
- Status tracking (draft, sent, approved, rejected)

**Integration:**
- Links to customer
- Converts to job when approved
- Feeds pricing into invoice

### 4. Enhanced Customer Management

**Additions to Current:**
- Customer portal login
- Service history
- Billing history & statements
- Pool specifications (size, type, equipment)
- Chemical preferences
- Equipment inventory (pumps, filters, heaters)
- Service plan details
- Communication log
- Files & photos

**Database Changes:**
- `customer_pools` table (multiple pools per customer)
- `customer_equipment` table
- `customer_service_plans` table
- `customer_communications` table
- `customer_portal_access` table

### 5. Enhanced Team Management

**Additions to Current:**
- Time tracking (clock in/out)
- Performance metrics
- Certifications & licenses
- Equipment assigned to tech
- Commission tracking
- Pay rate management
- Scheduling preferences
- Mobile app access

**Database Changes:**
- `time_entries` table
- `tech_certifications` table
- `tech_equipment` table
- Commission rules

### 6. Pool Scout Pro (PSP) Integration

**Purpose:** Integrate existing Sacramento County pool inspection scraping system

**Core Features:**
- Scrape Sacramento County online pool inspections
- Store violation data in database
- Track inspection history per pool
- Alert on new violations
- Link violations to customer records
- Compliance tracking and reporting

**Database Changes:**
- `inspections` table (date, inspector, findings)
- `violations` table (type, severity, status)
- Link to `customer_pools` table

**Integration:**
- New module in sidebar navigation
- Scheduled scraping (daily/weekly)
- Violation notifications
- Customer-facing violation history

### 7. Inventory Management (Optional)

**Purpose:** Track chemicals and equipment

**Core Features:**
- Stock levels
- Reorder alerts
- Usage tracking
- Cost tracking
- Supplier management
- Purchase orders

**Database Changes:**
- `inventory_items` table
- `inventory_transactions` table
- `suppliers` table
- `purchase_orders` table

## Database Architecture Strategy

### Approach: Unified Database with Module Separation

All modules share core entities (customers, drivers) but maintain clear boundaries:

**Core Entities (Existing):**
- customers
- drivers
- routes
- route_stops

**Jobs Module:**
- jobs (FK to customer_id, driver_id, route_stop_id)
- job_notes
- job_photos
- job_status_history

**Invoicing Module:**
- invoices (FK to customer_id)
- invoice_line_items (FK to invoice_id, optional job_id)
- payments (FK to invoice_id)

**Estimates Module:**
- estimates (FK to customer_id)
- estimate_line_items

**Relationships:**
- Route stop → Job (one-to-one or one-to-many)
- Job → Invoice line item (many-to-one)
- Customer → Everything (one-to-many)

## API Structure Strategy

Organize by module:
- `/api/customers` (existing)
- `/api/drivers` (existing)
- `/api/routes` (existing)
- `/api/jobs` (future)
- `/api/invoices` (future)
- `/api/payments` (future)
- `/api/estimates` (future)

Each module is self-contained service layer.

## UI/UX Integration

**Navigation:**
- Icon sidebar with: Dashboard, Team, Clients, Routes, Jobs, Invoicing, Estimates, Settings
- Each module is its own view/page
- Consistent design patterns across modules
- Shared components (tables, forms, modals)

**Dashboard:**
- Today's routes summary
- Outstanding invoices
- Overdue payments
- Pending estimates
- Team status
- Key metrics (revenue, customers, jobs completed)

## Implementation Priority

**Phase 1: Foundation (Current)**
- Routing module refinement
- UI framework for multi-module app

**Phase 2: Jobs**
- Job tracking system
- Mobile tech interface
- Job completion workflow

**Phase 3: Invoicing**
- Invoice generation
- Payment tracking
- Recurring billing

**Phase 4: Estimates**
- Estimate creation
- Approval workflow
- Conversion to jobs

**Phase 5: Enhanced Features**
- Customer portal
- Advanced reporting
- Inventory management

## Technical Considerations

- **Authentication:** Will need user auth system (techs, admins, customers)
- **Mobile:** Native app or PWA for techs in field
- **Real-time:** WebSocket for live updates (job status, driver location)
- **File storage:** S3 or similar for photos/documents
- **Email:** Transactional email service (invoices, estimates, reminders)
- **Payments:** Stripe/Square integration for credit card processing
- **Reporting:** Analytics and financial reporting

## Success Metrics

- Single platform replaces 3-5 separate tools
- Reduces admin time by 50%
- Improves cash flow (faster invoicing)
- Better customer experience
- Scalable to 100+ customers, 10+ techs
- Marketable as SaaS product
