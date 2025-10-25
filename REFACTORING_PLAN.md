# JavaScript Refactoring Plan

**Current Status:** app.js is 3,514 lines (140KB) - MUST be refactored incrementally

**Goal:** Break monolithic `static/js/app.js` into focused, testable modules

## Target Structure

```
static/js/
├── app.js                    # Main entry point (<200 lines)
├── modules/
│   ├── navigation.js         # Module routing & sidebar
│   ├── map.js               # Leaflet map initialization & markers
│   ├── modals.js            # Modal dialogs (optimize, filters, etc.)
│   ├── drivers.js           # Driver/team CRUD & color picker
│   ├── routes.js            # Route optimization & display
│   ├── customers.js         # Customer CRUD & profile display
│   └── bulk-edit.js         # Bulk editing & CSV import/export
└── utils/
    ├── api.js               # API wrapper functions
    ├── helpers.js           # Utility functions (address parsing, escapeHtml)
    └── forms.js             # Form validation & manipulation
```

## Module Extraction Progress

### ✅ Completed Modules
- None yet

### 🔄 In Progress
- None

### ⏳ Pending

#### 1. Utils Module (helpers.js) - ~100 lines
**Functions to extract:**
- `escapeHtml(text)` - Lines 3175-3180
- `combineAddressFields(street, city, state, zip)` - Lines 1342-1346
- `parseAddress(fullAddress)` - Lines 1347-1369

**Dependencies:** None (pure functions)

#### 2. Utils Module (api.js) - ~200 lines
**Functions to extract:**
- All inline `fetch()` calls wrapped into:
  - `customerAPI.getAll()`, `customerAPI.getById()`, `customerAPI.create()`, etc.
  - `driverAPI.getAll()`, `driverAPI.create()`, `driverAPI.update()`, etc.
  - `routeAPI.optimize()`, `routeAPI.save()`, `routeAPI.getByDay()`

**Dependencies:** None (wraps fetch API)

#### 3. Navigation Module (navigation.js) - ~150 lines
**Functions to extract:**
- `initModuleNavigation()` - Lines 43-95
- `switchModule(moduleName)` - Lines 96-134
- `handleHashChange()` - Lines 135-148

**Dependencies:** Uses map global, calls loadCustomersManagement(), loadDrivers()

#### 4. Modals Module (modals.js) - ~150 lines
**Functions to extract:**
- `openModal(modalId)` - Lines 151-157
- `closeModal(modalId)` - Lines 158-164
- `initOptimizationModal()` - Lines 165-218
- `toggleContextMenu(event, menuId)` - Lines 218-231
- `closeAllContextMenus()` - Lines 232-237

**Dependencies:** calls optimizeRoutes()

#### 5. Map Module (map.js) - ~200 lines
**Functions to extract:**
- `initializeMap()` - Lines 238-248
- `loadGooglePlacesAPI()` - Lines 249-275
- `initAutocomplete(inputElement)` - Lines 276-298
- `loadCustomers()` - Lines 299-316
- `displayCustomersOnMap(customers)` - Lines 317-421
- `highlightCustomerMarker(customerId)` - Lines 422-454

**Dependencies:** Uses map, customerMarkers globals; calls API

#### 6. Routes Module (routes.js) - ~600 lines
**Functions to extract:**
- `initDaySelector()` - Lines 487-513
- `optimizeRoutes()` - Lines 522-570
- `displayRoutes(result)` - Lines 571-646
- `saveRoutes(result)` - Lines 647-681
- `loadSavedRoutes(serviceDay)` - Lines 682-739
- `displayRoutesOnMap(routes)` - Lines 740-800
- `makeSavedRoutesEditable(routes)` - Lines 3292-3339
- `createDraggableStop(stop, routeId)` - Lines 3340-3356
- Drag-and-drop handlers (Lines 3357-3500)

**Dependencies:** Uses map, routeLayers; calls API; calls displayCustomersOnMap()

#### 7. Drivers Module (drivers.js) - ~600 lines
**Functions to extract:**
- `loadDrivers()` - Lines 952-976
- `populateTechChips(drivers)` - Lines 977-1047
- `toggleAllTechs()` - Lines 1048-1083
- `toggleTechSelection(driverId, multiSelect)` - Lines 1084-1141
- `filterRoutesByDrivers()` - Lines 1142-1152
- `displayDrivers(drivers)` - Lines 1153-1181
- `createColorPickerButton()` - Lines 1182-1189
- `openColorPickerModal(inputId)` - Lines 1190-1215
- `closeColorPickerModal()` - Lines 1216-1222
- `selectColor(color, inputId)` - Lines 1223-1228
- `showAddDriverForm()` - Lines 1229-1341
- `saveDriver()` - Lines 1370-1423
- `deleteDriver(driverId)` - Lines 1424-1444
- `showEditDriverForm(driverId)` - Lines 1445-1572
- `updateDriver(driverId)` - Lines 1573-1635

**Dependencies:** Calls API; uses driverAPI

#### 8. Customers Module (customers.js) - ~1200 lines
**Functions to extract:**
- `loadCustomersManagement()` - Lines 1636-1661
- `applyClientFilters()` - Lines 1662-1689
- `initClientSearch()` - Lines 1690-1696
- `initClientFilter()` - Lines 1697-1754
- `displayCustomersManagement(customers)` - Lines 1863-1904
- `displayClientProfile(customer)` - Lines 1905-1998
- `showAddCustomerForm()` - Lines 1999-2223
- `updateAddServiceDayOptions()` - Lines 2193-2223
- `saveCustomer()` - Lines 2224-2336
- `editCustomer(customerId)` - Lines 2337-2352
- `showEditCustomerForm(customer)` - Lines 2353-2550
- `storeOriginalFormValues()` - Lines 2551-2576
- `detectFormChanges()` - Lines 2577-2617
- `cancelEditCustomer(customerId)` - Lines 2618-2630
- `updateServiceDayOptions()` - Lines 2631-2667
- `toggleNameFields()` - Lines 2668-2687
- `toggleAddNameFields()` - Lines 2688-2707
- `updateCustomer(customerId)` - Lines 2708-2828
- `deleteCustomer(customerId)` - Lines 2829-2850
- `regeocodeCustomer(customerId)` - Lines 2851-2913
- `validateCoordinates()` - Lines 2914-3004
- `fixCustomerCoordinates(customerId, lat, lng)` - Lines 3005-3035

**Dependencies:** Massive; calls API, uses map, calls combineAddressFields(), parseAddress()

#### 9. Bulk Edit Module (bulk-edit.js) - ~300 lines
**Functions to extract:**
- `initBulkEditModal()` - Lines 1755-1790
- `handleCSVImport(event)` - Lines 1791-1824
- `downloadCSVTemplate()` - Lines 1825-1842
- `exportCustomersCSV()` - Lines 1843-1862
- `showBulkEditCustomers()` - Lines 3036-3062
- `renderBulkEditTable()` - Lines 3063-3174
- `markCustomerModified(customerId)` - Lines 3181-3196
- `saveBulkEditChanges()` - Lines 3197-3291

**Dependencies:** Calls API, uses customerAPI

## Refactoring Process

When extracting a module:

1. **Before you start:**
   - Mark module as "In Progress" in this document
   - Create `static/js/modules/` and `static/js/utils/` directories if they don't exist

2. **Extract functions:**
   - Copy functions to new file with proper JSDoc comments
   - Keep functions in global scope (not ES6 modules for now)
   - Add file header comment with module purpose
   - Preserve dependencies (document what globals are used)

3. **Update HTML:**
   - Add `<script>` tag to `static/index.html` in correct load order
   - Utilities must load before modules
   - Modules must load before app.js

4. **Test thoroughly:**
   - Verify functionality works exactly as before
   - Check browser console for errors
   - Test all features in the extracted module

5. **Update documentation:**
   - Mark module as "Completed" in this document
   - Add line count reduction to app.js
   - Commit with clear message

## Load Order Dependencies

Scripts MUST be loaded in this order in index.html:

```html
<!-- Utilities (no dependencies) -->
<script src="/static/js/utils/helpers.js"></script>
<script src="/static/js/utils/api.js"></script>
<script src="/static/js/utils/forms.js"></script>

<!-- Core modules -->
<script src="/static/js/modules/navigation.js"></script>
<script src="/static/js/modules/map.js"></script>
<script src="/static/js/modules/modals.js"></script>

<!-- Feature modules (depend on core) -->
<script src="/static/js/modules/drivers.js"></script>
<script src="/static/js/modules/routes.js"></script>
<script src="/static/js/modules/customers.js"></script>
<script src="/static/js/modules/bulk-edit.js"></script>

<!-- Main entry point (depends on all modules) -->
<script src="/static/js/app.js"></script>
```

## Progress Tracking

**Initial:** 3,514 lines
**Current:** 3,514 lines
**Target:** <200 lines in app.js

**Modules extracted:** 0/9
**Estimated time:** ~6-8 hours total (1 hour per major module)

## Notes

- Do NOT rush this refactor. Each module must be tested before moving to the next.
- Keep app.js functional throughout - never break the application.
- If a module extraction introduces bugs, roll back immediately and fix.
- Update this document as you progress - it's your accountability tracker.

**Last Updated:** October 25, 2025
