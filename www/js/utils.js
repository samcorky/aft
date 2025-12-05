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
    this.createModal();
  }

  createModal() {
    // Create modal HTML structure
    const modalHTML = `
      <div id="appModal" class="modal" role="dialog" aria-modal="true" aria-labelledby="appModalTitle" aria-describedby="appModalMessage">
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

    this.modal = document.getElementById('appModal');
    this.title = document.getElementById('appModalTitle');
    this.message = document.getElementById('appModalMessage');
    this.input = document.getElementById('appModalInput');
    this.cancelBtn = document.getElementById('appModalCancelBtn');
    this.confirmBtn = document.getElementById('appModalConfirmBtn');
  }

  show(title, message, options = {}) {
    return new Promise((resolve) => {
      this.title.textContent = title;
      this.message.textContent = message;
      
      // Handle input field for prompt
      if (options.showInput) {
        this.input.style.display = 'block';
        this.input.value = options.defaultValue || '';
        this.input.focus();
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

      // Show modal
      this.modal.classList.add('show');

      // Handle confirm
      const handleConfirm = () => {
        cleanup();
        this.modal.classList.remove('show');
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
        if (options.showInput) {
          resolve(null);
        } else {
          resolve(false);
        }
      };

      // Handle escape key
      const handleEscape = (e) => {
        if (e.key === 'Escape') {
          handleCancel();
        }
      };

      // Handle enter key in input
      const handleEnter = (e) => {
        if (e.key === 'Enter' && options.showInput) {
          handleConfirm();
        }
      };

      // Cleanup function
      const cleanup = () => {
        this.confirmBtn.removeEventListener('click', handleConfirm);
        this.cancelBtn.removeEventListener('click', handleCancel);
        document.removeEventListener('keydown', handleEscape);
        this.input.removeEventListener('keydown', handleEnter);
      };

      // Add event listeners
      this.confirmBtn.addEventListener('click', handleConfirm);
      this.cancelBtn.addEventListener('click', handleCancel);
      document.addEventListener('keydown', handleEscape);
      this.input.addEventListener('keydown', handleEnter);

      // Focus appropriate element
      if (options.showInput) {
        setTimeout(() => this.input.focus(), 100);
      } else {
        setTimeout(() => this.confirmBtn.focus(), 100);
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

// Wrapper functions to match browser API
function showAlert(message, title) {
  return modalDialog.alert(message, title);
}

function showConfirm(message, title) {
  return modalDialog.confirm(message, title);
}

function showPrompt(message, defaultValue, title) {
  return modalDialog.prompt(message, defaultValue, title);
}
