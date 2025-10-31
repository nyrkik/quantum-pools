// RouteOptimizer - Techs Module
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
        // Create wrapper for label + badge button
        const wrapper = document.createElement('div');
        wrapper.className = 'tech-chip-wrapper';

        // Calculate stop count
        let stopCount = 0;

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

        // Check if this tech is currently selected
        const isSelected = resetSelection ? true : selectedTechIds.has(tech.id);

        // Add to selectedTechIds if resetting selection
        if (resetSelection) {
            selectedTechIds.add(tech.id);
        }

        // Create name label (clickable)
        const nameLabel = document.createElement('span');
        nameLabel.className = isSelected ? 'tech-chip-label selected' : 'tech-chip-label';
        nameLabel.dataset.techId = tech.id;
        nameLabel.style.color = tech.color || '#3498db';
        nameLabel.textContent = tech.name;

        // Create count badge button (clickable)
        const badge = document.createElement('button');
        badge.className = isSelected ? 'tech-chip-badge selected' : 'tech-chip-badge unselected';
        badge.dataset.techId = tech.id;
        badge.style.backgroundColor = tech.color || '#3498db';
        badge.style.opacity = isSelected ? '1' : '0.3';
        badge.textContent = stopCount > 0 ? stopCount : '0';

        wrapper.appendChild(nameLabel);
        wrapper.appendChild(badge);

        // Click handler with Ctrl detection for both label and badge
        const clickHandler = function(e) {
            toggleTechSelection(tech.id, e.ctrlKey || e.metaKey);
        };
        nameLabel.addEventListener('click', clickHandler);
        badge.addEventListener('click', clickHandler);

        // Long-press handler for mobile multi-select
        let pressTimer;
        badge.addEventListener('touchstart', function(e) {
            pressTimer = setTimeout(function() {
                toggleTechSelection(tech.id, true); // true = multi-select mode
            }, 500); // 500ms for long-press
        });
        badge.addEventListener('touchend', function() {
            clearTimeout(pressTimer);
        });
        badge.addEventListener('touchmove', function() {
            clearTimeout(pressTimer);
        });

        container.appendChild(wrapper);
    });

    // Add unassigned chip if there are unassigned customers
    if (window.unassignedCustomerCount && window.unassignedCustomerCount > 0) {
        const wrapper = document.createElement('div');
        wrapper.className = 'tech-chip-wrapper';

        const isUnassignedSelected = resetSelection ? true : selectedTechIds.has('unassigned');

        if (resetSelection) {
            selectedTechIds.add('unassigned');
        }

        const nameLabel = document.createElement('span');
        nameLabel.className = isUnassignedSelected ? 'tech-chip-label selected' : 'tech-chip-label';
        nameLabel.dataset.techId = 'unassigned';
        nameLabel.style.color = '#e74c3c';
        nameLabel.textContent = 'Unassigned';

        const badge = document.createElement('button');
        badge.className = isUnassignedSelected ? 'tech-chip-badge selected unassigned-badge' : 'tech-chip-badge unselected unassigned-badge';
        badge.dataset.techId = 'unassigned';
        badge.style.backgroundColor = '#e74c3c';
        badge.style.opacity = isUnassignedSelected ? '1' : '0.3';
        badge.textContent = window.unassignedCustomerCount;

        wrapper.appendChild(nameLabel);
        wrapper.appendChild(badge);

        const clickHandler = function(e) {
            toggleTechSelection('unassigned', e.ctrlKey || e.metaKey);
        };
        nameLabel.addEventListener('click', clickHandler);
        badge.addEventListener('click', clickHandler);

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
            const badge = document.querySelector(`.tech-chip-badge[data-tech-id="${tech.id}"]`);
            const label = document.querySelector(`.tech-chip-label[data-tech-id="${tech.id}"]`);
            if (badge) {
                badge.classList.remove('unselected');
                badge.classList.add('selected');
                badge.style.opacity = '1';
            }
            if (label) {
                label.classList.add('selected');
            }
        });

        // Select unassigned if exists
        selectedTechIds.add('unassigned');
        const unassignedBadge = document.querySelector(`.tech-chip-badge[data-tech-id="unassigned"]`);
        const unassignedLabel = document.querySelector(`.tech-chip-label[data-tech-id="unassigned"]`);
        if (unassignedBadge) {
            unassignedBadge.classList.remove('unselected');
            unassignedBadge.classList.add('selected');
            unassignedBadge.style.opacity = '1';
        }
        if (unassignedLabel) {
            unassignedLabel.classList.add('selected');
        }
    } else {
        // Deselect all
        selectedTechIds.clear();

        allTechs.forEach(tech => {
            const badge = document.querySelector(`.tech-chip-badge[data-tech-id="${tech.id}"]`);
            const label = document.querySelector(`.tech-chip-label[data-tech-id="${tech.id}"]`);
            if (badge) {
                badge.classList.remove('selected');
                badge.classList.add('unselected');
                badge.style.opacity = '0.3';
            }
            if (label) {
                label.classList.remove('selected');
            }
        });

        // Deselect unassigned if exists
        const unassignedBadge = document.querySelector(`.tech-chip-badge[data-tech-id="unassigned"]`);
        const unassignedLabel = document.querySelector(`.tech-chip-label[data-tech-id="unassigned"]`);
        if (unassignedBadge) {
            unassignedBadge.classList.remove('selected');
            unassignedBadge.classList.add('unselected');
            unassignedBadge.style.opacity = '0.3';
        }
        if (unassignedLabel) {
            unassignedLabel.classList.remove('selected');
        }
    }

    filterRoutesByTechs();
}

function toggleTechSelection(techId, multiSelect = false) {
    const badge = document.querySelector(`.tech-chip-badge[data-tech-id="${techId}"]`);
    const label = document.querySelector(`.tech-chip-label[data-tech-id="${techId}"]`);
    if (!badge) return;

    const allToggle = document.getElementById('all-toggle');

    if (multiSelect) {
        // Multi-select mode: toggle this tech only
        if (selectedTechIds.has(techId)) {
            selectedTechIds.delete(techId);
            badge.classList.remove('selected');
            badge.classList.add('unselected');
            badge.style.opacity = '0.3';
            if (label) label.classList.remove('selected');
        } else {
            selectedTechIds.add(techId);
            badge.classList.remove('unselected');
            badge.classList.add('selected');
            badge.style.opacity = '1';
            if (label) label.classList.add('selected');
        }
    } else {
        // Single-select mode: deselect all others, select only this one
        selectedTechIds.clear();

        // Deselect all badges and labels
        allTechs.forEach(tech => {
            const otherBadge = document.querySelector(`.tech-chip-badge[data-tech-id="${tech.id}"]`);
            const otherLabel = document.querySelector(`.tech-chip-label[data-tech-id="${tech.id}"]`);
            if (otherBadge) {
                otherBadge.classList.remove('selected');
                otherBadge.classList.add('unselected');
                otherBadge.style.opacity = '0.3';
            }
            if (otherLabel) {
                otherLabel.classList.remove('selected');
            }
        });

        // Deselect unassigned if exists
        const unassignedBadge = document.querySelector(`.tech-chip-badge[data-tech-id="unassigned"]`);
        const unassignedLabel = document.querySelector(`.tech-chip-label[data-tech-id="unassigned"]`);
        if (unassignedBadge) {
            unassignedBadge.classList.remove('selected');
            unassignedBadge.classList.add('unselected');
            unassignedBadge.style.opacity = '0.3';
        }
        if (unassignedLabel) {
            unassignedLabel.classList.remove('selected');
        }

        // Select only this tech
        selectedTechIds.add(techId);
        badge.classList.remove('unselected');
        badge.classList.add('selected');
        badge.style.opacity = '1';
        if (label) label.classList.add('selected');
    }

    // Update All toggle state
    if (allToggle) {
        allToggle.checked = (selectedTechIds.size === allTechs.length);
    }

    filterRoutesByTechs();
}

function filterRoutesByTechs() {
    // Reload customers to update map with filtered techs
    loadCustomers();

    // Re-filter and redisplay routes if they exist
    if (currentRouteResult && currentRouteResult.routes) {
        displayRoutes(currentRouteResult);
        displayRoutesOnMap(currentRouteResult.routes);
    }
}

function displayTechs(techs) {
    const container = document.getElementById('techs-list');

    if (!techs || techs.length === 0) {
        container.innerHTML = '<p class="placeholder">No techs configured. Add a tech to get started.</p>';
        return;
    }

    container.innerHTML = '';
    techs.forEach(tech => {
        const driverCard = document.createElement('div');
        driverCard.className = 'tech-card';
        driverCard.innerHTML = `
            <div class="tech-color-indicator" style="background-color: ${tech.color || '#3498db'}"></div>
            <div class="tech-info">
                <strong>${tech.name}</strong>
                <small>${tech.working_hours_start} - ${tech.working_hours_end}</small>
                <small>Max: ${tech.max_customers_per_day} customers/day</small>
            </div>
            <button class="context-menu-btn" onclick="toggleContextMenu(event, 'tech-${tech.id}')">⋮</button>
            <div id="menu-tech-${tech.id}" class="context-menu">
                <button onclick="showEditTechForm('${tech.id}'); closeAllContextMenus();">Edit</button>
                <button onclick="deleteTech('${tech.id}'); closeAllContextMenus();" class="delete">Delete</button>
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
                max_customers_per_day: maxCustomers
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
                max_customers_per_day: maxCustomers
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
