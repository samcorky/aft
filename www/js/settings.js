// Settings page functionality
class Settings {
  constructor() {
    this.defaultBoardSelect = document.getElementById('default-board');
    this.timeFormatRadios = document.querySelectorAll('input[name="time-format"]');
    this.themeSelect = document.getElementById('theme-select');
    this.statusElement = document.getElementById('settings-status');
    this.saveTimeout = null;
  }

  async init() {
    await this.loadBoards();
    await this.loadSettings();
    this.loadThemeSelection();
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
      // Load default board
      const boardResponse = await fetch('/api/settings/default_board');
      
      if (boardResponse.ok) {
        const data = await boardResponse.json();
        if (data.success) {
          const defaultBoardId = data.value || '';
          this.defaultBoardSelect.value = defaultBoardId;
        }
      } else if (boardResponse.status === 404) {
        // Setting doesn't exist yet, will be created on save
        this.defaultBoardSelect.value = '';
      } else {
        console.error('Error loading default board:', boardResponse.statusText);
      }

      // Load time format
      const timeResponse = await fetch('/api/settings/time_format');
      
      if (timeResponse.ok) {
        const data = await timeResponse.json();
        if (data.success) {
          const value = data.value || '24';
          const timeFormat = (value === '12' || value === '24') ? value : '24';
          const radio = document.querySelector(`input[name="time-format"][value="${timeFormat}"]`);
          if (radio) {
            radio.checked = true;
          }
        }
      } else if (timeResponse.status === 404) {
        // Setting doesn't exist yet, will be created on save
        const defaultRadio = document.querySelector('input[name="time-format"][value="24"]');
        if (defaultRadio) {
          defaultRadio.checked = true;
        }
      } else {
        console.error('Error loading time format:', timeResponse.statusText);
      }
    } catch (err) {
      console.error('Error loading settings:', err);
    }
  }

  loadThemeSelection() {
    // For now, use session storage since themes aren't in database yet
    // TODO: Load from API when theme system is connected to database
    const savedTheme = sessionStorage.getItem('selectedTheme') || 'default';
    if (savedTheme && this.themeSelect) {
      this.themeSelect.value = savedTheme;
    }
  }

  saveThemeSelection() {
    // For now, save to session storage since themes aren't in database yet
    // TODO: Save to API when theme system is connected to database
    if (this.themeSelect) {
      const selectedTheme = this.themeSelect.value;
      sessionStorage.setItem('selectedTheme', selectedTheme);
      
      // Load the theme colors
      this.applyThemeColors(selectedTheme);
      
      this.showStatus('Theme saved', 'success');
      
      // Clear status after 2 seconds
      setTimeout(() => {
        this.statusElement.textContent = '';
        this.statusElement.className = 'settings-status';
      }, 2000);
    }
  }

  applyThemeColors(themeName) {
    // Define available themes (matching theme-builder.js)
    const themes = {
      'default': {
        'primary-color': '#3498DB',
        'primary-hover': '#2980B9',
        'secondary-color': '#95A5A6',
        'secondary-hover': '#7F8C8D',
        'success-color': '#28A745',
        'error-color': '#DC3545',
        'warning-color': '#FFC107',
        'text-color': '#2C3E50',
        'text-bold': '#2C3E50',
        'text-muted': '#7F8C8D',
        'background-light': '#F5F5F5',
        'page-panel-background': '#FFFFFF',
        'border-color': '#E0E0E0',
        'card-bg-color': '#FFFFFF',
        'header-background': '#2C3E50',
        'header-text-color': '#FFFFFF',
        'header-menu-background': '#FFFFFF',
        'header-menu-hover': '#F5F5F5',
        'header-menu-text-color': '#2C3E50',
        'header-button-background': '#404E5C',
        'header-button-hover': '#384552',
        'icon-color': '#FFFFFF'
      },
      'custom1': {
        'primary-color': '#d4a574',
        'primary-hover': '#b9945f',
        'secondary-color': '#06B6D4',
        'secondary-hover': '#0891b2',
        'success-color': '#14b8a6',
        'error-color': '#f43f5e',
        'warning-color': '#fb923c',
        'text-color': '#0f172a',
        'text-bold': '#2c3e50',
        'text-muted': '#64743b',
        'background-light': '#f0f9ff',
        'page-panel-background': '#ffffff',
        'border-color': '#cbd5e1',
        'card-bg-color': '#fafaf0',
        'header-background': '#d4a574',
        'header-text-color': '#ffffff',
        'header-menu-background': '#06B6D4',
        'header-menu-hover': '#0891b2',
        'header-menu-text-color': '#ffffff',
        'header-button-background': '#06B6D4',
        'header-button-hover': '#0891b2',
        'icon-color': '#ffffff'
      }
    };

    const theme = themes[themeName] || themes['default'];
    
    // Apply CSS variables to the page
    const root = document.documentElement;
    Object.keys(theme).forEach(key => {
      root.style.setProperty(`--${key}`, theme[key]);
    });

    // Save to session storage
    sessionStorage.setItem('currentTheme', JSON.stringify(theme));
  }

  async saveSettings() {
    try {
      // Show saving status
      this.showStatus('Saving...', 'info');
      
      const defaultBoardId = this.defaultBoardSelect.value;
      
      // Convert empty string to null for JSON
      const value = defaultBoardId === '' ? null : parseInt(defaultBoardId, 10);

      const response = await fetch('/api/settings/default_board', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ value })
      });

      const data = await response.json();

      if (!response.ok) {
        // Extract error message from API response if available
        const errorMessage = data.message || `HTTP error! status: ${response.status}`;
        throw new Error(errorMessage);
      }

      if (data.success) {
        this.showStatus('Saved', 'success');

        // Clear status after 2 seconds
        setTimeout(() => {
          this.statusElement.textContent = '';
          this.statusElement.className = 'settings-status';
        }, 2000);
      } else {
        this.showStatus('Error: ' + data.message, 'error');
      }

    } catch (err) {
      this.showStatus('Error: ' + err.message, 'error');
    }
  }

  async saveTimeFormat() {
    try {
      // Show saving status
      this.showStatus('Saving...', 'info');
      
      const selectedRadio = document.querySelector('input[name="time-format"]:checked');
      const timeFormat = selectedRadio ? selectedRadio.value : '24';

      const response = await fetch('/api/settings/time_format', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ value: timeFormat })
      });

      const data = await response.json();

      if (!response.ok) {
        const errorMessage = data.message || `HTTP error! status: ${response.status}`;
        throw new Error(errorMessage);
      }

      if (data.success) {
        // Update session storage to invalidate cache
        sessionStorage.setItem('timeFormat', timeFormat);
        
        this.showStatus('Saved', 'success');

        // Clear status after 2 seconds
        setTimeout(() => {
          this.statusElement.textContent = '';
          this.statusElement.className = 'settings-status';
        }, 2000);
      } else {
        this.showStatus('Error: ' + data.message, 'error');
      }

    } catch (err) {
      this.showStatus('Error: ' + err.message, 'error');
    }
  }

  attachEventListeners() {
    this.defaultBoardSelect.addEventListener('change', () => {
      // Clear any pending save
      if (this.saveTimeout) {
        clearTimeout(this.saveTimeout);
      }
      
      // Show pending status immediately
      this.showStatus('Pending...', 'info');
      
      // Debounce save by 500ms
      this.saveTimeout = setTimeout(() => {
        this.saveSettings();
      }, 500);
    });

    // Time format radio buttons
    this.timeFormatRadios.forEach(radio => {
      radio.addEventListener('change', () => {
        // Clear any pending save
        if (this.saveTimeout) {
          clearTimeout(this.saveTimeout);
        }
        
        // Show pending status immediately
        this.showStatus('Pending...', 'info');
        
        // Debounce save by 500ms
        this.saveTimeout = setTimeout(() => {
          this.saveTimeFormat();
        }, 500);
      });
    });

    // Theme selector
    if (this.themeSelect) {
      this.themeSelect.addEventListener('change', () => {
        // Clear any pending save
        if (this.saveTimeout) {
          clearTimeout(this.saveTimeout);
        }
        
        // Show pending status immediately
        this.showStatus('Pending...', 'info');
        
        // Debounce save by 500ms
        this.saveTimeout = setTimeout(() => {
          this.saveThemeSelection();
        }, 500);
      });
    }
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
