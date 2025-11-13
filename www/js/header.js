// Header component functionality
class Header {
  constructor() {
    this.statusIcon = null;
    this.statusText = null;
    this.versionInfo = null;
  }

  // Load the header HTML component
  async load() {
    const response = await fetch('/components/header.html');
    const html = await response.text();
    document.body.insertAdjacentHTML('afterbegin', html);
    
    // Get references to status elements after HTML is inserted
    this.statusIcon = document.getElementById('status-icon');
    this.statusText = document.getElementById('status-text');
    this.versionInfo = document.getElementById('version-info');
    
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
      const boardText = count === 1 ? 'board' : 'boards';
      this.statusText.textContent = `DB connected: ${count} ${boardText}`;
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
      const [testResponse, versionResponse] = await Promise.all([
        fetch('/api/test'),
        fetch('/api/version')
      ]);
      
      const testData = await testResponse.json();
      const versionData = await versionResponse.json();
      
      if (testData.success) {
        this.updateStatus('success', 'Connected', testData.boards_count);
      } else {
        this.updateStatus('error', testData.message);
      }
      
      // Update version display
      if (versionData.success) {
        this.updateVersion(versionData.app_version, versionData.db_version);
      }
    } catch (err) {
      this.updateStatus('error', err.message);
    }
  }

  // Update version display
  updateVersion(appVersion, dbVersion) {
    const versionElement = this.versionInfo || document.getElementById('version-info');
    if (versionElement) {
      versionElement.textContent = `v${appVersion} | DB:${dbVersion}`;
    }
  }
}

// Initialize header on page load
const header = new Header();
window.header = header; // Make it globally accessible
document.addEventListener('DOMContentLoaded', () => {
  header.load();
});
