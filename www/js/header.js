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
    this.wsLastHeartbeat = null; // Track last WebSocket heartbeat
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
    
    // Initialize status as "healthy" by default (optimistic approach)
    // Will be updated by checks if there's an actual problem
    if (this.statusIcon && this.statusText) {
      this.statusIcon.className = 'status-icon success';
      this.statusText.textContent = 'Server healthy';
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
  monitorWebSocketConnection() {
    // Check WebSocket status every 5 seconds
    this.wsCheckInterval = setInterval(() => {
      this.checkWebSocketStatusWithInitialDelay();
    }, 5000);
    
    // Listen for socket connection events on board manager socket if available
    if (window.boardManager && window.boardManager.wsManager) {
      const wsManager = window.boardManager.wsManager;
      // Store reference so we can attach listeners when socket is created
      wsManager.onSocketCreated = (socket) => {
        socket.on('connect', () => {
          // Immediately update when connected
          this.updateWebSocketStatus();
        });
        socket.on('disconnect', () => {
          // Immediately update when disconnected
          this.updateWebSocketStatus();
        });
      };
    }
    
    // Listen for theme builder socket events
    // Theme socket creation is handled differently, check in real-time
  }

  /**
   * Check WebSocket status with awareness of initial page load.
   * 
   * On initial page load, don't mark a "connecting" socket as an error.
   * Only mark as error if socket exists and is clearly disconnected (not connecting).
   */
  checkWebSocketStatusWithInitialDelay() {
    const { hasSocket, wsHealthy, wsConnecting } = this._getWebSocketConnectionState();
    
    // Track state changes
    const newState = { hasSocket, wsHealthy, wsConnecting };
    
    // Only update if state actually changed (not on every 5s interval)
    if (JSON.stringify(this.lastWsState) !== JSON.stringify(newState)) {
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
      // Socket.io not loaded on this page
      return { hasSocket: false, wsHealthy: false, wsConnecting: false };
    }
    
    // Check for board manager socket OR theme builder socket
    const boardSocket = (window.boardManager && 
                         window.boardManager.wsManager && 
                         window.boardManager.wsManager.socket);
    const boardSocketConnected = boardSocket && boardSocket.connected;
    
    const themeSocketExists = window.themeBuilderSocket !== undefined;
    const themeSocket = themeSocketExists ? window.themeBuilderSocket : null;
    const themeSocketConnected = themeSocket && themeSocket.connected;
    
    // Check if either socket is connecting (don't show error while connecting)
    const boardSocketConnecting = boardSocket && boardSocket.disconnected === false && !boardSocketConnected;
    const themeSocketConnecting = themeSocket && themeSocket.disconnected === false && !themeSocketConnected;
    
    const hasSocket = !!boardSocket || !!themeSocket;
    const wsHealthy = boardSocketConnected || themeSocketConnected;
    const wsConnecting = boardSocketConnecting || themeSocketConnecting;
    
    return { hasSocket, wsHealthy, wsConnecting };
  }

  updateWebSocketStatus() {
    const { hasSocket, wsHealthy, wsConnecting } = this._getWebSocketConnectionState();
    
    this.wsConnected = wsHealthy;
    
    // Only show connection error if socket exists and is not connecting and is not healthy
    if (hasSocket && !wsHealthy && !wsConnecting) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Connection Error';
      this.statusText.title = 'WebSocket connection lost. Real-time updates may not work. Try force reloading the page (Ctrl+Shift+R).';
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
      this.statusText.textContent = 'Server healthy';
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
   * Check database connection status by calling API.
   * 
   * Polls database health, version info, and scheduler status.
   * Updates header status based on results.
   */
  async checkDatabaseStatus() {
    // Only check WebSocket if socket.io is actually loaded on this page
    if (typeof io === 'undefined') {
      // Socket.io not loaded on this page - just check database directly
      // This happens on pages like settings that don't have real-time updates
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      try {
        const response = await fetch('/api/test', {
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        const data = await response.json();
        if (data.success) {
          this.updateStatus('success', 'Connected');
        } else {
          // API responded but DB is unhealthy
          this.statusIcon.className = 'status-icon error';
          this.statusText.textContent = 'DB Error';
          this.statusText.title = `Database error: ${data.message}`;
          this.dbConnected = false;
        }
      } catch (error) {
        clearTimeout(timeoutId);
        // Server/connection error
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'Server Connection Error';
        this.statusText.title = 'Unable to connect to server';
        this.dbConnected = false;
      }
      return;
    }
    
    // Check for board manager socket OR theme builder socket
    const boardSocketConnected = (window.boardManager && 
                                  window.boardManager.wsManager && 
                                  window.boardManager.wsManager.socket && 
                                  window.boardManager.wsManager.socket.connected);
    
    const themeSocketConnected = (window.themeBuilderSocket && 
                                  window.themeBuilderSocket.connected);
    
    const wsHealthy = (boardSocketConnected || themeSocketConnected);
    
    if (!wsHealthy) {
      // WebSocket disconnected = connection error, skip DB check
      // Don't check DB if connectivity is down - it requires connectivity
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Connection Error';
      this.statusText.title = 'WebSocket connection lost. Real-time updates may not work. Try force reloading the page (Ctrl+Shift+R).';
      this.dbConnected = false;
      return;
    }
    
    // Only perform DB check if WebSocket connectivity is healthy
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const [testResponse, versionResponse, healthResponse] = await Promise.all([
        fetch('/api/test', { signal: controller.signal }),
        fetch('/api/version', { signal: controller.signal }),
        fetch('/api/scheduler/health', { signal: controller.signal })
      ]);
      
      clearTimeout(timeoutId);
      
      const testData = await testResponse.json();
      const versionData = await versionResponse.json();
      const healthData = await healthResponse.json();
      
      if (testData.success) {
        // Check housekeeping scheduler health
        const housekeepingHealth = healthData.housekeeping_scheduler;
        const isHousekeepingHealthy = housekeepingHealth && 
                                       housekeepingHealth.running && 
                                       housekeepingHealth.thread_alive;
        
        this.updateStatus('success', 'Connected', testData.boards_count, isHousekeepingHealthy);
      } else {
        // API responded but DB is unhealthy - distinguish this from server connection errors
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'DB Error';
        this.statusText.title = `Database error: ${testData.message}`;
        this.dbConnected = false;
      }
      
      // Update version display
      if (versionData.success) {
        this.updateVersion(versionData.app_version, versionData.db_version);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      
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
