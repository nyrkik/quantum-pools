// QuantumPools - Techs Module
//
// Handles tech/team member management, tech chips, and color picker
// Dependencies: API_BASE, allTechs, selectedTechIds globals, filterRoutesByTechs(), loadCustomers(), displayRoutes(), displayRoutesOnMap(), combineAddressFields(), parseAddress(), initAutocomplete()

// Predefined colors for techs (excluding red which is reserved for unassigned)
const TECH_COLORS = [
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

// Tech Management Functions

let allTechs = [];
let selectedTechIds = new Set();
let savedRoutesData = null; // Store saved routes from database

async function loadTechs() {
    try {
        // Include service_day parameter to get customer counts
        let url = `${API_BASE}/api/techs/`;
        if (selectedDay && selectedDay !== 'all') {
            url += `?service_day=${selectedDay}`;
        }

        const response = await Auth.apiRequest(url);
        if (!response.ok) {
            console.error('Failed to load techs');
            return;
        }

        const data = await response.json();
        allTechs = data.techs || [];

        displayTechs(allTechs);
        populateTechChips(allTechs);

        // Refresh map and route list to apply tech filter
        if (window.currentCustomers) {
            displayCustomersOnMap(window.currentCustomers);
            if (typeof displayCurrentAssignments === 'function') {
                displayCurrentAssignments(window.currentCustomers);
            }
        }

        // Show add tech button
        const addBtn = document.getElementById('add-tech-btn');
        if (addBtn) addBtn.style.display = 'block';
    } catch (error) {
        console.error('Error loading techs:', error);
        if (document.getElementById('techs-list')) {
            document.getElementById('techs-list').innerHTML = '<p class="placeholder">Failed to load techs</p>';
        }
    }
}

async function loadSavedRoutesForDay(serviceDay) {
    console.log('Loading saved routes for:', serviceDay);
    if (!serviceDay || serviceDay === 'all') {
        savedRoutesData = null;
        console.log('No service day selected, clearing saved routes');
        return;
    }

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/routes/day/${serviceDay}`);
        console.log('Routes API response status:', response.status);
        if (!response.ok) {
            savedRoutesData = null;
            return;
        }

        const routes = await response.json();
        console.log('Loaded routes from database:', routes);
        if (routes && routes.length > 0) {
            savedRoutesData = { routes: routes };
            console.log('Set savedRoutesData:', savedRoutesData);
        } else {
            savedRoutesData = null;
            console.log('No saved routes found for', serviceDay);
        }
    } catch (error) {
        console.error('Error loading saved routes:', error);
        savedRoutesData = null;
    }
}

function populateTechChips(techs, resetSelection = true) {
    const container = document.getElementById('tech-chips');
    if (!container) return;

    container.innerHTML = '';

    // Only clear and select all by default if resetSelection is true
    if (resetSelection) {
        selectedTechIds.clear();
    }

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
    checkbox.checked = resetSelection; // Only checked if we're resetting (selecting all)
    checkbox.addEventListener('change', toggleAllTechs);

    const slider = document.createElement('span');
    slider.className = 'toggle-slider';

    toggleSwitch.appendChild(checkbox);
    toggleSwitch.appendChild(slider);
    toggleContainer.appendChild(label);
    toggleContainer.appendChild(toggleSwitch);
    container.appendChild(toggleContainer);

    if (!techs || techs.length === 0) {
        return;
    }

    techs.forEach(tech => {
        // Calculate stop count and temp assignment count
        let stopCount = 0;
        let tempCount = 0;

        // First check if customer_count is available from API (assigned customers)
        if (tech.customer_count !== undefined && tech.customer_count !== null) {
            stopCount = tech.customer_count;
        }
        // Otherwise check current optimization result
        else if (currentRouteResult && currentRouteResult.routes) {
            const techRoute = currentRouteResult.routes.find(r => r.driver_id === tech.id);
            if (techRoute && techRoute.stops) {
                stopCount = techRoute.stops.length;
            }
        }

        // Count temp assignments for this tech from current customers
        if (window.currentCustomers) {
            tempCount = window.currentCustomers.filter(c =>
                c.assigned_tech_id === tech.id && c.has_temp_assignment
            ).length;
            if (tempCount > 0) {
                console.log(`Tech ${tech.name} has ${tempCount} temp assignments`);
            }
        }

        // Check if this tech is currently selected
        const isSelected = resetSelection ? true : selectedTechIds.has(tech.id);

        // Add to selectedTechIds if resetting selection
        if (resetSelection) {
            selectedTechIds.add(tech.id);
        }

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = isSelected ? 'tech-chip-wrapper selected' : 'tech-chip-wrapper unselected';
        wrapper.dataset.techId = tech.id;

        const techColor = tech.color || '#3498db';

        // Add border color
        wrapper.style.borderColor = techColor;

        // Convert hex to rgba for lighter background
        const hex = techColor.replace('#', '');
        const r = parseInt(hex.substr(0, 2), 16);
        const g = parseInt(hex.substr(2, 2), 16);
        const b = parseInt(hex.substr(4, 2), 16);

        // Add background to entire wrapper
        wrapper.style.backgroundColor = `rgba(${r}, ${g}, ${b}, 0.25)`;

        // Create name span
        const nameSpan = document.createElement('span');
        nameSpan.className = 'tech-chip-name';
        nameSpan.style.color = techColor;
        nameSpan.textContent = tech.name;

        // Create count badge with full color
        const badge = document.createElement('span');
        badge.className = 'tech-chip-badge';
        badge.style.backgroundColor = techColor;

        // Display count with temp assignments if any
        if (tempCount > 0) {
            badge.innerHTML = `${stopCount} <span style="color: #ff8800;">+${tempCount}</span>`;
        } else {
            badge.textContent = stopCount;
        }

        wrapper.appendChild(nameSpan);
        wrapper.appendChild(badge);

        // Click handler with Ctrl detection
        wrapper.addEventListener('click', function(e) {
            toggleTechSelection(tech.id, e.ctrlKey || e.metaKey);
        });

        // Long-press handler for mobile multi-select
        let pressTimer;
        wrapper.addEventListener('touchstart', function(e) {
            pressTimer = setTimeout(function() {
                toggleTechSelection(tech.id, true);
            }, 500);
        });
        wrapper.addEventListener('touchend', function() {
            clearTimeout(pressTimer);
        });
        wrapper.addEventListener('touchmove', function() {
            clearTimeout(pressTimer);
        });

        container.appendChild(wrapper);
    });

    // Add unassigned container if there are unassigned customers
    if (window.unassignedCustomerCount && window.unassignedCustomerCount > 0) {
        const isUnassignedSelected = resetSelection ? true : selectedTechIds.has('unassigned');

        if (resetSelection) {
            selectedTechIds.add('unassigned');
        }

        // Create container
        const wrapper = document.createElement('div');
        wrapper.className = isUnassignedSelected ? 'unassigned-container selected' : 'unassigned-container unselected';
        wrapper.dataset.techId = 'unassigned';

        // Create name span
        const nameSpan = document.createElement('span');
        nameSpan.className = 'unassigned-name';
        nameSpan.textContent = 'Unassigned';

        // Create count badge
        const countSpan = document.createElement('span');
        countSpan.className = 'unassigned-count';
        countSpan.textContent = window.unassignedCustomerCount;

        wrapper.appendChild(nameSpan);
        wrapper.appendChild(countSpan);

        wrapper.addEventListener('click', function(e) {
            toggleTechSelection('unassigned', e.ctrlKey || e.metaKey);
        });

        container.appendChild(wrapper);
    }
}

function toggleAllTechs() {
    const allToggle = document.getElementById('all-toggle');
    const isChecked = allToggle.checked;

    if (isChecked) {
        // Select all
        selectedTechIds.clear();

        allTechs.forEach(tech => {
            selectedTechIds.add(tech.id);
            const wrapper = document.querySelector(`.tech-chip-wrapper[data-tech-id="${tech.id}"]`);
            if (wrapper) {
                wrapper.classList.remove('unselected');
                wrapper.classList.add('selected');
            }
        });

        // Select unassigned if exists
        selectedTechIds.add('unassigned');
        const unassignedWrapper = document.querySelector(`.unassigned-container[data-tech-id="unassigned"]`);
        if (unassignedWrapper) {
            unassignedWrapper.classList.remove('unselected');
            unassignedWrapper.classList.add('selected');
        }
    } else {
        // Deselect all
        selectedTechIds.clear();

        allTechs.forEach(tech => {
            const wrapper = document.querySelector(`.tech-chip-wrapper[data-tech-id="${tech.id}"]`);
            if (wrapper) {
                wrapper.classList.remove('selected');
                wrapper.classList.add('unselected');
            }
        });

        // Deselect unassigned if exists
        const unassignedWrapper = document.querySelector(`.unassigned-container[data-tech-id="unassigned"]`);
        if (unassignedWrapper) {
            unassignedWrapper.classList.remove('selected');
            unassignedWrapper.classList.add('unselected');
        }
    }

    filterRoutesByTechs();
}

function toggleTechSelection(techId, multiSelect = false) {
    const wrapper = document.querySelector(`.tech-chip-wrapper[data-tech-id="${techId}"], .unassigned-container[data-tech-id="${techId}"]`);
    if (!wrapper) return;

    const allToggle = document.getElementById('all-toggle');

    if (multiSelect) {
        // Multi-select mode: toggle this tech only
        if (selectedTechIds.has(techId)) {
            selectedTechIds.delete(techId);
            wrapper.classList.remove('selected');
            wrapper.classList.add('unselected');
        } else {
            selectedTechIds.add(techId);
            wrapper.classList.remove('unselected');
            wrapper.classList.add('selected');
        }
    } else {
        // Single-select mode: deselect all others, select only this one
        selectedTechIds.clear();

        // Deselect all tech wrappers
        allTechs.forEach(tech => {
            const otherWrapper = document.querySelector(`.tech-chip-wrapper[data-tech-id="${tech.id}"]`);
            if (otherWrapper) {
                otherWrapper.classList.remove('selected');
                otherWrapper.classList.add('unselected');
            }
        });

        // Deselect unassigned if exists
        const unassignedWrapper = document.querySelector(`.unassigned-container[data-tech-id="unassigned"]`);
        if (unassignedWrapper) {
            unassignedWrapper.classList.remove('selected');
            unassignedWrapper.classList.add('unselected');
        }

        // Select only this tech
        selectedTechIds.add(techId);
        wrapper.classList.remove('unselected');
        wrapper.classList.add('selected');
    }

    // Update All toggle state
    if (allToggle) {
        // All is checked if all techs are selected AND unassigned is selected (if it exists)
        const allTechsSelected = allTechs.every(tech => selectedTechIds.has(tech.id));
        const unassignedSelected = window.unassignedCustomerCount > 0 ? selectedTechIds.has('unassigned') : true;
        allToggle.checked = allTechsSelected && unassignedSelected;
    }

    filterRoutesByTechs();
}

async function filterRoutesByTechs() {
    // Reload customers FIRST to update map with filtered techs and temp assignments
    await loadCustomers();

    // Re-filter and redisplay routes if they exist
    if (currentRouteResult && currentRouteResult.routes) {
        displayRoutes(currentRouteResult);
        displayRoutesOnMap(currentRouteResult.routes);
    } else {
        // Reload persistent tech routes for the selected day
        await loadTechRoutesForDay(selectedDay);
    }
}

function displayTechs(techs) {
    const container = document.getElementById('techs-list');

    if (!techs || techs.length === 0) {
        container.innerHTML = '<p class="placeholder">No techs configured. Add a tech to get started.</p>';
        return;
    }

    container.innerHTML = '';

    // Apply filters
    const searchTerm = document.getElementById('team-search')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('team-status-filter')?.value || 'active';
    const workloadFilter = document.getElementById('team-workload-filter')?.value || 'all';

    const filteredTechs = techs.filter(tech => {
        // Search filter
        if (searchTerm && !tech.name.toLowerCase().includes(searchTerm)) {
            return false;
        }

        // Status filter
        if (statusFilter === 'active' && !tech.is_active) return false;
        if (statusFilter === 'inactive' && tech.is_active) return false;

        // Workload filter
        const customerCount = tech.customer_count || 0;
        if (workloadFilter === 'high' && customerCount <= 30) return false;
        if (workloadFilter === 'medium' && (customerCount < 15 || customerCount > 30)) return false;
        if (workloadFilter === 'low' && customerCount >= 15) return false;

        return true;
    });

    if (filteredTechs.length === 0) {
        container.innerHTML = '<p class="placeholder">No team members match your filters</p>';
        return;
    }

    filteredTechs.forEach(tech => {
        const initials = tech.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
        const customerCount = tech.customer_count || 0;
        const maxCustomers = tech.max_customers_per_day || 50;
        const workloadPercent = Math.min(100, Math.round((customerCount / maxCustomers) * 100));
        const efficiencyMultiplier = tech.efficiency_multiplier || 1.0;
        const statusBadge = tech.is_active
            ? '<span class="status-badge status-active">Active</span>'
            : '<span class="status-badge status-inactive">Inactive</span>';

        // Workload indicator color
        let workloadColor = '#27ae60'; // green
        if (workloadPercent > 80) workloadColor = '#e74c3c'; // red
        else if (workloadPercent > 60) workloadColor = '#f39c12'; // orange

        const driverCard = document.createElement('div');
        driverCard.className = 'tech-card-enhanced';
        driverCard.dataset.techId = tech.id;
        driverCard.dataset.customerCount = customerCount;

        driverCard.innerHTML = `
            <div class="tech-card-header">
                <div class="tech-avatar" style="background-color: ${tech.color || '#3498db'}">
                    ${initials}
                </div>
                <div class="tech-header-info">
                    <div class="tech-name-row">
                        <h3>${tech.name}</h3>
                        ${statusBadge}
                    </div>
                    <div class="tech-contact">
                        ${tech.phone ? `<span>📞 ${tech.phone}</span>` : ''}
                        ${tech.email ? `<span>✉️ ${tech.email}</span>` : ''}
                    </div>
                </div>
                <button class="context-menu-btn" onclick="toggleContextMenu(event, 'tech-${tech.id}')">⋮</button>
                <div id="menu-tech-${tech.id}" class="context-menu">
                    <button onclick="showEditTechForm('${tech.id}'); closeAllContextMenus();">Edit</button>
                    <button onclick="deleteTech('${tech.id}'); closeAllContextMenus();" class="delete">Delete</button>
                </div>
            </div>

            <div class="tech-card-body">
                <div class="tech-stats-grid">
                    <div class="tech-stat">
                        <span class="stat-label">Customers</span>
                        <span class="stat-value">${customerCount}</span>
                    </div>
                    <div class="tech-stat">
                        <span class="stat-label">Max/Day</span>
                        <span class="stat-value">${maxCustomers}</span>
                    </div>
                    <div class="tech-stat">
                        <span class="stat-label">Efficiency</span>
                        <span class="stat-value">${efficiencyMultiplier}x</span>
                    </div>
                    <div class="tech-stat">
                        <span class="stat-label">Hours</span>
                        <span class="stat-value">${tech.working_hours_start}-${tech.working_hours_end}</span>
                    </div>
                </div>

                <div class="workload-indicator">
                    <div class="workload-label">
                        <span>Workload</span>
                        <span>${workloadPercent}%</span>
                    </div>
                    <div class="workload-bar">
                        <div class="workload-fill" style="width: ${workloadPercent}%; background-color: ${workloadColor}"></div>
                    </div>
                </div>

                ${tech.start_location_address ? `
                <div class="tech-location">
                    <span class="location-label">📍 Depot:</span>
                    <span class="location-address">${tech.start_location_address.split(',')[0]}</span>
                </div>
                ` : ''}
            </div>

            <div class="tech-card-actions">
                <button class="btn-action" onclick="viewTechCustomers('${tech.id}')" title="View Customers">
                    <span>👥</span> Customers
                </button>
                <button class="btn-action" onclick="viewTechRoutes('${tech.id}')" title="View Routes">
                    <span>🗺️</span> Routes
                </button>
                <button class="btn-action" onclick="showEditTechForm('${tech.id}')" title="Edit">
                    <span>✏️</span> Edit
                </button>
            </div>
        `;
        container.appendChild(driverCard);
    });
}

function createColorPickerButton(selectedColor = '#3498db', inputId = 'tech-color') {
    return `
        <button type="button" class="color-picker-button-square" id="${inputId}-button" style="background-color: ${selectedColor};" title="Click to change color">
        </button>
        <input type="hidden" id="${inputId}" value="${selectedColor}">
    `;
}

function openColorPickerModal(inputId) {
    const currentColor = document.getElementById(inputId).value;

    const colorsHtml = TECH_COLORS.map(color => `
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

function showAddTechForm() {
    const container = document.getElementById('techs-list');

    const formHtml = `
        <div class="tech-form-header">
            <h3>Add New Team Member</h3>
            <div class="form-actions">
                <button class="btn-primary" onclick="saveTech()">Save Team Member</button>
                <button class="btn-secondary" onclick="loadTechs()">Cancel</button>
            </div>
        </div>
        <div class="tech-form">
            <div class="form-section">
                <h4>Basic Information</h4>
                <div class="form-row">
                    <div class="control-group control-group-large">
                        <label>Name:</label>
                        <input type="text" id="tech-name" placeholder="Team Member Name">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>Color:</label>
                        ${createColorPickerButton('#3498db', 'tech-color')}
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Start Location</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="tech-start-street" placeholder="123 Main Street">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="tech-start-city" placeholder="Sacramento">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="tech-start-state" placeholder="CA" maxlength="2">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="tech-start-zip" placeholder="95814" maxlength="10">
                    </div>
                </div>
                <input type="hidden" id="tech-start-location">
            </div>

            <div class="form-section">
                <h4>End Location</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="tech-end-street" placeholder="123 Main Street">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="tech-end-city" placeholder="Sacramento">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="tech-end-state" placeholder="CA" maxlength="2">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="tech-end-zip" placeholder="95814" maxlength="10">
                    </div>
                </div>
                <input type="hidden" id="tech-end-location">
            </div>

            <div class="form-section">
                <h4>Working Hours & Capacity</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Start Time:</label>
                        <input type="time" id="tech-start-time" value="08:00">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>End Time:</label>
                        <input type="time" id="tech-end-time" value="17:00">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Max Customers/Day:</label>
                        <input type="number" id="tech-max-customers" min="1" max="50" value="20">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Efficiency Multiplier:</label>
                        <input type="number" id="tech-efficiency" min="0.1" max="5.0" step="0.1" value="1.0" title="1.0 = normal, 1.5 = 50% more efficient">
                    </div>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = formHtml;

    // Hide add tech button during add form
    const addBtn = document.getElementById('add-tech-btn');
    if (addBtn) addBtn.style.display = 'none';

    // Initialize color picker button
    const colorButton = document.getElementById('tech-color-button');
    if (colorButton) {
        colorButton.addEventListener('click', () => openColorPickerModal('tech-color'));
    }

    // Initialize autocomplete on street address fields
    setTimeout(() => {
        const startStreetInput = document.getElementById('tech-start-street');
        const endStreetInput = document.getElementById('tech-end-street');
        if (startStreetInput) initAutocomplete(startStreetInput);
        if (endStreetInput) initAutocomplete(endStreetInput);
    }, 100);
}

async function saveTech() {
    const name = document.getElementById('tech-name').value;
    const color = document.getElementById('tech-color').value;

    const startStreet = document.getElementById('tech-start-street').value;
    const startCity = document.getElementById('tech-start-city').value;
    const startState = document.getElementById('tech-start-state').value;
    const startZip = document.getElementById('tech-start-zip').value;
    const startLocation = combineAddressFields(startStreet, startCity, startState, startZip);

    const endStreet = document.getElementById('tech-end-street').value;
    const endCity = document.getElementById('tech-end-city').value;
    const endState = document.getElementById('tech-end-state').value;
    const endZip = document.getElementById('tech-end-zip').value;
    const endLocation = combineAddressFields(endStreet, endCity, endState, endZip);

    const startTime = document.getElementById('tech-start-time').value;
    const endTime = document.getElementById('tech-end-time').value;
    const maxCustomers = parseInt(document.getElementById('tech-max-customers').value);
    const efficiencyMultiplier = parseFloat(document.getElementById('tech-efficiency').value) || 1.0;

    if (!name || !startLocation || !endLocation) {
        alert('Please fill in all required fields');
        return;
    }

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/techs/`, {
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
                max_customers_per_day: maxCustomers,
                efficiency_multiplier: efficiencyMultiplier
            })
        });

        if (!response.ok) {
            throw new Error('Failed to create tech');
        }

        alert('Tech created successfully!');
        loadTechs();
    } catch (error) {
        console.error('Error creating tech:', error);
        alert('Failed to create tech. Please try again.');
    }
}

async function deleteTech(techId) {
    if (!confirm('Are you sure you want to delete this tech?')) {
        return;
    }

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/techs/${techId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete tech');
        }

        loadTechs();
    } catch (error) {
        console.error('Error deleting tech:', error);
        alert('Failed to delete tech. Please try again.');
    }
}

async function showEditTechForm(techId) {
    const container = document.getElementById('techs-list');

    // Fetch tech data
    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/techs/${techId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch tech');
        }

        const tech = await response.json();

        const startAddr = parseAddress(tech.start_location_address || '');
        const endAddr = parseAddress(tech.end_location_address || '');

        const formHtml = `
            <div class="tech-form-header">
                <h3>Edit Team Member</h3>
                <div class="form-actions">
                    <button class="btn-primary" onclick="updateTech('${techId}')">Update Team Member</button>
                    <button class="btn-secondary" onclick="loadTechs()">Cancel</button>
                </div>
            </div>
            <div class="tech-form">
                <div class="form-section">
                    <h4>Basic Information</h4>
                    <div class="form-row">
                        <div class="control-group control-group-large">
                            <label>Name:</label>
                            <input type="text" id="edit-tech-name" value="${tech.name}">
                        </div>
                        <div class="control-group control-group-narrow">
                            <label>Color:</label>
                            ${createColorPickerButton(tech.color || '#3498db', 'edit-tech-color')}
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h4>Start Location</h4>
                    <div class="form-row">
                        <div class="control-group" style="flex: 3;">
                            <label>Street:</label>
                            <input type="text" id="edit-tech-start-street" value="${startAddr.street}" placeholder="123 Main Street">
                        </div>
                        <div class="control-group" style="flex: 2;">
                            <label>City:</label>
                            <input type="text" id="edit-tech-start-city" value="${startAddr.city}" placeholder="Sacramento">
                        </div>
                        <div class="control-group control-group-narrow">
                            <label>State:</label>
                            <input type="text" id="edit-tech-start-state" value="${startAddr.state}" placeholder="CA" maxlength="2">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Zip:</label>
                            <input type="text" id="edit-tech-start-zip" value="${startAddr.zip}" placeholder="95814" maxlength="10">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h4>End Location</h4>
                    <div class="form-row">
                        <div class="control-group" style="flex: 3;">
                            <label>Street:</label>
                            <input type="text" id="edit-tech-end-street" value="${endAddr.street}" placeholder="123 Main Street">
                        </div>
                        <div class="control-group" style="flex: 2;">
                            <label>City:</label>
                            <input type="text" id="edit-tech-end-city" value="${endAddr.city}" placeholder="Sacramento">
                        </div>
                        <div class="control-group control-group-narrow">
                            <label>State:</label>
                            <input type="text" id="edit-tech-end-state" value="${endAddr.state}" placeholder="CA" maxlength="2">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Zip:</label>
                            <input type="text" id="edit-tech-end-zip" value="${endAddr.zip}" placeholder="95814" maxlength="10">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h4>Working Hours & Capacity</h4>
                    <div class="form-row">
                        <div class="control-group control-group-medium">
                            <label>Start Time:</label>
                            <input type="time" id="edit-tech-start-time" value="${tech.working_hours_start ? tech.working_hours_start.substring(0, 5) : '08:00'}">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>End Time:</label>
                            <input type="time" id="edit-tech-end-time" value="${tech.working_hours_end ? tech.working_hours_end.substring(0, 5) : '17:00'}">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Max Customers/Day:</label>
                            <input type="number" id="edit-tech-max-customers" min="1" max="50" value="${tech.max_customers_per_day || 20}">
                        </div>
                        <div class="control-group control-group-medium">
                            <label>Efficiency Multiplier:</label>
                            <input type="number" id="edit-tech-efficiency" min="0.1" max="5.0" step="0.1" value="${tech.efficiency_multiplier || 1.0}" title="1.0 = normal, 1.5 = 50% more efficient">
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = formHtml;

        // Hide add tech button during edit
        const addBtn = document.getElementById('add-tech-btn');
        if (addBtn) addBtn.style.display = 'none';

        // Initialize color picker button
        const colorButton = document.getElementById('edit-tech-color-button');
        if (colorButton) {
            colorButton.addEventListener('click', () => openColorPickerModal('edit-tech-color'));
        }

        // Initialize autocomplete on street address fields
        setTimeout(() => {
            const startStreetInput = document.getElementById('edit-tech-start-street');
            const endStreetInput = document.getElementById('edit-tech-end-street');
            if (startStreetInput) initAutocomplete(startStreetInput);
            if (endStreetInput) initAutocomplete(endStreetInput);
        }, 100);

    } catch (error) {
        console.error('Error loading tech for edit:', error);
        alert('Failed to load tech data. Please try again.');
    }
}

async function updateTech(techId) {
    const name = document.getElementById('edit-tech-name').value;
    const color = document.getElementById('edit-tech-color').value;

    const startStreet = document.getElementById('edit-tech-start-street').value;
    const startCity = document.getElementById('edit-tech-start-city').value;
    const startState = document.getElementById('edit-tech-start-state').value;
    const startZip = document.getElementById('edit-tech-start-zip').value;
    const startLocation = combineAddressFields(startStreet, startCity, startState, startZip);

    const endStreet = document.getElementById('edit-tech-end-street').value;
    const endCity = document.getElementById('edit-tech-end-city').value;
    const endState = document.getElementById('edit-tech-end-state').value;
    const endZip = document.getElementById('edit-tech-end-zip').value;
    const endLocation = combineAddressFields(endStreet, endCity, endState, endZip);

    const startTime = document.getElementById('edit-tech-start-time').value;
    const endTime = document.getElementById('edit-tech-end-time').value;
    const maxCustomers = parseInt(document.getElementById('edit-tech-max-customers').value);
    const efficiencyMultiplier = parseFloat(document.getElementById('edit-tech-efficiency').value) || 1.0;

    if (!name || !startLocation || !endLocation) {
        alert('Please fill in all required fields');
        return;
    }

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/techs/${techId}`, {
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
                max_customers_per_day: maxCustomers,
                efficiency_multiplier: efficiencyMultiplier
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update tech');
        }

        alert('Tech updated successfully!');
        loadTechs();
    } catch (error) {
        console.error('Error updating tech:', error);
        alert('Failed to update tech. Please try again.');
    }
}

// Helper functions for quick actions
function viewTechCustomers(techId) {
    // Navigate to clients module and filter by tech
    const navItem = document.querySelector('[data-module="clients"]');
    if (navItem) {
        navItem.click();
        
        // Wait for module to load, then apply filter
        setTimeout(() => {
            const techFilter = document.getElementById('filter-assigned-tech');
            if (techFilter) {
                techFilter.value = techId;
                techFilter.dispatchEvent(new Event('change'));
            }
        }, 200);
    }
}

function viewTechRoutes(techId) {
    // Navigate to routes module and select tech
    const navItem = document.querySelector('[data-module="routes"]');
    if (navItem) {
        navItem.click();
        
        // Wait for module to load, then select only this tech
        setTimeout(() => {
            selectedTechIds.clear();
            selectedTechIds.add(techId);
            
            // Update visual selection
            document.querySelectorAll('.tech-chip-wrapper').forEach(wrapper => {
                if (wrapper.dataset.techId === techId) {
                    wrapper.classList.add('selected');
                    wrapper.classList.remove('unselected');
                } else {
                    wrapper.classList.remove('selected');
                    wrapper.classList.add('unselected');
                }
            });
            
            // Reload routes for this tech
            filterRoutesByTechs();
        }, 200);
    }
}

// Event listeners for filters
document.addEventListener('DOMContentLoaded', function() {
    const teamSearch = document.getElementById('team-search');
    const statusFilter = document.getElementById('team-status-filter');
    const workloadFilter = document.getElementById('team-workload-filter');
    
    if (teamSearch) {
        teamSearch.addEventListener('input', () => {
            if (allTechs && allTechs.length > 0) {
                displayTechs(allTechs);
            }
        });
    }
    
    if (statusFilter) {
        statusFilter.addEventListener('change', () => {
            if (allTechs && allTechs.length > 0) {
                displayTechs(allTechs);
            }
        });
    }
    
    if (workloadFilter) {
        workloadFilter.addEventListener('change', () => {
            if (allTechs && allTechs.length > 0) {
                displayTechs(allTechs);
            }
        });
    }
});
