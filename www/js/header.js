// Header component functionality
class Header {
  constructor() {
    this.statusIcon = null;
    this.statusText = null;
    this.versionInfo = null;
    this.currentView = 'task'; // Default view
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
    
    // Initialize notifications if the class exists
    if (typeof Notifications !== 'undefined') {
      window.notifications = new Notifications();
    }
    
    // Initialize views dropdown
    this.initializeViewsDropdown();
    
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

  // Show or hide the views dropdown
  showViewsDropdown(show) {
    const viewsDropdown = document.getElementById('views-dropdown');
    if (viewsDropdown) {
      viewsDropdown.style.display = show ? 'block' : 'none';
    }
  }

  // Initialize views dropdown functionality
  initializeViewsDropdown() {
    const dropdownBtn = document.getElementById('views-dropdown-btn');
    const dropdownMenu = document.getElementById('views-dropdown-menu');
    const dropdownItems = document.querySelectorAll('.views-dropdown-item');

    if (!dropdownBtn || !dropdownMenu) return;

    // Toggle dropdown on button click
    dropdownBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = dropdownMenu.classList.contains('show');
      dropdownMenu.classList.toggle('show', !isOpen);
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (!dropdownBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
        dropdownMenu.classList.remove('show');
      }
    });

    // Handle view selection
    dropdownItems.forEach(item => {
      item.addEventListener('click', (e) => {
        // Don't allow clicking the active view
        if (item.classList.contains('active')) {
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        const view = e.currentTarget.dataset.view;
        this.setView(view);
        dropdownMenu.classList.remove('show');
      });
    });
  }

  // Set the current view
  setView(view) {
    this.currentView = view;
    
    // Update dropdown label
    const label = document.getElementById('views-dropdown-label');
    if (label) {
      const viewNames = {
        'task': 'Task View',
        'scheduled': 'Scheduled View',
        'archived': 'Archived View'
      };
      label.textContent = viewNames[view] || 'Task View';
    }

    // Highlight active item
    document.querySelectorAll('.views-dropdown-item').forEach(item => {
      item.classList.toggle('active', item.dataset.view === view);
    });

    // Dispatch custom event for board.js to handle
    window.dispatchEvent(new CustomEvent('viewChanged', { detail: { view } }));
  }

  // Get the current view
  getView() {
    return this.currentView;
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
