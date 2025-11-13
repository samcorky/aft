// Board detail page functionality
class BoardManager {
  constructor() {
    this.container = document.getElementById('board-container');
    this.boardId = null;
    this.boardName = '';
    this.columns = [];
  }

  async init() {
    // Get board ID from URL query parameter
    const urlParams = new URLSearchParams(window.location.search);
    this.boardId = urlParams.get('id');
    
    if (!this.boardId) {
      this.showError('No board ID specified');
      return;
    }

    this.render();
    await this.loadBoard();
  }

  render() {
    this.container.innerHTML = `
      <div class="loading-board">Loading board...</div>
    `;
  }

  async loadBoard() {
    try {
      // Load board with nested structure (board -> columns -> cards)
      const response = await fetch(`/api/boards/${this.boardId}/cards`);
      const data = await response.json();
      
      if (!data.success) {
        this.showError('Failed to load board: ' + data.message);
        return;
      }

      const board = data.board;
      this.boardName = board.name;
      this.columns = board.columns;
      
      // Update header with board name and page title
      this.updateBoardTitle();
      
      this.renderBoard();
    } catch (err) {
      this.showError('Error loading board: ' + err.message);
    }
  }

  updateBoardTitle() {
    // Update page title
    document.title = `AFT - ${this.boardName}`;
    
    // Update header navbar with board name
    if (window.header) {
      window.header.setBoardName(this.boardName);
    }
  }

  renderBoard() {
    if (this.columns.length === 0) {
      this.container.innerHTML = `
        <div class="empty-board">
          <div class="empty-board-icon">📋</div>
          <h3>No columns yet</h3>
          <p>Add your first column to start organizing tasks!</p>
          <button class="btn btn-primary" id="add-column-empty-btn">+ Add Column</button>
        </div>
      `;
      
      // Add event listener for add column button
      document.getElementById('add-column-empty-btn').addEventListener('click', () => this.openAddColumnModal());
    } else {
      this.container.innerHTML = `
        <div class="columns-container">
          ${this.columns.map(column => `
            <div class="column" data-column-id="${column.id}" data-board-id="${this.boardId}" data-order="${column.order}">
              <div class="column-header">
                <div class="column-title-group">
                  <h4>${this.escapeHtml(column.name)}</h4>
                  <button class="column-edit-btn" data-column-id="${column.id}" data-column-name="${this.escapeHtml(column.name)}" title="Edit column">✎</button>
                </div>
                <div class="column-actions">
                  <button class="column-add-card-btn" data-column-id="${column.id}" title="Add card">+</button>
                  <button class="column-delete-cards-btn" data-column-id="${column.id}" title="Delete all cards">🗑</button>
                  <button class="column-move-left-btn" data-column-id="${column.id}" data-order="${column.order}" title="Move left">◀</button>
                  <button class="column-move-right-btn" data-column-id="${column.id}" data-order="${column.order}" title="Move right">▶</button>
                  <button class="column-delete-btn" data-column-id="${column.id}" title="Delete column">×</button>
                </div>
              </div>
              <div class="column-cards" data-column-id="${column.id}">
                ${column.cards && column.cards.length > 0 ? 
                  column.cards.map(card => `
                    <div class="card" draggable="true" data-card-id="${card.id}" data-column-id="${column.id}" data-order="${card.order}">
                      <button class="card-delete-btn" data-card-id="${card.id}" title="Delete card">×</button>
                      <h5 class="card-title">${this.escapeHtml(card.title)}</h5>
                      <p class="card-description">${this.escapeHtml(card.description)}</p>
                    </div>
                  `).join('') : ''
                }
                <button class="btn btn-secondary add-card-btn" data-column-id="${column.id}">+ Add Card</button>
              </div>
            </div>
          `).join('')}
          <div class="add-column-placeholder">
            <button class="btn btn-primary" id="add-column-inline-btn">+ Add Column</button>
          </div>
        </div>
      `;
      
      // Add event listener for add column button next to columns
      document.getElementById('add-column-inline-btn').addEventListener('click', () => this.openAddColumnModal());
      
      // Add event listeners for edit column buttons
      document.querySelectorAll('.column-edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          const columnName = e.target.getAttribute('data-column-name');
          this.openEditColumnModal(columnId, columnName);
        });
      });
      
      // Add event listeners for add card buttons (header and empty state)
      document.querySelectorAll('.column-add-card-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          this.openAddCardModal(columnId, 0); // Add at top (order 0)
        });
      });
      
      document.querySelectorAll('.add-card-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          this.openAddCardModal(columnId); // Add at bottom (default)
        });
      });
      
      // Add event listeners for delete column buttons
      document.querySelectorAll('.column-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          this.deleteColumn(columnId);
        });
      });
      
      // Add event listeners for delete all cards buttons
      document.querySelectorAll('.column-delete-cards-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          this.deleteAllCardsInColumn(columnId);
        });
      });
      
      // Add event listeners for move column buttons
      document.querySelectorAll('.column-move-left-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          const currentOrder = parseInt(e.target.getAttribute('data-order'));
          if (currentOrder > 0) {
            this.moveColumn(columnId, currentOrder - 1);
          }
        });
      });
      
      document.querySelectorAll('.column-move-right-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          const currentOrder = parseInt(e.target.getAttribute('data-order'));
          const maxOrder = this.columns.length - 1;
          if (currentOrder < maxOrder) {
            this.moveColumn(columnId, currentOrder + 1);
          }
        });
      });
      
      // Add event listeners for card clicks (open edit modal)
      document.querySelectorAll('.card').forEach(card => {
        card.addEventListener('click', (e) => {
          // Don't trigger if clicking the delete button
          if (e.target.classList.contains('card-delete-btn')) return;
          
          const cardId = parseInt(card.getAttribute('data-card-id'));
          const cardTitle = card.querySelector('.card-title').textContent;
          const cardDescription = card.querySelector('.card-description').textContent;
          this.openEditCardModal(cardId, cardTitle, cardDescription);
        });
      });
      
      // Add event listeners for delete card buttons
      document.querySelectorAll('.card-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.target.getAttribute('data-card-id'));
          this.deleteCard(cardId);
        });
      });
      
      // Add drag and drop event listeners for cards
      this.setupDragAndDrop();
    }
  }

  async moveColumn(columnId, newOrder) {
    await this.updateColumnPosition(columnId, newOrder);
  }

  async updateColumnPosition(columnId, order) {
    try {
      const response = await fetch(`/api/columns/${columnId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ order: order })
      });
      
      const data = await response.json();
      
      if (!data.success) {
        console.error('Failed to update column position:', data.message);
        // Reload board to restore correct state
        await this.loadBoard();
      } else {
        // Reload board to get updated order for all columns
        await this.loadBoard();
      }
    } catch (err) {
      console.error('Error updating column position:', err);
      // Reload board to restore correct state
      await this.loadBoard();
    }
  }

  setupDragAndDrop() {
    const cards = document.querySelectorAll('.card');
    const columnCards = document.querySelectorAll('.column-cards');
    
    let draggedCard = null;
    
    // Card drag events
    cards.forEach(card => {
      card.addEventListener('dragstart', (e) => {
        e.stopPropagation(); // Prevent column from also starting to drag
        draggedCard = card;
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', card.innerHTML);
      });
      
      card.addEventListener('dragend', (e) => {
        card.classList.remove('dragging');
        draggedCard = null;
      });
    });
    
    // Column drop zone events
    columnCards.forEach(columnContainer => {
      columnContainer.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        
        const afterElement = this.getDragAfterElement(columnContainer, e.clientY);
        const dragging = document.querySelector('.dragging');
        
        if (afterElement == null) {
          // Append at the end (before the add card button)
          const addCardBtn = columnContainer.querySelector('.add-card-btn');
          if (addCardBtn && dragging) {
            columnContainer.insertBefore(dragging, addCardBtn);
          }
        } else {
          if (dragging) {
            columnContainer.insertBefore(dragging, afterElement);
          }
        }
      });
      
      columnContainer.addEventListener('drop', async (e) => {
        e.preventDefault();
        
        if (!draggedCard) return;
        
        const targetColumnId = parseInt(columnContainer.getAttribute('data-column-id'));
        const cardId = parseInt(draggedCard.getAttribute('data-card-id'));
        const oldColumnId = parseInt(draggedCard.getAttribute('data-column-id'));
        
        // Calculate new order based on position in DOM
        const cardsInColumn = Array.from(columnContainer.querySelectorAll('.card'));
        const newOrder = cardsInColumn.indexOf(draggedCard);
        
        // Only update if position or column changed
        const oldOrder = parseInt(draggedCard.getAttribute('data-order'));
        if (targetColumnId !== oldColumnId || newOrder !== oldOrder) {
          await this.updateCardPosition(cardId, targetColumnId, newOrder);
        }
      });
    });
  }

  getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.card:not(.dragging)')];
    
    return draggableElements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      
      if (offset < 0 && offset > closest.offset) {
        return { offset: offset, element: child };
      } else {
        return closest;
      }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  async updateCardPosition(cardId, columnId, order) {
    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          column_id: columnId,
          order: order
        })
      });
      
      const data = await response.json();
      
      if (!data.success) {
        console.error('Failed to update card position:', data.message);
        // Reload board to restore correct state
        await this.loadBoard();
      } else {
        // Update local data attributes
        const cardElement = document.querySelector(`[data-card-id="${cardId}"]`);
        if (cardElement) {
          cardElement.setAttribute('data-column-id', columnId);
          cardElement.setAttribute('data-order', order);
        }
      }
    } catch (err) {
      console.error('Error updating card position:', err);
      // Reload board to restore correct state
      await this.loadBoard();
    }
  }

  openAddColumnModal() {
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="add-column-modal">
        <div class="modal-content">
          <h2>Add New Column</h2>
          <form id="add-column-form">
            <div class="form-group">
              <label for="column-name">Column Name:</label>
              <input type="text" id="column-name" name="column-name" required>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancel-column-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Create Column</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('add-column-modal');
    const form = document.getElementById('add-column-form');
    const cancelBtn = document.getElementById('cancel-column-btn');
    const nameInput = document.getElementById('column-name');

    // Focus on input
    nameInput.focus();

    // Handle cancel
    cancelBtn.addEventListener('click', () => {
      modal.remove();
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const columnName = nameInput.value.trim();
      
      if (columnName) {
        await this.createColumn(columnName);
        modal.remove();
      }
    });

    // Close modal on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
  }

  async createColumn(name) {
    try {
      const response = await fetch(`/api/boards/${this.boardId}/columns`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });

      const data = await response.json();

      if (data.success) {
        // Reload columns to show the new one
        await this.loadBoard();
      } else {
        alert('Failed to create column: ' + data.message);
      }
    } catch (err) {
      alert('Error creating column: ' + err.message);
    }
  }

  async deleteColumn(columnId) {
    if (!confirm('Are you sure you want to delete this column?')) {
      return;
    }

    try {
      const response = await fetch(`/api/columns/${columnId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        // Reload columns to reflect deletion
        await this.loadBoard();
      } else {
        alert('Failed to delete column: ' + data.message);
      }
    } catch (err) {
      alert('Error deleting column: ' + err.message);
    }
  }

  async deleteAllCardsInColumn(columnId) {
    if (!confirm('Are you sure you want to delete all cards in this column? This action cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch(`/api/columns/${columnId}/cards`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        // Reload board to reflect deletion
        await this.loadBoard();
      } else {
        alert('Failed to delete cards: ' + data.message);
      }
    } catch (err) {
      alert('Error deleting cards: ' + err.message);
    }
  }

  openEditColumnModal(columnId, currentName) {
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="edit-column-modal">
        <div class="modal-content">
          <h2>Edit Column</h2>
          <form id="edit-column-form">
            <div class="form-group">
              <label for="edit-column-name">Column Name:</label>
              <input type="text" id="edit-column-name" name="edit-column-name" value="${this.escapeHtml(currentName)}" required>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancel-edit-column-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Save</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('edit-column-modal');
    const form = document.getElementById('edit-column-form');
    const cancelBtn = document.getElementById('cancel-edit-column-btn');
    const nameInput = document.getElementById('edit-column-name');

    // Focus on input and select text
    nameInput.focus();
    nameInput.select();

    // Handle cancel
    cancelBtn.addEventListener('click', () => {
      modal.remove();
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const columnName = nameInput.value.trim();
      
      if (columnName) {
        await this.updateColumn(columnId, columnName);
        modal.remove();
      }
    });

    // Close modal on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
  }

  async updateColumn(columnId, name) {
    try {
      const response = await fetch(`/api/columns/${columnId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });

      const data = await response.json();

      if (data.success) {
        // Reload columns to show the updated name
        await this.loadBoard();
      } else {
        alert('Failed to update column: ' + data.message);
      }
    } catch (err) {
      alert('Error updating column: ' + err.message);
    }
  }

  openAddCardModal(columnId, order = null) {
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="add-card-modal">
        <div class="modal-content">
          <h2>Add New Card</h2>
          <form id="add-card-form">
            <div class="form-group">
              <label for="card-title">Title:</label>
              <input type="text" id="card-title" name="card-title" required>
            </div>
            <div class="form-group">
              <label for="card-description">Description:</label>
              <textarea id="card-description" name="card-description" rows="4"></textarea>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancel-card-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Create Card</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('add-card-modal');
    const form = document.getElementById('add-card-form');
    const cancelBtn = document.getElementById('cancel-card-btn');
    const titleInput = document.getElementById('card-title');

    // Focus on input
    titleInput.focus();

    // Handle cancel
    cancelBtn.addEventListener('click', () => {
      modal.remove();
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const title = titleInput.value.trim();
      const description = document.getElementById('card-description').value.trim();
      
      if (title) {
        await this.createCard(columnId, title, description, order);
        modal.remove();
      }
    });

    // Close modal on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
  }

  async createCard(columnId, title, description, order = null) {
    try {
      const body = { title, description };
      if (order !== null) {
        body.order = order;
      }
      
      const response = await fetch(`/api/columns/${columnId}/cards`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (data.success) {
        // Reload board to show the new card
        await this.loadBoard();
      } else {
        alert('Failed to create card: ' + data.message);
      }
    } catch (err) {
      alert('Error creating card: ' + err.message);
    }
  }

  openEditCardModal(cardId, currentTitle, currentDescription) {
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="edit-card-modal">
        <div class="modal-content">
          <h2>Edit Card</h2>
          <form id="edit-card-form">
            <div class="form-group">
              <label for="edit-card-title">Title:</label>
              <input type="text" id="edit-card-title" name="edit-card-title" value="${this.escapeHtml(currentTitle)}" required>
            </div>
            <div class="form-group">
              <label for="edit-card-description">Description:</label>
              <textarea id="edit-card-description" name="edit-card-description" rows="4">${this.escapeHtml(currentDescription)}</textarea>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancel-edit-card-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Save</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('edit-card-modal');
    const form = document.getElementById('edit-card-form');
    const cancelBtn = document.getElementById('cancel-edit-card-btn');
    const titleInput = document.getElementById('edit-card-title');

    // Focus on input and select text
    titleInput.focus();
    titleInput.select();

    // Handle cancel
    cancelBtn.addEventListener('click', () => {
      modal.remove();
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const title = titleInput.value.trim();
      const description = document.getElementById('edit-card-description').value.trim();
      
      if (title) {
        await this.updateCard(cardId, title, description);
        modal.remove();
      }
    });

    // Close modal on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
  }

  async updateCard(cardId, title, description) {
    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ title, description })
      });

      const data = await response.json();

      if (data.success) {
        // Reload board to show the updated card
        await this.loadBoard();
      } else {
        alert('Failed to update card: ' + data.message);
      }
    } catch (err) {
      alert('Error updating card: ' + err.message);
    }
  }

  async deleteCard(cardId) {
    if (!confirm('Are you sure you want to delete this card?')) {
      return;
    }

    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        // Reload board to reflect deletion
        await this.loadBoard();
      } else {
        alert('Failed to delete card: ' + data.message);
      }
    } catch (err) {
      alert('Error deleting card: ' + err.message);
    }
  }

  showError(message) {
    this.container.innerHTML = `
      <div class="empty-board">
        <div class="empty-board-icon">⚠️</div>
        <h3>Error</h3>
        <p>${this.escapeHtml(message)}</p>
        <button class="btn btn-secondary" onclick="window.location.href='/'">← Back to Boards</button>
      </div>
    `;
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize board manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const boardManager = new BoardManager();
  boardManager.init();
});
