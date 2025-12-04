/**
 * Dashboard Module
 * Loads summary statistics for quick navigation
 */

/**
 * Initialize dashboard and load stats
 */
async function initDashboard() {
    await loadDashboardStats();
}

/**
 * Load dashboard statistics
 */
async function loadDashboardStats() {
    try {
        const token = Auth.getToken();
        if (!token) return;

        // Load visits count (today's visits)
        const today = new Date().toISOString().split('T')[0];
        const visitsResp = await fetch(`/api/visits?start_date=${today}&end_date=${today}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (visitsResp.ok) {
            const visitsData = await visitsResp.json();
            document.getElementById('dashboard-visits-count').textContent = visitsData.total || 0;
        }

        // Load alerts count (pending issues)
        const alertsResp = await fetch('/api/issues?status=pending', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (alertsResp.ok) {
            const alertsData = await alertsResp.json();
            document.getElementById('dashboard-alerts-count').textContent = alertsData.total || 0;
        }

        // Load routes count - just show 0 for now
        // TODO: Need proper endpoint to get all tech routes across all days
        document.getElementById('dashboard-routes-count').textContent = 0;

        // Load customers count
        const customersResp = await fetch('/api/customers', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (customersResp.ok) {
            const customersData = await customersResp.json();
            document.getElementById('dashboard-clients-count').textContent = customersData.total || 0;
        }

    } catch (error) {
        console.error('Error loading dashboard stats:', error);
    }
}

// Export
window.initDashboard = initDashboard;
