# Frontend Error Handling Guidelines

## Overview

This document defines best practices for error handling in the frontend JavaScript code when making API calls. All frontend code must follow these patterns to ensure a consistent user experience when the database or API is unavailable.

## Core Principles

1. **Non-Blocking Feedback**: Use toast notifications for errors, not blocking `alert()` dialogs
2. **Timeout Protection**: All API calls must timeout after 5 seconds maximum
3. **Loading States**: Show visual feedback within 500ms of operation start
4. **Preserve User Work**: Keep modals open on failure, restore UI state, allow retry
5. **Graceful Degradation**: Disable features when database is disconnected

## Database Connection Monitoring

### Header Status Widget

The header component continuously monitors database connectivity:

```javascript
// In header.js constructor
this.dbConnected = false; // Track connection status

// Poll every 5 seconds
setInterval(() => {
  this.checkDatabaseStatus();
}, 5000);
```

### Status Check with Timeout

```javascript
async checkDatabaseStatus() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  
  try {
    const response = await fetch('/api/test', {
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    if (response.ok) {
      this.dbConnected = true;
      this.updateStatus('success', 'Database connected');
    } else {
      this.dbConnected = false;
      this.updateStatus('error', 'DB Error');
    }
  } catch (err) {
    clearTimeout(timeoutId);
    
    if (err.name === 'AbortError') {
      this.dbConnected = false;
      this.updateStatus('error', 'DB Timeout');
      this.showErrorToast('Database connection timed out');
    } else {
      this.dbConnected = false;
      this.updateStatus('error', 'DB Error');
    }
  }
}
```

### Block Operations When Disconnected

```javascript
// Check before opening modals
openAddCardModal(columnId) {
  // Block if database disconnected
  if (!window.header || !window.header.dbConnected) {
    this.showErrorToast('Cannot create card: Database not connected');
    return;
  }
  
  // Proceed with modal
  // ...
}
```

## API Call Pattern

### Standard API Call with Timeout

All fetch calls must use this pattern:

```javascript
async performAPIOperation(cardId, data) {
  // 1. Create AbortController for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  
  try {
    // 2. Make fetch request with signal
    const response = await fetch(`/api/cards/${cardId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data),
      signal: controller.signal
    });
    
    // 3. Clear timeout on response
    clearTimeout(timeoutId);
    
    // 4. Parse response safely
    const result = await this.parseResponse(response);
    
    // 5. Check success
    if (!result.success) {
      throw new Error(result.message || 'Operation failed');
    }
    
    // 6. Return result
    return result;
    
  } catch (err) {
    // 7. Always clear timeout
    clearTimeout(timeoutId);
    
    // 8. Handle abort (timeout) specifically
    if (err.name === 'AbortError') {
      console.error('API call timed out after 5 seconds');
      throw new Error('Request timed out. Check your connection.');
    }
    
    // 9. Re-throw other errors
    throw err;
  }
}
```

### Safe JSON Parsing

Use a helper to handle non-JSON error responses:

```javascript
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
```

## Visual Feedback

### Loading States

Show loading state after 500ms delay (avoids flashing on fast connections):

```javascript
async saveCard() {
  const saveButton = this.modal.querySelector('#save-card-btn');
  
  // Add loading state with delay
  const loadingTimeout = setTimeout(() => {
    saveButton.textContent = 'Saving...';
    saveButton.disabled = true;
  }, 500);
  
  try {
    const result = await this.performAPIOperation(cardId, data);
    
    // Clear loading timeout on success
    clearTimeout(loadingTimeout);
    
    // Close modal on success
    this.modal.remove();
    
  } catch (err) {
    // Clear loading state
    clearTimeout(loadingTimeout);
    saveButton.textContent = 'Save';
    saveButton.disabled = false;
    
    // Show error (modal stays open)
    this.showErrorToast(err.message);
  }
}
```

### Card Loading Overlay

For operations on cards (delete, archive):

```javascript
async deleteCard(cardId) {
  const cardElement = document.querySelector(`[data-card-id="${cardId}"]`);
  
  // Show loading overlay
  if (cardElement) {
    cardElement.style.position = 'relative';
    const overlay = document.createElement('div');
    overlay.className = 'card-loading-overlay';
    overlay.innerHTML = '<div class="spinner"></div>';
    cardElement.appendChild(overlay);
  }
  
  try {
    await this.performAPIOperation(cardId);
    
    // Remove card on success
    cardElement.remove();
    
  } catch (err) {
    // Remove overlay, keep card
    const overlay = cardElement.querySelector('.card-loading-overlay');
    if (overlay) overlay.remove();
    
    this.showErrorToast(err.message);
  }
}
```

### Full-Screen Loading

For view changes and board loads:

```javascript
showBoardLoading() {
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
```

## Error Notifications

### Non-Blocking Toast

All errors should use toast notifications:

```javascript
/**
 * Show a non-blocking error toast notification
 * @param {string} message - The error message to display
 * @param {number} duration - How long to show the toast in milliseconds (default 3000)
 */
showErrorToast(message, duration = 3000) {
  const toast = document.createElement('div');
  toast.className = 'error-toast';
  toast.textContent = message;
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
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease-in';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
```

### NEVER Use Blocking Alerts

❌ **Don't do this:**
```javascript
if (!result.success) {
  alert('Failed to save card!'); // Blocks UI, interrupts work
}
```

✅ **Do this instead:**
```javascript
if (!result.success) {
  this.showErrorToast('Failed to save card');
  // Modal stays open, user can retry
}
```

### Styled Modal Confirmations

For confirmation dialogs, use styled modals from `utils.js`:

```javascript
// From utils.js
async function showConfirm(title, message) {
  return new Promise((resolve) => {
    // Create styled modal with OK/Cancel buttons
    // Returns true/false based on user choice
  });
}

// Usage
const confirmed = await showConfirm(
  'Unsaved Changes',
  'You have unsaved changes. Discard them?'
);

if (confirmed) {
  this.modal.remove();
}
```

## State Preservation and Rollback

### Keep Modals Open on Failure

```javascript
async saveCard() {
  try {
    await this.performAPIOperation(cardId, data);
    
    // Only close modal on success
    this.modal.remove();
    
  } catch (err) {
    // Modal stays open - user can fix issues and retry
    this.showErrorToast(err.message);
    // Do NOT remove modal
  }
}
```

### Rollback UI Changes

For optimistic updates, restore state on failure:

```javascript
async toggleCheckbox(itemId, currentState) {
  const checkbox = document.querySelector(`#checkbox-${itemId}`);
  
  // Optimistic update
  checkbox.checked = !currentState;
  
  try {
    await this.updateChecklistItem(itemId, !currentState);
    // Success - keep new state
    
  } catch (err) {
    // Rollback to original state
    checkbox.checked = currentState;
    this.showErrorToast('Failed to update checkbox');
  }
}
```

### Restore Deleted Items

```javascript
async deleteItem(itemId) {
  const itemElement = document.querySelector(`#item-${itemId}`);
  
  // Store for restoration
  const itemData = {
    element: itemElement.cloneNode(true),
    parentContainer: itemElement.parentElement,
    nextSibling: itemElement.nextSibling
  };
  
  // Remove from DOM
  itemElement.remove();
  
  try {
    await this.performAPIOperation(itemId);
    // Success - item stays deleted
    
  } catch (err) {
    // Restore item to original position
    if (itemData.nextSibling) {
      itemData.parentContainer.insertBefore(itemData.element, itemData.nextSibling);
    } else {
      itemData.parentContainer.appendChild(itemData.element);
    }
    
    // Re-attach event listeners
    this.attachItemEventListeners(itemData.element);
    
    this.showErrorToast('Failed to delete item');
  }
}
```

### Preserve Form Data

```javascript
async postComment() {
  const textarea = this.modal.querySelector('#comment-text');
  const commentText = textarea.value.trim();
  const postButton = this.modal.querySelector('#post-comment-btn');
  
  // Show loading state
  postButton.textContent = 'Posting...';
  postButton.disabled = true;
  
  try {
    await this.performAPIOperation(cardId, { text: commentText });
    
    // Success - clear textarea
    textarea.value = '';
    
  } catch (err) {
    // Failure - preserve text, allow retry
    postButton.textContent = 'Post Comment';
    postButton.disabled = false;
    
    // Text remains in textarea - user doesn't lose their work
    this.showErrorToast('Failed to post comment');
  }
}
```

## Card Drag Special Case

Card drag operations have unique requirements:

### DOM-Only Restoration (No API Reload)

```javascript
async updateCardPosition(cardId, columnId, order, originalPosition) {
  try {
    await this.performAPIOperation(cardId, { column_id: columnId, order });
    
    // Success - reload board to update counts
    await this.loadBoard();
    
  } catch (err) {
    // Restore card to original position (DOM only)
    this.restoreCardPosition(cardElement, originalPosition);
    
    // Show error toast
    this.showErrorToast('Failed to move card');
    
    // DO NOT reload board - restoration is DOM-only
    // This prevents unnecessary API calls and preserves performance
  }
}

restoreCardPosition(cardElement, originalPosition) {
  const { container, nextSibling, columnId, order } = originalPosition;
  
  // Move element back to original position
  if (nextSibling) {
    container.insertBefore(cardElement, nextSibling);
  } else {
    container.appendChild(cardElement);
  }
  
  // Restore data attributes
  cardElement.setAttribute('data-column-id', columnId);
  cardElement.setAttribute('data-order', order);
}
```

### Why DOM-Only?

1. **Performance**: Avoids unnecessary API call after failure
2. **Correctness**: Server state unchanged, so reload would show original position anyway
3. **User Experience**: Faster restoration without network delay

## Complex Modal Operations

### Track Multiple Operations

Edit card modal performs multiple operations - track them all:

```javascript
async saveAllChanges() {
  const operations = {
    cardUpdate: false,
    checkboxUpdates: [],
    newItems: [],
    reordering: false
  };
  
  let hasErrors = false;
  const errors = [];
  
  // 1. Update card details
  try {
    await this.updateCardDetails(cardId, data);
    operations.cardUpdate = true;
  } catch (err) {
    hasErrors = true;
    errors.push(`Card update: ${err.message}`);
  }
  
  // 2. Update checkboxes
  for (const change of checkboxChanges) {
    try {
      await this.updateChecklistItem(change.id, change.checked);
      operations.checkboxUpdates.push({ id: change.id, success: true });
    } catch (err) {
      hasErrors = true;
      errors.push(`Checkbox update: ${err.message}`);
      operations.checkboxUpdates.push({ id: change.id, success: false });
    }
  }
  
  // 3. Create new items
  for (const item of newItems) {
    try {
      await this.createChecklistItem(cardId, item.text);
      operations.newItems.push({ text: item.text, success: true });
    } catch (err) {
      hasErrors = true;
      errors.push(`Create item: ${err.message}`);
      operations.newItems.push({ text: item.text, success: false });
    }
  }
  
  if (hasErrors) {
    // Show all errors
    errors.forEach(error => this.showErrorToast(error));
    
    // Modal stays open for retry
    return false;
  }
  
  // All successful - close modal
  return true;
}
```

### Individual Operation Rollback

Each operation should handle its own rollback:

```javascript
async updateChecklistItem(itemId, checked) {
  const checkbox = document.querySelector(`#checkbox-${itemId}`);
  const originalState = checkbox.checked;
  
  // Optimistic update
  checkbox.checked = checked;
  checkbox.disabled = true;
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  
  try {
    const response = await fetch(`/api/checklist/${itemId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checked }),
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    const data = await this.parseResponse(response);
    
    if (!data.success) {
      // Rollback on failure
      checkbox.checked = originalState;
      checkbox.disabled = false;
      return false;
    }
    
    checkbox.disabled = false;
    return true;
    
  } catch (err) {
    clearTimeout(timeoutId);
    
    // Rollback on error
    checkbox.checked = originalState;
    checkbox.disabled = false;
    
    if (err.name === 'AbortError') {
      throw new Error('Checkbox update timed out');
    }
    
    throw err;
  }
}
```

## Testing Error Handling

### Manual Testing Checklist

Test with database stopped (`docker stop aft-db`):

- [ ] All API calls timeout after 5 seconds
- [ ] Toast notifications appear for all errors
- [ ] No blocking `alert()` dialogs
- [ ] Loading states show and clear properly
- [ ] Modals stay open on failure
- [ ] User input/work is preserved
- [ ] UI state rollback works correctly
- [ ] Database status widget shows "DB Error"
- [ ] Create/Edit modals are blocked when DB disconnected
- [ ] Card drag restores position without reload

### Network Testing

Use browser DevTools Network tab:

1. **Throttle to Slow 3G**: Verify loading states appear
2. **Offline Mode**: Verify immediate error handling
3. **Selective Blocking**: Block specific API endpoints to test partial failures

### Console Verification

Check browser console:

- No unhandled promise rejections
- Appropriate error logging with `console.error()`
- Timeout messages logged clearly

## CSS Animations

### Required Animations

```css
/* Toast slide in/out */
@keyframes slideIn {
  from {
    transform: translateX(400px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

@keyframes slideOut {
  from {
    transform: translateX(0);
    opacity: 1;
  }
  to {
    transform: translateX(400px);
    opacity: 0;
  }
}

/* Card states */
.card.updating {
  opacity: 0.6;
  pointer-events: none;
}

.card.update-success {
  animation: successFlash 1s ease-in-out;
}

.card.update-failed {
  animation: errorShake 0.5s ease-in-out;
}

@keyframes successFlash {
  0%, 100% { background-color: inherit; }
  50% { background-color: #d4edda; }
}

@keyframes errorShake {
  0%, 100% { transform: translateX(0); }
  10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
  20%, 40%, 60%, 80% { transform: translateX(5px); }
}

/* Loading overlay */
.board-loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

/* Pulse animation for loading spinners */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

## Anti-Patterns to Avoid

### ❌ Don't: Use alert() for errors
```javascript
if (!response.ok) {
  alert('Error saving card!'); // Blocks UI
}
```

### ✅ Do: Use toast notifications
```javascript
if (!response.ok) {
  this.showErrorToast('Error saving card');
}
```

### ❌ Don't: Close modal on any error
```javascript
try {
  await saveCard();
} catch (err) {
  console.error(err);
}
modal.remove(); // Loses user's work!
```

### ✅ Do: Keep modal open, allow retry
```javascript
try {
  await saveCard();
  modal.remove(); // Only close on success
} catch (err) {
  this.showErrorToast(err.message);
  // Modal stays open
}
```

### ❌ Don't: Reload page on error
```javascript
if (!result.success) {
  window.location.reload(); // Loses all state
}
```

### ✅ Do: Show error and allow retry
```javascript
if (!result.success) {
  this.showErrorToast(result.message);
  this.enableRetry();
}
```

### ❌ Don't: Forget timeout handling
```javascript
const response = await fetch('/api/cards'); // Can hang forever
```

### ✅ Do: Always use AbortController
```javascript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 5000);

try {
  const response = await fetch('/api/cards', { signal: controller.signal });
  clearTimeout(timeoutId);
} catch (err) {
  clearTimeout(timeoutId);
  if (err.name === 'AbortError') {
    this.showErrorToast('Request timed out');
  }
}
```

### ❌ Don't: Make unnecessary API calls on rollback
```javascript
catch (err) {
  await this.loadBoard(); // Unnecessary - server state unchanged
  this.restoreCardPosition();
}
```

### ✅ Do: DOM-only restoration when appropriate
```javascript
catch (err) {
  this.restoreCardPosition(); // DOM only
  // No API call needed - server was never updated
}
```

## Summary

All frontend API interactions must follow these patterns:

1. ✅ **5-second timeout** using AbortController
2. ✅ **Safe JSON parsing** with parseResponse helper
3. ✅ **Loading states** with 500ms delay
4. ✅ **Non-blocking toasts** for all errors
5. ✅ **Modal persistence** on failure
6. ✅ **State rollback** for optimistic updates
7. ✅ **Database awareness** via header status
8. ✅ **Graceful degradation** when disconnected
9. ✅ **DOM-only rollback** for card drag
10. ✅ **Preserve user work** in all failure scenarios

These patterns ensure a consistent, professional user experience even when the backend is unavailable or slow.
