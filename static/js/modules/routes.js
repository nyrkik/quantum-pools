// QuantumPools - Routes Module
//
// Handles route optimization, display, saving, and drag-and-drop editing
// Dependencies: API_BASE, selectedDay, currentRouteResult, draggedStop, draggedStopRoute, selectedTechIds, map global, displayRoutesOnMap() from map.js, loadCustomers(), loadCustomersManagement()

function initDaySelector() {
    // Get current day of week
    const daysOfWeek = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const today = daysOfWeek[new Date().getDay()];

    // Set today as selected day and active tab
    selectedDay = today;

    // Load routes for today initially (wait for customers to load first in app.js)
    // loadTechRoutesForDay will be called after customers load

    document.querySelectorAll('.day-tab').forEach(tab => {
        if (tab.dataset.day === today) {
            tab.classList.add('active');
        }

        tab.addEventListener('click', async function() {
            selectedDay = this.dataset.day;

            // Update active day
            document.querySelectorAll('.day-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Reload customers FIRST so temp assignment borders work
            await loadCustomers();

            // Check if there's a saved route result for this day
            if (routeResultsByDay[selectedDay]) {
                currentRouteResult = routeResultsByDay[selectedDay];
                displayRoutes(currentRouteResult);
                displayRoutesOnMap(currentRouteResult.routes);
            } else {
                currentRouteResult = null;
                displayRoutesOnMap([]);
                initRoutesHeader();

                // Load persistent tech routes for this day
                await loadTechRoutesForDay(selectedDay);
            }

            loadCustomersManagement();

            // Reload techs to get updated customer counts for selected day
            loadTechs();
        });
    });
}

async function optimizeRoutes() {
    console.log('optimizeRoutes called');

    const optimizationScope = document.querySelector('input[name="optimization-scope"]:checked')?.value;
    if (!optimizationScope) {
        console.error('No optimization scope selected');
        alert('Please select an optimization scope');
        return;
    }

    const includeUnassigned = document.getElementById('include-unassigned')?.checked || false;
    const includePending = document.getElementById('include-pending')?.checked || false;
    const includeSaturday = document.getElementById('include-saturday')?.checked || false;
    const includeSunday = document.getElementById('include-sunday')?.checked || false;

    // For complete rerouting, always use 'full' mode
    const optimizationModeElement = document.querySelector('input[name="optimization-mode"]:checked');
    const optimizationMode = optimizationScope === 'complete_rerouting' ? 'full' : (optimizationModeElement ? optimizationModeElement.value : 'full');

    const optimizationSpeedElement = document.querySelector('input[name="optimization-speed"]:checked');
    if (!optimizationSpeedElement) {
        console.error('No optimization speed selected');
        alert('Please select an optimization speed');
        return;
    }
    const optimizationSpeed = optimizationSpeedElement.value;


    // Get selected tech IDs (excluding unassigned)
    const selectedTechs = Array.from(selectedTechIds).filter(id => id !== 'unassigned');

    // Validate tech selection for non-complete-rerouting scopes
    if (optimizationScope !== 'complete_rerouting' && selectedTechs.length === 0) {
        alert('Please select at least one tech to optimize.');
        return;
    }

    // Get unlocked customer IDs for complete rerouting (unlocked = can move days)
    let unlockedCustomerIds = [];
    if (optimizationScope === 'complete_rerouting') {
        const lockButtons = document.querySelectorAll('.customer-lock-toggle');
        unlockedCustomerIds = Array.from(lockButtons)
            .filter(btn => btn.dataset.locked === 'false')
            .map(btn => btn.dataset.customerId);
    }

    // Show loading overlay
    showLoadingOverlay('Calculating optimal routes...');

    try {
        const requestBody = {
            optimization_scope: optimizationScope,
            selected_tech_ids: optimizationScope === 'complete_rerouting' ? null : selectedTechs,
            service_day: (optimizationScope === 'complete_rerouting' || selectedDay === 'all') ? null : selectedDay,
            unlocked_customer_ids: optimizationScope === 'complete_rerouting' ? unlockedCustomerIds : null,
            include_unassigned: includeUnassigned,
            include_pending: includePending,
            include_saturday: includeSaturday,
            include_sunday: includeSunday,
            optimization_mode: optimizationMode,
            optimization_speed: optimizationSpeed
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
            // When complete rerouting returns routes for all days, split and store them by day
            const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'];
            if (includeSaturday) days.push('saturday');
            if (includeSunday) days.push('sunday');
            const routesByDay = {};

            days.forEach(day => {
                routesByDay[day] = result.routes.filter(route => route.service_day === day);
            });

            // Store routes for each day separately
            days.forEach(day => {
                if (routesByDay[day].length > 0) {
                    routeResultsByDay[day] = {
                        routes: routesByDay[day],
                        summary: result.summary // Use overall summary for now
                    };
                }
            });

            // Auto-select techs that are in the optimization result
            selectedTechIds.clear();
            result.routes.forEach(route => {
                if (route.driver_id) {
                    selectedTechIds.add(route.driver_id);
                }
            });

            // Uncheck "All" toggle
            const allToggle = document.getElementById('all-toggle');
            if (allToggle) {
                allToggle.checked = false;
            }

            // Display only routes for the current selected day
            const currentDayRoutes = routeResultsByDay[selectedDay] || result;
            displayRoutes(currentDayRoutes);
            displayRoutesOnMap(currentDayRoutes.routes);

            // Update tech chips with stop counts and selection state
            // Pass false to preserve the selectedTechIds we just set
            if (allTechs && allTechs.length > 0) {
                populateTechChips(allTechs, false);
            }
        } else {
            currentRouteResult = null;
            delete routeResultsByDay[selectedDay];
            alert(result.message || 'No routes generated. Add customers and techs first.');
        }
    } catch (error) {
        console.error('Error optimizing routes:', error);
        alert(`Failed to optimize routes: ${error.message}`);
    } finally {
        hideLoadingOverlay();
    }
}

function initRoutesHeader() {
    const container = document.getElementById('routes-content');
    container.innerHTML = '';

    // Create sticky header
    const summary = document.createElement('div');
    summary.id = 'routes-summary-header';
    summary.className = 'route-summary';
    summary.style.position = 'sticky';
    summary.style.top = '0';
    summary.style.zIndex = '100';
    summary.style.fontSize = '0.85rem';
    summary.style.padding = '0.75rem';
    summary.style.display = 'none'; // Hidden by default, shown only when optimized

    const content = document.createElement('div');
    content.id = 'routes-summary-content';
    summary.appendChild(content);
    container.appendChild(summary);

    // Placeholder for route cards
    const routesContainer = document.createElement('div');
    routesContainer.id = 'routes-cards-container';
    container.appendChild(routesContainer);
}

function displayRoutes(result) {
    const container = document.getElementById('routes-content');
    const summaryHeader = document.getElementById('routes-summary-header');
    const summaryContent = document.getElementById('routes-summary-content');
    const routesContainer = document.getElementById('routes-cards-container');

    // Initialize if not present
    if (!summaryHeader) {
        initRoutesHeader();
        return displayRoutes(result);
    }

    // Clear routes container
    routesContainer.innerHTML = '';

    if (!result.routes || result.routes.length === 0) {
        summaryHeader.style.display = 'none';
        return;
    }

    // Show and update summary content
    summaryHeader.style.display = 'block';
    if (result.summary) {
        // Format total duration
        const totalMinutes = result.summary.total_duration_minutes || 0;
        const totalHours = Math.floor(totalMinutes / 60);
        const totalMins = totalMinutes % 60;
        const totalDurationStr = totalHours > 0 ? `${totalHours}hr ${totalMins}min` : `${totalMins}min`;

        summaryContent.innerHTML = `
            <p style="margin: 0.25rem 0;"><strong>Total Routes:</strong> ${result.summary.total_routes}</p>
            <p style="margin: 0.25rem 0;"><strong>Total Customers:</strong> ${result.summary.total_customers || 0}</p>
            <p style="margin: 0.25rem 0;"><strong>Total Distance:</strong> ${(result.summary.total_distance_miles || 0).toFixed(1)} miles</p>
            <p style="margin: 0.25rem 0;"><strong>Total Duration:</strong> ${totalDurationStr}</p>
        `;

        // Add action buttons
        const buttonContainer = document.createElement('div');
        buttonContainer.style.display = 'flex';
        buttonContainer.style.gap = '1rem';
        buttonContainer.style.marginTop = '1rem';

        const acceptBtn = document.createElement('button');
        acceptBtn.className = 'btn-primary';
        acceptBtn.textContent = 'Accept Changes';
        acceptBtn.onclick = async () => {
            await saveRoutes(result);
            currentRouteResult = null;
            delete routeResultsByDay[selectedDay];
            await loadCustomers();
            loadTechs();
            initRoutesHeader();
        };

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn-secondary';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.onclick = () => {
            currentRouteResult = null;
            delete routeResultsByDay[selectedDay];
            displayRoutesOnMap([]);
            loadCustomers();
            loadTechs();
            initRoutesHeader();
        };

        buttonContainer.appendChild(acceptBtn);
        buttonContainer.appendChild(cancelBtn);
        summaryContent.appendChild(buttonContainer);
    }

    // Filter and show routes based on selected techs and current day
    const filteredRoutes = result.routes.filter(route => {
        if (selectedTechIds.size === 0) return false;
        if (route.driver_id && !selectedTechIds.has(route.driver_id)) return false;
        // Filter by current day tab (only show routes for the selected day)
        if (route.service_day && route.service_day !== selectedDay) return false;
        return true;
    });

    if (filteredRoutes.length === 0) {
        routesContainer.innerHTML = '<p class="placeholder">No routes for selected techs</p>';
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
        title.style.cursor = 'pointer';
        title.style.userSelect = 'none';

        // Format duration as "Xhr Ymin"
        const hours = Math.floor(route.total_duration_minutes / 60);
        const mins = route.total_duration_minutes % 60;
        const durationStr = hours > 0 ? `${hours}hr ${mins}min` : `${mins}min`;

        // Format distance
        const distanceStr = `${route.total_distance_miles.toFixed(0)} mi`;

        title.innerHTML = `<span class="collapse-icon">▶</span> <strong>${route.driver_name}</strong> <span class="stop-count">- ${route.total_customers} stops - ${durationStr} - ${distanceStr}</span>`;
        routeCard.appendChild(title);

        const stopsList = document.createElement('ul');
        stopsList.className = 'route-stops';

        route.stops.forEach((stop) => {
            const stopItem = document.createElement('li');
            stopItem.dataset.customerId = stop.customer_id;
            stopItem.innerHTML = `<span class="customer-name">${stop.customer_name}</span>`;

            // Add hover handlers to highlight marker and show popup
            stopItem.addEventListener('mouseenter', () => {
                if (stop.customer_id) {
                    highlightCustomerMarker(stop.customer_id, true);
                }
            });
            stopItem.addEventListener('mouseleave', () => {
                if (stop.customer_id) {
                    resetCustomerMarker(stop.customer_id);
                }
            });

            stopsList.appendChild(stopItem);
        });

        // Collapsed by default
        stopsList.style.display = 'none';

        routeCard.appendChild(stopsList);

        // Add collapse/expand functionality
        title.addEventListener('click', () => {
            const icon = title.querySelector('.collapse-icon');
            if (stopsList.style.display === 'none' || !stopsList.style.display) {
                stopsList.style.display = 'block';
                icon.textContent = '▼';
            } else {
                stopsList.style.display = 'none';
                icon.textContent = '▶';
            }
        });

        routesContainer.appendChild(routeCard);
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

        // Reload saved routes data for tech chips
        await loadSavedRoutesForDay(serviceDay);

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
        title.innerHTML = `<span class="collapse-icon">▶</span> Route: ${route.id.substring(0, 8)} - ${route.service_day}`;
        title.style.cursor = 'pointer';
        title.style.userSelect = 'none';
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

        // Collapsed by default
        stopsList.style.display = 'none';

        // Add collapse/expand functionality
        title.addEventListener('click', () => {
            const icon = title.querySelector('.collapse-icon');
            if (stopsList.style.display === 'none' || !stopsList.style.display) {
                stopsList.style.display = 'block';
                icon.textContent = '▼';
            } else {
                stopsList.style.display = 'none';
                icon.textContent = '▶';
            }
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

async function loadTechRoutesForDay(serviceDay) {
    // Show loading spinner
    showLoadingOverlay('Loading routes...');

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/tech-routes/${serviceDay}`);

        if (!response.ok) {
            console.error('Failed to load tech routes');
            hideLoadingOverlay();
            return;
        }

        const routes = await response.json();

        if (routes.length === 0) {
            hideLoadingOverlay();
            displayRoutesOnMap([]);
            return;
        }

        // Display routes on map with depot markers and polylines
        displayRoutesOnMap(routes);

        hideLoadingOverlay();
    } catch (error) {
        console.error('Error loading tech routes:', error);
        hideLoadingOverlay();
    }
}
