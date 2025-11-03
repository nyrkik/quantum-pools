// QuantumPools - Modals Module
//
// Handles modal dialogs and context menus
// Dependencies: optimizeRoutes() function from app.js

/**
 * Opens a modal dialog by adding the 'active' class
 * @param {string} modalId - The ID of the modal to open
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

/**
 * Closes a modal dialog by removing the 'active' class
 * @param {string} modalId - The ID of the modal to close
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Initializes the route optimization modal
 * Sets up event listeners for opening, closing, and running optimization
 */
function initOptimizationModal() {
    const modal = document.getElementById('optimize-modal');
    const optimizeBtn = document.getElementById('optimize-btn');
    const runOptimizeBtn = document.getElementById('run-optimize-btn');
    const closeBtn = modal.querySelector('.modal-close');
    const scopeInputs = document.querySelectorAll('input[name="optimization-scope"]');
    const customerLockSection = document.getElementById('customer-lock-section');
    const techAssignmentSection = document.getElementById('tech-assignment-section');

    // Open modal when clicking "Optimize Routes" button
    optimizeBtn.addEventListener('click', async function() {
        // Load tech selection checkboxes
        loadTechSelection();

        // Load customer list for complete rerouting
        await loadCustomerLockList();

        openModal('optimize-modal');
    });

    // Handle scope change
    scopeInputs.forEach(input => {
        input.addEventListener('change', function() {
            if (this.value === 'complete_rerouting') {
                customerLockSection.style.display = 'block';
                techAssignmentSection.style.display = 'none';
            } else {
                customerLockSection.style.display = 'none';
                techAssignmentSection.style.display = 'block';
            }
        });
    });

    // Lock/Unlock All buttons
    document.getElementById('lock-all-btn').addEventListener('click', function() {
        document.querySelectorAll('.customer-lock-toggle').forEach(btn => {
            btn.dataset.locked = 'true';
            btn.textContent = '🔒';
            btn.title = 'Locked - Click to unlock';
        });
    });

    document.getElementById('unlock-all-btn').addEventListener('click', function() {
        document.querySelectorAll('.customer-lock-toggle').forEach(btn => {
            btn.dataset.locked = 'false';
            btn.textContent = '🔓';
            btn.title = 'Unlocked - Click to lock';
        });
    });

    // Close modal when clicking X
    closeBtn.addEventListener('click', function() {
        closeModal('optimize-modal');
    });

    // Close modal when clicking outside
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal('optimize-modal');
        }
    });

    // Run optimization and close modal
    runOptimizeBtn.addEventListener('click', async function() {
        closeModal('optimize-modal');
        await optimizeRoutes();
    });
}

function loadTechSelection() {
    const container = document.getElementById('opt-tech-selection');
    container.innerHTML = '';

    if (!allTechs || allTechs.length === 0) {
        container.innerHTML = '<p style="color: #999;">No techs available</p>';
        return;
    }

    allTechs.forEach(tech => {
        const row = document.createElement('div');
        row.style.padding = '0.5rem';
        row.style.borderBottom = '1px solid #eee';
        row.style.display = 'flex';
        row.style.alignItems = 'center';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'tech-select-checkbox';
        checkbox.dataset.techId = tech.id;
        checkbox.checked = selectedTechIds.has(tech.id);
        checkbox.style.marginRight = '0.5rem';

        // Handle checkbox change
        checkbox.addEventListener('change', function() {
            if (this.checked) {
                selectedTechIds.add(tech.id);
                // Remove unassigned if selecting a tech
                selectedTechIds.delete('unassigned');
            } else {
                selectedTechIds.delete(tech.id);
            }

            // Update main tech chips display
            if (typeof populateTechChips === 'function' && allTechs) {
                populateTechChips(allTechs, false);
            }
        });

        const colorIndicator = document.createElement('span');
        colorIndicator.style.display = 'inline-block';
        colorIndicator.style.width = '12px';
        colorIndicator.style.height = '12px';
        colorIndicator.style.borderRadius = '50%';
        colorIndicator.style.backgroundColor = tech.color || '#3498db';
        colorIndicator.style.marginRight = '0.5rem';

        const label = document.createElement('label');
        label.style.flex = '1';
        label.style.cursor = 'pointer';
        label.style.fontSize = '0.9rem';
        label.textContent = tech.name;
        label.addEventListener('click', () => {
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event('change'));
        });

        row.appendChild(checkbox);
        row.appendChild(colorIndicator);
        row.appendChild(label);
        container.appendChild(row);
    });
}

async function loadCustomerLockList() {
    const container = document.getElementById('customer-lock-list');

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers?page_size=1000&status=active,pending`);
        if (!response.ok) return;

        const data = await response.json();
        const customers = data.customers || [];

        container.innerHTML = '';

        if (customers.length === 0) {
            container.innerHTML = '<p style="color: #999;">No customers found</p>';
            return;
        }

        customers.forEach(customer => {
            const row = document.createElement('div');
            row.style.padding = '0.5rem';
            row.style.borderBottom = '1px solid #eee';
            row.style.display = 'flex';
            row.style.alignItems = 'center';
            row.style.gap = '0.5rem';

            // Determine initial lock status (locked if customer.locked is true)
            const isLocked = customer.locked === true;

            // Lock/unlock icon button
            const lockButton = document.createElement('button');
            lockButton.type = 'button';
            lockButton.className = 'customer-lock-toggle';
            lockButton.dataset.customerId = customer.id;
            lockButton.dataset.locked = isLocked;
            lockButton.style.background = 'none';
            lockButton.style.border = 'none';
            lockButton.style.fontSize = '1.2rem';
            lockButton.style.cursor = 'pointer';
            lockButton.style.padding = '0.25rem';
            lockButton.textContent = isLocked ? '🔒' : '🔓';
            lockButton.title = isLocked ? 'Locked - Click to unlock' : 'Unlocked - Click to lock';

            lockButton.addEventListener('click', function() {
                const currentlyLocked = this.dataset.locked === 'true';
                this.dataset.locked = !currentlyLocked;
                this.textContent = !currentlyLocked ? '🔒' : '🔓';
                this.title = !currentlyLocked ? 'Locked - Click to unlock' : 'Unlocked - Click to lock';
            });

            // Display schedule
            let scheduleText = '';
            if (customer.service_days_per_week > 1 && customer.service_schedule) {
                // Multi-day customer: show full schedule
                const dayMap = {Mo: 'Mon', Tu: 'Tue', We: 'Wed', Th: 'Thu', Fr: 'Fri', Sa: 'Sat', Su: 'Sun'};
                const days = customer.service_schedule.split(',').map(d => dayMap[d] || d).join(', ');
                scheduleText = `${customer.service_days_per_week}x/week: ${days}`;
            } else if (customer.service_day) {
                // Single-day customer
                scheduleText = customer.service_day;
            } else {
                scheduleText = 'No schedule';
            }

            const label = document.createElement('label');
            label.style.flex = '1';
            label.style.fontSize = '0.9rem';
            label.innerHTML = `${customer.display_name} <span style="color: #999;">(${scheduleText})</span>`;

            row.appendChild(lockButton);
            row.appendChild(label);
            container.appendChild(row);
        });
    } catch (error) {
        console.error('Error loading customers:', error);
        container.innerHTML = '<p style="color: #e74c3c;">Error loading customers</p>';
    }
}

/**
 * Toggles a context menu's visibility
 * @param {Event} event - The click event
 * @param {string} menuId - The ID of the menu to toggle (without 'menu-' prefix)
 */
function toggleContextMenu(event, menuId) {
    event.stopPropagation();
    const menu = document.getElementById('menu-' + menuId);
    const isCurrentlyOpen = menu.classList.contains('show');

    // Close all menus first
    closeAllContextMenus();

    // Toggle the clicked menu
    if (!isCurrentlyOpen) {
        menu.classList.add('show');
    }
}

/**
 * Closes all open context menus
 */
function closeAllContextMenus() {
    document.querySelectorAll('.context-menu').forEach(menu => {
        menu.classList.remove('show');
    });
}
