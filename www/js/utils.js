/**
 * Shared utility functions for the AFT application
 */

/**
 * Format a date/timestamp for display in tooltips.
 * Returns a consistent format across the application: "4 Dec 2025 14:30"
 * 
 * @param {Date|string} date - Date object or ISO date string
 * @returns {string} Formatted date string
 */
function formatTooltipDateTime(date) {
  const dateObj = date instanceof Date ? date : new Date(date);
  return `${dateObj.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} ${dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
}

/**
 * Modal Dialog System
 * Replaces browser alert(), confirm(), and prompt() with styled modals
 */
class ModalDialog {
  constructor() {
    this.modal = null;
    this.title = null;
    this.message = null;
    this.input = null;
    this.cancelBtn = null;
    this.confirmBtn = null;
    this.isOpen = false;
    this.currentCleanup = null;
    this.isInitialized = false;
  }

  ensureInitialized() {
    // Lazy initialization - only create modal when first needed
    if (this.isInitialized && this.modal) {
      return true;
    }

    // Check if DOM is ready
    if (typeof document === 'undefined' || !document.body) {
      console.error('ModalDialog: Document body not available yet');
      return false;
    }

    // Create modal HTML structure
    const modalHTML = `
      <div id="appModal" class="modal-app" role="dialog" aria-modal="true" aria-labelledby="appModalTitle" aria-describedby="appModalMessage">
        <div class="modal-content">
          <div class="modal-header">
            <h2 id="appModalTitle"></h2>
          </div>
          <div class="modal-body">
            <p id="appModalMessage"></p>
            <input type="text" id="appModalInput" style="display: none;" class="modal-input">
          </div>
          <div class="modal-actions">
            <button class="btn btn-secondary" id="appModalCancelBtn" style="display: none;">Cancel</button>
            <button class="btn btn-primary" id="appModalConfirmBtn">OK</button>
          </div>
        </div>
      </div>
    `;

    // Add modal to body if not already present
    if (!document.getElementById('appModal')) {
      document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    // Get references to modal elements
    this.modal = document.getElementById('appModal');
    this.title = document.getElementById('appModalTitle');
    this.message = document.getElementById('appModalMessage');
    this.input = document.getElementById('appModalInput');
    this.cancelBtn = document.getElementById('appModalCancelBtn');
    this.confirmBtn = document.getElementById('appModalConfirmBtn');

    // Verify all elements were found
    if (!this.modal || !this.title || !this.message || !this.input || !this.cancelBtn || !this.confirmBtn) {
      console.error('ModalDialog: Failed to initialize modal elements');
      return false;
    }

    this.isInitialized = true;
    return true;
  }

  show(title, message, options = {}) {
    return new Promise((resolve) => {
      // Ensure modal is initialized
      if (!this.ensureInitialized()) {
        console.error('ModalDialog: Cannot show modal - initialization failed');
        // Fallback to browser alert/confirm
        if (options.showInput) {
          resolve(prompt(message, options.defaultValue || ''));
        } else if (options.showCancel) {
          resolve(confirm(message));
        } else {
          alert(message);
          resolve(true);
        }
        return;
      }

      // If modal is already open, wait for it to close first
      if (this.isOpen) {
        // Clean up previous modal immediately
        if (this.currentCleanup) {
          this.currentCleanup();
        }
        // Remove show class and wait for animation to complete
        this.modal.classList.remove('show');
        
        // Wait for CSS animation to complete (300ms from modalSlideIn animation)
        // Adding small buffer for safety
        setTimeout(() => {
          this.isOpen = false;
          this.currentCleanup = null;
          // Now show the new modal
          this.showModalContent(title, message, options, resolve);
        }, 350);
        return;
      }

      this.showModalContent(title, message, options, resolve);
    });
  }

  showModalContent(title, message, options, resolve) {
      this.isOpen = true;
      this.title.textContent = title;
      
      // Handle multi-line messages by converting \n to <br> and preserving whitespace
      // Clear existing content first
      this.message.innerHTML = '';
      
      // Split message by newlines and create text nodes with breaks
      const lines = message.split('\n');
      lines.forEach((line, index) => {
        this.message.appendChild(document.createTextNode(line));
        if (index < lines.length - 1) {
          this.message.appendChild(document.createElement('br'));
        }
      });
      
      // Handle input field for prompt
      if (options.showInput) {
        this.input.style.display = 'block';
        this.input.value = options.defaultValue || '';
      } else {
        this.input.style.display = 'none';
      }

      // Handle cancel button for confirm/prompt
      if (options.showCancel) {
        this.cancelBtn.style.display = 'inline-block';
        this.cancelBtn.textContent = options.cancelText || 'Cancel';
      } else {
        this.cancelBtn.style.display = 'none';
      }

      // Set confirm button text
      this.confirmBtn.textContent = options.confirmText || 'OK';

      // Store currently focused element and blur it to prevent scroll on modal close
      const previouslyFocused = document.activeElement;
      if (previouslyFocused && previouslyFocused !== document.body) {
        previouslyFocused.blur();
      }

      // Show modal
      this.modal.classList.add('show');

      // Handle confirm
      const handleConfirm = () => {
        cleanup();
        this.modal.classList.remove('show');
        this.isOpen = false;
        this.currentCleanup = null;
        
        // Ensure no element receives focus that could cause scrolling
        if (document.activeElement && document.activeElement !== document.body) {
          document.activeElement.blur();
        }
        
        if (options.showInput) {
          resolve(this.input.value);
        } else {
          resolve(true);
        }
      };

      // Handle cancel
      const handleCancel = () => {
        cleanup();
        this.modal.classList.remove('show');
        this.isOpen = false;
        this.currentCleanup = null;
        
        // Ensure no element receives focus that could cause scrolling
        if (document.activeElement && document.activeElement !== document.body) {
          document.activeElement.blur();
        }
        
        if (options.showInput) {
          resolve(null);
        } else {
          resolve(false);
        }
      };

      // Handle escape/Enter key
      const handleEscape = (e) => {
        if (e.key === 'Escape') {
          handleCancel();
        } else if (e.key === 'Enter') {
          // Only auto-confirm on Enter for alert and prompt modals
          if (!options.showCancel || options.showInput) {
            e.preventDefault();
            handleConfirm();
          }
        }
      };

      // Handle backdrop click (click outside modal content)
      const handleBackdropClick = (e) => {
        // Only close if clicking directly on the backdrop, not on modal content
        if (e.target === this.modal) {
          handleCancel();
        }
      };

      // Cleanup function
      const cleanup = () => {
        this.confirmBtn.removeEventListener('click', handleConfirm);
        this.cancelBtn.removeEventListener('click', handleCancel);
        document.removeEventListener('keydown', handleEscape);
        this.modal.removeEventListener('click', handleBackdropClick);
      };

      // Store cleanup function for potential early cleanup
      this.currentCleanup = cleanup;

      // Add event listeners
      this.confirmBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleConfirm();
      });
      this.cancelBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleCancel();
      });
      document.addEventListener('keydown', handleEscape);
      this.modal.addEventListener('click', handleBackdropClick);

      // Focus appropriate element after ensuring DOM is ready
      // Using requestAnimationFrame for more reliable focus timing
      // preventScroll prevents the browser from scrolling to the focused element
      requestAnimationFrame(() => {
        if (options.showInput) {
          this.input.focus({ preventScroll: true });
        } else {
          this.confirmBtn.focus({ preventScroll: true });
        }
      });
  }

  alert(message, title = 'Alert') {
    return this.show(title, message, { showCancel: false });
  }

  confirm(message, title = 'Confirm') {
    return this.show(title, message, { showCancel: true, confirmText: 'OK', cancelText: 'Cancel' });
  }

  prompt(message, defaultValue = '', title = 'Input') {
    return this.show(title, message, { showInput: true, showCancel: true, defaultValue });
  }
}

// Create global modal instance
const modalDialog = new ModalDialog();

/**
 * Display a styled alert modal dialog (replacement for browser alert()).
 * Supports multi-line messages using \n characters.
 * 
 * @param {string} message - The message to display. Use \n for line breaks.
 * @param {string} [title='Alert'] - The title of the alert dialog.
 * @returns {Promise<boolean>} Promise that resolves to true when dismissed.
 * 
 * @example
 * await showAlert('Operation completed successfully!');
 * 
 * @example
 * await showAlert('Error details:\n\nFailed to save data.\nPlease try again.', 'Error');
 */
function showAlert(message, title = 'Alert') {
  return modalDialog.alert(message, title);
}

/**
 * Display a styled confirmation modal dialog (replacement for browser confirm()).
 * Supports multi-line messages using \n characters.
 * 
 * @param {string} message - The message to display. Use \n for line breaks.
 * @param {string} [title='Confirm'] - The title of the confirmation dialog.
 * @returns {Promise<boolean>} Promise that resolves to true if OK is clicked, false if Cancel is clicked or dialog is dismissed.
 * 
 * @example
 * const confirmed = await showConfirm('Are you sure you want to delete this item?');
 * if (confirmed) {
 *   // Proceed with deletion
 * }
 * 
 * @example
 * const result = await showConfirm('This action cannot be undone.\n\nAre you sure?', 'Warning');
 */
function showConfirm(message, title = 'Confirm') {
  return modalDialog.confirm(message, title);
}

/**
 * Display a styled prompt modal dialog (replacement for browser prompt()).
 * Allows user to input text with an optional default value.
 * 
 * @param {string} message - The message to display.
 * @param {string} [defaultValue=''] - The default value for the input field.
 * @param {string} [title='Input'] - The title of the prompt dialog.
 * @returns {Promise<string|null>} Promise that resolves to the input value if OK is clicked, null if Cancel is clicked or dialog is dismissed.
 * 
 * @example
 * const name = await showPrompt('Enter your name:', 'John Doe');
 * if (name !== null) {
 *   console.log('User entered:', name);
 * }
 * 
 * @example
 * const boardName = await showPrompt('Enter board name:', '', 'Create Board');
 */
function showPrompt(message, defaultValue = '', title = 'Input') {
  return modalDialog.prompt(message, defaultValue, title);
}
