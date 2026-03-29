/**
 * Permission Manager - Manages API endpoint permissions and UI element rendering
 * 
 * This module provides a centralized way to:
 * 1. Load API endpoint<->permission mappings on page load
 * 2. Check if the current user has permission for specific API calls
 * 3. Conditionally render DOM elements based on permissions
 * 4. Provide an extensible framework for all pages
 * 
 * Usage:
 *   // Initialize on page load
 *   await PermissionManager.init(boardId); // boardId optional
 *   
 *   // Check if user has permission for an endpoint
 *   if (PermissionManager.canCallEndpoint('POST', '/api/boards/:id/columns')) {
 *     // Show "Add Column" button
 *   }
 *   
 *   // Conditionally render element based on endpoint permission
 *   PermissionManager.renderIfAllowed(button, 'POST', '/api/cards/:id');
 *   
 *   // Check specific permission
 *   if (PermissionManager.hasPermission('card.create')) {
 *     // User has card create permission
 *   }
 */

class PermissionManagerClass {
  constructor() {
    this.endpointPermissions = new Map(); // Map of "METHOD /path" -> endpoint rule object
    this.userPermissions = new Set(); // Set of user's permissions
    this.userContext = {}; // Additional server-provided context for composite rules
    this.isInitialized = false;
    this.boardId = null;
  }

  /**
   * Initialize the permission manager by loading permissions from the API
   * Should be called on page load before rendering any permission-based elements
   * 
   * @param {number|null} boardId - Optional board ID for board-specific permissions
   * @returns {Promise<boolean>} True if initialization succeeded
   */
  async init(boardId = null) {
    try {
      this.boardId = boardId;
      
      // Build query string
      let url = '/api/permissions/mapping';
      if (boardId) {
        url += `?board_id=${boardId}`;
      }
      
      const response = await fetch(url, {
        method: 'GET',
        credentials: 'include'
      });
      
      if (!response.ok) {
        console.error('Failed to load permissions:', response.status, response.statusText);
        return false;
      }
      
      const data = await response.json();
      
      if (!data.success) {
        console.error('Failed to load permissions:', data.message);
        return false;
      }
      
      // Store endpoint permissions mapping
      this.endpointPermissions.clear();
      Object.entries(data.endpoint_permissions).forEach(([endpoint, info]) => {
        this.endpointPermissions.set(endpoint, info);
      });
      
      // Store user permissions
      this.userPermissions.clear();
      (data.user_permissions || []).forEach(perm => {
        this.userPermissions.add(perm);
      });

      // Store optional context fields used by composite permission checks
      this.userContext = data.user_context || {};
      
      this.isInitialized = true;
      
      console.log(`PermissionManager initialized with ${this.endpointPermissions.size} endpoints and ${this.userPermissions.size} user permissions`);
      
      return true;
    } catch (error) {
      console.error('Error initializing PermissionManager:', error);
      return false;
    }
  }

  /**
   * Reload permissions (e.g., after board change or role assignment change)
   * 
   * @param {number|null} boardId - Optional board ID for board-specific permissions
   * @returns {Promise<boolean>} True if reload succeeded
   */
  async reload(boardId = null) {
    console.log('Reloading permissions...');
    return await this.init(boardId);
  }

  /**
   * Check if the user has a specific permission
   * 
   * @param {string} permission - Permission to check (e.g., 'card.create')
   * @returns {boolean} True if user has the permission
   */
  hasPermission(permission) {
    if (!this.isInitialized) {
      console.warn('PermissionManager not initialized. Call init() first.');
      return false;
    }
    
    // If permission is null or undefined, treat as no permission required (public)
    if (!permission) {
      return true;
    }
    
    return this.userPermissions.has(permission);
  }

  /**
   * Check whether user has any permission from a list.
   *
   * @param {Array<string>} permissions - Permission list
   * @returns {boolean} True if user has at least one permission
   */
  hasAnyPermission(permissions = []) {
    if (!Array.isArray(permissions) || permissions.length === 0) {
      return false;
    }

    return permissions.some(permission => this.hasPermission(permission));
  }

  /**
   * Evaluate an endpoint rule object from /api/permissions/mapping.
   *
   * Supported rule shapes:
   * - { mode: 'public' }
   * - { mode: 'authenticated' }
   * - { permission: 'card.update' }
   * - { mode: 'composite', any_permissions: [...], allow_board_assignment: true }
   *
   * @param {object} endpointInfo - Endpoint rule object
   * @returns {boolean} True if user can call endpoint
   */
  evaluateEndpointRule(endpointInfo) {
    if (!endpointInfo || typeof endpointInfo !== 'object') {
      return false;
    }

    const mode = endpointInfo.mode || null;

    if (mode === 'public') {
      return true;
    }

    if (mode === 'authenticated') {
      // PermissionManager only initializes for authenticated users.
      return true;
    }

    if (mode === 'composite') {
      const anyPermissions = Array.isArray(endpointInfo.any_permissions)
        ? endpointInfo.any_permissions
        : [];
      const allPermissions = Array.isArray(endpointInfo.all_permissions)
        ? endpointInfo.all_permissions
        : [];

      if (anyPermissions.length > 0 && this.hasAnyPermission(anyPermissions)) {
        return true;
      }

      if (allPermissions.length > 0 && allPermissions.every(permission => this.hasPermission(permission))) {
        return true;
      }

      if (endpointInfo.permission && this.hasPermission(endpointInfo.permission)) {
        return true;
      }

      if (endpointInfo.allow_board_assignment && this.userContext.has_board_assignment === true) {
        return true;
      }

      if (endpointInfo.allow_board_edit_assignment && this.userContext.has_board_edit_assignment === true) {
        return true;
      }

      return false;
    }

    if (Array.isArray(endpointInfo.any_permissions) && endpointInfo.any_permissions.length > 0) {
      return this.hasAnyPermission(endpointInfo.any_permissions);
    }

    // Backward-compatible default: single permission field (or null for public).
    return this.hasPermission(endpointInfo.permission);
  }

  /**
   * Check if the user can call a specific API endpoint
   * 
   * @param {string} method - HTTP method (GET, POST, PATCH, DELETE, etc.)
   * @param {string} endpoint - API endpoint path (can include :id placeholders)
   * @returns {boolean} True if user has permission to call this endpoint
   */
  canCallEndpoint(method, endpoint) {
    if (!this.isInitialized) {
      console.warn('PermissionManager not initialized. Call init() first.');
      return false;
    }
    
    // Normalize method to uppercase
    method = method.toUpperCase();
    
    // Normalize endpoint - remove leading slash if present in input
    const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    
    // Build lookup key
    const lookupKey = `${method} ${normalizedEndpoint}`;
    
    // Get permission requirement for this endpoint
    const endpointInfo = this.endpointPermissions.get(lookupKey);
    
    if (!endpointInfo) {
      console.warn(`No permission mapping found for: ${lookupKey}`);
      return false;
    }

    return this.evaluateEndpointRule(endpointInfo);
  }

  /**
   * Conditionally render a DOM element based on endpoint permission
   * If user doesn't have permission, element is removed from DOM or hidden
   * 
   * @param {HTMLElement} element - DOM element to conditionally render
   * @param {string} method - HTTP method (GET, POST, PATCH, DELETE, etc.)
   * @param {string} endpoint - API endpoint path
   * @param {string} mode - 'remove' (default) or 'hide' - how to handle no permission
   * @returns {boolean} True if element should be/is rendered
   */
  renderIfAllowed(element, method, endpoint, mode = 'remove') {
    if (!element) {
      console.warn('renderIfAllowed: element is null or undefined');
      return false;
    }
    
    const hasPermission = this.canCallEndpoint(method, endpoint);
    
    if (!hasPermission) {
      if (mode === 'hide') {
        element.style.display = 'none';
      } else {
        // Remove from DOM
        element.remove();
      }
      return false;
    }
    
    return true;
  }

  /**
   * Conditionally render a DOM element based on specific permission
   * 
   * @param {HTMLElement} element - DOM element to conditionally render
   * @param {string} permission - Permission to check (e.g., 'card.create')
   * @param {string} mode - 'remove' (default) or 'hide' - how to handle no permission
   * @returns {boolean} True if element should be/is rendered
   */
  renderIfHasPermission(element, permission, mode = 'remove') {
    if (!element) {
      console.warn('renderIfHasPermission: element is null or undefined');
      return false;
    }
    
    const hasPermission = this.hasPermission(permission);
    
    if (!hasPermission) {
      if (mode === 'hide') {
        element.style.display = 'none';
      } else {
        // Remove from DOM
        element.remove();
      }
      return false;
    }
    
    return true;
  }

  /**
   * Get information about an endpoint (permission required, description)
   * 
   * @param {string} method - HTTP method
   * @param {string} endpoint - API endpoint path
   * @returns {object|null} Endpoint info or null if not found
   */
  getEndpointInfo(method, endpoint) {
    method = method.toUpperCase();
    const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const lookupKey = `${method} ${normalizedEndpoint}`;
    
    return this.endpointPermissions.get(lookupKey) || null;
  }

  /**
   * Get all user permissions
   * 
   * @returns {Array<string>} Array of permission strings
   */
  getUserPermissions() {
    return Array.from(this.userPermissions);
  }

  /**
   * Check if manager is initialized
   * 
   * @returns {boolean} True if initialized
   */
  get initialized() {
    return this.isInitialized;
  }

  /**
   * Get current board ID
   * 
   * @returns {number|null} Board ID or null
   */
  getCurrentBoardId() {
    return this.boardId;
  }

  /**
   * Utility: Apply permission checks to multiple elements at once
   * Each element should have data attributes:
   *   - data-permission-method: HTTP method
   *   - data-permission-endpoint: API endpoint
   *   - data-permission-mode: 'remove' or 'hide' (optional, defaults to 'remove')
   * 
   * Example:
   *   <button data-permission-method="POST" 
   *           data-permission-endpoint="/api/boards/:id/columns"
   *           data-permission-mode="hide">Add Column</button>
   * 
   * @param {string} selector - CSS selector to find elements
   * @param {HTMLElement} container - Container to search within (defaults to document)
   */
  applyToElements(selector = '[data-permission-method]', container = document) {
    const elements = container.querySelectorAll(selector);
    
    elements.forEach(element => {
      const method = element.getAttribute('data-permission-method');
      const endpoint = element.getAttribute('data-permission-endpoint');
      const mode = element.getAttribute('data-permission-mode') || 'remove';
      
      if (method && endpoint) {
        this.renderIfAllowed(element, method, endpoint, mode);
      }
    });
  }

  /**
   * Utility: Create a wrapper function for event handlers that only executes
   * if the user has permission for the endpoint
   * 
   * @param {Function} handler - Event handler function
   * @param {string} method - HTTP method
   * @param {string} endpoint - API endpoint
   * @returns {Function} Wrapped handler that checks permissions first
   */
  wrapHandler(handler, method, endpoint) {
    return (...args) => {
      if (!this.canCallEndpoint(method, endpoint)) {
        console.warn(`Permission denied for ${method} ${endpoint}`);
        showNotification('You do not have permission to perform this action', 'error');
        return;
      }
      
      return handler(...args);
    };
  }
}

// Export singleton instance
const PermissionManager = new PermissionManagerClass();

// Make available globally
if (typeof window !== 'undefined') {
  window.PermissionManager = PermissionManager;
}
