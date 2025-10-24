// RouteOptimizer Frontend Application

// Initialize map
let map;
let routeLayers = [];

document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    attachEventListeners();
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

function attachEventListeners() {
    document.getElementById('optimize-btn').addEventListener('click', optimizeRoutes);
    document.getElementById('import-btn').addEventListener('click', importCSV);
}

async function optimizeRoutes() {
    const numDrivers = document.getElementById('num-drivers').value;
    const serviceDay = document.getElementById('service-day').value;

    try {
        const response = await fetch('/api/routes/optimize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                num_drivers: parseInt(numDrivers),
                service_day: serviceDay === 'all' ? null : serviceDay
            })
        });

        if (!response.ok) {
            throw new Error('Optimization failed');
        }

        const routes = await response.json();
        displayRoutes(routes);
        displayRoutesOnMap(routes);
    } catch (error) {
        console.error('Error optimizing routes:', error);
        alert('Failed to optimize routes. Make sure the API is running and customers are added.');
    }
}

function displayRoutes(routes) {
    const container = document.getElementById('routes-content');
    container.innerHTML = '';

    routes.forEach((route, index) => {
        const routeCard = document.createElement('div');
        routeCard.className = 'route-card';

        const title = document.createElement('h3');
        title.textContent = `Driver ${index + 1} - ${route.service_day}`;
        routeCard.appendChild(title);

        const info = document.createElement('p');
        info.textContent = `${route.stops.length} stops, Est. ${route.total_duration} min`;
        routeCard.appendChild(info);

        const stopsList = document.createElement('ul');
        stopsList.className = 'route-stops';

        route.stops.forEach((stop, stopIndex) => {
            const stopItem = document.createElement('li');
            stopItem.textContent = `${stopIndex + 1}. ${stop.customer_name} - ${stop.address}`;
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
    // TODO: Implement CSV import dialog
    alert('CSV import feature coming soon! Use the API endpoint /api/imports/csv for now.');
}
