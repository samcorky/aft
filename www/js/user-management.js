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
    this.showActiveOnlyToggle = document.getElementById('show-active-only');
    
    // Role assignment elements
    this.roleUsersContainer = document.getElementById('role-users-list');
    this.roleUsersLoading = document.getElementById('role-users-loading');
    this.roleUsersEmpty = document.getElementById('role-users-empty');
    this.roleUserSearchInput = document.getElementById('role-user-search');
    
    this.addRoleModal = document.getElementById('add-role-modal');
    this.addRoleUserName = document.getElementById('add-role-user-name');
    this.roleSelect = document.getElementById('role-select');
    this.boardSelect = document.getElementById('board-select');
    this.addRoleCancelBtn = document.getElementById('add-role-cancel-btn');
    this.addRoleOkBtn = document.getElementById('add-role-ok-btn');
    
    this.pendingCallback = null;
    this.allUsers = [];
    this.showActiveOnly = true;
    this.currentUserId = null;
    this.roleUsers = [];
    this.roles = [];
    this.boards = [];
  }

  async init() {
    // Check permission before loading page content
    const hasUserManage = typeof hasPermission === 'function' && hasPermission('user.manage');
    const hasUserRole = typeof hasPermission === 'function' && hasPermission('user.role');
    
    if (!hasUserManage && !hasUserRole) {
      // User doesn't have either permission - show access denied
      showAccessDenied('You need either "user.manage" or "user.role" permission to access this page.');
      return;
    }
    
    this.attachEventListeners();
    
    // Load data based on permissions
    const loadPromises = [];
    
    if (hasUserManage) {
      loadPromises.push(this.loadPendingUsers());
      loadPromises.push(this.loadActiveUsers());
    }
    
    if (hasUserRole) {
      loadPromises.push(this.loadRoles());
      loadPromises.push(this.loadBoards());
      loadPromises.push(this.loadRoleUsers());
    }
    
    await Promise.all(loadPromises);
    
    // Hide sections based on permissions
    if (!hasUserManage) {
      // Hide pending and active user sections if user can't manage users
      const pendingSection = document.querySelector('.settings-section:nth-child(1)');
      const activeSection = document.querySelector('.settings-section:nth-child(2)');
      if (pendingSection) pendingSection.style.display = 'none';
      if (activeSection) activeSection.style.display = 'none';
    }
    
    if (!hasUserRole) {
      // Hide role assignment section if user can't assign roles
      const roleSection = document.querySelector('.settings-section:nth-child(3)');
      if (roleSection) roleSection.style.display = 'none';
    }
  }

  attachEventListeners() {
    // Search functionality
    this.searchInput.addEventListener('input', () => {
      this.filterUsers(this.searchInput.value);
    });

    // Role user search functionality
    if (this.roleUserSearchInput) {
      this.roleUserSearchInput.addEventListener('input', () => {
        this.filterRoleUsers(this.roleUserSearchInput.value);
      });
    }

    // Active only toggle
    if (this.showActiveOnlyToggle) {
      this.showActiveOnlyToggle.addEventListener('change', (e) => {
        this.showActiveOnly = e.target.checked;
        this.filterUsers(this.searchInput.value);
      });
    }

    // Modal close handlers
    this.confirmCancelBtn.addEventListener('click', () => {
      this.closeConfirmModal();
    });

    // Add role modal handlers
    if (this.addRoleCancelBtn) {
      this.addRoleCancelBtn.addEventListener('click', () => {
        this.closeAddRoleModal();
      });
    }

    if (this.addRoleOkBtn) {
      this.addRoleOkBtn.addEventListener('click', () => {
        this.handleAddRole();
      });
    }

    // Click outside modal to close
    this.confirmModal.addEventListener('click', (e) => {
      if (e.target === this.confirmModal) {
        this.closeConfirmModal();
      }
    });

    if (this.addRoleModal) {
      this.addRoleModal.addEventListener('click', (e) => {
        if (e.target === this.addRoleModal) {
          this.closeAddRoleModal();
        }
      });
    }
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
          // Use filterUsers to respect the toggle state on initial load
          this.filterUsers('');
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
    
    let filtered = this.allUsers;
    
    // Filter by active status if toggle is on
    if (this.showActiveOnly) {
      filtered = filtered.filter(user => user.is_active);
    }
    
    // Filter by search term
    if (term !== '') {
      filtered = filtered.filter(user => {
        const displayName = (user.display_name || '').toLowerCase();
        const username = (user.username || '').toLowerCase();
        const email = (user.email || '').toLowerCase();
        
        return displayName.includes(term) || username.includes(term) || email.includes(term);
      });
    }

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

  // Role assignment methods
  async loadRoles() {
    try {
      const response = await fetch('/api/roles');
      
      if (response.status === 403) {
        console.warn('Permission denied loading roles');
        return;
      }
      
      const data = await response.json();

      if (data.success && data.roles) {
        this.roles = data.roles;
      }
    } catch (error) {
      console.error('Error loading roles:', error);
    }
  }

  async loadBoards() {
    try {
      const response = await fetch('/api/roles/boards');
      
      if (response.status === 403) {
        console.warn('Permission denied loading boards');
        return;
      }
      
      const data = await response.json();

      if (data.success && data.boards) {
        this.boards = data.boards;
      }
    } catch (error) {
      console.error('Error loading boards:', error);
    }
  }

  async loadRoleUsers() {
    if (!this.roleUsersContainer) {
      return; // Elements don't exist, skip loading
    }

    try {
      this.roleUsersLoading.style.display = 'block';
      this.roleUsersEmpty.style.display = 'none';
      this.roleUsersContainer.style.display = 'none';

      const response = await fetch('/api/roles/users');
      
      if (response.status === 403) {
        console.warn('Permission denied loading role users');
        this.roleUsersLoading.style.display = 'none';
        return;
      }
      
      const data = await response.json();

      if (data.success && data.users) {
        this.roleUsers = data.users;
        
        if (this.roleUsers.length === 0) {
          this.roleUsersLoading.style.display = 'none';
          this.roleUsersEmpty.style.display = 'block';
        } else {
          this.renderRoleUsers(this.roleUsers);
          this.roleUsersLoading.style.display = 'none';
          this.roleUsersContainer.style.display = 'block';
        }
      } else {
        throw new Error(data.message || 'Failed to load users for role assignment');
      }
    } catch (error) {
      console.error('Error loading role users:', error);
      this.showStatus('Error loading users for role assignment: ' + error.message, 'error');
      this.roleUsersLoading.style.display = 'none';
    }
  }

  renderRoleUsers(users) {
    this.roleUsersContainer.innerHTML = '';

    users.forEach(user => {
      const userCard = this.createRoleUserCard(user);
      this.roleUsersContainer.appendChild(userCard);
    });
  }

  createRoleUserCard(user) {
    const card = document.createElement('div');
    card.className = 'user-card';
    card.dataset.userId = user.id;

    const rolesHtml = user.roles.length > 0
      ? user.roles.map(role => `
          <div class="user-role-item">
            <div class="role-info">
              <span class="role-name-badge">${this.escapeHtml(role.role_name)}</span>
              <span class="role-scope">${role.board_name ? `(Board: ${this.escapeHtml(role.board_name)})` : '(Global)'}</span>
            </div>
            <button class="remove-role-btn" data-user-id="${user.id}" data-role-id="${role.role_id}" data-board-id="${role.board_id || ''}">
              Remove
            </button>
          </div>
        `).join('')
      : '<div class="no-roles-message">No roles assigned</div>';

    card.innerHTML = `
      <div class="user-header">
        <div class="user-info">
          <div class="user-name">${this.escapeHtml(user.username)}</div>
          <div class="user-email">${this.escapeHtml(user.email)}</div>
        </div>
        <div class="user-actions">
          <button class="btn-icon" title="Add Role" data-action="add-role" data-user-id="${user.id}" data-username="${this.escapeHtml(user.username)}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
        </div>
      </div>
      <div class="user-roles">
        ${rolesHtml}
      </div>
    `;

    // Attach event listeners
    const addRoleBtn = card.querySelector('[data-action="add-role"]');
    if (addRoleBtn) {
      addRoleBtn.addEventListener('click', (e) => {
        const userId = parseInt(e.currentTarget.dataset.userId);
        const username = e.currentTarget.dataset.username;
        this.openAddRoleModal(userId, username);
      });
    }

    const removeRoleBtns = card.querySelectorAll('.remove-role-btn');
    removeRoleBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const userId = parseInt(e.currentTarget.dataset.userId);
        const roleId = parseInt(e.currentTarget.dataset.roleId);
        const boardId = e.currentTarget.dataset.boardId ? parseInt(e.currentTarget.dataset.boardId) : null;
        const user = this.roleUsers.find(u => u.id === userId);
        const role = user?.roles.find(r => r.role_id === roleId && (r.board_id || null) === boardId);
        
        if (user && role) {
          const scope = role.board_name ? ` on board "${role.board_name}"` : ' (global)';
          this.confirmRemoveRole(userId, roleId, boardId, `${user.username}: ${role.role_name}${scope}`);
        }
      });
    });

    return card;
  }

  filterRoleUsers(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    
    if (!term) {
      this.renderRoleUsers(this.roleUsers);
      return;
    }

    const filtered = this.roleUsers.filter(user => 
      user.username.toLowerCase().includes(term) ||
      user.email.toLowerCase().includes(term)
    );

    if (filtered.length === 0) {
      this.roleUsersContainer.innerHTML = '<div class="empty-message">No users match your search.</div>';
      this.roleUsersContainer.style.display = 'block';
    } else {
      this.renderRoleUsers(filtered);
    }
  }

  openAddRoleModal(userId, username) {
    this.currentUserId = userId;
    this.addRoleUserName.textContent = `Assign role to: ${username}`;
    
    // Populate roles dropdown
    this.roleSelect.innerHTML = '<option value="">Select a role...</option>';
    this.roles.forEach(role => {
      const option = document.createElement('option');
      option.value = role.id;
      option.textContent = role.name;
      this.roleSelect.appendChild(option);
    });

    // Populate boards dropdown
    this.boardSelect.innerHTML = '<option value="">Global (All Boards)</option>';
    this.boards.forEach(board => {
      const option = document.createElement('option');
      option.value = board.id;
      option.textContent = board.name;
      this.boardSelect.appendChild(option);
    });

    this.addRoleModal.style.display = 'flex';
  }

  closeAddRoleModal() {
    this.addRoleModal.style.display = 'none';
    this.currentUserId = null;
    this.roleSelect.value = '';
    this.boardSelect.value = '';
  }

  async handleAddRole() {
    const roleId = parseInt(this.roleSelect.value);
    const boardId = this.boardSelect.value ? parseInt(this.boardSelect.value) : null;

    if (!roleId) {
      this.showStatus('Please select a role', 'error');
      return;
    }

    try {
      const response = await fetch('/api/roles/assign', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: this.currentUserId,
          role_id: roleId,
          board_id: boardId
        })
      });

      const data = await response.json();

      if (data.success) {
        this.showStatus(data.message || 'Role assigned successfully', 'success');
        this.closeAddRoleModal();
        await this.loadRoleUsers();
      } else {
        throw new Error(data.message || 'Failed to assign role');
      }
    } catch (error) {
      console.error('Error assigning role:', error);
      this.showStatus('Error: ' + error.message, 'error');
    }
  }

  confirmRemoveRole(userId, roleId, boardId, roleDescription) {
    this.confirmModalTitle.textContent = 'Confirm Role Removal';
    this.confirmModalMessage.textContent = `Are you sure you want to remove the role: ${roleDescription}?`;
    
    // Store callback locally before setting up OK button
    const callback = async () => {
      await this.removeRole(userId, roleId, boardId);
    };
    
    this.pendingCallback = callback;

    // Remove old listener and add new one
    const newOkBtn = this.confirmOkBtn.cloneNode(true);
    this.confirmOkBtn.parentNode.replaceChild(newOkBtn, this.confirmOkBtn);
    this.confirmOkBtn = newOkBtn;
    
    this.confirmOkBtn.addEventListener('click', async () => {
      const cb = this.pendingCallback;
      this.closeConfirmModal();
      if (cb) {
        try {
          await cb();
        } catch (error) {
          console.error('Error in confirm callback:', error);
          this.showStatus('Error: ' + error.message, 'error');
        }
      }
    });
    
    this.confirmModal.style.display = 'flex';
  }

  async removeRole(userId, roleId, boardId) {
    try {
      const response = await fetch('/api/roles/remove', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          role_id: roleId,
          board_id: boardId
        })
      });

      const data = await response.json();

      if (data.success) {
        this.showStatus(data.message || 'Role removed successfully', 'success');
        await this.loadRoleUsers();
      } else {
        throw new Error(data.message || 'Failed to remove role');
      }
    } catch (error) {
      console.error('Error removing role:', error);
      this.showStatus('Error: ' + error.message, 'error');
    }
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
