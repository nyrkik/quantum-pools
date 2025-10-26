// RouteOptimizer - Modals Module
//
// Handles modal dialogs and context menus
// Dependencies: optimizeRoutes() function from app.js

/**
 * Opens a modal dialog by adding the 'active' class
 * @param {string} modalId - The ID of the modal to open
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

/**
 * Closes a modal dialog by removing the 'active' class
 * @param {string} modalId - The ID of the modal to close
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Initializes the route optimization modal
 * Sets up event listeners for opening, closing, and running optimization
 */
function initOptimizationModal() {
    const modal = document.getElementById('optimize-modal');
    const optimizeBtn = document.getElementById('optimize-btn');
    const runOptimizeBtn = document.getElementById('run-optimize-btn');
    const closeBtn = modal.querySelector('.modal-close');

    // Open modal when clicking "Optimize Routes" button
    optimizeBtn.addEventListener('click', function() {
        openModal('optimize-modal');
    });

    // Close modal when clicking X
    closeBtn.addEventListener('click', function() {
        closeModal('optimize-modal');
    });

    // Close modal when clicking outside
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal('optimize-modal');
        }
    });

    // Run optimization and close modal
    runOptimizeBtn.addEventListener('click', async function() {
        closeModal('optimize-modal');
        await optimizeRoutes();
    });
}

/**
 * Toggles a context menu's visibility
 * @param {Event} event - The click event
 * @param {string} menuId - The ID of the menu to toggle (without 'menu-' prefix)
 */
function toggleContextMenu(event, menuId) {
    event.stopPropagation();
    const menu = document.getElementById('menu-' + menuId);
    const isCurrentlyOpen = menu.classList.contains('show');

    // Close all menus first
    closeAllContextMenus();

    // Toggle the clicked menu
    if (!isCurrentlyOpen) {
        menu.classList.add('show');
    }
}

/**
 * Closes all open context menus
 */
function closeAllContextMenus() {
    document.querySelectorAll('.context-menu').forEach(menu => {
        menu.classList.remove('show');
    });
}
