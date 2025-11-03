// QuantumPools - Customers Module
//
// Handles customer management, CRUD operations, search, and filtering
// Dependencies: API_BASE, loadCustomers() from map.js, highlightCustomerMarker() from map.js,
//               openModal()/closeModal() from modals.js, showBulkEditCustomers() from bulk-edit.js

// Global variable for form change detection
let originalFormValues = {};

// Global variable for current filter state
let currentFilters = {
    serviceDay: '',
    assignedTech: '',
    serviceType: '',
    status: 'active_pending'
};

// ========================================
// Customer Management & Display
// ========================================

async function loadCustomersManagement() {
    try {
        // Build URL with current filters
        let url = `${API_BASE}/api/customers?page_size=1000`;

        if (currentFilters.serviceDay) {
            url += `&service_day=${currentFilters.serviceDay}`;
        }
        if (currentFilters.assignedTech) {
            url += `&assigned_tech_id=${currentFilters.assignedTech}`;
        }
        if (currentFilters.serviceType) {
            url += `&service_type=${currentFilters.serviceType}`;
        }

        // Status filtering
        if (currentFilters.status === 'active_pending') {
            // Show active and pending (comma-separated for OR logic)
            url += `&status=active,pending`;
        } else if (currentFilters.status === 'active') {
            url += `&status=active`;
        } else if (currentFilters.status === 'pending') {
            url += `&status=pending`;
        } else if (currentFilters.status === 'inactive') {
            url += `&status=inactive`;
        }
        // If status is 'all', don't add any status filter

        const response = await Auth.apiRequest(url);
        if (!response.ok) {
            console.error('Failed to load customers:', response.status);
            displayCustomersManagement([]);
            return;
        }

        const data = await response.json();
        displayCustomersManagement(data.customers || []);
    } catch (error) {
        console.error('Error loading customers for management:', error);
        displayCustomersManagement([]);
    }
}

function displayCustomersManagement(customers) {
    const container = document.getElementById('customers-list');
    const profilePane = document.getElementById('tab-profile');

    if (!customers || customers.length === 0) {
        container.innerHTML = '<p class="placeholder">No customers found. Add a customer to get started.</p>';
        profilePane.innerHTML = '<div class="empty-state"><p>Add a client to view details</p></div>';
        return;
    }

    container.innerHTML = '';
    customers.forEach(customer => {
        const listItem = document.createElement('div');
        listItem.className = 'client-list-item';
        listItem.dataset.customerId = customer.id;
        listItem.dataset.serviceType = customer.service_type;

        // Add pending class if status is pending
        if (customer.status === 'pending') {
            listItem.classList.add('pending');
        }

        // Use display_name if available, fallback to name
        const displayName = customer.display_name || customer.name;

        // Parse street address from full address
        const streetAddress = customer.address ? customer.address.split(',')[0] : '';

        // Add pending badge if status is pending
        const pendingBadge = customer.status === 'pending' ? '<span class="pending-badge">PENDING</span>' : '';

        listItem.innerHTML = `
            <div class="client-list-item-name">${displayName}${pendingBadge}</div>
            <div class="client-list-item-address">${streetAddress}</div>
        `;

        // Click handler to show customer profile
        listItem.addEventListener('click', function() {
            // Remove active state from all items
            document.querySelectorAll('.client-list-item').forEach(item => {
                item.classList.remove('active');
            });

            // Mark this item as active
            listItem.classList.add('active');

            // Display customer profile in detail pane
            displayClientProfile(customer);
        });

        container.appendChild(listItem);
    });

    // Auto-select first customer
    const firstItem = container.querySelector('.client-list-item');
    if (firstItem) {
        firstItem.click();
    }
}

function formatAddress(address) {
    if (!address) return 'N/A';
    const parts = address.split(',').map(p => p.trim());
    if (parts.length >= 3) {
        const street = parts[0];
        const cityStateZip = parts.slice(1).join(', ');
        return `${street}<br>${cityStateZip}`;
    }
    return address;
}

function displayClientProfile(customer) {
    const profilePane = document.getElementById('tab-profile');

    // Use display_name if available, fallback to name
    const displayName = customer.display_name || customer.name;

    // Determine icon based on service type
    const serviceIcon = customer.service_type === 'commercial' ? 'fa-building' : 'fa-home';

    profilePane.innerHTML = `
        <div class="client-profile">
            <div class="profile-header">
                <div class="profile-header-name">
                    <i class="fas ${serviceIcon} profile-icon"></i>
                    <h2>${displayName}</h2>
                </div>
                <div class="profile-actions">
                    <button class="btn-icon btn-icon-primary" onclick="editCustomer('${customer.id}')" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                </div>
            </div>

            <div class="profile-section">
                <h3>Contact Information</h3>
                <div class="profile-grid">
                    <div class="profile-field">
                        <label>Name</label>
                        <p>${displayName}</p>
                    </div>
                    <div class="profile-field">
                        <label>Address</label>
                        <p>${formatAddress(customer.address)}</p>
                    </div>
                    <div class="profile-field">
                        <label>Email</label>
                        <p>${customer.email || 'N/A'}</p>
                    </div>
                    <div class="profile-field">
                        <label>Phone</label>
                        <p>${customer.phone || 'N/A'}</p>
                    </div>
                </div>
            </div>

            <div class="profile-section">
                <h3>Service Details</h3>
                <div class="profile-grid">
                    <div class="profile-field">
                        <label>Service Day</label>
                        <p>${customer.service_day ? customer.service_day.charAt(0).toUpperCase() + customer.service_day.slice(1) : 'N/A'}</p>
                    </div>
                    <div class="profile-field">
                        <label>Service Type</label>
                        <p>${customer.service_type ? customer.service_type.charAt(0).toUpperCase() + customer.service_type.slice(1) : 'N/A'}</p>
                    </div>
                    <div class="profile-field">
                        <label>Service Duration</label>
                        <p>${customer.service_duration_minutes || 'N/A'}${customer.service_duration_minutes ? ' minutes' : ''}</p>
                    </div>
                    <div class="profile-field">
                        <label>Difficulty</label>
                        <p>${customer.difficulty || 'N/A'}</p>
                    </div>
                    <div class="profile-field">
                        <label>Assigned Tech</label>
                        <p>${customer.assigned_tech?.name || 'Unassigned'}</p>
                    </div>
                    <div class="profile-field">
                        <label>Service Day Locked</label>
                        <p>${customer.locked ? 'Yes' : 'No'}</p>
                    </div>
                </div>
            </div>
        </div>
    `;
}

async function editCustomer(customerId) {
    // Fetch customer data first
    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/${customerId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch customer');
        }
        const customer = await response.json();
        console.log('Customer data loaded:', customer);
        showEditCustomerForm(customer);
    } catch (error) {
        console.error('Error loading customer for edit:', error);
        alert('Failed to load customer. Please try again.');
    }
}


// ========================================
// Customer CRUD Operations
// ========================================

function showAddCustomerForm() {
    const container = document.getElementById('tab-profile');

    const formHtml = `
        <div class="customer-form">
            <h3>Add New Customer</h3>

            <div class="control-group">
                <label>Service Type: <span class="required">*</span></label>
                <select id="customer-service-type" onchange="toggleCustomerTypeFields()">
                    <option value="residential">Residential</option>
                    <option value="commercial">Commercial</option>
                </select>
            </div>

            <div id="residential-fields">
                <div class="control-group">
                    <label>First Name:</label>
                    <input type="text" id="customer-first-name" placeholder="John">
                </div>
                <div class="control-group">
                    <label>Last Name:</label>
                    <input type="text" id="customer-last-name" placeholder="Smith">
                </div>
            </div>

            <div id="commercial-fields" style="display: none;">
                <div class="control-group">
                    <label>Name:</label>
                    <input type="text" id="customer-business-name" placeholder="ABC Pool Service">
                </div>
                <div class="control-group">
                    <label>Management Company:</label>
                    <input type="text" id="customer-mgmt-company" placeholder="Optional">
                </div>
                <div class="control-group">
                    <label>Invoice Email:</label>
                    <input type="email" id="customer-invoice-email" placeholder="billing@example.com">
                </div>
            </div>

            <div class="control-group">
                <label>Street Address: <span class="required">*</span></label>
                <input type="text" id="customer-street" placeholder="123 Main St">
            </div>
            <div class="control-group">
                <label>City: <span class="required">*</span></label>
                <input type="text" id="customer-city" placeholder="Phoenix">
            </div>
            <div class="control-group">
                <label>State: <span class="required">*</span></label>
                <input type="text" id="customer-state" placeholder="AZ" maxlength="2">
            </div>
            <div class="control-group">
                <label>ZIP: <span class="required">*</span></label>
                <input type="text" id="customer-zip" placeholder="85001">
            </div>

            <div class="control-group">
                <label>Email:</label>
                <input type="email" id="customer-email" placeholder="customer@example.com">
            </div>
            <div class="control-group">
                <label>Phone:</label>
                <input type="tel" id="customer-phone" placeholder="555-1234">
            </div>
            <div class="control-group">
                <label>Alt Email:</label>
                <input type="email" id="customer-alt-email" placeholder="Optional">
            </div>
            <div class="control-group">
                <label>Alt Phone:</label>
                <input type="tel" id="customer-alt-phone" placeholder="Optional">
            </div>

            <div class="control-group">
                <label>Service Days Per Week:</label>
                <select id="customer-days-per-week" onchange="toggleDaySelection()">
                    <option value="1">1 day/week</option>
                    <option value="2">2 days/week</option>
                    <option value="3">3 days/week</option>
                </select>
            </div>

            <div id="single-day-selector" class="control-group">
                <label>Service Day: <span class="required">*</span></label>
                <select id="customer-service-day">
                    <option value="monday">Monday</option>
                    <option value="tuesday">Tuesday</option>
                    <option value="wednesday">Wednesday</option>
                    <option value="thursday">Thursday</option>
                    <option value="friday">Friday</option>
                    <option value="saturday">Saturday</option>
                    <option value="sunday">Sunday</option>
                </select>
            </div>

            <div id="multi-day-selector" class="control-group" style="display: none;">
                <label>Service Days: <span class="required">*</span></label>
                <select id="customer-service-schedule">
                    <!-- Populated by toggleDaySelection() -->
                </select>
            </div>

            <div class="control-group">
                <label>Visit Duration (minutes):</label>
                <input type="number" id="customer-visit-duration" min="5" max="120" value="15">
            </div>

            <div class="control-group">
                <label>Difficulty (1-5):</label>
                <input type="number" id="customer-difficulty" min="1" max="5" value="1">
            </div>

            <div class="control-group">
                <label>Service Rate ($):</label>
                <input type="number" id="customer-service-rate" step="0.01" min="0" placeholder="125.00">
            </div>

            <div class="control-group">
                <label>Billing Frequency:</label>
                <select id="customer-billing-frequency">
                    <option value="">-- Select --</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="per-visit">Per Visit</option>
                </select>
            </div>

            <div class="control-group">
                <label>Notes:</label>
                <textarea id="customer-notes" rows="3" placeholder="Optional notes"></textarea>
            </div>

            <div class="control-group">
                <label>
                    <input type="checkbox" id="customer-locked">
                    Lock service day (cannot be reassigned during optimization)
                </label>
            </div>

            <button class="btn-primary" onclick="saveCustomer()">Save Customer</button>
            <button class="btn-secondary" onclick="loadCustomersManagement()">Cancel</button>
        </div>
    `;

    container.innerHTML = formHtml;
}

function toggleCustomerTypeFields() {
    const serviceType = document.getElementById('customer-service-type').value;
    const residentialFields = document.getElementById('residential-fields');
    const commercialFields = document.getElementById('commercial-fields');
    const daysPerWeekSelect = document.getElementById('customer-days-per-week');

    if (serviceType === 'residential') {
        residentialFields.style.display = 'block';
        commercialFields.style.display = 'none';
        // Residential can have 1, 2, or 3 days
        daysPerWeekSelect.innerHTML = `
            <option value="1">1 day/week</option>
            <option value="2">2 days/week</option>
            <option value="3">3 days/week</option>
        `;
    } else {
        residentialFields.style.display = 'none';
        commercialFields.style.display = 'block';
        // Commercial can only have 2 or 3 days
        daysPerWeekSelect.innerHTML = `
            <option value="2">2 days/week</option>
            <option value="3">3 days/week</option>
        `;
    }
    // Trigger day selection update
    toggleDaySelection();
}

function toggleDaySelection() {
    const daysPerWeek = parseInt(document.getElementById('customer-days-per-week').value);
    const singleDaySelector = document.getElementById('single-day-selector');
    const multiDaySelector = document.getElementById('multi-day-selector');
    const scheduleSelect = document.getElementById('customer-service-schedule');

    if (daysPerWeek === 1) {
        singleDaySelector.style.display = 'block';
        multiDaySelector.style.display = 'none';
    } else {
        singleDaySelector.style.display = 'none';
        multiDaySelector.style.display = 'block';

        if (daysPerWeek === 2) {
            scheduleSelect.innerHTML = `
                <option value="Mo/Th">Mo/Th</option>
                <option value="Tu/Fr">Tu/Fr</option>
            `;
            scheduleSelect.disabled = false;
        } else if (daysPerWeek === 3) {
            scheduleSelect.innerHTML = `
                <option value="Mo/We/Fr">Mo/We/Fr</option>
            `;
            scheduleSelect.disabled = true;
        }
    }
}

async function saveCustomer() {
    const serviceType = document.getElementById('customer-service-type').value;

    // Get address fields
    const street = document.getElementById('customer-street').value;
    const city = document.getElementById('customer-city').value;
    const state = document.getElementById('customer-state').value;
    const zip = document.getElementById('customer-zip').value;

    if (!street || !city || !state || !zip) {
        alert('Please fill in all required address fields');
        return;
    }

    const address = `${street}, ${city}, ${state} ${zip}`;

    // Get service days
    const daysPerWeek = parseInt(document.getElementById('customer-days-per-week').value);
    let serviceDay;
    let serviceSchedule = null;

    if (daysPerWeek === 1) {
        // Single day - get from dropdown
        serviceDay = document.getElementById('customer-service-day').value;
    } else {
        // Multi-day - get from schedule dropdown
        serviceSchedule = document.getElementById('customer-service-schedule').value;

        // Map schedule to primary service day
        if (serviceSchedule === 'Mo/Th' || serviceSchedule === 'Mo/We/Fr') {
            serviceDay = 'monday';
        } else if (serviceSchedule === 'Tu/Fr') {
            serviceDay = 'tuesday';
        }
    }

    const data = {
        service_type: serviceType,
        address: address,
        service_day: serviceDay,
        service_days_per_week: daysPerWeek,
        visit_duration: parseInt(document.getElementById('customer-visit-duration').value),
        difficulty: parseInt(document.getElementById('customer-difficulty').value),
        locked: document.getElementById('customer-locked').checked
    };

    if (serviceSchedule) {
        data.service_schedule = serviceSchedule;
    }

    // Residential or Commercial specific fields
    if (serviceType === 'residential') {
        data.first_name = document.getElementById('customer-first-name').value;
        data.last_name = document.getElementById('customer-last-name').value;
    } else {
        data.name = document.getElementById('customer-business-name').value;
        const mgmtCompany = document.getElementById('customer-mgmt-company').value;
        const invoiceEmail = document.getElementById('customer-invoice-email').value;
        if (mgmtCompany) data.management_company = mgmtCompany;
        if (invoiceEmail) data.invoice_email = invoiceEmail;
    }

    // Contact info
    const email = document.getElementById('customer-email').value;
    const phone = document.getElementById('customer-phone').value;
    const altEmail = document.getElementById('customer-alt-email').value;
    const altPhone = document.getElementById('customer-alt-phone').value;
    if (email) data.email = email;
    if (phone) data.phone = phone;
    if (altEmail) data.alt_email = altEmail;
    if (altPhone) data.alt_phone = altPhone;

    // Billing
    const serviceRate = document.getElementById('customer-service-rate').value;
    const billingFreq = document.getElementById('customer-billing-frequency').value;
    if (serviceRate) data.service_rate = parseFloat(serviceRate);
    if (billingFreq) data.billing_frequency = billingFreq;

    // Notes
    const notes = document.getElementById('customer-notes').value;
    if (notes) data.notes = notes;

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error('Failed to create customer');
        }

        alert('Customer created successfully!');
        loadCustomersManagement();
        if (typeof loadCustomers === 'function') {
            loadCustomers();
        }
        if (typeof showBulkEditCustomers === 'function' && document.getElementById('bulk-edit-modal').classList.contains('active')) {
            showBulkEditCustomers();
        }
    } catch (error) {
        console.error('Error creating customer:', error);
        alert('Failed to create customer. Please try again.');
    }
}

async function deleteCustomer(customerId) {
    if (!confirm('Are you sure you want to delete this customer?')) {
        return;
    }

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/${customerId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete customer');
        }

        loadCustomersManagement();
        if (typeof loadCustomers === 'function') {
            loadCustomers(); // Reload map
        }
    } catch (error) {
        console.error('Error deleting customer:', error);
        alert('Failed to delete customer. Please try again.');
    }
}

// ========================================
// Customer Edit Functions
// ========================================

async function showEditCustomerForm(customer) {
    try {
        console.log('showEditCustomerForm called with:', customer);
        const container = document.getElementById('tab-profile');

        // Fetch techs for the dropdown
        let driversOptions = '<option value="">None</option>';
        try {
            const driversResponse = await Auth.apiRequest(`${API_BASE}/api/techs/`);
            if (driversResponse.ok) {
                const driversData = await driversResponse.json();
                driversOptions += driversData.techs.map(tech =>
                    `<option value="${escapeHtml(tech.id)}" ${customer.assigned_tech_id === tech.id ? 'selected' : ''}>${escapeHtml(tech.name)}</option>`
                ).join('');
            }
        } catch (error) {
            console.error('Error loading techs:', error);
        }

        // Fetch management companies for the datalist
        let managementCompaniesOptions = '';
        try {
            const companiesResponse = await Auth.apiRequest(`${API_BASE}/api/customers/management-companies`);
            if (companiesResponse.ok) {
                const companies = await companiesResponse.json();
                managementCompaniesOptions = companies.map(company =>
                    `<option value="${escapeHtml(company)}">`
                ).join('');
            }
        } catch (error) {
            console.error('Error loading management companies:', error);
        }

        const addr = parseAddress(customer.address || '');
        console.log('Parsed address:', addr);
        console.log('Customer name:', customer.name);
        console.log('Service type:', customer.service_type);

    // Determine icon based on service type
        const serviceIcon = customer.service_type === 'commercial' ? 'fa-building' : 'fa-home';
        const displayName = customer.display_name || customer.name;

    const formHtml = `
        <div class="customer-form-header">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <i class="fas ${serviceIcon} profile-icon"></i>
                <h3>${displayName}</h3>
            </div>
            <div class="form-actions">
                <button id="update-customer-btn" class="btn-icon btn-icon-primary" onclick="updateCustomer('${customer.id}')" disabled title="Save Changes">
                    <i class="fas fa-save"></i>
                </button>
                <button class="btn-icon btn-icon-secondary" onclick="cancelEditCustomer('${customer.id}')" title="Cancel">
                    <i class="fas fa-times"></i>
                </button>
                <button class="btn-icon btn-icon-danger" onclick="deleteCustomer('${customer.id}')" title="Delete Customer">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
        <div class="customer-form">
            <div class="form-section">
                <h4>Name</h4>
                <div class="form-row" id="residential-name-fields" style="display: ${customer.service_type === 'residential' ? 'flex' : 'none'};">
                    <div class="control-group" style="flex: 1;">
                        <label>Last Name:</label>
                        <input type="text" id="edit-customer-last-name" value="${escapeHtml(customer.last_name || '')}" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>First Name:</label>
                        <input type="text" id="edit-customer-first-name" value="${escapeHtml(customer.first_name || '')}" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" id="commercial-name-field" style="display: ${customer.service_type === 'commercial' ? 'flex' : 'none'};">
                    <div class="control-group" style="flex: 1;">
                        <label>Business Name:</label>
                        <input type="text" id="edit-customer-name" value="${escapeHtml(customer.name || '')}" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" style="margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Display Name:</label>
                        <input type="text" id="edit-customer-display-name" value="${escapeHtml(customer.display_name || '')}" placeholder="Auto-generated if left blank" oninput="detectFormChanges()">
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h4>Address</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 3;">
                        <label>Street:</label>
                        <input type="text" id="edit-customer-street" value="${escapeHtml(addr.street)}" placeholder="123 Main Street" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 2;">
                        <label>City:</label>
                        <input type="text" id="edit-customer-city" value="${escapeHtml(addr.city)}" placeholder="Sacramento" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>State:</label>
                        <input type="text" id="edit-customer-state" value="${escapeHtml(addr.state)}" placeholder="CA" maxlength="2" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Zip:</label>
                        <input type="text" id="edit-customer-zip" value="${escapeHtml(addr.zip)}" placeholder="95814" maxlength="10" oninput="detectFormChanges()">
                    </div>
                </div>
            </div>

            <div class="form-section" style="margin-top: 2rem;">
                <h4>Contact</h4>
                <div class="form-row">
                    <div class="control-group" style="flex: 1;">
                        <label>Email:</label>
                        <input type="email" id="edit-customer-email" value="${escapeHtml(customer.email || '')}" placeholder="email@example.com" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>Phone:</label>
                        <input type="tel" id="edit-customer-phone" value="${escapeHtml(customer.phone || '')}" placeholder="(555) 123-4567" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" style="margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Alt Email:</label>
                        <input type="email" id="edit-customer-alt-email" value="${escapeHtml(customer.alt_email || '')}" placeholder="alt@example.com" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>Alt Phone:</label>
                        <input type="tel" id="edit-customer-alt-phone" value="${escapeHtml(customer.alt_phone || '')}" placeholder="(555) 987-6543" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" id="commercial-invoice-email-field" style="display: ${customer.service_type === 'commercial' ? 'flex' : 'none'}; margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Invoice Email:</label>
                        <input type="email" id="edit-customer-invoice-email" value="${escapeHtml(customer.invoice_email || '')}" placeholder="invoices@example.com" oninput="detectFormChanges()">
                    </div>
                </div>
                <div class="form-row" id="commercial-management-field" style="display: ${customer.service_type === 'commercial' ? 'flex' : 'none'}; margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Management Company:</label>
                        <input type="text" id="edit-customer-management-company" value="${escapeHtml(customer.management_company || '')}" list="management-companies-datalist" oninput="detectFormChanges()">
                        <datalist id="management-companies-datalist">
                            ${managementCompaniesOptions}
                        </datalist>
                    </div>
                </div>
            </div>

            <div class="form-section" style="margin-top: 2rem;">
                <h4>Service</h4>
                <div class="form-row">
                    <div class="control-group control-group-medium">
                        <label>Type:</label>
                        <select id="edit-customer-service-type" onchange="toggleNameFields(); detectFormChanges();">
                            <option value="residential" ${customer.service_type === 'residential' ? 'selected' : ''}>Residential</option>
                            <option value="commercial" ${customer.service_type === 'commercial' ? 'selected' : ''}>Commercial</option>
                        </select>
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Status:</label>
                        <select id="edit-customer-status" onchange="detectFormChanges();">
                            <option value="pending" ${customer.status === 'pending' ? 'selected' : ''}>Pending</option>
                            <option value="active" ${customer.status === 'active' ? 'selected' : ''}>Active</option>
                            <option value="inactive" ${customer.status === 'inactive' ? 'selected' : ''}>Inactive</option>
                        </select>
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Days Per Week:</label>
                        <select id="edit-customer-days-per-week" onchange="updateCustomerServiceDayOptions(); detectFormChanges();">
                            <option value="1" ${customer.service_days_per_week === 1 ? 'selected' : ''}>1 day</option>
                            <option value="2" ${customer.service_days_per_week === 2 ? 'selected' : ''}>2 days</option>
                            <option value="3" ${customer.service_days_per_week === 3 ? 'selected' : ''}>3 days</option>
                        </select>
                    </div>
                    <div class="control-group" style="flex: 1;">
                        <label>Service Day:</label>
                        <select id="edit-customer-service-day" onchange="detectFormChanges()">
                        </select>
                    </div>
                    <div class="control-group">
                        <label>
                            <input type="checkbox" id="edit-customer-locked" ${customer.locked ? 'checked' : ''} onchange="detectFormChanges()">
                            Lock service day
                        </label>
                    </div>
                </div>
                <div class="form-row" style="margin-top: 1rem;">
                    <div class="control-group" style="flex: 1;">
                        <label>Assigned Tech:</label>
                        <select id="edit-customer-assigned-tech" onchange="detectFormChanges()">
                            ${driversOptions}
                        </select>
                    </div>
                    <div class="control-group control-group-medium">
                        <label>Duration (minutes):</label>
                        <input type="number" id="edit-customer-visit-duration" min="5" max="120" value="${customer.visit_duration || 15}" oninput="detectFormChanges()">
                    </div>
                    <div class="control-group control-group-narrow">
                        <label>Difficulty:</label>
                        <input type="number" id="edit-customer-difficulty" min="1" max="5" value="${customer.difficulty}" oninput="detectFormChanges()">
                    </div>
                </div>
            </div>
        </div>
    `;

        container.innerHTML = formHtml;
        console.log('Edit form HTML rendered successfully');

        // Initialize autocomplete on street field
        setTimeout(() => {
            try {
                console.log('Initializing form fields...');
                const streetInput = document.getElementById('edit-customer-street');
                if (streetInput && typeof initAutocomplete === 'function') {
                    initAutocomplete(streetInput);
                }

                // Initialize service day options based on current days per week
                console.log('Calling updateCustomerServiceDayOptions with:', customer.service_day, customer.service_schedule);
                updateCustomerServiceDayOptions(customer.service_day, customer.service_schedule);

                // Store original form values for change detection
                console.log('Storing original form values');
                storeOriginalFormValues();
                console.log('Form initialization complete');
            } catch (error) {
                console.error('Error during form initialization:', error);
                console.error('Customer service_day:', customer.service_day);
                console.error('Customer service_schedule:', customer.service_schedule);
            }
        }, 100);
    } catch (error) {
        console.error('Error in showEditCustomerForm:', error);
        console.error('Customer data that caused error:', customer);
        alert('Failed to display edit form. Check console for details.');
    }
}

function storeOriginalFormValues() {
    originalFormValues = {
        serviceType: document.getElementById('edit-customer-service-type')?.value,
        status: document.getElementById('edit-customer-status')?.value,
        lastName: document.getElementById('edit-customer-last-name')?.value,
        firstName: document.getElementById('edit-customer-first-name')?.value,
        name: document.getElementById('edit-customer-name')?.value,
        displayName: document.getElementById('edit-customer-display-name')?.value,
        street: document.getElementById('edit-customer-street')?.value,
        city: document.getElementById('edit-customer-city')?.value,
        state: document.getElementById('edit-customer-state')?.value,
        zip: document.getElementById('edit-customer-zip')?.value,
        email: document.getElementById('edit-customer-email')?.value,
        phone: document.getElementById('edit-customer-phone')?.value,
        altEmail: document.getElementById('edit-customer-alt-email')?.value,
        altPhone: document.getElementById('edit-customer-alt-phone')?.value,
        invoiceEmail: document.getElementById('edit-customer-invoice-email')?.value,
        managementCompany: document.getElementById('edit-customer-management-company')?.value,
        daysPerWeek: document.getElementById('edit-customer-days-per-week')?.value,
        serviceDay: document.getElementById('edit-customer-service-day')?.value,
        locked: document.getElementById('edit-customer-locked')?.checked,
        assignedTech: document.getElementById('edit-customer-assigned-tech')?.value,
        visitDuration: document.getElementById('edit-customer-visit-duration')?.value,
        difficulty: document.getElementById('edit-customer-difficulty')?.value
    };
}

function detectFormChanges() {
    const currentValues = {
        serviceType: document.getElementById('edit-customer-service-type')?.value,
        status: document.getElementById('edit-customer-status')?.value,
        lastName: document.getElementById('edit-customer-last-name')?.value,
        firstName: document.getElementById('edit-customer-first-name')?.value,
        name: document.getElementById('edit-customer-name')?.value,
        displayName: document.getElementById('edit-customer-display-name')?.value,
        street: document.getElementById('edit-customer-street')?.value,
        city: document.getElementById('edit-customer-city')?.value,
        state: document.getElementById('edit-customer-state')?.value,
        zip: document.getElementById('edit-customer-zip')?.value,
        email: document.getElementById('edit-customer-email')?.value,
        phone: document.getElementById('edit-customer-phone')?.value,
        altEmail: document.getElementById('edit-customer-alt-email')?.value,
        altPhone: document.getElementById('edit-customer-alt-phone')?.value,
        invoiceEmail: document.getElementById('edit-customer-invoice-email')?.value,
        managementCompany: document.getElementById('edit-customer-management-company')?.value,
        daysPerWeek: document.getElementById('edit-customer-days-per-week')?.value,
        serviceDay: document.getElementById('edit-customer-service-day')?.value,
        locked: document.getElementById('edit-customer-locked')?.checked,
        assignedTech: document.getElementById('edit-customer-assigned-tech')?.value,
        visitDuration: document.getElementById('edit-customer-visit-duration')?.value,
        difficulty: document.getElementById('edit-customer-difficulty')?.value
    };

    // Compare current values with original
    let hasChanges = false;
    for (const key in originalFormValues) {
        if (originalFormValues[key] !== currentValues[key]) {
            hasChanges = true;
            break;
        }
    }

    // Enable/disable Update button
    const updateBtn = document.getElementById('update-customer-btn');
    if (updateBtn) {
        updateBtn.disabled = !hasChanges;
    }
}

async function cancelEditCustomer(customerId) {
    // Fetch the customer again and show their profile
    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/${customerId}`);
        if (response.ok) {
            const customer = await response.json();
            displayClientProfile(customer);
        }
    } catch (error) {
        console.error('Error reloading customer profile:', error);
    }
}

function updateCustomerServiceDayOptions(currentServiceDay = null, currentSchedule = null) {
    console.log('updateCustomerServiceDayOptions called with:', {currentServiceDay, currentSchedule});

    const daysPerWeekSelect = document.getElementById('edit-customer-days-per-week');
    const serviceDaySelect = document.getElementById('edit-customer-service-day');

    if (!daysPerWeekSelect || !serviceDaySelect) {
        console.error('Required elements not found:', {daysPerWeekSelect, serviceDaySelect});
        return;
    }

    const daysPerWeek = parseInt(daysPerWeekSelect.value);
    console.log('Days per week:', daysPerWeek);

    // Determine current selection
    let selectedValue = currentServiceDay;
    if (daysPerWeek > 1 && currentSchedule) {
        selectedValue = currentSchedule;
    }
    console.log('Selected value to use:', selectedValue);

    if (daysPerWeek === 1) {
        // Single day - show all weekdays
        serviceDaySelect.innerHTML = `
            <option value="monday" ${selectedValue === 'monday' ? 'selected' : ''}>Monday</option>
            <option value="tuesday" ${selectedValue === 'tuesday' ? 'selected' : ''}>Tuesday</option>
            <option value="wednesday" ${selectedValue === 'wednesday' ? 'selected' : ''}>Wednesday</option>
            <option value="thursday" ${selectedValue === 'thursday' ? 'selected' : ''}>Thursday</option>
            <option value="friday" ${selectedValue === 'friday' ? 'selected' : ''}>Friday</option>
            <option value="saturday" ${selectedValue === 'saturday' ? 'selected' : ''}>Saturday</option>
        `;
        serviceDaySelect.disabled = false;
    } else if (daysPerWeek === 2) {
        // Two days - show Mo/Th and Tu/Fr
        serviceDaySelect.innerHTML = `
            <option value="Mo/Th" ${selectedValue === 'Mo/Th' ? 'selected' : ''}>Mo/Th</option>
            <option value="Tu/Fr" ${selectedValue === 'Tu/Fr' ? 'selected' : ''}>Tu/Fr</option>
        `;
        serviceDaySelect.disabled = false;
    } else if (daysPerWeek === 3) {
        // Three days - only Mo/We/Fr, disabled
        serviceDaySelect.innerHTML = `
            <option value="Mo/We/Fr">Mo/We/Fr</option>
        `;
        serviceDaySelect.disabled = true;
    }

    console.log('Service day dropdown updated with', serviceDaySelect.options.length, 'options');
}

function toggleNameFields() {
    const serviceType = document.getElementById('edit-customer-service-type').value;
    const residentialFields = document.getElementById('residential-name-fields');
    const commercialField = document.getElementById('commercial-name-field');
    const managementField = document.getElementById('commercial-management-field');
    const invoiceEmailField = document.getElementById('commercial-invoice-email-field');

    if (serviceType === 'residential') {
        residentialFields.style.display = 'flex';
        commercialField.style.display = 'none';
        if (managementField) managementField.style.display = 'none';
        if (invoiceEmailField) invoiceEmailField.style.display = 'none';
    } else {
        residentialFields.style.display = 'none';
        commercialField.style.display = 'flex';
        if (managementField) managementField.style.display = 'flex';
        if (invoiceEmailField) invoiceEmailField.style.display = 'flex';
    }
}

async function updateCustomer(customerId) {
    const serviceType = document.getElementById('edit-customer-service-type').value;
    const status = document.getElementById('edit-customer-status').value;

    // Get name fields based on service type
    let name = null;
    let firstName = null;
    let lastName = null;

    if (serviceType === 'residential') {
        firstName = document.getElementById('edit-customer-first-name').value;
        lastName = document.getElementById('edit-customer-last-name').value;
        if (!firstName || !lastName) {
            alert('Please fill in first and last name');
            return;
        }
    } else {
        name = document.getElementById('edit-customer-name').value;
        if (!name) {
            alert('Please fill in business name');
            return;
        }
    }

    const street = document.getElementById('edit-customer-street').value;
    const city = document.getElementById('edit-customer-city').value;
    const state = document.getElementById('edit-customer-state').value;
    const zip = document.getElementById('edit-customer-zip').value;
    const address = combineAddressFields(street, city, state, zip);

    const assignedTechId = document.getElementById('edit-customer-assigned-tech').value || null;
    const serviceDayValue = document.getElementById('edit-customer-service-day').value;
    const daysPerWeek = parseInt(document.getElementById('edit-customer-days-per-week').value);
    const difficulty = parseInt(document.getElementById('edit-customer-difficulty').value);
    const visitDuration = parseInt(document.getElementById('edit-customer-visit-duration').value);
    const locked = document.getElementById('edit-customer-locked').checked;

    if (!address) {
        alert('Please fill in all required fields');
        return;
    }

    // Determine service_day and service_schedule based on daysPerWeek
    let serviceDay;
    let schedule;

    if (daysPerWeek === 1) {
        // Single day - value is the day name
        serviceDay = serviceDayValue;
        schedule = null;
    } else if (daysPerWeek === 2) {
        // Two days - value is schedule like "Mo/Th" or "Tu/Fr"
        schedule = serviceDayValue;
        // Extract primary day from schedule
        if (serviceDayValue === 'Mo/Th') {
            serviceDay = 'monday';
        } else if (serviceDayValue === 'Tu/Fr') {
            serviceDay = 'tuesday';
        }
    } else if (daysPerWeek === 3) {
        // Three days - always Mo/We/Fr
        serviceDay = 'monday';
        schedule = 'Mo/We/Fr';
    }

    // Capture contact and management fields
    const email = document.getElementById('edit-customer-email').value || null;
    const phone = document.getElementById('edit-customer-phone').value || null;
    const altEmail = document.getElementById('edit-customer-alt-email').value || null;
    const altPhone = document.getElementById('edit-customer-alt-phone').value || null;
    const invoiceEmail = document.getElementById('edit-customer-invoice-email').value || null;
    const managementCompany = document.getElementById('edit-customer-management-company').value || null;
    const displayName = document.getElementById('edit-customer-display-name').value || null;

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/${customerId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                first_name: firstName,
                last_name: lastName,
                display_name: displayName,
                address: address,
                email: email,
                phone: phone,
                alt_email: altEmail,
                alt_phone: altPhone,
                invoice_email: invoiceEmail,
                management_company: managementCompany,
                assigned_tech_id: assignedTechId,
                service_day: serviceDay,
                service_type: serviceType,
                service_days_per_week: daysPerWeek,
                service_schedule: schedule,
                difficulty: difficulty,
                visit_duration: visitDuration,
                locked: locked,
                status: status
            })
        });

        if (!response.ok) {
            throw new Error('Failed to update customer');
        }

        const updatedCustomer = await response.json();
        alert('Customer updated successfully!');

        // Reload the customer list in sidebar (in case name changed)
        loadCustomersManagement();
        // Reload map markers
        if (typeof loadCustomers === 'function') {
            loadCustomers();
        }
        // Reload bulk edit if open
        if (typeof showBulkEditCustomers === 'function' && document.getElementById('bulk-edit-modal').classList.contains('active')) {
            showBulkEditCustomers();
        }
        // Show updated profile in detail panel
        displayClientProfile(updatedCustomer);
    } catch (error) {
        console.error('Error updating customer:', error);
        alert('Failed to update customer. Please try again.');
    }
}

// ========================================
// Event Listeners
// ========================================

function attachEventListeners() {
    // Note: optimize-btn listener is in modals.js (initOptimizationModal)
    document.getElementById('add-tech-btn').addEventListener('click', showAddTechForm);
    document.getElementById('add-customer-btn').addEventListener('click', showAddCustomerForm);

    // Bulk edit button
    const bulkEditBtn = document.getElementById('bulk-edit-btn');
    if (bulkEditBtn) {
        bulkEditBtn.addEventListener('click', () => {
            if (typeof openModal === 'function') {
                openModal('bulk-edit-modal');
                if (typeof showBulkEditCustomers === 'function') {
                    showBulkEditCustomers();
                }
            }
        });
    }
}

// ========================================
// Search & Filter
// ========================================

function initClientSearch() {
    const searchInput = document.getElementById('clients-search');
    if (!searchInput) return;

    searchInput.addEventListener('input', function(e) {
        const searchTerm = e.target.value.toLowerCase();
        const customerItems = document.querySelectorAll('.client-list-item');

        customerItems.forEach(item => {
            const text = item.textContent.toLowerCase();
            if (text.includes(searchTerm)) {
                item.style.display = '';
            } else {
                item.style.display = 'none';
            }
        });

        // Auto-select first visible item after search
        const firstVisibleItem = Array.from(customerItems).find(item => item.style.display !== 'none');
        if (firstVisibleItem) {
            firstVisibleItem.click();
        } else {
            // No visible items - show empty state
            const profilePane = document.getElementById('tab-profile');
            if (profilePane) {
                profilePane.innerHTML = '<div class="empty-state"><p>No clients match your search</p></div>';
            }
        }
    });
}

function initClientFilter() {
    const filterBtn = document.getElementById('clients-filter-btn');
    const modal = document.getElementById('clients-filter-modal');
    if (!filterBtn || !modal) return;

    filterBtn.addEventListener('click', function() {
        if (typeof openModal === 'function') {
            openModal('clients-filter-modal');
        }
    });

    // Close modal when clicking X
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            if (typeof closeModal === 'function') {
                closeModal('clients-filter-modal');
            }
        });
    }

    // Close modal when clicking outside
    modal.addEventListener('click', function(e) {
        if (e.target === modal && typeof closeModal === 'function') {
            closeModal('clients-filter-modal');
        }
    });

    // Apply filter button
    const applyBtn = document.getElementById('apply-filter-btn');
    if (applyBtn) {
        applyBtn.addEventListener('click', applyClientFilters);
    }

    // Clear filter button
    const clearBtn = document.getElementById('clear-filter-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            document.getElementById('filter-service-day').value = '';
            document.getElementById('filter-assigned-tech').value = '';
            document.getElementById('filter-service-type').value = '';
            document.getElementById('filter-status').value = 'active';

            // Reset filter state
            currentFilters = {
                serviceDay: '',
                assignedTech: '',
                serviceType: '',
                status: 'active'
            };

            loadCustomersManagement();
            if (typeof closeModal === 'function') {
                closeModal('clients-filter-modal');
            }
        });
    }
}

async function applyClientFilters() {
    const serviceDay = document.getElementById('filter-service-day').value;
    const assignedTech = document.getElementById('filter-assigned-tech').value;
    const serviceType = document.getElementById('filter-service-type').value;
    const status = document.getElementById('filter-status').value;

    // Save filter state
    currentFilters = {
        serviceDay: serviceDay,
        assignedTech: assignedTech,
        serviceType: serviceType,
        status: status
    };

    // Reload with new filters
    await loadCustomersManagement();

    if (typeof closeModal === 'function') {
        closeModal('clients-filter-modal');
    }
}

function initQuickFilter() {
    const filterButtons = document.querySelectorAll('.quick-filter-btn');
    if (!filterButtons.length) return;

    filterButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const filterType = this.dataset.filter;

            // Update active state
            filterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Filter customer list items
            const customerItems = document.querySelectorAll('.client-list-item');
            customerItems.forEach(item => {
                const customerId = item.dataset.customerId;
                // Find the customer data from the stored dataset
                const customerData = item.querySelector('.client-list-item-name');
                if (!customerData) return;

                // Show/hide based on filter
                if (filterType === 'all') {
                    item.style.display = '';
                } else {
                    // Get service type from customer data attribute (we'll need to add this)
                    const serviceType = item.dataset.serviceType;
                    if (serviceType === filterType) {
                        item.style.display = '';
                    } else {
                        item.style.display = 'none';
                    }
                }
            });

            // Auto-select first visible item
            const firstVisibleItem = Array.from(customerItems).find(item => item.style.display !== 'none');
            if (firstVisibleItem) {
                firstVisibleItem.click();
            } else {
                // No visible items - show empty state
                const profilePane = document.getElementById('tab-profile');
                if (profilePane) {
                    profilePane.innerHTML = '<div class="empty-state"><p>No clients match this filter</p></div>';
                }
            }
        });
    });
}
