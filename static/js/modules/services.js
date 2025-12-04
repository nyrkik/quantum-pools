/**
 * Services Module
 * Manages the service catalog - standardized services for easy job tracking
 */

// Module state
let currentServices = [];
let serviceCategories = ['Cleaning', 'Chemical', 'Repair', 'Inspection', 'Maintenance', 'Other'];

/**
 * Initialize the services module
 */
async function initServicesModule() {
    console.log('Initializing Services module');
    await loadServices();
    setupEventListeners();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    const addBtn = document.getElementById('add-service-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => showServiceModal());
    }
}

/**
 * Load services from API
 */
async function loadServices() {
    try {
        const response = await fetch('/api/services', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            currentServices = data.services || [];
            displayServices();
        } else {
            console.error('Failed to load services');
            showError('Failed to load services');
        }
    } catch (error) {
        console.error('Error loading services:', error);
        showError('Error loading services');
    }
}

/**
 * Display services grouped by category
 */
function displayServices() {
    const container = document.getElementById('services-container');
    if (!container) return;

    if (currentServices.length === 0) {
        container.innerHTML = `
            <div class="placeholder-content">
                <i class="fas fa-clipboard-list"></i>
                <p>No services in catalog</p>
                <p style="font-size: 0.875rem; color: #666;">Add standardized services to make job tracking easier</p>
            </div>
        `;
        return;
    }

    // Group by category
    const grouped = {};
    currentServices.forEach(service => {
        const category = service.category || 'Other';
        if (!grouped[category]) grouped[category] = [];
        grouped[category].push(service);
    });

    let html = '';
    serviceCategories.forEach(category => {
        const services = grouped[category];
        if (!services || services.length === 0) return;

        html += `
            <div class="service-category">
                <h3 class="service-category-header">
                    <i class="fas fa-folder"></i> ${category} (${services.length})
                </h3>
                <div class="service-grid">
                    ${services.map(service => renderServiceCard(service)).join('')}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

/**
 * Render a service card
 */
function renderServiceCard(service) {
    const duration = service.estimated_duration ?
        `<span class="service-duration"><i class="fas fa-clock"></i> ${service.estimated_duration} min</span>` : '';

    return `
        <div class="service-card ${!service.is_active ? 'service-inactive' : ''}" onclick="showServiceModal('${service.id}')">
            <div class="service-card-header">
                <h4>${service.name}</h4>
                ${!service.is_active ? '<span class="badge badge-secondary">Inactive</span>' : ''}
            </div>
            <div class="service-card-body">
                ${service.description ? `<p>${service.description}</p>` : ''}
                ${duration}
            </div>
        </div>
    `;
}

/**
 * Show service modal (create or edit)
 */
async function showServiceModal(serviceId = null) {
    let service = null;

    if (serviceId) {
        service = currentServices.find(s => s.id === serviceId);
    }

    const isNew = !service;
    const modalId = 'service-modal-' + Date.now();

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = modalId;
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-header">
                <h3>${isNew ? 'Add Service' : 'Edit Service'}</h3>
                <button class="modal-close" onclick="document.getElementById('${modalId}').remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <form id="service-form-${modalId}">
                    <div class="control-group">
                        <label>Service Name *</label>
                        <input type="text"
                               id="service-name-${modalId}"
                               value="${service?.name || ''}"
                               placeholder="e.g., Pool Cleaning, Filter Replacement"
                               required>
                    </div>

                    <div class="control-group">
                        <label>Category *</label>
                        <select id="service-category-${modalId}" required>
                            ${serviceCategories.map(cat => `
                                <option value="${cat}" ${service?.category === cat ? 'selected' : ''}>
                                    ${cat}
                                </option>
                            `).join('')}
                        </select>
                    </div>

                    <div class="control-group">
                        <label>Description</label>
                        <textarea id="service-description-${modalId}"
                                  rows="3"
                                  placeholder="Brief description of this service...">${service?.description || ''}</textarea>
                    </div>

                    <div class="control-group">
                        <label>Estimated Duration (minutes)</label>
                        <input type="number"
                               id="service-duration-${modalId}"
                               value="${service?.estimated_duration || ''}"
                               min="1"
                               placeholder="30">
                    </div>

                    ${!isNew ? `
                        <div class="control-group">
                            <label class="checkbox-label">
                                <input type="checkbox"
                                       id="service-active-${modalId}"
                                       ${service.is_active ? 'checked' : ''}>
                                Active (show in service selection)
                            </label>
                        </div>
                    ` : ''}
                </form>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="document.getElementById('${modalId}').remove()">
                    Cancel
                </button>
                ${!isNew ? `
                    <button class="btn btn-danger" onclick="deleteService('${service.id}', '${modalId}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                ` : ''}
                <button class="btn btn-primary" onclick="saveService('${modalId}', ${isNew}, '${serviceId || ''}')">
                    <i class="fas fa-save"></i> ${isNew ? 'Add Service' : 'Update'}
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

/**
 * Save service (create or update)
 */
async function saveService(modalId, isNew, serviceId) {
    const name = document.getElementById(`service-name-${modalId}`).value.trim();
    const category = document.getElementById(`service-category-${modalId}`).value;
    const description = document.getElementById(`service-description-${modalId}`).value.trim();
    const duration = document.getElementById(`service-duration-${modalId}`).value;

    if (!name) {
        alert('Please enter a service name');
        return;
    }

    const payload = {
        name,
        category,
        description: description || null,
        estimated_duration: duration ? parseInt(duration) : null
    };

    if (!isNew) {
        const activeCheckbox = document.getElementById(`service-active-${modalId}`);
        if (activeCheckbox) {
            payload.is_active = activeCheckbox.checked;
        }
    }

    try {
        const url = isNew ? '/api/services' : `/api/services/${serviceId}`;
        const method = isNew ? 'POST' : 'PUT';

        const response = await fetch(url, {
            method,
            headers: {
                'Authorization': `Bearer ${Auth.getToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            document.getElementById(modalId).remove();
            await loadServices();
            alert(isNew ? 'Service added successfully' : 'Service updated successfully');
        } else {
            const error = await response.json();
            alert('Error: ' + (error.detail || 'Failed to save service'));
        }
    } catch (error) {
        console.error('Error saving service:', error);
        alert('Error saving service');
    }
}

/**
 * Delete service
 */
async function deleteService(serviceId, modalId) {
    if (!confirm('Are you sure you want to delete this service?')) {
        return;
    }

    try {
        const response = await fetch(`/api/services/${serviceId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            document.getElementById(modalId).remove();
            await loadServices();
            alert('Service deleted successfully');
        } else {
            alert('Error deleting service');
        }
    } catch (error) {
        console.error('Error deleting service:', error);
        alert('Error deleting service');
    }
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.getElementById('services-container');
    if (container) {
        container.innerHTML = `
            <div class="placeholder-content">
                <i class="fas fa-exclamation-triangle"></i>
                <p>${message}</p>
            </div>
        `;
    }
}

// Export functions
window.initServicesModule = initServicesModule;
window.showServiceModal = showServiceModal;
window.saveService = saveService;
window.deleteService = deleteService;
