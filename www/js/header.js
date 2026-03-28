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
    this.workingStyle = 'kanban'; // Working style: 'kanban' or 'board_task_category'
    this.dbConnected = false; // Track database connection status
    this.wsConnected = false; // Track WebSocket connection status
    this.wsConnectionStartTime = null; // Track when WebSocket connection attempt started (for timeout detection)
    this.wsCheckInterval = null; // WebSocket check interval
    this.mobileBreakpoint = 900;
    this.boardFiltersVisibilityHandler = this.handleBoardFiltersVisibilityChanged.bind(this);
    this.boardFilterStateWatchInterval = null;
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

    // Initialize mobile drawer behavior
    this.initializeMobileMenu();

    // Initialize mobile notifications panel
    this.initializeMobileNotifications();

    // Initialize board-only filter toggle in settings menu
    this.initializeBoardFilterToggleMenu();
    
    // Load current user info
    await this.loadCurrentUser();
    
    // Load working style preference
    await this.loadWorkingStyle();
    
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
    const { wsHealthy, wsConnecting, ...rest } = this._getWebSocketConnectionState();
    
    // Track state changes by comparing individual properties
    const newState = { ...rest, wsHealthy, wsConnecting };
    
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
    
    const themeSocket = window.AFT?.themeBuilderSocket || window.themeBuilderSocket;
    const themeSocketConnected = themeSocket && themeSocket.connected;
    
    // Check if either socket is connecting
    // A socket is "connecting" if it exists but is not connected and not explicitly disconnected
    // Socket.IO's internal state handles reconnection automatically
    const boardSocketConnecting = boardSocket && !boardSocketConnected && 
                                  boardSocket.io?.engine?.readyState && 
                                  boardSocket.io.engine.readyState !== 'closed';
    const themeSocketConnecting = themeSocket && !themeSocketConnected && 
                                  themeSocket.io?.engine?.readyState && 
                                  themeSocket.io.engine.readyState !== 'closed';
    
    const hasSocket = !!boardSocket || !!themeSocket;
    const wsHealthy = boardSocketConnected || themeSocketConnected;
    const wsConnecting = boardSocketConnecting || themeSocketConnecting;
    
    return { hasSocket, wsHealthy, wsConnecting, ioLoaded: true };
  }

  updateWebSocketStatus() {
    const { hasSocket, wsHealthy, wsConnecting, ioLoaded } = this._getWebSocketConnectionState();
    
    this.wsConnected = wsHealthy;
    
    // If Socket.IO library failed to load on a page that needs it, show error
    // Note: REST API calls still work without WebSocket, so don't block card operations
    if (ioLoaded && !hasSocket && !wsConnecting) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'WebSocket Disconnected';
      this.statusText.title = 'Real-time updates are unavailable. Board changes will not sync in real-time. Try force reloading (Ctrl+Shift+R).';
      // Note: Don't modify dbConnected here - this method doesn't verify server/DB health
      // Only checkDatabaseStatus() can safely set dbConnected=true after verifying server is reachable
      return;
    }
    
    // Only show connection error if socket exists and is not connecting and is not healthy
    // Note: REST API calls and card creation still work without WebSocket
    if (hasSocket && !wsHealthy && !wsConnecting) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'WebSocket Disconnected';
      this.statusText.title = 'Real-time updates are unavailable. Board changes will not sync in real-time. Try force reloading (Ctrl+Shift+R).';
      // Note: Don't modify dbConnected here - this method doesn't verify server/DB health
      // Only checkDatabaseStatus() can safely set dbConnected=true after verifying server is reachable
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

    this.syncMobileViewVisibility(show);
  }

  // Keep mobile view section visibility aligned with desktop view control state
  syncMobileViewVisibility(show) {
    const mobileViewsSection = document.getElementById('mobile-views-section');
    if (mobileViewsSection) {
      mobileViewsSection.style.display = show ? '' : 'none';
    }
  }

  // Initialize mobile drawer menu interactions
  initializeMobileMenu() {
    const header = document.querySelector('.header');
    const toggleBtn = document.getElementById('mobile-menu-toggle');
    const closeBtn = document.getElementById('mobile-menu-close');
    const overlay = document.getElementById('mobile-menu-overlay');
    const drawer = document.getElementById('mobile-menu-drawer');

    if (!header || !toggleBtn || !closeBtn || !overlay || !drawer) {
      return;
    }

    const openMenu = () => {
      header.classList.add('mobile-menu-open');
      document.body.classList.add('mobile-menu-open');
      toggleBtn.setAttribute('aria-expanded', 'true');
    };

    const closeMenu = () => {
      header.classList.remove('mobile-menu-open');
      document.body.classList.remove('mobile-menu-open');
      toggleBtn.setAttribute('aria-expanded', 'false');
    };

    toggleBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (header.classList.contains('mobile-menu-open')) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    closeBtn.addEventListener('click', closeMenu);
    overlay.addEventListener('click', closeMenu);

    // Auto-close drawer after selecting a menu option
    drawer.addEventListener('click', (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      if (target.matches('a.mobile-menu-link, a.mobile-notification-link')) {
        closeMenu();
      }
    });

    // Close on escape and when returning to desktop layout
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && header.classList.contains('mobile-menu-open')) {
        closeMenu();
      }
    });

    window.addEventListener('resize', () => {
      if (window.innerWidth > this.mobileBreakpoint) {
        closeMenu();
      }
    });

    // Handle mobile view actions
    drawer.querySelectorAll('.mobile-view-item').forEach(item => {
      item.addEventListener('click', (e) => {
        const view = e.currentTarget.dataset.view;
        if (!view) {
          return;
        }
        this.setView(view);
        closeMenu();
      });
    });

    // Hook mobile logout button into existing logout flow
    const mobileLogoutItem = document.getElementById('mobile-logout-menu-item');
    if (mobileLogoutItem) {
      mobileLogoutItem.addEventListener('click', () => {
        closeMenu();
        this.handleLogout();
      });
    }
  }

  // Initialize mobile notifications section and sync it with notifications.js state
  initializeMobileNotifications() {
    const markAllReadBtn = document.getElementById('mobile-mark-all-read-btn');

    if (markAllReadBtn) {
      markAllReadBtn.addEventListener('click', async () => {
        if (window.notifications && typeof window.notifications.markAllAsRead === 'function') {
          await window.notifications.markAllAsRead();
          this.renderMobileNotifications(window.notifications.notifications || []);
        }
      });
    }

    window.addEventListener('notificationsUpdated', (e) => {
      const notifications = e.detail?.notifications || [];
      this.renderMobileNotifications(notifications);
    });

    if (window.notifications) {
      this.renderMobileNotifications(window.notifications.notifications || []);
    }
  }

  // Toggle mobile notification card read state using shared notifications component logic
  toggleMobileNotificationRead(card, notificationId, isCurrentlyUnread) {
    if (!card || !(card instanceof HTMLElement)) {
      return;
    }

    card.classList.toggle('unread', !isCurrentlyUnread);
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', isCurrentlyUnread ? 'Mark notification as unread' : 'Mark notification as read');

    if (window.notifications && typeof window.notifications.toggleRead === 'function') {
      window.notifications.toggleRead(notificationId, isCurrentlyUnread);
    } else if (isCurrentlyUnread && window.notifications && typeof window.notifications.markAsRead === 'function') {
      // Fallback for compatibility if toggleRead is unavailable.
      window.notifications.markAsRead(notificationId, true);
    }
  }

  // Build mobile notification cards and unread badge for the drawer
  renderMobileNotifications(notifications) {
    const mobileMenu = document.getElementById('mobile-notifications-menu');
    const badge = document.getElementById('mobile-notification-badge');
    const toggleDot = document.getElementById('mobile-menu-toggle-dot');
    const markAllReadBtn = document.getElementById('mobile-mark-all-read-btn');

    if (!mobileMenu || !badge || !markAllReadBtn) {
      return;
    }

    const allNotifications = Array.isArray(notifications) ? notifications : [];
    const unreadCount = allNotifications.filter(n => n.unread).length;

    if (unreadCount > 0) {
      badge.textContent = unreadCount > 9 ? '9+' : String(unreadCount);
      badge.style.display = 'inline-block';
      if (toggleDot) {
        toggleDot.style.display = 'inline-block';
      }
    } else {
      badge.style.display = 'none';
      if (toggleDot) {
        toggleDot.style.display = 'none';
      }
    }

    if (allNotifications.length > 0) {
      markAllReadBtn.style.display = '';
      markAllReadBtn.textContent = unreadCount === 0 ? 'Delete all' : 'Mark all read';
    } else {
      markAllReadBtn.style.display = 'none';
    }

    mobileMenu.innerHTML = '';

    if (allNotifications.length === 0) {
      mobileMenu.innerHTML = '<div class="mobile-menu-loading">No notifications</div>';
      return;
    }

    const sortedNotifications = [...allNotifications].sort((a, b) => {
      return new Date(b.created_at) - new Date(a.created_at);
    });

    sortedNotifications.slice(0, 10).forEach(notification => {
      const item = document.createElement('div');
      item.className = `mobile-notification-item${notification.unread ? ' unread' : ''}`;
      item.dataset.notificationId = String(notification.id);

      item.setAttribute('role', 'button');
      item.setAttribute('tabindex', '0');
      item.setAttribute('aria-label', notification.unread ? 'Mark notification as read' : 'Mark notification as unread');

      const handleCardActivate = (e) => {
        if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') {
          return;
        }
        if (e.target && e.target.closest('.mobile-notification-link')) {
          return;
        }
        if (e.type === 'keydown') {
          e.preventDefault();
        }
        const isUnread = item.classList.contains('unread');
        this.toggleMobileNotificationRead(item, notification.id, isUnread);
      };
      item.addEventListener('click', handleCardActivate);
      item.addEventListener('keydown', handleCardActivate);

      const subject = document.createElement('div');
      subject.className = 'mobile-notification-subject';
      subject.textContent = notification.subject || '';

      const message = document.createElement('div');
      message.className = 'mobile-notification-message';
      message.textContent = notification.message || '';

      const meta = document.createElement('div');
      meta.className = 'mobile-notification-meta';

      const time = document.createElement('div');
      time.className = 'mobile-notification-time';
      time.textContent = this.formatRelativeTime(notification.created_at);
      meta.appendChild(time);

      const hasAction = notification.action_title && notification.action_url && this.isSafeMobileUrl(notification.action_url);
      if (hasAction) {
        const actionLink = document.createElement('a');
        actionLink.className = 'mobile-notification-link';
        actionLink.href = notification.action_url;
        actionLink.textContent = notification.action_title;
        if (notification.unread && window.notifications && typeof window.notifications.markAsRead === 'function') {
          actionLink.addEventListener('click', () => {
            window.notifications.markAsRead(notification.id, true);
          });
        }
        meta.appendChild(actionLink);
      }

      item.appendChild(subject);
      item.appendChild(message);
      item.appendChild(meta);
      mobileMenu.appendChild(item);
    });
  }

  // Restrict actionable notification links to safe protocols
  isSafeMobileUrl(url) {
    if (!url || typeof url !== 'string') {
      return false;
    }

    const normalized = url.trim().toLowerCase();
    return normalized.startsWith('/') || normalized.startsWith('http://') || normalized.startsWith('https://');
  }

  // Format notification timestamps for compact mobile cards
  formatRelativeTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
      return 'Just now';
    }
    if (diffMins < 60) {
      return `${diffMins}m ago`;
    }
    if (diffHours < 24) {
      return `${diffHours}h ago`;
    }
    if (diffDays < 7) {
      return `${diffDays}d ago`;
    }
    return date.toLocaleDateString();
  }

  // Load current user info
  async loadCurrentUser() {
    try {
      const userNameEl = document.getElementById('header-user-name');
      const mobileUserNameEl = document.getElementById('mobile-header-user-name');
      const loginItem = document.getElementById('login-menu-item');
      const mobileLoginItem = document.getElementById('mobile-login-menu-item');
      const logoutItem = document.getElementById('logout-menu-item');
      const mobileLogoutItem = document.getElementById('mobile-logout-menu-item');
      
      // Check sessionStorage cache first to avoid API calls on every page load
      const cachedUser = sessionStorage.getItem('currentUser');
      if (cachedUser) {
        try {
          const userData = JSON.parse(cachedUser);
          // Use cached data
          window.currentUser = userData;
          
          const displayName = userData.display_name || userData.username || userData.email;
          if (userNameEl) userNameEl.textContent = displayName;
          if (mobileUserNameEl) mobileUserNameEl.textContent = displayName;
          if (loginItem) loginItem.style.display = 'none';
          if (mobileLoginItem) mobileLoginItem.style.display = 'none';
          if (logoutItem) {
            logoutItem.style.display = 'block';
            // Add logout handler
            logoutItem.addEventListener('click', () => this.handleLogout());
          }
          if (mobileLogoutItem) {
            mobileLogoutItem.style.display = 'block';
          }
          
          // Filter menu items based on permissions
          this.filterMenuByPermissions();
          
          // Mark user data as ready
          window.userDataReady = true;
          return; // Use cache, skip API call
        } catch (e) {
          // Invalid cache, remove it and fetch fresh
          sessionStorage.removeItem('currentUser');
        }
      }
      
      // No cache or invalid cache - fetch from API
      const response = await fetch('/api/auth/me');
      
      if (response.ok) {
        const data = await response.json();
        if (data.user) {
          // User is logged in - store globally and in cache
          window.currentUser = data.user;
          sessionStorage.setItem('currentUser', JSON.stringify(data.user));
          
          const displayName = data.user.display_name || data.user.username || data.user.email;
          if (userNameEl) userNameEl.textContent = displayName;
          if (mobileUserNameEl) mobileUserNameEl.textContent = displayName;
          if (loginItem) loginItem.style.display = 'none';
          if (mobileLoginItem) mobileLoginItem.style.display = 'none';
          if (logoutItem) {
            logoutItem.style.display = 'block';
            // Add logout handler
            logoutItem.addEventListener('click', () => this.handleLogout());
          }
          if (mobileLogoutItem) {
            mobileLogoutItem.style.display = 'block';
          }
          
          // Filter menu items based on permissions
          this.filterMenuByPermissions();
          
          // Mark user data as ready
          window.userDataReady = true;
          return;
        }
      }
      
      // User is not logged in or error occurred
      window.currentUser = null;
      sessionStorage.removeItem('currentUser');
      if (userNameEl) userNameEl.textContent = 'Guest';
      if (mobileUserNameEl) mobileUserNameEl.textContent = 'Guest';
      if (loginItem) loginItem.style.display = 'block';
      if (mobileLoginItem) mobileLoginItem.style.display = 'block';
      if (logoutItem) logoutItem.style.display = 'none';
      if (mobileLogoutItem) mobileLogoutItem.style.display = 'none';
      
      // Hide permission-protected menu items
      this.filterMenuByPermissions();
      
      // Mark user data as ready (even if not logged in)
      window.userDataReady = true;
    } catch (error) {
      console.error('Error loading current user:', error);
      // Show guest on error
      window.currentUser = null;
      sessionStorage.removeItem('currentUser');
      const userNameEl = document.getElementById('header-user-name');
      const mobileUserNameEl = document.getElementById('mobile-header-user-name');
      if (userNameEl) userNameEl.textContent = 'Guest';
      if (mobileUserNameEl) mobileUserNameEl.textContent = 'Guest';
      const loginItem = document.getElementById('login-menu-item');
      const mobileLoginItem = document.getElementById('mobile-login-menu-item');
      const logoutItem = document.getElementById('logout-menu-item');
      const mobileLogoutItem = document.getElementById('mobile-logout-menu-item');
      if (loginItem) loginItem.style.display = 'block';
      if (mobileLoginItem) mobileLoginItem.style.display = 'block';
      if (logoutItem) logoutItem.style.display = 'none';
      if (mobileLogoutItem) mobileLogoutItem.style.display = 'none';
      
      // Hide permission-protected menu items
      this.filterMenuByPermissions();
      
      // Mark user data as ready (even on error)
      window.userDataReady = true;
    }
  }

  // Filter menu items based on user permissions
  filterMenuByPermissions() {
    // Menu items and their required permissions
    const protectedItems = [
      {
        selectors: ['a[href="/backup-restore.html"]'],
        permission: 'admin.database'
      },
      {
        selectors: ['a[href="/user-management.html"]'],
        permissions: ['user.manage', 'user.role'],
        requireAny: true
      },
      {
        selectors: ['a[href="/role-management.html"]'],
        permission: 'role.manage'
      }
    ];
    
    protectedItems.forEach(item => {
      const selectors = item.selectors || (item.selector ? [item.selector] : []);
      const menuItems = selectors.flatMap(selector => Array.from(document.querySelectorAll(selector)));
      if (menuItems.length > 0) {
        let hasAccess = false;
        
        // Check if user has permission (hasPermission is defined in utils.js)
        if (item.permissions && item.requireAny) {
          // User needs ANY of the listed permissions
          hasAccess = item.permissions.some(perm => 
            typeof hasPermission === 'function' && hasPermission(perm)
          );
        } else if (item.permission) {
          // User needs the single permission
          hasAccess = typeof hasPermission === 'function' && hasPermission(item.permission);
        }
        
        menuItems.forEach(menuItem => {
          if (hasAccess) {
            menuItem.style.display = '';  // Show
          } else {
            menuItem.style.display = 'none';  // Hide
          }
        });
      }
    });
  }

  // Handle logout
  async handleLogout() {
    try {
      // Clear cached user data
      sessionStorage.removeItem('currentUser');
      window.currentUser = null;
      window.userDataReady = false;
      
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      // Redirect to logout page regardless of response
      window.location.href = '/logout.html';
    } catch (error) {
      console.error('Error logging out:', error);
      // Still redirect to logout page
      window.location.href = '/logout.html';
    }
  }

  // Load working style preference
  async loadWorkingStyle() {
    try {
      const response = await fetch('/api/settings/working-style');
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          this.workingStyle = data.value || 'kanban';
          // Update views dropdown based on working style
          this.updateViewsDropdown();
        }
      } else if (response.status === 404) {
        // Setting doesn't exist, default to kanban
        this.workingStyle = 'kanban';
        this.updateViewsDropdown();
      }
    } catch (error) {
      console.error('Error loading working style:', error);
      this.workingStyle = 'kanban';
      this.updateViewsDropdown();
    }
  }

  initializeBoardFilterToggleMenu() {
    const menuItem = document.getElementById('toggle-board-filters-menu-item');
    if (!menuItem) {
      return;
    }

    const isBoardPage = document.body.classList.contains('board-page');
    menuItem.style.display = isBoardPage ? '' : 'none';
    if (!isBoardPage) {
      return;
    }

    if (!menuItem.dataset.boundToggleHandler) {
      menuItem.addEventListener('click', (e) => {
        e.preventDefault();

        window.dispatchEvent(new CustomEvent('boardFiltersToggleRequested'));

        closeAllMenusExcept(null);
        updateMenuHoverState();
      });
      menuItem.dataset.boundToggleHandler = 'true';
    }

    // Initialize label from current board manager state when possible.
    let initialVisible = false;
    if (window.boardManager && typeof window.boardManager.assigneeFilterVisible === 'boolean') {
      initialVisible = window.boardManager.assigneeFilterVisible;
    }
    this.updateBoardFilterMenuLabel(initialVisible);
    window.addEventListener('boardFiltersVisibilityChanged', this.boardFiltersVisibilityHandler);

    // Request current state in case the initial board event happened before this listener was attached.
    window.dispatchEvent(new CustomEvent('boardFiltersStateRequest'));
    this.watchForBoardFilterState();
  }

  watchForBoardFilterState() {
    if (this.boardFilterStateWatchInterval) {
      clearInterval(this.boardFilterStateWatchInterval);
      this.boardFilterStateWatchInterval = null;
    }

    let attempts = 0;
    const maxAttempts = 50;
    this.boardFilterStateWatchInterval = setInterval(() => {
      attempts += 1;

      if (window.boardManager && typeof window.boardManager.assigneeFilterVisible === 'boolean') {
        this.updateBoardFilterMenuLabel(window.boardManager.assigneeFilterVisible);
        window.dispatchEvent(new CustomEvent('boardFiltersStateRequest'));
        clearInterval(this.boardFilterStateWatchInterval);
        this.boardFilterStateWatchInterval = null;
        return;
      }

      if (attempts >= maxAttempts) {
        clearInterval(this.boardFilterStateWatchInterval);
        this.boardFilterStateWatchInterval = null;
      }
    }, 100);
  }

  handleBoardFiltersVisibilityChanged(event) {
    const visible = !!event?.detail?.visible;
    this.updateBoardFilterMenuLabel(visible);
  }

  updateBoardFilterMenuLabel(visible) {
    const menuItem = document.getElementById('toggle-board-filters-menu-item');
    if (!menuItem) {
      return;
    }

    menuItem.textContent = visible ? 'Hide filters' : 'Show filters';
  }

  // Update views dropdown to show/hide done view based on working style
  updateViewsDropdown() {
    const dropdownMenu = document.getElementById('views-dropdown-menu');
    if (!dropdownMenu) return;

    if (this.workingStyle === 'board_task_category') {
      // Check if done view already exists
      if (!document.querySelector('.views-dropdown-item[data-view="done"]')) {
        // Add done view option
        const doneItem = document.createElement('button');
        doneItem.className = 'views-dropdown-item';
        doneItem.setAttribute('data-view', 'done');
        doneItem.innerHTML = `
          <svg class="views-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span>Done View</span>
        `;
        
        // Add click handler directly to the new item
        doneItem.addEventListener('click', (e) => {
          if (doneItem.classList.contains('active')) {
            e.preventDefault();
            e.stopPropagation();
            return;
          }
          this.setView('done');
          dropdownMenu.classList.remove('show');
        });
        
        dropdownMenu.appendChild(doneItem);
      }
    } else {
      // Remove done view if it exists
      const doneItem = document.querySelector('.views-dropdown-item[data-view="done"]');
      if (doneItem) {
        doneItem.remove();
      }
    }

    // Keep mobile views in sync with active working style
    const mobileViewsSection = document.getElementById('mobile-views-section');
    if (mobileViewsSection) {
      const mobileDoneItem = mobileViewsSection.querySelector('.mobile-view-item[data-view="done"]');
      if (this.workingStyle === 'board_task_category') {
        if (!mobileDoneItem) {
          const doneBtn = document.createElement('button');
          doneBtn.className = 'mobile-view-item';
          doneBtn.setAttribute('data-view', 'done');
          doneBtn.textContent = 'Done View';
          doneBtn.addEventListener('click', () => {
            this.setView('done');
            const header = document.querySelector('.header');
            if (header) {
              header.classList.remove('mobile-menu-open');
            }
            document.body.classList.remove('mobile-menu-open');
            const mobileToggle = document.getElementById('mobile-menu-toggle');
            if (mobileToggle) {
              mobileToggle.setAttribute('aria-expanded', 'false');
            }
          });
          mobileViewsSection.querySelector('.mobile-tree-items')?.appendChild(doneBtn);
        }
      } else if (mobileDoneItem) {
        mobileDoneItem.remove();
      }
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
        'archived': 'Archived View',
        'done': 'Done View'
      };
      label.textContent = viewNames[view] || 'Task View';
    }

    // Highlight active item
    document.querySelectorAll('.views-dropdown-item').forEach(item => {
      item.classList.toggle('active', item.dataset.view === view);
    });

    document.querySelectorAll('.mobile-view-item').forEach(item => {
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
    // Note: WebSocket is for real-time sync only. REST API calls still work, so don't block operations
    if (hasSocket && !wsHealthy && !wsConnecting) {
      // WebSocket exists but is down and not connecting = connection error
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Connection Error';
      this.statusText.title = 'WebSocket connection lost. Real-time updates may not work. Try force reloading the page (Ctrl+Shift+R).';
      // Note: dbConnected NOT set to false - REST API calls still work
      return;
    }
    
    // WebSocket is connected (or not required on this page), now evaluate DB status
    // Note: Housekeeping scheduler health is displayed but does NOT block database operations
    // Only critical failures (DB, WebSocket, Server) prevent card creation
    
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
    // First: Check if server is reachable (API responds at all)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    let liveData = null;
    
    try {
      const response = await fetch('/api/health/live', {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      liveData = await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      // Server is not responding - network error or server is down
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Server Disconnected';
      this.statusText.title = 'Unable to connect to server. Check your connection or try refreshing the page.';
      this.dbConnected = false;
      return;
    }

    // Second: Check WebSocket status on pages that need it (board, theme-builder)
    // Do this BEFORE checking database health so we can report WebSocket issues even if DB is down
    // Detect if we're on a page that should have Socket.IO loaded
    // Check for page-specific elements rather than socket existence to handle Socket.IO load failures
    const isOnBoardPage = (window.boardManager && window.boardManager.wsManager) || 
                          (document.getElementById('theme-builder-select') !== null);
    
    if (isOnBoardPage) {
      const { hasSocket, wsHealthy, wsConnecting, ioLoaded } = this._getWebSocketConnectionState();
      
      // If we're on a board page but Socket.IO isn't loaded, that's an error
      // However: REST API calls still work without WebSocket, so don't block operations
      if (!ioLoaded) {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'WebSocket Disconnected';
        this.statusText.title = 'Real-time updates are unavailable. Socket.IO library failed to load. Try force reloading (Ctrl+Shift+R).';
        // Set dbConnected=true: We've already verified server is reachable (via /api/health/live above)
        // WebSocket failure doesn't affect REST API calls or database operations
        this.dbConnected = true;
        return;
      }
      
      // If Socket.IO is loaded but WebSocket isn't working (not connected and not trying)
      // Display error but don't block API operations since REST calls still work
      // Also consider it disconnected if it's been trying to connect for too long (>30 seconds)
      const connectionDuration = Date.now() - (this.wsConnectionStartTime || Date.now());
      const isConnectingTooLong = wsConnecting && connectionDuration > 30000;
      
      if ((!wsHealthy && !wsConnecting) || isConnectingTooLong) {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'WebSocket Disconnected';
        this.statusText.title = 'Real-time updates are unavailable. Board changes will not sync in real-time. Try force reloading (Ctrl+Shift+R).';
        // Set dbConnected=true: We've already verified server is reachable (via /api/health/live above)
        // WebSocket failure doesn't affect REST API calls or database operations
        this.dbConnected = true;
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

    if (!liveData || !liveData.ok) {
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'Server Disconnected';
      this.statusText.title = 'Unable to connect to server. Check your connection or try refreshing the page.';
      this.dbConnected = false;
      return;
    }

    // Third: Check database health via authenticated version endpoint
    let versionData = null;
    const dbController = new AbortController();
    const dbTimeoutId = setTimeout(() => dbController.abort(), 5000);

    try {
      const versionResponse = await fetch('/api/version', { signal: dbController.signal });
      clearTimeout(dbTimeoutId);
      versionData = await versionResponse.json();

      if (!versionResponse.ok || !versionData.success) {
        this.statusIcon.className = 'status-icon error';
        this.statusText.textContent = 'DB Error';
        this.statusText.title = versionData?.message || 'Database error. Check database connection.';
        this.dbConnected = false;
        return;
      }
    } catch (err) {
      clearTimeout(dbTimeoutId);
      this.statusIcon.className = 'status-icon error';
      this.statusText.textContent = 'DB Error';
      this.statusText.title = err.name === 'AbortError'
        ? 'Database check timed out (5s).'
        : `Database check failed: ${err.message}`;
      this.dbConnected = false;
      return;
    }

    // All systems OK - get scheduler status
    const healthController = new AbortController();
    const healthTimeoutId = setTimeout(() => healthController.abort(), 5000);
    
    try {
      const healthResponse = await fetch('/api/scheduler/health', { signal: healthController.signal });
      
      clearTimeout(healthTimeoutId);
      
      const healthData = await healthResponse.json();
      
      // Check housekeeping scheduler health
      const housekeepingHealth = healthData.housekeeping_scheduler;
      const isHousekeepingHealthy = housekeepingHealth && 
                                     housekeepingHealth.running && 
                                     housekeepingHealth.thread_alive;
      
      this.updateStatus('success', 'Connected', null, isHousekeepingHealthy);
      
      // Update version display
      if (versionData.success) {
        this.updateVersion(versionData.app_version, versionData.db_version);
      }
    } catch (err) {
      clearTimeout(healthTimeoutId);
      
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
      const mobileBoardsMenu = document.getElementById('mobile-boards-menu');
      if (!dropdown) return;
      
      if (data.success && data.boards && data.boards.length > 0) {
        // Clear loading message
        dropdown.innerHTML = '';
        if (mobileBoardsMenu) {
          mobileBoardsMenu.innerHTML = '';
        }
        
        // Add each board as a link
        data.boards.forEach(board => {
          const link = document.createElement('a');
          link.href = `/board.html?id=${board.id}`;
          link.className = 'boards-dropdown-item';
          link.textContent = board.name;
          dropdown.appendChild(link);

          if (mobileBoardsMenu) {
            const mobileLink = document.createElement('a');
            mobileLink.href = `/board.html?id=${board.id}`;
            mobileLink.className = 'mobile-menu-link';
            mobileLink.textContent = board.name;
            mobileBoardsMenu.appendChild(mobileLink);
          }
        });
      } else {
        dropdown.innerHTML = '<div class="boards-dropdown-empty">No boards yet</div>';
        if (mobileBoardsMenu) {
          mobileBoardsMenu.innerHTML = '<div class="mobile-menu-loading">No boards yet</div>';
        }
      }
    } catch (error) {
      console.error('Error loading boards dropdown:', error);
      const dropdown = document.getElementById('boards-dropdown-menu');
      const mobileBoardsMenu = document.getElementById('mobile-boards-menu');
      if (dropdown) {
        dropdown.innerHTML = '<div class="boards-dropdown-empty">Error loading boards</div>';
      }
      if (mobileBoardsMenu) {
        mobileBoardsMenu.innerHTML = '<div class="mobile-menu-loading">Error loading boards</div>';
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

    window.removeEventListener('boardFiltersVisibilityChanged', this.boardFiltersVisibilityHandler);
    if (this.boardFilterStateWatchInterval) {
      clearInterval(this.boardFilterStateWatchInterval);
      this.boardFilterStateWatchInterval = null;
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
