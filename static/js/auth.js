/**
 * Authentication Utility
 * Handles authentication state, token management, and API requests
 */

const Auth = {
    /**
     * Get the stored authentication token
     */
    getToken() {
        return localStorage.getItem('auth_token');
    },

    /**
     * Get the stored user information
     */
    getUser() {
        const userStr = localStorage.getItem('user');
        return userStr ? JSON.parse(userStr) : null;
    },

    /**
     * Get the stored organization information
     */
    getOrganization() {
        const orgStr = localStorage.getItem('organization');
        return orgStr ? JSON.parse(orgStr) : null;
    },

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!this.getToken();
    },

    /**
     * Logout user and redirect to login page
     */
    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        localStorage.removeItem('organization');
        window.location.href = '/static/login.html';
    },

    /**
     * Redirect to login if not authenticated
     */
    requireAuth() {
        if (!this.isAuthenticated()) {
            window.location.href = '/static/login.html';
            return false;
        }
        return true;
    },

    /**
     * Make an authenticated API request
     * @param {string} url - API endpoint
     * @param {object} options - Fetch options
     * @returns {Promise} - Response promise
     */
    async apiRequest(url, options = {}) {
        const token = this.getToken();

        // Set up headers
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        // Add authorization header if token exists
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        // Make request
        const response = await fetch(url, {
            ...options,
            headers
        });

        // Handle 401 Unauthorized - redirect to login
        if (response.status === 401) {
            this.logout();
            throw new Error('Authentication required');
        }

        return response;
    },

    /**
     * Convenience method for GET requests
     */
    async get(url) {
        const response = await this.apiRequest(url, {
            method: 'GET'
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }

        return response.json();
    },

    /**
     * Convenience method for POST requests
     */
    async post(url, data) {
        const response = await this.apiRequest(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || response.statusText);
        }

        return response.json();
    },

    /**
     * Convenience method for PUT requests
     */
    async put(url, data) {
        const response = await this.apiRequest(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || response.statusText);
        }

        return response.json();
    },

    /**
     * Convenience method for PATCH requests
     */
    async patch(url, data) {
        const response = await this.apiRequest(url, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || response.statusText);
        }

        return response.json();
    },

    /**
     * Convenience method for DELETE requests
     */
    async delete(url) {
        const response = await this.apiRequest(url, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || response.statusText);
        }

        // DELETE may return 204 No Content
        if (response.status === 204) {
            return null;
        }

        return response.json();
    }
};

// Auto-export for modules if available
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Auth;
}
