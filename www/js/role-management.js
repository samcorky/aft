// Role Management functionality
class RoleManagement {
  constructor() {
    this.rolesContainer = document.getElementById('roles-list');
    this.rolesLoading = document.getElementById('roles-loading');
    
    this.usersContainer = document.getElementById('users-list');
    this.usersLoading = document.getElementById('users-loading');
    this.usersEmpty = document.getElementById('users-empty');
    
    this.searchInput = document.getElementById('user-search');
    this.statusMessage = document.getElementById('status-message');
    
    this.addRoleModal = document.getElementById('add-role-modal');
    this.addRoleUserName = document.getElementById('add-role-user-name');
    this.roleSelect = document.getElementById('role-select');
    this.boardSelect = document.getElementById('board-select');
    this.addRoleCancelBtn = document.getElementById('add-role-cancel-btn');
    this.addRoleOkBtn = document.getElementById('add-role-ok-btn');
    
    this.confirmModal = document.getElementById('confirm-modal');
    this.confirmModalTitle = document.getElementById('confirm-modal-title');
    this.confirmModalMessage = document.getElementById('confirm-modal-message');
    this.confirmCancelBtn = document.getElementById('confirm-cancel-btn');
    this.confirmOkBtn = document.getElementById('confirm-ok-btn');
    
    // Role editor modal
    this.roleEditorModal = document.getElementById('role-editor-modal');
    this.roleEditorTitle = document.getElementById('role-editor-modal-title');
    this.roleNameInput = document.getElementById('role-name-input');
    this.roleDescriptionInput = document.getElementById('role-description-input');
    this.permissionsGrid = document.getElementById('permissions-grid');
    this.permissionsSearchInput = document.getElementById('permissions-search-input');
    this.roleEditorError = document.getElementById('role-editor-error');
    this.roleEditorCancelBtn = document.getElementById('role-editor-cancel-btn');
    this.roleEditorSaveBtn = document.getElementById('role-editor-save-btn');
    
    // Copy role modal
    this.copyRoleModal = document.getElementById('copy-role-modal');
    this.copyRoleSourceName = document.getElementById('copy-role-source-name');
    this.copyRoleNameInput = document.getElementById('copy-role-name-input');
    this.copyRoleError = document.getElementById('copy-role-error');
    this.copyRoleCancelBtn = document.getElementById('copy-role-cancel-btn');
    this.copyRoleOkBtn = document.getElementById('copy-role-ok-btn');
    
    // Permission mappings
    this.mappingsLoading = document.getElementById('mappings-loading');
    this.mappingsError = document.getElementById('mappings-error');
    this.mappingsByPermission = document.getElementById('mappings-by-permission');
    this.mappingsByEndpoint = document.getElementById('mappings-by-endpoint');
    this.toggleMappingViewBtn = document.getElementById('toggle-mapping-view-btn');
    this.viewToggleText = document.getElementById('view-toggle-text');
    
    this.confirmCallback = null;
    this.currentUserId = null;
    this.currentRoleId = null;
    this.editMode = false;
    this.allUsers = [];
    this.roles = [];
    this.boards = [];
    this.permissions = {};
    this.allPermissions = [];
    this.currentMappingView = 'permission'; // 'permission' or 'endpoint'
    this.permissionMappings = null;
  }

  async init() {
    // Check permissions before loading page content
    const hasRoleManage = typeof hasPermission === 'function' && hasPermission('role.manage');
    const hasUserRole = typeof hasPermission === 'function' && hasPermission('user.role');
    
    if (!hasRoleManage && !hasUserRole) {
      // User doesn't have either permission - show access denied
      showAccessDenied('You need either "role.manage" or "user.role" permission to access this page.');
      return;
    }
    
    this.attachEventListeners();
    
    // Load data based on permissions
    const loadPromises = [];
    
    if (hasRoleManage || hasUserRole) {
      loadPromises.push(this.loadPermissions());
      loadPromises.push(this.loadRoles());
      loadPromises.push(this.loadBoards());
      loadPromises.push(this.loadPermissionMappings());
    }
    
    if (hasUserRole) {
      loadPromises.push(this.loadUsers());
    }
    
    await Promise.all(loadPromises);
    
    // Hide sections based on permissions
    if (!hasRoleManage) {
      // Hide create role button if user can't manage roles
      const createRoleBtn = document.getElementById('create-role-btn');
      if (createRoleBtn) {
        createRoleBtn.style.display = 'none';
      }
    }
    
    if (!hasUserRole) {
      // Hide user role assignment section if user can't assign roles
      const userSection = document.querySelector('.settings-section:nth-child(2)');
      if (userSection) {
        userSection.style.display = 'none';
      }
    }
  }

  attachEventListeners() {
    // Search functionality
    this.searchInput.addEventListener('input', () => {
      this.filterUsers(this.searchInput.value);
    });

    // Create role button
    const createRoleBtn = document.getElementById('create-role-btn');
    if (createRoleBtn) {
      createRoleBtn.addEventListener('click', () => {
        this.openRoleEditorModal();
      });
    }

    // Toggle mapping view button
    if (this.toggleMappingViewBtn) {
      this.toggleMappingViewBtn.addEventListener('click', () => {
        this.toggleMappingView();
      });
    }

    // Add role modal handlers
    this.addRoleCancelBtn.addEventListener('click', () => {
      this.closeAddRoleModal();
    });

    this.addRoleOkBtn.addEventListener('click', () => {
      this.handleAddRole();
    });

    // Role editor modal handlers
    this.roleEditorCancelBtn.addEventListener('click', () => {
      this.closeRoleEditorModal();
    });

    this.roleEditorSaveBtn.addEventListener('click', () => {
      this.handleSaveRole();
    });

    // Copy role modal handlers
    this.copyRoleCancelBtn.addEventListener('click', () => {
      this.closeCopyRoleModal();
    });

    this.copyRoleOkBtn.addEventListener('click', () => {
      this.handleCopyRole();
    });

    // Permissions search
    this.permissionsSearchInput.addEventListener('input', () => {
      this.filterPermissions(this.permissionsSearchInput.value);
    });

    // Confirmation modal handlers
    this.confirmCancelBtn.addEventListener('click', () => {
      this.closeConfirmModal();
    });

    // Click outside modal to close
    this.addRoleModal.addEventListener('click', (e) => {
      if (e.target === this.addRoleModal) {
        this.closeAddRoleModal();
      }
    });

    this.confirmModal.addEventListener('click', (e) => {
      if (e.target === this.confirmModal) {
        this.closeConfirmModal();
      }
    });

    this.roleEditorModal.addEventListener('click', (e) => {
      if (e.target === this.roleEditorModal) {
        this.closeRoleEditorModal();
      }
    });

    this.copyRoleModal.addEventListener('click', (e) => {
      if (e.target === this.copyRoleModal) {
        this.closeCopyRoleModal();
      }
    });
  }

  async loadPermissions() {
    try {
      const response = await fetch('/api/roles/permissions');
      
      if (response.status === 403) {
        return;
      }
      
      const data = await response.json();

      if (data.success && data.permissions) {
        this.permissions = data.permissions;
        this.allPermissions = Object.keys(data.permissions).sort();
      }
    } catch (error) {
      console.error('Error loading permissions:', error);
    }
  }

  async loadRoles() {
    try {
      this.rolesLoading.style.display = 'block';
      this.rolesContainer.style.display = 'none';

      const response = await fetch('/api/roles');
      
      // Check for permission errors
      if (response.status === 403) {
        console.warn('Permission denied loading roles');
        this.rolesLoading.style.display = 'none';
        return;
      }
      
      const data = await response.json();

      if (data.success && data.roles) {
        this.roles = data.roles;
        this.renderRoles(data.roles);
        this.rolesLoading.style.display = 'none';
        this.rolesContainer.style.display = 'block';
      } else {
        throw new Error(data.message || 'Failed to load roles');
      }
    } catch (error) {
      console.error('Error loading roles:', error);
      this.showStatus('Error loading roles: ' + error.message, 'error');
      this.rolesLoading.style.display = 'none';
    }
  }

  async loadBoards() {
    try {
      const response = await fetch('/api/roles/boards');
      
      // Check for permission errors
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

  async loadUsers() {
    try {
      this.usersLoading.style.display = 'block';
      this.usersEmpty.style.display = 'none';
      this.usersContainer.style.display = 'none';

      const response = await fetch('/api/roles/users');
      
      // Check for permission errors
      if (response.status === 403) {
        console.warn('Permission denied loading users');
        this.usersLoading.style.display = 'none';
        return;
      }
      
      const data = await response.json();

      if (data.success && data.users) {
        this.allUsers = data.users;
        
        if (this.allUsers.length === 0) {
          this.usersLoading.style.display = 'none';
          this.usersEmpty.style.display = 'block';
        } else {
          this.renderUsers(this.allUsers);
          this.usersLoading.style.display = 'none';
          this.usersContainer.style.display = 'block';
        }
      } else {
        throw new Error(data.message || 'Failed to load users');
      }
    } catch (error) {
      console.error('Error loading users:', error);
      this.showStatus('Error loading users: ' + error.message, 'error');
      this.usersLoading.style.display = 'none';
    }
  }

  renderRoles(roles) {
    this.rolesContainer.innerHTML = '';

    roles.forEach(role => {
      const roleCard = this.createRoleCard(role);
      this.rolesContainer.appendChild(roleCard);
    });
  }

  createRoleCard(role) {
    const card = document.createElement('div');
    card.className = 'role-card';
    card.dataset.roleId = role.id;

    const permissionsPreview = role.permissions.slice(0, 5);
    const hasMore = role.permissions.length > 5;
    const permissionsHtml = permissionsPreview.map(p => 
      `<span class="permission-tag">${this.escapeHtml(p)}</span>`
    ).join('');

    // Check if user has role.manage permission
    const hasRoleManage = typeof hasPermission === 'function' && hasPermission('role.manage');

    // Action buttons - Edit and Delete only for non-system roles AND if user has role.manage
    // Copy is available for all roles if user has role.manage
    const actionsHtml = hasRoleManage ? `
      <div class="role-actions">
        ${!role.is_system_role ? `
          <button class="role-action-btn" data-action="edit" data-role-id="${role.id}" title="Edit role">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
            Edit
          </button>
        ` : ''}
        <button class="role-action-btn" data-action="copy" data-role-id="${role.id}" title="Copy role">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          Copy
        </button>
        ${!role.is_system_role ? `
          <button class="role-action-btn danger" data-action="delete" data-role-id="${role.id}" title="Delete role">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            Delete
          </button>
        ` : ''}
      </div>
    ` : '';

    card.innerHTML = `
      <div class="role-header">
        <div>
          <div class="role-name">${this.escapeHtml(role.name)}</div>
          ${role.is_system_role ? '<span class="role-badge">System</span>' : ''}
        </div>
        ${actionsHtml}
      </div>
      ${role.description ? `<div class="role-description">${this.escapeHtml(role.description)}</div>` : ''}
      <div>
        <strong>Permissions (${role.permissions.length}):</strong>
        <div class="role-permissions" data-role-id="${role.id}">
          ${permissionsHtml}
          ${hasMore ? `<span class="permission-tag">+${role.permissions.length - 5} more</span>` : ''}
        </div>
        ${hasMore ? `<a href="javascript:void(0)" class="permission-toggle" data-role-id="${role.id}">Show all permissions</a>` : ''}
      </div>
    `;

    // Add click handler for showing all permissions
    const toggleLink = card.querySelector('.permission-toggle');
    if (toggleLink) {
      toggleLink.addEventListener('click', () => {
        this.togglePermissions(role.id, role.permissions);
      });
    }

    // Add action button handlers
    const editBtn = card.querySelector('[data-action="edit"]');
    if (editBtn) {
      editBtn.addEventListener('click', () => {
        this.openRoleEditorModal(role);
      });
    }

    const copyBtn = card.querySelector('[data-action="copy"]');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        this.openCopyRoleModal(role);
      });
    }

    const deleteBtn = card.querySelector('[data-action="delete"]');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', () => {
        this.confirmDeleteRole(role);
      });
    }

    return card;
  }

  togglePermissions(roleId, allPermissions) {
    const permissionsDiv = document.querySelector(`.role-permissions[data-role-id="${roleId}"]`);
    const toggleLink = document.querySelector(`.permission-toggle[data-role-id="${roleId}"]`);
    
    if (!permissionsDiv || !toggleLink) return;

    const isExpanded = permissionsDiv.dataset.expanded === 'true';

    if (isExpanded) {
      // Collapse - show only first 5
      const permissionsPreview = allPermissions.slice(0, 5);
      const permissionsHtml = permissionsPreview.map(p => 
        `<span class="permission-tag">${this.escapeHtml(p)}</span>`
      ).join('') + `<span class="permission-tag">+${allPermissions.length - 5} more</span>`;
      
      permissionsDiv.innerHTML = permissionsHtml;
      permissionsDiv.dataset.expanded = 'false';
      toggleLink.textContent = 'Show all permissions';
    } else {
      // Expand - show all
      const permissionsHtml = allPermissions.map(p => 
        `<span class="permission-tag">${this.escapeHtml(p)}</span>`
      ).join('');
      
      permissionsDiv.innerHTML = permissionsHtml;
      permissionsDiv.dataset.expanded = 'true';
      toggleLink.textContent = 'Show less';
    }
  }

  renderUsers(users) {
    this.usersContainer.innerHTML = '';

    users.forEach(user => {
      const userCard = this.createUserCard(user);
      this.usersContainer.appendChild(userCard);
    });
  }

  createUserCard(user) {
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
        const user = this.allUsers.find(u => u.id === userId);
        const role = user?.roles.find(r => r.role_id === roleId && (r.board_id || null) === boardId);
        
        if (user && role) {
          const scope = role.board_name ? ` on board "${role.board_name}"` : ' (global)';
          this.confirmRemoveRole(userId, roleId, boardId, `${user.username}: ${role.role_name}${scope}`);
        }
      });
    });

    return card;
  }

  filterUsers(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    
    if (!term) {
      this.renderUsers(this.allUsers);
      return;
    }

    const filtered = this.allUsers.filter(user => 
      user.username.toLowerCase().includes(term) ||
      user.email.toLowerCase().includes(term)
    );

    if (filtered.length === 0) {
      this.usersContainer.innerHTML = '<div class="empty-message">No users match your search.</div>';
      this.usersContainer.style.display = 'block';
    } else {
      this.renderUsers(filtered);
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
        await this.loadUsers();
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
    
    this.confirmOkBtn.onclick = async () => {
      await this.removeRole(userId, roleId, boardId);
      this.closeConfirmModal();
    };
    
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
        await this.loadUsers();
      } else {
        throw new Error(data.message || 'Failed to remove role');
      }
    } catch (error) {
      console.error('Error removing role:', error);
      this.showStatus('Error: ' + error.message, 'error');
    }
  }

  closeConfirmModal() {
    this.confirmModal.style.display = 'none';
    this.confirmOkBtn.onclick = null;
  }

  // Role Editor Modal methods
  openRoleEditorModal(role = null) {
    this.editMode = !!role;
    this.currentRoleId = role ? role.id : null;
    
    if (this.editMode) {
      this.roleEditorTitle.textContent = 'Edit Role';
      this.roleNameInput.value = role.name;
      this.roleDescriptionInput.value = role.description || '';
      this.roleEditorSaveBtn.textContent = 'Update Role';
    } else {
      this.roleEditorTitle.textContent = 'Create Role';
      this.roleNameInput.value = '';
      this.roleDescriptionInput.value = '';
      this.roleEditorSaveBtn.textContent = 'Create Role';
    }
    
    this.roleEditorError.style.display = 'none';
    this.permissionsSearchInput.value = '';
    this.renderPermissionsGrid(role ? role.permissions : []);
    
    this.roleEditorModal.style.display = 'flex';
  }

  closeRoleEditorModal() {
    this.roleEditorModal.style.display = 'none';
    this.currentRoleId = null;
    this.editMode = false;
  }

  renderPermissionsGrid(selectedPermissions = []) {
    this.permissionsGrid.innerHTML = '';
    
    this.allPermissions.forEach(permKey => {
      const permDesc = this.permissions[permKey];
      const isChecked = selectedPermissions.includes(permKey);
      
      const item = document.createElement('div');
      item.className = 'permission-checkbox-item';
      item.dataset.permission = permKey;
      
      item.innerHTML = `
        <input type="checkbox" id="perm-${permKey}" ${isChecked ? 'checked' : ''} />
        <label for="perm-${permKey}" class="permission-checkbox-label">
          <div class="permission-checkbox-name">${this.escapeHtml(permKey)}</div>
          <div class="permission-checkbox-desc">${this.escapeHtml(permDesc)}</div>
        </label>
      `;
      
      // Make the whole item clickable
      item.addEventListener('click', (e) => {
        if (e.target.tagName !== 'INPUT') {
          const checkbox = item.querySelector('input[type="checkbox"]');
          checkbox.checked = !checkbox.checked;
        }
      });
      
      this.permissionsGrid.appendChild(item);
    });
  }

  filterPermissions(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    const items = this.permissionsGrid.querySelectorAll('.permission-checkbox-item');
    
    items.forEach(item => {
      const permKey = item.dataset.permission;
      const permDesc = this.permissions[permKey];
      
      if (!term || permKey.toLowerCase().includes(term) || permDesc.toLowerCase().includes(term)) {
        item.style.display = 'flex';
      } else {
        item.style.display = 'none';
      }
    });
  }

  getSelectedPermissions() {
    const checkboxes = this.permissionsGrid.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.id.replace('perm-', ''));
  }

  async handleSaveRole() {
    const name = this.roleNameInput.value.trim();
    const description = this.roleDescriptionInput.value.trim();
    const permissions = this.getSelectedPermissions();
    
    // Validation
    if (!name) {
      this.roleEditorError.textContent = 'Role name is required';
      this.roleEditorError.style.display = 'block';
      return;
    }
    
    if (permissions.length === 0) {
      this.roleEditorError.textContent = 'At least one permission must be selected';
      this.roleEditorError.style.display = 'block';
      return;
    }
    
    try {
      let response;
      
      if (this.editMode) {
        // Update existing role
        response = await fetch(`/api/roles/${this.currentRoleId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            name,
            description,
            permissions
          })
        });
      } else {
        // Create new role
        response = await fetch('/api/roles', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            name,
            description,
            permissions
          })
        });
      }
      
      const data = await response.json();
      
      if (data.success) {
        this.showStatus(data.message || (this.editMode ? 'Role updated successfully' : 'Role created successfully'), 'success');
        this.closeRoleEditorModal();
        await this.loadRoles();
      } else {
        this.roleEditorError.textContent = data.message || 'Failed to save role';
        this.roleEditorError.style.display = 'block';
      }
    } catch (error) {
      console.error('Error saving role:', error);
      this.roleEditorError.textContent = 'Error: ' + error.message;
      this.roleEditorError.style.display = 'block';
    }
  }

  // Copy Role Modal methods
  openCopyRoleModal(role) {
    this.currentRoleId = role.id;
    this.copyRoleSourceName.textContent = `Creating a copy of: ${role.name}`;
    this.copyRoleNameInput.value = `${role.name} (Copy)`;
    this.copyRoleError.style.display = 'none';
    this.copyRoleModal.style.display = 'flex';
  }

  closeCopyRoleModal() {
    this.copyRoleModal.style.display = 'none';
    this.currentRoleId = null;
  }

  async handleCopyRole() {
    const newName = this.copyRoleNameInput.value.trim();
    
    if (!newName) {
      this.copyRoleError.textContent = 'Role name is required';
      this.copyRoleError.style.display = 'block';
      return;
    }
    
    try {
      const response = await fetch(`/api/roles/${this.currentRoleId}/copy`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: newName
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        this.showStatus(data.message || 'Role copied successfully', 'success');
        this.closeCopyRoleModal();
        await this.loadRoles();
      } else {
        this.copyRoleError.textContent = data.message || 'Failed to copy role';
        this.copyRoleError.style.display = 'block';
      }
    } catch (error) {
      console.error('Error copying role:', error);
      this.copyRoleError.textContent = 'Error: ' + error.message;
      this.copyRoleError.style.display = 'block';
    }
  }

  // Delete Role methods
  confirmDeleteRole(role) {
    this.confirmModalTitle.textContent = 'Confirm Role Deletion';
    this.confirmModalMessage.textContent = `Are you sure you want to delete the role "${role.name}"? This action cannot be undone. Users with this role will lose these permissions.`;
    
    this.confirmOkBtn.onclick = async () => {
      await this.deleteRole(role.id);
      this.closeConfirmModal();
    };
    
    this.confirmModal.style.display = 'flex';
  }

  async deleteRole(roleId) {
    try {
      const response = await fetch(`/api/roles/${roleId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();
      
      if (data.success) {
        this.showStatus(data.message || 'Role deleted successfully', 'success');
        await this.loadRoles();
      } else {
        throw new Error(data.message || 'Failed to delete role');
      }
    } catch (error) {
      console.error('Error deleting role:', error);
      this.showStatus('Error: ' + error.message, 'error');
    }
  }

  async loadPermissionMappings() {
    try {
      const response = await fetch('/api/roles/permission-mappings');
      
      if (response.status === 403) {
        this.mappingsLoading.style.display = 'none';
        this.mappingsError.textContent = 'You do not have permission to view permission mappings.';
        this.mappingsError.style.display = 'block';
        return;
      }
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();

      if (data.success && data.by_permission && data.by_endpoint) {
        this.permissionMappings = data;
        this.renderMappingsByPermission();
        this.mappingsLoading.style.display = 'none';
        this.mappingsByPermission.style.display = 'block';
      } else {
        throw new Error(data.message || data.error || 'Failed to load permission mappings');
      }
    } catch (error) {
      console.error('Error loading permission mappings:', error);
      this.mappingsLoading.style.display = 'none';
      this.mappingsError.textContent = 'Failed to load permission mappings: ' + error.message;
      this.mappingsError.style.display = 'block';
    }
  }

  renderMappingsByPermission() {
    if (!this.permissionMappings) return;

    const { by_permission, permission_details, summary } = this.permissionMappings;
    
    let html = '';
    
    // Summary stats
    html += `
      <div class="mappings-summary">
        <div class="summary-stat">
          <span class="summary-label">Total Permissions:</span>
          <span class="summary-value">${summary.total_permissions}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-label">Total Endpoints:</span>
          <span class="summary-value">${summary.total_endpoints}</span>
        </div>
      </div>
    `;

    // Permissions list
    const permissionKeys = Object.keys(by_permission).sort();
    
    for (const permission of permissionKeys) {
      const endpoints = by_permission[permission];
      const details = permission_details[permission];
      const description = details ? details.description : 'No description';
      
      html += `
        <div class="mapping-card">
          <div class="mapping-card-header">
            <div class="mapping-header-content">
              <code class="permission-name">${this.escapeHtml(permission)}</code>
              <span class="endpoint-count">${endpoints.length} endpoint${endpoints.length !== 1 ? 's' : ''}</span>
            </div>
            <p class="permission-description">${this.escapeHtml(description)}</p>
          </div>
          <div class="mapping-card-body">
            <ul class="endpoints-list">
      `;
      
      for (const endpoint of endpoints) {
        const methodsStr = endpoint.methods.join(', ');
        const note = endpoint.note ? ` <span class="endpoint-note">(${this.escapeHtml(endpoint.note)})</span>` : '';
        html += `
          <li class="endpoint-item">
            <span class="endpoint-methods">${this.escapeHtml(methodsStr)}</span>
            <code class="endpoint-path">${this.escapeHtml(endpoint.path)}</code>
            ${note}
          </li>
        `;
      }
      
      html += `
            </ul>
          </div>
        </div>
      `;
    }
    
    this.mappingsByPermission.innerHTML = html;
  }

  renderMappingsByEndpoint() {
    if (!this.permissionMappings) return;

    const { by_endpoint, summary } = this.permissionMappings;
    
    let html = '';
    
    // Summary stats
    html += `
      <div class="mappings-summary">
        <div class="summary-stat">
          <span class="summary-label">Total Endpoints:</span>
          <span class="summary-value">${summary.total_endpoints}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-label">Permission Protected:</span>
          <span class="summary-value">${summary.permission_protected}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-label">Authentication Only:</span>
          <span class="summary-value">${summary.authentication_only}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-label">Board Access:</span>
          <span class="summary-value">${summary.board_access}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-label">Public:</span>
          <span class="summary-value">${summary.public}</span>
        </div>
      </div>
    `;

    // Endpoints list
    const endpointKeys = Object.keys(by_endpoint).sort();
    
    for (const endpointPath of endpointKeys) {
      const endpoint = by_endpoint[endpointPath];
      const methodsStr = endpoint.methods.join(', ');
      const protectionType = endpoint.protection;
      
      let protectionBadge = '';
      
      if (protectionType === 'permission') {
        protectionBadge = '<span class="protection-badge protection-permission">Permission Required</span>';
      } else if (protectionType === 'authentication') {
        protectionBadge = '<span class="protection-badge protection-auth">Authentication Only</span>';
      } else if (protectionType === 'board_access') {
        protectionBadge = '<span class="protection-badge protection-board">Board Access Required</span>';
      } else if (protectionType === 'public') {
        protectionBadge = '<span class="protection-badge protection-public">Public</span>';
      }
      
      html += `
        <div class="mapping-card">
          <div class="mapping-card-header">
            <div class="endpoint-header">
              <div class="endpoint-info">
                <span class="endpoint-methods">${this.escapeHtml(methodsStr)}</span>
                <code class="endpoint-path">${this.escapeHtml(endpoint.path)}</code>
              </div>
              ${protectionBadge}
            </div>
          </div>
      `;
      
      if (protectionType === 'permission' && endpoint.permissions && endpoint.permissions.length > 0) {
        html += `
          <div class="mapping-card-body">
            <ul class="permissions-list">
              ${endpoint.permissions.map(perm => `<li><code class="permission-name">${this.escapeHtml(perm)}</code></li>`).join('')}
            </ul>
          </div>
        `;
      }
      
      html += `</div>`;
    }
    
    this.mappingsByEndpoint.innerHTML = html;
  }

  toggleMappingView() {
    if (this.currentMappingView === 'permission') {
      // Switch to endpoint view
      this.currentMappingView = 'endpoint';
      this.mappingsByPermission.style.display = 'none';
      this.mappingsByEndpoint.style.display = 'block';
      this.viewToggleText.textContent = 'View by Permission';
      this.renderMappingsByEndpoint();
    } else {
      // Switch to permission view
      this.currentMappingView = 'permission';
      this.mappingsByEndpoint.style.display = 'none';
      this.mappingsByPermission.style.display = 'block';
      this.viewToggleText.textContent = 'View by Endpoint';
      this.renderMappingsByPermission();
    }
  }

  showStatus(message, type = 'info') {
    this.statusMessage.textContent = message;
    this.statusMessage.className = 'settings-status ' + type;
    this.statusMessage.style.display = 'block';

    setTimeout(() => {
      this.statusMessage.style.display = 'none';
    }, 5000);
  }

  escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return unsafe
      .toString()
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
  // Wait for header to load and user info to be available
  // The header.js sets window.userDataReady flag when done
  let attempts = 0;
  while (!window.userDataReady && attempts < 50) {
    await new Promise(resolve => setTimeout(resolve, 100)); // Wait 100ms
    attempts++;
  }
  
  const roleManagement = new RoleManagement();
  await roleManagement.init();
});
