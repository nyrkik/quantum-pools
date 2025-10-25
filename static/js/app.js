// RouteOptimizer Frontend Application

/*
 * ⚠️  WARNING: THIS FILE IS 3,500+ LINES AND MUST BE REFACTORED INCREMENTALLY ⚠️
 *
 * Before adding ANY substantial code (>50 lines) to this file:
 * 1. Check file size: wc -l static/js/app.js
 * 2. Read REFACTORING_PLAN.md to see module boundaries
 * 3. Extract the relevant module FIRST before making changes
 * 4. Update REFACTORING_PLAN.md to track progress
 *
 * See CLAUDE.md § 16 for full refactoring guidelines.
 *
 * DO NOT ignore this warning. The monolith stops here.
 */

// Initialize map
let map;
let routeLayers = [];
let customerMarkers = [];
let customerMarkersById = {}; // Map customer IDs to marker objects
let highlightedMarker = null; // Currently highlighted marker
const API_BASE = window.location.origin;
const HOME_BASE = { lat: 38.4088, lng: -121.3716 }; // Elk Grove, CA

// Predefined colors for drivers (excluding red which is reserved for unassigned)
const DRIVER_COLORS = [
    '#3498db', // Blue
    '#2ecc71', // Green
    '#9b59b6', // Purple
    '#f39c12', // Orange
    '#1abc9c', // Turquoise
    '#34495e', // Dark gray
    '#e67e22', // Carrot
    '#16a085', // Green sea
    '#2980b9', // Belize hole
    '#8e44ad', // Wisteria
    '#f1c40f', // Sun flower
    '#d35400'  // Pumpkin
];

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

// ===== MODULE NAVIGATION =====
function initModuleNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const mobileToggle = document.getElementById('mobile-menu-toggle');
    const sidebar = document.getElementById('app-sidebar');

    // Handle module navigation
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const targetModule = this.dataset.module;
            switchModule(targetModule);

            // Update active state
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');

            // Close mobile menu if open
            if (window.innerWidth <= 768) {
                sidebar.classList.remove('mobile-open');
            }
        });
    });

    // Handle mobile sidebar toggle
    if (mobileToggle) {
        mobileToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            sidebar.classList.toggle('mobile-open');
        });
    }

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(e) {
        if (window.innerWidth <= 768 &&
            sidebar.classList.contains('mobile-open') &&
            !sidebar.contains(e.target) &&
            !mobileToggle.contains(e.target)) {
            sidebar.classList.remove('mobile-open');
        }
    });

    // Handle hash navigation (URL #routes, etc.)
    window.addEventListener('hashchange', handleHashChange);

    // Check initial hash or default to dashboard
    const hash = window.location.hash.substring(1);
    if (!hash) {
        window.location.hash = 'dashboard';
    } else {
        handleHashChange();
    }
}

function switchModule(moduleName) {
    // Hide all modules
    const modules = document.querySelectorAll('.module-content');
    modules.forEach(module => {
        module.classList.remove('active');
        module.style.display = 'none';
    });

    // Show target module
    const targetModule = document.getElementById('module-' + moduleName);
    if (targetModule) {
        targetModule.classList.add('active');
        targetModule.style.display = 'block';

        // If switching to routes, reinitialize map
        if (moduleName === 'routes' && map) {
            setTimeout(() => {
                map.invalidateSize();
            }, 100);
        }

        // If switching to clients, reload customer list
        if (moduleName === 'clients') {
            loadCustomersManagement();
        }

        // Load module-specific data
        if (moduleName === 'team' && !document.getElementById('drivers-list').dataset.loaded) {
            loadDrivers();
            document.getElementById('drivers-list').dataset.loaded = 'true';
        }

        if (moduleName === 'clients' && !document.getElementById('customers-list').dataset.loaded) {
            loadCustomersManagement();
            document.getElementById('customers-list').dataset.loaded = 'true';
        }
    }
}

function handleHashChange() {
    const hash = window.location.hash.substring(1); // Remove #
    if (hash) {
        switchModule(hash);
        // Update nav active state
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            if (item.dataset.module === hash) {
                navItems.forEach(nav => nav.classList.remove('active'));
                item.classList.add('active');
            }
        });
    }
}

// ===== MODAL FUNCTIONS =====
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

function initOptimizationModal() {
    const modal = document.getElementById('optimize-modal');
    const optimizeBtn = document.getElementById('optimize-btn');
    const runOptimizeBtn = document.getElementById('run-optimize-btn');
    const closeBtn = modal.querySelector('.modal-close');

    // Open modal when clicking "Optimize Routes" button
    optimizeBtn.addEventListener('click', function() {
        openModal('optimize-modal');
    });

    // Close modal when clicking X
    closeBtn.addEventListener('click', function() {
        closeModal('optimize-modal');
    });

    // Close modal when clicking outside
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal('optimize-modal');
        }
    });

    // Run optimization and close modal
    runOptimizeBtn.addEventListener('click', async function() {
        closeModal('optimize-modal');
        await optimizeRoutes();
    });
}

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

function toggleContextMenu(event, menuId) {
    event.stopPropagation();
    const menu = document.getElementById('menu-' + menuId);
    const isCurrentlyOpen = menu.classList.contains('show');

    // Close all menus first
    closeAllContextMenus();

    // Toggle the clicked menu
    if (!isCurrentlyOpen) {
        menu.classList.add('show');
    }
}

function closeAllContextMenus() {
    document.querySelectorAll('.context-menu').forEach(menu => {
        menu.classList.remove('show');
    });
}

function initializeMap() {
    // Initialize Leaflet map centered on US (will be updated based on data)
    map = L.map('map').setView([39.8283, -98.5795], 4);

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);
}

async function loadGooglePlacesAPI() {
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const config = await response.json();

        hasGoogleMapsKey = config.has_google_maps;

        if (hasGoogleMapsKey && config.google_maps_api_key) {
            // Load Google Places API dynamically
            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${config.google_maps_api_key}&libraries=places`;
            script.async = true;
            script.defer = true;
            script.onload = () => {
                googlePlacesLoaded = true;
                console.log('Google Places API loaded successfully');
            };
            script.onerror = () => {
                console.warn('Failed to load Google Places API');
            };
            document.head.appendChild(script);
        }
    } catch (error) {
        console.error('Error loading Google Places configuration:', error);
    }
}

function initAutocomplete(inputElement) {
    if (!googlePlacesLoaded || !hasGoogleMapsKey || !window.google) {
        return;
    }

    try {
        const autocomplete = new google.maps.places.Autocomplete(inputElement, {
            types: ['address'],
            componentRestrictions: { country: 'us' }
        });

        // Optional: Add listener to handle place selection
        autocomplete.addListener('place_changed', function() {
            const place = autocomplete.getPlace();
            if (place.formatted_address) {
                inputElement.value = place.formatted_address;
            }
        });
    } catch (error) {
        console.error('Error initializing autocomplete:', error);
    }
}

async function loadCustomers() {
    try {
        let url = `${API_BASE}/api/customers?page_size=100`;
        if (selectedDay !== 'all') {
            url += `&service_day=${selectedDay}`;
        }

        const response = await fetch(url);
        if (!response.ok) return;

        const data = await response.json();
        displayCustomersOnMap(data.customers || []);
    } catch (error) {
        console.error('Error loading customers:', error);
        displayCustomersOnMap([]);
    }
}

function displayCustomersOnMap(customers) {
    // Clear existing customer markers
    customerMarkers.forEach(marker => map.removeLayer(marker));
    customerMarkers = [];
    customerMarkersById = {};

    const coordinates = [];

    // Track coordinate usage to offset duplicates
    const coordCounts = {};

    customers.forEach(customer => {
        if (customer.latitude && customer.longitude) {
            // Determine if we should show this customer
            const isUnassigned = !customer.assigned_driver_id;
            const isSelectedDriver = customer.assigned_driver_id && selectedDriverIds.has(customer.assigned_driver_id);

            // Show if: unassigned (always) OR assigned to selected driver
            if (!isUnassigned && selectedDriverIds.size > 0 && !isSelectedDriver) {
                return; // Skip if not in our selected drivers
            }

            if (!isUnassigned && selectedDriverIds.size === 0) {
                return; // No drivers selected, don't show assigned customers
            }
            // Create coordinate key
            const coordKey = `${customer.latitude},${customer.longitude}`;

            // Track how many times we've used this coordinate
            if (!coordCounts[coordKey]) {
                coordCounts[coordKey] = 0;
            }
            const offset = coordCounts[coordKey];
            coordCounts[coordKey]++;

            // Apply small offset for overlapping markers (0.0003 degrees ≈ 30 meters)
            let lat = customer.latitude;
            let lng = customer.longitude;

            if (offset > 0) {
                const angle = (offset - 1) * (360 / 8); // Spread in a circle
                const distance = 0.0003;
                lat += distance * Math.cos(angle * Math.PI / 180);
                lng += distance * Math.sin(angle * Math.PI / 180);
            }

            const latLng = [lat, lng];
            coordinates.push(latLng);

            // Red for unassigned, blue for assigned
            const markerColor = isUnassigned ? '#e74c3c' : '#3498db';

            const marker = L.circleMarker(latLng, {
                radius: 6,
                fillColor: markerColor,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: isUnassigned ? 0.9 : 0.7
            }).addTo(map);

            // Display schedule or single day - abbreviated format
            let scheduleDisplay;
            if (customer.service_schedule) {
                // Multi-day schedule like "Mo/Th" or "Mo/We/Fr"
                scheduleDisplay = customer.service_schedule;
            } else {
                // Single day - convert to abbreviation
                const dayAbbrev = {
                    'monday': 'Mo',
                    'tuesday': 'Tu',
                    'wednesday': 'We',
                    'thursday': 'Th',
                    'friday': 'Fr',
                    'saturday': 'Sa',
                    'sunday': 'Su'
                };
                scheduleDisplay = dayAbbrev[customer.service_day] || customer.service_day;
            }

            marker.bindPopup(`
                <b>${customer.display_name}</b><br>
                ${customer.address}<br>
                <em>${scheduleDisplay}</em>
            `);

            // Store customer ID with marker for later reference
            marker.customerId = customer.id;
            customerMarkers.push(marker);
            customerMarkersById[customer.id] = marker;
        }
    });

    if (coordinates.length > 0) {
        const bounds = L.latLngBounds(coordinates);
        map.fitBounds(bounds, {
            padding: [80, 80],
            maxZoom: 14
        });
    } else {
        // No customers to display, center on home base
        map.setView([HOME_BASE.lat, HOME_BASE.lng], 12);
    }
}

function highlightCustomerMarker(customerId) {
    // Reset previously highlighted marker
    if (highlightedMarker) {
        highlightedMarker.setStyle({
            radius: 6,
            fillColor: '#3498db',
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.7
        });
    }

    // Highlight the selected marker
    const marker = customerMarkersById[customerId];
    if (marker) {
        marker.setStyle({
            radius: 10,
            fillColor: '#e74c3c',
            color: '#fff',
            weight: 3,
            opacity: 1,
            fillOpacity: 0.9
        });

        // Pan to marker and open popup
        map.panTo(marker.getLatLng());
        marker.openPopup();

        highlightedMarker = marker;
    }
}

function initTabs() {
    // Routes module tabs (.nav-tab)
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            const tabName = this.dataset.tab;

            // Update active tab
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Show corresponding content
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });

    // Clients module tabs (.tab-btn)
    document.querySelectorAll('.clients-tabs .tab-btn').forEach(tab => {
        tab.addEventListener('click', function() {
            const tabName = this.dataset.tab;

            // Update active tab
            document.querySelectorAll('.clients-tabs .tab-btn').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Show corresponding content
            document.querySelectorAll('.clients-tab-content .tab-pane').forEach(pane => pane.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });
}

function initDaySelector() {
    // Get current day of week
    const daysOfWeek = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const today = daysOfWeek[new Date().getDay()];

    // Set today as selected day and active tab
    selectedDay = today;

    document.querySelectorAll('.day-tab').forEach(tab => {
        if (tab.dataset.day === today) {
            tab.classList.add('active');
        }

        tab.addEventListener('click', function() {
            selectedDay = this.dataset.day;

            // Update active day
            document.querySelectorAll('.day-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Reload customers for selected day
            loadCustomers();
            loadCustomersManagement();
        });
    });
}

function attachEventListeners() {
    // Module event listeners
    document.getElementById('add-driver-btn')?.addEventListener('click', showAddDriverForm);
    document.getElementById('add-customer-btn')?.addEventListener('click', showAddCustomerForm);
    document.getElementById('bulk-edit-btn')?.addEventListener('click', showBulkEditCustomers);
    // Note: CSV import/export and coordinate validation features will be moved to Bulk Edit modal
}

async function optimizeRoutes() {
    const numDrivers = parseInt(document.getElementById('num-drivers').value);
    const allowReassignment = document.getElementById('allow-reassignment').checked;
    const optimizationMode = document.querySelector('input[name="optimization-mode"]:checked').value;

    const optimizeBtn = document.getElementById('optimize-btn');
    optimizeBtn.disabled = true;
    optimizeBtn.textContent = 'Optimizing...';

    try {
        const requestBody = {
            num_drivers: numDrivers || null,
            service_day: selectedDay === 'all' ? null : selectedDay,
            allow_day_reassignment: allowReassignment,
            optimization_mode: optimizationMode
        };

        const response = await fetch(`${API_BASE}/api/routes/optimize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Optimization failed');
        }

        const result = await response.json();

        if (result.routes && result.routes.length > 0) {
            currentRouteResult = result; // Store for filtering
            displayRoutes(result);
            displayRoutesOnMap(result.routes);
        } else {
            currentRouteResult = null;
            alert(result.message || 'No routes generated. Add customers and drivers first.');
        }
    } catch (error) {
        console.error('Error optimizing routes:', error);
        alert(`Failed to optimize routes: ${error.message}`);
    } finally {
        optimizeBtn.disabled = false;
        optimizeBtn.textContent = 'Optimize Routes';
    }
}

function displayRoutes(result) {
    const container = document.getElementById('routes-content');
    container.innerHTML = '';

    if (!result.routes || result.routes.length === 0) {
        container.innerHTML = '<p class="placeholder">No routes generated</p>';
        return;
    }

    // Show summary
    if (result.summary) {
        const summary = document.createElement('div');
        summary.className = 'route-summary';
        summary.innerHTML = `
            <h3>Route Summary</h3>
            <p><strong>Total Routes:</strong> ${result.summary.total_routes}</p>
            <p><strong>Total Customers:</strong> ${result.summary.total_customers}</p>
            <p><strong>Total Distance:</strong> ${result.summary.total_distance_miles.toFixed(1)} miles</p>
            <p><strong>Total Duration:</strong> ${result.summary.total_duration_minutes} minutes</p>
        `;

        // Add save button
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn-primary';
        saveBtn.textContent = 'Save Routes';
        saveBtn.style.marginTop = '1rem';
        saveBtn.onclick = () => saveRoutes(result);
        summary.appendChild(saveBtn);

        container.appendChild(summary);
    }

    // Filter and show routes based on selected drivers
    const filteredRoutes = result.routes.filter(route => {
        if (selectedDriverIds.size === 0) return false;
        if (route.driver_id && !selectedDriverIds.has(route.driver_id)) return false;
        return true;
    });

    if (filteredRoutes.length === 0) {
        container.innerHTML += '<p class="placeholder">No routes for selected drivers</p>';
        return;
    }

    filteredRoutes.forEach((route, index) => {
        const routeCard = document.createElement('div');
        routeCard.className = 'route-card';

        // Add color indicator
        const colorIndicator = document.createElement('div');
        colorIndicator.className = 'route-color-indicator';
        colorIndicator.style.backgroundColor = route.driver_color || '#3498db';
        routeCard.appendChild(colorIndicator);

        const title = document.createElement('h3');
        title.textContent = `${route.driver_name} - ${route.service_day}`;
        routeCard.appendChild(title);

        const info = document.createElement('p');
        info.textContent = `${route.total_customers} stops, ${route.total_distance_miles.toFixed(1)} miles, ${route.total_duration_minutes} min`;
        routeCard.appendChild(info);

        const stopsList = document.createElement('ul');
        stopsList.className = 'route-stops';

        route.stops.forEach((stop) => {
            const stopItem = document.createElement('li');
            stopItem.textContent = `${stop.sequence}. ${stop.customer_name} - ${stop.address} (${stop.service_duration} min)`;
            stopsList.appendChild(stopItem);
        });

        routeCard.appendChild(stopsList);
        container.appendChild(routeCard);
    });
}

async function saveRoutes(result) {
    if (!result.routes || result.routes.length === 0) {
        alert('No routes to save');
        return;
    }

    const serviceDay = result.routes[0].service_day;

    try {
        const response = await fetch(`${API_BASE}/api/routes/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                service_day: serviceDay,
                routes: result.routes
            })
        });

        if (!response.ok) {
            throw new Error('Failed to save routes');
        }

        const saveResult = await response.json();
        alert(`Successfully saved ${saveResult.route_ids.length} routes for ${serviceDay}!`);

        // Reload saved routes and show download options
        await loadSavedRoutes(serviceDay);
    } catch (error) {
        console.error('Error saving routes:', error);
        alert('Failed to save routes. Please try again.');
    }
}

async function loadSavedRoutes(serviceDay) {
    try {
        const response = await fetch(`${API_BASE}/api/routes/day/${serviceDay}`);

        if (!response.ok) {
            console.error('No saved routes found');
            return;
        }

        const routes = await response.json();

        if (routes.length === 0) {
            return;
        }

        // Add download section
        const container = document.getElementById('routes-content');
        const downloadSection = document.createElement('div');
        downloadSection.className = 'route-summary';
        downloadSection.style.marginTop = '1rem';
        downloadSection.innerHTML = '<h3>Download Route Sheets</h3>';

        // Add edit routes button
        const editBtn = document.createElement('button');
        editBtn.className = 'btn-secondary';
        editBtn.textContent = `Edit Routes (Drag & Drop)`;
        editBtn.style.marginTop = '0.5rem';
        editBtn.onclick = () => makeSavedRoutesEditable(routes);
        downloadSection.appendChild(editBtn);

        // Add download all button
        const downloadAllBtn = document.createElement('button');
        downloadAllBtn.className = 'btn-primary';
        downloadAllBtn.textContent = `Download All Routes for ${serviceDay} (PDF)`;
        downloadAllBtn.style.marginTop = '0.5rem';
        downloadAllBtn.onclick = () => {
            window.location.href = `${API_BASE}/api/routes/day/${serviceDay}/pdf`;
        };
        downloadSection.appendChild(downloadAllBtn);

        // Add individual route download buttons
        routes.forEach(route => {
            const downloadBtn = document.createElement('button');
            downloadBtn.className = 'btn-secondary';
            downloadBtn.textContent = `Download Route ${route.id.substring(0, 8)} (PDF)`;
            downloadBtn.style.marginTop = '0.5rem';
            downloadBtn.onclick = () => {
                window.location.href = `${API_BASE}/api/routes/${route.id}/pdf`;
            };
            downloadSection.appendChild(downloadBtn);
        });

        container.appendChild(downloadSection);
    } catch (error) {
        console.error('Error loading saved routes:', error);
    }
}

function displayRoutesOnMap(routes) {
    // Clear existing route layers
    routeLayers.forEach(layer => map.removeLayer(layer));
    routeLayers = [];

    const allCoordinates = [];

    routes.forEach((route) => {
        // Filter by selected drivers
        if (selectedDriverIds.size === 0) {
            return; // No drivers selected, don't show route
        }

        if (route.driver_id && !selectedDriverIds.has(route.driver_id)) {
            return; // Skip routes for drivers not in selection
        }

        // Use driver's color, or fall back to default
        const color = route.driver_color || '#3498db';
        const coordinates = [];

        route.stops.forEach(stop => {
            if (stop.latitude && stop.longitude) {
                const latLng = [stop.latitude, stop.longitude];
                coordinates.push(latLng);
                allCoordinates.push(latLng);

                // Add marker
                const marker = L.circleMarker(latLng, {
                    radius: 8,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8
                }).addTo(map);

                marker.bindPopup(`<b>${stop.customer_name}</b><br>${stop.address}<br><em>${route.driver_name}</em>`);
                routeLayers.push(marker);
            }
        });

        // Draw route line
        if (coordinates.length > 1) {
            const polyline = L.polyline(coordinates, {
                color: color,
                weight: 3,
                opacity: 0.7
            }).addTo(map);

            routeLayers.push(polyline);
        }
    });

    // Fit map to show all routes
    if (allCoordinates.length > 0) {
        const bounds = L.latLngBounds(allCoordinates);
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

function importCSV() {
    // Create file input
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv';

    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${API_BASE}/api/imports/customers/csv?geocode=true`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Import failed');
            }

            const result = await response.json();

            // Build detailed message
            let message = `Import complete!\n\n`;
            message += `Total rows: ${result.total_rows}\n`;
            message += `Imported: ${result.imported}\n`;
            message += `Skipped: ${result.skipped}\n`;
            message += `Errors: ${result.errors}\n`;

            // Show error details if any
            if (result.error_details && result.error_details.length > 0) {
                message += `\nError Details:\n`;
                result.error_details.slice(0, 5).forEach(err => {
                    message += `  Row ${err.row}: ${err.error}\n`;
                });
                if (result.error_details.length > 5) {
                    message += `  ... and ${result.error_details.length - 5} more errors\n`;
                }
            }

            // Show skipped details if any
            if (result.skipped_customers && result.skipped_customers.length > 0) {
                message += `\nSkipped (already exist):\n`;
                result.skipped_customers.slice(0, 5).forEach(skip => {
                    message += `  Row ${skip.row}: ${skip.name}\n`;
                });
                if (result.skipped_customers.length > 5) {
                    message += `  ... and ${result.skipped_customers.length - 5} more\n`;
                }
            }

            alert(message);

            // Reload customers on map
            loadCustomers();
            loadCustomersManagement();
        } catch (error) {
            console.error('Error importing CSV:', error);
            alert(`Failed to import CSV file:\n${error.message}`);
        }
    };

    input.click();
}

function downloadCSVTemplate() {
    window.location.href = `${API_BASE}/api/imports/customers/template`;
}

function showCSVHelp() {
    const container = document.getElementById('customers-list');

    const helpHtml = `
        <div class="customer-form">
            <h3>CSV Import Format</h3>

            <p><strong>Required Columns:</strong></p>
            <ul style="margin-left: 1.5rem; margin-bottom: 1rem;">
                <li><strong>Client</strong> - Customer name</li>
                <li><strong>Address</strong> - Street address</li>
                <li><strong>City</strong> - City name</li>
                <li><strong>State</strong> - State abbreviation (e.g., CA, TX, FL)</li>
                <li><strong>Zip</strong> - Zip code</li>
                <li><strong>Type</strong> - Must be "Residential" or "Commercial"</li>
                <li><strong>Days</strong> - See below for format</li>
            </ul>

            <p><strong>Days Column Format:</strong></p>
            <ul style="margin-left: 1.5rem; margin-bottom: 1rem;">
                <li><strong>Residential:</strong> Two-letter day code
                    <ul style="margin-left: 1rem;">
                        <li>Mo (Monday), Tu (Tuesday), We (Wednesday)</li>
                        <li>Th (Thursday), Fr (Friday), Sa (Saturday), Su (Sunday)</li>
                    </ul>
                </li>
                <li><strong>Commercial:</strong> Number indicating frequency
                    <ul style="margin-left: 1rem;">
                        <li><strong>2</strong> = Twice per week (Mo/Th schedule)</li>
                        <li><strong>3</strong> = Three times per week (Mo/We/Fr schedule)</li>
                    </ul>
                </li>
            </ul>

            <p><strong>Optional Columns:</strong></p>
            <ul style="margin-left: 1.5rem; margin-bottom: 1rem;">
                <li><strong>Difficulty</strong> - Number 1-5 (1=easy, 5=very hard). Affects service time (+5 min per level).</li>
                <li><strong>Latitude</strong> - Latitude coordinate (will geocode if blank)</li>
                <li><strong>Longitude</strong> - Longitude coordinate (will geocode if blank)</li>
            </ul>

            <p><strong>Service Times:</strong></p>
            <ul style="margin-left: 1.5rem; margin-bottom: 1rem;">
                <li>Residential: 15 minutes base time</li>
                <li>Commercial: 25 minutes base time</li>
                <li>Difficulty adds +5 minutes per level (e.g., difficulty 3 adds 10 minutes)</li>
            </ul>

            <p><strong>Multiple Service Days:</strong></p>
            <p style="margin-left: 1.5rem; margin-bottom: 1rem;">
                Commercial properties with Days=2 or Days=3 will be stored as a single customer with a service schedule.
                For example, Days=2 creates a customer with schedule "Mo/Th" (Monday/Thursday).
                The optimizer will assign the actual service days based on route efficiency while respecting the frequency.
            </p>

            <p><strong>Example CSV:</strong></p>
            <pre style="background: #f5f5f5; padding: 1rem; border-radius: 4px; overflow-x: auto; font-size: 0.85rem;">
Client,Address,City,State,Zip,Type,Days,Difficulty,Latitude,Longitude
John's Pool,123 Main St,Anytown,CA,90210,Residential,Mo,1,,
Smith Residence,456 Elm St,Cityville,CA,90211,Residential,We,2,,
ABC Corp Pool,789 Business Blvd,Townsburg,CA,90212,Commercial,2,3,,
XYZ Commercial,321 Industry Dr,Metropolis,CA,90213,Commercial,3,4,,
            </pre>

            <p style="margin-top: 1rem;"><em>Tip: Click "Download CSV Template" to get a pre-formatted template with examples.</em></p>

            <button class="btn-primary" onclick="loadCustomersManagement()">Close</button>
        </div>
    `;

    container.innerHTML = helpHtml;
}

// Driver Management Functions

let allDrivers = [];
let selectedDriverIds = new Set();

async function loadDrivers() {
    try {
        const response = await fetch(`${API_BASE}/api/drivers/`);
        if (!response.ok) {
            console.error('Failed to load drivers');
            return;
        }

        const data = await response.json();
        allDrivers = data.drivers || [];

        displayDrivers(allDrivers);
        populateTechChips(allDrivers);

        // Show add driver button
        const addBtn = document.getElementById('add-driver-btn');
        if (addBtn) addBtn.style.display = 'block';
    } catch (error) {
        console.error('Error loading drivers:', error);
        if (document.getElementById('drivers-list')) {
            document.getElementById('drivers-list').innerHTML = '<p class="placeholder">Failed to load drivers</p>';
        }
    }
}

function populateTechChips(drivers) {
    const container = document.getElementById('tech-chips');
    if (!container) return;

    container.innerHTML = '';
    selectedDriverIds.clear();

    // Add "All" toggle switch first
    const toggleContainer = document.createElement('div');
    toggleContainer.className = 'tech-toggle-container';

    const label = document.createElement('span');
    label.className = 'tech-toggle-label';
    label.textContent = 'All';

    const toggleSwitch = document.createElement('label');
    toggleSwitch.className = 'toggle-switch';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = 'all-toggle';
    checkbox.checked = true;
    checkbox.addEventListener('change', toggleAllTechs);

    const slider = document.createElement('span');
    slider.className = 'toggle-slider';

    toggleSwitch.appendChild(checkbox);
    toggleSwitch.appendChild(slider);
    toggleContainer.appendChild(label);
    toggleContainer.appendChild(toggleSwitch);
    container.appendChild(toggleContainer);

    if (!drivers || drivers.length === 0) {
        return;
    }

    drivers.forEach(driver => {
        const chip = document.createElement('button');
        chip.className = 'tech-chip selected';
        chip.dataset.driverId = driver.id;
        chip.style.borderColor = driver.color || '#3498db';
        chip.style.backgroundColor = driver.color || '#3498db';
        chip.style.color = 'white';
        chip.textContent = driver.name;

        selectedDriverIds.add(driver.id);

        // Click handler with Ctrl detection
        chip.addEventListener('click', function(e) {
            toggleTechSelection(driver.id, e.ctrlKey || e.metaKey);
        });

        // Long-press handler for mobile multi-select
        let pressTimer;
        chip.addEventListener('touchstart', function(e) {
            pressTimer = setTimeout(function() {
                toggleTechSelection(driver.id, true); // true = multi-select mode
            }, 500); // 500ms for long-press
        });
        chip.addEventListener('touchend', function() {
            clearTimeout(pressTimer);
        });
        chip.addEventListener('touchmove', function() {
            clearTimeout(pressTimer);
        });

        container.appendChild(chip);
    });
}

function toggleAllTechs() {
    const allToggle = document.getElementById('all-toggle');
    const isChecked = allToggle.checked;

    if (isChecked) {
        // Select all
        selectedDriverIds.clear();

        allDrivers.forEach(driver => {
            selectedDriverIds.add(driver.id);
            const chip = document.querySelector(`.tech-chip[data-driver-id="${driver.id}"]`);
            if (chip) {
                chip.classList.remove('unselected');
                chip.classList.add('selected');
                chip.style.backgroundColor = driver.color || '#3498db';
                chip.style.color = 'white';
            }
        });
    } else {
        // Deselect all
        selectedDriverIds.clear();

        allDrivers.forEach(driver => {
            const chip = document.querySelector(`.tech-chip[data-driver-id="${driver.id}"]`);
            if (chip) {
                chip.classList.remove('selected');
                chip.classList.add('unselected');
                chip.style.backgroundColor = '#f5f5f5';
                chip.style.color = '#999';
            }
        });
    }

    filterRoutesByDrivers();
}

function toggleTechSelection(driverId, multiSelect = false) {
    const chip = document.querySelector(`.tech-chip[data-driver-id="${driverId}"]`);
    if (!chip) return;

    const allToggle = document.getElementById('all-toggle');

    if (multiSelect) {
        // Multi-select mode: toggle this driver only
        if (selectedDriverIds.has(driverId)) {
            selectedDriverIds.delete(driverId);
            chip.classList.remove('selected');
            chip.classList.add('unselected');
            chip.style.backgroundColor = '#f5f5f5';
            chip.style.color = '#999';
        } else {
            selectedDriverIds.add(driverId);
            chip.classList.remove('unselected');
            chip.classList.add('selected');
            const driver = allDrivers.find(d => d.id === driverId);
            if (driver) {
                chip.style.backgroundColor = driver.color || '#3498db';
                chip.style.color = 'white';
            }
        }
    } else {
        // Single-select mode: deselect all others, select only this one
        selectedDriverIds.clear();

        // Deselect all chips
        allDrivers.forEach(driver => {
            const otherChip = document.querySelector(`.tech-chip[data-driver-id="${driver.id}"]`);
            if (otherChip) {
                otherChip.classList.remove('selected');
                otherChip.classList.add('unselected');
                otherChip.style.backgroundColor = '#f5f5f5';
                otherChip.style.color = '#999';
            }
        });

        // Select only this driver
        selectedDriverIds.add(driverId);
        chip.classList.remove('unselected');
        chip.classList.add('selected');
        const driver = allDrivers.find(d => d.id === driverId);
        if (driver) {
            chip.style.backgroundColor = driver.color || '#3498db';
            chip.style.color = 'white';
        }
    }

    // Update All toggle state
    if (allToggle) {
        allToggle.checked = (selectedDriverIds.size === allDrivers.length);
    }

    filterRoutesByDrivers();
}

function filterRoutesByDrivers() {
    // Reload customers to update map with filtered drivers
    loadCustomers();

    // Re-filter and redisplay routes if they exist
    if (currentRouteResult && currentRouteResult.routes) {
        displayRoutes(currentRouteResult);
        displayRoutesOnMap(currentRouteResult.routes);
    }
}

function displayDrivers(drivers) {
    const container = document.getElementById('drivers-list');

    if (!drivers || drivers.length === 0) {
        container.innerHTML = '<p class="placeholder">No drivers configured. Add a driver to get started.</p>';
        return;
    }

    container.innerHTML = '';
    drivers.forEach(driver => {
        const driverCard = document.createElement('div');
        driverCard.className = 'driver-card';
        driverCard.innerHTML = `
            <div class="driver-color-indicator" style="background-color: ${driver.color || '#3498db'}"></div>
            <div class="driver-info">
                <strong>${driver.name}</strong>
                <small>${driver.working_hours_start} - ${driver.working_hours_end}</small>
                <small>Max: ${driver.max_customers_per_day} customers/day</small>
            </div>
            <button class="context-menu-btn" onclick="toggleContextMenu(event, 'driver-${driver.id}')">⋮</button>
            <div id="menu-driver-${driver.id}" class="context-menu">
                <button onclick="showEditDriverForm('${driver.id}'); closeAllContextMenus();">Edit</button>
                <button onclick="deleteDriver('${driver.id}'); closeAllContextMenus();" class="delete">Delete</button>
            </div>
        `;
        container.appendChild(driverCard);
    });
}

function createColorPickerButton(selectedColor = '#3498db', inputId = 'driver-color') {
    return `
        <button type="button" class="color-picker-button-square" id="${inputId}-button" style="background-color: ${selectedColor};" title="Click to change color">
        </button>
        <input type="hidden" id="${inputId}" value="${selectedColor}">
    `;
}

function openColorPickerModal(inputId) {
    const currentColor = document.getElementById(inputId).value;

    const colorsHtml = DRIVER_COLORS.map(color => `
        <div class="color-tile-modal ${color === currentColor ? 'selected' : ''}"
             data-color="${color}"
             style="background-color: ${color};"
             onclick="selectColor('${color}', '${inputId}')">
        </div>
    `).join('');

    const modalHtml = `
        <div class="modal-overlay" onclick="closeColorPickerModal()">
            <div class="color-picker-modal" onclick="event.stopPropagation()">
                <h3>Select Color</h3>
                <div class="color-grid">
                    ${colorsHtml}
                </div>
                <button class="btn-secondary" onclick="closeColorPickerModal()">Cancel</button>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeColorPickerModal() {
    const overlay = document.querySelector('.modal-overlay');
    if (overlay) {
        overlay.remove();
    }
}

function selectColor(color, inputId) {
    document.getElementById(inputId).value = color;
    document.getElementById(`${inputId}-button`).style.backgroundColor = color;
    closeColorPickerModal();
}

function showAddDriverForm() {
    const container = document.getElementById('drivers-list');

    const formHtml = `
        <div class="driver-form-header">
            <h3>Add New Team Member</h3>
            <div class="form-actions">
                <button class="btn-primary" onclick="saveDriver()">Save Team Member</button>
                <button class="btn-secondary" onclick="loadDrivers()">Cancel</button>
            </div>
        </div>
        <div class="driver-form">
            <div class="form-section">
                <h4>Basic Information</h4>
                <div class="form-row">
                    <div class="control-group control-group-large">
                        <label>Name:</label>
                        <input type="text" id="driver-name" placeholder="Team Member Name">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>Color:</label>
                        ${createColorPickerButton('#3498db', 'driver-color')}
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Start Location</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="driver-start-street" placeholder="123 Main Street">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="driver-start-city" placeholder="Sacramento">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="driver-start-state" placeholder="CA" maxlength="2">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="driver-start-zip" placeholder="95814" maxlength="10">
                    </div>
                </div>
                <input type="hidden" id="driver-start-location">
            </div>

            <div class="form-section">
                <h4>End Location</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="driver-end-street" placeholder="123 Main Street">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="driver-end-city" placeholder="Sacramento">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="driver-end-state" placeholder="CA" maxlength="2">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="driver-end-zip" placeholder="95814" maxlength="10">
                    </div>
                </div>
                <input type="hidden" id="driver-end-location">
            </div>

            <div class="form-section">
                <h4>Working Hours & Capacity</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Start Time:</label>
                        <input type="time" id="driver-start-time" value="08:00">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>End Time:</label>
                        <input type="time" id="driver-end-time" value="17:00">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Max Customers/Day:</label>
                        <input type="number" id="driver-max-customers" min="1" max="50" value="20">
                    </div>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = formHtml;

    // Hide add driver button during add form
    const addBtn = document.getElementById('add-driver-btn');
    if (addBtn) addBtn.style.display = 'none';

    // Initialize color picker button
    const colorButton = document.getElementById('driver-color-button');
    if (colorButton) {
        colorButton.addEventListener('click', () => openColorPickerModal('driver-color'));
    }

    // Initialize autocomplete on street address fields
    setTimeout(() => {
        const startStreetInput = document.getElementById('driver-start-street');
        const endStreetInput = document.getElementById('driver-end-street');
        if (startStreetInput) initAutocomplete(startStreetInput);
        if (endStreetInput) initAutocomplete(endStreetInput);
    }, 100);
}

function combineAddressFields(street, city, state, zip) {
    const parts = [street, city, state, zip].filter(p => p && p.trim());
    return parts.join(', ');
}

function parseAddress(fullAddress) {
    if (!fullAddress) return { street: '', city: '', state: '', zip: '' };

    const parts = fullAddress.split(',').map(p => p.trim());

    if (parts.length >= 3) {
        const lastPart = parts[parts.length - 1];
        const zipMatch = lastPart.match(/\b(\d{5}(-\d{4})?)\b/);
        const stateMatch = lastPart.match(/\b([A-Z]{2})\b/);

        return {
            street: parts[0] || '',
            city: parts[1] || '',
            state: stateMatch ? stateMatch[1] : '',
            zip: zipMatch ? zipMatch[1] : ''
        };
    }

    return { street: fullAddress, city: '', state: '', zip: '' };
}

// Removed old initColorSelector function - now using modal color picker

async function saveDriver() {
    const name = document.getElementById('driver-name').value;
    const color = document.getElementById('driver-color').value;

    const startStreet = document.getElementById('driver-start-street').value;
    const startCity = document.getElementById('driver-start-city').value;
    const startState = document.getElementById('driver-start-state').value;
    const startZip = document.getElementById('driver-start-zip').value;
    const startLocation = combineAddressFields(startStreet, startCity, startState, startZip);

    const endStreet = document.getElementById('driver-end-street').value;
    const endCity = document.getElementById('driver-end-city').value;
    const endState = document.getElementById('driver-end-state').value;
    const endZip = document.getElementById('driver-end-zip').value;
    const endLocation = combineAddressFields(endStreet, endCity, endState, endZip);

    const startTime = document.getElementById('driver-start-time').value;
    const endTime = document.getElementById('driver-end-time').value;
    const maxCustomers = parseInt(document.getElementById('driver-max-customers').value);

    if (!name || !startLocation || !endLocation) {
        alert('Please fill in all required fields');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/drivers/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                color: color,
                start_location_address: startLocation,
                end_location_address: endLocation,
                working_hours_start: startTime + ':00',
                working_hours_end: endTime + ':00',
                max_customers_per_day: maxCustomers
            })
        });

        if (!response.ok) {
            throw new Error('Failed to create driver');
        }

        alert('Driver created successfully!');
        loadDrivers();
    } catch (error) {
        console.error('Error creating driver:', error);
        alert('Failed to create driver. Please try again.');
    }
}

async function deleteDriver(driverId) {
    if (!confirm('Are you sure you want to delete this driver?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/drivers/${driverId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete driver');
        }

        loadDrivers();
    } catch (error) {
        console.error('Error deleting driver:', error);
        alert('Failed to delete driver. Please try again.');
    }
}

async function showEditDriverForm(driverId) {
    const container = document.getElementById('drivers-list');

    // Fetch driver data
    try {
        const response = await fetch(`${API_BASE}/api/drivers/${driverId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch driver');
        }

        const driver = await response.json();

        const startAddr = parseAddress(driver.start_location_address || '');
        const endAddr = parseAddress(driver.end_location_address || '');

        const formHtml = `
            <div class="driver-form-header">
                <h3>Edit Team Member</h3>
                <div class="form-actions">
                    <button class="btn-primary" onclick="updateDriver('${driverId}')">Update Team Member</button>
                    <button class="btn-secondary" onclick="loadDrivers()">Cancel</button>
                </div>
            </div>
            <div class="driver-form">
                <div class="form-section">
                    <h4>Basic Information</h4>
                    <div class="form-row">
                        <div class="control-group control-group-large">
                            <label>Name:</label>
                            <input type="text" id="edit-driver-name" value="${driver.name}">
                        </div>
                        <div class="control-group control-group-narrow">
                            <label>Color:</label>
                            ${createColorPickerButton(driver.color || '#3498db', 'edit-driver-color')}
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h4>Start Location</h4>
                    <div class="form-row">
                        <div class="control-group" style="flex: 3;">
                            <label>Street:</label>
                            <input type="text" id="edit-driver-start-street" value="${startAddr.street}" placeholder="123 Main Street">
                        </div>
                        <div class="control-group" style="flex: 2;">
                            <label>City:</label>
                            <input type="text" id="edit-driver-start-city" value="${startAddr.city}" placeholder="Sacramento">
                        </div>
                        <div class="control-group control-group-narrow">
                            <label>State:</label>
                            <input type="text" id="edit-driver-start-state" value="${startAddr.state}" placeholder="CA" maxlength="2">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Zip:</label>
                            <input type="text" id="edit-driver-start-zip" value="${startAddr.zip}" placeholder="95814" maxlength="10">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h4>End Location</h4>
                    <div class="form-row">
                        <div class="control-group" style="flex: 3;">
                            <label>Street:</label>
                            <input type="text" id="edit-driver-end-street" value="${endAddr.street}" placeholder="123 Main Street">
                        </div>
                        <div class="control-group" style="flex: 2;">
                            <label>City:</label>
                            <input type="text" id="edit-driver-end-city" value="${endAddr.city}" placeholder="Sacramento">
                        </div>
                        <div class="control-group control-group-narrow">
                            <label>State:</label>
                            <input type="text" id="edit-driver-end-state" value="${endAddr.state}" placeholder="CA" maxlength="2">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Zip:</label>
                            <input type="text" id="edit-driver-end-zip" value="${endAddr.zip}" placeholder="95814" maxlength="10">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h4>Working Hours & Capacity</h4>
                    <div class="form-row">
                        <div class="control-group control-group-medium">
                            <label>Start Time:</label>
                            <input type="time" id="edit-driver-start-time" value="${driver.working_hours_start ? driver.working_hours_start.substring(0, 5) : '08:00'}">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>End Time:</label>
                            <input type="time" id="edit-driver-end-time" value="${driver.working_hours_end ? driver.working_hours_end.substring(0, 5) : '17:00'}">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Max Customers/Day:</label>
                            <input type="number" id="edit-driver-max-customers" min="1" max="50" value="${driver.max_customers_per_day || 20}">
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = formHtml;

        // Hide add driver button during edit
        const addBtn = document.getElementById('add-driver-btn');
        if (addBtn) addBtn.style.display = 'none';

        // Initialize color picker button
        const colorButton = document.getElementById('edit-driver-color-button');
        if (colorButton) {
            colorButton.addEventListener('click', () => openColorPickerModal('edit-driver-color'));
        }

        // Initialize autocomplete on street address fields
        setTimeout(() => {
            const startStreetInput = document.getElementById('edit-driver-start-street');
            const endStreetInput = document.getElementById('edit-driver-end-street');
            if (startStreetInput) initAutocomplete(startStreetInput);
            if (endStreetInput) initAutocomplete(endStreetInput);
        }, 100);

    } catch (error) {
        console.error('Error loading driver for edit:', error);
        alert('Failed to load driver data. Please try again.');
    }
}

async function updateDriver(driverId) {
    const name = document.getElementById('edit-driver-name').value;
    const color = document.getElementById('edit-driver-color').value;

    const startStreet = document.getElementById('edit-driver-start-street').value;
    const startCity = document.getElementById('edit-driver-start-city').value;
    const startState = document.getElementById('edit-driver-start-state').value;
    const startZip = document.getElementById('edit-driver-start-zip').value;
    const startLocation = combineAddressFields(startStreet, startCity, startState, startZip);

    const endStreet = document.getElementById('edit-driver-end-street').value;
    const endCity = document.getElementById('edit-driver-end-city').value;
    const endState = document.getElementById('edit-driver-end-state').value;
    const endZip = document.getElementById('edit-driver-end-zip').value;
    const endLocation = combineAddressFields(endStreet, endCity, endState, endZip);

    const startTime = document.getElementById('edit-driver-start-time').value;
    const endTime = document.getElementById('edit-driver-end-time').value;
    const maxCustomers = parseInt(document.getElementById('edit-driver-max-customers').value);

    if (!name || !startLocation || !endLocation) {
        alert('Please fill in all required fields');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/drivers/${driverId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                color: color,
                start_location_address: startLocation,
                end_location_address: endLocation,
                working_hours_start: startTime + ':00',
                working_hours_end: endTime + ':00',
                max_customers_per_day: maxCustomers
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update driver');
        }

        alert('Driver updated successfully!');
        loadDrivers();
    } catch (error) {
        console.error('Error updating driver:', error);
        alert('Failed to update driver. Please try again.');
    }
}

// Customer Management Functions

let allCustomers = []; // Store all customers for filtering
let currentFilters = {
    serviceDay: '',
    assignedTech: '',
    serviceType: ''
};

async function loadCustomersManagement() {
    try {
        console.log('Loading customers for management view...');
        // Always load ALL customers for the clients management view (no day filtering)
        let url = `${API_BASE}/api/customers?page_size=100`;

        const response = await fetch(url);
        if (!response.ok) {
            console.error('Failed to load customers');
            return;
        }

        const data = await response.json();
        console.log('Loaded customers:', data.customers?.length);
        allCustomers = data.customers;
        applyClientFilters();

        // Show add customer button
        const addBtn = document.getElementById('add-customer-btn');
        if (addBtn) addBtn.style.display = '';
    } catch (error) {
        console.error('Error loading customers:', error);
        document.getElementById('customers-list').innerHTML = '<p class="placeholder">Failed to load customers</p>';
    }
}

function applyClientFilters() {
    const searchTerm = document.getElementById('clients-search')?.value.toLowerCase() || '';

    let filtered = allCustomers.filter(customer => {
        // Search filter
        const matchesSearch = !searchTerm ||
            customer.display_name.toLowerCase().includes(searchTerm) ||
            customer.address.toLowerCase().includes(searchTerm);

        // Service day filter
        const matchesServiceDay = !currentFilters.serviceDay ||
            customer.service_day === currentFilters.serviceDay ||
            (customer.service_schedule && customer.service_schedule.includes(currentFilters.serviceDay.substring(0, 2).toUpperCase()));

        // Assigned tech filter
        const matchesAssignedTech = !currentFilters.assignedTech ||
            customer.assigned_driver_id === currentFilters.assignedTech;

        // Service type filter
        const matchesServiceType = !currentFilters.serviceType ||
            customer.service_type === currentFilters.serviceType;

        return matchesSearch && matchesServiceDay && matchesAssignedTech && matchesServiceType;
    });

    displayCustomersManagement(filtered);
}

function initClientSearch() {
    const searchInput = document.getElementById('clients-search');
    if (searchInput) {
        searchInput.addEventListener('input', applyClientFilters);
    }
}

function initClientFilter() {
    const filterBtn = document.getElementById('clients-filter-btn');
    const filterModal = document.getElementById('clients-filter-modal');
    const applyBtn = document.getElementById('apply-filter-btn');
    const clearBtn = document.getElementById('clear-filter-btn');

    if (filterBtn) {
        filterBtn.addEventListener('click', async () => {
            // Populate tech dropdown
            const techSelect = document.getElementById('filter-assigned-tech');
            try {
                const response = await fetch(`${API_BASE}/api/drivers/`);
                if (response.ok) {
                    const data = await response.json();
                    const options = data.drivers.map(driver =>
                        `<option value="${driver.id}" ${currentFilters.assignedTech === driver.id ? 'selected' : ''}>${driver.name}</option>`
                    ).join('');
                    techSelect.innerHTML = '<option value="">All Techs</option>' + options;
                }
            } catch (error) {
                console.error('Error loading drivers:', error);
            }

            // Set current filter values
            document.getElementById('filter-service-day').value = currentFilters.serviceDay;
            document.getElementById('filter-service-type').value = currentFilters.serviceType;

            filterModal.classList.add('active');
        });
    }

    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            currentFilters.serviceDay = document.getElementById('filter-service-day').value;
            currentFilters.assignedTech = document.getElementById('filter-assigned-tech').value;
            currentFilters.serviceType = document.getElementById('filter-service-type').value;
            applyClientFilters();
            filterModal.classList.remove('active');
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            currentFilters = { serviceDay: '', assignedTech: '', serviceType: '' };
            document.getElementById('filter-service-day').value = '';
            document.getElementById('filter-assigned-tech').value = '';
            document.getElementById('filter-service-type').value = '';
            applyClientFilters();
            filterModal.classList.remove('active');
        });
    }

    // Close modal on X button
    filterModal?.querySelector('.modal-close')?.addEventListener('click', () => {
        filterModal.classList.remove('active');
    });
}

function initBulkEditModal() {
    const bulkEditModal = document.getElementById('bulk-edit-modal');
    const saveBtn = document.getElementById('save-bulk-changes-btn');

    // Close modal on X button
    bulkEditModal?.querySelector('.modal-close')?.addEventListener('click', () => {
        bulkEditModal.classList.remove('active');
    });

    // Close modal when clicking outside
    bulkEditModal?.addEventListener('click', (e) => {
        if (e.target === bulkEditModal) {
            bulkEditModal.classList.remove('active');
        }
    });

    // Save changes button
    if (saveBtn) {
        saveBtn.addEventListener('click', saveBulkEditChanges);
    }

    // CSV Import button
    document.getElementById('import-csv-btn')?.addEventListener('click', () => {
        document.getElementById('csv-file-input').click();
    });

    // Handle CSV file selection
    document.getElementById('csv-file-input')?.addEventListener('change', handleCSVImport);

    // Download template button
    document.getElementById('download-template-btn')?.addEventListener('click', downloadCSVTemplate);

    // Export CSV button
    document.getElementById('export-csv-btn')?.addEventListener('click', exportCustomersCSV);
}

async function handleCSVImport(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE}/api/customers/import-csv`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to import CSV');
        }

        const result = await response.json();
        alert(`Successfully imported ${result.imported || 0} customers`);

        // Reload customers
        await showBulkEditCustomers(); // Refresh the bulk edit table
        loadCustomersManagement(); // Refresh the sidebar
        loadCustomers(); // Refresh the map
    } catch (error) {
        console.error('CSV import error:', error);
        alert(`Failed to import CSV: ${error.message}`);
    } finally {
        // Clear the file input
        event.target.value = '';
    }
}

function downloadCSVTemplate() {
    const headers = ['Name', 'Street Address', 'City', 'State', 'ZIP', 'Service Type', 'Service Day', 'Days Per Week', 'Duration (min)', 'Difficulty', 'Locked'];
    const sampleRow = ['John\'s Pool', '123 Main St', 'Springfield', 'IL', '62701', 'residential', 'monday', '1', '15', '1', 'false'];

    const csvContent = [
        headers.join(','),
        sampleRow.join(',')
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'customers_template.csv';
    a.click();
    window.URL.revokeObjectURL(url);
}

async function exportCustomersCSV() {
    try {
        const response = await fetch(`${API_BASE}/api/customers/export-csv`);
        if (!response.ok) {
            throw new Error('Failed to export CSV');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `customers_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('CSV export error:', error);
        alert('Failed to export CSV. Please try again.');
    }
}

function displayCustomersManagement(customers) {
    const container = document.getElementById('customers-list');

    if (!customers || customers.length === 0) {
        container.innerHTML = '<p class="placeholder">No customers found. Add a customer to get started.</p>';
        return;
    }

    container.innerHTML = '';
    customers.forEach(customer => {
        const listItem = document.createElement('div');
        listItem.className = 'client-list-item';
        listItem.dataset.customerId = customer.id;

        // Parse address to get street only
        // Format is typically: "Street, City, State Zip"
        const addressParts = customer.address.split(',');
        const street = addressParts.length >= 1 ? addressParts[0].trim() : customer.address;

        listItem.innerHTML = `
            <div class="client-list-item-name">${customer.display_name}</div>
            <div class="client-list-item-address">${street}</div>
        `;

        // Add click handler to select client and show details
        listItem.addEventListener('click', () => {
            // Remove active class from all items
            container.querySelectorAll('.client-list-item').forEach(item => {
                item.classList.remove('active');
            });

            // Add active class to clicked item
            listItem.classList.add('active');

            // Display client details in the detail panel
            displayClientProfile(customer);
        });

        container.appendChild(listItem);
    });
}

function displayClientProfile(customer) {
    const profileTab = document.getElementById('tab-profile');

    // Parse address parts
    const addressParts = customer.address.split(',');
    const street = addressParts.length >= 1 ? addressParts[0].trim() : '';
    const city = addressParts.length >= 2 ? addressParts[1].trim() : '';
    const stateZip = addressParts.length >= 3 ? addressParts.slice(2).join(',').trim() : '';

    // Format service day/schedule
    let scheduleDisplay;
    if (customer.service_schedule) {
        scheduleDisplay = customer.service_schedule;
    } else if (customer.service_day) {
        const dayNames = {
            'monday': 'Monday',
            'tuesday': 'Tuesday',
            'wednesday': 'Wednesday',
            'thursday': 'Thursday',
            'friday': 'Friday',
            'saturday': 'Saturday',
            'sunday': 'Sunday'
        };
        scheduleDisplay = dayNames[customer.service_day] || customer.service_day;
    } else {
        scheduleDisplay = 'Not set';
    }

    // Get driver name
    const driverName = customer.assigned_driver ? customer.assigned_driver.name : 'Not assigned';

    // Check coordinate status
    const hasValidCoordinates = customer.latitude && customer.longitude &&
        customer.latitude >= -90 && customer.latitude <= 90 &&
        customer.longitude >= -180 && customer.longitude <= 180;

    const coordinateStatus = hasValidCoordinates
        ? `<span style="color: #2ecc71;">✓ Valid</span>`
        : `<span style="color: #e74c3c;">⚠ Invalid or missing</span>`;

    // Service type icon
    const serviceIcon = customer.service_type === 'residential'
        ? '<i class="fas fa-home" style="color: #3498db; margin-left: 1rem;" title="Residential"></i>'
        : '<i class="fas fa-building" style="color: #9b59b6; margin-left: 1rem;" title="Commercial"></i>';

    profileTab.innerHTML = `
        <div style="max-width: 600px;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 2rem;">
                <h2 style="color: var(--primary-dark); margin: 0; display: flex; align-items: center;">
                    ${customer.display_name}
                    ${serviceIcon}
                </h2>
                <div style="display: flex; gap: 0.5rem;">
                    <button class="btn-primary" onclick="editCustomer('${customer.id}')">Edit</button>
                    <button class="btn-secondary" onclick="if(confirm('Delete ${customer.display_name}?')) deleteCustomer('${customer.id}')">Delete</button>
                </div>
            </div>

            <div style="display: grid; gap: 1.5rem;">
                <div>
                    <h3 style="color: var(--primary-dark); font-size: 1rem; margin-bottom: 0.5rem;">Address</h3>
                    <div style="color: var(--text-color);">
                        ${street}<br>
                        ${city}${stateZip ? ', ' + stateZip : ''}
                    </div>
                </div>

                <div>
                    <h3 style="color: var(--primary-dark); font-size: 1rem; margin-bottom: 0.5rem;">Service Schedule</h3>
                    <div style="color: var(--text-color);">${scheduleDisplay}</div>
                </div>

                <div>
                    <h3 style="color: var(--primary-dark); font-size: 1rem; margin-bottom: 0.5rem;">Assigned Driver</h3>
                    <div style="color: var(--text-color);">${driverName}</div>
                </div>

                <div>
                    <h3 style="color: var(--primary-dark); font-size: 1rem; margin-bottom: 0.5rem;">Coordinates</h3>
                    <div style="color: var(--text-color);">
                        ${hasValidCoordinates
                            ? `${customer.latitude.toFixed(6)}, ${customer.longitude.toFixed(6)}`
                            : 'Not available'}
                        ${coordinateStatus}
                    </div>
                    ${!hasValidCoordinates
                        ? `<button class="btn-secondary" style="margin-top: 0.5rem;" onclick="regeocodeCustomer('${customer.id}')">Get Coordinates</button>`
                        : ''}
                </div>
            </div>
        </div>
    `;
}

async function showAddCustomerForm() {
    const container = document.getElementById('customers-list');

    // Fetch drivers for the dropdown
    let driversOptions = '<option value="">None</option>';
    try {
        const driversResponse = await fetch(`${API_BASE}/api/drivers/`);
        if (driversResponse.ok) {
            const driversData = await driversResponse.json();
            driversOptions += driversData.drivers.map(driver =>
                `<option value="${driver.id}">${driver.name}</option>`
            ).join('');
        }
    } catch (error) {
        console.error('Error loading drivers:', error);
    }

    // Fetch management companies for the datalist
    let managementCompaniesOptions = '';
    try {
        const companiesResponse = await fetch(`${API_BASE}/api/customers/management-companies`);
        if (companiesResponse.ok) {
            const companies = await companiesResponse.json();
            managementCompaniesOptions = companies.map(company =>
                `<option value="${company}">`
            ).join('');
        }
    } catch (error) {
        console.error('Error loading management companies:', error);
    }

    const formHtml = `
        <div class="customer-form-header">
            <h3>Add New Customer</h3>
            <div class="form-actions">
                <button class="btn-primary" onclick="saveCustomer()">Save Customer</button>
                <button class="btn-secondary" onclick="loadCustomersManagement()">Cancel</button>
            </div>
        </div>
        <div class="customer-form">
            <div class="form-section">
                <h4>Basic Information</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Service Type:</label>
                        <select id="customer-service-type" onchange="toggleAddNameFields()">
                            <option value="residential">Residential</option>
                            <option value="commercial">Commercial</option>
                        </select>
                    </div>
                </div>
                <div class="form-row" id="add-residential-name-fields">
                    <div class="control-group control-group-medium">
                        <label>First Name:</label>
                        <input type="text" id="customer-first-name" placeholder="John">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Last Name:</label>
                        <input type="text" id="customer-last-name" placeholder="Doe">
                    </div>
                </div>
                <div class="form-row" id="add-commercial-name-field" style="display: none;">
                    <div class="control-group control-group-large">
                        <label>Business Name:</label>
                        <input type="text" id="customer-name" placeholder="ABC Pool Service">
                    </div>
                </div>
                <div class="form-row" id="add-commercial-management-field" style="display: none;">
                    <div class="control-group control-group-large">
                        <label>Management Company:</label>
                        <input type="text" id="customer-management-company" list="management-companies" placeholder="Enter or select management company">
                        <datalist id="management-companies">
                            ${managementCompaniesOptions}
                        </datalist>
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Contact Information</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Email:</label>
                        <input type="email" id="customer-email" placeholder="email@example.com">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Phone:</label>
                        <input type="tel" id="customer-phone" placeholder="(555) 123-4567">
                    </div>
                </div>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Alt Email:</label>
                        <input type="email" id="customer-alt-email" placeholder="alt@example.com">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Alt Phone:</label>
                        <input type="tel" id="customer-alt-phone" placeholder="(555) 987-6543">
                    </div>
                </div>
                <div class="form-row" id="add-commercial-invoice-email-field" style="display: none;">
                    <div class="control-group control-group-large">
                        <label>Invoice Email:</label>
                        <input type="email" id="customer-invoice-email" placeholder="invoices@example.com">
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Address</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="customer-street" placeholder="123 Main Street">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="customer-city" placeholder="Sacramento">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="customer-state" placeholder="CA" maxlength="2">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="customer-zip" placeholder="95814" maxlength="10">
                    </div>
                </div>
                <input type="hidden" id="customer-address">
            </div>

            <div class="form-section">
                <h4>Service Schedule</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Days Per Week:</label>
                        <select id="customer-days-per-week" onchange="updateAddServiceDayOptions()">
                            <option value="1" selected>1 day</option>
                            <option value="2">2 days</option>
                            <option value="3">3 days</option>
                        </select>
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Service Day:</label>
                        <select id="customer-service-day">
                        </select>
                    </div>
                    <div class="control-group">
                        <label>
                            <input type="checkbox" id="customer-locked">
                            Lock service day
                        </label>
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Assignment & Difficulty</h4>
                <div class="form-row">
                    <div class="control-group control-group-large">
                        <label>Assigned Tech:</label>
                        <select id="customer-assigned-driver">
                            ${driversOptions}
                        </select>
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Duration (minutes):</label>
                        <input type="number" id="customer-visit-duration" min="5" max="120" value="15">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>Difficulty:</label>
                        <input type="number" id="customer-difficulty" min="1" max="5" value="1">
                    </div>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = formHtml;

    // Initialize autocomplete on street field
    setTimeout(() => {
        const streetInput = document.getElementById('customer-street');
        if (streetInput) initAutocomplete(streetInput);

        // Initialize service day options (defaults to 1 day)
        updateAddServiceDayOptions();
    }, 100);

    // Hide add customer button
    const addBtn = document.getElementById('add-customer-btn');
    if (addBtn) addBtn.style.display = 'none';
}

function updateAddServiceDayOptions() {
    const daysPerWeek = parseInt(document.getElementById('customer-days-per-week').value);
    const serviceDaySelect = document.getElementById('customer-service-day');

    if (daysPerWeek === 1) {
        // Single day - show all weekdays
        serviceDaySelect.innerHTML = `
            <option value="monday">Monday</option>
            <option value="tuesday">Tuesday</option>
            <option value="wednesday">Wednesday</option>
            <option value="thursday">Thursday</option>
            <option value="friday">Friday</option>
            <option value="saturday">Saturday</option>
        `;
        serviceDaySelect.disabled = false;
    } else if (daysPerWeek === 2) {
        // Two days - show Mo/Th and Tu/Fr
        serviceDaySelect.innerHTML = `
            <option value="Mo/Th">Mo/Th</option>
            <option value="Tu/Fr">Tu/Fr</option>
        `;
        serviceDaySelect.disabled = false;
    } else if (daysPerWeek === 3) {
        // Three days - only Mo/We/Fr, disabled
        serviceDaySelect.innerHTML = `
            <option value="Mo/We/Fr">Mo/We/Fr</option>
        `;
        serviceDaySelect.disabled = true;
    }
}

async function saveCustomer() {
    const serviceType = document.getElementById('customer-service-type').value;

    // Get name fields based on service type
    let name = null;
    let firstName = null;
    let lastName = null;

    if (serviceType === 'residential') {
        firstName = document.getElementById('customer-first-name').value;
        lastName = document.getElementById('customer-last-name').value;
        if (!firstName || !lastName) {
            alert('Please fill in first and last name');
            return;
        }
    } else {
        name = document.getElementById('customer-name').value;
        if (!name) {
            alert('Please fill in business name');
            return;
        }
    }

    const street = document.getElementById('customer-street').value;
    const city = document.getElementById('customer-city').value;
    const state = document.getElementById('customer-state').value;
    const zip = document.getElementById('customer-zip').value;
    const address = combineAddressFields(street, city, state, zip);

    const assignedDriverId = document.getElementById('customer-assigned-driver').value || null;
    const serviceDayValue = document.getElementById('customer-service-day').value;
    const daysPerWeek = parseInt(document.getElementById('customer-days-per-week').value);
    const difficulty = parseInt(document.getElementById('customer-difficulty').value);
    const visitDuration = parseInt(document.getElementById('customer-visit-duration').value);
    const locked = document.getElementById('customer-locked').checked;

    if (!address) {
        alert('Please fill in all required fields');
        return;
    }

    // Determine service_day and service_schedule based on daysPerWeek
    let serviceDay;
    let schedule;

    if (daysPerWeek === 1) {
        // Single day - value is the day name
        serviceDay = serviceDayValue;
        schedule = null;
    } else if (daysPerWeek === 2) {
        // Two days - value is schedule like "Mo/Th" or "Tu/Fr"
        schedule = serviceDayValue;
        // Extract primary day from schedule
        if (serviceDayValue === 'Mo/Th') {
            serviceDay = 'monday';
        } else if (serviceDayValue === 'Tu/Fr') {
            serviceDay = 'tuesday';
        }
    } else if (daysPerWeek === 3) {
        // Three days - always Mo/We/Fr
        serviceDay = 'monday';
        schedule = 'Mo/We/Fr';
    }

    // Capture contact and management fields
    const email = document.getElementById('customer-email').value || null;
    const phone = document.getElementById('customer-phone').value || null;
    const altEmail = document.getElementById('customer-alt-email').value || null;
    const altPhone = document.getElementById('customer-alt-phone').value || null;
    const invoiceEmail = document.getElementById('customer-invoice-email').value || null;
    const managementCompany = document.getElementById('customer-management-company').value || null;

    try {
        const response = await fetch(`${API_BASE}/api/customers/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                first_name: firstName,
                last_name: lastName,
                address: address,
                email: email,
                phone: phone,
                alt_email: altEmail,
                alt_phone: altPhone,
                invoice_email: invoiceEmail,
                management_company: managementCompany,
                assigned_driver_id: assignedDriverId,
                service_day: serviceDay,
                service_type: serviceType,
                service_days_per_week: daysPerWeek,
                service_schedule: schedule,
                difficulty: difficulty,
                visit_duration: visitDuration,
                locked: locked
            })
        });

        if (!response.ok) {
            throw new Error('Failed to create customer');
        }

        alert('Customer created successfully!');
        loadCustomersManagement();
        loadCustomers(); // Reload map
    } catch (error) {
        console.error('Error creating customer:', error);
        alert('Failed to create customer. Please try again.');
    }
}

async function editCustomer(customerId) {
    try {
        // Fetch customer details
        const response = await fetch(`${API_BASE}/api/customers/${customerId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch customer');
        }

        const customer = await response.json();
        showEditCustomerForm(customer);
    } catch (error) {
        console.error('Error fetching customer:', error);
        alert('Failed to load customer. Please try again.');
    }
}

async function showEditCustomerForm(customer) {
    const container = document.getElementById('tab-profile');

    // Fetch drivers for the dropdown
    let driversOptions = '<option value="">None</option>';
    try {
        const driversResponse = await fetch(`${API_BASE}/api/drivers/`);
        if (driversResponse.ok) {
            const driversData = await driversResponse.json();
            driversOptions += driversData.drivers.map(driver =>
                `<option value="${driver.id}" ${customer.assigned_driver_id === driver.id ? 'selected' : ''}>${driver.name}</option>`
            ).join('');
        }
    } catch (error) {
        console.error('Error loading drivers:', error);
    }

    // Fetch management companies for the datalist
    let managementCompaniesOptions = '';
    try {
        const companiesResponse = await fetch(`${API_BASE}/api/customers/management-companies`);
        if (companiesResponse.ok) {
            const companies = await companiesResponse.json();
            managementCompaniesOptions = companies.map(company =>
                `<option value="${company}">`
            ).join('');
        }
    } catch (error) {
        console.error('Error loading management companies:', error);
    }

    const addr = parseAddress(customer.address || '');

    const formHtml = `
        <div class="customer-form-header">
            <div style="display: flex; align-items: center; gap: 2rem;">
                <h3>Edit Client</h3>
                <div class="control-group" style="margin-bottom: 0;">
                    <select id="edit-customer-service-type" onchange="toggleNameFields(); detectFormChanges();">
                        <option value="residential" ${customer.service_type === 'residential' ? 'selected' : ''}>Residential</option>
                        <option value="commercial" ${customer.service_type === 'commercial' ? 'selected' : ''}>Commercial</option>
                    </select>
                </div>
            </div>
            <div class="form-actions">
                <button id="update-customer-btn" class="btn-primary" onclick="updateCustomer('${customer.id}')" disabled>Update</button>
                <button class="btn-secondary" onclick="cancelEditCustomer('${customer.id}')">Cancel</button>
            </div>
        </div>
        <div class="customer-form">
            <div class="form-section">
                <h4>Name</h4>
                <div class="form-row" id="residential-name-fields" style="display: ${customer.service_type === 'residential' ? 'flex' : 'none'};">
                    <div class="control-group" style="flex: 1;">
                        <label>Last Name:</label>
                        <input type="text" id="edit-customer-last-name" value="${customer.last_name || ''}" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>First Name:</label>
                        <input type="text" id="edit-customer-first-name" value="${customer.first_name || ''}" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" id="commercial-name-field" style="display: ${customer.service_type === 'commercial' ? 'flex' : 'none'};">
                    <div class="control-group" style="flex: 1;">
                        <label>Business Name:</label>
                        <input type="text" id="edit-customer-name" value="${customer.name || ''}" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" style="margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Display Name:</label>
                        <input type="text" id="edit-customer-display-name" value="${customer.display_name || ''}" placeholder="Auto-generated if left blank" oninput="detectFormChanges()">
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Address</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="edit-customer-street" value="${addr.street}" placeholder="123 Main Street" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="edit-customer-city" value="${addr.city}" placeholder="Sacramento" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="edit-customer-state" value="${addr.state}" placeholder="CA" maxlength="2" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="edit-customer-zip" value="${addr.zip}" placeholder="95814" maxlength="10" oninput="detectFormChanges()">
                    </div>
                </div>
            </div>

            <div class="form-section" style="margin-top: 2rem;">
                <h4>Contact</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 1;">
                        <label>Email:</label>
                        <input type="email" id="edit-customer-email" value="${customer.email || ''}" placeholder="email@example.com" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>Phone:</label>
                        <input type="tel" id="edit-customer-phone" value="${customer.phone || ''}" placeholder="(555) 123-4567" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" style="margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Alt Email:</label>
                        <input type="email" id="edit-customer-alt-email" value="${customer.alt_email || ''}" placeholder="alt@example.com" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>Alt Phone:</label>
                        <input type="tel" id="edit-customer-alt-phone" value="${customer.alt_phone || ''}" placeholder="(555) 987-6543" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" id="commercial-invoice-email-field" style="display: ${customer.service_type === 'commercial' ? 'flex' : 'none'}; margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Invoice Email:</label>
                        <input type="email" id="edit-customer-invoice-email" value="${customer.invoice_email || ''}" placeholder="invoices@example.com" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" id="commercial-management-field" style="display: ${customer.service_type === 'commercial' ? 'flex' : 'none'}; margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Management Company:</label>
                        <input type="text" id="edit-customer-management-company" value="${customer.management_company || ''}" list="management-companies-datalist" oninput="detectFormChanges()">
                        <datalist id="management-companies-datalist">
                            ${managementCompaniesOptions}
                        </datalist>
                    </div>
                </div>
            </div>

            <div class="form-section" style="margin-top: 2rem;">
                <h4>Service</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Days Per Week:</label>
                        <select id="edit-customer-days-per-week" onchange="updateServiceDayOptions(); detectFormChanges();">
                            <option value="1" ${customer.service_days_per_week === 1 ? 'selected' : ''}>1 day</option>
                            <option value="2" ${customer.service_days_per_week === 2 ? 'selected' : ''}>2 days</option>
                            <option value="3" ${customer.service_days_per_week === 3 ? 'selected' : ''}>3 days</option>
                        </select>
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>Service Day:</label>
                        <select id="edit-customer-service-day" onchange="detectFormChanges()">
                        </select>
                    </div>
                    <div class="control-group">
                        <label>
                            <input type="checkbox" id="edit-customer-locked" ${customer.locked ? 'checked' : ''} onchange="detectFormChanges()">
                            Lock service day
                        </label>
                    </div>
                </div>
                <div class="form-row" style="margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Assigned Tech:</label>
                        <select id="edit-customer-assigned-driver" onchange="detectFormChanges()">
                            ${driversOptions}
                        </select>
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Duration (minutes):</label>
                        <input type="number" id="edit-customer-visit-duration" min="5" max="120" value="${customer.visit_duration || 15}" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>Difficulty:</label>
                        <input type="number" id="edit-customer-difficulty" min="1" max="5" value="${customer.difficulty}" oninput="detectFormChanges()">
                    </div>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = formHtml;

    // Initialize autocomplete on street field
    setTimeout(() => {
        const streetInput = document.getElementById('edit-customer-street');
        if (streetInput) initAutocomplete(streetInput);

        // Initialize service day options based on current days per week
        updateServiceDayOptions(customer.service_day, customer.service_schedule);

        // Store original form values for change detection
        storeOriginalFormValues();
    }, 100);
}

// Store original form values
let originalFormValues = {};

function storeOriginalFormValues() {
    originalFormValues = {
        serviceType: document.getElementById('edit-customer-service-type')?.value,
        lastName: document.getElementById('edit-customer-last-name')?.value,
        firstName: document.getElementById('edit-customer-first-name')?.value,
        name: document.getElementById('edit-customer-name')?.value,
        displayName: document.getElementById('edit-customer-display-name')?.value,
        street: document.getElementById('edit-customer-street')?.value,
        city: document.getElementById('edit-customer-city')?.value,
        state: document.getElementById('edit-customer-state')?.value,
        zip: document.getElementById('edit-customer-zip')?.value,
        email: document.getElementById('edit-customer-email')?.value,
        phone: document.getElementById('edit-customer-phone')?.value,
        altEmail: document.getElementById('edit-customer-alt-email')?.value,
        altPhone: document.getElementById('edit-customer-alt-phone')?.value,
        invoiceEmail: document.getElementById('edit-customer-invoice-email')?.value,
        managementCompany: document.getElementById('edit-customer-management-company')?.value,
        daysPerWeek: document.getElementById('edit-customer-days-per-week')?.value,
        serviceDay: document.getElementById('edit-customer-service-day')?.value,
        locked: document.getElementById('edit-customer-locked')?.checked,
        assignedDriver: document.getElementById('edit-customer-assigned-driver')?.value,
        visitDuration: document.getElementById('edit-customer-visit-duration')?.value,
        difficulty: document.getElementById('edit-customer-difficulty')?.value
    };
}

function detectFormChanges() {
    const currentValues = {
        serviceType: document.getElementById('edit-customer-service-type')?.value,
        lastName: document.getElementById('edit-customer-last-name')?.value,
        firstName: document.getElementById('edit-customer-first-name')?.value,
        name: document.getElementById('edit-customer-name')?.value,
        displayName: document.getElementById('edit-customer-display-name')?.value,
        street: document.getElementById('edit-customer-street')?.value,
        city: document.getElementById('edit-customer-city')?.value,
        state: document.getElementById('edit-customer-state')?.value,
        zip: document.getElementById('edit-customer-zip')?.value,
        email: document.getElementById('edit-customer-email')?.value,
        phone: document.getElementById('edit-customer-phone')?.value,
        altEmail: document.getElementById('edit-customer-alt-email')?.value,
        altPhone: document.getElementById('edit-customer-alt-phone')?.value,
        invoiceEmail: document.getElementById('edit-customer-invoice-email')?.value,
        managementCompany: document.getElementById('edit-customer-management-company')?.value,
        daysPerWeek: document.getElementById('edit-customer-days-per-week')?.value,
        serviceDay: document.getElementById('edit-customer-service-day')?.value,
        locked: document.getElementById('edit-customer-locked')?.checked,
        assignedDriver: document.getElementById('edit-customer-assigned-driver')?.value,
        visitDuration: document.getElementById('edit-customer-visit-duration')?.value,
        difficulty: document.getElementById('edit-customer-difficulty')?.value
    };

    // Compare current values with original
    let hasChanges = false;
    for (const key in originalFormValues) {
        if (originalFormValues[key] !== currentValues[key]) {
            hasChanges = true;
            break;
        }
    }

    // Enable/disable Update button
    const updateBtn = document.getElementById('update-customer-btn');
    if (updateBtn) {
        updateBtn.disabled = !hasChanges;
    }
}

async function cancelEditCustomer(customerId) {
    // Fetch the customer again and show their profile
    try {
        const response = await fetch(`${API_BASE}/api/customers/${customerId}`);
        if (response.ok) {
            const customer = await response.json();
            displayClientProfile(customer);
        }
    } catch (error) {
        console.error('Error reloading customer profile:', error);
    }
}

function updateServiceDayOptions(currentServiceDay = null, currentSchedule = null) {
    const daysPerWeek = parseInt(document.getElementById('edit-customer-days-per-week').value);
    const serviceDaySelect = document.getElementById('edit-customer-service-day');

    // Determine current selection
    let selectedValue = currentServiceDay;
    if (daysPerWeek > 1 && currentSchedule) {
        selectedValue = currentSchedule;
    }

    if (daysPerWeek === 1) {
        // Single day - show all weekdays
        serviceDaySelect.innerHTML = `
            <option value="monday" ${selectedValue === 'monday' ? 'selected' : ''}>Monday</option>
            <option value="tuesday" ${selectedValue === 'tuesday' ? 'selected' : ''}>Tuesday</option>
            <option value="wednesday" ${selectedValue === 'wednesday' ? 'selected' : ''}>Wednesday</option>
            <option value="thursday" ${selectedValue === 'thursday' ? 'selected' : ''}>Thursday</option>
            <option value="friday" ${selectedValue === 'friday' ? 'selected' : ''}>Friday</option>
            <option value="saturday" ${selectedValue === 'saturday' ? 'selected' : ''}>Saturday</option>
        `;
        serviceDaySelect.disabled = false;
    } else if (daysPerWeek === 2) {
        // Two days - show Mo/Th and Tu/Fr
        serviceDaySelect.innerHTML = `
            <option value="Mo/Th" ${selectedValue === 'Mo/Th' ? 'selected' : ''}>Mo/Th</option>
            <option value="Tu/Fr" ${selectedValue === 'Tu/Fr' ? 'selected' : ''}>Tu/Fr</option>
        `;
        serviceDaySelect.disabled = false;
    } else if (daysPerWeek === 3) {
        // Three days - only Mo/We/Fr, disabled
        serviceDaySelect.innerHTML = `
            <option value="Mo/We/Fr">Mo/We/Fr</option>
        `;
        serviceDaySelect.disabled = true;
    }
}

function toggleNameFields() {
    const serviceType = document.getElementById('edit-customer-service-type').value;
    const residentialFields = document.getElementById('residential-name-fields');
    const commercialField = document.getElementById('commercial-name-field');
    const managementField = document.getElementById('commercial-management-field');
    const invoiceEmailField = document.getElementById('commercial-invoice-email-field');

    if (serviceType === 'residential') {
        residentialFields.style.display = 'flex';
        commercialField.style.display = 'none';
        if (managementField) managementField.style.display = 'none';
        if (invoiceEmailField) invoiceEmailField.style.display = 'none';
    } else {
        residentialFields.style.display = 'none';
        commercialField.style.display = 'flex';
        if (managementField) managementField.style.display = 'flex';
        if (invoiceEmailField) invoiceEmailField.style.display = 'flex';
    }
}

function toggleAddNameFields() {
    const serviceType = document.getElementById('customer-service-type').value;
    const residentialFields = document.getElementById('add-residential-name-fields');
    const commercialField = document.getElementById('add-commercial-name-field');
    const managementField = document.getElementById('add-commercial-management-field');
    const invoiceEmailField = document.getElementById('add-commercial-invoice-email-field');

    if (serviceType === 'residential') {
        residentialFields.style.display = 'flex';
        commercialField.style.display = 'none';
        if (managementField) managementField.style.display = 'none';
        if (invoiceEmailField) invoiceEmailField.style.display = 'none';
    } else {
        residentialFields.style.display = 'none';
        commercialField.style.display = 'flex';
        if (managementField) managementField.style.display = 'flex';
        if (invoiceEmailField) invoiceEmailField.style.display = 'flex';
    }
}

async function updateCustomer(customerId) {
    const serviceType = document.getElementById('edit-customer-service-type').value;

    // Get name fields based on service type
    let name = null;
    let firstName = null;
    let lastName = null;

    if (serviceType === 'residential') {
        firstName = document.getElementById('edit-customer-first-name').value;
        lastName = document.getElementById('edit-customer-last-name').value;
        if (!firstName || !lastName) {
            alert('Please fill in first and last name');
            return;
        }
    } else {
        name = document.getElementById('edit-customer-name').value;
        if (!name) {
            alert('Please fill in business name');
            return;
        }
    }

    const street = document.getElementById('edit-customer-street').value;
    const city = document.getElementById('edit-customer-city').value;
    const state = document.getElementById('edit-customer-state').value;
    const zip = document.getElementById('edit-customer-zip').value;
    const address = combineAddressFields(street, city, state, zip);

    const assignedDriverId = document.getElementById('edit-customer-assigned-driver').value || null;
    const serviceDayValue = document.getElementById('edit-customer-service-day').value;
    const daysPerWeek = parseInt(document.getElementById('edit-customer-days-per-week').value);
    const difficulty = parseInt(document.getElementById('edit-customer-difficulty').value);
    const visitDuration = parseInt(document.getElementById('edit-customer-visit-duration').value);
    const locked = document.getElementById('edit-customer-locked').checked;

    if (!address) {
        alert('Please fill in all required fields');
        return;
    }

    // Determine service_day and service_schedule based on daysPerWeek
    let serviceDay;
    let schedule;

    if (daysPerWeek === 1) {
        // Single day - value is the day name
        serviceDay = serviceDayValue;
        schedule = null;
    } else if (daysPerWeek === 2) {
        // Two days - value is schedule like "Mo/Th" or "Tu/Fr"
        schedule = serviceDayValue;
        // Extract primary day from schedule
        if (serviceDayValue === 'Mo/Th') {
            serviceDay = 'monday';
        } else if (serviceDayValue === 'Tu/Fr') {
            serviceDay = 'tuesday';
        }
    } else if (daysPerWeek === 3) {
        // Three days - always Mo/We/Fr
        serviceDay = 'monday';
        schedule = 'Mo/We/Fr';
    }

    // Capture contact and management fields
    const email = document.getElementById('edit-customer-email').value || null;
    const phone = document.getElementById('edit-customer-phone').value || null;
    const altEmail = document.getElementById('edit-customer-alt-email').value || null;
    const altPhone = document.getElementById('edit-customer-alt-phone').value || null;
    const invoiceEmail = document.getElementById('edit-customer-invoice-email').value || null;
    const managementCompany = document.getElementById('edit-customer-management-company').value || null;
    const displayName = document.getElementById('edit-customer-display-name').value || null;

    try {
        const response = await fetch(`${API_BASE}/api/customers/${customerId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                first_name: firstName,
                last_name: lastName,
                display_name: displayName,
                address: address,
                email: email,
                phone: phone,
                alt_email: altEmail,
                alt_phone: altPhone,
                invoice_email: invoiceEmail,
                management_company: managementCompany,
                assigned_driver_id: assignedDriverId,
                service_day: serviceDay,
                service_type: serviceType,
                service_days_per_week: daysPerWeek,
                service_schedule: schedule,
                difficulty: difficulty,
                visit_duration: visitDuration,
                locked: locked
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update customer');
        }

        const updatedCustomer = await response.json();
        alert('Customer updated successfully!');

        // Reload the customer list in sidebar (in case name changed)
        loadCustomersManagement();
        // Reload map markers
        loadCustomers();
        // Show updated profile in detail panel
        displayClientProfile(updatedCustomer);
    } catch (error) {
        console.error('Error updating customer:', error);
        alert('Failed to update customer. Please try again.');
    }
}

async function deleteCustomer(customerId) {
    if (!confirm('Are you sure you want to delete this customer?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/customers/${customerId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete customer');
        }

        loadCustomersManagement();
        loadCustomers(); // Reload map
    } catch (error) {
        console.error('Error deleting customer:', error);
        alert('Failed to delete customer. Please try again.');
    }
}

async function regeocodeCustomer(customerId) {
    if (!confirm('Re-geocode this customer\'s address? This will update their GPS coordinates.')) {
        return;
    }

    try {
        // Get customer data first
        const customerResponse = await fetch(`${API_BASE}/api/customers/${customerId}`);
        if (!customerResponse.ok) {
            throw new Error('Failed to fetch customer');
        }

        const customer = await customerResponse.json();

        // Call geocoding service
        const geocodeResponse = await fetch(`${API_BASE}/api/geocode?address=${encodeURIComponent(customer.address)}`);
        if (!geocodeResponse.ok) {
            throw new Error('Geocoding service unavailable');
        }

        const geocodeData = await geocodeResponse.json();

        // Check for error in response
        if (geocodeData.error) {
            alert(`Geocoding failed: ${geocodeData.error}\n\nAddress: ${customer.address}\n\nPlease verify the address is complete (street, city, state, ZIP).`);
            return;
        }

        if (!geocodeData.latitude || !geocodeData.longitude) {
            alert(`Could not geocode address: ${customer.address}\n\nPlease ensure the address includes:\n- Street number and name\n- City\n- State\n- ZIP code`);
            return;
        }

        // Update customer with new coordinates
        const updateResponse = await fetch(`${API_BASE}/api/customers/${customerId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                latitude: geocodeData.latitude,
                longitude: geocodeData.longitude
            })
        });

        if (!updateResponse.ok) {
            throw new Error('Failed to update customer coordinates');
        }

        alert('Customer coordinates updated successfully!');
        // Refresh the view - check if we're in validation mode or regular mode
        if (document.getElementById('customers-list').querySelector('.btn-secondary')?.textContent.includes('Back to Customer List')) {
            validateCoordinates(); // Re-run validation to update the list
        } else {
            loadCustomersManagement();
        }
        loadCustomers(); // Reload map
    } catch (error) {
        console.error('Error re-geocoding customer:', error);
        alert('Failed to re-geocode customer. Please try again.');
    }
}

async function validateCoordinates() {
    const button = document.getElementById('validate-coordinates-btn');
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Validating...';

    try {
        const response = await fetch(`${API_BASE}/api/customers/validate-coordinates`);
        if (!response.ok) {
            throw new Error('Validation failed');
        }

        const data = await response.json();

        if (data.error) {
            alert(`Validation error: ${data.error}`);
            return;
        }

        // Display results
        const container = document.getElementById('customers-list');

        if (data.issues_found === 0) {
            container.innerHTML = `
                <div style="background-color: #d4edda; border: 1px solid #28a745; border-radius: 4px; padding: 1rem; margin-bottom: 1rem;">
                    <h3 style="color: #155724; margin: 0 0 0.5rem 0;">✓ All Coordinates Valid</h3>
                    <p style="margin: 0; color: #155724;">All ${data.total_customers} customers have valid coordinates matching their addresses.</p>
                </div>
            `;
            setTimeout(() => loadCustomersManagement(), 3000);
            return;
        }

        let html = `
            <div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 1rem; margin-bottom: 1rem;">
                <h3 style="color: #856404; margin: 0 0 0.5rem 0;">⚠️ Coordinate Issues Found</h3>
                <p style="margin: 0; color: #856404;">Found ${data.issues_found} customers with coordinate issues out of ${data.total_customers} total.</p>
            </div>
        `;

        data.customers_with_issues.forEach(issue => {
            const severityColor = {
                'high': '#dc3545',
                'medium': '#ffc107',
                'low': '#17a2b8'
            }[issue.severity] || '#6c757d';

            html += `
                <div style="border: 1px solid ${severityColor}; border-left: 4px solid ${severityColor}; border-radius: 4px; padding: 0.75rem; margin-bottom: 0.5rem; background-color: #fff;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <strong style="color: #333;">${issue.name}</strong>
                            <div style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;">${issue.address}</div>
                            <div style="font-size: 0.85rem; color: ${severityColor}; margin-top: 0.25rem;">
                                ${issue.issues.join(', ')}
                            </div>
                            ${issue.distance_miles ? `<div style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;">Distance from address: ${issue.distance_miles} miles</div>` : ''}
                        </div>
                        ${issue.correct_latitude ? `
                            <button onclick="fixCustomerCoordinates('${issue.id}', ${issue.correct_latitude}, ${issue.correct_longitude})"
                                    style="background-color: #28a745; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-size: 0.85rem; white-space: nowrap;">
                                Fix Coordinates
                            </button>
                        ` : `
                            <button onclick="regeocodeCustomer('${issue.id}')"
                                    style="background-color: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-size: 0.85rem; white-space: nowrap;">
                                Re-geocode
                            </button>
                        `}
                    </div>
                </div>
            `;
        });

        html += `
            <button onclick="loadCustomersManagement()" class="btn-secondary" style="margin-top: 1rem;">
                Back to Customer List
            </button>
        `;

        container.innerHTML = html;

    } catch (error) {
        console.error('Error validating coordinates:', error);
        alert('Failed to validate coordinates. Please try again.');
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}

async function fixCustomerCoordinates(customerId, latitude, longitude) {
    try {
        const response = await fetch(`${API_BASE}/api/customers/${customerId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                latitude: latitude,
                longitude: longitude
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update coordinates');
        }

        alert('Coordinates updated successfully!');
        validateCoordinates(); // Re-run validation
        loadCustomers(); // Reload map
    } catch (error) {
        console.error('Error fixing coordinates:', error);
        alert('Failed to update coordinates. Please try again.');
    }
}

// Bulk Edit Functions

let bulkEditCustomers = [];
let modifiedCustomers = new Set();

async function showBulkEditCustomers() {
    try {
        // Load ALL customers (no day filtering for bulk edit)
        const url = `${API_BASE}/api/customers?page_size=1000`;

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to load customers');
        }

        const data = await response.json();
        bulkEditCustomers = data.customers;
        modifiedCustomers.clear();

        renderBulkEditTable();

        // Open the modal
        const modal = document.getElementById('bulk-edit-modal');
        if (modal) {
            modal.classList.add('active');
        }
    } catch (error) {
        console.error('Error loading customers for bulk edit:', error);
        alert('Failed to load customers. Please try again.');
    }
}

function renderBulkEditTable() {
    const tbody = document.getElementById('bulk-edit-tbody');
    const countElement = document.getElementById('bulk-edit-count');

    if (!bulkEditCustomers || bulkEditCustomers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; padding: 2rem;">No customers found.</td></tr>';
        if (countElement) countElement.textContent = '0 clients loaded';
        return;
    }

    if (countElement) {
        countElement.textContent = `${bulkEditCustomers.length} client${bulkEditCustomers.length !== 1 ? 's' : ''} loaded`;
    }

    // Build driver options
    let driversOptions = '<option value="">Unassigned</option>';
    if (Array.isArray(window.allDrivers)) {
        window.allDrivers.forEach(driver => {
            driversOptions += `<option value="${driver.id}">${escapeHtml(driver.name)}</option>`;
        });
    }

    let tableHtml = '';
    bulkEditCustomers.forEach((customer, index) => {
        // Parse address into components
        const addressParts = customer.address.split(',').map(p => p.trim());
        const street = addressParts[0] || '';
        const city = addressParts[1] || '';
        const stateZip = addressParts[2] || '';
        const stateZipParts = stateZip.split(' ');
        const state = stateZipParts[0] || '';
        const zip = stateZipParts[1] || '';

        tableHtml += `
            <tr data-customer-id="${customer.id}" data-index="${index}">
                <td class="wide">
                    <input type="text" data-field="display_name" value="${escapeHtml(customer.display_name)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="wide">
                    <input type="text" data-field="street" value="${escapeHtml(street)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="medium">
                    <input type="text" data-field="city" value="${escapeHtml(city)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="narrow">
                    <input type="text" data-field="state" value="${escapeHtml(state)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="narrow">
                    <input type="text" data-field="zip" value="${escapeHtml(zip)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="medium">
                    <select data-field="assigned_driver_id" onchange="markCustomerModified('${customer.id}')">
                        ${driversOptions}
                    </select>
                </td>
                <td class="medium">
                    <select data-field="service_day" onchange="markCustomerModified('${customer.id}')">
                        <option value="monday" ${customer.service_day === 'monday' ? 'selected' : ''}>Monday</option>
                        <option value="tuesday" ${customer.service_day === 'tuesday' ? 'selected' : ''}>Tuesday</option>
                        <option value="wednesday" ${customer.service_day === 'wednesday' ? 'selected' : ''}>Wednesday</option>
                        <option value="thursday" ${customer.service_day === 'thursday' ? 'selected' : ''}>Thursday</option>
                        <option value="friday" ${customer.service_day === 'friday' ? 'selected' : ''}>Friday</option>
                        <option value="saturday" ${customer.service_day === 'saturday' ? 'selected' : ''}>Saturday</option>
                        <option value="sunday" ${customer.service_day === 'sunday' ? 'selected' : ''}>Sunday</option>
                    </select>
                </td>
                <td class="narrow">
                    <select data-field="service_days_per_week" onchange="markCustomerModified('${customer.id}')">
                        <option value="1" ${customer.service_days_per_week === 1 ? 'selected' : ''}>1</option>
                        <option value="2" ${customer.service_days_per_week === 2 ? 'selected' : ''}>2</option>
                        <option value="3" ${customer.service_days_per_week === 3 ? 'selected' : ''}>3</option>
                    </select>
                </td>
                <td class="medium">
                    <select data-field="service_type" onchange="markCustomerModified('${customer.id}')">
                        <option value="residential" ${customer.service_type === 'residential' ? 'selected' : ''}>Residential</option>
                        <option value="commercial" ${customer.service_type === 'commercial' ? 'selected' : ''}>Commercial</option>
                    </select>
                </td>
                <td class="narrow">
                    <input type="number" data-field="visit_duration" min="5" max="120" value="${customer.visit_duration || 15}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="narrow">
                    <select data-field="difficulty" onchange="markCustomerModified('${customer.id}')">
                        <option value="1" ${customer.difficulty === 1 ? 'selected' : ''}>1</option>
                        <option value="2" ${customer.difficulty === 2 ? 'selected' : ''}>2</option>
                        <option value="3" ${customer.difficulty === 3 ? 'selected' : ''}>3</option>
                        <option value="4" ${customer.difficulty === 4 ? 'selected' : ''}>4</option>
                        <option value="5" ${customer.difficulty === 5 ? 'selected' : ''}>5</option>
                    </select>
                </td>
                <td class="narrow" style="text-align: center;">
                    <input type="checkbox" data-field="locked" ${customer.locked ? 'checked' : ''} onchange="markCustomerModified('${customer.id}')">
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = tableHtml;

    // Set selected driver for each row
    bulkEditCustomers.forEach(customer => {
        const row = document.querySelector(`tr[data-customer-id="${customer.id}"]`);
        if (row && customer.assigned_driver_id) {
            const select = row.querySelector('[data-field="assigned_driver_id"]');
            if (select) {
                select.value = customer.assigned_driver_id;
            }
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function markCustomerModified(customerId) {
    modifiedCustomers.add(customerId);

    // Highlight the row
    const row = document.querySelector(`tr[data-customer-id="${customerId}"]`);
    if (row) {
        row.classList.add('modified');
    }

    // Update count display
    const countElement = document.getElementById('modified-count');
    if (countElement) {
        countElement.textContent = `${modifiedCustomers.size} customer${modifiedCustomers.size !== 1 ? 's' : ''} modified`;
    }
}

async function saveBulkEditChanges() {
    if (modifiedCustomers.size === 0) {
        alert('No changes to save');
        return;
    }

    if (!confirm(`Save changes to ${modifiedCustomers.size} customer${modifiedCustomers.size !== 1 ? 's' : ''}?`)) {
        return;
    }

    const saveBtn = document.getElementById('save-bulk-changes-btn');
    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

    let successCount = 0;
    let errorCount = 0;

    try {
        for (const customerId of modifiedCustomers) {
            const row = document.querySelector(`tr[data-customer-id="${customerId}"]`);
            if (!row) continue;

            // Collect data from the row and reconstruct address
            const name = row.querySelector('[data-field="name"]').value.trim();
            const street = row.querySelector('[data-field="street"]').value.trim();
            const city = row.querySelector('[data-field="city"]').value.trim();
            const state = row.querySelector('[data-field="state"]').value.trim();
            const zip = row.querySelector('[data-field="zip"]').value.trim();
            const address = combineAddressFields(street, city, state, zip);

            const assignedDriverValue = row.querySelector('[data-field="assigned_driver_id"]').value;
            const assignedDriverId = assignedDriverValue ? assignedDriverValue : null;

            const data = {
                name: name,
                address: address,
                assigned_driver_id: assignedDriverId,
                service_day: row.querySelector('[data-field="service_day"]').value,
                service_type: row.querySelector('[data-field="service_type"]').value,
                service_days_per_week: parseInt(row.querySelector('[data-field="service_days_per_week"]').value),
                visit_duration: parseInt(row.querySelector('[data-field="visit_duration"]').value),
                difficulty: parseInt(row.querySelector('[data-field="difficulty"]').value),
                locked: row.querySelector('[data-field="locked"]').checked
            };

            try {
                const response = await fetch(`${API_BASE}/api/customers/${customerId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    throw new Error('Failed to update');
                }

                successCount++;
                row.classList.remove('modified');
            } catch (error) {
                console.error(`Error updating customer ${customerId}:`, error);
                errorCount++;
            }
        }

        let message = `Successfully updated ${successCount} customer${successCount !== 1 ? 's' : ''}`;
        if (errorCount > 0) {
            message += `\nFailed to update ${errorCount} customer${errorCount !== 1 ? 's' : ''}`;
        }

        alert(message);

        // Clear modified set
        modifiedCustomers.clear();

        // Close modal
        const modal = document.getElementById('bulk-edit-modal');
        if (modal) modal.classList.remove('active');

        // Reload customers
        loadCustomersManagement();
        loadCustomers(); // Reload map
    } catch (error) {
        console.error('Error during bulk save:', error);
        alert('An error occurred while saving changes. Please try again.');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    }
}

// Drag and Drop Functions

function makeSavedRoutesEditable(routes) {
    const container = document.getElementById('routes-content');
    container.innerHTML = '';

    const header = document.createElement('div');
    header.className = 'route-summary';
    header.innerHTML = `
        <h3>Edit Routes (Drag & Drop)</h3>
        <p>Drag stops to reorder them or move them between routes</p>
    `;
    container.appendChild(header);

    routes.forEach(async (route) => {
        // Get route details with stops
        const response = await fetch(`${API_BASE}/api/routes/${route.id}`);
        const routeDetails = await response.json();

        const routeCard = document.createElement('div');
        routeCard.className = 'route-card';
        routeCard.dataset.routeId = route.id;

        const title = document.createElement('h3');
        title.textContent = `Route: ${route.id.substring(0, 8)} - ${route.service_day}`;
        routeCard.appendChild(title);

        const info = document.createElement('p');
        info.textContent = `${route.total_customers} stops, ${route.total_distance_miles?.toFixed(1) || 0} miles`;
        routeCard.appendChild(info);

        const stopsList = document.createElement('ul');
        stopsList.className = 'route-stops editable-stops';
        stopsList.dataset.routeId = route.id;

        // Add drop zone handlers to the list
        stopsList.addEventListener('dragover', handleDragOver);
        stopsList.addEventListener('drop', handleDrop);
        stopsList.addEventListener('dragleave', handleDragLeave);

        routeDetails.stops.forEach((stop) => {
            const stopItem = createDraggableStop(stop, route.id);
            stopsList.appendChild(stopItem);
        });

        routeCard.appendChild(stopsList);
        container.appendChild(routeCard);
    });
}

function createDraggableStop(stop, routeId) {
    const stopItem = document.createElement('li');
    stopItem.className = 'draggable-stop';
    stopItem.draggable = true;
    stopItem.dataset.stopId = stop.stop_id || stop.id;
    stopItem.dataset.routeId = routeId;
    stopItem.dataset.sequence = stop.sequence;
    stopItem.textContent = `${stop.sequence}. ${stop.customer_name} - ${stop.address}`;

    stopItem.addEventListener('dragstart', handleDragStart);
    stopItem.addEventListener('dragend', handleDragEnd);
    stopItem.addEventListener('dragover', handleDragOver);
    stopItem.addEventListener('drop', handleDrop);

    return stopItem;
}

function handleDragStart(e) {
    draggedStop = e.target;
    draggedStopRoute = e.target.dataset.routeId;
    e.target.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', e.target.innerHTML);
}

function handleDragEnd(e) {
    e.target.style.opacity = '1';

    // Remove all drag-over classes
    document.querySelectorAll('.drag-over').forEach(el => {
        el.classList.remove('drag-over');
    });
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';

    if (e.target.classList.contains('editable-stops')) {
        e.target.classList.add('drag-over');
    }

    return false;
}

function handleDragLeave(e) {
    if (e.target.classList.contains('editable-stops')) {
        e.target.classList.remove('drag-over');
    }
}

async function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    e.preventDefault();

    if (!draggedStop) return;

    const dropTarget = e.target;

    // Dropping on another stop item - reorder within same route or move to different route
    if (dropTarget.classList.contains('draggable-stop')) {
        const targetRouteId = dropTarget.dataset.routeId;
        const sourceRouteId = draggedStop.dataset.routeId;

        if (sourceRouteId === targetRouteId) {
            // Reorder within same route
            const parent = dropTarget.parentNode;
            const allStops = Array.from(parent.querySelectorAll('.draggable-stop'));
            const draggedIndex = allStops.indexOf(draggedStop);
            const targetIndex = allStops.indexOf(dropTarget);

            if (draggedIndex < targetIndex) {
                parent.insertBefore(draggedStop, dropTarget.nextSibling);
            } else {
                parent.insertBefore(draggedStop, dropTarget);
            }

            // Update sequences
            await updateStopSequences(sourceRouteId, parent);
        } else {
            // Move to different route
            const targetSequence = parseInt(dropTarget.dataset.sequence);
            await moveStopToRoute(draggedStop.dataset.stopId, sourceRouteId, targetRouteId, targetSequence);
        }
    }
    // Dropping on the route list itself - add to end
    else if (dropTarget.classList.contains('editable-stops')) {
        const targetRouteId = dropTarget.dataset.routeId;
        const sourceRouteId = draggedStop.dataset.routeId;

        if (sourceRouteId !== targetRouteId) {
            const newSequence = dropTarget.children.length + 1;
            await moveStopToRoute(draggedStop.dataset.stopId, sourceRouteId, targetRouteId, newSequence);
        } else {
            dropTarget.appendChild(draggedStop);
            await updateStopSequences(targetRouteId, dropTarget);
        }
    }

    return false;
}

async function updateStopSequences(routeId, stopsList) {
    const stops = Array.from(stopsList.querySelectorAll('.draggable-stop'));
    const updates = stops.map((stop, index) => ({
        stop_id: stop.dataset.stopId,
        sequence: index + 1
    }));

    // Update sequence numbers in UI
    stops.forEach((stop, index) => {
        stop.dataset.sequence = index + 1;
        const text = stop.textContent;
        const nameAndAddress = text.substring(text.indexOf('.') + 2);
        stop.textContent = `${index + 1}. ${nameAndAddress}`;
    });

    try {
        const response = await fetch(`${API_BASE}/api/routes/${routeId}/stops`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ stops: updates })
        });

        if (!response.ok) {
            throw new Error('Failed to update stop sequence');
        }
    } catch (error) {
        console.error('Error updating stop sequence:', error);
        alert('Failed to update stop order. Please try again.');
    }
}

async function moveStopToRoute(stopId, sourceRouteId, targetRouteId, sequence) {
    try {
        const response = await fetch(`${API_BASE}/api/routes/${sourceRouteId}/stops/${stopId}/move`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                target_route_id: targetRouteId,
                sequence: sequence
            })
        });

        if (!response.ok) {
            throw new Error('Failed to move stop');
        }

        // Reload the editable view
        location.reload();
    } catch (error) {
        console.error('Error moving stop:', error);
        alert('Failed to move stop. Please try again.');
    }
}
