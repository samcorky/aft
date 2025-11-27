// Board detail page functionality

/**
 * Calculate the percentage of checked items in a checklist
 * @param {Array} items - Array of checklist items with 'checked' property
 * @returns {number} Percentage (0-100) of checked items
 */
function calculateChecklistPercentage(items) {
  if (!items || items.length === 0) return 0;
  const checkedCount = items.filter(i => i.checked).length;
  return Math.round((checkedCount / items.length) * 100);
}

/**
 * Convert URLs in text to clickable hyperlinks
 * @param {string} text - Text that may contain URLs
 * @returns {string} HTML with URLs converted to links
 */
function linkifyUrls(text) {
  if (!text) return '';
  
  // More robust URL regex that handles parentheses and various URL formats
  // Matches: protocol, domain, path with balanced parentheses, query strings, fragments
  const urlRegex = /https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_\+.~#?&\/=]*/gi;
  
  return text.replace(urlRegex, (url) => {
    // Clean up trailing punctuation, but preserve closing parentheses if there's a matching opening one
    let cleanUrl = url;
    
    // Count parentheses in the URL
    const openParens = (cleanUrl.match(/\(/g) || []).length;
    const closeParens = (cleanUrl.match(/\)/g) || []).length;
    
    // If unbalanced closing parens at the end, remove them
    while (cleanUrl.endsWith(')') && (cleanUrl.match(/\)/g) || []).length > (cleanUrl.match(/\(/g) || []).length) {
      cleanUrl = cleanUrl.slice(0, -1);
    }
    
    // Remove other trailing punctuation
    cleanUrl = cleanUrl.replace(/[.,;!?]+$/, '');
    
    // Escape the URL for use in HTML attribute to prevent XSS
    const escapedUrl = cleanUrl.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    // Escape the display text for HTML context
    const displayUrl = cleanUrl.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<a href="${escapedUrl}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${displayUrl}</a>`;
  });
}

// Shared checklist management helper
class ChecklistManager {
  constructor(container, pendingItems, options = {}) {
    this.container = container;
    this.pendingItems = pendingItems;
    this.updateSummary = options.updateSummary || (() => {});
    this.onItemCommitted = options.onItemCommitted || (() => {});
    this.deleteButtonClass = options.deleteButtonClass || 'checklist-delete-btn-temp';
    
    // Set up event delegation
    this.setupEventDelegation();
  }

  setupEventDelegation() {
    // Single event listener on container for all checkboxes
    this.container.addEventListener('change', (e) => {
      if (e.target.classList.contains('checklist-checkbox')) {
        const tempId = Number(e.target.getAttribute('data-temp-id'));
        const item = this.pendingItems.find(i => i.tempId === tempId);
        if (item) {
          item.checked = e.target.checked;
          this.updateSummary();
        }
      }
    });

    // Single event listener for delete buttons
    this.container.addEventListener('click', (e) => {
      if (e.target.matches(`.${this.deleteButtonClass}`)) {
        const tempId = Number(e.target.getAttribute('data-temp-id'));
        const index = this.pendingItems.findIndex(i => i.tempId === tempId);
        if (index > -1) {
          this.pendingItems.splice(index, 1);
        }
        e.target.closest('.checklist-item').remove();
        this.updateSummary();
      }
    });

    // Single event listener for blur on inputs
    this.container.addEventListener('blur', (e) => {
      if (e.target.classList.contains('checklist-item-input')) {
        // Defer to next event loop cycle to allow other events (like delete button clicks) to process first
        setTimeout(() => this.commitInput(e.target), 0);
      }
    }, true); // Use capture to catch blur

    // Single event listener for Enter key on inputs
    this.container.addEventListener('keydown', (e) => {
      if (e.target.classList.contains('checklist-item-input') && e.key === 'Enter') {
        e.preventDefault();
        e.target.blur();
      }
    });
  }

  commitInput(inputElement) {
    if (!inputElement || !inputElement.classList.contains('checklist-item-input')) return;
    
    const name = inputElement.value.trim();
    const tempId = Number(inputElement.getAttribute('data-temp-id'));
    
    if (name) {
      const item = this.pendingItems.find(i => i.tempId === tempId);
      if (item) {
        item.name = name;
        
        // Replace input with display span
        const itemElement = inputElement.closest('.checklist-item');
        const nameSpan = document.createElement('span');
        nameSpan.className = 'checklist-item-name';
        nameSpan.textContent = name;
        inputElement.replaceWith(nameSpan);
        
        // Re-enable dragging
        itemElement.draggable = true;
        
        this.updateSummary();
        this.onItemCommitted(tempId);
      }
    } else {
      // Remove empty item
      const index = this.pendingItems.findIndex(i => i.tempId === tempId);
      if (index > -1) {
        this.pendingItems.splice(index, 1);
      }
      inputElement.closest('.checklist-item').remove();
      this.updateSummary();
    }
  }

  addItem(insertAtTop = false) {
    const tempId = Date.now() + Math.random();
    const item = {
      name: '',
      checked: false,
      tempId: tempId
    };

    if (insertAtTop) {
      this.pendingItems.unshift(item);
    } else {
      this.pendingItems.push(item);
    }

    // Add item to UI with input field
    const itemHtml = `
      <div class="checklist-item" data-temp-id="${tempId}" draggable="false">
        <span class="drag-handle" title="Drag to reorder">&#9776;</span>
        <input type="checkbox" class="checklist-checkbox" data-temp-id="${tempId}">
        <input type="text" class="checklist-item-input" data-temp-id="${tempId}" placeholder="Enter item name...">
        <div class="checklist-item-actions">
          <button type="button" class="${this.deleteButtonClass}" data-temp-id="${tempId}" title="Delete">🗑</button>
        </div>
      </div>
    `;

    if (insertAtTop) {
      this.container.insertAdjacentHTML('afterbegin', itemHtml);
    } else {
      this.container.insertAdjacentHTML('beforeend', itemHtml);
    }

    // Focus the newly added input
    const newInput = this.container.querySelector(`input.checklist-item-input[data-temp-id="${tempId}"]`);
    if (newInput) {
      newInput.focus();
    }

    this.updateSummary();
  }
}

class BoardManager {
  constructor() {
    this.container = document.getElementById('board-container');
    this.boardId = null;
    this.boardName = '';
    this.columns = [];
    this.hoveredColumnId = null;
    this.lastUsedColumnId = null;
    this.showArchived = false; // Track whether to show archived or active cards
    this.keyboardHandler = this.handleKeydown.bind(this);
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
    this.setupKeyboardShortcuts();
  }

  render() {
    this.container.innerHTML = `
      <div class="loading-board">Loading board...</div>
    `;
  }

  async loadBoard() {
    try {
      // Load board with nested structure (board -> columns -> cards)
      // Add archived parameter to filter cards based on showArchived state
      const archivedParam = this.showArchived ? 'true' : 'false';
      const response = await fetch(`/api/boards/${this.boardId}/cards?archived=${archivedParam}`);
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

  setupKeyboardShortcuts() {
    document.addEventListener('keydown', this.keyboardHandler);
  }

  handleKeydown(e) {
    // Don't trigger shortcuts if user is typing in an input/textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      return;
    }

    // Don't trigger if inside a modal
    if (e.target.closest('.modal')) {
      return;
    }

    // 'n' key - add card at top of column
    if (e.key === 'n' || e.key === 'N') {
      e.preventDefault();
      const columnId = this.hoveredColumnId || this.lastUsedColumnId;
      if (columnId) {
        this.openAddCardModal(columnId, 0); // 0 = top
      }
    }

    // 'm' key - add card at bottom of column
    if (e.key === 'm' || e.key === 'M') {
      e.preventDefault();
      const columnId = this.hoveredColumnId || this.lastUsedColumnId;
      if (columnId) {
        this.openAddCardModal(columnId); // default = bottom
      }
    }
  }

  cleanup() {
    // Remove event listener to prevent memory leaks
    document.removeEventListener('keydown', this.keyboardHandler);
  }

  async toggleArchiveView() {
    // Toggle the showArchived state
    this.showArchived = !this.showArchived;
    // Reload board with new archived parameter
    await this.loadBoard();
  }

  renderBoard() {
    // Hide archive toggle in header when there are no columns
    const archiveToggleWrapper = document.getElementById('archive-toggle-wrapper');
    
    if (this.columns.length === 0) {
      if (archiveToggleWrapper) {
        archiveToggleWrapper.style.display = 'none';
      }
      
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
                  <h4>${this.escapeHtml(column.name)} <span class="card-count">(${column.cards ? column.cards.length : 0})</span></h4>
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
                    <div class="card ${card.archived ? 'archived-card' : ''}" draggable="true" data-card-id="${card.id}" data-column-id="${column.id}" data-order="${card.order}" data-archived="${card.archived}">
                      <div class="card-action-buttons">
                        ${card.archived ? 
                          `<button class="card-unarchive-btn" data-card-id="${card.id}" title="Unarchive card">📂</button>` :
                          `<button class="card-archive-btn" data-card-id="${card.id}" title="Archive card">🗄️</button>`
                        }
                        <button class="card-delete-btn" data-card-id="${card.id}" title="Delete card">×</button>
                      </div>
                      <h5 class="card-title">${linkifyUrls(this.escapeHtml(card.title))}</h5>
                      <p class="card-description">${linkifyUrls(this.escapeHtml(card.description))}</p>
                      ${card.checklist_items && card.checklist_items.length > 0 ? `
                        <div class="card-checklist">
                          <div class="card-checklist-summary">
                            ${card.checklist_items.filter(i => i.checked).length}/${card.checklist_items.length} (${calculateChecklistPercentage(card.checklist_items)}%)
                          </div>
                          ${card.checklist_items.map(item => `
                            <div class="card-checklist-item">
                              <input 
                                type="checkbox" 
                                class="card-checklist-checkbox" 
                                data-item-id="${item.id}"
                                ${item.checked ? 'checked' : ''}
                              >
                              <span class="card-checklist-name ${item.checked ? 'checked' : ''}">${linkifyUrls(this.escapeHtml(item.name))}</span>
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
      
      // Show and set up archive toggle in header
      const archiveToggleWrapper = document.getElementById('archive-toggle-wrapper');
      const archiveToggleCheckbox = document.getElementById('archive-toggle-checkbox');
      
      if (archiveToggleWrapper && archiveToggleCheckbox) {
        // Show the toggle
        archiveToggleWrapper.style.display = 'flex';
        
        // Set initial state
        archiveToggleCheckbox.checked = this.showArchived;
        
        // Remove any existing listener by cloning and replacing the element
        const newCheckbox = archiveToggleCheckbox.cloneNode(true);
        archiveToggleCheckbox.parentNode.replaceChild(newCheckbox, archiveToggleCheckbox);
        
        // Set initial state on the new checkbox
        newCheckbox.checked = this.showArchived;
        
        // Add event listener to the new checkbox
        newCheckbox.addEventListener('change', () => this.toggleArchiveView());
      }
      
      // Add event listener for add column button next to columns
      document.getElementById('add-column-inline-btn').addEventListener('click', () => this.openAddColumnModal());
      
      // Add hover listeners for columns to track which column is hovered
      document.querySelectorAll('.column').forEach(column => {
        column.addEventListener('mouseenter', (e) => {
          const columnId = parseInt(e.currentTarget.getAttribute('data-column-id'));
          if (!isNaN(columnId)) {
            this.hoveredColumnId = columnId;
          }
        });
        column.addEventListener('mouseleave', () => {
          this.hoveredColumnId = null;
        });
      });
      
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
            const items = Array.from(allCheckboxes).map(cb => ({ checked: cb.checked }));
            const percentage = calculateChecklistPercentage(items);
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
      
      // Add event listeners for archive card buttons
      document.querySelectorAll('.card-archive-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.target.getAttribute('data-card-id'));
          this.archiveCard(cardId);
        });
      });
      
      // Add event listeners for unarchive card buttons
      document.querySelectorAll('.card-unarchive-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.target.getAttribute('data-card-id'));
          this.unarchiveCard(cardId);
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
        
        if (!dragging) return;
        
        if (!afterElement) {
          // Append at the end (before the add card button if it exists)
          const addCardBtn = columnContainer.querySelector('.add-card-btn');
          if (addCardBtn) {
            columnContainer.insertBefore(dragging, addCardBtn);
          } else {
            columnContainer.appendChild(dragging);
          }
        } else {
          columnContainer.insertBefore(dragging, afterElement);
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
        // Reload board to update card counts
        await this.loadBoard();
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
    // Track the last used column for keyboard shortcuts
    this.lastUsedColumnId = columnId;
    
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
        const total = pendingChecklistItems.length;
        const checked = pendingChecklistItems.filter(i => i.checked).length;
        const percentage = calculateChecklistPercentage(pendingChecklistItems);
        summaryElement.textContent = `${checked}/${total} (${percentage}%)`;
      }
    };
    
    // Set up drag and drop with event delegation (only needs to be called once)
    this.setupNewCardChecklistDragAndDrop(checklistContainer, pendingChecklistItems);
    
    // Create checklist manager with event delegation
    const checklistManager = new ChecklistManager(checklistContainer, pendingChecklistItems, {
      updateSummary: updateChecklistSummary,
      deleteButtonClass: 'checklist-delete-btn-new'
    });
    
    // Show checklist UI with header and top/bottom buttons
    const showChecklistUI = () => {
      if (!checklistVisible) {
        checklistVisible = true;
        checklistHeaderContainer.style.display = 'none';
        checklistContentContainer.style.display = 'block';
      }
    };

    // Handle add checklist item buttons
    const addInitialBtn = document.getElementById('add-checklist-item-initial-btn');
    const addTopBtn = document.getElementById('add-checklist-item-top-btn');
    const addBottomBtn = document.getElementById('add-checklist-item-bottom-btn');
    
    if (addInitialBtn) {
      addInitialBtn.addEventListener('click', () => {
        showChecklistUI();
        checklistManager.addItem(false);
      });
    }
    if (addTopBtn) {
      addTopBtn.addEventListener('click', () => {
        showChecklistUI();
        checklistManager.addItem(true);
      });
    }
    if (addBottomBtn) {
      addBottomBtn.addEventListener('click', () => {
        showChecklistUI();
        checklistManager.addItem(false);
      });
    }

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
        // TODO: Consider creating a batch endpoint POST /api/cards/batch that accepts card + checklist items
        // in a single request to avoid multiple sequential API calls and ensure atomicity.
        // This would prevent race conditions and improve performance.
        // If there are checklist items, create them with their checked state
        if (checklistItems.length > 0) {
          const cardId = data.card.id;
          for (let i = 0; i < checklistItems.length; i++) {
            const item = checklistItems[i];
            // Pass checked state directly to createChecklistItem
            await this.createChecklistItem(cardId, item.name, i, item.checked || false);
          }
        }
        
        // Reload board once at the end to show the new card
        await this.loadBoard();
      } else {
        alert('Failed to create card: ' + data.message);
      }
    } catch (err) {
      alert('Error creating card: ' + err.message);
    }
  }

  openEditCardModal(cardId, cardData) {
    const checklistItems = cardData.checklist_items || [];
    const comments = cardData.comments || [];
    const hasChecklist = checklistItems.length > 0;
    const hasComments = comments.length > 0;
    
    // Store original values for change detection
    const originalTitle = cardData.title;
    const originalDescription = cardData.description || '';
    
    // Track changes
    let hasUnsavedChanges = false;
    let checklistOrderChanged = false;
    
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="edit-card-modal">
        <div class="modal-content card-modal-content">
          <div class="modal-header">
            <h2>Edit Card</h2>
            <div class="modal-header-actions">
              ${cardData.archived ? 
                `<button type="button" class="btn btn-secondary" id="unarchive-card-detail-btn" data-card-id="${cardData.id}">📂 Unarchive</button>` :
                `<button type="button" class="btn btn-secondary" id="archive-card-detail-btn" data-card-id="${cardData.id}">🗄️ Archive</button>`
              }
              <button type="button" class="btn btn-secondary" id="cancel-edit-card-btn">Cancel</button>
              <button type="submit" form="edit-card-form" class="btn btn-primary">Save</button>
            </div>
          </div>
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
                  <span class="checklist-summary">${checklistItems.filter(i => i.checked).length}/${checklistItems.length} (${calculateChecklistPercentage(checklistItems)}%)</span>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-top-btn">+ Add Item</button>
                <div class="checklist-items" id="checklist-items">
                  ${checklistItems.map(item => `
                    <div class="checklist-item" data-item-id="${item.id}" data-item-order="${item.order}" draggable="true">
                      <span class="drag-handle" title="Drag to reorder">&#9776;</span>
                      <input type="checkbox" class="checklist-checkbox" data-item-id="${item.id}" ${item.checked ? 'checked' : ''}>
                      <span class="checklist-item-name">${linkifyUrls(this.escapeHtml(item.name))}</span>
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
            
            <div class="comments-section">
              <div class="comments-header">
                <h3>Comments</h3>
              </div>
              <div class="comment-input-container">
                <textarea id="new-comment-input" placeholder="Add a comment..." rows="3" maxlength="50000"></textarea>
                <button type="button" class="btn btn-primary btn-sm" id="post-comment-btn">Post Comment</button>
              </div>
              <div class="comments-list" id="comments-list">
                ${hasComments ? comments.map(comment => this.generateCommentHtml(comment)).join('') : '<p class="no-comments">No comments yet.</p>'}
              </div>
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
    const archiveBtn = document.getElementById('archive-card-detail-btn');
    const unarchiveBtn = document.getElementById('unarchive-card-detail-btn');
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

    // Helper to check for unposted comment
    const hasUnpostedComment = () => {
      const commentInput = document.getElementById('new-comment-input');
      return commentInput && commentInput.value.trim().length > 0;
    };

    // Handle archive button
    if (archiveBtn) {
      archiveBtn.addEventListener('click', async () => {
        modal.remove();
        await this.archiveCard(cardId);
      });
    }

    // Handle unarchive button
    if (unarchiveBtn) {
      unarchiveBtn.addEventListener('click', async () => {
        modal.remove();
        await this.unarchiveCard(cardId);
      });
    }

    // Handle cancel with warning if there are unsaved changes
    const handleCancel = () => {
      if (hasUnpostedComment()) {
        if (!confirm('You have an unposted comment. Are you sure you want to cancel?')) {
          return;
        }
      }
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
        const items = Array.from(allCheckboxes).map(cb => ({ checked: cb.checked }));
        const percentage = calculateChecklistPercentage(items);
        summaryElement.textContent = `${checkedCount}/${total} (${percentage}%)`;
      }
    };

    // Handle checklist item checkbox changes (defer save until form submit)
    let checklistCheckboxChanges = new Map(); // Track checkbox changes: itemId -> checked state
    
    document.querySelectorAll('.checklist-checkbox').forEach(checkbox => {
      checkbox.addEventListener('change', (e) => {
        const itemId = parseInt(e.target.getAttribute('data-item-id'));
        const checked = e.target.checked;
        checklistCheckboxChanges.set(itemId, checked);
        hasUnsavedChanges = true;
        
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
    
    const checklistContainer = document.getElementById('checklist-items');
    
    // Set up drag and drop once with event delegation
    this.setupChecklistDragAndDrop(cardId, () => {
      checklistOrderChanged = true;
    });
    
    // Create checklist manager for new items with event delegation
    const checklistManager = new ChecklistManager(checklistContainer, pendingNewItems, {
      updateSummary: updateEditModalSummary,
      deleteButtonClass: 'checklist-delete-btn-temp',
      onItemCommitted: () => {
        hasUnsavedChanges = true;
      }
    });

    const addTopBtn = document.getElementById('add-checklist-item-top-btn');
    const addBottomBtn = document.getElementById('add-checklist-item-bottom-btn');
    const addInitialBtn = document.getElementById('add-checklist-item-initial-btn');

    if (addTopBtn) {
      addTopBtn.addEventListener('click', () => {
        showChecklistUI();
        checklistManager.addItem(true);
      });
    }
    if (addBottomBtn) {
      addBottomBtn.addEventListener('click', () => {
        showChecklistUI();
        checklistManager.addItem(false);
      });
    }
    if (addInitialBtn) {
      addInitialBtn.addEventListener('click', () => {
        showChecklistUI();
        checklistManager.addItem(false);
      });
    }

    // Handle edit checklist item buttons - inline editing
    document.querySelectorAll('.checklist-edit-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const itemId = parseInt(e.target.getAttribute('data-item-id'));
        const itemElement = e.target.closest('.checklist-item');
        const nameSpan = itemElement.querySelector('.checklist-item-name');
        const currentName = nameSpan.textContent;
        
        // Replace span with input for inline editing
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'checklist-item-input';
        input.value = currentName;
        input.setAttribute('data-item-id', itemId);
        nameSpan.replaceWith(input);
        input.focus();
        input.select();
        
        // Disable dragging while editing
        itemElement.draggable = false;
        
        const saveEdit = async () => {
          const newName = input.value.trim();
          if (newName && newName !== currentName) {
            await this.updateChecklistItem(itemId, { name: newName });
            const newNameSpan = document.createElement('span');
            newNameSpan.className = 'checklist-item-name';
            newNameSpan.textContent = newName;
            input.replaceWith(newNameSpan);
            hasUnsavedChanges = false; // This action was already saved
          } else if (newName) {
            // No change, just restore
            const newNameSpan = document.createElement('span');
            newNameSpan.className = 'checklist-item-name';
            newNameSpan.textContent = currentName;
            input.replaceWith(newNameSpan);
          } else {
            // Empty name, restore original
            const newNameSpan = document.createElement('span');
            newNameSpan.className = 'checklist-item-name';
            newNameSpan.textContent = currentName;
            input.replaceWith(newNameSpan);
          }
          // Re-enable dragging
          itemElement.draggable = true;
        };
        
        // Save on blur
        input.addEventListener('blur', () => {
          setTimeout(saveEdit, 100);
        });
        
        // Save on Enter
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
          } else if (e.key === 'Escape') {
            // Cancel edit
            const newNameSpan = document.createElement('span');
            newNameSpan.className = 'checklist-item-name';
            newNameSpan.textContent = currentName;
            input.replaceWith(newNameSpan);
            itemElement.draggable = true;
          }
        });
      });
    });

    // Handle delete checklist item buttons
    document.querySelectorAll('.checklist-delete-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        if (confirm('Delete this checklist item?')) {
          const itemId = parseInt(e.target.getAttribute('data-item-id'));
          await this.deleteChecklistItem(itemId);
          // Remove the item element in-place instead of closing modal
          const itemElement = e.target.closest('.checklist-item');
          itemElement.remove();
          // Update summary after deletion
          updateEditModalSummary();
          hasUnsavedChanges = false; // This action was already saved
          
          // Update the card in board view to reflect deletion
          const cardElement = document.querySelector(`.card[data-card-id="${cardId}"]`);
          if (cardElement) {
            const checklistElement = cardElement.querySelector('.card-checklist');
            const remainingItems = modal.querySelectorAll('.checklist-item').length;
            
            // If no items left, remove the entire checklist section
            if (remainingItems === 0 && checklistElement) {
              checklistElement.remove();
            } else if (checklistElement) {
              // Update the checklist item count and remove this specific item from board view
              const boardChecklistItem = checklistElement.querySelector(`input[data-item-id="${itemId}"]`)?.closest('.card-checklist-item');
              if (boardChecklistItem) {
                boardChecklistItem.remove();
              }
              
              // Update summary in board view
              const summaryElement = checklistElement.querySelector('.card-checklist-summary');
              if (summaryElement) {
                const boardCheckboxes = checklistElement.querySelectorAll('.card-checklist-checkbox');
                const total = boardCheckboxes.length;
                const checked = Array.from(boardCheckboxes).filter(cb => cb.checked).length;
                const items = Array.from(boardCheckboxes).map(cb => ({ checked: cb.checked }));
                const percentage = calculateChecklistPercentage(items);
                summaryElement.textContent = `${checked}/${total} (${percentage}%)`;
              }
            }
          }
        }
      });
    });

    // Handle post comment button
    const postCommentBtn = document.getElementById('post-comment-btn');
    const newCommentInput = document.getElementById('new-comment-input');
    const MAX_COMMENT_LENGTH = 50000;
    
    postCommentBtn.addEventListener('click', async () => {
      const commentText = newCommentInput.value.trim();
      if (!commentText) return;
      
      // Validate comment length on client side
      if (commentText.length > MAX_COMMENT_LENGTH) {
        alert(`Comment is too long. Maximum length is ${MAX_COMMENT_LENGTH.toLocaleString()} characters. Your comment is ${commentText.length.toLocaleString()} characters.`);
        return;
      }
      
      try {
        const response = await fetch(`/api/cards/${cardId}/comments`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ comment: commentText })
        });
        
        const data = await response.json();
        
        if (data.success) {
          // Add the new comment to the UI at the top of the list
          const commentsList = document.getElementById('comments-list');
          const noCommentsMsg = commentsList.querySelector('.no-comments');
          if (noCommentsMsg) {
            noCommentsMsg.remove();
          }
          
          const isLongComment = data.comment.comment.split('\n').length > 10 || data.comment.comment.length > 500;
          const newCommentHtml = this.generateCommentHtml(data.comment);
          
          commentsList.insertAdjacentHTML('afterbegin', newCommentHtml);
          
          // Attach delete handler to new comment
          const newComment = commentsList.querySelector(`[data-comment-id="${data.comment.id}"]`);
          const deleteBtn = newComment.querySelector('.comment-delete-btn');
          deleteBtn.addEventListener('click', () => this.deleteCommentHandler(deleteBtn, cardId));
          
          // Attach read more handler if it's a long comment
          if (isLongComment) {
            const readMoreBtn = newComment.querySelector('.comment-read-more');
            readMoreBtn.addEventListener('click', (e) => {
              const commentText = newComment.querySelector('.comment-text');
              this.toggleCommentCollapse(commentText, e.target);
            });
          }
          
          // Clear input
          newCommentInput.value = '';
        } else {
          alert('Failed to post comment: ' + data.message);
        }
      } catch (err) {
        console.error('Error posting comment:', err);
        alert('Error posting comment');
      }
    });
    
    // Handle delete comment buttons
    document.querySelectorAll('.comment-delete-btn').forEach(btn => {
      btn.addEventListener('click', () => this.deleteCommentHandler(btn, cardId));
    });
    
    // Handle read more buttons
    document.querySelectorAll('.comment-read-more').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const commentId = e.target.getAttribute('data-comment-id');
        const commentText = document.querySelector(`.comment-text[data-comment-id="${commentId}"]`);
        this.toggleCommentCollapse(commentText, e.target);
      });
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      // Check for unposted comment
      if (hasUnpostedComment()) {
        if (!confirm('You have an unposted comment. Are you sure you want to save without posting it?')) {
          return;
        }
      }
      
      const title = titleInput.value.trim();
      const description = document.getElementById('edit-card-description').value.trim();
      
      if (title) {
        // TODO: PERFORMANCE - Consider creating a batch endpoint PATCH /api/cards/{id}/batch that accepts
        // card updates + checklist item changes (creates, updates, deletes, reorders) in a single
        // transaction. This would:
        // - Reduce network overhead (1 request instead of N)
        // - Ensure atomicity (all changes succeed or fail together)
        // - Prevent race conditions from interleaved requests
        // - Improve performance on slow connections
        // - Use database transactions for consistency
        // - Support bulk updates (e.g., UPDATE checklist_items SET ... WHERE id IN (...))
        // Current implementation: N sequential API calls (can be slow for cards with many checklist items)
        
        // 1. Update the card
        await this.updateCard(cardId, title, description);
        
        // 2. Save checkbox changes for existing items
        // PERF: Sequential updates - could be batched
        for (const [itemId, checked] of checklistCheckboxChanges.entries()) {
          await this.updateChecklistItem(itemId, { checked });
        }
        
        // 3. Save any pending new checklist items in their current DOM order
        const checklistContainer = document.getElementById('checklist-items');
        const allItems = Array.from(checklistContainer.querySelectorAll('.checklist-item'));
        
        for (let i = 0; i < allItems.length; i++) {
          const el = allItems[i];
          const tempId = el.getAttribute('data-temp-id');
          
          // Check if this is a pending new item
          if (tempId) {
            const pendingItem = pendingNewItems.find(item => item.tempId === Number(tempId));
            if (pendingItem && pendingItem.name) {
              // Save with the current position index and checked state
              await this.createChecklistItem(cardId, pendingItem.name, i, pendingItem.checked);
            }
          }
        }
        
        // 4. Update order for existing items if changed
        // PERF: Sequential updates - could use bulk update endpoint
        if (checklistOrderChanged) {
          for (let i = 0; i < allItems.length; i++) {
            const el = allItems[i];
            const itemId = el.getAttribute('data-item-id');
            if (itemId && itemId !== 'null') {
              await this.updateChecklistItem(parseInt(itemId), { order: i });
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
    // Fetch single card data from dedicated endpoint
    try {
      const response = await fetch(`/api/cards/${cardId}`);
      const data = await response.json();
      
      if (data.success) {
        return data.card;
      } else {
        console.error('Failed to get card data:', data.message);
        return null;
      }
    } catch (err) {
      console.error('Error getting card data:', err.message);
      return null;
    }
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

  async archiveCard(cardId) {
    try {
      const response = await fetch(`/api/cards/${cardId}/archive`, {
        method: 'PATCH'
      });

      const data = await response.json();

      if (data.success) {
        // Reload board to reflect archiving
        await this.loadBoard();
      } else {
        alert('Failed to archive card: ' + data.message);
      }
    } catch (err) {
      alert('Error archiving card: ' + err.message);
    }
  }

  async unarchiveCard(cardId) {
    try {
      const response = await fetch(`/api/cards/${cardId}/unarchive`, {
        method: 'PATCH'
      });

      const data = await response.json();

      if (data.success) {
        // Reload board to reflect unarchiving
        await this.loadBoard();
      } else {
        alert('Failed to unarchive card: ' + data.message);
      }
    } catch (err) {
      alert('Error unarchiving card: ' + err.message);
    }
  }

  setupChecklistDragAndDrop(cardId, onOrderChange) {
    const container = document.getElementById('checklist-items');
    this._setupChecklistDragAndDropInternal(container, { onOrderChange });
  }

  setupNewCardChecklistDragAndDrop(container, pendingChecklistItems) {
    this._setupChecklistDragAndDropInternal(container, { pendingChecklistItems });
  }

  /**
   * Internal method to set up drag-and-drop for checklist items.
   * Supports two modes:
   * 1. Edit mode: Pass onOrderChange callback to be notified of reordering
   * 2. New card mode: Pass pendingChecklistItems array to keep in sync with DOM order
   */
  _setupChecklistDragAndDropInternal(container, options = {}) {
    const { onOrderChange, pendingChecklistItems } = options;
    
    // Use a flag to track if we've already set up listeners on this container
    if (container._dragListenersSetup) return;
    container._dragListenersSetup = true;

    let draggedElement = null;

    // Event delegation for drag events
    container.addEventListener('dragstart', (e) => {
      if (e.target.classList.contains('checklist-item')) {
        draggedElement = e.target;
        e.target.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      }
    });

    container.addEventListener('dragend', (e) => {
      if (e.target.classList.contains('checklist-item')) {
        e.target.classList.remove('dragging');
        
        // Handle order change based on mode
        if (onOrderChange) {
          // Edit mode: notify that order changed (will be saved on form submit)
          onOrderChange();
        } else if (pendingChecklistItems) {
          // New card mode: update pendingChecklistItems array to match new DOM order
          const allItems = Array.from(container.querySelectorAll('.checklist-item'));
          const newOrder = allItems.map(el => {
            const tempId = Number(el.getAttribute('data-temp-id'));
            return pendingChecklistItems.find(i => i.tempId === tempId);
          }).filter(Boolean);
          
          // Update the array in place
          pendingChecklistItems.length = 0;
          pendingChecklistItems.push(...newOrder);
        }
        
        draggedElement = null;
      }
    });

    container.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      
      const afterElement = this.getChecklistDragAfterElement(container, e.clientY);
      
      if (draggedElement && afterElement === null) {
        container.appendChild(draggedElement);
      } else if (draggedElement) {
        container.insertBefore(draggedElement, afterElement);
      }
    });
  }

  getChecklistDragAfterElement(container, y) {
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

  toggleCommentCollapse(commentText, button) {
    if (commentText.classList.contains('collapsed')) {
      commentText.classList.remove('collapsed');
      button.textContent = 'Read less';
      button.setAttribute('aria-expanded', 'true');
    } else {
      commentText.classList.add('collapsed');
      button.textContent = 'Read more...';
      button.setAttribute('aria-expanded', 'false');
    }
  }

  formatCommentDate(dateString) {
    if (!dateString) return '';
    
    // Parse the date string - assumes ISO 8601 format from server
    // The Date constructor automatically handles timezone conversion to local time
    const date = new Date(dateString);
    const now = new Date();
    
    // Calculate difference in milliseconds
    // Both dates are in local timezone, so comparison is accurate
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    // Return relative time for recent comments
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    
    // Format as date/time for older comments (day/month/year format)
    const dateOptions = { day: 'numeric', month: 'short', year: 'numeric' };
    const timeOptions = { hour: '2-digit', minute: '2-digit' };
    return date.toLocaleDateString('en-GB', dateOptions) + ' ' + date.toLocaleTimeString(undefined, timeOptions);
  }

  generateCommentHtml(comment) {
    const isLongComment = comment.comment.split('\n').length > 10 || comment.comment.length > 500;
    return `
      <div class="comment-item" data-comment-id="${comment.id}">
        <div class="comment-header">
          <span class="comment-date">${this.formatCommentDate(comment.created_at)}</span>
          <button type="button" class="comment-delete-btn" data-comment-id="${comment.id}" title="Delete" aria-label="Delete comment">🗑</button>
        </div>
        <div class="comment-text ${isLongComment ? 'collapsed' : ''}" id="comment-text-${comment.id}" data-comment-id="${comment.id}">${linkifyUrls(this.escapeHtml(comment.comment))}</div>
        ${isLongComment ? `<button type="button" class="comment-read-more" data-comment-id="${comment.id}" aria-expanded="false" aria-controls="comment-text-${comment.id}" aria-label="Expand comment">Read more...</button>` : ''}
      </div>
    `;
  }

  async deleteCommentHandler(deleteBtn, cardId) {
    const commentId = parseInt(deleteBtn.getAttribute('data-comment-id'));
    
    if (!confirm('Are you sure you want to delete this comment?')) {
      return;
    }
    
    try {
      const response = await fetch(`/api/comments/${commentId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Remove comment from UI
        const commentItem = deleteBtn.closest('.comment-item');
        commentItem.remove();
        
        // If no comments left, show "no comments" message
        const commentsList = document.getElementById('comments-list');
        if (commentsList && commentsList.querySelectorAll('.comment-item').length === 0) {
          commentsList.innerHTML = '<p class="no-comments">No comments yet.</p>';
        }
      } else {
        alert('Failed to delete comment: ' + data.message);
      }
    } catch (err) {
      console.error('Error deleting comment:', err);
      alert('Error deleting comment');
    }
  }
}

// Initialize board manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const boardManager = new BoardManager();
  boardManager.init();
});
