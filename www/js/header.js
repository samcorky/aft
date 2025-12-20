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
    
    // Check database status immediately
    this.checkDatabaseStatus();
    
    // Poll database status every 5 seconds
    this.statusCheckInterval = setInterval(() => {
      this.checkDatabaseStatus();
    }, 5000);
    
    // Initialize WebSocket monitoring
    this.monitorWebSocketConnection();
  }

  // Monitor WebSocket connection status
  monitorWebSocketConnection() {
    // Check WebSocket status every 5 seconds
    this.wsCheckInterval = setInterval(() => {
      this.updateWebSocketStatus();
    }, 5000);
    
    // Initial check
    this.updateWebSocketStatus();
  }

  // Update WebSocket connection status
  updateWebSocketStatus() {
    // Check if socket.io global is available and connected
    const wsHealthy = (typeof io !== 'undefined' && 
                       window.boardManager && 
                       window.boardManager.wsManager && 
                       window.boardManager.wsManager.socket && 
                       window.boardManager.wsManager.socket.connected);
    
    this.wsConnected = wsHealthy;
    
    // If WebSocket is disconnected, show connection error (don't bother with DB check)
    if (!wsHealthy) {
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

  // Update the database status indicator
  updateStatus(status, message, count = null, housekeepingHealthy = true) {
    if (!this.statusIcon || !this.statusText) return;

    // First check if WebSocket is connected - if not, show connection error only
    const wsHealthy = (typeof io !== 'undefined' && 
                       window.boardManager && 
                       window.boardManager.wsManager && 
                       window.boardManager.wsManager.socket && 
                       window.boardManager.wsManager.socket.connected);
    
    if (!wsHealthy) {
      // WebSocket down = connection error, don't show DB errors
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Connection Error';
      this.statusText.title = 'WebSocket connection lost. Real-time updates may not work. Try force reloading the page (Ctrl+Shift+R).';
      this.dbConnected = false;
      return;
    }
    
    // WebSocket is connected, now evaluate DB status
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

  // Check database connection status
  async checkDatabaseStatus() {
    // First check if WebSocket is connected - if not, don't bother checking DB
    const wsHealthy = (typeof io !== 'undefined' && 
                       window.boardManager && 
                       window.boardManager.wsManager && 
                       window.boardManager.wsManager.socket && 
                       window.boardManager.wsManager.socket.connected);
    
    if (!wsHealthy) {
      // WebSocket disconnected = connection error, skip DB check
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Connection Error';
      this.statusText.title = 'WebSocket connection lost. Real-time updates may not work. Try force reloading the page (Ctrl+Shift+R).';
      this.dbConnected = false;
      return;
    }
    
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
        this.updateStatus('error', testData.message, null, false);
      }
      
      // Update version display
      if (versionData.success) {
        this.updateVersion(versionData.app_version, versionData.db_version);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      
      if (err.name === 'AbortError') {
        this.updateStatus('error', 'Connection timeout (5s)', null, false);
      } else {
        this.updateStatus('error', err.message, null, false);
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
