// RouteOptimizer Frontend Application

/*
 * ✅ REFACTORING COMPLETE: Reduced from 3,516 lines to ~108 lines (96.9% reduction)
 *
 * This file now serves as the main entry point and global state container.
 * All feature code has been extracted to focused modules in /static/js/modules/
 *
 * See REFACTORING_PLAN.md for module details.
 */

// Initialize map
let map;
// routeLayers moved to /static/js/modules/routes.js
let customerMarkers = [];
let customerMarkersById = {}; // Map customer IDs to marker objects
let highlightedMarker = null; // Currently highlighted marker
const API_BASE = window.location.origin;
const HOME_BASE = { lat: 38.4088, lng: -121.3716 }; // Elk Grove, CA
// Driver constants moved to /static/js/modules/drivers.js

// Current route result (for filtering when driver selection changes)
let currentRouteResult = null;

// Drag and drop state
let draggedStop = null;
let draggedStopRoute = null;

// Selected day
let selectedDay = 'all';

// Google Places configuration
let googlePlacesLoaded = false;
let hasGoogleMapsKey = false;

// Navigation functions moved to /static/js/modules/navigation.js

// ===== MODAL FUNCTIONS =====
// Modal functions moved to /static/js/modules/modals.js

document.addEventListener('DOMContentLoaded', function() {
    initModuleNavigation();
    initializeMap();
    attachEventListeners();
    initOptimizationModal();
    loadCustomers();
    loadDrivers();
    loadCustomersManagement();
    initTabs();
    initDaySelector();
    loadGooglePlacesAPI();
    initClientSearch();
    initClientFilter();
    initBulkEditModal();

    // Close context menus when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.context-menu-btn') && !e.target.closest('.context-menu')) {
            closeAllContextMenus();
        }
    });
});

// ========================================
// All Feature Code Extracted to Modules
// ========================================
// - Navigation & tabs → /static/js/modules/navigation.js
// - Map & markers → /static/js/modules/map.js
// - Modals & context menus → /static/js/modules/modals.js
// - Drivers management → /static/js/modules/drivers.js
// - Routes optimization → /static/js/modules/routes.js
// - Customer management → /static/js/modules/customers.js
// - Bulk editing → /static/js/modules/bulk-edit.js
// - Helper utilities → /static/js/utils/helpers.js
