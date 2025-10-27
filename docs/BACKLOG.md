# Feature Backlog

**Future features and enhancements for RouteOptimizer, organized by priority.**

## High Priority (Next 3-6 Months)

### Service Visit Tracking
**Why:** Core business value - track what was done at each visit
- Mark visits as complete, skipped, or issue
- Record chemicals added (pH, chlorine, alkalinity)
- Photo uploads of pool conditions
- Technician notes and recommendations
- Customer signature capture
- Historical visit records

### Customer Service Agreements
**Why:** Enable billing and revenue tracking
- Define service plans (weekly, bi-weekly, monthly)
- Track agreement start/end dates
- Link to visit records for billing
- Calculate monthly recurring revenue
- Generate invoices from service history

### Mobile App for Technicians
**Why:** Techs need route info in the field
- View assigned route for the day
- Navigate to next stop (Maps integration)
- Mark visits complete from phone
- Add chemicals and notes
- Take photos of pool conditions
- Offline mode for areas with poor signal

### Advanced Route Optimization
**Why:** Improve efficiency and customer satisfaction
- Break windows (preferred but not required time windows)
- Variable service durations based on pool size
- Traffic-aware routing (Google Maps API)
- Multi-day route planning
- Route templates for recurring customers

### Reporting & Analytics
**Why:** Business insights for decision-making
- Revenue by customer, tech, route
- Efficiency metrics (time per stop, miles per customer)
- Chemical usage trends
- Customer retention analysis
- Custom date range reports
- Export to PDF/Excel

## Medium Priority (6-12 Months)

### Billing & Payments (Stripe Integration)
- Automated invoice generation from service agreements
- Customer payment portal
- Credit card storage (PCI compliant via Stripe)
- Recurring billing automation
- Payment reminders and overdue notices
- Revenue dashboards

### Customer Portal
**Why:** Self-service reduces admin overhead
- View service history and upcoming visits
- See photos and notes from technicians
- Update contact information
- Request service changes or cancellations
- Make payments online
- Download invoices

### Inventory Management
**Why:** Track chemical costs and usage
- Chemical inventory tracking
- Automatic depletion from visits
- Reorder alerts when low
- Cost per visit calculations
- Purchase order generation
- Vendor management

### Equipment Maintenance Tracking
**Why:** Prevent equipment failures, proactive service
- Track pool equipment (pumps, filters, heaters)
- Maintenance schedules and reminders
- Repair history
- Warranty tracking
- Replacement recommendations

### Work Order System
**Why:** Handle one-time jobs beyond regular service
- Create work orders for repairs, installations
- Quote generation and approval workflow
- Parts and labor tracking
- Job costing and profitability
- Integration with regular service routes

## Low Priority (12+ Months)

### Multi-Location Support
- Companies with multiple service areas/branches
- Territory management
- Branch-level reporting
- Inter-branch transfers

### API for Third-Party Integrations
- RESTful API with rate limiting
- Webhook support for events
- Integration with QuickBooks, Xero
- Zapier integration
- Public API documentation

### AI-Powered Recommendations
- Predict chemical needs based on weather
- Recommend service frequency adjustments
- Identify at-risk customers (churn prediction)
- Optimize pricing based on market
- Auto-generate service notes from photos

### White-Label Options
- Custom branding (logo, colors)
- Custom domain names
- Remove "Powered by RouteOptimizer"
- Email templates with customer branding

### Advanced Scheduling
- Recurring work orders (monthly repairs)
- Seasonal schedule adjustments
- Vacation holds and resumptions
- Customer-requested date changes
- Automated schedule conflict resolution

### Fleet Management
- Vehicle maintenance tracking
- Fuel cost tracking
- GPS tracking of technician vehicles
- Mileage reports for tax purposes

## Feature Ideas (Unpriced/Unvalidated)

**These need customer validation before prioritizing:**

- SMS notifications to customers (visit complete, tech on way)
- Customer referral program with tracking
- Weather integration (skip visits on rain days)
- Pool chemical supplier marketplace
- Equipment vendor partnerships
- Franchise management tools
- Compliance tracking for health department
- Automated marketing campaigns
- Customer satisfaction surveys
- Social media integration for reviews
- IoT sensor integration (smart pool monitors)

## Won't Do (Out of Scope)

- Residential pool equipment sales (e-commerce)
- Pool construction project management
- Landscape/hardscape design tools
- HVAC or other non-pool services
- Become a marketplace (connecting customers to service providers)

## How to Add to Backlog

Use the `backlog: [idea]` command in Claude Code:

```bash
User: backlog: Add weather API to skip routes on heavy rain days
→ Claude adds to appropriate priority section with brief description
```

Or edit this file directly in priority order.

---

**See Also:**
- [PROJECT_STATUS.md](PROJECT_STATUS.md) - What's currently being built
- [ARCHITECTURE.md](ARCHITECTURE.md) - How features fit into system design
