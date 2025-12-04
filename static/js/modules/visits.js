/**
 * Visits Module
 * Manages service visits - tracks when techs visit customers and what services they perform
 */

// Module state
let currentVisits = [];
let allServices = [];
let visitsAllCustomers = [];
let visitsAllTechs = [];
let currentUser = null;
let visitFilters = {
    status: null,
    tech_id: null,
    customer_id: null
};

/**
 * Initialize the visits module
 */
async function initVisitsModule() {
    console.log('Initializing Visits module');
    await loadCurrentUser();
    await loadInitialData();
    await loadTechOverview();
    setupEventListeners();
    await loadVisits();
}

/**
 * Load current user info to check if they're a tech
 */
async function loadCurrentUser() {
    try {
        const resp = await fetch('/api/v1/auth/me', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (resp.ok) {
            currentUser = await resp.json();
        }
    } catch (error) {
        console.error('Error loading current user:', error);
    }
}

/**
 * Load tech overview (only for non-tech users)
 */
async function loadTechOverview() {
    const overviewEl = document.getElementById('tech-overview');

    // Only show overview if user is NOT a tech
    if (!currentUser || currentUser.is_tech) {
        overviewEl.style.display = 'none';
        return;
    }

    try {
        const resp = await fetch('/api/techs/summary', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (!resp.ok) return;

        const data = await resp.json();
        const cardsContainer = overviewEl.querySelector('.tech-summary-cards');

        cardsContainer.innerHTML = data.techs.map(tech => `
            <div class="tech-summary-card"
                 style="border-left-color: ${tech.color}"
                 data-tech-id="${tech.id}"
                 onclick="filterByTech('${tech.id}', '${tech.name}')">
                <div class="tech-name">${tech.name}</div>
                <div class="tech-stat">
                    <i class="fas fa-calendar-check"></i>
                    <span class="tech-stat-value">${tech.visit_count}</span>
                    <span>visits today</span>
                </div>
                <div class="tech-stat">
                    <i class="fas fa-clock"></i>
                    <span>${tech.working_hours_start} - ${tech.working_hours_end}</span>
                </div>
            </div>
        `).join('');

        overviewEl.style.display = 'block';
    } catch (error) {
        console.error('Error loading tech overview:', error);
    }
}

/**
 * Filter visits by specific tech
 */
function filterByTech(techId, techName) {
    // Update filter
    visitFilters.tech_id = techId;

    // Update visual selection
    document.querySelectorAll('.tech-summary-card').forEach(card => {
        card.classList.remove('selected');
    });
    document.querySelector(`[data-tech-id="${techId}"]`)?.classList.add('selected');

    // Update tech filter dropdown
    const techFilter = document.getElementById('visit-tech-filter');
    if (techFilter) {
        techFilter.value = techId;
    }

    // Reload visits with new filter
    loadVisits();
}

/**
 * Load initial data (services, customers, techs)
 */
async function loadInitialData() {
    try {
        // Load services for selection
        const servicesResp = await fetch('/api/services', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (servicesResp.ok) {
            const servicesData = await servicesResp.json();
            allServices = servicesData.services || [];
        }

        // Load customers
        const customersResp = await fetch('/api/customers', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (customersResp.ok) {
            const customersData = await customersResp.json();
            visitsAllCustomers = customersData.customers || [];
        }

        // Load techs
        const techsResp = await fetch('/api/techs', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (techsResp.ok) {
            const techsData = await techsResp.json();
            visitsAllTechs = techsData.techs || [];
        }
    } catch (error) {
        console.error('Error loading initial data:', error);
    }
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    const addBtn = document.getElementById('add-visit-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => showVisitModal());
    }

    // Filter listeners
    const statusFilter = document.getElementById('visit-status-filter');
    const techFilter = document.getElementById('visit-tech-filter');
    const customerFilter = document.getElementById('visit-customer-filter');

    if (statusFilter) {
        statusFilter.addEventListener('change', (e) => {
            visitFilters.status = e.target.value || null;
            loadVisits();
        });
    }

    if (techFilter) {
        techFilter.addEventListener('change', (e) => {
            visitFilters.tech_id = e.target.value || null;
            loadVisits();
        });
    }

    if (customerFilter) {
        customerFilter.addEventListener('change', (e) => {
            visitFilters.customer_id = e.target.value || null;
            loadVisits();
        });
    }
}

/**
 * Load visits from API
 */
async function loadVisits() {
    try {
        let url = '/api/visits?';
        const params = new URLSearchParams();

        if (visitFilters.status) params.append('status', visitFilters.status);
        if (visitFilters.tech_id) params.append('tech_id', visitFilters.tech_id);
        if (visitFilters.customer_id) params.append('customer_id', visitFilters.customer_id);

        const response = await fetch(url + params.toString(), {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            currentVisits = data.visits || [];
            displayVisits();
        } else {
            console.error('Failed to load visits');
            showError('Failed to load visits');
        }
    } catch (error) {
        console.error('Error loading visits:', error);
        showError('Error loading visits');
    }
}

/**
 * Display visits in a list/table
 */
function displayVisits() {
    const container = document.getElementById('visits-container');
    if (!container) return;

    if (currentVisits.length === 0) {
        container.innerHTML = `
            <div class="placeholder-content">
                <i class="fas fa-calendar-check"></i>
                <p>No visits found</p>
                <p style="font-size: 0.875rem; color: #666;">Create visits to track service calls</p>
            </div>
        `;
        return;
    }

    let html = '<div class="visits-list">';
    currentVisits.forEach(visit => {
        html += renderVisitCard(visit);
    });
    html += '</div>';

    container.innerHTML = html;
}

/**
 * Render a visit card
 */
function renderVisitCard(visit) {
    const statusClass = `status-${visit.status}`;
    const scheduledDate = new Date(visit.scheduled_date).toLocaleString();
    const servicesHtml = visit.services && visit.services.length > 0
        ? `<div class="visit-services">
            <strong>Services:</strong> ${visit.services.map(s => s.service_name).join(', ')}
           </div>`
        : '';

    return `
        <div class="visit-card ${statusClass}" onclick="showVisitModal('${visit.id}')">
            <div class="visit-card-header">
                <div>
                    <h4>${visit.customer_name || 'Unknown Customer'}</h4>
                    <p class="visit-address">${visit.customer_address || ''}</p>
                </div>
                <span class="badge badge-${visit.status}">${visit.status.replace('_', ' ')}</span>
            </div>
            <div class="visit-card-body">
                <p><i class="fas fa-user-hard-hat"></i> <strong>Tech:</strong> ${visit.tech_name || 'Unassigned'}</p>
                <p><i class="fas fa-calendar"></i> <strong>Scheduled:</strong> ${scheduledDate}</p>
                ${servicesHtml}
                ${visit.notes ? `<p class="visit-notes">${visit.notes}</p>` : ''}
            </div>
        </div>
    `;
}

/**
 * Show visit modal (create or edit)
 */
async function showVisitModal(visitId = null) {
    let visit = null;

    if (visitId) {
        // Load full visit details
        const response = await fetch(`/api/visits/${visitId}`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (response.ok) {
            visit = await response.json();
        }
    }

    const isNew = !visit;
    const modalId = 'visit-modal-' + Date.now();

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = modalId;
    modal.innerHTML = `
        <div class="modal-dialog modal-large">
            <div class="modal-header">
                <h3>${isNew ? 'Create Visit' : 'Edit Visit'}</h3>
                <button class="modal-close" onclick="document.getElementById('${modalId}').remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <form id="visit-form-${modalId}">
                    <div class="form-row">
                        <div class="control-group">
                            <label>Customer *</label>
                            <select id="visit-customer-${modalId}" required ${!isNew ? 'disabled' : ''}>
                                <option value="">Select customer...</option>
                                ${visitsAllCustomers.map(c => `
                                    <option value="${c.id}" ${visit?.customer_id === c.id ? 'selected' : ''}>
                                        ${c.display_name}
                                    </option>
                                `).join('')}
                            </select>
                        </div>

                        <div class="control-group">
                            <label>Tech *</label>
                            <select id="visit-tech-${modalId}" required>
                                <option value="">Select tech...</option>
                                ${visitsAllTechs.map(t => `
                                    <option value="${t.id}" ${visit?.tech_id === t.id ? 'selected' : ''}>
                                        ${t.name}
                                    </option>
                                `).join('')}
                            </select>
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="control-group">
                            <label>Scheduled Date *</label>
                            <input type="datetime-local"
                                   id="visit-scheduled-${modalId}"
                                   value="${visit?.scheduled_date ? new Date(visit.scheduled_date).toISOString().slice(0, 16) : ''}"
                                   required>
                        </div>

                        <div class="control-group">
                            <label>Service Day *</label>
                            <select id="visit-service-day-${modalId}" required>
                                <option value="">Select day...</option>
                                ${['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(day => `
                                    <option value="${day}" ${visit?.service_day === day ? 'selected' : ''}>
                                        ${day.charAt(0).toUpperCase() + day.slice(1)}
                                    </option>
                                `).join('')}
                            </select>
                        </div>

                        <div class="control-group">
                            <label>Status *</label>
                            <select id="visit-status-${modalId}" required>
                                <option value="scheduled" ${visit?.status === 'scheduled' ? 'selected' : ''}>Scheduled</option>
                                <option value="in_progress" ${visit?.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
                                <option value="completed" ${visit?.status === 'completed' ? 'selected' : ''}>Completed</option>
                                <option value="cancelled" ${visit?.status === 'cancelled' ? 'selected' : ''}>Cancelled</option>
                                <option value="no_show" ${visit?.status === 'no_show' ? 'selected' : ''}>No Show</option>
                            </select>
                        </div>
                    </div>

                    <div class="control-group">
                        <label>Services Performed</label>
                        <div id="visit-services-${modalId}" class="services-selector">
                            ${renderServiceSelector(modalId, visit?.services || [])}
                        </div>
                    </div>

                    <div class="control-group">
                        <label>Notes</label>
                        <textarea id="visit-notes-${modalId}"
                                  rows="3"
                                  placeholder="Any notes or observations...">${visit?.notes || ''}</textarea>
                    </div>
                </form>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="document.getElementById('${modalId}').remove()">
                    Cancel
                </button>
                ${!isNew ? `
                    <button class="btn btn-danger" onclick="deleteVisit('${visit.id}', '${modalId}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                ` : ''}
                <button class="btn btn-primary" onclick="saveVisit('${modalId}', ${isNew}, '${visitId || ''}')">
                    <i class="fas fa-save"></i> ${isNew ? 'Create Visit' : 'Update'}
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

/**
 * Render service selector with checkboxes
 */
function renderServiceSelector(modalId, selectedServices = []) {
    const selectedIds = selectedServices.map(s => s.service_catalog_id);

    let html = '<div class="service-checkboxes">';

    if (allServices.length === 0) {
        html += '<p style="color: #666; font-size: 0.875rem;">No services in catalog. <a href="#jobs">Add services</a> first.</p>';
    } else {
        allServices.filter(s => s.is_active).forEach(service => {
            const isChecked = selectedIds.includes(service.id);
            html += `
                <label class="checkbox-label">
                    <input type="checkbox"
                           class="service-checkbox"
                           data-service-id="${service.id}"
                           data-service-name="${service.name}"
                           ${isChecked ? 'checked' : ''}>
                    <span>${service.name}</span>
                    ${service.estimated_duration ? `<span class="service-duration">(${service.estimated_duration} min)</span>` : ''}
                </label>
            `;
        });
    }

    html += '</div>';
    html += `
        <div class="control-group" style="margin-top: 1rem;">
            <label>Custom Service (if not in catalog)</label>
            <input type="text"
                   id="visit-custom-service-${modalId}"
                   placeholder="e.g., Emergency repair">
        </div>
    `;

    return html;
}

/**
 * Save visit (create or update)
 */
async function saveVisit(modalId, isNew, visitId) {
    const customerId = document.getElementById(`visit-customer-${modalId}`).value;
    const techId = document.getElementById(`visit-tech-${modalId}`).value;
    const scheduledDate = document.getElementById(`visit-scheduled-${modalId}`).value;
    const serviceDay = document.getElementById(`visit-service-day-${modalId}`).value;
    const status = document.getElementById(`visit-status-${modalId}`).value;
    const notes = document.getElementById(`visit-notes-${modalId}`).value.trim();

    if (!customerId || !techId || !scheduledDate || !serviceDay) {
        alert('Please fill in all required fields');
        return;
    }

    const payload = {
        customer_id: customerId,
        tech_id: techId,
        scheduled_date: new Date(scheduledDate).toISOString(),
        service_day: serviceDay,
        status: status,
        notes: notes || null
    };

    try {
        let response;

        if (isNew) {
            response = await fetch('/api/visits', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${Auth.getToken()}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
        } else {
            response = await fetch(`/api/visits/${visitId}`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${Auth.getToken()}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
        }

        if (response.ok) {
            const savedVisit = await response.json();

            // Handle services
            await saveVisitServices(savedVisit.id, modalId);

            document.getElementById(modalId).remove();
            await loadVisits();
            alert(isNew ? 'Visit created successfully' : 'Visit updated successfully');
        } else {
            const error = await response.json();
            alert('Error: ' + (error.detail || 'Failed to save visit'));
        }
    } catch (error) {
        console.error('Error saving visit:', error);
        alert('Error saving visit');
    }
}

/**
 * Save services associated with visit
 */
async function saveVisitServices(visitId, modalId) {
    const checkboxes = document.querySelectorAll('.service-checkbox:checked');
    const customService = document.getElementById(`visit-custom-service-${modalId}`).value.trim();

    // Add catalog services
    for (const checkbox of checkboxes) {
        const serviceId = checkbox.dataset.serviceId;
        await fetch(`/api/visits/${visitId}/services`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${Auth.getToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                service_catalog_id: serviceId
            })
        });
    }

    // Add custom service if provided
    if (customService) {
        await fetch(`/api/visits/${visitId}/services`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${Auth.getToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                custom_service_name: customService
            })
        });
    }
}

/**
 * Delete visit
 */
async function deleteVisit(visitId, modalId) {
    if (!confirm('Are you sure you want to delete this visit?')) {
        return;
    }

    try {
        const response = await fetch(`/api/visits/${visitId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            document.getElementById(modalId).remove();
            await loadVisits();
            alert('Visit deleted successfully');
        } else {
            alert('Error deleting visit');
        }
    } catch (error) {
        console.error('Error deleting visit:', error);
        alert('Error deleting visit');
    }
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.getElementById('visits-container');
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
window.initVisitsModule = initVisitsModule;
window.showVisitModal = showVisitModal;
window.saveVisit = saveVisit;
window.deleteVisit = deleteVisit;
window.filterByTech = filterByTech;
