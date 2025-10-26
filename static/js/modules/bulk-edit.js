/**
 * Bulk Edit Module
 *
 * Handles bulk editing of customers through modal interface with inline table editing,
 * CSV import/export functionality, and change tracking.
 *
 * Dependencies:
 * - Global variables: API_BASE, window.allTechs
 * - Functions: escapeHtml() (from app.js), combineAddressFields() (from app.js),
 *              loadCustomersManagement() (from customers.js), loadCustomers() (from map.js)
 *
 * Extracted from app.js as part of incremental refactoring.
 * Lines extracted: 1769-1880, 3047-3302
 */

// Global state for bulk edit
let bulkEditCustomers = [];
let modifiedCustomers = new Set();

/**
 * Initialize bulk edit modal event listeners
 * Sets up CSV import, template download, export functionality, and close button
 */
function initBulkEditModal() {
    const modal = document.getElementById('bulk-edit-modal');

    // Helper function to close modal with unsaved changes warning
    const closeModalWithWarning = () => {
        if (modifiedCustomers.size > 0) {
            if (!confirm(`You have ${modifiedCustomers.size} unsaved change${modifiedCustomers.size !== 1 ? 's' : ''}. Close without saving?`)) {
                return;
            }
        }
        modal.classList.remove('active');
        modifiedCustomers.clear();

        // Reset save button state
        const saveBtn = document.getElementById('save-bulk-changes-btn');
        if (saveBtn) {
            saveBtn.disabled = true;
        }
    };

    // Close button
    const closeBtn = modal?.querySelector('.modal-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModalWithWarning);
    }

    // Click outside to close
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModalWithWarning();
            }
        });
    }

    // CSV Import
    const importBtn = document.getElementById('import-csv-btn');
    if (importBtn) {
        importBtn.addEventListener('click', () => {
            document.getElementById('csv-file-input').click();
        });
    }

    const csvInput = document.getElementById('csv-file-input');
    if (csvInput) {
        csvInput.addEventListener('change', handleCSVImport);
    }

    // Download CSV Template
    const templateBtn = document.getElementById('download-template-btn');
    if (templateBtn) {
        templateBtn.addEventListener('click', downloadCSVTemplate);
    }

    // Export CSV
    const exportBtn = document.getElementById('export-csv-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportCustomersCSV);
    }

    // Save Changes
    const saveBtn = document.getElementById('save-bulk-changes-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveBulkEditChanges);
        // Initially disable save button
        saveBtn.disabled = true;
    }
}

/**
 * Handle CSV file import
 * Uploads CSV file to server for processing and importing customers
 *
 * @param {Event} event - File input change event
 */
async function handleCSVImport(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/import-csv`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to import CSV');
        }

        const result = await response.json();
        alert(`Successfully imported ${result.imported} customers`);

        // Reload customers
        loadCustomersManagement();
        loadCustomers();
    } catch (error) {
        console.error('Error importing CSV:', error);
        alert('Failed to import CSV. Please check the file format and try again.');
    } finally {
        // Clear file input
        event.target.value = '';
    }
}

/**
 * Download CSV template file
 * Generates a template CSV with headers for customer import
 */
function downloadCSVTemplate() {
    const headers = ['display_name', 'address', 'assigned_tech_name', 'service_day', 'service_days_per_week', 'service_type', 'visit_duration', 'difficulty', 'locked'];
    const csvContent = headers.join(',') + '\n' +
                      'John Smith,"123 Main St, Springfield, IL 62701",Tech Name,monday,1,residential,15,2,false';

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'customer_import_template.csv';
    a.click();
    window.URL.revokeObjectURL(url);
}

/**
 * Export all customers to CSV
 * Downloads a CSV file with all customer data
 */
async function exportCustomersCSV() {
    try {
        const response = await Auth.apiRequest(`${API_BASE}/api/customers/export-csv`);
        if (!response.ok) {
            throw new Error('Failed to export CSV');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `customers_export_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Error exporting CSV:', error);
        alert('Failed to export CSV. Please try again.');
    }
}

/**
 * Show bulk edit modal with all customers loaded
 * Loads all customers (no day filtering) and displays in editable table
 */
async function showBulkEditCustomers() {
    try {
        // Fetch techs first if not already loaded
        if (!window.allTechs || window.allTechs.length === 0) {
            const driversResponse = await Auth.apiRequest(`${API_BASE}/api/techs`);
            if (driversResponse.ok) {
                const driversData = await driversResponse.json();
                window.allTechs = driversData.techs;  // Extract techs array from response
            }
        }

        // Load ALL customers (no day filtering for bulk edit)
        const url = `${API_BASE}/api/customers?page_size=1000`;

        const response = await Auth.apiRequest(url);
        if (!response.ok) {
            throw new Error('Failed to load customers');
        }

        const data = await response.json();
        bulkEditCustomers = data.customers;
        modifiedCustomers.clear();

        renderBulkEditTable();

        // Disable save button initially (no changes yet)
        const saveBtn = document.getElementById('save-bulk-changes-btn');
        if (saveBtn) {
            saveBtn.disabled = true;
        }

        // Open the modal
        const modal = document.getElementById('bulk-edit-modal');
        if (modal) {
            modal.classList.add('active');
        }
    } catch (error) {
        console.error('Error loading customers for bulk edit:', error);
        alert('Failed to load customers. Please try again.');
    }
}

/**
 * Render bulk edit table with all customers
 * Creates editable table rows for each customer with inline form controls
 */
function renderBulkEditTable() {
    const tbody = document.getElementById('bulk-edit-tbody');
    const countElement = document.getElementById('bulk-edit-count');

    if (!bulkEditCustomers || bulkEditCustomers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="20" style="text-align: center; padding: 2rem;">No customers found.</td></tr>';
        if (countElement) countElement.textContent = '0 clients loaded';
        return;
    }

    if (countElement) {
        countElement.textContent = `${bulkEditCustomers.length} client${bulkEditCustomers.length !== 1 ? 's' : ''} loaded`;
    }

    // Build tech options
    let driversOptions = '<option value="">Unassigned</option>';
    if (Array.isArray(window.allTechs)) {
        window.allTechs.forEach(tech => {
            driversOptions += `<option value="${tech.id}">${escapeHtml(tech.name)}</option>`;
        });
    }

    // Build management company options from unique values in customers
    const uniqueManagementCompanies = new Set();
    bulkEditCustomers.forEach(customer => {
        if (customer.management_company && customer.management_company.trim()) {
            uniqueManagementCompanies.add(customer.management_company.trim());
        }
    });
    let managementOptions = '<option value="">None</option>';
    Array.from(uniqueManagementCompanies).sort().forEach(company => {
        managementOptions += `<option value="${escapeHtml(company)}">${escapeHtml(company)}</option>`;
    });

    let tableHtml = '';
    bulkEditCustomers.forEach((customer, index) => {
        // Parse address into components
        const addressParts = customer.address.split(',').map(p => p.trim());
        const street = addressParts[0] || '';
        const city = addressParts[1] || '';
        const stateZip = addressParts[2] || '';
        const stateZipParts = stateZip.split(' ');
        const state = stateZipParts[0] || '';
        const zip = stateZipParts[1] || '';

        // Generate service day options based on service_days_per_week
        const daysPerWeek = customer.service_days_per_week || 1;
        let serviceDayOptions = '';
        let serviceDayDisabled = '';

        if (daysPerWeek === 2) {
            // For 2 days: Mo/Th or Tu/Fr - store as service_schedule pattern
            const currentSchedule = customer.service_schedule || '';
            serviceDayOptions = `
                <option value="Mo/Th" ${currentSchedule.includes('Mo') && currentSchedule.includes('Th') ? 'selected' : ''}>Mo/Th</option>
                <option value="Tu/Fr" ${currentSchedule.includes('Tu') && currentSchedule.includes('Fr') ? 'selected' : ''}>Tu/Fr</option>
            `;
        } else if (daysPerWeek === 3) {
            // For 3 days: Mo/We/Fr only (locked)
            serviceDayOptions = `<option value="Mo/We/Fr" selected>Mo/We/Fr</option>`;
            serviceDayDisabled = ' disabled';
        } else {
            // For 1 day: Normal dropdown
            serviceDayOptions = `
                <option value="monday" ${customer.service_day === 'monday' ? 'selected' : ''}>Monday</option>
                <option value="tuesday" ${customer.service_day === 'tuesday' ? 'selected' : ''}>Tuesday</option>
                <option value="wednesday" ${customer.service_day === 'wednesday' ? 'selected' : ''}>Wednesday</option>
                <option value="thursday" ${customer.service_day === 'thursday' ? 'selected' : ''}>Thursday</option>
                <option value="friday" ${customer.service_day === 'friday' ? 'selected' : ''}>Friday</option>
                <option value="saturday" ${customer.service_day === 'saturday' ? 'selected' : ''}>Saturday</option>
                <option value="sunday" ${customer.service_day === 'sunday' ? 'selected' : ''}>Sunday</option>
            `;
        }

        tableHtml += `
            <tr data-customer-id="${customer.id}" data-index="${index}">
                <td class="wide">
                    <select data-field="service_type" onchange="markCustomerModified('${customer.id}')">
                        <option value="residential" ${customer.service_type === 'residential' ? 'selected' : ''}>Res</option>
                        <option value="commercial" ${customer.service_type === 'commercial' ? 'selected' : ''}>Com</option>
                    </select>
                </td>
                <td class="xx-wide">
                    <input type="text" data-field="display_name" value="${escapeHtml(customer.display_name || '')}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="x-wide">
                    <input type="text" data-field="first_name" value="${escapeHtml(customer.first_name || '')}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="x-wide">
                    <input type="text" data-field="last_name" value="${escapeHtml(customer.last_name || '')}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="xx-wide">
                    <input type="text" data-field="street" value="${escapeHtml(street)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="x-wide">
                    <input type="text" data-field="city" value="${escapeHtml(city)}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="medium">
                    <input type="text" data-field="state" value="${escapeHtml(state)}" maxlength="2" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="medium">
                    <input type="text" data-field="zip" value="${escapeHtml(zip)}" maxlength="10" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="xx-wide">
                    <input type="email" data-field="email" value="${escapeHtml(customer.email || '')}" placeholder="email@example.com" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="x-wide">
                    <input type="tel" data-field="phone" value="${escapeHtml(customer.phone || '')}" placeholder="(555) 123-4567" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="xx-wide">
                    <input type="email" data-field="alt_email" value="${escapeHtml(customer.alt_email || '')}" placeholder="alt@example.com" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="x-wide">
                    <input type="tel" data-field="alt_phone" value="${escapeHtml(customer.alt_phone || '')}" placeholder="(555) 987-6543" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="xx-wide">
                    <input type="email" data-field="invoice_email" value="${escapeHtml(customer.invoice_email || '')}" placeholder="invoices@example.com" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="x-wide">
                    <select data-field="management_company" onchange="markCustomerModified('${customer.id}')">
                        ${managementOptions}
                    </select>
                </td>
                <td class="x-wide">
                    <select data-field="assigned_tech_id" onchange="markCustomerModified('${customer.id}')">
                        ${driversOptions}
                    </select>
                </td>
                <td class="x-wide">
                    <select data-field="service_day" onchange="markCustomerModified('${customer.id}')"${serviceDayDisabled}>
                        ${serviceDayOptions}
                    </select>
                </td>
                <td class="narrow">
                    <select data-field="service_days_per_week" onchange="updateServiceDayOptions(this); markCustomerModified('${customer.id}')">
                        <option value="1" ${customer.service_days_per_week === 1 ? 'selected' : ''}>1</option>
                        <option value="2" ${customer.service_days_per_week === 2 ? 'selected' : ''}>2</option>
                        <option value="3" ${customer.service_days_per_week === 3 ? 'selected' : ''}>3</option>
                    </select>
                </td>
                <td class="narrow">
                    <input type="number" data-field="visit_duration" min="5" max="120" value="${customer.visit_duration || 15}" onchange="markCustomerModified('${customer.id}')">
                </td>
                <td class="narrow">
                    <select data-field="difficulty" onchange="markCustomerModified('${customer.id}')">
                        <option value="1" ${customer.difficulty === 1 ? 'selected' : ''}>1</option>
                        <option value="2" ${customer.difficulty === 2 ? 'selected' : ''}>2</option>
                        <option value="3" ${customer.difficulty === 3 ? 'selected' : ''}>3</option>
                        <option value="4" ${customer.difficulty === 4 ? 'selected' : ''}>4</option>
                        <option value="5" ${customer.difficulty === 5 ? 'selected' : ''}>5</option>
                    </select>
                </td>
                <td class="narrow" style="text-align: center;">
                    <input type="checkbox" data-field="locked" ${customer.locked ? 'checked' : ''} onchange="markCustomerModified('${customer.id}')">
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = tableHtml;

    // Set selected tech and management company for each row
    bulkEditCustomers.forEach(customer => {
        const row = document.querySelector(`tr[data-customer-id="${customer.id}"]`);
        if (row) {
            // Set tech
            if (customer.assigned_tech_id) {
                const driverSelect = row.querySelector('[data-field="assigned_tech_id"]');
                if (driverSelect) {
                    driverSelect.value = customer.assigned_tech_id;
                }
            }
            // Set management company
            if (customer.management_company) {
                const mgmtSelect = row.querySelector('[data-field="management_company"]');
                if (mgmtSelect) {
                    mgmtSelect.value = customer.management_company;
                }
            }
        }
    });
}

/**
 * Update service day dropdown options based on service days per week
 * Called when user changes the Days/Week dropdown
 *
 * @param {HTMLElement} selectElement - The service_days_per_week select element that changed
 */
function updateServiceDayOptions(selectElement) {
    const row = selectElement.closest('tr');
    if (!row) return;

    const daysPerWeek = parseInt(selectElement.value);
    const serviceDaySelect = row.querySelector('[data-field="service_day"]');
    if (!serviceDaySelect) return;

    let options = '';
    let disabled = false;

    if (daysPerWeek === 2) {
        // For 2 days: Mo/Th or Tu/Fr
        options = `
            <option value="Mo/Th">Mo/Th</option>
            <option value="Tu/Fr">Tu/Fr</option>
        `;
    } else if (daysPerWeek === 3) {
        // For 3 days: Mo/We/Fr only (locked)
        options = `<option value="Mo/We/Fr">Mo/We/Fr</option>`;
        disabled = true;
    } else {
        // For 1 day: Normal dropdown
        options = `
            <option value="monday">Monday</option>
            <option value="tuesday">Tuesday</option>
            <option value="wednesday">Wednesday</option>
            <option value="thursday">Thursday</option>
            <option value="friday">Friday</option>
            <option value="saturday">Saturday</option>
            <option value="sunday">Sunday</option>
        `;
    }

    serviceDaySelect.innerHTML = options;
    serviceDaySelect.disabled = disabled;
}

/**
 * Mark a customer as modified
 * Tracks changes and updates UI to show modified state
 *
 * @param {string} customerId - UUID of the customer that was modified
 */
function markCustomerModified(customerId) {
    modifiedCustomers.add(customerId);

    // Highlight the row
    const row = document.querySelector(`tr[data-customer-id="${customerId}"]`);
    if (row) {
        row.classList.add('modified');
    }

    // Update count display
    const countElement = document.getElementById('modified-count');
    if (countElement) {
        countElement.textContent = `${modifiedCustomers.size} customer${modifiedCustomers.size !== 1 ? 's' : ''} modified`;
    }

    // Enable/disable save button based on whether there are changes
    const saveBtn = document.getElementById('save-bulk-changes-btn');
    if (saveBtn) {
        saveBtn.disabled = modifiedCustomers.size === 0;
    }
}

/**
 * Save all bulk edit changes
 * Iterates through modified customers and saves changes to API
 * Updates display_name field and all other customer properties
 */
async function saveBulkEditChanges() {
    if (modifiedCustomers.size === 0) {
        alert('No changes to save');
        return;
    }

    if (!confirm(`Save changes to ${modifiedCustomers.size} customer${modifiedCustomers.size !== 1 ? 's' : ''}?`)) {
        return;
    }

    const saveBtn = document.getElementById('save-bulk-changes-btn');
    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

    let successCount = 0;
    let errorCount = 0;

    try {
        for (const customerId of modifiedCustomers) {
            const row = document.querySelector(`tr[data-customer-id="${customerId}"]`);
            if (!row) continue;

            // Collect data from the row
            const serviceType = row.querySelector('[data-field="service_type"]').value;
            const displayName = row.querySelector('[data-field="display_name"]').value.trim();
            const firstName = row.querySelector('[data-field="first_name"]').value.trim();
            const lastName = row.querySelector('[data-field="last_name"]').value.trim();
            const street = row.querySelector('[data-field="street"]').value.trim();
            const city = row.querySelector('[data-field="city"]').value.trim();
            const state = row.querySelector('[data-field="state"]').value.trim();
            const zip = row.querySelector('[data-field="zip"]').value.trim();
            const address = combineAddressFields(street, city, state, zip);
            const email = row.querySelector('[data-field="email"]').value.trim();
            const phone = row.querySelector('[data-field="phone"]').value.trim();
            const altEmail = row.querySelector('[data-field="alt_email"]').value.trim();
            const altPhone = row.querySelector('[data-field="alt_phone"]').value.trim();
            const invoiceEmail = row.querySelector('[data-field="invoice_email"]').value.trim();
            const managementCompany = row.querySelector('[data-field="management_company"]').value.trim();

            const assignedTechValue = row.querySelector('[data-field="assigned_tech_id"]').value;
            const assignedTechId = assignedTechValue ? assignedTechValue : null;

            // Handle service_day based on days per week
            const serviceDaysPerWeek = parseInt(row.querySelector('[data-field="service_days_per_week"]').value);
            const serviceDayValue = row.querySelector('[data-field="service_day"]').value;
            let serviceDay;
            let serviceSchedule;

            if (serviceDaysPerWeek === 1) {
                // Single day - use the selected day
                serviceDay = serviceDayValue;
                serviceSchedule = null;
            } else if (serviceDaysPerWeek === 2) {
                // Two days - set schedule and first day
                serviceSchedule = serviceDayValue; // "Mo/Th" or "Tu/Fr"
                serviceDay = serviceDayValue === 'Mo/Th' ? 'monday' : 'tuesday';
            } else if (serviceDaysPerWeek === 3) {
                // Three days - always Mo/We/Fr
                serviceSchedule = 'Mo/We/Fr';
                serviceDay = 'monday';
            }

            const data = {
                service_type: serviceType,
                display_name: displayName || null,
                first_name: firstName || null,
                last_name: lastName || null,
                address: address,
                email: email || null,
                phone: phone || null,
                alt_email: altEmail || null,
                alt_phone: altPhone || null,
                invoice_email: invoiceEmail || null,
                management_company: managementCompany || null,
                assigned_tech_id: assignedTechId,
                service_day: serviceDay,
                service_days_per_week: serviceDaysPerWeek,
                service_schedule: serviceSchedule,
                visit_duration: parseInt(row.querySelector('[data-field="visit_duration"]').value),
                difficulty: parseInt(row.querySelector('[data-field="difficulty"]').value),
                locked: row.querySelector('[data-field="locked"]').checked
            };

            try {
                const response = await Auth.apiRequest(`${API_BASE}/api/customers/${customerId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    throw new Error('Failed to update');
                }

                successCount++;
                row.classList.remove('modified');
            } catch (error) {
                console.error(`Error updating customer ${customerId}:`, error);
                errorCount++;
            }
        }

        let message = `Successfully updated ${successCount} customer${successCount !== 1 ? 's' : ''}`;
        if (errorCount > 0) {
            message += `\nFailed to update ${errorCount} customer${errorCount !== 1 ? 's' : ''}`;
        }

        alert(message);

        // Clear modified set
        modifiedCustomers.clear();

        // Reload bulk edit table with fresh data (keep modal open)
        await showBulkEditCustomers();

        // Also reload customers in background
        loadCustomersManagement();
        loadCustomers(); // Reload map
    } catch (error) {
        console.error('Error during bulk save:', error);
        alert('An error occurred while saving changes. Please try again.');
    } finally {
        // Reset save button to disabled state (no changes remain)
        saveBtn.disabled = true;
        saveBtn.innerHTML = originalText;
    }
}
