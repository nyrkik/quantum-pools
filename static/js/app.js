// QuantumPools Frontend Application

/*
 * ✅ REFACTORING COMPLETE: Reduced from 3,516 lines to ~108 lines (96.9% reduction)
 *
 * This file now serves as the main entry point and global state container.
 * All feature code has been extracted to focused modules in /static/js/modules/
 *
 * See REFACTORING_PLAN.md for module details.
 */

// Initialize map
let map;
// routeLayers moved to /static/js/modules/routes.js
let customerMarkers = [];
let customerMarkersById = {}; // Map customer IDs to marker objects
let highlightedMarker = null; // Currently highlighted marker
const API_BASE = window.location.origin;
const HOME_BASE = { lat: 38.4088, lng: -121.3716 }; // Elk Grove, CA
// Tech constants moved to /static/js/modules/techs.js

// Current route result (for filtering when tech selection changes)
let currentRouteResult = null;
// Store route results per day
let routeResultsByDay = {};

// Drag and drop state
let draggedStop = null;
let draggedStopRoute = null;

// Selected day
let selectedDay = 'all';

// Google Places configuration
let googlePlacesLoaded = false;
let hasGoogleMapsKey = false;

// Navigation functions moved to /static/js/modules/navigation.js

// ===== MODAL FUNCTIONS =====
// Modal functions moved to /static/js/modules/modals.js

document.addEventListener('DOMContentLoaded', async function() {
    // Check authentication
    if (!Auth.isAuthenticated()) {
        window.location.href = '/static/login.html';
        return;
    }

    // Setup logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            Auth.logout();
        });
    }

    // Setup profile avatar and context menu
    const user = Auth.getUser();
    const profileAvatar = document.getElementById('profile-avatar');
    const profileContextMenu = document.getElementById('profile-context-menu');

    if (user && profileAvatar) {
        const initial = user.first_name ? user.first_name.charAt(0).toUpperCase() : 'U';
        profileAvatar.textContent = initial;
    }

    if (profileAvatar && profileContextMenu) {
        profileAvatar.addEventListener('click', (e) => {
            e.stopPropagation();
            profileContextMenu.classList.toggle('show');
        });
    }

    // Profile settings link - close menu on click
    const profileSettingsLink = document.getElementById('profile-settings-link');
    if (profileSettingsLink) {
        profileSettingsLink.addEventListener('click', () => {
            if (profileContextMenu) {
                profileContextMenu.classList.remove('show');
            }
        });
    }

    // Profile menu logout button
    const profileMenuLogout = document.getElementById('profile-menu-logout');
    if (profileMenuLogout) {
        profileMenuLogout.addEventListener('click', () => {
            Auth.logout();
        });
    }

    initModuleNavigation();
    initSettings();
    initializeMap();
    attachEventListeners();
    initOptimizationModal();
    initDaySelector();  // Must run before loadCustomers to set selectedDay
    initRoutesHeader();  // Initialize routes header
    await loadCustomers();  // Load customers first to count unassigned
    loadTechs();  // Then load techs with unassigned count
    await loadTechRoutesForDay(selectedDay);  // Load routes after customers are ready
    loadCustomersManagement();
    initTabs();
    loadGooglePlacesAPI();
    initClientSearch();
    initClientFilter();
    initQuickFilter();
    initBulkEditModal();

    // Close context menus when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.context-menu-btn') &&
            !e.target.closest('.context-menu') &&
            !e.target.closest('.profile-avatar')) {
            closeAllContextMenus();
        }
    });
});

/**
 * Initialize settings page
 */
function initSettings() {
    // Load user data into settings form
    const user = Auth.getUser();
    const org = Auth.getOrganization();

    if (user) {
        document.getElementById('settings-first-name').value = user.first_name || '';
        document.getElementById('settings-last-name').value = user.last_name || '';
        document.getElementById('settings-email').value = user.email || '';
    }

    if (org) {
        document.getElementById('settings-org-name').value = org.name || '';
    }

    // Handle edit profile button
    const editProfileBtn = document.getElementById('edit-profile-btn');
    const firstNameInput = document.getElementById('settings-first-name');
    const lastNameInput = document.getElementById('settings-last-name');
    const emailInput = document.getElementById('settings-email');
    const saveProfileBtn = document.getElementById('save-profile-btn');

    if (editProfileBtn) {
        editProfileBtn.addEventListener('click', () => {
            const isEditing = !firstNameInput.hasAttribute('readonly');

            if (isEditing) {
                // Cancel editing
                firstNameInput.setAttribute('readonly', '');
                lastNameInput.setAttribute('readonly', '');
                emailInput.setAttribute('readonly', '');
                saveProfileBtn.style.display = 'none';
                editProfileBtn.innerHTML = '<i class="fas fa-pen"></i> Edit';

                // Reset values
                if (user) {
                    firstNameInput.value = user.first_name || '';
                    lastNameInput.value = user.last_name || '';
                    emailInput.value = user.email || '';
                }
            } else {
                // Enable editing
                firstNameInput.removeAttribute('readonly');
                lastNameInput.removeAttribute('readonly');
                emailInput.removeAttribute('readonly');
                saveProfileBtn.style.display = 'inline-block';
                editProfileBtn.innerHTML = '<i class="fas fa-times"></i> Cancel';
                firstNameInput.focus();
            }
        });
    }

    // Handle profile save (redefine saveProfileBtn to avoid conflict)
    if (saveProfileBtn) {
        saveProfileBtn.addEventListener('click', async () => {
            const firstName = firstNameInput.value.trim();
            const lastName = lastNameInput.value.trim();
            const email = emailInput.value.trim();
            const errorDiv = document.getElementById('profile-error');
            const successDiv = document.getElementById('profile-success');

            errorDiv.style.display = 'none';
            successDiv.style.display = 'none';

            // Validation
            if (!firstName || !lastName || !email) {
                errorDiv.textContent = 'All fields are required';
                errorDiv.style.display = 'block';
                return;
            }

            if (!email.includes('@')) {
                errorDiv.textContent = 'Invalid email address';
                errorDiv.style.display = 'block';
                return;
            }

            saveProfileBtn.disabled = true;
            saveProfileBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

            try {
                const response = await Auth.put('/api/v1/auth/profile', {
                    first_name: firstName,
                    last_name: lastName,
                    email: email
                });

                // Update local storage
                const updatedUser = { ...user, first_name: firstName, last_name: lastName, email: email };
                localStorage.setItem('user', JSON.stringify(updatedUser));

                // Update profile avatar initial
                const profileAvatar = document.getElementById('profile-avatar');
                if (profileAvatar) {
                    profileAvatar.textContent = firstName.charAt(0).toUpperCase();
                }

                successDiv.style.display = 'block';

                // Exit edit mode
                firstNameInput.setAttribute('readonly', '');
                lastNameInput.setAttribute('readonly', '');
                emailInput.setAttribute('readonly', '');
                saveProfileBtn.style.display = 'none';
                editProfileBtn.innerHTML = '<i class="fas fa-pen"></i> Edit';
            } catch (error) {
                errorDiv.textContent = error.message || 'Failed to update profile';
                errorDiv.style.display = 'block';
            } finally {
                saveProfileBtn.disabled = false;
                saveProfileBtn.innerHTML = '<i class="fas fa-save"></i> Save Changes';
            }
        });
    }

    // Handle password change
    const changePasswordBtn = document.getElementById('change-password-btn');
    if (changePasswordBtn) {
        changePasswordBtn.addEventListener('click', async () => {
            const currentPassword = document.getElementById('current-password').value;
            const newPassword = document.getElementById('new-password').value;
            const confirmPassword = document.getElementById('confirm-password').value;
            const errorDiv = document.getElementById('password-error');
            const successDiv = document.getElementById('password-success');

            errorDiv.style.display = 'none';
            successDiv.style.display = 'none';

            // Validation
            if (!currentPassword || !newPassword || !confirmPassword) {
                errorDiv.textContent = 'All fields are required';
                errorDiv.style.display = 'block';
                return;
            }

            if (newPassword.length < 8) {
                errorDiv.textContent = 'New password must be at least 8 characters';
                errorDiv.style.display = 'block';
                return;
            }

            if (newPassword !== confirmPassword) {
                errorDiv.textContent = 'New passwords do not match';
                errorDiv.style.display = 'block';
                return;
            }

            // Disable button
            changePasswordBtn.disabled = true;
            changePasswordBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Updating...';

            try {
                await Auth.post('/api/v1/auth/change-password', {
                    current_password: currentPassword,
                    new_password: newPassword
                });

                successDiv.style.display = 'block';
                document.getElementById('current-password').value = '';
                document.getElementById('new-password').value = '';
                document.getElementById('confirm-password').value = '';
            } catch (error) {
                errorDiv.textContent = error.message || 'Failed to change password';
                errorDiv.style.display = 'block';
            } finally {
                changePasswordBtn.disabled = false;
                changePasswordBtn.innerHTML = '<i class="fas fa-key"></i> Update Password';
            }
        });
    }
}

// ========================================
// All Feature Code Extracted to Modules
// ========================================
// - Navigation & tabs → /static/js/modules/navigation.js
// - Map & markers → /static/js/modules/map.js
// - Modals & context menus → /static/js/modules/modals.js
// - Techs management → /static/js/modules/techs.js
// - Routes optimization → /static/js/modules/routes.js
// - Customer management → /static/js/modules/customers.js
// - Bulk editing → /static/js/modules/bulk-edit.js
// - Helper utilities → /static/js/utils/helpers.js
