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

/**
 * Shows a loading overlay with a message
 * @param {string} message - Loading message to display
 */
function showLoadingOverlay(message = 'Loading...') {
    let overlay = document.getElementById('loading-overlay');

    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;

        const content = document.createElement('div');
        content.style.cssText = `
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            text-align: center;
        `;

        const spinner = document.createElement('div');
        spinner.style.cssText = `
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        `;

        const messageEl = document.createElement('div');
        messageEl.id = 'loading-message';
        messageEl.textContent = message;
        messageEl.style.cssText = `
            font-size: 1.1rem;
            color: #333;
        `;

        content.appendChild(spinner);
        content.appendChild(messageEl);
        overlay.appendChild(content);

        // Add spinner animation style if not present
        if (!document.getElementById('spinner-style')) {
            const style = document.createElement('style');
            style.id = 'spinner-style';
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(overlay);
    } else {
        const messageEl = document.getElementById('loading-message');
        if (messageEl) {
            messageEl.textContent = message;
        }
        overlay.style.display = 'flex';
    }
}

/**
 * Hides the loading overlay
 */
function hideLoadingOverlay() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}
