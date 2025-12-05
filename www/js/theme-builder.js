// Theme Builder functionality

class ThemeBuilder {
  constructor() {
    this.themeSelect = null;
    this.saveBtn = null;
    this.resetBtn = null;
    this.statusDiv = null;
    this.colorInputs = {};
    
    // Available themes
    this.themes = {
      'default': {
        'primary-color': '#3498db',
        'primary-hover': '#2980b9',
        'secondary-color': '#95a5a6',
        'secondary-hover': '#7f8c8d',
        'success-color': '#28a745',
        'error-color': '#dc3545',
        'warning-color': '#ffc107',
        'text-color': '#2c3e50',
        'text-muted': '#7f8c8d',
        'background-light': '#f5f5f5',
        'card-background': '#ffffff',
        'border-color': '#e0e0e0',
        'card-bg-color': '#ffffff'
      },
      'custom1': {
        'primary-color': '#d4a574',
        'primary-hover': '#b8945f',
        'secondary-color': '#1e40af',
        'secondary-hover': '#1e3a8a',
        'success-color': '#14b8a6',
        'error-color': '#f43f5e',
        'warning-color': '#fb923c',
        'text-color': '#0f172a',
        'text-muted': '#64748b',
        'background-light': '#f0f9ff',
        'card-background': '#ffffff',
        'border-color': '#cbd5e1',
        'card-bg-color': '#fefce8'
      }
    };
    this.defaultTheme = this.themes['default'];
  }

  async init() {
    // Get element references
    this.themeSelect = document.getElementById('theme-builder-select');
    this.saveBtn = document.getElementById('save-theme-btn');
    this.resetBtn = document.getElementById('reset-theme-btn');
    this.statusDiv = document.getElementById('theme-status');

    // Get all color inputs
    const colorFields = [
      'primary-color', 'primary-hover', 'secondary-color', 'secondary-hover',
      'success-color', 'error-color', 'warning-color',
      'text-color', 'text-muted',
      'background-light', 'card-background', 'border-color',
      'card-bg-color'
    ];

    colorFields.forEach(field => {
      const colorInput = document.getElementById(field);
      const textInput = colorInput.nextElementSibling;
      this.colorInputs[field] = { color: colorInput, text: textInput };

      // Update text input when color changes
      colorInput.addEventListener('input', (e) => {
        textInput.value = e.target.value.toUpperCase();
        this.applyThemeToPage();
      });

      // Also sync text input to color picker
      textInput.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-Fa-f]{6}$/.test(value)) {
          colorInput.value = value;
          this.applyThemeToPage();
        }
      });
    });

    // Set up event listeners
    this.setupEventListeners();

    // Load current theme from session storage or defaults
    this.loadCurrentTheme();
  }

  setupEventListeners() {
    // Save theme button
    if (this.saveBtn) {
      this.saveBtn.addEventListener('click', () => {
        this.saveTheme();
      });
    }

    // Reset button
    if (this.resetBtn) {
      this.resetBtn.addEventListener('click', () => {
        this.resetToDefaults();
      });
    }

    // Theme selector (for future when we have multiple themes)
    if (this.themeSelect) {
      this.themeSelect.addEventListener('change', () => {
        this.loadSelectedTheme();
      });
    }
  }

  loadCurrentTheme() {
    // Check which theme is selected in session
    const selectedTheme = sessionStorage.getItem('selectedTheme') || 'default';
    if (this.themeSelect) {
      this.themeSelect.value = selectedTheme;
    }
    
    // Load the base theme for the selector (don't apply session customizations)
    // This allows user to see and edit the base theme without session overrides
    this.loadSelectedTheme();
  }

  loadSelectedTheme() {
    const selectedTheme = this.themeSelect ? this.themeSelect.value : 'default';
    
    // Load the theme for preview (don't save to session automatically)
    const theme = this.themes[selectedTheme] || this.defaultTheme;
    this.applyTheme(theme);
    
    // TODO: Later this will fetch from API based on selected theme ID
  }

  applyTheme(theme) {
    // Update all color inputs
    Object.keys(theme).forEach(key => {
      if (this.colorInputs[key]) {
        const value = theme[key];
        this.colorInputs[key].color.value = value;
        this.colorInputs[key].text.value = value.toUpperCase();
      }
    });

    // Apply to page
    this.applyThemeToPage();
  }

  applyThemeToPage() {
    // Get current values from inputs
    const theme = {};
    Object.keys(this.colorInputs).forEach(key => {
      theme[key] = this.colorInputs[key].color.value;
    });

    // Apply CSS variables to the page (preview only, not saved to session)
    const root = document.documentElement;
    Object.keys(theme).forEach(key => {
      root.style.setProperty(`--${key}`, theme[key]);
    });
  }

  saveTheme() {
    // Get current values
    const theme = {};
    Object.keys(this.colorInputs).forEach(key => {
      theme[key] = this.colorInputs[key].color.value;
    });

    // Get selected theme name
    const selectedTheme = this.themeSelect ? this.themeSelect.value : 'default';

    // Save customized theme to session storage
    sessionStorage.setItem('currentTheme', JSON.stringify(theme));
    sessionStorage.setItem('selectedTheme', selectedTheme);

    // Show success message
    this.showStatus('Theme saved and applied to session!', 'success');

    // TODO: When API is ready, save to database
    // fetch('/api/themes', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(theme)
    // });
  }

  resetToDefaults() {
    const selectedTheme = this.themeSelect ? this.themeSelect.value : 'default';
    const theme = this.themes[selectedTheme] || this.defaultTheme;
    this.applyTheme(theme);
    this.showStatus('Preview reset to base theme', 'success');
  }

  showStatus(message, type = 'success') {
    if (!this.statusDiv) return;

    this.statusDiv.textContent = message;
    this.statusDiv.className = `settings-status ${type}`;
    this.statusDiv.style.display = 'block';

    setTimeout(() => {
      this.statusDiv.style.display = 'none';
    }, 3000);
  }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
  const themeBuilder = new ThemeBuilder();
  themeBuilder.init();
});
