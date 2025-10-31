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

        // Count unassigned customers
        const customers = data.customers || [];
        window.unassignedCustomerCount = customers.filter(c => !c.assigned_tech_id).length;
        window.currentCustomers = customers;

        displayCustomersOnMap(customers);
        displayCurrentAssignments(customers);
    } catch (error) {
        console.error('Error loading customers:', error);
        window.unassignedCustomerCount = 0;
        window.currentCustomers = [];
        displayCustomersOnMap([]);
        displayCurrentAssignments([]);
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
            const showUnassigned = selectedTechIds.has('unassigned');

            // Show if: unassigned (and unassigned is selected) OR assigned to selected tech OR no techs loaded yet
            if (selectedTechIds.size > 0) {
                if (isUnassigned && !showUnassigned) {
                    return; // Skip unassigned if unassigned chip not selected
                }
                if (!isUnassigned && !isSelectedTech) {
                    return; // Skip if not in our selected techs
                }
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

            // Parse address to show only street and city
            const addressParts = customer.address.split(',').map(p => p.trim());
            const streetAndCity = addressParts.length >= 2
                ? `${addressParts[0]}, ${addressParts[1]}`
                : customer.address;

            marker.bindPopup(`
                <b>${customer.display_name}</b><br>
                ${streetAndCity}
            `);

            // Add tooltip for property name on hover
            marker.bindTooltip(customer.display_name, {
                permanent: false,
                direction: 'top',
                offset: [0, -10]
            });

            // Add hover effect - red border
            marker.on('mouseover', function() {
                this.setStyle({
                    color: '#e74c3c',
                    weight: 3
                });
            });

            marker.on('mouseout', function() {
                this.setStyle({
                    color: '#fff',
                    weight: 2
                });
            });

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

function highlightCustomerMarker(customerId, openPopup = false) {
    // Reset previously highlighted marker to its original color
    if (highlightedMarker && highlightedMarker.customerId !== customerId) {
        highlightedMarker.setStyle({
            radius: 6,
            fillColor: highlightedMarker.originalColor || '#3498db',
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: highlightedMarker.originalFillOpacity || 0.7
        });
        highlightedMarker.closePopup();
    }

    // Highlight the selected marker
    const marker = customerMarkersById[customerId];
    if (marker) {
        marker.setStyle({
            radius: 8,
            fillColor: marker.originalColor || '#3498db',
            color: '#e74c3c',
            weight: 3,
            opacity: 1,
            fillOpacity: marker.originalFillOpacity || 0.7
        });

        if (openPopup) {
            marker.openPopup();
        }

        highlightedMarker = marker;
    }
}

function resetCustomerMarker(customerId) {
    const marker = customerMarkersById[customerId];
    if (marker) {
        marker.setStyle({
            radius: 6,
            fillColor: marker.originalColor || '#3498db',
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: marker.originalFillOpacity || 0.7
        });
        marker.closePopup();
    }
    if (highlightedMarker && highlightedMarker.customerId === customerId) {
        highlightedMarker = null;
    }
}

// ========================================
// Route Visualization on Map
// ========================================

// Route layers for map display
let routeLayers = [];

async function drawActualRoute(coordinates, color) {
    // Convert Leaflet [lat, lon] to OSRM [lon, lat] format
    const osrmCoords = coordinates.map(c => `${c[1]},${c[0]}`).join(';');
    const url = `http://router.project-osrm.org/route/v1/driving/${osrmCoords}?overview=full&geometries=geojson`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`OSRM API error: ${response.status}`);
        }

        const data = await response.json();
        if (data.code !== 'Ok' || !data.routes || data.routes.length === 0) {
            throw new Error('No route found');
        }

        // Extract GeoJSON coordinates and convert to Leaflet [lat, lon] format
        const routeCoords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);

        const polyline = L.polyline(routeCoords, {
            color: color,
            weight: 3,
            opacity: 0.7
        }).addTo(map);

        routeLayers.push(polyline);
    } catch (error) {
        console.error('OSRM routing error:', error);
        throw error; // Re-throw to trigger fallback
    }
}

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

        const routeTechId = route.tech_id || route.driver_id;
        if (routeTechId && !selectedTechIds.has(routeTechId)) {
            return; // Skip routes for techs not in selection
        }

        // Use tech's color, or fall back to default
        const color = route.driver_color || '#3498db';
        const coordinates = [];

        // Add start depot marker if available
        if (route.start_location && route.start_location.latitude && route.start_location.longitude) {
            const startLatLng = [route.start_location.latitude, route.start_location.longitude];
            coordinates.push(startLatLng);
            allCoordinates.push(startLatLng);

            // Create house icon for depot
            const startIcon = L.divIcon({
                html: `<div style="color: ${color}; font-size: 20px;">🏠</div>`,
                className: 'depot-marker',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });

            const startMarker = L.marker(startLatLng, { icon: startIcon }).addTo(map);
            startMarker.bindPopup(`<b>Start: ${route.driver_name}</b><br>${route.start_location.address}`);
            routeLayers.push(startMarker);
        }

        // Add stop markers with sequence numbers
        route.stops.forEach((stop, index) => {
            if (stop.latitude && stop.longitude) {
                const latLng = [stop.latitude, stop.longitude];
                coordinates.push(latLng);
                allCoordinates.push(latLng);

                // Create numbered marker icon
                const numberIcon = L.divIcon({
                    html: `<div style="background-color: ${color}; color: white; border: 2px solid white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">${index + 1}</div>`,
                    className: 'numbered-marker',
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                });

                const marker = L.marker(latLng, { icon: numberIcon }).addTo(map);

                marker.bindPopup(`<b>#${index + 1}: ${stop.customer_name}</b><br>${stop.address}<br><em>${route.driver_name}</em>`);
                routeLayers.push(marker);
            }
        });

        // Add end depot marker if available
        if (route.end_location && route.end_location.latitude && route.end_location.longitude) {
            const endLatLng = [route.end_location.latitude, route.end_location.longitude];
            coordinates.push(endLatLng);
            allCoordinates.push(endLatLng);

            // Create house icon for depot
            const endIcon = L.divIcon({
                html: `<div style="color: ${color}; font-size: 20px;">🏠</div>`,
                className: 'depot-marker',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });

            const endMarker = L.marker(endLatLng, { icon: endIcon }).addTo(map);
            endMarker.bindPopup(`<b>End: ${route.driver_name}</b><br>${route.end_location.address}`);
            routeLayers.push(endMarker);
        }

        // Draw actual driving route using OSRM
        if (coordinates.length > 1) {
            drawActualRoute(coordinates, color).catch(err => {
                console.error('Failed to draw OSRM route, using straight line:', err);
                // Fallback to straight line
                const polyline = L.polyline(coordinates, {
                    color: color,
                    weight: 3,
                    opacity: 0.7
                }).addTo(map);
                routeLayers.push(polyline);
            });
        }
    });

    // Fit map to show all routes
    if (allCoordinates.length > 0) {
        const bounds = L.latLngBounds(allCoordinates);
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

function displayCurrentAssignments(customers) {
    // Skip if there's an optimization result being displayed
    if (currentRouteResult) {
        return;
    }

    const container = document.getElementById('routes-content');
    if (!container) return;

    container.innerHTML = '';

    // Group customers by tech
    const techGroups = {};
    const unassigned = [];

    customers.forEach(customer => {
        if (!customer.assigned_tech_id) {
            unassigned.push(customer);
        } else {
            if (!techGroups[customer.assigned_tech_id]) {
                techGroups[customer.assigned_tech_id] = {
                    tech: customer.assigned_tech,
                    customers: []
                };
            }
            techGroups[customer.assigned_tech_id].customers.push(customer);
        }
    });

    // Display tech groups
    let hasDisplayedRoutes = false;

    Object.entries(techGroups).forEach(([techId, group]) => {
        // Filter by selected techs
        if (selectedTechIds.size > 0 && !selectedTechIds.has(techId)) {
            return;
        }

        hasDisplayedRoutes = true;

        const routeCard = document.createElement('div');
        routeCard.className = 'route-card';

        // Add color indicator
        const colorIndicator = document.createElement('div');
        colorIndicator.className = 'route-color-indicator';
        colorIndicator.style.backgroundColor = group.tech.color || '#3498db';
        routeCard.appendChild(colorIndicator);

        const title = document.createElement('h3');
        title.innerHTML = `<strong>${group.tech.name}</strong> <span class="stop-count">- ${group.customers.length} stops</span>`;
        routeCard.appendChild(title);

        const stopsList = document.createElement('ul');
        stopsList.className = 'route-stops';

        group.customers.forEach(customer => {
            const stopItem = document.createElement('li');
            stopItem.dataset.customerId = customer.id;
            // Extract just the street address (before city/state)
            const addressParts = customer.address.split(',');
            const streetAddress = addressParts[0] || customer.address;
            stopItem.innerHTML = `<span class="customer-name">${customer.display_name}</span> - ${streetAddress}`;

            // Add hover handlers to highlight marker and show popup
            stopItem.addEventListener('mouseenter', () => {
                if (customer.id) {
                    highlightCustomerMarker(customer.id, true);
                }
            });
            stopItem.addEventListener('mouseleave', () => {
                if (customer.id) {
                    resetCustomerMarker(customer.id);
                }
            });

            stopsList.appendChild(stopItem);
        });

        routeCard.appendChild(stopsList);
        container.appendChild(routeCard);
    });

    // Display unassigned if selected
    if (unassigned.length > 0 && selectedTechIds.has('unassigned')) {
        hasDisplayedRoutes = true;

        const routeCard = document.createElement('div');
        routeCard.className = 'route-card';

        // Add color indicator
        const colorIndicator = document.createElement('div');
        colorIndicator.className = 'route-color-indicator';
        colorIndicator.style.backgroundColor = '#e74c3c';
        routeCard.appendChild(colorIndicator);

        const title = document.createElement('h3');
        title.innerHTML = `<strong>Unassigned</strong> <span class="stop-count">- ${unassigned.length} stops</span>`;
        routeCard.appendChild(title);

        const stopsList = document.createElement('ul');
        stopsList.className = 'route-stops';

        unassigned.forEach(customer => {
            const stopItem = document.createElement('li');
            stopItem.dataset.customerId = customer.id;
            // Extract just the street address (before city/state)
            const addressParts = customer.address.split(',');
            const streetAddress = addressParts[0] || customer.address;
            stopItem.innerHTML = `<span class="customer-name">${customer.display_name}</span> - ${streetAddress}`;

            // Add hover handlers to highlight marker and show popup
            stopItem.addEventListener('mouseenter', () => {
                if (customer.id) {
                    highlightCustomerMarker(customer.id, true);
                }
            });
            stopItem.addEventListener('mouseleave', () => {
                if (customer.id) {
                    resetCustomerMarker(customer.id);
                }
            });

            stopsList.appendChild(stopItem);
        });

        routeCard.appendChild(stopsList);
        container.appendChild(routeCard);
    }

    if (!hasDisplayedRoutes) {
        container.innerHTML = '<p class="placeholder">No stops for selected techs</p>';
    }
}
