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
      // For now, load from localStorage
      // TODO: Later we'll load from API/database
      const defaultBoardId = localStorage.getItem('defaultBoardId') || '';
      this.defaultBoardSelect.value = defaultBoardId;
    } catch (err) {
      console.error('Error loading settings:', err);
    }
  }

  async saveSettings() {
    try {
      const defaultBoardId = this.defaultBoardSelect.value;

      // For now, save to localStorage
      // TODO: Later we'll save to API/database
      if (defaultBoardId) {
        localStorage.setItem('defaultBoardId', defaultBoardId);
      } else {
        localStorage.removeItem('defaultBoardId');
      }

      this.showStatus('Settings saved successfully', 'success');

      // Clear status after 3 seconds
      setTimeout(() => {
        this.statusElement.textContent = '';
        this.statusElement.className = 'settings-status';
      }, 3000);

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
