/**
 * Issues Module
 * Handles issue management - viewing, filtering, assigning, and resolving issues
 */

// Module state
let currentIssues = [];
let currentTechs = [];
let issueFilters = {
    status: 'pending',
    severity: 'all',
    tech_id: 'all'
};

/**
 * Initialize the issues module
 */
async function initIssuesModule() {
    console.log('Initializing Issues module');

    // Load techs for filter
    await loadTechs();

    // Load issues
    await loadIssues();

    // Setup event listeners
    setupEventListeners();
}

/**
 * Setup event listeners for the issues module
 */
function setupEventListeners() {
    // Filter toggle
    const filterBtn = document.getElementById('issue-filter-btn');
    if (filterBtn) {
        filterBtn.addEventListener('click', () => {
            const filtersDiv = document.querySelector('.issues-filters');
            if (filtersDiv) {
                filtersDiv.style.display = filtersDiv.style.display === 'none' ? 'block' : 'none';
            }
        });
    }

    // Filter changes
    const statusFilter = document.getElementById('issue-status-filter');
    const severityFilter = document.getElementById('issue-severity-filter');
    const techFilter = document.getElementById('issue-tech-filter');

    if (statusFilter) {
        statusFilter.addEventListener('change', async () => {
            issueFilters.status = statusFilter.value;
            await loadIssues();
        });
    }

    if (severityFilter) {
        severityFilter.addEventListener('change', async () => {
            issueFilters.severity = severityFilter.value;
            await loadIssues();
        });
    }

    if (techFilter) {
        techFilter.addEventListener('change', async () => {
            issueFilters.tech_id = techFilter.value;
            await loadIssues();
        });
    }
}

/**
 * Load techs for filter dropdown
 */
async function loadTechs() {
    try {
        const response = await fetch('/api/techs', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            currentTechs = data.techs || [];

            // Populate tech filter
            const techFilter = document.getElementById('issue-tech-filter');
            if (techFilter) {
                techFilter.innerHTML = '<option value="all">All Techs</option>';
                currentTechs.forEach(tech => {
                    if (tech.is_active) {
                        const option = document.createElement('option');
                        option.value = tech.id;
                        option.textContent = tech.name;
                        techFilter.appendChild(option);
                    }
                });
            }
        }
    } catch (error) {
        console.error('Error loading techs:', error);
    }
}

/**
 * Load issues from API
 */
async function loadIssues() {
    try {
        // Build query params
        const params = new URLSearchParams();
        if (issueFilters.status !== 'all') {
            params.append('status', issueFilters.status);
        }
        if (issueFilters.severity !== 'all') {
            params.append('severity', issueFilters.severity);
        }
        if (issueFilters.tech_id !== 'all') {
            params.append('assigned_tech_id', issueFilters.tech_id);
        }

        const response = await fetch(`/api/issues?${params.toString()}`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            currentIssues = data.issues || [];
            displayIssues();
        } else {
            console.error('Failed to load issues');
            showError('Failed to load issues');
        }
    } catch (error) {
        console.error('Error loading issues:', error);
        showError('Error loading issues');
    }
}

/**
 * Display issues in the UI
 */
function displayIssues() {
    const container = document.getElementById('issues-container');
    if (!container) return;

    if (currentIssues.length === 0) {
        container.innerHTML = `
            <div class="placeholder-content">
                <i class="fas fa-check-circle"></i>
                <p>No issues found</p>
            </div>
        `;
        return;
    }

    // Group issues by status
    const grouped = {
        pending: [],
        scheduled: [],
        in_progress: [],
        resolved: []
    };

    currentIssues.forEach(issue => {
        if (grouped[issue.status]) {
            grouped[issue.status].push(issue);
        }
    });

    let html = '';

    // Show each group
    Object.keys(grouped).forEach(status => {
        const issues = grouped[status];
        if (issues.length === 0) return;

        const statusLabels = {
            pending: 'Pending Review',
            scheduled: 'Scheduled',
            in_progress: 'In Progress',
            resolved: 'Resolved'
        };

        html += `
            <div class="issue-group">
                <h3 class="issue-group-header">${statusLabels[status]} (${issues.length})</h3>
                <div class="issue-list">
                    ${issues.map(issue => renderIssueCard(issue)).join('')}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;

    // Add click handlers
    currentIssues.forEach(issue => {
        const card = document.getElementById(`issue-${issue.id}`);
        if (card) {
            card.addEventListener('click', () => showIssueDetail(issue));
        }
    });
}

/**
 * Render a single issue card
 */
function renderIssueCard(issue) {
    const severityColors = {
        critical: '#dc3545',
        high: '#fd7e14',
        medium: '#ffc107',
        low: '#28a745'
    };

    const severityColor = severityColors[issue.severity] || '#6c757d';

    const reportedDate = new Date(issue.reported_at).toLocaleDateString();

    return `
        <div class="issue-card" id="issue-${issue.id}" style="border-left: 4px solid ${severityColor}">
            <div class="issue-card-header">
                <span class="issue-severity" style="background: ${severityColor}">${issue.severity.toUpperCase()}</span>
                <span class="issue-date">${reportedDate}</span>
            </div>
            <div class="issue-card-body">
                <h4>${issue.customer_name}</h4>
                <p class="issue-address">${issue.customer_address || ''}</p>
                <p class="issue-description">${issue.description}</p>
            </div>
            <div class="issue-card-footer">
                <span class="issue-reporter">
                    <i class="fas fa-user"></i> ${issue.reported_by_name || 'Unknown'}
                </span>
                ${issue.assigned_tech_name ? `
                    <span class="issue-assigned">
                        <i class="fas fa-user-check"></i> ${issue.assigned_tech_name}
                    </span>
                ` : ''}
            </div>
        </div>
    `;
}

/**
 * Show issue detail modal
 */
function showIssueDetail(issue) {
    const modal = createIssueModal(issue);
    document.body.appendChild(modal);
}

// Store current issue being edited
let currentEditingIssue = null;

/**
 * Show new issue creation modal
 */
function showNewIssueModal(customerId = null, customerName = null) {
    const modal = createIssueModal(null, customerId, customerName);
    document.body.appendChild(modal);
}

/**
 * Create issue modal (for viewing/editing existing or creating new)
 */
function createIssueModal(issue = null, presetCustomerId = null, presetCustomerName = null) {
    const isNew = !issue;
    const modalId = 'issue-modal-' + Date.now();

    // Store current issue for saving
    if (!isNew) {
        currentEditingIssue = issue;
    }

    const severityOptions = ['low', 'medium', 'high', 'critical'];
    const statusOptions = ['pending', 'scheduled', 'in_progress', 'resolved', 'closed'];

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = modalId;
    modal.innerHTML = `
        <div class="modal-dialog modal-mobile" style="max-width: 700px;">
            <div class="modal-header">
                <h3>${isNew ? 'Report Service Alert' : 'Service Alert Details'}</h3>
                <button class="modal-close btn-mobile-touch" onclick="document.getElementById('${modalId}').remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <form id="issue-form-${modalId}">
                    ${isNew && !presetCustomerId ? `
                        <div class="control-group">
                            <label>Customer *</label>
                            <div class="search-dropdown-wrapper">
                                <input type="text"
                                       id="issue-customer-search-${modalId}"
                                       placeholder="Search or select customer..."
                                       autocomplete="off"
                                       required>
                                <i class="fas fa-chevron-down search-dropdown-icon"></i>
                            </div>
                            <input type="hidden" id="issue-customer-${modalId}">
                            <div id="issue-customer-results-${modalId}" class="autocomplete-results"></div>
                        </div>
                    ` : `
                        <div class="control-group">
                            <label>Customer</label>
                            <input type="text" value="${issue?.customer_name || presetCustomerName || ''}" disabled>
                            <input type="hidden" id="issue-customer-${modalId}" value="${issue?.customer_id || presetCustomerId || ''}">
                        </div>
                    `}

                    <div class="control-group">
                        <label>Severity *</label>
                        <select id="issue-severity-${modalId}" required>
                            ${severityOptions.map(s => `
                                <option value="${s}" ${(!isNew && issue.severity === s) || (isNew && s === 'medium') ? 'selected' : ''}>
                                    ${s.charAt(0).toUpperCase() + s.slice(1)}
                                </option>
                            `).join('')}
                        </select>
                    </div>

                    ${!isNew ? `
                        <div class="control-group">
                            <label>Status</label>
                            <select id="issue-status-${modalId}">
                                ${statusOptions.map(s => `
                                    <option value="${s}" ${issue.status === s ? 'selected' : ''}>
                                        ${s.replace('_', ' ').charAt(0).toUpperCase() + s.replace('_', ' ').slice(1)}
                                    </option>
                                `).join('')}
                            </select>
                        </div>

                        <div class="control-group">
                            <label>Assign To</label>
                            <select id="issue-assigned-tech-${modalId}">
                                <option value="">Unassigned</option>
                            </select>
                        </div>
                    ` : ''}

                    <div class="control-group">
                        <label>Description *</label>
                        <textarea id="issue-description-${modalId}" class="input-mobile" rows="4" required placeholder="Describe the issue...">${issue?.description || ''}</textarea>
                    </div>

                    <div class="control-group">
                        <label>Photos</label>
                        <input type="file"
                               id="issue-photos-${modalId}"
                               accept="image/*"
                               multiple
                               style="display: none;">
                        <button type="button"
                                class="btn btn-secondary btn-mobile-lg"
                                onclick="document.getElementById('issue-photos-${modalId}').click()">
                            <i class="fas fa-camera"></i> Add Photos
                        </button>
                        <div id="issue-photos-preview-${modalId}" class="photos-preview"></div>
                    </div>

                    ${!isNew && issue.status === 'resolved' ? `
                        <div class="control-group">
                            <label>Resolution Notes</label>
                            <textarea id="issue-resolution-${modalId}" rows="3" placeholder="How was this resolved?">${issue.resolution_notes || ''}</textarea>
                        </div>
                    ` : ''}

                    ${!isNew ? `
                        <div class="form-row" style="gap: 1rem;">
                            <div class="control-group" style="flex: 1;">
                                <label>Reported By</label>
                                <input type="text" value="${issue.reported_by_name || 'Unknown'}" disabled>
                            </div>
                            <div class="control-group" style="flex: 1;">
                                <label>Reported At</label>
                                <input type="text" value="${new Date(issue.reported_at).toLocaleString()}" disabled>
                            </div>
                        </div>
                    ` : ''}
                </form>
            </div>
            <div class="modal-footer modal-footer-mobile">
                <button class="btn btn-secondary btn-mobile-lg" onclick="document.getElementById('${modalId}').remove()">
                    Cancel
                </button>
                ${!isNew ? `
                    <button class="btn btn-danger btn-mobile-lg" onclick="deleteIssue('${issue.id}', '${modalId}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                ` : ''}
                <button class="btn btn-primary btn-mobile-lg" onclick="saveIssue('${modalId}', ${isNew})">
                    <i class="fas fa-save"></i> ${isNew ? 'Report Alert' : 'Update'}
                </button>
            </div>
        </div>
    `;

    // Setup customer search if needed
    if (isNew && !presetCustomerId) {
        setTimeout(() => setupCustomerSearch(modalId), 100);
    }

    // Load techs for assignment
    if (!isNew) {
        loadTechsForSelect(`issue-assigned-tech-${modalId}`, issue.assigned_tech_id);
    }

    // Setup photo upload handler
    setTimeout(() => setupPhotoUpload(modalId, issue), 100);

    return modal;
}

/**
 * Setup customer search autocomplete
 */
let issuesAllCustomers = [];
let customerSearchTimeout = null;

async function setupCustomerSearch(modalId) {
    const searchInput = document.getElementById(`issue-customer-search-${modalId}`);
    const hiddenInput = document.getElementById(`issue-customer-${modalId}`);
    const resultsDiv = document.getElementById(`issue-customer-results-${modalId}`);
    const dropdownIcon = searchInput?.parentElement.querySelector('.search-dropdown-icon');

    if (!searchInput) return;

    // Load all customers once
    try {
        const response = await fetch('/api/customers', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            issuesAllCustomers = data.customers || [];
        }
    } catch (error) {
        console.error('Error loading customers:', error);
    }

    // Function to display customers
    function displayCustomers(customers) {
        if (customers.length === 0) {
            resultsDiv.innerHTML = '<div class="autocomplete-item">No customers found</div>';
            resultsDiv.style.display = 'block';
            return;
        }

        resultsDiv.innerHTML = customers.map(customer => `
            <div class="autocomplete-item" data-id="${customer.id}" data-name="${customer.display_name}">
                <div><strong>${customer.display_name}</strong></div>
                <div style="font-size: 0.875rem; color: #666;">${customer.address || ''}</div>
            </div>
        `).join('');
        resultsDiv.style.display = 'block';

        // Add click handlers
        resultsDiv.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const customerId = item.dataset.id;
                const customerName = item.dataset.name;
                if (customerName) {
                    searchInput.value = customerName;
                    hiddenInput.value = customerId;
                    resultsDiv.style.display = 'none';
                }
            });
        });
    }

    // Show all customers on focus
    searchInput.addEventListener('focus', () => {
        const query = searchInput.value.toLowerCase().trim();
        if (query.length === 0) {
            displayCustomers(issuesAllCustomers.slice(0, 50));
        }
    });

    // Setup search handler
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();

        if (query.length === 0) {
            displayCustomers(issuesAllCustomers.slice(0, 50));
            hiddenInput.value = '';
            return;
        }

        // Filter customers
        const matches = issuesAllCustomers
            .filter(c => c.display_name.toLowerCase().includes(query) ||
                        c.address?.toLowerCase().includes(query))
            .slice(0, 50);

        displayCustomers(matches);
    });

    // Dropdown icon click toggles results
    if (dropdownIcon) {
        dropdownIcon.addEventListener('click', () => {
            if (resultsDiv.style.display === 'block') {
                resultsDiv.style.display = 'none';
            } else {
                displayCustomers(issuesAllCustomers.slice(0, 50));
                searchInput.focus();
            }
        });
    }

    // Hide results when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) &&
            !resultsDiv.contains(e.target) &&
            e.target !== dropdownIcon) {
            resultsDiv.style.display = 'none';
        }
    });
}

/**
 * Setup photo upload handling
 */
let uploadedPhotos = [];

async function setupPhotoUpload(modalId, issue) {
    const fileInput = document.getElementById(`issue-photos-${modalId}`);
    const previewDiv = document.getElementById(`issue-photos-preview-${modalId}`);

    if (!fileInput || !previewDiv) return;

    // Reset photos array for new issue
    uploadedPhotos = [];

    // Display existing photos if editing
    if (issue && issue.photos && issue.photos.length > 0) {
        uploadedPhotos = [...issue.photos];
        displayPhotoPreviews(previewDiv, modalId);
    }

    fileInput.addEventListener('change', async (e) => {
        const files = Array.from(e.target.files);

        for (const file of files) {
            if (file.size > 5 * 1024 * 1024) {
                alert(`File ${file.name} is too large. Maximum size is 5MB.`);
                continue;
            }

            try {
                const base64 = await fileToBase64(file);
                uploadedPhotos.push(base64);
            } catch (error) {
                console.error('Error processing file:', error);
                alert(`Error processing ${file.name}`);
            }
        }

        displayPhotoPreviews(previewDiv, modalId);
        fileInput.value = ''; // Reset input
    });
}

/**
 * Convert file to base64
 */
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/**
 * Display photo previews
 */
function displayPhotoPreviews(previewDiv, modalId) {
    if (uploadedPhotos.length === 0) {
        previewDiv.innerHTML = '';
        return;
    }

    previewDiv.innerHTML = uploadedPhotos.map((photo, index) => `
        <div class="photo-preview-item" style="position: relative; display: inline-block; margin: 0.5rem;">
            <img src="${photo}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 4px;">
            <button type="button"
                    class="photo-remove-btn"
                    onclick="removePhoto(${index}, '${modalId}')"
                    style="position: absolute; top: -8px; right: -8px; background: #dc3545; color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 16px; line-height: 1;">
                ×
            </button>
        </div>
    `).join('');
}

/**
 * Remove photo from array
 */
function removePhoto(index, modalId) {
    uploadedPhotos.splice(index, 1);
    const previewDiv = document.getElementById(`issue-photos-preview-${modalId}`);
    if (previewDiv) {
        displayPhotoPreviews(previewDiv, modalId);
    }
}

/**
 * Load customers for dropdown
 */
async function loadCustomersForSelect(selectId) {
    try {
        const response = await fetch('/api/customers', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById(selectId);
            if (select) {
                data.customers.forEach(customer => {
                    const option = document.createElement('option');
                    option.value = customer.id;
                    option.textContent = customer.display_name;
                    select.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('Error loading customers:', error);
    }
}

/**
 * Load techs for dropdown
 */
async function loadTechsForSelect(selectId, selectedTechId = null) {
    try {
        const response = await fetch('/api/techs', {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            const data = await response.json();
            const select = document.getElementById(selectId);
            if (select) {
                data.techs.forEach(tech => {
                    if (tech.is_active) {
                        const option = document.createElement('option');
                        option.value = tech.id;
                        option.textContent = tech.name;
                        option.selected = selectedTechId === tech.id;
                        select.appendChild(option);
                    }
                });
            }
        }
    } catch (error) {
        console.error('Error loading techs:', error);
    }
}

/**
 * Save issue (create or update)
 */
async function saveIssue(modalId, isNew) {
    const customerId = document.getElementById(`issue-customer-${modalId}`).value;
    const severity = document.getElementById(`issue-severity-${modalId}`).value;
    const description = document.getElementById(`issue-description-${modalId}`).value;

    if (!customerId || !description) {
        alert('Please fill in all required fields');
        return;
    }

    const payload = {
        customer_id: customerId,
        severity: severity,
        description: description,
        photos: uploadedPhotos
    };

    if (!isNew) {
        const statusEl = document.getElementById(`issue-status-${modalId}`);
        const assignedTechEl = document.getElementById(`issue-assigned-tech-${modalId}`);
        const resolutionEl = document.getElementById(`issue-resolution-${modalId}`);

        if (statusEl) payload.status = statusEl.value;
        if (assignedTechEl && assignedTechEl.value) payload.assigned_tech_id = assignedTechEl.value;
        if (resolutionEl) payload.resolution_notes = resolutionEl.value;
    }

    try {
        const url = isNew ? '/api/issues' : `/api/issues/${currentEditingIssue.id}`;
        const method = isNew ? 'POST' : 'PUT';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Authorization': `Bearer ${Auth.getToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            document.getElementById(modalId).remove();
            await loadIssues();
            alert(isNew ? 'Issue reported successfully' : 'Issue updated successfully');
        } else {
            const error = await response.json();
            alert('Error: ' + (error.detail || 'Failed to save issue'));
        }
    } catch (error) {
        console.error('Error saving issue:', error);
        alert('Error saving issue');
    }
}

/**
 * Delete issue
 */
async function deleteIssue(issueId, modalId) {
    if (!confirm('Are you sure you want to delete this issue?')) {
        return;
    }

    try {
        const response = await fetch(`/api/issues/${issueId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (response.ok) {
            document.getElementById(modalId).remove();
            await loadIssues();
            alert('Issue deleted successfully');
        } else {
            alert('Error deleting issue');
        }
    } catch (error) {
        console.error('Error deleting issue:', error);
        alert('Error deleting issue');
    }
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.getElementById('issues-container');
    if (container) {
        container.innerHTML = `
            <div class="placeholder-content">
                <i class="fas fa-exclamation-triangle"></i>
                <p>${message}</p>
            </div>
        `;
    }
}

// Export all functions to global scope (must be at end after all definitions)
window.initIssuesModule = initIssuesModule;
window.showNewIssueModal = showNewIssueModal;
window.saveIssue = saveIssue;
window.deleteIssue = deleteIssue;
window.removePhoto = removePhoto;
