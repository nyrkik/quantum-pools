// RouteOptimizer - Map Module
//
// Handles Leaflet map initialization, Google Places autocomplete, and customer markers
// Dependencies: map, customerMarkers, customerMarkersById, highlightedMarker, selectedTechIds, selectedDay, API_BASE, HOME_BASE globals

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
        const response = await Auth.apiRequest(`${API_BASE}/api/config`);
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

        const response = await Auth.apiRequest(url);
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
            const isUnassigned = !customer.assigned_tech_id;
            const isSelectedTech = customer.assigned_tech_id && selectedTechIds.has(customer.assigned_tech_id);

            // Show if: unassigned (always) OR assigned to selected tech OR no techs loaded yet
            if (!isUnassigned && selectedTechIds.size > 0 && !isSelectedTech) {
                return; // Skip if not in our selected techs
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

            // Red for unassigned, use assigned tech's color for assigned customers
            let markerColor = '#e74c3c'; // Default red for unassigned
            if (!isUnassigned && customer.assigned_tech && customer.assigned_tech.color) {
                markerColor = customer.assigned_tech.color;
            }

            const marker = L.circleMarker(latLng, {
                radius: 6,
                fillColor: markerColor,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: isUnassigned ? 0.9 : 0.7
            }).addTo(map);

            // Store original color for later use (when unhighlighting)
            marker.originalColor = markerColor;
            marker.originalFillOpacity = isUnassigned ? 0.9 : 0.7;

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
    // Reset previously highlighted marker to its original color
    if (highlightedMarker) {
        highlightedMarker.setStyle({
            radius: 6,
            fillColor: highlightedMarker.originalColor || '#3498db',
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: highlightedMarker.originalFillOpacity || 0.7
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

// ========================================
// Route Visualization on Map
// ========================================

// Route layers for map display
let routeLayers = [];

function displayRoutesOnMap(routes) {
    // Clear existing route layers
    routeLayers.forEach(layer => map.removeLayer(layer));
    routeLayers = [];

    const allCoordinates = [];

    routes.forEach((route) => {
        // Filter by selected techs
        if (selectedTechIds.size === 0) {
            return; // No techs selected, don't show route
        }

        if (route.tech_id && !selectedTechIds.has(route.tech_id)) {
            return; // Skip routes for techs not in selection
        }

        // Use tech's color, or fall back to default
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
