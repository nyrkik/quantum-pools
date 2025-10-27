// RouteOptimizer - Routes Module
//
// Handles route optimization, display, saving, and drag-and-drop editing
// Dependencies: API_BASE, selectedDay, currentRouteResult, draggedStop, draggedStopRoute, selectedTechIds, map global, displayRoutesOnMap() from map.js, loadCustomers(), loadCustomersManagement()

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

            // Clear route result when switching days
            currentRouteResult = null;

            // Update active day
            document.querySelectorAll('.day-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Reload customers for selected day
            loadCustomers();
            loadCustomersManagement();

            // Repopulate tech chips to clear stop counts
            if (allTechs && allTechs.length > 0) {
                populateTechChips(allTechs);
            }
        });
    });
}

async function optimizeRoutes() {
    const numTechs = parseInt(document.getElementById('num-techs').value);
    const allowReassignment = document.getElementById('allow-reassignment').checked;
    const optimizationMode = document.querySelector('input[name="optimization-mode"]:checked').value;

    const optimizeBtn = document.getElementById('optimize-btn');
    optimizeBtn.disabled = true;
    optimizeBtn.textContent = 'Optimizing...';

    try {
        const requestBody = {
            num_drivers: numTechs || null,
            service_day: selectedDay === 'all' ? null : selectedDay,
            allow_day_reassignment: allowReassignment,
            optimization_mode: optimizationMode
        };

        const response = await Auth.apiRequest(`${API_BASE}/api/routes/optimize`, {
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

            // Update tech chips with stop counts
            if (allTechs && allTechs.length > 0) {
                populateTechChips(allTechs);
            }
        } else {
            currentRouteResult = null;
            alert(result.message || 'No routes generated. Add customers and techs first.');
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

    // Filter and show routes based on selected techs
    const filteredRoutes = result.routes.filter(route => {
        if (selectedTechIds.size === 0) return false;
        if (route.driver_id && !selectedTechIds.has(route.driver_id)) return false;
        return true;
    });

    if (filteredRoutes.length === 0) {
        container.innerHTML += '<p class="placeholder">No routes for selected techs</p>';
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
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/save`, {
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
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/day/${serviceDay}`);

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

// ========================================
// Route Visualization
// displayRoutesOnMap() has been moved to /static/js/modules/map.js
// This separates route business logic from map rendering logic
// ========================================

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
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/${route.id}`);
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
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/${routeId}/stops`, {
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
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/${sourceRouteId}/stops/${stopId}/move`, {
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
