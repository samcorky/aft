// User Management functionality
class UserManagement {
  constructor() {
    this.pendingUsersContainer = document.getElementById('pending-users-list');
    this.pendingUsersLoading = document.getElementById('pending-users-loading');
    this.pendingUsersEmpty = document.getElementById('pending-users-empty');
    
    this.activeUsersContainer = document.getElementById('active-users-list');
    this.activeUsersLoading = document.getElementById('active-users-loading');
    this.activeUsersEmpty = document.getElementById('active-users-empty');
    
    this.searchInput = document.getElementById('user-search');
    this.statusMessage = document.getElementById('status-message');
    
    this.confirmModal = document.getElementById('confirm-modal');
    this.confirmModalTitle = document.getElementById('confirm-modal-title');
    this.confirmModalMessage = document.getElementById('confirm-modal-message');
    this.confirmCancelBtn = document.getElementById('confirm-cancel-btn');
    this.confirmOkBtn = document.getElementById('confirm-ok-btn');
    
    this.pendingCallback = null;
    this.allUsers = [];
  }

  async init() {
    // Check permission before loading page content
    if (typeof hasPermission === 'function' && !hasPermission('user.manage')) {
      // User doesn't have permission - show access denied
      showAccessDenied('You need the "user.manage" permission to access this page.');
      return;
    }
    
    this.attachEventListeners();
    await this.loadPendingUsers();
    await this.loadActiveUsers();
  }

  attachEventListeners() {
    // Search functionality
    this.searchInput.addEventListener('input', () => {
      this.filterUsers(this.searchInput.value);
    });

    // Modal close handlers
    this.confirmCancelBtn.addEventListener('click', () => {
      this.closeConfirmModal();
    });

    // Click outside modal to close
    this.confirmModal.addEventListener('click', (e) => {
      if (e.target === this.confirmModal) {
        this.closeConfirmModal();
      }
    });
  }

  async loadPendingUsers() {
    try {
      this.pendingUsersLoading.style.display = 'block';
      this.pendingUsersEmpty.style.display = 'none';
      this.pendingUsersContainer.style.display = 'none';

      const response = await fetch('/api/users/pending');
      
      // Check for permission errors
      if (response.status === 403) {
        showAccessDenied('You need the "user.manage" permission to access pending user data.');
        return;
      }
      
      const data = await response.json();

      if (data.success && data.users) {
        if (data.users.length === 0) {
          this.pendingUsersLoading.style.display = 'none';
          this.pendingUsersEmpty.style.display = 'block';
        } else {
          this.renderPendingUsers(data.users);
          this.pendingUsersLoading.style.display = 'none';
          this.pendingUsersContainer.style.display = 'block';
        }
      } else {
        throw new Error(data.message || 'Failed to load pending users');
      }
    } catch (error) {
      console.error('Error loading pending users:', error);
      this.showStatus('Error loading pending users: ' + error.message, 'error');
      this.pendingUsersLoading.style.display = 'none';
    }
  }

  async loadActiveUsers() {
    try {
      this.activeUsersLoading.style.display = 'block';
      this.activeUsersEmpty.style.display = 'none';
      this.activeUsersContainer.style.display = 'none';

      const response = await fetch('/api/users?status=approved');
      
      // Check for permission errors
      if (response.status === 403) {
        showAccessDenied('You need the "user.manage" permission to access active user data.');
        return;
      }
      
      const data = await response.json();

      if (data.success && data.users) {
        this.allUsers = data.users;
        
        if (this.allUsers.length === 0) {
          this.activeUsersLoading.style.display = 'none';
          this.activeUsersEmpty.style.display = 'block';
        } else {
          this.renderActiveUsers(this.allUsers);
          this.activeUsersLoading.style.display = 'none';
          this.activeUsersContainer.style.display = 'block';
        }
      } else {
        throw new Error(data.message || 'Failed to load users');
      }
    } catch (error) {
      console.error('Error loading users:', error);
      this.showStatus('Error loading users: ' + error.message, 'error');
      this.activeUsersLoading.style.display = 'none';
    }
  }

  renderPendingUsers(users) {
    this.pendingUsersContainer.innerHTML = '';

    users.forEach(user => {
      const userCard = this.createPendingUserCard(user);
      this.pendingUsersContainer.appendChild(userCard);
    });
  }

  createPendingUserCard(user) {
    const card = document.createElement('div');
    card.className = 'user-card pending-user-card';
    card.dataset.userId = user.id;

    const displayName = user.display_name || user.username || user.email;
    const createdDate = user.created_at ? new Date(user.created_at).toLocaleDateString() : 'Unknown';

    card.innerHTML = `
      <div class="user-info">
        <div class="user-avatar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
        </div>
        <div class="user-details">
          <div class="user-name">${this.escapeHtml(displayName)}</div>
          <div class="user-email">${this.escapeHtml(user.email)}</div>
          ${user.username ? `<div class="user-meta">Username: ${this.escapeHtml(user.username)}</div>` : ''}
          <div class="user-meta">Registered: ${createdDate}</div>
        </div>
      </div>
      <div class="user-actions">
        <button class="btn btn-primary btn-sm" data-action="approve" data-user-id="${user.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          Approve
        </button>
        <button class="btn btn-danger btn-sm" data-action="reject" data-user-id="${user.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
          Reject
        </button>
      </div>
    `;

    // Attach event listeners to buttons
    const approveBtn = card.querySelector('[data-action="approve"]');
    const rejectBtn = card.querySelector('[data-action="reject"]');

    approveBtn.addEventListener('click', () => this.handleApprove(user));
    rejectBtn.addEventListener('click', () => this.handleReject(user));

    return card;
  }

  renderActiveUsers(users) {
    this.activeUsersContainer.innerHTML = '';

    if (users.length === 0) {
      this.activeUsersContainer.style.display = 'none';
      this.activeUsersEmpty.style.display = 'block';
      return;
    }

    this.activeUsersContainer.style.display = 'block';
    this.activeUsersEmpty.style.display = 'none';

    users.forEach(user => {
      const userCard = this.createActiveUserCard(user);
      this.activeUsersContainer.appendChild(userCard);
    });
  }

  createActiveUserCard(user) {
    const card = document.createElement('div');
    card.className = 'user-card active-user-card';
    if (!user.is_active) {
      card.classList.add('user-deactivated');
    }
    card.dataset.userId = user.id;

    const displayName = user.display_name || user.username || user.email;
    const createdDate = user.created_at ? new Date(user.created_at).toLocaleDateString() : 'Unknown';
    const lastLogin = user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : 'Never';
    
    const roles = user.roles && user.roles.length > 0
      ? user.roles.map(r => `<span class="role-badge">${this.escapeHtml(r.name)}</span>`).join('')
      : '<span class="role-badge role-badge-none">No roles</span>';

    const statusBadge = user.is_active
      ? '<span class="status-badge status-active">Active</span>'
      : '<span class="status-badge status-inactive">Inactive</span>';

    card.innerHTML = `
      <div class="user-info">
        <div class="user-avatar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
        </div>
        <div class="user-details">
          <div class="user-name">
            ${this.escapeHtml(displayName)}
            ${statusBadge}
          </div>
          <div class="user-email">${this.escapeHtml(user.email)}</div>
          ${user.username ? `<div class="user-meta">Username: ${this.escapeHtml(user.username)}</div>` : ''}
          <div class="user-meta">Registered: ${createdDate} • Last login: ${lastLogin}</div>
          <div class="user-roles">
            ${roles}
          </div>
        </div>
      </div>
      <div class="user-actions">
        ${user.is_active
          ? `<button class="btn btn-secondary btn-sm" data-action="deactivate" data-user-id="${user.id}" ${window.currentUser && user.id === window.currentUser.id ? 'disabled title="You cannot deactivate your own account"' : ''}>Deactivate</button>`
          : `<button class="btn btn-primary btn-sm" data-action="activate" data-user-id="${user.id}">Activate</button>`
        }
      </div>
    `;

    // Attach event listeners to buttons
    if (user.is_active) {
      const deactivateBtn = card.querySelector('[data-action="deactivate"]');
      // Only add event listener if it's not the current user's own account
      if (!window.currentUser || user.id !== window.currentUser.id) {
        deactivateBtn.addEventListener('click', () => this.handleDeactivate(user));
      }
    } else {
      const activateBtn = card.querySelector('[data-action="activate"]');
      activateBtn.addEventListener('click', () => this.handleActivate(user));
    }

    return card;
  }

  filterUsers(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    
    if (term === '') {
      this.renderActiveUsers(this.allUsers);
      return;
    }

    const filtered = this.allUsers.filter(user => {
      const displayName = (user.display_name || '').toLowerCase();
      const username = (user.username || '').toLowerCase();
      const email = (user.email || '').toLowerCase();
      
      return displayName.includes(term) || username.includes(term) || email.includes(term);
    });

    this.renderActiveUsers(filtered);
  }

  async handleApprove(user) {
    const displayName = user.display_name || user.username || user.email;
    
    this.showConfirmModal(
      'Approve User',
      `Are you sure you want to approve ${displayName}? They will be able to access the system.`,
      async () => {
        console.log('Approving user:', user.id, user.email);
        try {
          const url = `/api/users/${user.id}/approve`;
          console.log('Making POST request to:', url);
          
          const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin'  // Ensure cookies are sent
          });

          console.log('Response status:', response.status);
          console.log('Response headers:', Object.fromEntries(response.headers.entries()));

          const data = await response.json();
          console.log('Response data:', data);

          if (response.ok && data.success) {
            this.showStatus('User approved successfully', 'success');
            await this.loadPendingUsers();
            await this.loadActiveUsers();
          } else {
            // Show specific error message from server
            const errorMsg = data.message || `Failed to approve user (Status: ${response.status})`;
            this.showStatus('Error: ' + errorMsg, 'error');
            console.error('Approve user failed:', { status: response.status, data });
          }
        } catch (error) {
          console.error('Error approving user:', error);
          this.showStatus('Error approving user: ' + error.message, 'error');
        }
      }
    );
  }

  async handleReject(user) {
    const displayName = user.display_name || user.username || user.email;
    
    this.showConfirmModal(
      'Reject User',
      `Are you sure you want to reject ${displayName}? This will permanently delete their account.`,
      async () => {
        try {
          const response = await fetch(`/api/users/${user.id}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          });

          const data = await response.json();

          if (data.success) {
            this.showStatus('User rejected and removed', 'success');
            await this.loadPendingUsers();
          } else {
            throw new Error(data.message || 'Failed to reject user');
          }
        } catch (error) {
          console.error('Error rejecting user:', error);
          this.showStatus('Error rejecting user: ' + error.message, 'error');
        }
      }
    );
  }

  async handleDeactivate(user) {
    const displayName = user.display_name || user.username || user.email;
    
    this.showConfirmModal(
      'Deactivate User',
      `Are you sure you want to deactivate ${displayName}? They will not be able to log in.`,
      async () => {
        try {
          const response = await fetch(`/api/users/${user.id}/deactivate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          });

          const data = await response.json();

          if (data.success) {
            this.showStatus('User deactivated successfully', 'success');
            await this.loadActiveUsers();
          } else {
            throw new Error(data.message || 'Failed to deactivate user');
          }
        } catch (error) {
          console.error('Error deactivating user:', error);
          this.showStatus('Error deactivating user: ' + error.message, 'error');
        }
      }
    );
  }

  async handleActivate(user) {
    const displayName = user.display_name || user.username || user.email;
    
    this.showConfirmModal(
      'Activate User',
      `Are you sure you want to activate ${displayName}? They will be able to log in again.`,
      async () => {
        try {
          const response = await fetch(`/api/users/${user.id}/activate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          });

          const data = await response.json();

          if (data.success) {
            this.showStatus('User activated successfully', 'success');
            await this.loadActiveUsers();
          } else {
            throw new Error(data.message || 'Failed to activate user');
          }
        } catch (error) {
          console.error('Error activating user:', error);
          this.showStatus('Error activating user: ' + error.message, 'error');
        }
      }
    );
  }

  showConfirmModal(title, message, callback) {
    console.log('showConfirmModal called', { title, hasCallback: !!callback });
    this.confirmModalTitle.textContent = title;
    this.confirmModalMessage.textContent = message;
    this.pendingCallback = callback;
    
    console.log('Stored callback:', !!this.pendingCallback);
    
    // Remove old listener and add new one
    const newOkBtn = this.confirmOkBtn.cloneNode(true);
    this.confirmOkBtn.parentNode.replaceChild(newOkBtn, this.confirmOkBtn);
    this.confirmOkBtn = newOkBtn;
    
    console.log('Added new event listener to OK button');
    
    this.confirmOkBtn.addEventListener('click', async (e) => {
      console.log('OK button clicked!');
      console.log('pendingCallback exists?', !!this.pendingCallback);
      
      // Store callback locally before closing modal (which clears it)
      const callback = this.pendingCallback;
      
      this.closeConfirmModal();
      
      if (callback) {
        console.log('Executing callback...');
        // Await the callback if it's async
        try {
          await callback();
          console.log('Callback executed successfully');
        } catch (error) {
          console.error('Error in modal callback:', error);
          this.showStatus('Error: ' + error.message, 'error');
        }
      } else {
        console.log('No pending callback to execute');
      }
    });
    
    this.confirmModal.style.display = 'flex';
    console.log('Modal displayed');
  }

  closeConfirmModal() {
    this.confirmModal.style.display = 'none';
    this.pendingCallback = null;
  }

  showStatus(message, type = 'info') {
    this.statusMessage.textContent = message;
    this.statusMessage.className = 'settings-status ' + type;
    
    setTimeout(() => {
      this.statusMessage.textContent = '';
      this.statusMessage.className = 'settings-status';
    }, 5000);
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', async () => {
  // Wait for header to load and user info to be available
  // The header.js sets window.userDataReady flag when done
  let attempts = 0;
  while (!window.userDataReady && attempts < 50) {
    await new Promise(resolve => setTimeout(resolve, 100)); // Wait 100ms
    attempts++;
  }
  
  const userManagement = new UserManagement();
  await userManagement.init();
});
