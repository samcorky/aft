// Header component functionality

/**
 * Close all pinned dropdown menus except the specified one.
 * This provides centralized coordination of menu states.
 * @param {HTMLElement|null} exceptMenu - Menu to keep open (null to close all)
 * @global
 */
function closeAllMenusExcept(exceptMenu = null) {
  const settingsMenu = document.getElementById('settings-dropdown-menu');
  const userMenu = document.getElementById('user-dropdown-menu');
  const notificationsPopup = document.getElementById('notifications-popup');
  const allMenus = [settingsMenu, userMenu, notificationsPopup].filter(Boolean);
  
  allMenus.forEach(menu => {
    if (menu !== exceptMenu) {
      const wasPinned = menu.classList.contains('pinned');
      
      if (wasPinned) {
        menu.classList.remove('pinned');
      }
      
      // Sync notifications component state if closing notifications
      // (regardless of whether it was pinned or just had state set)
      if (menu === notificationsPopup && window.notifications && window.notifications.isPopupOpen) {
        window.notifications.isPopupOpen = false;
      }
    }
  });
}

/**
 * Update hover state for all dropdown menus based on whether any are pinned.
 * This is shared between header dropdowns and notifications.
 * @global
 */
function updateMenuHoverState() {
  const settingsMenu = document.getElementById('settings-dropdown-menu');
  const userMenu = document.getElementById('user-dropdown-menu');
  const notificationsPopup = document.getElementById('notifications-popup');
  const allMenus = [settingsMenu, userMenu, notificationsPopup].filter(Boolean);
  
  // Check if any menu is pinned
  const anyPinned = allMenus.some(menu => menu.classList.contains('pinned'));
  
  // Add/remove no-hover class on all menus
  allMenus.forEach(menu => {
    if (anyPinned) {
      menu.classList.add('no-hover');
    } else {
      menu.classList.remove('no-hover');
    }
  });
}

class Header {
  constructor() {
    this.statusIcon = null;
    this.statusText = null;
    this.versionInfo = null;
    this.currentView = 'task'; // Default view
    this.dbConnected = false; // Track database connection status
    this.wsConnected = false; // Track WebSocket connection status
    this.wsConnectionStartTime = null; // Track when WebSocket connection attempt started (for timeout detection)
    this.wsCheckInterval = null; // WebSocket check interval
  }

  // Load the header HTML component
  async load() {
    const response = await fetch('/components/header.html');
    const html = await response.text();
    document.body.insertAdjacentHTML('afterbegin', html);
    
    // Get references to status elements after HTML is inserted
    this.statusIcon = document.getElementById('status-icon');
    this.statusText = document.getElementById('status-text');
    this.versionInfo = document.getElementById('version-info');
    
    // Initialize status as "Connected" by default (optimistic approach)
    // Will be updated by checks if there's an actual problem
    if (this.statusIcon && this.statusText) {
      this.statusIcon.className = 'status-icon success';
      this.statusText.textContent = 'Connected';
    }
    
    // Add click handler to db-status
    const dbStatus = document.querySelector('.db-status');
    if (dbStatus) {
      dbStatus.addEventListener('click', () => {
        window.location.href = '/system-info.html';
      });
    }
    
    // Initialize notifications if the class exists
    if (typeof Notifications !== 'undefined') {
      window.notifications = new Notifications();
    }
    
    // Initialize dropdown pin behavior for settings and user menus
    this.initializeDropdownPin();
    
    // Initialize views dropdown
    this.initializeViewsDropdown();
    
    // Load boards dropdown
    this.loadBoardsDropdown();
    
    // Fetch version info immediately (without checking status)
    this.loadVersionInfo();
    
    // Poll database status every 5 seconds
    this.statusCheckInterval = setInterval(() => {
      this.checkDatabaseStatus();
    }, 5000);
    
    // Initialize WebSocket monitoring
    this.monitorWebSocketConnection();
    
    // Store last WebSocket state to detect changes
    this.lastWsState = null;
  }

  /**
   * Monitor WebSocket connection status with periodic checks and event listeners.
   * 
   * Polls WebSocket status every 5 seconds to detect disconnections.
   * Also listens for connect/disconnect events to update immediately.
   * On initial page load, don't report connecting sockets as failed.
   */
  /**
   * Monitor WebSocket connection status with periodic checks and event listeners.
   * 
   * Sets up two mechanisms for status updates:
   * 1. Periodic polling every 5 seconds (fallback for all scenarios)
   * 2. Real-time event listeners via WebSocketManager.onSocketCreated callback
   *    (only works if wsManager exists before or shortly after this is called)
   * 
   * The callback pattern allows header.js to get immediate socket events without
   * waiting for the 5-second polling interval. The callback is set on wsManager.onSocketCreated
   * which the WebSocketManager checks and invokes when socket is created.
   */
  monitorWebSocketConnection() {
    // Check WebSocket status every 5 seconds
    this.wsCheckInterval = setInterval(() => {
      this.checkWebSocketStatusWithInitialDelay();
    }, 5000);
    
    // Attempt to attach event listener callback if wsManager already exists
    // (this works if board page has already initialized)
    this.attachWebSocketCallback();
    
    // Also set up a watcher to attach callback when wsManager becomes available
    // (this handles cases where header loads before board page initializes wsManager)
    this.watchForWebSocketManager();
  }

  /**
   * Attach socket event listeners via wsManager callback pattern.
   * Safe to call multiple times - only attaches if wsManager exists and callback not yet set.
   */
  attachWebSocketCallback() {
    if (window.boardManager && window.boardManager.wsManager) {
      const wsManager = window.boardManager.wsManager;
      // Only set callback if it hasn't been set already (avoid overwriting)
      if (!wsManager.onSocketCreated) {
        wsManager.onSocketCreated = (socket) => {
          socket.on('connect', () => {
            this.updateWebSocketStatus();
          });
          socket.on('disconnect', () => {
            this.updateWebSocketStatus();
          });
        };
      }
    }
  }

  /**
   * Watch for wsManager to become available and attach callback when it does.
   * Uses a polling approach since we can't rely on event listeners at this stage.
   */
  watchForWebSocketManager() {
    let attempts = 0;
    const maxAttempts = 50; // Watch for up to ~5 seconds (5000ms / 100ms per check)
    
    const watchInterval = setInterval(() => {
      attempts++;
      if (window.boardManager && window.boardManager.wsManager) {
        this.attachWebSocketCallback();
        clearInterval(watchInterval); // Found it, stop watching
      } else if (attempts >= maxAttempts) {
        clearInterval(watchInterval); // Give up after max attempts
      }
    }, 100); // Check every 100ms
  }

  /**
   * Check WebSocket status with awareness of initial page load.
   * 
   * On initial page load, don't mark a "connecting" socket as an error.
   * Only mark as error if socket exists and is clearly disconnected (not connecting).
   */
  checkWebSocketStatusWithInitialDelay() {
    const { hasSocket, wsHealthy, wsConnecting } = this._getWebSocketConnectionState();
    
    // Track state changes by comparing individual properties
    const newState = { hasSocket, wsHealthy, wsConnecting };
    
    // Only update if state actually changed (not on every 5s interval)
    const stateChanged = !this.lastWsState || 
                        this.lastWsState.hasSocket !== newState.hasSocket ||
                        this.lastWsState.wsHealthy !== newState.wsHealthy ||
                        this.lastWsState.wsConnecting !== newState.wsConnecting;
    
    if (stateChanged) {
      this.lastWsState = newState;
      this.updateWebSocketStatus();
    }
  }

  /**
   * Update WebSocket connection status by checking available sockets.
   * 
   * Checks for board manager socket or theme builder socket.
   * Only shows error if socket exists and is not connecting and not healthy.
   */
  _getWebSocketConnectionState() {
    // Only check WebSocket if socket.io is actually loaded on this page
    if (typeof io === 'undefined') {
      // Socket.io not loaded on this page - that's OK
      return { hasSocket: false, wsHealthy: false, wsConnecting: false, ioLoaded: false };
    }
    
    // Socket.IO is loaded on this page, so check for actual sockets
    // Check for board manager socket OR theme builder socket
    const boardSocket = (window.boardManager && 
                         window.boardManager.wsManager && 
                         window.boardManager.wsManager.socket);
    const boardSocketConnected = boardSocket && boardSocket.connected;
    
    const themeSocket = window.themeBuilderSocket;
    const themeSocketConnected = themeSocket && themeSocket.connected;
    
    // Check if either socket is connecting
    // A socket is "connecting" if it exists but is not connected and not explicitly disconnected
    // Socket.IO's internal state handles reconnection automatically
    const boardSocketConnecting = boardSocket && !boardSocketConnected && boardSocket.io && boardSocket.io.engine && boardSocket.io.engine.readyState !== 'closed';
    const themeSocketConnecting = themeSocket && !themeSocketConnected && themeSocket.io && themeSocket.io.engine && themeSocket.io.engine.readyState !== 'closed';
    
    const hasSocket = !!boardSocket || !!themeSocket;
    const wsHealthy = boardSocketConnected || themeSocketConnected;
    const wsConnecting = boardSocketConnecting || themeSocketConnecting;
    
    return { hasSocket, wsHealthy, wsConnecting, ioLoaded: true };
  }

  updateWebSocketStatus() {
    const { hasSocket, wsHealthy, wsConnecting, ioLoaded } = this._getWebSocketConnectionState();
    
    this.wsConnected = wsHealthy;
    
    // If Socket.IO library failed to load on a page that needs it, show error
    if (ioLoaded && !hasSocket && !wsConnecting) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'WebSocket Disconnected';
      this.statusText.title = 'Real-time updates are unavailable. Board changes will not sync in real-time. Try force reloading (Ctrl+Shift+R).';
      this.dbConnected = false;
      return;
    }
    
    // Only show connection error if socket exists and is not connecting and is not healthy
    if (hasSocket && !wsHealthy && !wsConnecting) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'WebSocket Disconnected';
      this.statusText.title = 'Real-time updates are unavailable. Board changes will not sync in real-time. Try force reloading (Ctrl+Shift+R).';
      this.dbConnected = false; // Mark DB as disconnected when WS is down
    }
  }

  // Set the board name in the header
  setBoardName(boardName) {
    const navBoardName = document.getElementById('nav-board-name');
    if (navBoardName) {
      if (boardName) {
        navBoardName.textContent = boardName;
        document.title = `AFT - ${boardName}`;
      } else {
        navBoardName.textContent = '';
        document.title = 'AFT';
      }
    }
  }

  // Show or hide the views dropdown
  showViewsDropdown(show) {
    const viewsDropdown = document.getElementById('views-dropdown');
    if (viewsDropdown) {
      viewsDropdown.style.display = show ? 'block' : 'none';
    }
  }

  // Initialize dropdown pin behavior for settings and user menus
  initializeDropdownPin() {
    const dropdowns = [
      {
        trigger: document.querySelector('.settings-dropdown .icon-link'),
        menu: document.getElementById('settings-dropdown-menu')
      },
      {
        trigger: document.querySelector('.user-dropdown .icon-link'),
        menu: document.getElementById('user-dropdown-menu')
      }
    ];

    // Get notifications popup for coordinated hover prevention
    const notificationsPopup = document.getElementById('notifications-popup');
    const allMenus = [...dropdowns.map(d => d.menu), notificationsPopup].filter(Boolean);

    dropdowns.forEach(({ trigger, menu }) => {
      if (!trigger || !menu) return;

      // Toggle pinned state on click
      trigger.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        const wasPinned = menu.classList.contains('pinned');
        
        if (wasPinned) {
          // Close this menu
          menu.classList.remove('pinned');
        } else {
          // Close other menus and open this one
          closeAllMenusExcept(menu);
          menu.classList.add('pinned');
        }
        
        // Update hover state for all menus
        updateMenuHoverState();
      });
    });

    // Close pinned menus when clicking outside
    document.addEventListener('click', (e) => {
      const clickedInsideAnyMenu = dropdowns.some(({ trigger, menu }) => {
        return trigger && menu && (trigger.contains(e.target) || menu.contains(e.target));
      });
      
      const clickedInNotifications = notificationsPopup && 
        (notificationsPopup.contains(e.target) || 
         document.getElementById('notifications-icon-link')?.contains(e.target));

      if (!clickedInsideAnyMenu && !clickedInNotifications) {
        closeAllMenusExcept(null); // Close all menus
        updateMenuHoverState();
      }
    });

    // Close pinned menus on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const hadPinned = allMenus.some(menu => menu && menu.classList.contains('pinned'));
        
        if (hadPinned) {
          closeAllMenusExcept(null); // Close all menus
          updateMenuHoverState();
        }
      }
    });
  }

  // Initialize views dropdown functionality
  initializeViewsDropdown() {
    const dropdownBtn = document.getElementById('views-dropdown-btn');
    const dropdownMenu = document.getElementById('views-dropdown-menu');
    const dropdownItems = document.querySelectorAll('.views-dropdown-item');

    if (!dropdownBtn || !dropdownMenu) return;

    // Toggle dropdown on button click
    dropdownBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = dropdownMenu.classList.contains('show');
      dropdownMenu.classList.toggle('show', !isOpen);
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (!dropdownBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
        dropdownMenu.classList.remove('show');
      }
    });

    // Handle view selection
    dropdownItems.forEach(item => {
      item.addEventListener('click', (e) => {
        // Don't allow clicking the active view
        if (item.classList.contains('active')) {
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        const view = e.currentTarget.dataset.view;
        this.setView(view);
        dropdownMenu.classList.remove('show');
      });
    });
  }

  // Set the current view
  setView(view) {
    this.currentView = view;
    
    // Update dropdown label
    const label = document.getElementById('views-dropdown-label');
    if (label) {
      const viewNames = {
        'task': 'Task View',
        'scheduled': 'Scheduled View',
        'archived': 'Archived View'
      };
      label.textContent = viewNames[view] || 'Task View';
    }

    // Highlight active item
    document.querySelectorAll('.views-dropdown-item').forEach(item => {
      item.classList.toggle('active', item.dataset.view === view);
    });

    // Dispatch custom event for board.js to handle
    window.dispatchEvent(new CustomEvent('viewChanged', { detail: { view } }));
  }

  // Get the current view
  getView() {
    return this.currentView;
  }

  // Escape HTML to prevent XSS
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Update the status icon and text in the header.
   * 
   * Args:
   *   status: Status type ('success' or 'error')
   *   message: Status message to display
   *   count: Optional count of boards (shown in tooltip)
   *   housekeepingHealthy: Whether housekeeping scheduler is healthy
   */
  updateStatus(status, message, count = null, housekeepingHealthy = true) {
    if (!this.statusIcon || !this.statusText) return;

    // Check WebSocket health
    const { hasSocket, wsHealthy, wsConnecting } = this._getWebSocketConnectionState();
    
    // Only show error if we have a socket that's not connecting
    // If we don't have a socket yet, it's probably still initializing - don't error
    if (hasSocket && !wsHealthy && !wsConnecting) {
      // WebSocket exists but is down and not connecting = connection error
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Connection Error';
      this.statusText.title = 'WebSocket connection lost. Real-time updates may not work. Try force reloading the page (Ctrl+Shift+R).';
      this.dbConnected = false;
      return;
    }
    
    // WebSocket is connected (or not required on this page), now evaluate DB status
    // If housekeeping is unhealthy, override to show error
    if (status === 'success' && !housekeepingHealthy) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Housekeeping Error';
      this.statusText.title = 'Housekeeping scheduler is not running or unhealthy';
      this.dbConnected = false;
      return;
    }

    this.statusIcon.className = `status-icon ${status}`;
    this.dbConnected = (status === 'success');
    
    if (status === 'success') {
      this.statusText.textContent = 'Connected';
      this.statusText.title = ''; // Clear any previous error message
    } else if (status === 'error') {
      this.statusText.textContent = 'DB Error';
      this.statusText.title = message; // Show full error on hover
    } else {
      this.statusText.textContent = message;
      this.statusText.title = '';
    }
  }

  /**
   * Check system status with proper precedence:
   * 1. Server connectivity (can reach API?)
   * 2. WebSocket availability (on pages that need it)
   * 3. Database health (if server and WebSocket OK)
   * 
   * Updates header status based on first failure encountered.
   */
  async checkDatabaseStatus() {
    // First: Check if server is reachable
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    let serverReachable = false;
    let testData = null;
    
    try {
      const response = await fetch('/api/test', {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      serverReachable = response.ok;
      testData = await response.json();
      
      // If server responded but with an error status, treat as unreachable
      if (!serverReachable) {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'Server Disconnected';
        this.statusText.title = 'Server responded with an error. Check server status.';
        this.dbConnected = false;
        return;
      }
    } catch (error) {
      clearTimeout(timeoutId);
      // Server is not reachable - highest priority error
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Server Disconnected';
      this.statusText.title = 'Unable to connect to server. Check your connection or try refreshing the page.';
      this.dbConnected = false;
      return;
    }

    // Second: Check WebSocket status on pages that need it (board, theme-builder)
    // Detect if we're on a page that should have Socket.IO loaded
    const isOnBoardPage = (window.boardManager && window.boardManager.wsManager) || 
                          (window.themeBuilderSocket !== undefined);
    
    if (isOnBoardPage) {
      const { hasSocket, wsHealthy, wsConnecting, ioLoaded } = this._getWebSocketConnectionState();
      
      // If we're on a board page but Socket.IO isn't loaded, that's an error
      if (!ioLoaded) {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'WebSocket Disconnected';
        this.statusText.title = 'Real-time updates are unavailable. Socket.IO library failed to load. Try force reloading (Ctrl+Shift+R).';
        this.dbConnected = false;
        return;
      }
      
      // If Socket.IO is loaded but WebSocket isn't working, that's a priority issue
      // Also consider it disconnected if it's been trying to connect for too long (>30 seconds)
      const connectionDuration = Date.now() - (this.wsConnectionStartTime || Date.now());
      const isConnectingTooLong = wsConnecting && connectionDuration > 30000;
      
      if ((!wsHealthy && !wsConnecting) || isConnectingTooLong) {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'WebSocket Disconnected';
        this.statusText.title = 'Real-time updates are unavailable. Board changes will not sync in real-time. Try force reloading (Ctrl+Shift+R).';
        this.dbConnected = false;
        return;
      }
      
      // Track when connection started trying
      if (wsConnecting && !this.wsConnectionStartTime) {
        this.wsConnectionStartTime = Date.now();
      } else if (!wsConnecting && this.wsConnectionStartTime) {
        // No longer connecting (whether succeeded or failed), reset the timer
        this.wsConnectionStartTime = null;
      }
    }

    // Third: Check database health
    if (!serverReachable || !testData || !testData.success) {
      // Database is unhealthy
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'DB Error';
      this.statusText.title = testData?.message || 'Database error';
      this.dbConnected = false;
      return;
    }

    // All systems OK - get full status
    const versionController = new AbortController();
    const versionTimeoutId = setTimeout(() => versionController.abort(), 5000);
    
    try {
      const [versionResponse, healthResponse] = await Promise.all([
        fetch('/api/version', { signal: versionController.signal }),
        fetch('/api/scheduler/health', { signal: versionController.signal })
      ]);
      
      clearTimeout(versionTimeoutId);
      
      const versionData = await versionResponse.json();
      const healthData = await healthResponse.json();
      
      // Check housekeeping scheduler health
      const housekeepingHealth = healthData.housekeeping_scheduler;
      const isHousekeepingHealthy = housekeepingHealth && 
                                     housekeepingHealth.running && 
                                     housekeepingHealth.thread_alive;
      
      this.updateStatus('success', 'Connected', testData.boards_count, isHousekeepingHealthy);
      
      // Update version display
      if (versionData.success) {
        this.updateVersion(versionData.app_version, versionData.db_version);
      }
    } catch (err) {
      clearTimeout(versionTimeoutId);
      
      // Server/connection error (not a DB-specific error)
      if (err.name === 'AbortError') {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'Server Connection Error';
        this.statusText.title = 'API request timed out (5s). Check server connectivity.';
        this.dbConnected = false;
      } else {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'Server Connection Error';
        this.statusText.title = `Server connection error: ${err.message}`;
        this.dbConnected = false;
      }
    }
  }

  // Update version display
  updateVersion(appVersion, dbVersion) {
    const versionElement = this.versionInfo || document.getElementById('version-info');
    if (versionElement) {
      versionElement.textContent = `v${appVersion} | DB:${dbVersion}`;
    }
  }

  /**
   * Load version info from API.
   * 
   * Fetches app and database version information without triggering
   * WebSocket status checks. Silently fails if server is unavailable.
   */
  async loadVersionInfo() {
    try {
      const response = await fetch('/api/version', { 
        signal: AbortSignal.timeout(5000) 
      });
      const versionData = await response.json();
      
      if (versionData.success) {
        this.updateVersion(versionData.app_version, versionData.db_version);
      }
    } catch (error) {
      // Silently fail - version info is optional
      console.debug('Could not load version info:', error);
    }
  }

  // Load boards for dropdown menu
  async loadBoardsDropdown() {
    try {
      const response = await fetch('/api/boards');
      const data = await response.json();
      
      const dropdown = document.getElementById('boards-dropdown-menu');
      if (!dropdown) return;
      
      if (data.success && data.boards && data.boards.length > 0) {
        // Clear loading message
        dropdown.innerHTML = '';
        
        // Add each board as a link
        data.boards.forEach(board => {
          const link = document.createElement('a');
          link.href = `/board.html?id=${board.id}`;
          link.className = 'boards-dropdown-item';
          link.textContent = board.name;
          dropdown.appendChild(link);
        });
      } else {
        dropdown.innerHTML = '<div class="boards-dropdown-empty">No boards yet</div>';
      }
    } catch (error) {
      console.error('Error loading boards dropdown:', error);
      const dropdown = document.getElementById('boards-dropdown-menu');
      if (dropdown) {
        dropdown.innerHTML = '<div class="boards-dropdown-empty">Error loading boards</div>';
      }
    }
  }

  // Cleanup method to prevent memory leaks
  destroy() {
    if (this.statusCheckInterval) {
      clearInterval(this.statusCheckInterval);
      this.statusCheckInterval = null;
    }
    if (this.wsCheckInterval) {
      clearInterval(this.wsCheckInterval);
      this.wsCheckInterval = null;
    }
  }
}

// Initialize header on page load
const header = new Header();
window.header = header; // Make it globally accessible
document.addEventListener('DOMContentLoaded', () => {
  header.load();
  // Preload time format preference
  if (typeof preloadTimeFormat === 'function') {
    preloadTimeFormat();
  }
});

// Cleanup on page unload to prevent memory leaks
window.addEventListener('beforeunload', () => {
  header.destroy();
});
