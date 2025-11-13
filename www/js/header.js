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
    
    // Add click handler to db-status
    const dbStatus = document.querySelector('.db-status');
    if (dbStatus) {
      dbStatus.addEventListener('click', () => {
        window.location.href = '/system-info.html';
      });
    }
    
    // Load boards dropdown
    this.loadBoardsDropdown();
    
    // Check database status
    this.checkDatabaseStatus();
  }

  // Set the board name in the header
  setBoardName(boardName) {
    const navBoardName = document.getElementById('nav-board-name');
    if (navBoardName) {
      if (boardName) {
        navBoardName.textContent = boardName;
        document.title = `AFT - ${boardName}`;
      } else {
        navBoardName.textContent = '';
        document.title = 'AFT';
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

  // Load boards for dropdown menu
  async loadBoardsDropdown() {
    try {
      const response = await fetch('/api/boards');
      const data = await response.json();
      
      const dropdown = document.getElementById('boards-dropdown-menu');
      if (!dropdown) return;
      
      if (data.success && data.boards && data.boards.length > 0) {
        // Clear loading message
        dropdown.innerHTML = '';
        
        // Add each board as a link
        data.boards.forEach(board => {
          const link = document.createElement('a');
          link.href = `/board.html?id=${board.id}`;
          link.className = 'boards-dropdown-item';
          link.textContent = board.name;
          dropdown.appendChild(link);
        });
      } else {
        dropdown.innerHTML = '<div class="boards-dropdown-empty">No boards yet</div>';
      }
    } catch (error) {
      console.error('Error loading boards dropdown:', error);
      const dropdown = document.getElementById('boards-dropdown-menu');
      if (dropdown) {
        dropdown.innerHTML = '<div class="boards-dropdown-empty">Error loading boards</div>';
      }
    }
  }
}

// Initialize header on page load
const header = new Header();
window.header = header; // Make it globally accessible
document.addEventListener('DOMContentLoaded', () => {
  header.load();
});
