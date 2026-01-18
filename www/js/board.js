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
 * Setup modal background click handler that ignores text selection drags
 * Prevents modal from closing when user drags to select text and releases outside modal
 * @param {HTMLElement} modal - The modal element
 * @param {Function} closeHandler - Function to call when modal should close (e.g., handleCancel or modal.remove)
 *                                  Can be async - promise rejections are handled gracefully
 */
function setupModalBackgroundClose(modal, closeHandler) {
  let mouseDownOnBackground = false;
  
  modal.addEventListener('mousedown', (e) => {
    // Track if mousedown was on the background (not on modal content)
    mouseDownOnBackground = e.target === modal;
  });
  
  modal.addEventListener('click', async (e) => {
    // Only close if:
    // 1. Click target is the background
    // 2. Mousedown also started on the background (not a drag from inside)
    if (e.target === modal && mouseDownOnBackground) {
      try {
        // Handle both sync and async closeHandler functions
        await closeHandler();
      } catch (error) {
        console.error('Error in modal close handler:', error);
        // Don't close modal if there was an error
      }
    }
    mouseDownOnBackground = false;
  });
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
    this.onItemAdded = options.onItemAdded || (() => {});
    this.onItemChanged = options.onItemChanged || (() => {});
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
          this.onItemChanged();
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
        this.onItemChanged();
        this.updateSummary();
      }
    });

    // Single event listener for edit buttons
    this.container.addEventListener('click', (e) => {
      if (e.target.matches('.checklist-edit-btn')) {
        const tempId = Number(e.target.getAttribute('data-temp-id'));
        const itemElement = e.target.closest('.checklist-item');
        const nameSpan = itemElement.querySelector('.checklist-item-name');
        
        // If there's no name span yet, the item is still in edit mode
        if (!nameSpan) {
          return;
        }
        
        const currentName = nameSpan.textContent;
        
        // Replace span with input for inline editing
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'checklist-item-input';
        input.value = currentName;
        input.setAttribute('data-temp-id', tempId);
        input.setAttribute('data-editing', 'true'); // Flag to indicate edit mode
        nameSpan.replaceWith(input);
        input.focus();
        input.select();
        
        // Disable dragging while editing
        itemElement.draggable = false;
      }
    });

    // Single event listener for blur on inputs
    this.container.addEventListener('blur', (e) => {
      if (e.target.classList.contains('checklist-item-input')) {
        const isEditing = e.target.getAttribute('data-editing') === 'true';
        
        if (isEditing) {
          // This is an edited item - save changes
          const tempId = Number(e.target.getAttribute('data-temp-id'));
          const itemElement = e.target.closest('.checklist-item');
          const newName = e.target.value.trim();
          const currentName = e.target.value; // original value
          
          // Get the original name before editing
          const item = this.pendingItems.find(i => i.tempId === tempId);
          const originalName = item ? item.name : '';
          
          if (newName && newName !== originalName) {
            // Update the item in the array
            if (item) {
              item.name = newName;
            }
            this.onItemChanged();
          }
          
          // Replace input with name span
          const nameToDisplay = newName || originalName;
          const newNameSpan = this.createNameSpan(nameToDisplay);
          e.target.replaceWith(newNameSpan);
          
          // Re-enable dragging
          if (itemElement) {
            itemElement.draggable = true;
          }
        } else {
          // This is a new item being committed - use the existing logic
          // Defer to next event loop cycle to allow other events (like delete button clicks) to process first
          setTimeout(() => this.commitInput(e.target), 0);
        }
      }
    }, true); // Use capture to catch blur

    // Listen for commit complete event to trigger adding new item
    this.container.addEventListener('checklistItemCommitted', (e) => {
      if (e.detail.addItemAfter) {
        this.addItemAfter(e.detail.addItemAfter);
      }
    });

    // Single event listener for Enter key on inputs
    this.container.addEventListener('keydown', (e) => {
      if (e.target.classList.contains('checklist-item-input')) {
        const isEditing = e.target.getAttribute('data-editing') === 'true';
        
        if (e.key === 'Enter') {
          e.preventDefault();
          
          if (isEditing) {
            // For edited items, save and remove the flag
            e.target.removeAttribute('data-editing');
            e.target.blur(); // Trigger blur which will handle saving
          } else {
            // For new items, use existing logic
            const inputValue = e.target.value.trim();
            const tempId = Number(e.target.getAttribute('data-temp-id'));
            
            // Mark that we want to add an item after this one commits
            if (inputValue) {
              e.target.dataset.addItemAfterCommit = 'true';
            }
            
            // Trigger commit
            e.target.blur();
          }
        } else if (e.key === 'Escape' && isEditing) {
          // Cancel edit by removing the input and restoring name span
          e.preventDefault();
          e.stopPropagation();
          
          const itemElement = e.target.closest('.checklist-item');
          const tempId = Number(e.target.getAttribute('data-temp-id'));
          const item = this.pendingItems.find(i => i.tempId === tempId);
          const originalName = item ? item.name : '';
          
          // Replace input with name span (restore original)
          const newNameSpan = this.createNameSpan(originalName);
          e.target.replaceWith(newNameSpan);
          
          // Re-enable dragging
          if (itemElement) {
            itemElement.draggable = true;
          }
        }
      }
    });

  }

  createNameSpan(text) {
    const span = document.createElement('span');
    span.className = 'checklist-item-name';
    span.textContent = text;
    return span;
  }

  addEditButtonToItem(itemElement, tempId) {
    const actionsContainer = itemElement.querySelector('.checklist-item-actions');
    if (actionsContainer) {
      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'checklist-edit-btn';
      editBtn.setAttribute('data-temp-id', tempId);
      editBtn.title = 'Edit';
      editBtn.textContent = '✎';
      // Insert edit button before delete button
      actionsContainer.insertBefore(editBtn, actionsContainer.firstChild);
    }
  }

  commitInput(inputElement) {
    if (!inputElement || !inputElement.classList.contains('checklist-item-input')) return;
    
    const name = inputElement.value.trim();
    const tempId = Number(inputElement.getAttribute('data-temp-id'));
    const shouldAddItemAfter = inputElement.dataset.addItemAfterCommit === 'true';
    
    if (name) {
      const item = this.pendingItems.find(i => i.tempId === tempId);
      if (item) {
        item.name = name;
        
        // Replace input with display span
        const itemElement = inputElement.closest('.checklist-item');
        const nameSpan = this.createNameSpan(name);
        inputElement.replaceWith(nameSpan);
        
        // Add edit button now that item has a name
        this.addEditButtonToItem(itemElement, tempId);
        
        // Re-enable dragging
        itemElement.draggable = true;
        
        this.updateSummary();
        this.onItemCommitted(tempId);
        
        // Dispatch event to signal commit is complete
        if (shouldAddItemAfter) {
          this.container.dispatchEvent(new CustomEvent('checklistItemCommitted', {
            detail: { tempId, addItemAfter: true }
          }));
        }
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

  createItemElement(tempId) {
    const item = {
      name: '',
      checked: false,
      tempId: tempId
    };

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

    return { item, itemHtml };
  }

  focusNewItem(tempId) {
    const newInput = this.container.querySelector(`input.checklist-item-input[data-temp-id="${tempId}"]`);
    if (newInput) {
      newInput.focus();
    }
  }

  addItem(insertAtTop = false) {
    const tempId = Date.now() + Math.random();
    const { item, itemHtml } = this.createItemElement(tempId);

    if (insertAtTop) {
      this.pendingItems.unshift(item);
      this.container.insertAdjacentHTML('afterbegin', itemHtml);
    } else {
      this.pendingItems.push(item);
      this.container.insertAdjacentHTML('beforeend', itemHtml);
    }

    this.focusNewItem(tempId);
    this.onItemAdded();
    this.updateSummary();
  }

  addItemAfter(afterTempId) {
    const tempId = Date.now() + Math.random();
    const { item, itemHtml } = this.createItemElement(tempId);

    // Find the index of the item to insert after
    const afterIndex = this.pendingItems.findIndex(i => i.tempId === afterTempId);
    if (afterIndex !== -1) {
      this.pendingItems.splice(afterIndex + 1, 0, item);
    } else {
      this.pendingItems.push(item);
    }

    // Find the DOM element to insert after
    const afterElement = this.container.querySelector(`.checklist-item[data-temp-id="${afterTempId}"]`);
    if (afterElement) {
      afterElement.insertAdjacentHTML('afterend', itemHtml);
    } else {
      this.container.insertAdjacentHTML('beforeend', itemHtml);
    }

    this.focusNewItem(tempId);
    this.onItemAdded();
    this.updateSummary();
  }
}

/**
 * WebSocket Manager for Real-Time Board Updates
 * 
 * Manages Socket.IO connections for real-time board synchronization across clients.
 * Handles reconnection logic, event emission, and incoming event handlers.
 */
class WebSocketManager {
  /**
   * Initialize WebSocket manager
   * 
   * Args:
   *   boardId: The board ID to connect to
   *   boardManager: Reference to the BoardManager instance
   */
  constructor(boardId, boardManager) {
    this.boardId = boardId;
    this.boardManager = boardManager;
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = Infinity; // Infinite retries - Socket.IO handles exponential backoff internally
    this.reconnectDelay = 1000; // Socket.IO manages reconnection delays
    
    this.initializeConnection();
  }

  /**
   * Initialize WebSocket connection with auto-reconnection.
   * 
   * Sets up Socket.IO client with reconnection strategy and event listeners.
   */
  initializeConnection() {
    // Check if Socket.IO library is loaded
    if (typeof io === 'undefined') {
      console.error('❌ Socket.IO library not loaded! Make sure socket.io.js script is included.');
      return;
    }
    
    // Connect to the current server (socket.io client auto-detects the URL)
    // Don't pass a URL - let socket.io auto-detect it
    this.socket = io({
      reconnection: true,
      reconnectionDelay: this.reconnectDelay,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: this.maxReconnectAttempts,
      transports: ['websocket', 'polling']
    });

    // Notify any listeners that socket was created (e.g., header.js for immediate event updates)
    // This callback is optional - listeners should check if it exists before setting it
    if (typeof this.onSocketCreated === 'function') {
      try {
        this.onSocketCreated(this.socket);
      } catch (error) {
        console.error('Error in onSocketCreated callback:', error);
      }
    }

    this.setupEventListeners();
  }

  setupEventListeners() {
    // Connection events
    this.socket.on('connect', () => {
      this.reconnectAttempts = 0;
      this.joinBoard();
      this.joinThemeRoom();
      // Update header status immediately when WebSocket connects
      if (window.header) {
        window.header.updateWebSocketStatus();
        window.header.checkDatabaseStatus();
      }
    });

    this.socket.on('disconnect', () => {
      // Update header status immediately when WebSocket disconnects
      if (window.header) {
        window.header.updateWebSocketStatus();
      }
    });

    this.socket.on('connect_error', (error) => {
      // Connection error occurred
    });

    // Board room events
    this.socket.on('room_joined', (data) => {
      // Joined board room
    });
    this.socket.on('card_created', (data) => {
      this.handleCardCreated(data);
    });
    this.socket.on('card_updated', (data) => {
      this.handleCardUpdated(data);
    });
    this.socket.on('card_deleted', (data) => {
      this.handleCardDeleted(data);
    });
    this.socket.on('card_moved', (data) => {
      this.handleCardMoved(data);
    });
    this.socket.on('cards_moved', (data) => {
      this.handleCardsMoved(data);
    });
    this.socket.on('column_reordered', (data) => {
      this.handleColumnReordered(data);
    });
    this.socket.on('checklist_item_added', (data) => {
      this.handleChecklistItemAdded(data);
    });
    this.socket.on('checklist_item_updated', (data) => {
      this.handleChecklistItemUpdated(data);
    });
    this.socket.on('checklist_item_deleted', (data) => {
      this.handleChecklistItemDeleted(data);
    });
    this.socket.on('column_updated', (data) => {
      this.handleColumnUpdated(data);
    });
    this.socket.on('card_archived', (data) => {
      this.handleCardArchived(data);
    });
    this.socket.on('card_unarchived', (data) => {
      this.handleCardUnarchived(data);
    });
    
    // Theme room events
    this.socket.on('theme_changed', (data) => {
      this.handleThemeChanged(data);
    });
    this.socket.on('theme_updated', (data) => {
      this.handleThemeChanged(data);
    });
  }

  /**
   * Join the board room for real-time board updates.
   */
  joinBoard() {
    if (this.socket && this.socket.connected) {
      this.socket.emit('join_board', { board_id: this.boardId });
    }
  }

  /**
   * Join the theme room to receive theme update notifications.
   */
  joinThemeRoom() {
    if (this.socket && this.socket.connected) {
      this.socket.emit('join_theme');
    } else {
      console.warn('Cannot join theme room - socket not connected');
    }
  }

  /**
   * Leave the board room.
   */
  leaveBoard() {
    if (this.socket && this.socket.connected) {
      this.socket.emit('leave_board', { board_id: this.boardId });
    }
  }

  // Event emission methods for local changes
  emitCardCreated(columnId, cardId, cardData) {
    this.socket.emit('card_created', {
      board_id: this.boardId,
      column_id: columnId,
      card_id: cardId,
      card_data: cardData
    });
  }

  emitCardUpdated(cardId, columnId, cardData) {
    this.socket.emit('card_updated', {
      board_id: this.boardId,
      card_id: cardId,
      column_id: columnId,
      card_data: cardData
    });
  }

  emitCardDeleted(cardId, columnId) {
    this.socket.emit('card_deleted', {
      board_id: this.boardId,
      card_id: cardId,
      column_id: columnId
    });
  }

  emitCardMoved(cardId, fromColumnId, toColumnId, fromIndex, toIndex) {
    this.socket.emit('card_moved', {
      board_id: this.boardId,
      card_id: cardId,
      from_column_id: fromColumnId,
      to_column_id: toColumnId,
      from_index: fromIndex,
      to_index: toIndex
    });
  }

  emitColumnReordered(columnOrder) {
    this.socket.emit('column_reordered', {
      board_id: this.boardId,
      column_order: columnOrder
    });
  }

  emitChecklistItemAdded(cardId, itemId, itemData) {
    this.socket.emit('checklist_item_added', {
      board_id: this.boardId,
      card_id: cardId,
      item_id: itemId,
      item_data: itemData
    });
  }

  emitChecklistItemUpdated(cardId, itemId, updatedFields) {
    this.socket.emit('checklist_item_updated', {
      board_id: this.boardId,
      card_id: cardId,
      item_id: itemId,
      updated_fields: updatedFields
    });
  }

  emitChecklistItemDeleted(cardId, itemId) {
    this.socket.emit('checklist_item_deleted', {
      board_id: this.boardId,
      card_id: cardId,
      item_id: itemId
    });
  }

  // Handle incoming events from other clients
  handleCardCreated(data) {
    // A new card was created on another client
    if (this.boardManager) {
      // Request the board manager to refresh the card or column
      this.boardManager.loadBoard();
    }
  }

  handleCardUpdated(data) {
    // A card was updated on another client
    // Always reload the board to ensure consistency
    // Even if only the title changed, reloading guarantees the UI matches the server state
    this.boardManager.loadBoard();
  }

  handleCardDeleted(data) {
    // A card was deleted on another client
    const cardElement = document.querySelector(`[data-card-id="${data.card_id}"]`);
    if (cardElement) {
      cardElement.remove();
    }
  }

  handleCardMoved(data) {
    // A card was moved on another client
    // Refresh the entire board to ensure correct state
    this.boardManager.loadBoard();
  }

  handleCardsMoved(data) {
    // Multiple cards were moved on another client
    // Refresh the entire board to ensure correct state
    this.boardManager.loadBoard();
  }

  handleColumnReordered(data) {
    // Columns were reordered on another client
    // Refresh the board to reflect new column order
    this.boardManager.loadBoard();
  }

  handleChecklistItemAdded(data) {
    // A checklist item was added on another client
    // Reload board to reflect checklist changes
    this.boardManager.loadBoard();
  }

  handleChecklistItemUpdated(data) {
    // A checklist item was updated on another client
    // Reload board to reflect checklist changes in the card detail modal
    this.boardManager.loadBoard();
  }

  handleChecklistItemDeleted(data) {
    // A checklist item was deleted on another client
    // Reload board to reflect checklist changes
    this.boardManager.loadBoard();
  }

  handleColumnUpdated(data) {
    // A column was updated on another client
    // Reload board to reflect column name changes and order changes
    this.boardManager.loadBoard();
  }

  handleCardArchived(data) {
    // A card was archived on another client
    // Remove the card from the DOM if it's displayed
    const cardElement = document.querySelector(`[data-card-id="${data.card_id}"]`);
    if (cardElement) {
      cardElement.remove();
    }
    // Reload to update card count and ensure consistency
    this.boardManager.loadBoard();
  }

  handleCardUnarchived(data) {
    // A card was unarchived on another client
    // Reload board to show the restored card
    this.boardManager.loadBoard();
  }

  handleThemeChanged(data) {
    // Theme was changed by another client
    // Fetch the new theme and apply it without reloading
    
    // Try to use themeBuilder if available (on theme-builder page)
    const themeBuilder = window.AFT?.themeBuilder || window.themeBuilder;
    if (themeBuilder && typeof themeBuilder.loadAndApplyTheme === 'function') {
      themeBuilder.loadAndApplyTheme().catch(error => {
        console.error('✗ Error applying theme from WebSocket event:', error);
      });
    } else if (typeof loadAndApplyThemeGlobal === 'function') {
      // Use global function (available on all pages that include utils.js)
      loadAndApplyThemeGlobal().catch(error => {
        console.error('✗ Error applying theme from WebSocket event:', error);
      });
    } else {
      console.warn('⚠ Theme update received but no theme handler available');
    }
  }

  disconnect() {
    this.leaveBoard();
    if (this.socket) {
      this.socket.disconnect();
    }
  }
}

class BoardManager {
  constructor() {
    this.container = document.getElementById('board-container');
    this.boardId = null;
    this.boardName = '';
    this.columns = [];
    this.originalColumns = []; // Store original unfiltered columns for accurate card counting
    this.hoveredColumnId = null;
    this.lastUsedColumnId = null;
    this.showArchived = false; // Track whether to show archived or active cards
    this.showDone = false; // Track whether to show done cards (for board_task_category style)
    this.currentView = 'task'; // Track current view: 'task', 'scheduled', or 'archived'
    this.workingStyle = 'kanban'; // Track working style: 'kanban' or 'board_task_category'
    this.keyboardHandler = this.handleKeydown.bind(this);
    this.closeDropdownHandler = this.handleCloseDropdown.bind(this);
    this.currentLoadController = null; // Track in-flight board load requests
    this.currentViewState = null; // Track the view state for the current load
  }

  /**
   * Safely parse JSON response, handling non-JSON errors
   * @param {Response} response - Fetch response object
   * @returns {Promise<Object>} Parsed JSON data or error object
   */
  async parseResponse(response) {
    try {
      const data = await response.json();
      if (!response.ok) {
        // Response parsed successfully but HTTP status indicates error
        return data;
      }
      return data;
    } catch (error) {
      // JSON parsing failed
      return {
        success: false,
        message: response.ok 
          ? `Invalid JSON response from server` 
          : `HTTP error! status: ${response.status}`
      };
    }
  }

  /**
   * Show a non-blocking error toast notification
   * @param {string} message - The error message to display
   * @param {number} duration - How long to show the toast in milliseconds (default 3000)
   */
  showErrorToast(message, duration = 3000) {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    toast.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: #e74c3c;
      color: white;
      padding: 12px 20px;
      border-radius: 5px;
      box-shadow: 0 4px 8px rgba(0,0,0,0.3);
      z-index: 10000;
      animation: slideIn 0.3s ease-out;
      max-width: 400px;
      word-wrap: break-word;
    `;
    
    document.body.appendChild(toast);
    
    // Remove after specified duration
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease-in';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  showSuccessToast(message, duration = 3000) {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = 'success-toast';
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    toast.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: #27ae60;
      color: white;
      padding: 12px 20px;
      border-radius: 5px;
      box-shadow: 0 4px 8px rgba(0,0,0,0.3);
      z-index: 10000;
      animation: slideIn 0.3s ease-out;
      max-width: 400px;
      word-wrap: break-word;
    `;
    
    document.body.appendChild(toast);
    
    // Remove after specified duration
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease-in';
      setTimeout(() => toast.remove(), 300);
    }, duration);
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
    
    // Initialize WebSocket for real-time updates
    this.wsManager = new WebSocketManager(this.boardId, this);
    
    // Load working style preference
    await this.loadWorkingStyle();
    
    await this.loadBoard();
    this.setupKeyboardShortcuts();
    this.setupDropdownClickOutside();
    this.setupViewListener();
  }

  async loadWorkingStyle() {
    try {
      const response = await fetch('/api/settings/working-style');
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          this.workingStyle = data.value || 'kanban';
        }
      } else if (response.status === 404) {
        // Setting doesn't exist, default to kanban
        this.workingStyle = 'kanban';
      }
    } catch (error) {
      console.error('Error loading working style:', error);
      this.workingStyle = 'kanban';
    }
  }

  setupViewListener() {
    // Listen for view changes from header
    window.addEventListener('viewChanged', async (e) => {
      const newView = e.detail.view;
      
      // Show loading overlay
      this.showBoardLoading();
      
      // Map view names to internal state
      if (newView === 'archived') {
        this.currentView = 'task';
        this.showArchived = true;
      } else if (newView === 'scheduled') {
        this.currentView = 'scheduled';
        this.showArchived = false;
      } else if (newView === 'done') {
        this.currentView = 'task';
        this.showArchived = false;
        this.showDone = true;
      } else { // 'task'
        this.currentView = 'task';
        this.showArchived = false;
        this.showDone = false;
      }
      
      await this.loadBoard();
    });
  }

  setupDropdownClickOutside() {
    // Add click-outside handler once for all dropdowns
    document.addEventListener('click', this.closeDropdownHandler);
  }

  render() {
    this.container.innerHTML = `
      <div class="loading-board">Loading board...</div>
    `;
  }

  async loadBoard() {
    // Cancel any in-flight board load request
    if (this.currentLoadController) {
      this.currentLoadController.abort();
    }
    
    // Create new controller for this request
    const controller = new AbortController();
    this.currentLoadController = controller;
    
    // Capture current view state
    const viewState = {
      currentView: this.currentView,
      showArchived: this.showArchived
    };
    this.currentViewState = viewState;
    
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      let response;
      
      if (this.currentView === 'scheduled') {
        // Load board with all scheduled cards in a single request
        response = await fetch(`/api/boards/${this.boardId}/cards/scheduled`, {
          signal: controller.signal
        });
      } else {
        // Load board with nested structure (board -> columns -> cards)
        // Add archived parameter to filter cards based on showArchived state
        const archivedParam = this.showArchived ? 'true' : 'false';
        response = await fetch(`/api/boards/${this.boardId}/cards?archived=${archivedParam}`, {
          signal: controller.signal
        });
      }
      
      clearTimeout(timeoutId);
      
      // Check if this request is stale (view changed while loading)
      if (this.currentViewState !== viewState) {
        // View changed during load, ignore this response
        return;
      }
      
      const data = await this.parseResponse(response);
      
      // Check again after parsing in case view changed
      if (this.currentViewState !== viewState) {
        return;
      }
      
      if (!data.success) {
        this.hideBoardLoading();
        this.showErrorToast('Failed to load board: ' + data.message);
        this.showError('Failed to load board: ' + data.message);
        return;
      }

      const board = data.board;
      this.processBoard(board);
      this.hideBoardLoading();
    } catch (error) {
      clearTimeout(timeoutId);
      
      // Ignore aborted requests (they were intentionally cancelled)
      if (error.name === 'AbortError') {
        // Only show error if this was the timeout abort, not a cancellation
        if (this.currentViewState === viewState) {
          this.hideBoardLoading();
          this.showErrorToast('Load board timed out (5s). Please check your connection.');
          this.showError('Load board timed out. Please check your connection.');
        }
        return;
      }
      
      // Only process errors for non-stale requests
      if (this.currentViewState === viewState) {
        console.error('Error loading board:', error);
        this.hideBoardLoading();
        this.showErrorToast(`Error loading board: ${error.message}`);
        this.showError('An error occurred while loading the board');
      }
    } finally {
      // Always clear current load controller if this was the active request
      // This ensures cleanup even if there's an unexpected error path
      if (this.currentLoadController === controller) {
        this.currentLoadController = null;
      }
    }
  }

  processBoard(board) {
    try {
      this.boardName = board.name;
      // Store the original unfiltered columns for counting purposes
      this.originalColumns = JSON.parse(JSON.stringify(board.columns));
      this.columns = board.columns;
      
      // Filter cards based on done status and view
      if (this.workingStyle === 'board_task_category') {
        if (this.showDone) {
          // In done view, show only cards where done=true
          this.columns = this.columns.map(column => ({
            ...column,
            cards: (column.cards || []).filter(card => card.done)
          }));
        } else {
          // In task view, show only cards where done=false
          this.columns = this.columns.map(column => ({
            ...column,
            cards: (column.cards || []).filter(card => !card.done)
          }));
        }
      }
      
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

    // Don't trigger if any visible modal is open on the page
    const anyModalOpen = Array.from(document.querySelectorAll('.modal')).some((modal) => {
      const style = window.getComputedStyle(modal);
      return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    });
    if (anyModalOpen) {
      return;
    }

    // 'n' key - add card at top of column
    if (e.key === 'n' || e.key === 'N') {
      e.preventDefault();
      const columnId = this.hoveredColumnId || this.lastUsedColumnId;
      if (columnId) {
        const scheduled = this.currentView === 'scheduled';
        this.openAddCardModal(columnId, 0, scheduled); // 0 = top
      }
    }

    // 'm' key - add card at bottom of column
    if (e.key === 'm' || e.key === 'M') {
      e.preventDefault();
      const columnId = this.hoveredColumnId || this.lastUsedColumnId;
      if (columnId) {
        const scheduled = this.currentView === 'scheduled';
        this.openAddCardModal(columnId, null, scheduled); // default = bottom
      }
    }
  }

  cleanup() {
    // Remove event listeners to prevent memory leaks
    document.removeEventListener('keydown', this.keyboardHandler);
    document.removeEventListener('click', this.closeDropdownHandler);
  }

  handleCloseDropdown(e) {
    if (!e.target.closest('.column-menu-wrapper')) {
      document.querySelectorAll('.column-menu-dropdown').forEach(d => {
        d.classList.remove('show');
      });
    }
  }

  async toggleArchiveView() {
    // Toggle the showArchived state
    this.showArchived = !this.showArchived;
    // Reload board with new archived parameter
    await this.loadBoard();
  }

  /**
   * Get the card count display for a column.
   * In board_task_category mode:
   *   - Task view: shows "done/total" format using original unfiltered data
   *   - Done view: shows only count of done cards
   * Otherwise, shows just the total count.
   * 
   * All counts exclude archived and scheduled template cards.
   * 
   * @param {Object} column - The column object with cards array
   * @param {number} columnIndex - The index of the column in the columns array
   * @returns {string} Card count display string
   */
  getColumnCardCount(column, columnIndex) {
    if (!column.cards) return '0';
    
    if (this.workingStyle === 'board_task_category') {
      // Use original unfiltered column data for accurate counts
      const originalColumn = this.originalColumns[columnIndex];
      if (!originalColumn || !originalColumn.cards) return '0';
      
      // Count all active cards (non-archived, non-scheduled) in the original data
      const allActiveCards = originalColumn.cards.filter(card => !card.archived && !card.scheduled);
      const doneCards = allActiveCards.filter(card => card.done);
      
      if (this.currentView === 'task' && !this.showArchived) {
        // Task view: show done/total format
        return `${doneCards.length}/${allActiveCards.length}`;
      } else if (this.showDone) {
        // Done view: show only done count
        return doneCards.length.toString();
      }
    }
    
    // Default behavior: just show total count
    return column.cards.length.toString();
  }

  renderBoard() {
    // Show/hide views dropdown in header based on columns
    if (window.header) {
      window.header.showViewsDropdown(this.columns.length > 0);
    }
    
    if (this.columns.length === 0) {
      
      this.container.innerHTML = `
        <div class="empty-board-panel">
          <div class="empty-board">
            <div class="empty-board-icon">📋</div>
            <h3>No columns yet</h3>
            <p>Add your first column to start organizing tasks!</p>
            <button class="btn btn-primary" id="add-column-empty-btn">+ Add Column</button>
          </div>
        </div>
      `;
      
      // Add event listener for add column button
      document.getElementById('add-column-empty-btn').addEventListener('click', () => this.openAddColumnModal());
    } else {
      this.container.innerHTML = `
        <div class="columns-container">
          ${this.columns.map((column, index) => `
            <div class="column" data-column-id="${column.id}" data-board-id="${this.boardId}" data-order="${column.order}">
              <div class="column-header">
                <div class="column-title-group">
                  <h4>${this.escapeHtml(column.name)} <span class="card-count">(${this.getColumnCardCount(column, index)})</span></h4>
                  <button class="column-edit-btn" data-column-id="${column.id}" data-column-name="${this.escapeHtml(column.name)}" title="Edit column">✎</button>
                </div>
                <div class="column-actions">
                  ${!this.showArchived ? `<button class="column-add-card-btn" data-column-id="${column.id}" title="Add card">+</button>` : ''}
                  <button class="column-move-left-btn" data-column-id="${column.id}" data-order="${column.order}" title="Move left">◀</button>
                  <button class="column-move-right-btn" data-column-id="${column.id}" data-order="${column.order}" title="Move right">▶</button>
                  <div class="column-menu-wrapper">
                    <button class="column-menu-btn" data-column-id="${column.id}" title="Column menu">⋮</button>
                    <div class="column-menu-dropdown" data-column-id="${column.id}">
                      <button class="column-menu-item column-move-all-cards-btn" data-column-id="${column.id}">
                        <span>🔀</span>
                        <span>Move all cards...</span>
                      </button>
                      ${this.showArchived ? `
                        <button class="column-menu-item column-unarchive-all-cards-btn" data-column-id="${column.id}">
                          <span>📤</span>
                          <span>Unarchive all cards</span>
                        </button>
                      ` : `
                        <button class="column-menu-item column-archive-all-cards-btn" data-column-id="${column.id}">
                          <span>📥</span>
                          <span>Archive all cards</span>
                        </button>
                      `}
                      <button class="column-menu-item column-delete-cards-btn" data-column-id="${column.id}">
                        <span>🗑</span>
                        <span>Delete all cards</span>
                      </button>
                      <button class="column-menu-item column-delete-btn" data-column-id="${column.id}">
                        <span>×</span>
                        <span>Delete column</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div class="column-cards" data-column-id="${column.id}">
                ${column.cards && column.cards.length > 0 ? 
                  column.cards.map(card => `
                    <div class="card ${card.archived ? 'archived-card' : ''} ${this.currentView === 'scheduled' && !card.schedule ? 'no-schedule' : ''}" draggable="${!card.archived}" data-card-id="${card.id}" data-column-id="${column.id}" data-order="${card.order}" data-archived="${card.archived}" data-done="${card.done || false}">
                      <div class="card-action-buttons" draggable="false">
                        ${this.currentView === 'scheduled' ? '' : 
                          card.archived ? 
                            `<button class="card-unarchive-btn" data-card-id="${card.id}" title="Unarchive card" draggable="false">
                              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="3" y="4" width="18" height="16" rx="2"></rect>
                                <line x1="3" y1="10" x2="21" y2="10"></line>
                                <path d="M12 14v-2"></path>
                                <path d="M9 14l3 2 3-2"></path>
                              </svg>
                            </button>` :
                            `${this.workingStyle === 'board_task_category' ? 
                              `<button class="card-done-btn" data-card-id="${card.id}" title="${card.done ? 'Mark as not done' : 'Mark as done'}" draggable="false">
                                ${card.done ? '○' : '✓'}
                              </button>` :
                              `<button class="card-archive-btn" data-card-id="${card.id}" title="Archive card" draggable="false">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                  <rect x="3" y="4" width="18" height="16" rx="2"></rect>
                                  <line x1="3" y1="10" x2="21" y2="10"></line>
                                  <path d="M12 14v2"></path>
                                  <path d="M9 16l3-2 3 2"></path>
                                </svg>
                              </button>`
                            }`
                        }
                        <button class="card-delete-btn" data-card-id="${card.id}" title="Delete card" draggable="false">×</button>
                      </div>
                      <div class="card-content-wrapper" id="card-content-${card.id}">
                        <h5 class="card-title">${linkifyUrls(this.escapeHtml(card.title))}</h5>
                        <p class="card-description">${linkifyUrls(this.escapeHtml(card.description))}</p>
                        ${card.comments && card.comments.length > 0 ? `
                          <div class="card-comments-indicator">
                            💬 ${card.comments.length} ${card.comments.length === 1 ? 'comment' : 'comments'}
                          </div>
                        ` : ''}
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
                      <button class="card-expand-btn" data-card-id="${card.id}" role="button" aria-expanded="false" aria-controls="card-content-${card.id}">Show more...</button>
                    </div>
                  `).join('') : ''
                }
                ${!this.showArchived ? `<button class="btn btn-secondary add-card-btn" data-column-id="${column.id}">+ Add Card</button>` : ''}
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
      
      // Add event listeners for column menu buttons
      document.querySelectorAll('.column-menu-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const columnId = e.currentTarget.getAttribute('data-column-id');
          const dropdown = document.querySelector(`.column-menu-dropdown[data-column-id="${columnId}"]`);
          
          // Close all other dropdowns
          document.querySelectorAll('.column-menu-dropdown').forEach(d => {
            if (d !== dropdown) d.classList.remove('show');
          });
          
          // Toggle this dropdown
          dropdown.classList.toggle('show');
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
          const scheduled = this.currentView === 'scheduled';
          this.openAddCardModal(columnId, 0, scheduled); // Add at top (order 0)
        });
      });
      
      document.querySelectorAll('.add-card-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.target.getAttribute('data-column-id'));
          const scheduled = this.currentView === 'scheduled';
          this.openAddCardModal(columnId, null, scheduled); // Add at bottom (default)
        });
      });
      
      // Add event listeners for delete column buttons
      document.querySelectorAll('.column-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.currentTarget.getAttribute('data-column-id'));
          // Close the dropdown
          document.querySelectorAll('.column-menu-dropdown').forEach(d => d.classList.remove('show'));
          this.deleteColumn(columnId);
        });
      });
      
      // Add event listeners for delete all cards buttons
      document.querySelectorAll('.column-delete-cards-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.currentTarget.getAttribute('data-column-id'));
          // Close the dropdown
          document.querySelectorAll('.column-menu-dropdown').forEach(d => d.classList.remove('show'));
          this.deleteAllCardsInColumn(columnId);
        });
      });
      
      // Add event listeners for move all cards buttons
      document.querySelectorAll('.column-move-all-cards-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.currentTarget.getAttribute('data-column-id'));
          // Close the dropdown
          document.querySelectorAll('.column-menu-dropdown').forEach(d => d.classList.remove('show'));
          this.openMoveAllCardsModal(columnId);
        });
      });
      
      // Add event listeners for archive all cards buttons
      document.querySelectorAll('.column-archive-all-cards-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.currentTarget.getAttribute('data-column-id'));
          // Close the dropdown
          document.querySelectorAll('.column-menu-dropdown').forEach(d => d.classList.remove('show'));
          this.archiveAllCardsInColumn(columnId);
        });
      });
      
      // Add event listeners for unarchive all cards buttons
      document.querySelectorAll('.column-unarchive-all-cards-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const columnId = parseInt(e.currentTarget.getAttribute('data-column-id'));
          // Close the dropdown
          document.querySelectorAll('.column-menu-dropdown').forEach(d => d.classList.remove('show'));
          this.unarchiveAllCardsInColumn(columnId);
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
          // Don't trigger if clicking the delete button, checklist checkbox, or expand button
          // Use closest() to handle clicks on button content (like emoji text nodes)
          if (e.target.closest('.card-delete-btn')) return;
          if (e.target.closest('.card-checklist-checkbox')) return;
          if (e.target.closest('.card-expand-btn')) return;
          if (e.target.closest('.card-archive-btn')) return;
          if (e.target.closest('.card-unarchive-btn')) return;
          
          const cardId = parseInt(card.getAttribute('data-card-id'));
          
          // Show loading state on the card
          card.classList.add('updating');
          
          // Reload card data to get latest state
          const cardData = await this.getCardData(cardId);
          
          // Remove loading state
          card.classList.remove('updating');
          
          if (cardData) {
            this.openEditCardModal(cardId, cardData);
          }
          // Error toast already shown by getCardData if it failed
        });
      });

      // Initialize card collapse/expand functionality
      // Use requestAnimationFrame to ensure DOM is fully rendered before measuring
      requestAnimationFrame(() => {
        // Get the collapse threshold from CSS custom property
        const collapseHeightStr = getComputedStyle(document.documentElement)
          .getPropertyValue('--card-collapse-height')
          .trim();
        const collapseHeight = parseInt(collapseHeightStr);
        
        if (!collapseHeight || isNaN(collapseHeight)) {
          console.error('Card collapse height not defined in CSS. Skipping card collapse logic.');
          return;
        }
        
        document.querySelectorAll('.card').forEach(card => {
          const contentWrapper = card.querySelector('.card-content-wrapper');
          const expandBtn = card.querySelector('.card-expand-btn');
          
          if (contentWrapper && expandBtn) {
            // Measure the actual content height
            const contentHeight = contentWrapper.scrollHeight;
            
            // If content is taller than the threshold, make it collapsible
            if (contentHeight > collapseHeight) {
              card.classList.add('has-overflow');
              card.classList.add('collapsed');
            }
          }
        });
      });

      // Add event listeners for card expand buttons
      document.querySelectorAll('.card-expand-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation(); // Prevent card click event
          const card = e.currentTarget.closest('.card');
          
          if (card.classList.contains('collapsed')) {
            card.classList.remove('collapsed');
            e.currentTarget.textContent = 'Show less...';
            e.currentTarget.setAttribute('aria-expanded', 'true');
          } else {
            card.classList.add('collapsed');
            e.currentTarget.textContent = 'Show more...';
            e.currentTarget.setAttribute('aria-expanded', 'false');
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
        btn.addEventListener('mousedown', (e) => {
          e.stopPropagation(); // Prevent drag from starting
        });
        btn.addEventListener('click', async (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.currentTarget.getAttribute('data-card-id'));
          const cardElement = e.currentTarget.closest('.card');
          await this.deleteCard(cardId, cardElement);
        });
      });
      
      // Add event listeners for archive card buttons
      document.querySelectorAll('.card-archive-btn').forEach(btn => {
        btn.addEventListener('mousedown', (e) => {
          e.stopPropagation(); // Prevent drag from starting
        });
        btn.addEventListener('click', async (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.currentTarget.getAttribute('data-card-id'));
          const cardElement = e.currentTarget.closest('.card');
          await this.archiveCard(cardId, cardElement);
        });
      });
      
      // Add event listeners for unarchive card buttons
      document.querySelectorAll('.card-unarchive-btn').forEach(btn => {
        btn.addEventListener('mousedown', (e) => {
          e.stopPropagation(); // Prevent drag from starting
        });
        btn.addEventListener('click', async (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.currentTarget.getAttribute('data-card-id'));
          const cardElement = e.currentTarget.closest('.card');
          await this.unarchiveCard(cardId, cardElement);
        });
      });
      
      // Add event listeners for card done buttons
      document.querySelectorAll('.card-done-btn').forEach(btn => {
        btn.addEventListener('mousedown', (e) => {
          e.stopPropagation(); // Prevent drag from starting
        });
        btn.addEventListener('click', async (e) => {
          e.stopPropagation(); // Prevent card click event
          const cardId = parseInt(e.currentTarget.getAttribute('data-card-id'));
          const cardElement = e.currentTarget.closest('.card');
          const currentDone = cardElement.getAttribute('data-done') === 'true';
          await this.updateCardDoneStatus(cardId, !currentDone, cardElement);
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
      
      const data = await this.parseResponse(response);
      
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
    let originalPosition = null; // Store original position before drag
    
    // Card drag events
    cards.forEach(card => {
      card.addEventListener('dragstart', (e) => {
        // Don't allow drag if clicking on buttons or interactive elements
        if (e.target.closest('.card-delete-btn') || 
            e.target.closest('.card-archive-btn') || 
            e.target.closest('.card-unarchive-btn') ||
            e.target.closest('.card-expand-btn') ||
            e.target.closest('.card-checklist-checkbox') ||
            e.target.closest('.card-action-buttons')) {
          e.preventDefault();
          return false;
        }
        
        e.stopPropagation(); // Prevent column from also starting to drag
        draggedCard = card;
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', card.innerHTML);
        
        // Capture original position NOW, before any DOM manipulation
        const oldColumnId = parseInt(card.getAttribute('data-column-id'));
        const oldOrder = parseInt(card.getAttribute('data-order'));
        const originalColumnContainer = document.querySelector(`[data-column-id="${oldColumnId}"] .column-cards`);
        const actualNextSibling = card.nextElementSibling;
        
        originalPosition = {
          columnId: oldColumnId,
          order: oldOrder,
          container: originalColumnContainer,
          nextSibling: actualNextSibling
        };
      });
      
      card.addEventListener('dragend', (e) => {
        card.classList.remove('dragging');
        draggedCard = null;
        originalPosition = null; // Clear stored position
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
        
        if (!draggedCard || !originalPosition) return;
        
        const targetColumnId = parseInt(columnContainer.getAttribute('data-column-id'));
        const cardId = parseInt(draggedCard.getAttribute('data-card-id'));
        const oldColumnId = originalPosition.columnId;
        
        // Calculate new order based on position in DOM
        const cardsInColumn = Array.from(columnContainer.querySelectorAll('.card'));
        const newOrder = cardsInColumn.indexOf(draggedCard);
        
        // Only update if position or column changed
        const oldOrder = originalPosition.order;
        if (targetColumnId !== oldColumnId || newOrder !== oldOrder) {
          await this.updateCardPosition(cardId, targetColumnId, newOrder, originalPosition);
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

  async updateCardPosition(cardId, columnId, order, originalPosition = null) {
    const cardElement = document.querySelector(`[data-card-id="${cardId}"]`);
    
    // Add loading state with 500ms delay to avoid flashing on fast connections
    const loadingTimeout = setTimeout(() => {
      if (cardElement) {
        cardElement.classList.add('updating');
        cardElement.style.opacity = '0.6';
        cardElement.style.pointerEvents = 'none';
      }
    }, 500);
    
    // Set 5 second timeout for the request
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          column_id: columnId,
          order: order
        }),
        signal: controller.signal
      });
      
      // Clear timeouts immediately after fetch completes, before processing response
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      const data = await this.parseResponse(response);
      
      if (!data.success) {
        console.error('Failed to update card position:', data.message);
        
        // Restore card to original position (DOM only, no API call)
        if (cardElement && originalPosition) {
          this.restoreCardPosition(cardElement, originalPosition);
        }
        
        if (cardElement) {
          cardElement.classList.remove('updating'); // Remove loading state
          cardElement.classList.add('update-failed');
          cardElement.style.opacity = '';
          cardElement.style.pointerEvents = '';
          setTimeout(() => cardElement.classList.remove('update-failed'), 3000);
        }
        
        // Show non-blocking error toast instead of blocking alert
        this.showErrorToast('Failed to move card');
        
        // Don't reload board - restoration is DOM-only
      } else {
        // Update local data attributes
        if (cardElement) {
          cardElement.setAttribute('data-column-id', columnId);
          cardElement.setAttribute('data-order', order);
          cardElement.classList.remove('updating');
          cardElement.classList.add('update-success');
          cardElement.style.opacity = '';
          cardElement.style.pointerEvents = '';
          setTimeout(() => cardElement.classList.remove('update-success'), 1000);
        }
        // Reload board to update card counts
        await this.loadBoard();
      }
    } catch (err) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      // Restore card to original position
      if (cardElement && originalPosition) {
        this.restoreCardPosition(cardElement, originalPosition);
      }
      
      if (cardElement) {
        cardElement.classList.remove('updating');
        cardElement.classList.add('update-failed');
        cardElement.style.opacity = '';
        cardElement.style.pointerEvents = '';
        setTimeout(() => cardElement.classList.remove('update-failed'), 3000);
      }
      
      if (err.name === 'AbortError') {
        console.error('Card update timeout after 5 seconds');
        this.showErrorToast('Card update timed out. Check your connection.');
      } else {
        console.error('Error updating card position:', err);
        this.showErrorToast('Failed to move card');
      }
      
      // Don't reload board - restoration is DOM-only
    }
  }

  restoreCardPosition(cardElement, originalPosition) {
    try {
      // Restore data attributes
      cardElement.setAttribute('data-column-id', originalPosition.columnId);
      cardElement.setAttribute('data-order', originalPosition.order);
      
      // Validate container is still attached to the document
      if (originalPosition.container && document.contains(originalPosition.container)) {
        if (originalPosition.nextSibling && originalPosition.container.contains(originalPosition.nextSibling)) {
          // Insert before the next sibling (exact original position)
          originalPosition.container.insertBefore(cardElement, originalPosition.nextSibling);
        } else {
          // If next sibling is gone, append at end
          const addCardBtn = originalPosition.container.querySelector('.add-card-btn');
          if (addCardBtn) {
            originalPosition.container.insertBefore(cardElement, addCardBtn);
          } else {
            originalPosition.container.appendChild(cardElement);
          }
        }
        
      } else {
        console.warn('Cannot restore card: original container is no longer in the document');
        // Container was removed (column deleted or board reloaded)
        // The calling function will reload the board to get fresh state
      }
    } catch (err) {
      console.error('Failed to restore card position:', err);
      // Will fall back to board reload in calling function
    }
  }

  /**
   * Add a time interval to a date without mutating the original.
   * Handles month/year additions correctly to avoid mutation issues.
   * 
   * @param {Date} date - The base date
   * @param {number} amount - How many units to add
   * @param {string} unit - The unit (minute, hour, day, week, month, year)
   * @returns {Date} A new Date object with the interval added
   */
  addInterval(date, amount, unit) {
    switch (unit) {
      case 'minute':
        return new Date(date.getTime() + amount * 60 * 1000);
      case 'hour':
        return new Date(date.getTime() + amount * 60 * 60 * 1000);
      case 'day':
        return new Date(date.getTime() + amount * 24 * 60 * 60 * 1000);
      case 'week':
        return new Date(date.getTime() + amount * 7 * 24 * 60 * 60 * 1000);
      case 'month': {
        // Create new date to avoid mutation
        const newDate = new Date(date);
        newDate.setMonth(newDate.getMonth() + amount);
        return newDate;
      }
      case 'year': {
        // Create new date to avoid mutation
        const newDate = new Date(date);
        newDate.setFullYear(newDate.getFullYear() + amount);
        return newDate;
      }
      default:
        return new Date(date);
    }
  }

  async openScheduleModal(cardId, cardData, hasSchedule) {
    // Check database connection before opening modal
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot open schedule editor: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
    // If card has a schedule, fetch the schedule details
    let scheduleData = null;
    if (hasSchedule && cardData.schedule) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      try {
        const response = await fetch(`/api/schedules/${cardData.schedule}`, {
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        const data = await this.parseResponse(response);
        
        if (data.success) {
          scheduleData = data.schedule;
        } else {
          this.showErrorToast(`Failed to load schedule: ${data.message}`);
          return;
        }
      } catch (err) {
        clearTimeout(timeoutId);
        console.error('Error fetching schedule:', err);
        
        if (err.name === 'AbortError') {
          this.showErrorToast('Load schedule timed out (5s). Please check your connection.');
        } else {
          this.showErrorToast(`Error loading schedule: ${err.message}`);
        }
        return;
      }
    }

    // Set default values
    const now = new Date();
    const defaultStartDatetime = scheduleData?.start_datetime 
      ? scheduleData.start_datetime.substring(0, 16) // Format: YYYY-MM-DDTHH:MM
      : now.toISOString().substring(0, 16); // Current date and time
    const defaultEndDatetime = scheduleData?.end_datetime 
      ? scheduleData.end_datetime.substring(0, 16)
      : '';
    const defaultRunEvery = scheduleData?.run_every || 1;
    const defaultUnit = scheduleData?.unit || 'day';
    const defaultEnabled = scheduleData?.schedule_enabled !== false;
    const defaultAllowDuplicates = scheduleData?.allow_duplicates || false;

    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="schedule-modal">
        <div class="modal-content schedule-modal-content">
          <div class="modal-header">
            <div class="modal-header-actions">
              ${hasSchedule ? `<button type="button" class="btn btn-secondary" id="edit-template-btn" data-card-id="${scheduleData?.card_id || ''}">Edit Template</button>` : ''}
              ${hasSchedule ? `<button type="button" class="btn btn-danger" id="delete-schedule-btn">Delete Schedule</button>` : ''}
              <button type="button" class="btn btn-secondary" id="cancel-schedule-btn">Cancel</button>
              <button type="submit" form="schedule-form" class="btn btn-primary">${hasSchedule ? 'Update Schedule' : 'Create Schedule'}</button>
            </div>
            <h2>${hasSchedule ? 'Edit Schedule' : 'Create Schedule'}</h2>
          </div>
          <form id="schedule-form">
            <div class="form-row">
              <div class="form-group">
                <label for="schedule-run-every">Run Every:</label>
                <input type="number" id="schedule-run-every" name="run-every" min="1" value="${defaultRunEvery}" required>
              </div>
              <div class="form-group">
                <label for="schedule-unit">Unit:</label>
                <select id="schedule-unit" name="unit" required>
                  <option value="minute" ${defaultUnit === 'minute' ? 'selected' : ''}>Minute(s)</option>
                  <option value="hour" ${defaultUnit === 'hour' ? 'selected' : ''}>Hour(s)</option>
                  <option value="day" ${defaultUnit === 'day' ? 'selected' : ''}>Day(s)</option>
                  <option value="week" ${defaultUnit === 'week' ? 'selected' : ''}>Week(s)</option>
                  <option value="month" ${defaultUnit === 'month' ? 'selected' : ''}>Month(s)</option>
                  <option value="year" ${defaultUnit === 'year' ? 'selected' : ''}>Year(s)</option>
                </select>
              </div>
            </div>

            <div class="form-row">
              <div class="form-group full-width">
                <label for="schedule-start-datetime">Start Date & Time:</label>
                <input type="datetime-local" id="schedule-start-datetime" name="start-datetime" value="${defaultStartDatetime}" required>
              </div>
            </div>

            <div class="form-row">
              <div class="form-group full-width">
                <label for="schedule-end-datetime">End Date & Time (Optional):</label>
                <input type="datetime-local" id="schedule-end-datetime" name="end-datetime" value="${defaultEndDatetime}">
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" id="schedule-enabled" name="enabled" ${defaultEnabled ? 'checked' : ''}>
                <span>Schedule Enabled</span>
              </label>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" id="schedule-allow-duplicates" name="allow-duplicates" ${defaultAllowDuplicates ? 'checked' : ''}>
                <span>Allow Duplicates (create new cards even if unarchived cards from this schedule exist)</span>
              </label>
            </div>

            ${!hasSchedule ? `
            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" id="schedule-keep-source" name="keep-source" checked>
                <span>Keep Original Card (if unchecked, the original card will be deleted after creating the schedule template)</span>
              </label>
            </div>
            ` : ''}

            <div class="next-runs-section" id="next-runs-section">
              <h3>Next 4 Scheduled Runs</h3>
              <div class="next-runs-list" id="next-runs-list">
                <p class="next-runs-loading">Calculating...</p>
              </div>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('schedule-modal');
    const form = document.getElementById('schedule-form');
    const cancelBtn = document.getElementById('cancel-schedule-btn');
    const deleteBtn = document.getElementById('delete-schedule-btn');
    const runEveryInput = document.getElementById('schedule-run-every');
    const unitSelect = document.getElementById('schedule-unit');
    const startDatetimeInput = document.getElementById('schedule-start-datetime');
    const endDatetimeInput = document.getElementById('schedule-end-datetime');
    const nextRunsList = document.getElementById('next-runs-list');

    // Function to calculate and display next runs
    const updateNextRuns = async () => {
      const runEvery = parseInt(runEveryInput.value);
      const unit = unitSelect.value;
      const startDatetime = startDatetimeInput.value;
      const endDatetime = endDatetimeInput.value || null;

      if (!runEvery || !unit || !startDatetime) {
        nextRunsList.innerHTML = '<p class="next-runs-empty">Please fill in required fields</p>';
        return;
      }

      try {
        // Calculate next runs client-side
        const startDateTime = new Date(startDatetime);
        const endDateTime = endDatetime ? new Date(endDatetime) : null;
        const now = new Date();

        let runs = [];
        let current = startDateTime;
        let attempts = 0;
        const maxAttempts = 100;

        while (runs.length < 4 && attempts < maxAttempts) {
          attempts++;
          
          if (current >= now && (!endDateTime || current <= endDateTime)) {
            runs.push(new Date(current));
          }

          // Add interval using utility function
          current = this.addInterval(current, runEvery, unit);

          if (endDateTime && current > endDateTime) break;
        }

        if (runs.length === 0) {
          nextRunsList.innerHTML = '<p class="next-runs-empty">No upcoming runs (schedule may have ended)</p>';
        } else {
          nextRunsList.innerHTML = runs.map(run => {
            const dateStr = run.toLocaleDateString('en-US', { 
              weekday: 'short', 
              year: 'numeric', 
              month: 'short', 
              day: 'numeric' 
            });
            const timeStr = formatTimeSync(run);
            return `<div class="next-run-item">📅 ${dateStr} at ${timeStr}</div>`;
          }).join('');
        }
      } catch (err) {
        console.error('Error calculating next runs:', err);
        nextRunsList.innerHTML = '<p class="next-runs-error">Error calculating runs</p>';
      }
    };

    // Initial calculation
    updateNextRuns();

    // Track changes
    let hasUnsavedChanges = false;
    
    // Update on input changes
    [runEveryInput, unitSelect, startDatetimeInput, endDatetimeInput].forEach(input => {
      input.addEventListener('change', () => {
        hasUnsavedChanges = true;
        updateNextRuns();
      });
      input.addEventListener('input', () => {
        hasUnsavedChanges = true;
        // Debounce for text inputs
        clearTimeout(input.updateTimeout);
        input.updateTimeout = setTimeout(updateNextRuns, 500);
      });
    });
    
    // Track checkbox changes
    const enabledCheckbox = document.getElementById('schedule-enabled');
    const duplicatesCheckbox = document.getElementById('schedule-allow-duplicates');
    [enabledCheckbox, duplicatesCheckbox].forEach(checkbox => {
      if (checkbox) {
        checkbox.addEventListener('change', () => {
          hasUnsavedChanges = true;
        });
      }
    });

    // Handle cancel with warning
    let isCancelling = false;
    const handleCancel = async () => {
      // Atomic check-and-set: if already cancelling, return immediately
      if (isCancelling) return;
      isCancelling = true;
      
      // Disable cancel button immediately to prevent double-clicks
      const wasCancelDisabled = cancelBtn.disabled;
      cancelBtn.disabled = true;
      
      try {
        if (hasUnsavedChanges) {
          if (!await showConfirm('You have unsaved changes. Are you sure you want to cancel?', 'Confirm Cancellation')) {
            // User cancelled the cancellation, re-enable button
            cancelBtn.disabled = wasCancelDisabled;
            isCancelling = false;
            return;
          }
        }
        modal.remove();
      } catch (err) {
        // Re-enable button on error
        cancelBtn.disabled = wasCancelDisabled;
        isCancelling = false;
        console.error('Error during cancel:', err);
      }
    };
    
    cancelBtn.addEventListener('click', handleCancel);

    // Handle delete
    if (deleteBtn) {
      deleteBtn.addEventListener('click', async () => {
        if (!await showConfirm('Are you sure you want to delete this schedule? This will not delete cards already created.', 'Confirm Deletion')) {
          return;
        }

        // Show deleting state
        deleteBtn.disabled = true;
        deleteBtn.textContent = 'Deleting...';

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        try {
          const response = await fetch(`/api/schedules/${scheduleData.id}`, {
            method: 'DELETE',
            signal: controller.signal
          });

          clearTimeout(timeoutId);
          const data = await this.parseResponse(response);

          if (data.success) {
            modal.remove();
            // Close the edit card modal too
            const editModal = document.getElementById('edit-card-modal');
            if (editModal) editModal.remove();
            await this.loadBoard();
          } else {
            deleteBtn.disabled = false;
            deleteBtn.textContent = 'Delete Schedule';
            this.showErrorToast(`Failed to delete schedule: ${data.message}`);
          }
        } catch (err) {
          clearTimeout(timeoutId);
          console.error('Error deleting schedule:', err);
          deleteBtn.disabled = false;
          deleteBtn.textContent = 'Delete Schedule';
          
          if (err.name === 'AbortError') {
            this.showErrorToast('Delete schedule timed out (5s). Please check your connection.');
          } else {
            this.showErrorToast('An error occurred while deleting the schedule');
          }
        }
      });
    }

    // Handle edit template button
    const editTemplateBtn = document.getElementById('edit-template-btn');
    if (editTemplateBtn) {
      editTemplateBtn.addEventListener('click', async () => {
        const templateCardId = parseInt(editTemplateBtn.getAttribute('data-card-id'));
        if (templateCardId) {
          // Show loading state
          editTemplateBtn.disabled = true;
          editTemplateBtn.textContent = 'Loading...';

          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 5000);

          // Fetch the template card data
          try {
            const response = await fetch(`/api/cards/${templateCardId}`, {
              signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            const data = await this.parseResponse(response);
            
            if (data.success) {
              // Close schedule modal
              modal.remove();
              // Open edit card modal for the template
              this.openEditCardModal(templateCardId, data.card);
            } else {
              editTemplateBtn.disabled = false;
              editTemplateBtn.textContent = 'Edit Template';
              this.showErrorToast(`Failed to load template card: ${data.message}`);
            }
          } catch (err) {
            clearTimeout(timeoutId);
            console.error('Error loading template card:', err);
            editTemplateBtn.disabled = false;
            editTemplateBtn.textContent = 'Edit Template';
            
            if (err.name === 'AbortError') {
              this.showErrorToast('Load template card timed out (5s). Please check your connection.');
            } else {
              this.showErrorToast('Error loading template card');
            }
          }
        }
      });
    }

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const formData = {
        run_every: parseInt(runEveryInput.value),
        unit: unitSelect.value,
        start_datetime: startDatetimeInput.value ? new Date(startDatetimeInput.value).toISOString() : null,
        end_datetime: endDatetimeInput.value ? new Date(endDatetimeInput.value).toISOString() : null,
        schedule_enabled: document.getElementById('schedule-enabled').checked,
        allow_duplicates: document.getElementById('schedule-allow-duplicates').checked
      };

      // Show saving state
      const saveBtn = modal.querySelector('button[type="submit"]');
      saveBtn.disabled = true;
      saveBtn.textContent = hasSchedule ? 'Updating...' : 'Creating...';

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      try {
        let response;
        
        if (hasSchedule) {
          // Update existing schedule
          response = await fetch(`/api/schedules/${scheduleData.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData),
            signal: controller.signal
          });
        } else {
          // Create new schedule
          const keepSourceCheckbox = document.getElementById('schedule-keep-source');
          response = await fetch('/api/schedules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              card_id: cardId,
              keep_source_card: keepSourceCheckbox ? keepSourceCheckbox.checked : true,
              ...formData
            }),
            signal: controller.signal
          });
        }

        clearTimeout(timeoutId);
        const data = await this.parseResponse(response);

        if (data.success) {
          modal.remove();
          // Close the edit card modal too
          const editModal = document.getElementById('edit-card-modal');
          if (editModal) editModal.remove();
          await this.loadBoard();
        } else {
          saveBtn.disabled = false;
          saveBtn.textContent = hasSchedule ? 'Update Schedule' : 'Create Schedule';
          this.showErrorToast(`Failed to save schedule: ${data.message}`);
        }
      } catch (err) {
        clearTimeout(timeoutId);
        console.error('Error saving schedule:', err);
        saveBtn.disabled = false;
        saveBtn.textContent = hasSchedule ? 'Update Schedule' : 'Create Schedule';
        
        if (err.name === 'AbortError') {
          this.showErrorToast('Save schedule timed out (5s). Please check your connection.');
        } else {
          this.showErrorToast('An error occurred while saving the schedule');
        }
      }
    });

    // Close modal when clicking outside (ignore text selection drags)
    setupModalBackgroundClose(modal, handleCancel);
  }

  openAddColumnModal() {
    // Check database connection
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot add column: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
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

    // Close modal on background click (ignore text selection drags)
    setupModalBackgroundClose(modal, () => modal.remove());
  }

  async openAddTemplateWithScheduleModal(columnId, order = null) {
    // Check database connection
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot create scheduled card: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
    // Track the last used column for keyboard shortcuts
    this.lastUsedColumnId = columnId;
    
    // Track checklist items to be created
    let pendingChecklistItems = [];
    let checklistVisible = false;
    let hasUnsavedChanges = false;
    
    // Set default values for schedule
    const now = new Date();
    const defaultStartDatetime = now.toISOString().substring(0, 16); // Format: YYYY-MM-DDTHH:MM
    const defaultRunEvery = 1;
    const defaultUnit = 'day';
    const defaultEnabled = true;
    const defaultAllowDuplicates = false;
    
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="add-template-schedule-modal">
        <div class="modal-content schedule-modal-content">
          <div class="modal-header">
            <div class="modal-header-actions">
              <button type="button" class="btn btn-secondary" id="cancel-template-schedule-btn">Cancel</button>
              <button type="submit" form="add-template-schedule-form" class="btn btn-primary">Create Template & Schedule</button>
            </div>
            <h2>Add New Template with Schedule</h2>
          </div>
          <form id="add-template-schedule-form">
            <div class="form-group">
              <label for="template-title">Title:</label>
              <input type="text" id="template-title" name="template-title" required>
            </div>
            <div class="form-group">
              <label for="template-description">Description:</label>
              <textarea id="template-description" name="template-description" rows="4"></textarea>
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
                <div class="checklist-items" id="new-template-checklist-items"></div>
                <button type="button" class="btn btn-secondary btn-sm" id="add-checklist-item-bottom-btn">+ Add Item</button>
              </div>
            </div>
            
            <hr style="margin: 30px 0; border: none; border-top: 2px solid var(--border-color);">
            
            <h3 style="margin-bottom: 20px;">Schedule Settings</h3>
            
            <div class="form-row">
              <div class="form-group">
                <label for="template-schedule-run-every">Run Every:</label>
                <input type="number" id="template-schedule-run-every" name="run-every" min="1" value="${defaultRunEvery}" required>
              </div>
              <div class="form-group">
                <label for="template-schedule-unit">Unit:</label>
                <select id="template-schedule-unit" name="unit" required>
                  <option value="minute" ${defaultUnit === 'minute' ? 'selected' : ''}>Minute(s)</option>
                  <option value="hour" ${defaultUnit === 'hour' ? 'selected' : ''}>Hour(s)</option>
                  <option value="day" ${defaultUnit === 'day' ? 'selected' : ''}>Day(s)</option>
                  <option value="week" ${defaultUnit === 'week' ? 'selected' : ''}>Week(s)</option>
                  <option value="month" ${defaultUnit === 'month' ? 'selected' : ''}>Month(s)</option>
                  <option value="year" ${defaultUnit === 'year' ? 'selected' : ''}>Year(s)</option>
                </select>
              </div>
            </div>

            <div class="form-row">
              <div class="form-group full-width">
                <label for="template-schedule-start-datetime">Start Date & Time:</label>
                <input type="datetime-local" id="template-schedule-start-datetime" name="start-datetime" value="${defaultStartDatetime}" required>
              </div>
            </div>

            <div class="form-row">
              <div class="form-group full-width">
                <label for="template-schedule-end-datetime">End Date & Time (Optional):</label>
                <input type="datetime-local" id="template-schedule-end-datetime" name="end-datetime">
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" id="template-schedule-enabled" name="enabled" ${defaultEnabled ? 'checked' : ''}>
                <span>Schedule Enabled</span>
              </label>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" id="template-schedule-allow-duplicates" name="allow-duplicates" ${defaultAllowDuplicates ? 'checked' : ''}>
                <span>Allow Duplicates (create new cards even if unarchived cards from this schedule exist)</span>
              </label>
            </div>

            <div class="next-runs-section" id="next-runs-section">
              <h3>Next 4 Scheduled Runs</h3>
              <div class="next-runs-list" id="next-runs-list">
                <p class="next-runs-loading">Calculating...</p>
              </div>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('add-template-schedule-modal');
    const form = document.getElementById('add-template-schedule-form');
    const cancelBtn = document.getElementById('cancel-template-schedule-btn');
    const titleInput = document.getElementById('template-title');
    const runEveryInput = document.getElementById('template-schedule-run-every');
    const unitSelect = document.getElementById('template-schedule-unit');
    const startDatetimeInput = document.getElementById('template-schedule-start-datetime');
    const endDatetimeInput = document.getElementById('template-schedule-end-datetime');
    const nextRunsList = document.getElementById('next-runs-list');
    const checklistHeaderContainer = document.getElementById('checklist-header-container');
    const checklistContentContainer = document.getElementById('checklist-content-container');
    const checklistContainer = document.getElementById('new-template-checklist-items');

    // Focus on title input
    titleInput.focus();
    
    // Track changes in title and description
    titleInput.addEventListener('input', () => {
      hasUnsavedChanges = titleInput.value.trim() !== '';
    });
    
    const descriptionInput = document.getElementById('template-description');
    descriptionInput.addEventListener('input', () => {
      hasUnsavedChanges = titleInput.value.trim() !== '' || descriptionInput.value.trim() !== '';
    });
    
    // Track changes in schedule fields
    [runEveryInput, unitSelect, startDatetimeInput, endDatetimeInput].forEach(input => {
      input.addEventListener('input', () => {
        hasUnsavedChanges = true;
      });
      input.addEventListener('change', () => {
        hasUnsavedChanges = true;
      });
    });
    
    // Checklist management
    const updateChecklistSummary = () => {
      const summaryElement = document.getElementById('checklist-summary');
      if (summaryElement) {
        const total = pendingChecklistItems.length;
        const checked = pendingChecklistItems.filter(i => i.checked).length;
        const percentage = calculateChecklistPercentage(pendingChecklistItems);
        summaryElement.textContent = `${checked}/${total} (${percentage}%)`;
      }
    };
    
    this.setupNewCardChecklistDragAndDrop(checklistContainer, pendingChecklistItems);
    
    const checklistManager = new ChecklistManager(checklistContainer, pendingChecklistItems, {
      updateSummary: updateChecklistSummary,
      deleteButtonClass: 'checklist-delete-btn-new',
      onItemAdded: () => { hasUnsavedChanges = true; },
      onItemChanged: () => { hasUnsavedChanges = true; }
    });
    
    const showChecklistUI = () => {
      if (!checklistVisible) {
        checklistVisible = true;
        checklistHeaderContainer.style.display = 'none';
        checklistContentContainer.style.display = 'block';
      }
    };

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

    // Function to calculate and display next runs
    const updateNextRuns = async () => {
      const runEvery = parseInt(runEveryInput.value);
      const unit = unitSelect.value;
      const startDatetime = startDatetimeInput.value;
      const endDatetime = endDatetimeInput.value || null;

      if (!runEvery || !unit || !startDatetime) {
        nextRunsList.innerHTML = '<p class="next-runs-empty">Please fill in required fields</p>';
        return;
      }

      try {
        // Calculate next runs client-side
        const startDateTime = new Date(startDatetime);
        const endDateTime = endDatetime ? new Date(endDatetime) : null;
        const now = new Date();

        let runs = [];
        let current = startDateTime;
        let attempts = 0;
        const maxAttempts = 100;

        while (runs.length < 4 && attempts < maxAttempts) {
          attempts++;
          
          if (current >= now && (!endDateTime || current <= endDateTime)) {
            runs.push(new Date(current));
          }

          // Add interval using utility function
          current = this.addInterval(current, runEvery, unit);

          if (endDateTime && current > endDateTime) break;
        }

        if (runs.length === 0) {
          nextRunsList.innerHTML = '<p class="next-runs-empty">No upcoming runs (schedule may have ended)</p>';
        } else {
          nextRunsList.innerHTML = runs.map(run => {
            const dateStr = run.toLocaleDateString('en-US', { 
              weekday: 'short', 
              year: 'numeric', 
              month: 'short', 
              day: 'numeric' 
            });
            const timeStr = formatTimeSync(run);
            return `<div class="next-run-item">📅 ${dateStr} at ${timeStr}</div>`;
          }).join('');
        }
      } catch (err) {
        console.error('Error calculating next runs:', err);
        nextRunsList.innerHTML = '<p class="next-runs-error">Error calculating runs</p>';
      }
    };

    // Update next runs on input change
    runEveryInput.addEventListener('input', updateNextRuns);
    unitSelect.addEventListener('change', updateNextRuns);
    startDatetimeInput.addEventListener('change', updateNextRuns);
    endDatetimeInput.addEventListener('change', updateNextRuns);

    // Initial calculation
    updateNextRuns();

    // Handle cancel with warning if there are unsaved changes
    let isCancelling = false;
    const handleCancel = async () => {
      // Atomic check-and-set: if already cancelling, return immediately
      if (isCancelling) return;
      isCancelling = true;
      
      // Disable cancel button immediately to prevent double-clicks
      const wasCancelDisabled = cancelBtn.disabled;
      cancelBtn.disabled = true;
      
      try {
        // Check if there's any content or checklist items
        const hasContent = hasUnsavedChanges || pendingChecklistItems.some(item => item.name && item.name.trim());
        
        if (hasContent) {
          if (await showConfirm('You have unsaved changes. Are you sure you want to cancel?', 'Confirm Cancellation')) {
            modal.remove();
          } else {
            // User cancelled the cancellation, re-enable button
            cancelBtn.disabled = wasCancelDisabled;
            isCancelling = false;
          }
        } else {
          modal.remove();
        }
      } catch (err) {
        // Re-enable button on error
        cancelBtn.disabled = wasCancelDisabled;
        isCancelling = false;
        console.error('Error during cancel:', err);
      }
    };
    
    cancelBtn.addEventListener('click', handleCancel);

    // Handle form submit - create template card with schedule in one API call
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const title = titleInput.value.trim();
      const description = document.getElementById('template-description').value.trim();
      const validChecklistItems = pendingChecklistItems.filter(item => item.name && item.name.trim());

      const scheduleData = {
        run_every: parseInt(runEveryInput.value),
        unit: unitSelect.value,
        start_datetime: startDatetimeInput.value ? new Date(startDatetimeInput.value).toISOString() : null,
        end_datetime: endDatetimeInput.value ? new Date(endDatetimeInput.value).toISOString() : null,
        schedule_enabled: document.getElementById('template-schedule-enabled').checked,
        allow_duplicates: document.getElementById('template-schedule-allow-duplicates').checked
      };

      try {
        // Step 1: Create the template card
        const cardBody = {
          title,
          description,
          scheduled: true
        };
        if (order !== null) {
          cardBody.order = order;
        }

        const cardResponse = await fetch(`/api/columns/${columnId}/cards`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(cardBody)
        });

        const cardData = await this.parseResponse(cardResponse);

        if (!cardData.success) {
          await showAlert('Failed to create template card: ' + cardData.message, 'Error');
          return;
        }

        const cardId = cardData.card.id;

        // Step 2: Create checklist items if any
        if (validChecklistItems.length > 0) {
          for (let i = 0; i < validChecklistItems.length; i++) {
            const item = validChecklistItems[i];
            await this.createChecklistItem(cardId, item.name, i, item.checked || false);
          }
        }

        // Step 3: Create the schedule
        const scheduleResponse = await fetch('/api/schedules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            card_id: cardId,
            ...scheduleData,
            keep_source_card: false // Don't keep original since it IS the template
          })
        });

        const scheduleResponseData = await this.parseResponse(scheduleResponse);

        if (scheduleResponseData.success) {
          modal.remove();
          await this.loadBoard();
        } else {
          await showAlert('Failed to create schedule: ' + scheduleResponseData.message, 'Error');
        }

      } catch (err) {
        console.error('Error creating template with schedule:', err);
        await showAlert('Error creating template with schedule', 'Error');
      }
    });

    // Close modal on background click with warning (ignore text selection drags)
    setupModalBackgroundClose(modal, handleCancel);
  }

  async createColumn(name) {
    // Check database connection before creating column
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot create column: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
    try {
      const response = await fetch(`/api/boards/${this.boardId}/columns`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });

      const data = await this.parseResponse(response);

      if (data.success) {
        // Reload columns to show the new one
        await this.loadBoard();
      } else {
        await showAlert('Failed to create column: ' + data.message, 'Error');
      }
    } catch (err) {
      await showAlert('Error creating column: ' + err.message, 'Error');
    }
  }

  async deleteColumn(columnId) {
    if (!await showConfirm('Are you sure you want to delete this column?', 'Confirm Deletion')) {
      return;
    }

    try {
      const response = await fetch(`/api/columns/${columnId}`, {
        method: 'DELETE'
      });

      const data = await this.parseResponse(response);

      if (data.success) {
        // Reload columns to reflect deletion
        await this.loadBoard();
      } else {
        await showAlert('Failed to delete column: ' + data.message, 'Error');
      }
    } catch (err) {
      await showAlert('Error deleting column: ' + err.message, 'Error');
    }
  }

  async deleteAllCardsInColumn(columnId) {
    if (!await showConfirm('Are you sure you want to delete all cards in this column? This action cannot be undone.', 'Confirm Deletion')) {
      return;
    }

    try {
      const url = `/api/columns/${columnId}/cards`;
      
      const response = await fetch(url, {
        method: 'DELETE'
      });

      const data = await this.parseResponse(response);

      if (data.success) {
        // Reload board to reflect deletion
        await this.loadBoard();
      } else {
        await showAlert('Failed to delete cards: ' + data.message, 'Error');
      }
    } catch (err) {
      console.error('Error deleting cards:', err);
      await showAlert('Error deleting cards: ' + err.message, 'Error');
    }
  }

  async archiveAllCardsInColumn(columnId) {
    const column = this.columns.find(c => c.id === columnId);
    if (!column || !column.cards) {
      await showAlert('No cards found in this column', 'Warning');
      return;
    }

    // Get all unarchived cards
    const unarchivedCards = column.cards.filter(c => !c.archived);
    if (unarchivedCards.length === 0) {
      await showAlert('No active cards to archive in this column', 'Warning');
      return;
    }

    if (!await showConfirm(`Are you sure you want to archive all ${unarchivedCards.length} active card(s) in this column?`, 'Confirm Archive')) {
      return;
    }

    try {
      const cardIds = unarchivedCards.map(c => c.id);
      const response = await fetch('/api/cards/batch/archive', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ card_ids: cardIds })
      });

      const data = await this.parseResponse(response);

      if (data.success) {
        await this.loadBoard();
        await showAlert(`Successfully archived ${data.archived_count} card(s)`, 'Success');
      } else {
        await showAlert('Failed to archive cards: ' + data.message, 'Error');
      }
    } catch (err) {
      console.error('Error archiving cards:', err);
      await showAlert('Error archiving cards: ' + err.message, 'Error');
    }
  }

  async unarchiveAllCardsInColumn(columnId) {
    const column = this.columns.find(c => c.id === columnId);
    if (!column || !column.cards) {
      await showAlert('No cards found in this column', 'Warning');
      return;
    }

    // Get all archived cards
    const archivedCards = column.cards.filter(c => c.archived);
    if (archivedCards.length === 0) {
      await showAlert('No archived cards to unarchive in this column', 'Warning');
      return;
    }

    if (!confirm(`Are you sure you want to unarchive all ${archivedCards.length} archived card(s) in this column?`)) {
      return;
    }

    try {
      const cardIds = archivedCards.map(c => c.id);
      const response = await fetch('/api/cards/batch/unarchive', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ card_ids: cardIds })
      });

      const data = await this.parseResponse(response);

      if (data.success) {
        await this.loadBoard();
        await showAlert(`Successfully unarchived ${data.unarchived_count} card(s)`, 'Success');
      } else {
        await showAlert('Failed to unarchive cards: ' + data.message, 'Error');
      }
    } catch (err) {
      console.error('Error unarchiving cards:', err);
      await showAlert('Error unarchiving cards: ' + err.message, 'Error');
    }
  }

  async openMoveAllCardsModal(sourceColumnId) {
    // Check database connection
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot move cards: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
    // Get source column and its cards
    const sourceColumn = this.columns.find(c => c.id === sourceColumnId);
    if (!sourceColumn || !sourceColumn.cards || sourceColumn.cards.length === 0) {
      await showAlert('No cards to move in this column', 'Warning');
      return;
    }

    // Get target columns (exclude source column)
    const targetColumns = this.columns.filter(c => c.id !== sourceColumnId);
    if (targetColumns.length === 0) {
      await showAlert('No other columns available to move cards to', 'Warning');
      return;
    }

    // Count active cards (excluding archived) for display
    const activeCardCount = sourceColumn.cards.filter(c => !c.archived).length;
    const archivedCardCount = sourceColumn.cards.filter(c => c.archived).length;
    
    // Build card count message
    let cardCountMessage;
    if (archivedCardCount > 0) {
      cardCountMessage = `${activeCardCount} active card(s)`;
      if (archivedCardCount > 0) {
        cardCountMessage += ` (${archivedCardCount} archived)`;
      }
    } else {
      cardCountMessage = `${activeCardCount} card(s)`;
    }

    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="move-all-cards-modal">
        <div class="modal-content">
          <h2>Move All Cards</h2>
          <p>Move ${cardCountMessage} from <strong>${this.escapeHtml(sourceColumn.name)}</strong> to:</p>
          <form id="move-all-cards-form">
            <div class="form-group">
              <label for="target-column-select">Target Column:</label>
              <select id="target-column-select" name="target-column" required>
                <option value="">-- Select Column --</option>
                ${targetColumns.map(col => `
                  <option value="${col.id}">${this.escapeHtml(col.name)}</option>
                `).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="position-select">Position:</label>
              <select id="position-select" name="position" required>
                <option value="top">Top of column</option>
                <option value="bottom">Bottom of column</option>
              </select>
            </div>
            <div class="form-group">
              <label>
                <input type="checkbox" id="include-archived-checkbox" name="include-archived">
                Include archived cards
              </label>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancel-move-all-btn">Cancel</button>
              <button type="submit" class="btn btn-primary">Move Cards</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Get modal elements
    const modal = document.getElementById('move-all-cards-modal');
    const form = document.getElementById('move-all-cards-form');
    const cancelBtn = document.getElementById('cancel-move-all-btn');
    const targetSelect = document.getElementById('target-column-select');
    const positionSelect = document.getElementById('position-select');
    const includeArchivedCheckbox = document.getElementById('include-archived-checkbox');

    // Focus on select
    targetSelect.focus();

    // Handle cancel
    cancelBtn.addEventListener('click', () => {
      modal.remove();
    });

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const targetColumnId = parseInt(targetSelect.value);
      const position = positionSelect.value;
      const includeArchived = includeArchivedCheckbox.checked;
      
      if (targetColumnId && position) {
        modal.remove();
        await this.moveAllCards(sourceColumnId, targetColumnId, position, includeArchived);
      }
    });

    // Close modal on background click (ignore text selection drags)
    setupModalBackgroundClose(modal, () => modal.remove());
  }

  async moveAllCards(sourceColumnId, targetColumnId, position, includeArchived = false) {
    // Get source column's cards
    const sourceColumn = this.columns.find(c => c.id === sourceColumnId);
    if (!sourceColumn || !sourceColumn.cards || sourceColumn.cards.length === 0) {
      return;
    }

    // Get target column to determine starting order for bottom position
    const targetColumn = this.columns.find(c => c.id === targetColumnId);
    if (!targetColumn) {
      await showAlert('Target column not found', 'Error');
      return;
    }

    try {
      // Use batch move endpoint for atomic operation
      const response = await fetch(`/api/columns/${sourceColumnId}/cards/move`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          target_column_id: targetColumnId,
          position: position,
          include_archived: includeArchived
        })
      });

      const data = await this.parseResponse(response);
      
      if (!data.success) {
        throw new Error(data.message || 'Failed to move cards');
      }
      
      // Reload board to reflect changes
      await this.loadBoard();
      
      await showAlert(`Successfully moved ${data.moved_count} card(s)`, 'Success');
    } catch (err) {
      console.error('Error moving cards:', err);
      await showAlert('Error moving cards: ' + err.message, 'Error');
    }
  }

  openEditColumnModal(columnId, currentName) {
    // Check database connection
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot edit column: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
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

    // Close modal on background click (ignore text selection drags)
    setupModalBackgroundClose(modal, () => modal.remove());
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

      const data = await this.parseResponse(response);

      if (data.success) {
        // Reload columns to show the updated name
        await this.loadBoard();
      } else {
        await showAlert('Failed to update column: ' + data.message, 'Error');
      }
    } catch (err) {
      await showAlert('Error updating column: ' + err.message, 'Error');
    }
  }

  openAddCardModal(columnId, order = null, scheduled = false) {
    // Check database connection before opening modal
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot create card: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
    // If we're in scheduled view, open the combined template+schedule modal instead
    if (scheduled) {
      this.openAddTemplateWithScheduleModal(columnId, order);
      return;
    }
    
    // Track the last used column for keyboard shortcuts
    this.lastUsedColumnId = columnId;
    
    // Track checklist items to be created
    let pendingChecklistItems = [];
    let checklistVisible = false;
    let hasUnsavedChanges = false;
    
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="add-card-modal">
        <div class="modal-content card-modal-content">
          <h2>${scheduled ? 'Add New Template Card' : 'Add New Card'}</h2>
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
    
    // Track changes in title and description
    titleInput.addEventListener('input', () => {
      hasUnsavedChanges = titleInput.value.trim() !== '';
    });
    
    const descriptionInput = document.getElementById('card-description');
    descriptionInput.addEventListener('input', () => {
      hasUnsavedChanges = titleInput.value.trim() !== '' || descriptionInput.value.trim() !== '';
    });
    
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
      deleteButtonClass: 'checklist-delete-btn-new',
      onItemAdded: () => { hasUnsavedChanges = true; },
      onItemChanged: () => { hasUnsavedChanges = true; }
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

    // Handle cancel with warning if there are unsaved changes
    let isCancelling = false;
    const handleCancel = async () => {
      // Atomic check-and-set: if already cancelling, return immediately
      if (isCancelling) return;
      isCancelling = true;
      
      // Disable cancel button immediately to prevent double-clicks
      const wasCancelDisabled = cancelBtn.disabled;
      cancelBtn.disabled = true;
      
      try {
        // Check if there's any content or checklist items
        const hasContent = hasUnsavedChanges || pendingChecklistItems.some(item => item.name && item.name.trim());
        
        if (hasContent) {
          if (await showConfirm('You have unsaved changes. Are you sure you want to cancel?', 'Confirm Cancellation')) {
            modal.remove();
          } else {
            // User cancelled the cancellation, re-enable button
            cancelBtn.disabled = wasCancelDisabled;
            isCancelling = false;
          }
        } else {
          modal.remove();
        }
      } catch (err) {
        // Re-enable button on error
        cancelBtn.disabled = wasCancelDisabled;
        isCancelling = false;
        console.error('Error during cancel:', err);
      }
    };
    
    cancelBtn.addEventListener('click', handleCancel);

    // Handle form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const title = titleInput.value.trim();
      const description = document.getElementById('card-description').value.trim();
      const submitBtn = form.querySelector('button[type="submit"]');
      
      if (title) {
        // Disable button and show loading state
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating...';
        submitBtn.style.opacity = '0.6';
        
        // Filter out empty checklist items
        const validChecklistItems = pendingChecklistItems.filter(item => item.name && item.name.trim());
        const success = await this.createCard(columnId, title, description, order, validChecklistItems, scheduled);
        
        if (success) {
          modal.remove();
        } else {
          // Re-enable button on failure - keep modal open
          submitBtn.disabled = false;
          submitBtn.textContent = originalText;
          submitBtn.style.opacity = '';
        }
      }
    });

    // Close modal on background click with warning (ignore text selection drags)
    setupModalBackgroundClose(modal, handleCancel);
  }

  async createCard(columnId, title, description, order = null, checklistItems = [], scheduled = false) {
    // Set 5 second timeout for the request
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const body = { title, description };
      if (order !== null) {
        body.order = order;
      }
      if (scheduled) {
        body.scheduled = scheduled;
      }
      
      const response = await fetch(`/api/columns/${columnId}/cards`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body),
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (data.success) {
        const cardId = data.card.id;
        
        // The server broadcasts card_created to other clients via WebSocket.
        // For the originating client, we reload the board immediately via loadBoard()
        // to ensure instant UI update without waiting for broadcast.
        
        // TODO: Consider creating a batch endpoint POST /api/cards/batch that accepts card + checklist items
        // in a single request to avoid multiple sequential API calls and ensure atomicity.
        // This would prevent race conditions and improve performance.
        // If there are checklist items, create them with their checked state
        if (checklistItems.length > 0) {
          for (let i = 0; i < checklistItems.length; i++) {
            const item = checklistItems[i];
            // Pass checked state directly to createChecklistItem
            await this.createChecklistItem(cardId, item.name, i, item.checked || false);
          }
        }
        
        // Reload board once at the end to show the new card
        await this.loadBoard();
        
        // If this is a template card, prompt to create a schedule
        if (scheduled) {
          const createSchedule = await showConfirm(
            'Template card created! Would you like to create a schedule for it now?\n\nSchedules automatically create new task cards from this template at regular intervals.',
            'Create Schedule?'
          );
          
          if (createSchedule) {
            try {
              this.openScheduleModal(cardId);
            } catch (err) {
              console.error('Error opening schedule modal:', err);
              this.showErrorToast('Failed to open schedule editor');
            }
          }
        }
        
        return true;
      } else {
        console.error('Failed to create card:', data.message);
        this.showErrorToast('Failed to create card');
        return false;
      }
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        console.error('Create card timeout after 5 seconds');
        this.showErrorToast('Request timed out. Check your connection.');
      } else {
        console.error('Error creating card:', err);
        this.showErrorToast('Failed to create card');
      }
      return false;
    }
  }

  openEditCardModal(cardId, cardData) {
    // Check database connection before opening modal
    if (window.header && !window.header.dbConnected) {
      this.showErrorToast('Cannot edit card: Database is not connected. Please wait for the connection to be restored.');
      return;
    }
    
    const checklistItems = cardData.checklist_items || [];
    const comments = cardData.comments || [];
    const hasChecklist = checklistItems.length > 0;
    const hasComments = comments.length > 0;
    
    // Remove any existing edit card modal to prevent duplicates
    const existingModal = document.getElementById('edit-card-modal');
    if (existingModal) {
      existingModal.remove();
    }
    
    // Store original values for change detection
    const originalTitle = cardData.title;
    const originalDescription = cardData.description || '';
    
    // Check if this is a scheduled template card
    const isTemplate = cardData.scheduled === true;
    
    // Track changes
    let hasUnsavedChanges = false;
    let checklistOrderChanged = false;
    
    // Create modal HTML
    const modalHtml = `
      <div class="modal" id="edit-card-modal">
        <div class="modal-content card-modal-content">
          <div class="modal-header">
            <div class="modal-header-actions">
              ${isTemplate ?
                `<button type="button" class="btn btn-secondary" id="edit-schedule-from-template-btn" data-card-id="${cardData.id}" data-has-schedule="${cardData.schedule ? 'true' : 'false'}">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 4px;">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                  Edit Schedule
                </button>` :
                cardData.archived ? 
                  `<button type="button" class="btn btn-secondary" id="unarchive-card-detail-btn" data-card-id="${cardData.id}">📂 Unarchive</button>` :
                  `${this.workingStyle === 'board_task_category' ? 
                    `<button type="button" class="btn btn-secondary" id="done-card-detail-btn" data-card-id="${cardData.id}" title="${cardData.done ? 'Mark as not done' : 'Mark as done'}">
                      ${cardData.done ? '○ Mark Not Done' : '✓ Mark Done'}
                    </button>` :
                    ''
                  }
                  <button type="button" class="btn btn-secondary" id="archive-card-detail-btn" data-card-id="${cardData.id}">🗄️ Archive</button>`
              }
              <button type="button" class="btn btn-secondary" id="cancel-edit-card-btn">Cancel</button>
              <button type="submit" form="edit-card-form" class="btn btn-primary">Save</button>
            </div>
            <h2>${isTemplate ? 'Edit Card Template' : 'Edit Card'}</h2>
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
            
            <div class="schedule-section">
              <button type="button" class="btn btn-secondary" id="schedule-card-btn" data-card-id="${cardData.id}" data-has-schedule="${cardData.schedule ? 'true' : 'false'}">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 4px;">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                ${cardData.schedule ? 'Edit Schedule' : 'Create Schedule'}
              </button>
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
            
            ${!isTemplate ? `
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
            ` : ''}
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
        // Get the card element for visual feedback
        const cardElement = document.querySelector(`.card[data-card-id="${cardId}"]`);
        modal.remove();
        await this.archiveCard(cardId, cardElement);
      });
    }

    // Handle unarchive button
    if (unarchiveBtn) {
      unarchiveBtn.addEventListener('click', async () => {
        // Get the card element for visual feedback
        const cardElement = document.querySelector(`.card[data-card-id="${cardId}"]`);
        modal.remove();
        await this.unarchiveCard(cardId, cardElement);
      });
    }

    // Handle done button (for board_task_category working style)
    const doneBtn = document.getElementById('done-card-detail-btn');
    if (doneBtn) {
      doneBtn.addEventListener('click', async () => {
        const cardElement = document.querySelector(`.card[data-card-id="${cardId}"]`);
        // Toggle done status
        const newDoneStatus = !cardData.done;
        // Wait for update to complete before removing modal
        await this.updateCardDoneStatus(cardId, newDoneStatus, cardElement);
        modal.remove();
      });
    }

    // Handle edit schedule button from template modal
    const editScheduleFromTemplateBtn = document.getElementById('edit-schedule-from-template-btn');
    if (editScheduleFromTemplateBtn) {
      editScheduleFromTemplateBtn.addEventListener('click', async () => {
        // Check for unsaved changes
        if (hasUnsavedChanges || hasUnpostedComment()) {
          if (!await showConfirm('You have unsaved changes. Are you sure you want to open the schedule editor? Your changes will be lost.', 'Confirm Action')) {
            return;
          }
        }
        
        const hasSchedule = editScheduleFromTemplateBtn.getAttribute('data-has-schedule') === 'true';
        
        // Show loading state on button
        const originalText = editScheduleFromTemplateBtn.innerHTML;
        editScheduleFromTemplateBtn.disabled = true;
        editScheduleFromTemplateBtn.innerHTML = '<span style="opacity: 0.6;">Loading...</span>';
        
        try {
          // Try to open schedule modal - this will show error toast if it fails
          await this.openScheduleModal(cardId, cardData, hasSchedule);
          // Only remove edit card modal if schedule modal opened successfully
          modal.remove();
        } catch (err) {
          console.error('Error opening schedule modal:', err);
          // Re-enable button on error
          editScheduleFromTemplateBtn.disabled = false;
          editScheduleFromTemplateBtn.innerHTML = originalText;
        }
      });
    }

    // Handle schedule button
    const scheduleBtn = document.getElementById('schedule-card-btn');
    if (scheduleBtn) {
      scheduleBtn.addEventListener('click', async () => {
        // Check for unsaved changes
        if (hasUnsavedChanges || hasUnpostedComment()) {
          if (!await showConfirm('You have unsaved changes. Are you sure you want to open the schedule editor? Your changes will be lost.', 'Confirm Action')) {
            return;
          }
        }
        
        const hasSchedule = scheduleBtn.getAttribute('data-has-schedule') === 'true';
        
        // Show loading state on button
        const originalText = scheduleBtn.innerHTML;
        scheduleBtn.disabled = true;
        scheduleBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 4px; opacity: 0.6;"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg><span style="opacity: 0.6;">Loading...</span>';
        
        try {
          // Try to open schedule modal - this will show error toast if it fails
          await this.openScheduleModal(cardId, cardData, hasSchedule);
          // Only remove edit card modal if schedule modal opened successfully
          modal.remove();
        } catch (err) {
          console.error('Error opening schedule modal:', err);
          // Re-enable button on error
          scheduleBtn.disabled = false;
          scheduleBtn.innerHTML = originalText;
        }
      });
    }

    // Handle cancel with warning if there are unsaved changes
    let isCancelling = false;
    const handleCancel = async () => {
      // Atomic check-and-set: if already cancelling, return immediately
      if (isCancelling) return;
      isCancelling = true;
      
      // Disable cancel button immediately to prevent double-clicks
      const wasCancelDisabled = cancelBtn.disabled;
      cancelBtn.disabled = true;
      
      try {
        if (hasUnpostedComment()) {
          if (!await showConfirm('You have an unposted comment. Are you sure you want to cancel?', 'Confirm Action')) {
            // User cancelled the cancellation, re-enable button
            cancelBtn.disabled = wasCancelDisabled;
            isCancelling = false;
            return;
          }
        }
        if (hasUnsavedChanges || checklistOrderChanged) {
          if (await showConfirm('You have unsaved changes. Are you sure you want to cancel?', 'Confirm Cancellation')) {
            modal.remove();
          } else {
            // User cancelled the cancellation, re-enable button
            cancelBtn.disabled = wasCancelDisabled;
            isCancelling = false;
          }
        } else {
          modal.remove();
        }
      } catch (err) {
        // Re-enable button on error
        cancelBtn.disabled = wasCancelDisabled;
        isCancelling = false;
        console.error('Error during cancel:', err);
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
            // Show saving state
            input.disabled = true;
            
            const success = await this.updateChecklistItem(itemId, { name: newName });
            
            if (success) {
              const newNameSpan = document.createElement('span');
              newNameSpan.className = 'checklist-item-name';
              newNameSpan.innerHTML = linkifyUrls(this.escapeHtml(newName));
              input.replaceWith(newNameSpan);
              hasUnsavedChanges = false; // This action was already saved
            } else {
              // Error toast already shown, restore input and re-enable
              input.disabled = false;
              input.focus();
              input.select();
              return; // Stay in edit mode to allow retry
            }
          } else if (newName) {
            // No change, just restore
            const newNameSpan = document.createElement('span');
            newNameSpan.className = 'checklist-item-name';
            newNameSpan.innerHTML = linkifyUrls(this.escapeHtml(currentName));
            input.replaceWith(newNameSpan);
          } else {
            // Empty name, restore original
            const newNameSpan = document.createElement('span');
            newNameSpan.className = 'checklist-item-name';
            newNameSpan.innerHTML = linkifyUrls(this.escapeHtml(currentName));
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
    const createDeleteHandler = (btn) => {
      return async (e) => {
        if (await showConfirm('Delete this checklist item?', 'Confirm Deletion')) {
          const itemId = parseInt(e.target.getAttribute('data-item-id'));
          const itemElement = e.target.closest('.checklist-item');
          
          // Store item data for potential restoration
          const itemData = {
            id: itemId,
            html: itemElement.outerHTML,
            parentNode: itemElement.parentNode,
            nextSibling: itemElement.nextSibling
          };
          
          // Remove item from DOM
          itemElement.remove();
          updateEditModalSummary();
          
          // Attempt to delete from server
          const success = await this.deleteChecklistItem(itemId);
          
          if (success) {
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
          } else {
            // Restore item to DOM on failure
            if (itemData.nextSibling) {
              itemData.parentNode.insertBefore(document.createRange().createContextualFragment(itemData.html).firstChild, itemData.nextSibling);
            } else {
              itemData.parentNode.appendChild(document.createRange().createContextualFragment(itemData.html).firstChild);
            }
            
            // Reattach event listeners to restored element
            const restoredElement = itemData.parentNode.querySelector(`[data-item-id="${itemId}"]`);
            if (restoredElement) {
              const deleteBtn = restoredElement.querySelector('.checklist-delete-btn');
              const editBtn = restoredElement.querySelector('.checklist-edit-btn');
              const checkbox = restoredElement.querySelector('.checklist-checkbox');
              
              // Re-attach delete handler using the factory function
              if (deleteBtn) {
                deleteBtn.addEventListener('click', createDeleteHandler(deleteBtn));
              }
              
              // Re-attach edit handler (simplified - full handler is complex, just show it's restorable)
              if (editBtn) {
                editBtn.addEventListener('click', async (e) => {
                  this.showErrorToast('Please refresh the modal to edit this item after a failed delete.');
                });
              }
              
              // Re-attach checkbox handler
              if (checkbox) {
                checkbox.addEventListener('change', (e) => {
                  const itemId = parseInt(e.target.getAttribute('data-item-id'));
                  const checked = e.target.checked;
                  checklistCheckboxChanges.set(itemId, checked);
                  hasUnsavedChanges = true;
                  updateEditModalSummary();
                });
              }
            }
            
            updateEditModalSummary();
          }
        }
      };
    };
    
    // Attach delete handlers to all delete buttons
    document.querySelectorAll('.checklist-delete-btn').forEach(btn => {
      btn.addEventListener('click', createDeleteHandler(btn));
    });

    // Handle post comment button (only if comments section exists)
    const postCommentBtn = document.getElementById('post-comment-btn');
    const newCommentInput = document.getElementById('new-comment-input');
    const MAX_COMMENT_LENGTH = 50000;
    
    if (postCommentBtn && newCommentInput) {
      postCommentBtn.addEventListener('click', async () => {
        const commentText = newCommentInput.value.trim();
        if (!commentText) return;
        
        // Validate comment length on client side
        if (commentText.length > MAX_COMMENT_LENGTH) {
          await showAlert(`Comment is too long. Maximum length is ${MAX_COMMENT_LENGTH.toLocaleString()} characters. Your comment is ${commentText.length.toLocaleString()} characters.`, 'Invalid Input');
          return;
        }
        
        // Show posting state
        postCommentBtn.disabled = true;
        postCommentBtn.textContent = 'Posting...';
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        try {
          const response = await fetch(`/api/cards/${cardId}/comments`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ comment: commentText }),
            signal: controller.signal
          });
          
          clearTimeout(timeoutId);
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
            
            // Clear input and reset button
            newCommentInput.value = '';
            postCommentBtn.disabled = false;
            postCommentBtn.textContent = 'Post Comment';
          } else {
            this.showErrorToast(`Failed to post comment: ${data.message}`);
            postCommentBtn.disabled = false;
            postCommentBtn.textContent = 'Post Comment';
          }
        } catch (err) {
          clearTimeout(timeoutId);
          console.error('Error posting comment:', err);
          
          if (err.name === 'AbortError') {
            this.showErrorToast('Post comment timed out (5s). Please check your connection.');
          } else {
            this.showErrorToast(`Error posting comment: ${err.message}`);
          }
          
          postCommentBtn.disabled = false;
          postCommentBtn.textContent = 'Post Comment';
        }
      });
    }
    
    // Handle delete comment buttons (only if comments section exists)
    document.querySelectorAll('.comment-delete-btn').forEach(btn => {
      btn.addEventListener('click', () => this.deleteCommentHandler(btn, cardId));
    });
    
    // Handle read more buttons (only if comments section exists)
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
        if (!await showConfirm('You have an unposted comment. Are you sure you want to save without posting it?', 'Confirm Action')) {
          return;
        }
      }
      
      const title = titleInput.value.trim();
      const description = document.getElementById('edit-card-description').value.trim();
      // Save button is in modal header, not in form
      const saveBtn = modal.querySelector('button[type="submit"]');
      
      if (title) {
        // Validate that template cards have a schedule
        if (isTemplate && !cardData.schedule) {
          const createSchedule = await showConfirm(
            'This is a template card without a schedule. Template cards need a schedule to automatically create task cards.\n\nWould you like to create a schedule for this template now?',
            'Create Schedule?'
          );
          
          if (createSchedule) {
            // Save changes first, then open schedule modal
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            
            const success = await this.updateCard(cardId, title, description);
            
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
            
            if (!success) {
              // Error toast already shown by updateCard
              return; // Stay in modal to allow retry
            }
            
            modal.remove();
            
            // Open schedule modal for this template
            try {
              this.openScheduleModal(cardData.id);
            } catch (err) {
              await showAlert('Failed to open the schedule modal. Please try again.\n\nError: ' + (err && err.message ? err.message : err), 'Error');
            }
            return;
          } else {
            // User chose not to create a schedule, ask if they still want to save
            const saveAnyway = await showConfirm('Save template without a schedule? (You can add a schedule later using the Edit Schedule button)', 'Confirm Action');
            if (!saveAnyway) {
              return; // Don't save, stay in modal
            }
          }
        }
        
        // Show saving state
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        
        let allSuccessful = true;
        
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
        const cardUpdateSuccess = await this.updateCard(cardId, title, description);
        if (!cardUpdateSuccess) {
          allSuccessful = false;
        }
        
        // 2. Save checkbox changes for existing items
        // PERF: Sequential updates - could be batched
        for (const [itemId, checked] of checklistCheckboxChanges.entries()) {
          const success = await this.updateChecklistItem(itemId, { checked });
          if (!success) {
            allSuccessful = false;
            // Rollback checkbox in UI
            const checkbox = modal.querySelector(`.checklist-checkbox[data-item-id="${itemId}"]`);
            if (checkbox) {
              checkbox.checked = !checked;
            }
          }
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
              const success = await this.createChecklistItem(cardId, pendingItem.name, i, pendingItem.checked);
              if (!success) {
                allSuccessful = false;
                // Mark the item as failed (keep it in UI so user can retry)
                el.classList.add('update-failed');
              }
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
              const success = await this.updateChecklistItem(parseInt(itemId), { order: i });
              if (!success) {
                allSuccessful = false;
              }
            }
          }
        }
        
        // Re-enable save button
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
        
        // Reload board if card update succeeded, even if checklist operations failed
        // This ensures the card title/description changes are visible
        if (cardUpdateSuccess || allSuccessful) {
          await this.loadBoard();
        }
        
        if (allSuccessful) {
          hasUnsavedChanges = false;
          checklistOrderChanged = false;
          checklistCheckboxChanges.clear();
          modal.remove();
        } else {
          // Some operations failed - stay in modal for retry
          // Clear the checkbox changes that succeeded so they won't be retried
          for (const [itemId, checked] of checklistCheckboxChanges.entries()) {
            const checkbox = modal.querySelector(`.checklist-checkbox[data-item-id="${itemId}"]`);
            if (checkbox && checkbox.checked === checked) {
              // This one succeeded, remove from pending changes
              checklistCheckboxChanges.delete(itemId);
            }
          }
          
          // Show appropriate message based on what succeeded
          if (cardUpdateSuccess) {
            this.showErrorToast('Card updated, but some checklist changes failed. Please review and try again.');
          } else {
            this.showErrorToast('Failed to save changes. Please try again.');
          }
        }
      }
    });

    // Close modal on background click with warning (ignore text selection drags)
    setupModalBackgroundClose(modal, handleCancel);
  }

  async getCardData(cardId) {
    // Fetch single card data from dedicated endpoint
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      const data = await response.json();
      
      if (data.success) {
        return data.card;
      } else {
        console.error('Failed to get card data:', data.message);
        this.showErrorToast(`Failed to load card: ${data.message}`);
        return null;
      }
    } catch (err) {
      clearTimeout(timeoutId);
      console.error('Error getting card data:', err.message);
      
      if (err.name === 'AbortError') {
        this.showErrorToast('Load card timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error loading card: ${err.message}`);
      }
      return null;
    }
  }

  async createChecklistItem(cardId, name, order = null, checked = false) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
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
        body: JSON.stringify(body),
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (!data.success) {
        this.showErrorToast(`Failed to create checklist item: ${data.message}`);
        return false;
      }
      return true;
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        this.showErrorToast('Create checklist item timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error creating checklist item: ${err.message}`);
      }
      return false;
    }
  }

  async updateChecklistItem(itemId, updates) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/checklist-items/${itemId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates),
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (!data.success) {
        this.showErrorToast(`Failed to update checklist item: ${data.message}`);
        return false;
      }
      return true;
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        this.showErrorToast('Update checklist item timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error updating checklist item: ${err.message}`);
      }
      return false;
    }
  }

  async deleteChecklistItem(itemId) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/checklist-items/${itemId}`, {
        method: 'DELETE',
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (!data.success) {
        this.showErrorToast(`Failed to delete checklist item: ${data.message}`);
        return false;
      }
      return true;
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        this.showErrorToast('Delete checklist item timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error deleting checklist item: ${err.message}`);
      }
      return false;
    }
  }

  async updateCard(cardId, title, description) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ title, description }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (data.success) {
        // The server broadcasts card_updated to other clients via WebSocket.
        // For the originating client, we return true immediately since the API
        // request itself confirms the update succeeded. The client should reload
        // the board if needed.
        return true;
      } else {
        this.showErrorToast(`Failed to update card: ${data.message}`);
        return false;
      }
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        this.showErrorToast('Update card timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error updating card: ${err.message}`);
      }
      return false;
    }
  }

  async deleteCard(cardId, cardElement = null) {
    if (!await showConfirm('Are you sure you want to delete this card?', 'Confirm Deletion')) {
      return;
    }

    // Show loading state
    if (cardElement) {
      cardElement.classList.add('updating');
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`/api/cards/${cardId}`, {
        method: 'DELETE',
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (data.success) {
        // The server broadcasts card_deleted to other clients via WebSocket.
        // For the originating client, we reload the board immediately below
        // to ensure instant UI update and remove the card element.
        
        // Reload board to reflect deletion
        await this.loadBoard();
      } else {
        if (cardElement) {
          cardElement.classList.remove('updating');
        }
        this.showErrorToast(`Failed to delete card: ${data.message}`);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      if (cardElement) {
        cardElement.classList.remove('updating');
      }
      
      if (err.name === 'AbortError') {
        this.showErrorToast('Delete card timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error deleting card: ${err.message}`);
      }
    }
  }

  async archiveCard(cardId, cardElement = null) {
    // Show loading state after delay to avoid flashing on fast connections
    const loadingTimeout = setTimeout(() => {
      if (cardElement) {
        cardElement.classList.add('updating');
      }
    }, 500);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`/api/cards/${cardId}/archive`, {
        method: 'PATCH',
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      const data = await response.json();

      if (data.success) {
        clearTimeout(loadingTimeout);
        // Reload board to reflect archiving
        await this.loadBoard();
      } else {
        clearTimeout(loadingTimeout);
        if (cardElement) {
          cardElement.classList.remove('updating');
        }
        this.showErrorToast(`Failed to archive card: ${data.message}`);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      if (cardElement) {
        cardElement.classList.remove('updating');
      }
      
      if (err.name === 'AbortError') {
        this.showErrorToast('Archive card timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error archiving card: ${err.message}`);
      }
    }
  }

  async unarchiveCard(cardId, cardElement = null) {
    // Show loading state after delay to avoid flashing on fast connections
    const loadingTimeout = setTimeout(() => {
      if (cardElement) {
        cardElement.classList.add('updating');
      }
    }, 500);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`/api/cards/${cardId}/unarchive`, {
        method: 'PATCH',
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      const data = await response.json();

      if (data.success) {
        // Reload board to reflect unarchiving
        await this.loadBoard();
      } else {
        if (cardElement) {
          cardElement.classList.remove('updating');
        }
        this.showErrorToast(`Failed to unarchive card: ${data.message}`);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      if (cardElement) {
        cardElement.classList.remove('updating');
      }
      
      if (err.name === 'AbortError') {
        this.showErrorToast('Unarchive card timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error unarchiving card: ${err.message}`);
      }
    }
  }

  async updateCardDoneStatus(cardId, done, cardElement = null) {
    // Show loading state after delay to avoid flashing on fast connections
    const loadingTimeout = setTimeout(() => {
      if (cardElement) {
        cardElement.classList.add('updating');
      }
    }, 500);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`/api/cards/${cardId}/done`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ done: done }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      const data = await response.json();

      if (response.ok && data.success) {
        // Show success message
        const statusText = done ? 'Card marked as done' : 'Card marked as not done';
        this.showSuccessToast(statusText, 2000);
        
        // If in board_task_category mode, reload the board so the card appears/disappears based on done status
        if (this.workingStyle === 'board_task_category') {
          await this.loadBoard();
        } else {
          // For kanban mode, just update the button
          if (cardElement) {
            cardElement.setAttribute('data-done', done);
            
            // Update the button appearance
            const btn = cardElement.querySelector('.card-done-btn');
            if (btn) {
              btn.textContent = done ? '✓' : '○';
              btn.setAttribute('title', done ? 'Mark as not done' : 'Mark as done');
            }
            
            cardElement.classList.remove('updating');
          }
        }
      } else {
        if (cardElement) {
          cardElement.classList.remove('updating');
        }
        const errorMsg = data.message || `Server error: ${response.status}`;
        this.showErrorToast(`Failed to update card status: ${errorMsg}`);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      if (cardElement) {
        cardElement.classList.remove('updating');
      }
      
      if (err.name === 'AbortError') {
        this.showErrorToast('Update card status timed out (5s). Please check your connection.');
      } else {
        this.showErrorToast(`Error updating card status: ${err.message}`);
      }
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

  showBoardLoading() {
    // Add or show loading overlay
    let overlay = this.container.querySelector('.board-loading-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'board-loading-overlay';
      overlay.innerHTML = `
        <div class="board-loading-content">
          <div class="board-loading-spinner">⏳</div>
          <div class="board-loading-text">Loading...</div>
        </div>
      `;
      this.container.appendChild(overlay);
    }
    overlay.style.display = 'flex';
  }

  hideBoardLoading() {
    const overlay = this.container.querySelector('.board-loading-overlay');
    if (overlay) {
      overlay.style.display = 'none';
    }
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
    return date.toLocaleDateString('en-GB', dateOptions) + ' ' + formatTimeSync(date);
  }

  generateCommentHtml(comment) {
    const isLongComment = comment.comment.split('\n').length > 10 || comment.comment.length > 500;
    return `
      <div class="comment-item" data-comment-id="${comment.id}">
        <div class="comment-header">
          <span class="comment-date" data-tooltip="${formatTooltipDateTime(comment.created_at)}" aria-label="Created on ${formatTooltipDateTime(comment.created_at)}" tabindex="0">${this.formatCommentDate(comment.created_at)}</span>
          <button type="button" class="comment-delete-btn" data-comment-id="${comment.id}" title="Delete" aria-label="Delete comment">🗑</button>
        </div>
        <div class="comment-text ${isLongComment ? 'collapsed' : ''}" id="comment-text-${comment.id}" data-comment-id="${comment.id}">${linkifyUrls(this.escapeHtml(comment.comment))}</div>
        ${isLongComment ? `<button type="button" class="comment-read-more" data-comment-id="${comment.id}" aria-expanded="false" aria-controls="comment-text-${comment.id}" aria-label="Expand comment">Read more...</button>` : ''}
      </div>
    `;
  }

  async deleteCommentHandler(deleteBtn, cardId) {
    const commentId = parseInt(deleteBtn.getAttribute('data-comment-id'));
    
    if (!await showConfirm('Are you sure you want to delete this comment?', 'Confirm Deletion')) {
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
        await showAlert('Failed to delete comment: ' + data.message, 'Error');
      }
    } catch (err) {
      console.error('Error deleting comment:', err);
      await showAlert('Error deleting comment', 'Error');
    }
  }
}

// Initialize board manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.boardManager = new BoardManager();
  window.boardManager.init();
});
