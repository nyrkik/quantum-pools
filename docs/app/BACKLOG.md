# Feature Backlog

**Future enhancements and planned features for Quantum Pool Solutions.**

## High Priority

### Service Visit Tracking
**Status:** Planned
**Description:** Track actual service visits - when techs complete stops, record chemicals used, notes, photos, etc.

**Requirements:**
- `service_visits` table: visit_date, tech_id, customer_id, status (completed/skipped/issue), duration, notes
- `visit_chemicals` table: visit_id, chemical_type, amount_added, before_reading, after_reading
- `visit_photos` table: visit_id, photo_url, photo_type (before/after/issue)
- Mobile-friendly UI for techs to mark stops complete
- Chemical dosing calculations and recommendations
- Photo upload to cloud storage (DO Spaces)
- Visit history view for each customer
- Reporting: visits completed per tech, skipped stops, chemical usage trends

**Dependencies:**
- Cloud storage setup (DO Spaces)
- Mobile UI optimization
- Camera access in web app

---

## Medium Priority

### Persistent Route Management
**Status:** In Design
**Description:** Separate daily routing from strategic optimization

**Current Issue:**
- Routes regenerate every optimization
- No persistent route state per day
- Temporary assignments don't affect routing

**Proposed Solution:**
- `tech_routes` table: tech_id, service_day, route_date, stop_sequence (JSON), created_at
- Auto-generate routes on day load if they don't exist
- Auto-regenerate when stops change
- Keep routes for 6 days (clean up before same weekday next week)
- Separate "Route" (daily TSP) from "Optimize" (strategic reassignment)

**Implementation Steps:**
1. Create tech_routes table and model
2. Add route generation service (TSP per tech)
3. Add staleness detection (stops changed after route created_at)
4. Auto-route on day load
5. Route cleanup on temp assignment changes
6. Keep optimize as separate strategic operation

---

### Stripe Payment Integration
**Status:** Planned
**Description:** Accept payments from customers via Stripe

**Requirements:**
- Customer payment method storage (card/ACH)
- One-time payment processing
- Recurring billing setup
- Payment history
- Failed payment handling
- Customer portal for payment method updates

---

### Advanced Reporting
**Status:** Planned
**Description:** Business intelligence and analytics

**Features:**
- Revenue by day/week/month
- Customer acquisition trends
- Route efficiency metrics (miles per stop, time per stop)
- Tech productivity (stops completed, hours worked)
- Chemical usage and costs
- Customer retention/churn
- Export to PDF/Excel

---

## Low Priority

### Email Notifications
**Status:** Planned
**Description:** Automated emails for various events

**Types:**
- Service reminder (day before visit)
- Invoice sent
- Payment receipt
- Failed payment
- New customer welcome
- Tech assignment changes

**Provider:** SendGrid

---

### Mobile App
**Status:** Future
**Description:** Native mobile app for technicians

**Features:**
- View assigned stops for the day
- Navigate to next stop
- Mark stops complete
- Add chemical readings
- Take photos
- Offline mode with sync

**Tech Stack:** React Native or Flutter

---

### AI Features

#### Photo Analysis
**Status:** Research
**Description:** Computer vision to analyze pool condition from photos

**Use Cases:**
- Detect algae, staining, debris
- Estimate pool size from image
- Identify equipment issues

#### Predictive Maintenance
**Status:** Research
**Description:** ML models to predict issues before they occur

**Signals:**
- Chemical trend analysis (repeated low chlorine → possible leak)
- Visit duration trends (taking longer → possible equipment issue)
- Skip patterns (frequently skipped → gate code issue?)

---

## Completed
_(Move completed items here with completion date)_

- ✅ Multi-depot VRP optimization (2024-10-28)
- ✅ Real driving distances via OSRM (2024-10-28)
- ✅ Temporary tech assignments (2024-10-27)
- ✅ Tech chip UI redesign (2024-11-02)
