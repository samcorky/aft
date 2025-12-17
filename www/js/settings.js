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
    await this.loadThemes();
    await this.applyThemeColors(); // Ensure theme is loaded on page load
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

  async loadThemes() {
    try {
      const response = await fetch('/api/themes');
      if (!response.ok) throw new Error('Failed to load themes');
      
      const themes = await response.json();
      
      // Split into user and system themes
      const userThemes = themes.filter(t => !t.system_theme).sort((a, b) => a.name.localeCompare(b.name));
      const systemThemes = themes.filter(t => t.system_theme).sort((a, b) => a.name.localeCompare(b.name));
      
      // Populate theme select
      this.themeSelect.innerHTML = '';
      
      // Add user themes first
      if (userThemes.length > 0) {
        const userGroup = document.createElement('optgroup');
        userGroup.label = 'User Themes';
        userThemes.forEach(theme => {
          const option = document.createElement('option');
          option.value = theme.id;
          option.textContent = theme.name;
          userGroup.appendChild(option);
        });
        this.themeSelect.appendChild(userGroup);
      }
      
      // Add system themes
      if (systemThemes.length > 0) {
        const systemGroup = document.createElement('optgroup');
        systemGroup.label = 'System Themes';
        systemThemes.forEach(theme => {
          const option = document.createElement('option');
          option.value = theme.id;
          option.textContent = theme.name;
          systemGroup.appendChild(option);
        });
        this.themeSelect.appendChild(systemGroup);
      }
      
      // Load current theme selection
      const settingsResponse = await fetch('/api/settings/theme');
      if (settingsResponse.ok) {
        const currentTheme = await settingsResponse.json();
        this.themeSelect.value = currentTheme.id;
      }
    } catch (error) {
      console.error('Error loading themes:', error);
    }
  }
  
  async onThemeChange() {
    try {
      const themeId = parseInt(this.themeSelect.value);
      
      // Save theme selection
      const response = await fetch('/api/settings/theme', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme_id: themeId })
      });
      
      if (!response.ok) throw new Error('Failed to save theme selection');
      
      // Apply the theme colors
      await this.applyThemeColors();
      
      this.showStatus('Theme changed successfully', 'success');
    } catch (error) {
      console.error('Error changing theme:', error);
      this.showStatus('Error changing theme: ' + error.message, 'error');
    }
  }
  
  editTheme() {
    const themeId = this.themeSelect.value;
    // Navigate to theme builder with selected theme
    window.location.href = `/theme-builder.html?theme=${themeId}`;
  }

  async applyThemeColors() {
    // Fetch and apply theme from API
    try {
      const response = await fetch('/api/settings/theme');
      const theme = await response.json();
      const root = document.documentElement;
      const settings = theme.settings;
      
      // Apply all CSS variables
      for (const [key, value] of Object.entries(settings)) {
        root.style.setProperty(`--${key}`, value);
      }
      
      // Apply background image if present
      if (theme.background_image) {
        root.style.setProperty('--background-image', `url('/images/backgrounds/${theme.background_image}')`);
        sessionStorage.setItem('backgroundImage', theme.background_image);
      } else {
        root.style.setProperty('--background-image', 'none');
        sessionStorage.setItem('backgroundImage', 'none');
      }
      
      // Update sessionStorage for persistence
      sessionStorage.setItem('currentTheme', JSON.stringify(settings));
    } catch (error) {
      console.error('Error loading theme:', error);
    }
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
        this.onThemeChange();
      });
    }
    
    // Edit theme button
    const editThemeBtn = document.getElementById('edit-theme-btn');
    if (editThemeBtn) {
      editThemeBtn.addEventListener('click', () => {
        this.editTheme();
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
