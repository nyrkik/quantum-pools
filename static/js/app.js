// RouteOptimizer Frontend Application

// Initialize map
let map;
let routeLayers = [];
const API_BASE = window.location.origin;

// Drag and drop state
let draggedStop = null;
let draggedStopRoute = null;

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

        // Add save button
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn-primary';
        saveBtn.textContent = 'Save Routes';
        saveBtn.style.marginTop = '1rem';
        saveBtn.onclick = () => saveRoutes(result);
        summary.appendChild(saveBtn);

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
