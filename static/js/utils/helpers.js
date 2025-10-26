// RouteOptimizer Utilities - Helper Functions
//
// Pure utility functions with no dependencies
// Safe to load first before any other modules

/**
 * Combines address components into a comma-separated string
 * @param {string} street - Street address
 * @param {string} city - City name
 * @param {string} state - State abbreviation
 * @param {string} zip - ZIP code
 * @returns {string} Formatted address string
 */
function combineAddressFields(street, city, state, zip) {
    const parts = [street, city, state, zip].filter(p => p && p.trim());
    return parts.join(', ');
}

/**
 * Parses a full address string into components
 * @param {string} fullAddress - Complete address in format "street, city, state zip"
 * @returns {Object} Object with street, city, state, zip properties
 */
function parseAddress(fullAddress) {
    if (!fullAddress) return { street: '', city: '', state: '', zip: '' };

    const parts = fullAddress.split(',').map(p => p.trim());

    if (parts.length >= 3) {
        const lastPart = parts[parts.length - 1];
        const zipMatch = lastPart.match(/\b(\d{5}(-\d{4})?)\b/);
        const stateMatch = lastPart.match(/\b([A-Z]{2})\b/);

        return {
            street: parts[0] || '',
            city: parts[1] || '',
            state: stateMatch ? stateMatch[1] : '',
            zip: zipMatch ? zipMatch[1] : ''
        };
    }

    return { street: fullAddress, city: '', state: '', zip: '' };
}

/**
 * Escapes HTML special characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} HTML-safe text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
