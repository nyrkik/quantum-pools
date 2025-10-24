// RouteOptimizer Frontend Application

// Initialize map
let map;
let routeLayers = [];
const API_BASE = window.location.origin;

document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    attachEventListeners();
    loadCustomers();
});

function initializeMap() {
    // Initialize Leaflet map centered on US (will be updated based on data)
    map = L.map('map').setView([39.8283, -98.5795], 4);

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);
}

async function loadCustomers() {
    try {
        const response = await fetch(`${API_BASE}/api/customers?page_size=100`);
        if (!response.ok) return;

        const data = await response.json();
        if (data.customers && data.customers.length > 0) {
            displayCustomersOnMap(data.customers);
        }
    } catch (error) {
        console.error('Error loading customers:', error);
    }
}

function displayCustomersOnMap(customers) {
    const coordinates = [];

    customers.forEach(customer => {
        if (customer.latitude && customer.longitude) {
            const latLng = [customer.latitude, customer.longitude];
            coordinates.push(latLng);

            const marker = L.circleMarker(latLng, {
                radius: 6,
                fillColor: '#3498db',
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.7
            }).addTo(map);

            marker.bindPopup(`
                <b>${customer.name}</b><br>
                ${customer.address}<br>
                <em>${customer.service_type} - ${customer.service_day}</em>
            `);
        }
    });

    if (coordinates.length > 0) {
        const bounds = L.latLngBounds(coordinates);
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

function attachEventListeners() {
    document.getElementById('optimize-btn').addEventListener('click', optimizeRoutes);
    document.getElementById('import-btn').addEventListener('click', importCSV);
}

async function optimizeRoutes() {
    const numDrivers = parseInt(document.getElementById('num-drivers').value);
    const serviceDay = document.getElementById('service-day').value;

    const optimizeBtn = document.getElementById('optimize-btn');
    optimizeBtn.disabled = true;
    optimizeBtn.textContent = 'Optimizing...';

    try {
        const requestBody = {
            num_drivers: numDrivers || null,
            service_day: serviceDay === 'all' ? null : serviceDay,
            allow_day_reassignment: false
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
            displayRoutes(result);
            displayRoutesOnMap(result.routes);
        } else {
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
        container.appendChild(summary);
    }

    // Show routes
    result.routes.forEach((route, index) => {
        const routeCard = document.createElement('div');
        routeCard.className = 'route-card';

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

function displayRoutesOnMap(routes) {
    // Clear existing route layers
    routeLayers.forEach(layer => map.removeLayer(layer));
    routeLayers = [];

    const colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6'];
    const allCoordinates = [];

    routes.forEach((route, routeIndex) => {
        const color = colors[routeIndex % colors.length];
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

                marker.bindPopup(`<b>${stop.customer_name}</b><br>${stop.address}`);
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
                throw new Error('Import failed');
            }

            const result = await response.json();
            alert(`Import complete!\nImported: ${result.imported}\nSkipped: ${result.skipped}\nErrors: ${result.errors}`);

            // Reload customers on map
            loadCustomers();
        } catch (error) {
            console.error('Error importing CSV:', error);
            alert('Failed to import CSV file.');
        }
    };

    input.click();
}
