// RouteOptimizer - Drivers Module
//
// Handles driver/team member management, tech chips, and color picker
// Dependencies: API_BASE, allDrivers, selectedDriverIds globals, filterRoutesByDrivers(), loadCustomers(), displayRoutes(), displayRoutesOnMap(), combineAddressFields(), parseAddress(), initAutocomplete()

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
