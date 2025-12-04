// QuantumPools - Navigation Module
//
// Handles module switching, sidebar navigation, and hash-based routing
// Dependencies: map global, loadCustomersManagement(), loadTechs() from app.js

/**
 * Initializes module navigation system
 * Sets up click handlers for nav items, mobile menu, and hash navigation
 */
function initModuleNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const mobileToggle = document.getElementById('mobile-menu-toggle');
    const sidebar = document.getElementById('app-sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const appContent = document.getElementById('app-content');

    // Load sidebar state from localStorage (default to expanded on desktop)
    const sidebarPref = localStorage.getItem('sidebarExpanded');
    const sidebarExpanded = sidebarPref === null ? true : sidebarPref === 'true';
    if (sidebarExpanded) {
        sidebar.classList.add('expanded');
        appContent.classList.add('sidebar-expanded');
    }

    // Handle desktop sidebar toggle
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            sidebar.classList.toggle('expanded');
            appContent.classList.toggle('sidebar-expanded');

            // Save state to localStorage
            const isExpanded = sidebar.classList.contains('expanded');
            localStorage.setItem('sidebarExpanded', isExpanded);
        });
    }

    // Make logo navigate to dashboard
    const logo = document.querySelector('.logo');
    if (logo) {
        logo.addEventListener('click', function() {
            window.location.hash = 'dashboard';
            switchModule('dashboard');

            // Update nav active states
            const navItems = document.querySelectorAll('.nav-item');
            navItems.forEach(item => {
                if (item.dataset.module === 'dashboard') {
                    navItems.forEach(nav => nav.classList.remove('active'));
                    item.classList.add('active');
                }
            });
        });
    }

    // Handle module navigation
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const targetModule = this.dataset.module;
            switchModule(targetModule);

            // Update active state
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');

            // Close mobile menu if open
            if (window.innerWidth <= 768) {
                sidebar.classList.remove('mobile-open');
            }
        });
    });

    // Handle mobile sidebar toggle
    if (mobileToggle) {
        mobileToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            sidebar.classList.toggle('mobile-open');
        });
    }

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(e) {
        if (window.innerWidth <= 768 &&
            sidebar.classList.contains('mobile-open') &&
            !sidebar.contains(e.target) &&
            !mobileToggle.contains(e.target)) {
            sidebar.classList.remove('mobile-open');
        }
    });

    // Handle mobile bottom navigation
    const mobileNavItems = document.querySelectorAll('.mobile-nav-item');
    mobileNavItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const targetModule = this.dataset.module;
            switchModule(targetModule);

            // Update active state for mobile nav
            mobileNavItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');

            // Also update sidebar nav
            navItems.forEach(nav => nav.classList.remove('active'));
            const sidebarItem = document.querySelector(`.nav-item[data-module="${targetModule}"]`);
            if (sidebarItem) {
                sidebarItem.classList.add('active');
            }
        });
    });

    // Handle hash navigation (URL #routes, etc.)
    window.addEventListener('hashchange', handleHashChange);

    // Always start at dashboard on page load
    window.location.hash = 'dashboard';
}

/**
 * Switches to a different module view
 * @param {string} moduleName - Name of the module to display (e.g., 'dashboard', 'routes', 'clients')
 */
function switchModule(moduleName) {
    // Hide all modules
    const modules = document.querySelectorAll('.module-content');
    modules.forEach(module => {
        module.classList.remove('active');
        module.style.display = 'none';
    });

    // Show target module
    const targetModule = document.getElementById('module-' + moduleName);
    if (targetModule) {
        targetModule.classList.add('active');
        targetModule.style.display = 'block';

        // If switching to routes, reinitialize map and load customers
        if (moduleName === 'routes' && map) {
            setTimeout(() => {
                map.invalidateSize();
                loadCustomers();
            }, 100);
        }

        // If switching to clients, reload customer list
        if (moduleName === 'clients') {
            loadCustomersManagement();
        }

        // Load module-specific data
        if (moduleName === 'team' && !document.getElementById('techs-list').dataset.loaded) {
            loadTechs();
            document.getElementById('techs-list').dataset.loaded = 'true';
        }

        if (moduleName === 'clients' && !document.getElementById('customers-list').dataset.loaded) {
            loadCustomersManagement();
            document.getElementById('customers-list').dataset.loaded = 'true';
        }

        // Initialize issues module
        if (moduleName === 'issues' && !document.getElementById('issues-container').dataset.loaded) {
            initIssuesModule();
            document.getElementById('issues-container').dataset.loaded = 'true';
        }

        // Initialize services module
        if (moduleName === 'jobs' && !document.getElementById('services-container').dataset.loaded) {
            initServicesModule();
            document.getElementById('services-container').dataset.loaded = 'true';
        }

        // Initialize visits module
        if (moduleName === 'visits' && !document.getElementById('visits-container').dataset.loaded) {
            initVisitsModule();
            document.getElementById('visits-container').dataset.loaded = 'true';
        }

        // Initialize dashboard
        if (moduleName === 'dashboard') {
            initDashboard();
        }
    }
}

/**
 * Handles URL hash changes for navigation
 * Updates module view and nav active state based on hash
 */
function handleHashChange() {
    const hash = window.location.hash.substring(1); // Remove #
    if (hash) {
        switchModule(hash);

        // Update sidebar nav active state
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            if (item.dataset.module === hash) {
                navItems.forEach(nav => nav.classList.remove('active'));
                item.classList.add('active');
            }
        });

        // Update mobile bottom nav active state
        const mobileNavItems = document.querySelectorAll('.mobile-nav-item');
        mobileNavItems.forEach(item => {
            if (item.dataset.module === hash) {
                mobileNavItems.forEach(nav => nav.classList.remove('active'));
                item.classList.add('active');
            }
        });
    }
}

// ========================================
// Tab Management
// ========================================

/**
 * Initializes tab switching within modules
 * Handles both Routes module tabs (.nav-tab) and Clients module tabs (.tab-btn)
 */
function initTabs() {
    // Routes module tabs (.nav-tab)
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            const tabName = this.dataset.tab;

            // Update active tab
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Show corresponding content
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });

    // Clients module tabs (.tab-btn)
    document.querySelectorAll('.clients-tabs .tab-btn').forEach(tab => {
        tab.addEventListener('click', function() {
            const tabName = this.dataset.tab;

            // Update active tab
            document.querySelectorAll('.clients-tabs .tab-btn').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Show corresponding content
            document.querySelectorAll('.clients-tab-content .tab-pane').forEach(pane => pane.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });
}
