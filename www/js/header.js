// Header component functionality
class Header {
  constructor() {
    this.statusIcon = null;
    this.statusText = null;
  }

  // Load the header HTML component
  async load() {
    const response = await fetch('/components/header.html');
    const html = await response.text();
    document.body.insertAdjacentHTML('afterbegin', html);
    
    // Get references to status elements
    this.statusIcon = document.getElementById('status-icon');
    this.statusText = document.getElementById('status-text');
    
    // Check database status
    this.checkDatabaseStatus();
  }

  // Set the board name in the header
  setBoardName(boardName) {
    const headerLeft = document.querySelector('.header-left h1');
    if (headerLeft) {
      if (boardName) {
        headerLeft.innerHTML = `AFT <span class="board-name-separator">-</span> <span class="board-name">${this.escapeHtml(boardName)}</span>`;
        document.title = `AFT - ${boardName}`;
      } else {
        headerLeft.textContent = 'AFT';
      }
    }
  }

  // Escape HTML to prevent XSS
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Update the database status indicator
  updateStatus(status, message, count = null) {
    if (!this.statusIcon || !this.statusText) return;

    this.statusIcon.className = `status-icon ${status}`;
    
    if (status === 'success' && count !== null) {
      this.statusText.textContent = `DB connected: ${count} boards`;
    } else if (status === 'error') {
      this.statusText.textContent = 'DB Error';
      this.statusText.title = message; // Show full error on hover
    } else {
      this.statusText.textContent = message;
    }
  }

  // Check database connection status
  async checkDatabaseStatus() {
    try {
      const response = await fetch('/api/test');
      const data = await response.json();
      
      if (data.success) {
        this.updateStatus('success', 'Connected', data.boards_count);
      } else {
        this.updateStatus('error', data.message);
      }
    } catch (err) {
      this.updateStatus('error', err.message);
    }
  }
}

// Initialize header on page load
const header = new Header();
window.header = header; // Make it globally accessible
document.addEventListener('DOMContentLoaded', () => {
  header.load();
});
