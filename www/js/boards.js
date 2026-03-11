// Boards page functionality
class BoardsManager {
  constructor() {
    this.container = document.getElementById('boards-container');
    this.boards = [];
  }

  async init() {
    // Initialize Permission Manager (no board context for boards list)
    console.log('Initializing PermissionManager for boards page');
    const permissionInitSuccess = await PermissionManager.init();
    
    if (!permissionInitSuccess) {
      console.warn('Failed to initialize PermissionManager - some features may not be available');
    }
    
    // Check for default board setting and redirect if set
    const shouldRedirect = await this.checkDefaultBoard();
    if (shouldRedirect) {
      // Redirecting to default board, skip rendering
      return;
    }
    
    this.render();
    await this.loadBoards();
  }

  async checkDefaultBoard() {
    try {
      // Skip redirect if any URL parameters are present (e.g., ?show_boards=1)
      // This allows direct access to boards list when needed
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.toString()) {
        // URL has parameters, skip default board redirect
        return false;
      }
      
      const response = await fetch('/api/settings/default_board');
      
      if (response.ok) {
        const data = await response.json();
        
        if (data.success && data.value) {
          // Redirect to default board
          window.location.href = `/board.html?id=${data.value}`;
          return true; // Indicate redirect is happening
        }
      }
      // If no default board or error, continue to boards list
      return false;
    } catch (err) {
      // If error checking default board, continue to boards list
      console.error('Error checking default board:', err);
      return false;
    }
  }

  render() {
    this.container.innerHTML = `
      <div class="boards-header-panel">
        <div class="boards-header">
          <h3>My Boards</h3>
        </div>
      </div>
      <div id="boards-list" class="loading">
        Loading boards...
      </div>
      
      <!-- New Board Modal -->
      <div id="new-board-modal" class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h3>Create New Board</h3>
            <button class="modal-close" id="modal-close">&times;</button>
          </div>
          <form id="new-board-form">
            <div class="form-group">
              <label for="board-name">Board Name</label>
              <input type="text" id="board-name" name="name" required placeholder="Enter board name" autofocus>
            </div>
            <div class="form-group">
              <label for="board-description">Description (optional)</label>
              <textarea id="board-description" name="description" placeholder="Enter board description" rows="3"></textarea>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancel-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Create Board</button>
            </div>
          </form>
        </div>
      </div>
      
      <!-- Edit Board Modal -->
      <div id="edit-board-modal" class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h3>Edit Board</h3>
            <button class="modal-close" id="edit-modal-close">&times;</button>
          </div>
          <form id="edit-board-form">
            <input type="hidden" id="edit-board-id">
            <div class="form-group">
              <label for="edit-board-name">Board Name</label>
              <input type="text" id="edit-board-name" name="name" required placeholder="Enter board name" autofocus>
            </div>
            <div class="form-group">
              <label for="edit-board-description">Description</label>
              <textarea id="edit-board-description" name="description" placeholder="Enter board description" rows="3"></textarea>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="edit-cancel-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Save Changes</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // Attach event listeners for new board modal
    document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
    document.getElementById('cancel-btn').addEventListener('click', () => this.closeModal());
    document.getElementById('new-board-form').addEventListener('submit', (e) => this.handleCreateBoard(e));
    
    // Attach event listeners for edit board modal
    document.getElementById('edit-modal-close').addEventListener('click', () => this.closeEditModal());
    document.getElementById('edit-cancel-btn').addEventListener('click', () => this.closeEditModal());
    document.getElementById('edit-board-form').addEventListener('submit', (e) => this.handleEditBoard(e));
    
    // Close modals on backdrop click
    document.getElementById('new-board-modal').addEventListener('click', (e) => {
      if (e.target.id === 'new-board-modal') {
        this.closeModal();
      }
    });
    
    document.getElementById('edit-board-modal').addEventListener('click', (e) => {
      if (e.target.id === 'edit-board-modal') {
        this.closeEditModal();
      }
    });
  }

  async loadBoards() {
    try {
      const response = await fetch('/api/boards');
      
      // Check for authentication errors
      if (response.status === 401) {
        this.showError('Authentication required. Please log in to view your boards.');
        return;
      }
      
      // Check for other HTTP errors
      if (!response.ok) {
        this.showError(`Failed to load boards: HTTP ${response.status}`);
        return;
      }
      
      const data = await response.json();
      
      if (data.success) {
        this.boards = data.boards;
        this.renderBoardsList();
      } else {
        this.showError('Failed to load boards: ' + data.message);
      }
    } catch (err) {
      this.showError('Error loading boards: ' + err.message);
    }
  }

  renderBoardsList() {
    const listContainer = document.getElementById('boards-list');
    
    if (this.boards.length === 0) {
      listContainer.className = ''; // Remove grid class
      listContainer.innerHTML = `
        <div class="empty-state-panel">
          <div class="empty-state">
            <div class="empty-state-icon">📋</div>
            <h3>No boards yet</h3>
            <p>Create your first board to get started!</p>
            <button class="btn btn-primary" id="empty-state-new-board-btn">+ New Board</button>
          </div>
        </div>
      `;
      
      // Add event listener for the empty state button
      document.getElementById('empty-state-new-board-btn').addEventListener('click', () => this.openModal());
    } else {
      listContainer.className = 'boards-grid';
      
      // Render board cards (always include edit/delete buttons, will filter by permissions after)
      listContainer.innerHTML = this.boards.map(board => `
        <div class="board-card" data-board-id="${board.id}" data-can-edit="${board.can_edit}" data-can-delete="${board.can_delete}">
          <button class="board-edit-btn" data-board-id="${board.id}" data-board-name="${this.escapeHtml(board.name)}" data-board-description="${this.escapeHtml(board.description || '')}" title="Edit board">✎</button>
          <button class="board-delete-btn" data-board-id="${board.id}" title="Delete board">×</button>
          <h4>${this.escapeHtml(board.name)}</h4>
          ${board.description ? `<p class="board-description">${this.escapeHtml(board.description)}</p>` : ''}
        </div>
      `).join('') + `
        <div class="add-board-placeholder">
          <button class="btn btn-primary" id="add-board-inline-btn">+ New Board</button>
        </div>
      `;
      
      // Apply permission-based rendering to board action buttons
      this.applyPermissionBasedRendering();
      
      // Add event listener for inline add board button
      document.getElementById('add-board-inline-btn').addEventListener('click', () => this.openModal());
      
      // Add event listeners for edit buttons
      listContainer.querySelectorAll('.board-edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation(); // Prevent card click
          const boardId = parseInt(e.target.dataset.boardId);
          const boardName = e.target.dataset.boardName;
          const boardDescription = e.target.dataset.boardDescription;
          this.openEditModal(boardId, boardName, boardDescription);
        });
      });
      
      // Add event listeners for delete buttons
      listContainer.querySelectorAll('.board-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation(); // Prevent card click
          this.handleDeleteBoard(parseInt(e.target.dataset.boardId));
        });
      });
      
      // Add event listeners for board cards
      listContainer.querySelectorAll('.board-card').forEach(card => {
        card.addEventListener('click', (e) => {
          const boardId = e.currentTarget.dataset.boardId;
          window.location.href = `/board.html?id=${boardId}`;
        });
      });
    }
  }

  /**
   * Apply permission-based rendering to board action buttons
   * Removes edit/delete buttons based on backend permission flags and user permissions
   */
  applyPermissionBasedRendering() {
    if (!window.PermissionManager || !PermissionManager.initialized) {
      console.log('PermissionManager not available - using backend permission flags only');
      // Fallback: just use backend flags
      this.applyBackendPermissionFlags();
      return;
    }
    
    console.log('Applying permission-based rendering to board cards...');
    
    // For each board card, check permissions
    document.querySelectorAll('.board-card').forEach(card => {
      const canEdit = card.getAttribute('data-can-edit') === 'true';
      const canDelete = card.getAttribute('data-can-delete') === 'true';
      
      const editBtn = card.querySelector('.board-edit-btn');
      const deleteBtn = card.querySelector('.board-delete-btn');
      
      // Remove edit button if user doesn't have permission
      // Backend has already calculated board-specific permissions (ownership + roles)
      if (!canEdit) {
        editBtn?.remove();
      }
      
      // Remove delete button if user doesn't have permission
      if (!canDelete) {
        deleteBtn?.remove();
      }
    });
    
    // Check if user can create boards - if not, remove "New Board" button
    if (!PermissionManager.hasPermission('board.create')) {
      document.getElementById('add-board-inline-btn')?.remove();
      document.getElementById('empty-state-new-board-btn')?.remove();
    }
    
    console.log('Permission-based rendering complete');
  }

  /**
   * Fallback method when PermissionManager is not available
   * Uses backend permission flags only
   */
  applyBackendPermissionFlags() {
    document.querySelectorAll('.board-card').forEach(card => {
      const canEdit = card.getAttribute('data-can-edit') === 'true';
      const canDelete = card.getAttribute('data-can-delete') === 'true';
      
      const editBtn = card.querySelector('.board-edit-btn');
      const deleteBtn = card.querySelector('.board-delete-btn');
      
      if (!canEdit) {
        editBtn?.remove();
      }
      
      if (!canDelete) {
        deleteBtn?.remove();
      }
    });
  }

  openModal() {
    const modal = document.getElementById('new-board-modal');
    modal.classList.add('active');
    document.getElementById('board-name').focus();
  }

  closeModal() {
    const modal = document.getElementById('new-board-modal');
    modal.classList.remove('active');
    document.getElementById('new-board-form').reset();
  }

  async handleCreateBoard(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const boardName = formData.get('name').trim();
    const boardDescription = formData.get('description')?.trim() || null;
    
    if (!boardName) {
      await showAlert('Please enter a board name', 'Invalid Input');
      return;
    }

    try {
      const response = await fetch('/api/boards', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: boardName, description: boardDescription })
      });

      const data = await response.json();

      if (data.success) {
        this.closeModal();
        await this.loadBoards();
        
        // Update header status and boards dropdown if available
        if (window.header) {
          window.header.checkDatabaseStatus();
          window.header.loadBoardsDropdown();
        }
      } else {
        await showAlert('Failed to create board: ' + data.message, 'Error');
      }
    } catch (err) {
      await showAlert('Error creating board: ' + err.message, 'Error');
    }
  }

  async handleDeleteBoard(boardId) {
    if (!await showConfirm('Are you sure you want to delete this board?', 'Confirm Deletion')) {
      return;
    }

    try {
      const response = await fetch(`/api/boards/${boardId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        await this.loadBoards();
        
        // Update header status and boards dropdown if available
        if (window.header) {
          window.header.checkDatabaseStatus();
          window.header.loadBoardsDropdown();
        }
      } else {
        await showAlert('Failed to delete board: ' + data.message, 'Error');
      }
    } catch (err) {
      await showAlert('Error deleting board: ' + err.message, 'Error');
    }
  }

  openEditModal(boardId, boardName, boardDescription) {
    const modal = document.getElementById('edit-board-modal');
    document.getElementById('edit-board-id').value = boardId;
    document.getElementById('edit-board-name').value = boardName;
    document.getElementById('edit-board-description').value = boardDescription || '';
    modal.classList.add('active');
    document.getElementById('edit-board-name').focus();
  }

  closeEditModal() {
    const modal = document.getElementById('edit-board-modal');
    modal.classList.remove('active');
    document.getElementById('edit-board-form').reset();
  }

  async handleEditBoard(e) {
    e.preventDefault();
    
    const boardId = document.getElementById('edit-board-id').value;
    const formData = new FormData(e.target);
    const boardName = formData.get('name').trim();
    const boardDescription = formData.get('description')?.trim() || '';
    
    if (!boardName) {
      await showAlert('Please enter a board name', 'Invalid Input');
      return;
    }

    try {
      const response = await fetch(`/api/boards/${boardId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: boardName, description: boardDescription })
      });

      const data = await response.json();

      if (data.success) {
        this.closeEditModal();
        await this.loadBoards();
        
        // Update header status and boards dropdown if available
        if (window.header) {
          window.header.checkDatabaseStatus();
          window.header.loadBoardsDropdown();
        }
      } else {
        await showAlert('Failed to update board: ' + data.message, 'Error');
      }
    } catch (err) {
      await showAlert('Error updating board: ' + err.message, 'Error');
    }
  }

  showError(message) {
    const listContainer = document.getElementById('boards-list');
    listContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚠️</div>
        <h3>Error</h3>
        <p>${this.escapeHtml(message)}</p>
      </div>
    `;
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize boards manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const boardsManager = new BoardsManager();
  boardsManager.init();
});
