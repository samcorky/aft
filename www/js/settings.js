// Settings page functionality
class Settings {
  constructor() {
    this.defaultBoardSelect = document.getElementById('default-board');
    this.saveButton = document.getElementById('save-settings-btn');
    this.statusElement = document.getElementById('settings-status');
  }

  async init() {
    await this.loadBoards();
    await this.loadSettings();
    this.attachEventListeners();
  }

  async loadBoards() {
    try {
      const response = await fetch('/api/boards');
      const data = await response.json();

      if (data.success) {
        this.renderBoardOptions(data.boards);
      } else {
        this.showStatus('Failed to load boards: ' + data.message, 'error');
      }
    } catch (err) {
      this.showStatus('Error loading boards: ' + err.message, 'error');
    }
  }

  renderBoardOptions(boards) {
    // Clear existing options
    this.defaultBoardSelect.innerHTML = '';

    // Add "None" option
    const noneOption = document.createElement('option');
    noneOption.value = '';
    noneOption.textContent = 'None (Boards page)';
    this.defaultBoardSelect.appendChild(noneOption);

    // Add board options
    boards.forEach(board => {
      const option = document.createElement('option');
      option.value = board.id;
      option.textContent = board.name;
      this.defaultBoardSelect.appendChild(option);
    });
  }

  async loadSettings() {
    try {
      // Load from API
      const response = await fetch('/api/settings/default_board');
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          const defaultBoardId = data.value || '';
          this.defaultBoardSelect.value = defaultBoardId;
        }
      } else if (response.status === 404) {
        // Setting doesn't exist yet, will be created on save
        this.defaultBoardSelect.value = '';
      } else {
        console.error('Error loading settings:', response.statusText);
      }
    } catch (err) {
      console.error('Error loading settings:', err);
    }
  }

  async saveSettings() {
    try {
      const defaultBoardId = this.defaultBoardSelect.value;
      
      // Convert empty string to null for JSON
      const value = defaultBoardId === '' ? null : parseInt(defaultBoardId);

      const response = await fetch('/api/settings/default_board', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ value })
      });

      const data = await response.json();

      if (data.success) {
        this.showStatus('Settings saved successfully', 'success');

        // Clear status after 3 seconds
        setTimeout(() => {
          this.statusElement.textContent = '';
          this.statusElement.className = 'settings-status';
        }, 3000);
      } else {
        this.showStatus('Error saving settings: ' + data.message, 'error');
      }

    } catch (err) {
      this.showStatus('Error saving settings: ' + err.message, 'error');
    }
  }

  attachEventListeners() {
    this.saveButton.addEventListener('click', () => this.saveSettings());
  }

  showStatus(message, type = 'info') {
    this.statusElement.textContent = message;
    this.statusElement.className = `settings-status ${type}`;
  }
}

// Initialize settings when page loads
document.addEventListener('DOMContentLoaded', () => {
  const settings = new Settings();
  settings.init();
});
