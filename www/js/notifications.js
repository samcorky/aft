/**
 * Notifications component for managing and displaying user notifications.
 */
class Notifications {
  constructor() {
    this.notifications = [];
    this.iconLink = document.getElementById('notifications-icon-link');
    this.popup = document.getElementById('notifications-popup');
    this.list = document.getElementById('notifications-list');
    this.badge = document.getElementById('notification-badge');
    this.markAllReadBtn = document.getElementById('mark-all-read-btn');
    this.isPopupOpen = false;

    this.init();
  }

  /**
   * Initialize the notifications component.
   */
  init() {
    // Verify elements exist
    if (!this.iconLink || !this.popup || !this.list || !this.badge) {
      console.error('Notifications: Required elements not found');
      return;
    }

    console.log('Notifications: Initializing...');

    // Set up event listeners
    this.iconLink.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.togglePopup();
    });

    // Mark all as read button
    if (this.markAllReadBtn) {
      this.markAllReadBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.markAllAsRead();
      });
    }

    // Close popup when clicking outside
    document.addEventListener('click', (e) => {
      if (this.isPopupOpen && !this.popup.contains(e.target) && !this.iconLink.contains(e.target)) {
        this.closePopup();
      }
    });

    // Event delegation for notification actions
    this.list.addEventListener('click', (e) => this.handleNotificationClick(e));
    this.list.addEventListener('keydown', (e) => this.handleNotificationKeydown(e));

    // Load notifications
    this.loadNotifications();

    // Refresh every 60 seconds
    setInterval(() => this.loadNotifications(), 60000);
  }

  /**
   * Toggle the notifications popup.
   */
  togglePopup() {
    if (this.isPopupOpen) {
      this.closePopup();
    } else {
      this.openPopup();
    }
  }

  /**
   * Open the notifications popup.
   */
  openPopup() {
    this.popup.classList.add('show');
    this.isPopupOpen = true;
    // Reload notifications when opening popup
    this.loadNotifications();
  }

  /**
   * Close the notifications popup.
   */
  closePopup() {
    this.popup.classList.remove('show');
    this.isPopupOpen = false;
  }

  /**
   * Load notifications from the API.
   */
  async loadNotifications() {
    try {
      const response = await fetch('/api/notifications');
      if (!response.ok) {
        throw new Error('Failed to load notifications');
      }

      const data = await response.json();
      this.notifications = data.notifications || [];
      this.renderNotifications();
      this.updateBadge();
    } catch (error) {
      console.error('Error loading notifications:', error);
      this.showError('Failed to load notifications');
    }
  }

  /**
   * Render the notifications list.
   */
  renderNotifications() {
    if (this.notifications.length === 0) {
      this.list.innerHTML = '<div class="notifications-empty">No notifications</div>';
      return;
    }

    // Sort by created_at descending (newest first)
    const sortedNotifications = [...this.notifications].sort((a, b) => {
      return new Date(b.created_at) - new Date(a.created_at);
    });

    this.list.innerHTML = sortedNotifications.map(notification => {
      return `
        <div class="notification-item ${notification.unread ? 'unread' : ''}" 
             data-id="${notification.id}"
             data-unread="${notification.unread}"
             role="listitem"
             tabindex="0">
          <div class="notification-content">
            <div class="notification-subject">${this.escapeHtml(notification.subject)}</div>
            <div class="notification-message">${this.escapeHtml(notification.message)}</div>
            <div class="notification-time">${this.formatTime(notification.created_at)}</div>
          </div>
          <div class="notification-actions">
            <button class="notification-action-btn read-btn" 
                    data-action="toggle-read"
                    data-id="${notification.id}"
                    data-unread="${notification.unread}"
                    aria-label="${notification.unread ? 'Mark as read' : 'Mark as unread'}"
                    title="${notification.unread ? 'Mark as read' : 'Mark as unread'}">
              ${notification.unread ? '✓' : '○'}
            </button>
            <button class="notification-action-btn delete-btn" 
                    data-action="delete"
                    data-id="${notification.id}"
                    aria-label="Delete notification"
                    title="Delete">
              ✕
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * Handle click events on notification items and actions.
   */
  handleNotificationClick(e) {
    const target = e.target;
    
    // Handle action button clicks
    if (target.classList.contains('notification-action-btn')) {
      e.stopPropagation();
      const action = target.dataset.action;
      const id = parseInt(target.dataset.id);
      const isUnread = target.dataset.unread === 'true';
      
      if (action === 'toggle-read') {
        this.toggleRead(id, isUnread);
      } else if (action === 'delete') {
        this.deleteNotification(id);
      }
      return;
    }
    
    // Handle notification item click (mark as read if unread)
    const notificationItem = target.closest('.notification-item');
    if (notificationItem) {
      const id = parseInt(notificationItem.dataset.id);
      const isUnread = notificationItem.dataset.unread === 'true';
      this.markAsRead(id, isUnread);
    }
  }

  /**
   * Handle keyboard events on notification items.
   */
  handleNotificationKeydown(e) {
    if (e.key !== 'Enter' && e.key !== ' ') {
      return;
    }
    
    e.preventDefault();
    const target = e.target;
    
    // Handle action button keyboard activation
    if (target.classList.contains('notification-action-btn')) {
      const action = target.dataset.action;
      const id = parseInt(target.dataset.id);
      const isUnread = target.dataset.unread === 'true';
      
      if (action === 'toggle-read') {
        this.toggleRead(id, isUnread);
      } else if (action === 'delete') {
        this.deleteNotification(id);
      }
      return;
    }
    
    // Handle notification item keyboard activation
    const notificationItem = target.closest('.notification-item');
    if (notificationItem) {
      const id = parseInt(notificationItem.dataset.id);
      const isUnread = notificationItem.dataset.unread === 'true';
      this.markAsRead(id, isUnread);
    }
  }

  /**
   * Update the notification badge.
   */
  updateBadge() {
    const unreadCount = this.notifications.filter(n => n.unread).length;
    const totalCount = this.notifications.length;
    
    if (unreadCount > 0) {
      this.badge.textContent = unreadCount > 9 ? '9+' : unreadCount;
      this.badge.style.display = 'flex';
    } else {
      this.badge.style.display = 'none';
    }

    // Update button based on unread count
    if (this.markAllReadBtn) {
      if (unreadCount === 0 && totalCount > 0) {
        // Change to delete all button
        this.markAllReadBtn.textContent = 'Delete all';
        this.markAllReadBtn.title = 'Delete all notifications';
        this.markAllReadBtn.disabled = false;
        this.markAllReadBtn.classList.add('delete-mode');
      } else {
        // Change to mark all read button
        this.markAllReadBtn.textContent = 'Mark all read';
        this.markAllReadBtn.title = 'Mark all as read';
        this.markAllReadBtn.disabled = unreadCount === 0;
        this.markAllReadBtn.classList.remove('delete-mode');
      }
    }
  }

  /**
   * Mark all notifications as read or delete all based on current state.
   */
  async markAllAsRead() {
    const unreadCount = this.notifications.filter(n => n.unread).length;
    
    // If no unread notifications, delete all instead
    if (unreadCount === 0) {
      return this.deleteAllNotifications();
    }

    try {
      // Optimistic update: mark all as read locally
      this.notifications.forEach(n => n.unread = false);
      this.renderNotifications();
      this.updateBadge();

      const response = await fetch('/api/notifications/mark-all-read', {
        method: 'PUT'
      });

      if (!response.ok) {
        throw new Error('Failed to mark all notifications as read');
      }
    } catch (error) {
      console.error('Error marking all notifications as read:', error);
      this.showError('Failed to mark all as read');
      // Reload on error to restore correct state
      await this.loadNotifications();
    }
  }

  /**
   * Delete all notifications.
   */
  async deleteAllNotifications() {
    try {
      // Optimistic update: clear all locally
      this.notifications = [];
      this.renderNotifications();
      this.updateBadge();

      const response = await fetch('/api/notifications/delete-all', {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete all notifications');
      }
    } catch (error) {
      console.error('Error deleting all notifications:', error);
      this.showError('Failed to delete all notifications');
      // Reload on error to restore correct state
      await this.loadNotifications();
    }
  }

  /**
   * Mark a notification as read (only if currently unread).
   */
  async markAsRead(id, isCurrentlyUnread) {
    // Only mark as read if it's currently unread
    if (!isCurrentlyUnread) {
      return;
    }

    try {
      // Optimistic update: mark as read locally
      const notification = this.notifications.find(n => n.id === id);
      if (notification) {
        notification.unread = false;
        this.renderNotifications();
        this.updateBadge();
      }

      const response = await fetch(`/api/notifications/${id}/read`, {
        method: 'PUT'
      });

      if (!response.ok) {
        throw new Error('Failed to mark notification as read');
      }
    } catch (error) {
      console.error('Error marking notification as read:', error);
      this.showError('Failed to update notification');
      // Reload on error to restore correct state
      await this.loadNotifications();
    }
  }

  /**
   * Toggle read/unread status of a notification.
   */
  async toggleRead(id, isCurrentlyUnread) {
    try {
      // Optimistic update: toggle locally
      const notification = this.notifications.find(n => n.id === id);
      if (notification) {
        notification.unread = !isCurrentlyUnread;
        this.renderNotifications();
        this.updateBadge();
      }

      const action = isCurrentlyUnread ? 'read' : 'unread';
      const response = await fetch(`/api/notifications/${id}/${action}`, {
        method: 'PUT'
      });

      if (!response.ok) {
        throw new Error(`Failed to mark notification as ${action}`);
      }
    } catch (error) {
      console.error('Error toggling notification:', error);
      this.showError('Failed to update notification');
      // Reload on error to restore correct state
      await this.loadNotifications();
    }
  }

  /**
   * Delete a notification.
   */
  async deleteNotification(id) {
    try {
      // Optimistic update: remove locally
      const index = this.notifications.findIndex(n => n.id === id);
      if (index !== -1) {
        this.notifications.splice(index, 1);
        this.renderNotifications();
        this.updateBadge();
      }

      const response = await fetch(`/api/notifications/${id}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete notification');
      }
    } catch (error) {
      console.error('Error deleting notification:', error);
      this.showError('Failed to delete notification');
      // Reload on error to restore correct state
      await this.loadNotifications();
    }
  }

  /**
   * Format a timestamp for display.
   */
  formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
      return 'Just now';
    } else if (diffMins < 60) {
      return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays < 7) {
      return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } else {
      return date.toLocaleDateString();
    }
  }

  /**
   * Escape HTML to prevent XSS.
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Show an error message.
   */
  showError(message) {
    this.list.innerHTML = `<div class="notifications-error">${this.escapeHtml(message)}</div>`;
  }
}

// Note: Notifications will be initialized by header.js after the header HTML is loaded
