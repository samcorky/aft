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
                      ${card.checklist_items && card.checklist_items.length > 0 ? `
                        <div class="card-checklist">
                          <div class="card-checklist-summary">
                            ${card.checklist_items.filter(i => i.checked).length}/${card.checklist_items.length} (${card.checklist_items.length > 0 ? Math.round((card.checklist_items.filter(i => i.checked).length / card.checklist_items.length) * 100) : 0}%)
                          </div>
                          ${card.checklist_items.map(item => `
                            <div class="card-checklist-item">
                              <input 
                                type="checkbox" 
                                class="card-checklist-checkbox" 
                                data-item-id="${item.id}"
                                ${item.checked ? 'checked' : ''}
                              >
                              <span class="card-checklist-name ${item.checked ? 'checked' : ''}">${this.escapeHtml(item.name)}</span>
                            </div>
                          `).join('')}
                        </div>
                      ` : ''}
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
        card.addEventListener('click', async (e) => {
          // Don't trigger if clicking the delete button or checklist checkbox
          if (e.target.classList.contains('card-delete-btn')) return;
          if (e.target.classList.contains('card-checklist-checkbox')) return;
          
          const cardId = parseInt(card.getAttribute('data-card-id'));
          // Reload card data to get latest state
          const cardData = await this.getCardData(cardId);
          if (cardData) {
            this.openEditCardModal(cardId, cardData);
          }
        });
      });
      
      // Add event listeners for checklist checkboxes on cards
      document.querySelectorAll('.card-checklist-checkbox').forEach(checkbox => {
        checkbox.addEventListener('click', async (e) => {
          e.stopPropagation(); // Prevent card click event
          const itemId = parseInt(e.target.getAttribute('data-item-id'));
          const checked = e.target.checked;
          await this.updateChecklistItem(itemId, { checked });
          
          // Update the visual state of the text
          const label = e.target.nextElementSibling;
          if (checked) {
            label.classList.add('checked');
          } else {
            label.classList.remove('checked');
          }
          
          // Update the summary
          const card = e.target.closest('.card');
          const summaryElement = card.querySelector('.card-checklist-summary');
          if (summaryElement) {
            const allCheckboxes = card.querySelectorAll('.card-checklist-checkbox');
            const total = allCheckboxes.length;
            const checkedCount = Array.from(allCheckboxes).filter(cb => cb.checked).length;
            const percentage = total > 0 ? Math.round((checkedCount / total) * 100) : 0;
            summaryElement.textContent = `${checkedCount}/${total} (${percentage}%)`;
          }
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
    // Track checklist items to be created
    let pendingChecklistItems = [];
    let checklistVisible = false;
    
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="add-card-modal">
        <div class="modal-content card-modal-content">
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
            
            <div class="checklist-section">
              <div id="checklist-header-container">
                <button type="button" class="btn btn-secondary" id="add-checklist-item-initial-btn">+ Add Checklist</button>
              </div>
              <div id="checklist-content-container" style="display: none;">
                <div class="checklist-header">
                  <h3>Checklist</h3>
                  <span class="checklist-summary" id="checklist-summary">0/0 (0%)</span>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-top-btn">+ Add Item</button>
                <div class="checklist-items" id="new-card-checklist-items"></div>
                <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-bottom-btn">+ Add Item</button>
              </div>
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
    const checklistHeaderContainer = document.getElementById('checklist-header-container');
    const checklistContentContainer = document.getElementById('checklist-content-container');
    const checklistContainer = document.getElementById('new-card-checklist-items');

    // Focus on input
    titleInput.focus();
    
    // Helper to update checklist summary
    const updateChecklistSummary = () => {
      const summaryElement = document.getElementById('checklist-summary');
      if (summaryElement) {
        // Count all items, including those being edited
        const total = pendingChecklistItems.length;
        const checked = pendingChecklistItems.filter(i => i.checked).length;
        const percentage = total > 0 ? Math.round((checked / total) * 100) : 0;
        summaryElement.textContent = `${checked}/${total} (${percentage}%)`;
      }
    };
    
    // Helper to commit pending input
    const commitPendingInput = () => {
      const pendingInput = checklistContainer.querySelector('.checklist-item-input');
      if (pendingInput) {
        const name = pendingInput.value.trim();
        const tempId = parseFloat(pendingInput.getAttribute('data-temp-id'));
        
        if (name) {
          // Find and update the pending item
          const item = pendingChecklistItems.find(i => i.tempId === tempId);
          if (item) {
            item.name = name;
            
            // Replace input with display span
            const itemElement = pendingInput.closest('.checklist-item');
            const nameSpan = document.createElement('span');
            nameSpan.className = 'checklist-item-name';
            nameSpan.textContent = name;
            pendingInput.replaceWith(nameSpan);
            
            // Re-enable dragging
            itemElement.draggable = true;
            
            // Update summary
            updateChecklistSummary();
          }
        } else {
          // Remove empty item
          const index = pendingChecklistItems.findIndex(i => i.tempId === tempId);
          if (index > -1) {
            pendingChecklistItems.splice(index, 1);
          }
          pendingInput.closest('.checklist-item').remove();
          
          if (pendingChecklistItems.length === 0) {
            checklistVisible = false;
            checklistHeaderContainer.style.display = 'block';
            checklistContentContainer.style.display = 'none';
          }
          
          // Update summary
          updateChecklistSummary();
        }
      }
    };
    
    // Show checklist UI with header and top/bottom buttons
    const showChecklistUI = () => {
      if (!checklistVisible) {
        checklistVisible = true;
        checklistHeaderContainer.style.display = 'none';
        checklistContentContainer.style.display = 'block';
      }
    };

    // Helper to add a checklist item with inline input
    const addChecklistItemInline = (insertAtTop = false) => {
      // Show full checklist UI if not visible
      showChecklistUI();
      
      // Commit any pending input first
      commitPendingInput();
      
      const tempId = Date.now() + Math.random();
      const item = {
        name: '',
        checked: false,
        tempId: tempId
      };
      
      if (insertAtTop) {
        pendingChecklistItems.unshift(item);
      } else {
        pendingChecklistItems.push(item);
      }
      
      // Add item to UI with input field
      const itemHtml = `
        <div class="checklist-item" data-temp-id="${tempId}" draggable="false">
          <span class="drag-handle" title="Drag to reorder">☰</span>
          <input type="checkbox" class="checklist-checkbox" data-temp-id="${tempId}">
          <input type="text" class="checklist-item-input" data-temp-id="${tempId}" placeholder="Enter item name...">
          <div class="checklist-item-actions">
            <button type="button" class="checklist-delete-btn-new" data-temp-id="${tempId}" title="Delete">🗑</button>
          </div>
        </div>
      `;
      
      if (insertAtTop) {
        checklistContainer.insertAdjacentHTML('afterbegin', itemHtml);
      } else {
        checklistContainer.insertAdjacentHTML('beforeend', itemHtml);
      }
      
      // Get the newly added elements
      const newInput = checklistContainer.querySelector(`input.checklist-item-input[data-temp-id="${tempId}"]`);
      const checkbox = checklistContainer.querySelector(`input.checklist-checkbox[data-temp-id="${tempId}"]`);
      const deleteBtn = checklistContainer.querySelector(`.checklist-delete-btn-new[data-temp-id="${tempId}"]`);
      
      // Focus the input
      newInput.focus();
      
      // Handle blur to commit
      newInput.addEventListener('blur', () => {
        setTimeout(() => {
          commitPendingInput();
          this.setupNewCardChecklistDragAndDrop(checklistContainer, pendingChecklistItems);
        }, 100);
      });
      
      // Handle Enter key
      newInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          newInput.blur();
        }
      });
      
      // Add checkbox listener
      checkbox.addEventListener('change', (e) => {
        const checklistItem = pendingChecklistItems.find(i => i.tempId === tempId);
        if (checklistItem) {
          checklistItem.checked = e.target.checked;
          updateChecklistSummary();
        }
      });
      
      // Add delete listener
      deleteBtn.addEventListener('click', (e) => {
        const index = pendingChecklistItems.findIndex(i => i.tempId === tempId);
        if (index > -1) {
          pendingChecklistItems.splice(index, 1);
        }
        e.target.closest('.checklist-item').remove();
        
        // Hide checklist UI if no items left
        if (pendingChecklistItems.length === 0) {
          checklistVisible = false;
          checklistHeaderContainer.style.display = 'block';
          checklistContentContainer.style.display = 'none';
        }
        
        // Update summary
        updateChecklistSummary();
      });
      
      // Update summary after adding new item
      updateChecklistSummary();
    };

    // Handle add checklist item buttons
    const addInitialBtn = document.getElementById('add-checklist-item-initial-btn');
    const addTopBtn = document.getElementById('add-checklist-item-top-btn');
    const addBottomBtn = document.getElementById('add-checklist-item-bottom-btn');
    
    if (addInitialBtn) {
      addInitialBtn.addEventListener('click', () => addChecklistItemInline(false));
    }
    if (addTopBtn) {
      addTopBtn.addEventListener('click', () => addChecklistItemInline(true));
    }
    if (addBottomBtn) {
      addBottomBtn.addEventListener('click', () => addChecklistItemInline(false));
    }

    // Handle cancel
    cancelBtn.addEventListener('click', () => {
      modal.remove();
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      // Commit any pending input before submitting
      commitPendingInput();
      
      const title = titleInput.value.trim();
      const description = document.getElementById('card-description').value.trim();
      
      if (title) {
        // Filter out empty checklist items
        const validChecklistItems = pendingChecklistItems.filter(item => item.name && item.name.trim());
        await this.createCard(columnId, title, description, order, validChecklistItems);
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

  async createCard(columnId, title, description, order = null, checklistItems = []) {
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
        // If there are checklist items, create them
        if (checklistItems.length > 0) {
          const cardId = data.card.id;
          for (let i = 0; i < checklistItems.length; i++) {
            const item = checklistItems[i];
            await this.createChecklistItem(cardId, item.name, i);
            // Update the checked state if needed
            if (item.checked) {
              // We need to get the created item's ID first
              const cardData = await this.getCardData(cardId);
              const createdItem = cardData.checklist_items.find(ci => ci.name === item.name && ci.order === i);
              if (createdItem) {
                await this.updateChecklistItem(createdItem.id, { checked: true });
              }
            }
          }
        }
        
        // Reload board to show the new card
        await this.loadBoard();
      } else {
        alert('Failed to create card: ' + data.message);
      }
    } catch (err) {
      alert('Error creating card: ' + err.message);
    }
  }

  findCardById(cardId) {
    for (const column of this.columns) {
      if (column.cards) {
        const card = column.cards.find(c => c.id === cardId);
        if (card) return card;
      }
    }
    return null;
  }

  openEditCardModal(cardId, cardData) {
    const checklistItems = cardData.checklist_items || [];
    const hasChecklist = checklistItems.length > 0;
    
    // Store original values for change detection
    const originalTitle = cardData.title;
    const originalDescription = cardData.description || '';
    const originalChecklistOrder = checklistItems.map(item => item.id);
    
    // Track changes
    let hasUnsavedChanges = false;
    let checklistOrderChanged = false;
    
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="edit-card-modal">
        <div class="modal-content card-modal-content">
          <h2>Edit Card</h2>
          <form id="edit-card-form">
            <div class="form-group">
              <label for="edit-card-title">Title:</label>
              <input type="text" id="edit-card-title" name="edit-card-title" value="${this.escapeHtml(cardData.title)}" required>
            </div>
            <div class="form-group">
              <label for="edit-card-description">Description:</label>
              <textarea id="edit-card-description" name="edit-card-description" rows="4">${this.escapeHtml(cardData.description || '')}</textarea>
            </div>
            
            <div class="checklist-section">
              ${hasChecklist ? `
                <div class="checklist-header">
                  <h3>Checklist</h3>
                  <span class="checklist-summary">${checklistItems.filter(i => i.checked).length}/${checklistItems.length} (${checklistItems.length > 0 ? Math.round((checklistItems.filter(i => i.checked).length / checklistItems.length) * 100) : 0}%)</span>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-top-btn">+ Add Item</button>
                <div class="checklist-items" id="checklist-items">
                  ${checklistItems.map(item => `
                    <div class="checklist-item" data-item-id="${item.id}" data-item-order="${item.order}" draggable="true">
                      <span class="drag-handle" title="Drag to reorder">☰</span>
                      <input type="checkbox" class="checklist-checkbox" data-item-id="${item.id}" ${item.checked ? 'checked' : ''}>
                      <span class="checklist-item-name">${this.escapeHtml(item.name)}</span>
                      <div class="checklist-item-actions">
                        <button type="button" class="checklist-edit-btn" data-item-id="${item.id}" title="Edit">✎</button>
                        <button type="button" class="checklist-delete-btn" data-item-id="${item.id}" title="Delete">🗑</button>
                      </div>
                    </div>
                  `).join('')}
                </div>
                <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-bottom-btn">+ Add Item</button>
              ` : `
                <div id="checklist-header-container">
                  <button type="button" class="btn btn-secondary" id="add-checklist-item-initial-btn">+ Add Checklist</button>
                </div>
                <div id="checklist-content-container" style="display: none;">
                  <div class="checklist-header">
                    <h3>Checklist</h3>
                    <span class="checklist-summary">0/0 (0%)</span>
                  </div>
                  <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-top-btn">+ Add Item</button>
                  <div class="checklist-items" id="checklist-items"></div>
                  <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-bottom-btn">+ Add Item</button>
                </div>
              `}
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

    // Track changes in title and description
    titleInput.addEventListener('input', () => {
      hasUnsavedChanges = titleInput.value.trim() !== originalTitle;
    });
    
    const descriptionInput = document.getElementById('edit-card-description');
    descriptionInput.addEventListener('input', () => {
      hasUnsavedChanges = hasUnsavedChanges || descriptionInput.value.trim() !== originalDescription;
    });

    // Handle cancel with warning if there are unsaved changes
    const handleCancel = () => {
      if (hasUnsavedChanges || checklistOrderChanged) {
        if (confirm('You have unsaved changes. Are you sure you want to cancel?')) {
          modal.remove();
        }
      } else {
        modal.remove();
      }
    };
    
    cancelBtn.addEventListener('click', handleCancel);
    
    // Helper to update edit modal checklist summary
    const updateEditModalSummary = () => {
      const summaryElement = modal.querySelector('.checklist-summary');
      if (summaryElement) {
        const allCheckboxes = modal.querySelectorAll('.checklist-checkbox');
        const total = allCheckboxes.length;
        const checkedCount = Array.from(allCheckboxes).filter(cb => cb.checked).length;
        const percentage = total > 0 ? Math.round((checkedCount / total) * 100) : 0;
        summaryElement.textContent = `${checkedCount}/${total} (${percentage}%)`;
      }
    };

    // Handle checklist item checkbox changes
    document.querySelectorAll('.checklist-checkbox').forEach(checkbox => {
      checkbox.addEventListener('change', async (e) => {
        const itemId = parseInt(e.target.getAttribute('data-item-id'));
        const checked = e.target.checked;
        await this.updateChecklistItem(itemId, { checked });
        
        // Update the summary
        updateEditModalSummary();
      });
    });

    // Handle add checklist item buttons with inline editing
    let checklistVisible = hasChecklist;
    let pendingNewItems = []; // Track new items not yet saved
    
    const showChecklistUI = () => {
      if (!checklistVisible) {
        checklistVisible = true;
        const headerContainer = document.getElementById('checklist-header-container');
        const contentContainer = document.getElementById('checklist-content-container');
        if (headerContainer) headerContainer.style.display = 'none';
        if (contentContainer) contentContainer.style.display = 'block';
      }
    };
    
    const addChecklistItemInline = async (insertAtTop = false) => {
      showChecklistUI();
      
      const tempId = Date.now() + Math.random();
      const checklistContainer = document.getElementById('checklist-items');
      
      // Add to pending list
      pendingNewItems.push({ tempId, insertAtTop, checked: false });
      
      // Add item to UI with input field
      const itemHtml = `
        <div class="checklist-item" data-temp-id="${tempId}" draggable="false">
          <span class="drag-handle" title="Drag to reorder">☰</span>
          <input type="checkbox" class="checklist-checkbox" data-temp-id="${tempId}">
          <input type="text" class="checklist-item-input" data-temp-id="${tempId}" placeholder="Enter item name...">
          <div class="checklist-item-actions">
            <button type="button" class="checklist-delete-btn-temp" data-temp-id="${tempId}" title="Delete">🗑</button>
          </div>
        </div>
      `;
      
      if (insertAtTop) {
        checklistContainer.insertAdjacentHTML('afterbegin', itemHtml);
      } else {
        checklistContainer.insertAdjacentHTML('beforeend', itemHtml);
      }
      
      const newInput = checklistContainer.querySelector(`input.checklist-item-input[data-temp-id="${tempId}"]`);
      const checkbox = checklistContainer.querySelector(`input.checklist-checkbox[data-temp-id="${tempId}"]`);
      const deleteBtn = checklistContainer.querySelector(`.checklist-delete-btn-temp[data-temp-id="${tempId}"]`);
      
      // Add checkbox listener to update summary
      checkbox.addEventListener('change', (e) => {
        const pendingItem = pendingNewItems.find(i => i.tempId === tempId);
        if (pendingItem) {
          pendingItem.checked = e.target.checked;
          updateEditModalSummary();
        }
      });
      
      newInput.focus();
      
      // Update summary immediately after adding item
      updateEditModalSummary();
      
      // Handle blur to commit
      newInput.addEventListener('blur', async () => {
        setTimeout(async () => {
          const name = newInput.value.trim();
          if (name) {
            // Find the pending item and update it
            const pendingItem = pendingNewItems.find(i => i.tempId === tempId);
            if (pendingItem) {
              pendingItem.name = name;
              
              // Replace input with display span
              const itemElement = newInput.closest('.checklist-item');
              const nameSpan = document.createElement('span');
              nameSpan.className = 'checklist-item-name';
              nameSpan.textContent = name;
              newInput.replaceWith(nameSpan);
              
              // Re-enable dragging
              itemElement.draggable = true;
              
              // Re-initialize drag and drop
              this.setupChecklistDragAndDrop(cardId, () => {
                checklistOrderChanged = true;
              });
              
              // Re-attach checkbox listener for this temp item
              const checkbox = itemElement.querySelector('.checklist-checkbox');
              if (checkbox) {
                checkbox.addEventListener('change', (e) => {
                  const pendingItem = pendingNewItems.find(i => i.tempId === tempId);
                  if (pendingItem) {
                    pendingItem.checked = e.target.checked;
                    updateEditModalSummary();
                  }
                });
              }
              
              // Mark as having unsaved changes
              hasUnsavedChanges = true;
            }
          } else {
            // Remove empty item
            const index = pendingNewItems.findIndex(i => i.tempId === tempId);
            if (index > -1) {
              pendingNewItems.splice(index, 1);
            }
            newInput.closest('.checklist-item').remove();
            
            // Update summary after removal
            updateEditModalSummary();
          }
        }, 100);
      });
      
      // Handle Enter key
      newInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          newInput.blur();
        }
      });
      
      // Handle delete
      deleteBtn.addEventListener('click', () => {
        const index = pendingNewItems.findIndex(i => i.tempId === tempId);
        if (index > -1) {
          pendingNewItems.splice(index, 1);
        }
        newInput.closest('.checklist-item').remove();
      });
    };

    const addTopBtn = document.getElementById('add-checklist-item-top-btn');
    const addBottomBtn = document.getElementById('add-checklist-item-bottom-btn');
    const addInitialBtn = document.getElementById('add-checklist-item-initial-btn');

    if (addTopBtn) addTopBtn.addEventListener('click', () => addChecklistItemInline(true));
    if (addBottomBtn) addBottomBtn.addEventListener('click', () => addChecklistItemInline(false));
    if (addInitialBtn) addInitialBtn.addEventListener('click', () => addChecklistItemInline(false));

    // Handle drag and drop for reordering
    this.setupChecklistDragAndDrop(cardId, () => {
      // Callback when order changes
      checklistOrderChanged = true;
    });

    // Handle edit checklist item buttons
    document.querySelectorAll('.checklist-edit-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const itemId = parseInt(e.target.getAttribute('data-item-id'));
        const itemElement = e.target.closest('.checklist-item');
        const currentName = itemElement.querySelector('.checklist-item-name').textContent;
        const newName = prompt('Edit checklist item:', currentName);
        if (newName && newName.trim() && newName.trim() !== currentName) {
          await this.updateChecklistItem(itemId, { name: newName.trim() });
          modal.remove();
          const updatedCard = await this.getCardData(cardId);
          if (updatedCard) {
            this.openEditCardModal(cardId, updatedCard);
          }
        }
      });
    });

    // Handle delete checklist item buttons
    document.querySelectorAll('.checklist-delete-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        if (confirm('Delete this checklist item?')) {
          const itemId = parseInt(e.target.getAttribute('data-item-id'));
          await this.deleteChecklistItem(itemId);
          modal.remove();
          const updatedCard = await this.getCardData(cardId);
          if (updatedCard) {
            this.openEditCardModal(cardId, updatedCard);
          }
        }
      });
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const title = titleInput.value.trim();
      const description = document.getElementById('edit-card-description').value.trim();
      
      if (title) {
        // First update the card
        await this.updateCard(cardId, title, description);
        
        // Then save any pending new checklist items in their current DOM order
        const checklistContainer = document.getElementById('checklist-items');
        const allItems = Array.from(checklistContainer.querySelectorAll('.checklist-item'));
        
        for (let i = 0; i < allItems.length; i++) {
          const el = allItems[i];
          const tempId = el.getAttribute('data-temp-id');
          
          // Check if this is a pending new item
          if (tempId) {
            const pendingItem = pendingNewItems.find(item => item.tempId === parseFloat(tempId));
            if (pendingItem && pendingItem.name) {
              // Save with the current position index and checked state
              await this.createChecklistItem(cardId, pendingItem.name, i, pendingItem.checked);
            }
          }
        }
        
        hasUnsavedChanges = false;
        checklistOrderChanged = false;
        modal.remove();
        
        // Reload board to show updated data
        await this.loadBoard();
      }
    });

    // Close modal on background click with warning
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        handleCancel();
      }
    });
  }

  async getCardData(cardId) {
    // Reload board data to get fresh card info
    await this.loadBoard();
    return this.findCardById(cardId);
  }

  async createChecklistItem(cardId, name, order = null, checked = false) {
    try {
      const body = { name, checked };
      if (order !== null) {
        body.order = order;
      }
      
      const response = await fetch(`/api/cards/${cardId}/checklist-items`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (!data.success) {
        alert('Failed to create checklist item: ' + data.message);
      }
    } catch (err) {
      alert('Error creating checklist item: ' + err.message);
    }
  }

  async updateChecklistItem(itemId, updates) {
    try {
      const response = await fetch(`/api/checklist-items/${itemId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });

      const data = await response.json();

      if (!data.success) {
        alert('Failed to update checklist item: ' + data.message);
      }
    } catch (err) {
      alert('Error updating checklist item: ' + err.message);
    }
  }

  async deleteChecklistItem(itemId) {
    try {
      const response = await fetch(`/api/checklist-items/${itemId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (!data.success) {
        alert('Failed to delete checklist item: ' + data.message);
      }
    } catch (err) {
      alert('Error deleting checklist item: ' + err.message);
    }
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

  setupChecklistDragAndDrop(cardId, onOrderChange) {
    const checklistItems = document.querySelectorAll('.checklist-item');
    let draggedElement = null;

    checklistItems.forEach(item => {
      item.addEventListener('dragstart', (e) => {
        draggedElement = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      item.addEventListener('dragend', async (e) => {
        item.classList.remove('dragging');
        
        // Get all items in current order
        const container = document.getElementById('checklist-items');
        const allItems = Array.from(container.querySelectorAll('.checklist-item'));
        
        // Update order for all items based on their new position
        // Only update items that have been saved (have data-item-id)
        const updates = allItems
          .map((el, index) => {
            const itemId = el.getAttribute('data-item-id');
            if (itemId && itemId !== 'null') {
              return {
                id: parseInt(itemId),
                order: index
              };
            }
            return null;
          })
          .filter(update => update !== null);
        
        // Notify that order changed
        if (onOrderChange) {
          onOrderChange();
        }
        
        // Send updates to API
        for (const update of updates) {
          await this.updateChecklistItem(update.id, { order: update.order });
        }
        
        draggedElement = null;
      });

      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        
        const container = document.getElementById('checklist-items');
        const afterElement = this.getDragAfterElement(container, e.clientY);
        
        if (afterElement == null) {
          container.appendChild(draggedElement);
        } else {
          container.insertBefore(draggedElement, afterElement);
        }
      });
    });
  }

  getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.checklist-item:not(.dragging)')];
    
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

  setupNewCardChecklistDragAndDrop(container, pendingChecklistItems) {
    const checklistItems = container.querySelectorAll('.checklist-item');
    let draggedElement = null;

    checklistItems.forEach(item => {
      // Remove old listeners by cloning and replacing
      const newItem = item.cloneNode(true);
      item.parentNode.replaceChild(newItem, item);
    });

    // Re-query after replacing
    container.querySelectorAll('.checklist-item').forEach(item => {
      item.addEventListener('dragstart', (e) => {
        draggedElement = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      item.addEventListener('dragend', (e) => {
        item.classList.remove('dragging');
        
        // Update pendingChecklistItems array to match new order
        const allItems = Array.from(container.querySelectorAll('.checklist-item'));
        const newOrder = allItems.map(el => {
          const tempId = parseFloat(el.getAttribute('data-temp-id'));
          return pendingChecklistItems.find(i => i.tempId === tempId);
        }).filter(Boolean);
        
        // Update the array in place
        pendingChecklistItems.length = 0;
        pendingChecklistItems.push(...newOrder);
        
        draggedElement = null;
      });

      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        
        const afterElement = this.getDragAfterElement(container, e.clientY);
        
        if (afterElement == null) {
          container.appendChild(draggedElement);
        } else {
          container.insertBefore(draggedElement, afterElement);
        }
      });

      // Re-attach checkbox listener
      const checkbox = item.querySelector('.checklist-checkbox');
      const tempId = parseFloat(checkbox.getAttribute('data-temp-id'));
      checkbox.addEventListener('change', (e) => {
        const checklistItem = pendingChecklistItems.find(i => i.tempId === tempId);
        if (checklistItem) {
          checklistItem.checked = e.target.checked;
          // Update summary in the modal
          const summaryElement = document.getElementById('checklist-summary');
          if (summaryElement) {
            const total = pendingChecklistItems.length;
            const checked = pendingChecklistItems.filter(i => i.checked).length;
            const percentage = total > 0 ? Math.round((checked / total) * 100) : 0;
            summaryElement.textContent = `${checked}/${total} (${percentage}%)`;
          }
        }
      });

      // Re-attach delete listener
      const deleteBtn = item.querySelector('.checklist-delete-btn-new');
      deleteBtn.addEventListener('click', (e) => {
        const tempId = parseFloat(e.target.getAttribute('data-temp-id'));
        const index = pendingChecklistItems.findIndex(i => i.tempId === tempId);
        if (index > -1) {
          pendingChecklistItems.splice(index, 1);
        }
        e.target.closest('.checklist-item').remove();
        
        // Hide container if no items left
        if (pendingChecklistItems.length === 0) {
          container.style.display = 'none';
        }
      });
    });
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
