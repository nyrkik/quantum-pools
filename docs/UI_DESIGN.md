# UI Design & Architecture

**Last Updated:** 2025-10-25

## Overall App Structure

**Status:** 🔄 Redesign in progress

### Planned Navigation (Decided, Not Implemented)

**Option 3: Hybrid - Icon sidebar + collapsible menu**

- Slim left sidebar (~50-60px) with icon-only navigation
- Icons for: Dashboard, Team, Clients, Routes, Jobs, Invoicing, Settings
- Hover tooltip labels
- Click to open full menu overlay or panel (optional)
- Collapsible on mobile
- Maximizes screen real estate while maintaining easy access

**Rationale:** Best balance of screen space vs usability. Professional, modern, scalable.

### Main Modules

1. **Dashboard** - Landing page with revenue, customers, team overview
2. **Team** - Driver/technician management
3. **Clients** - Customer management
4. **Routes** - Route optimization (current focus)
5. **Jobs** - Job tracking (future)
6. **Invoicing** - Billing/invoicing (future)
7. **Settings** - App configuration (future)

## Routes Module Redesign

**Status:** 🔄 Design decided, not implemented

### Current Issues
- Sidebar takes ~330px width (from PSS screenshot)
- Reduces map visibility
- Doesn't scale well with many techs

### New Design (Option B - Decided)

**Layout:**
```
┌─────────────────────────────────────┐
│ Day Tabs: Mon | Tue | Wed | ...    │ ← Already exists
├─────────────────────────────────────┤
│ Tech Chips: [John] [Sarah] [Mike]  │ ← New: horizontal scrollable
│ [+ More ▾]  [Controls...]          │ ← Dropdown after threshold
├─────────────────────────────────────┤
│                                     │
│          Map (Full Width)           │
│                                     │
│                                     │
└─────────────────────────────────────┘
```

**Tech Selector:**
- Horizontal chips/pills with tech names
- Click to toggle selection
- Color-coded by driver color
- Scalable: First 6-8 techs as chips, rest in dropdown
- Touch-friendly (44x44px minimum)

**Controls Bar:**
- Optimization mode radio buttons
- Day reassignment toggle
- Other route settings
- Horizontal layout, compact

**Benefits:**
- Maximizes map space
- Scales to many technicians
- Modern, professional appearance
- Mobile-responsive

## Design Principles

### Screen Space Maximization
- Primary workspace (map, tables) gets maximum space
- Navigation compact but accessible
- Minimize chrome and borders
- Collapsible elements where appropriate

### Scalability
- UI works with 1 or 100 technicians
- Pagination for large data sets
- Hybrid approaches (chips + dropdown)
- Performance with 1000+ customers

### Professional Appearance
- Clean, modern interface
- Consistent spacing and colors
- Professional color palette
- Smooth transitions
- No jarring layout shifts

### Mobile-First Responsive
- Touch targets ≥44x44px
- Thumb-friendly placement
- Collapsible navigation
- Readable without zoom (≥16px text)
- Test on actual devices

### Accessibility
- Keyboard navigation
- ARIA labels
- Color contrast ≥4.5:1
- Focus indicators
- Screen reader compatible

## Current Frontend Tech

- **Framework:** Vanilla JavaScript
- **Map:** Leaflet.js
- **CSS:** Custom (Bootstrap classes used)
- **Build:** None (direct HTML/JS/CSS)

## Color Coding

- Driver routes: Custom colors from driver.color field
- Map markers: Numbered with driver colors
- Route polylines: Match driver color

## Responsive Breakpoints

- Desktop: >1200px (full layout)
- Tablet: 768-1200px (collapsible sidebar)
- Mobile: <768px (hamburger menu)

## Future Considerations

- Consider modern framework (React/Vue) for complex multi-module app
- Component library for consistency
- State management for large data sets
- Real-time updates (WebSocket)
- Progressive Web App (PWA) for mobile
