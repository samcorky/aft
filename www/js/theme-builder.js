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
      },
      'darkmode': {
        'primary-color': '#60A5FA',
        'primary-hover': '#3B82F6',
        'secondary-color': '#A78BFA',
        'secondary-hover': '#8B5CF6',
        'success-color': '#10B981',
        'error-color': '#EF4444',
        'warning-color': '#F59E0B',
        'text-color': '#E5E7EB',
        'text-bold': '#F9FAFB',
        'text-muted': '#9CA3AF',
        'background-light': '#1F2937',
        'page-panel-background': '#111827',
        'border-color': '#374151',
        'card-bg-color': '#1F2937',
        'header-background': '#0F172A',
        'header-text-color': '#F9FAFB',
        'header-menu-background': '#1E293B',
        'header-menu-hover': '#334155',
        'header-menu-text-color': '#E5E7EB',
        'header-button-background': '#1E40AF',
        'header-button-hover': '#1E3A8A',
        'icon-color': '#F9FAFB'
      },
      'jungle': {
        'primary-color': '#10B981',
        'primary-hover': '#059669',
        'secondary-color': '#F59E0B',
        'secondary-hover': '#D97706',
        'success-color': '#22C55E',
        'error-color': '#DC2626',
        'warning-color': '#FBBF24',
        'text-color': '#1C3D2C',
        'text-bold': '#14532D',
        'text-muted': '#6B7280',
        'background-light': '#F0FDF4',
        'page-panel-background': '#FFFFFF',
        'border-color': '#BBF7D0',
        'card-bg-color': '#ECFDF5',
        'header-background': '#166534',
        'header-text-color': '#F0FDF4',
        'header-menu-background': '#FEF3C7',
        'header-menu-hover': '#FDE68A',
        'header-menu-text-color': '#78350F',
        'header-button-background': '#CA8A04',
        'header-button-hover': '#A16207',
        'icon-color': '#F0FDF4'
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
      'text-color', 'text-bold', 'text-muted',
      'background-light', 'page-panel-background', 'border-color',
      'card-bg-color', 'header-background', 'header-text-color', 'header-menu-background', 'header-menu-hover', 'header-menu-text-color', 'header-button-background', 'header-button-hover', 'icon-color'
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

      // Also sync text input to color picker on input (live typing)
      textInput.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-Fa-f]{6}$/.test(value)) {
          colorInput.value = value;
          this.applyThemeToPage();
        }
      });

      // Apply color on blur even if incomplete during typing
      textInput.addEventListener('blur', (e) => {
        const value = e.target.value.trim();
        // Allow with or without # prefix
        const hexValue = value.startsWith('#') ? value : '#' + value;
        
        if (/^#[0-9A-Fa-f]{6}$/.test(hexValue)) {
          colorInput.value = hexValue;
          textInput.value = hexValue.toUpperCase();
          this.applyThemeToPage();
        } else if (/^#[0-9A-Fa-f]{3}$/.test(hexValue)) {
          // Convert 3-digit hex to 6-digit
          const expanded = '#' + hexValue[1] + hexValue[1] + hexValue[2] + hexValue[2] + hexValue[3] + hexValue[3];
          colorInput.value = expanded;
          textInput.value = expanded.toUpperCase();
          this.applyThemeToPage();
        } else {
          // Invalid hex, revert to current color picker value
          textInput.value = colorInput.value.toUpperCase();
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
    
    // Check if there are saved customizations in session
    const savedTheme = sessionStorage.getItem('currentTheme');
    
    if (savedTheme) {
      // Load the customized theme from session
      try {
        const theme = JSON.parse(savedTheme);
        this.applyTheme(theme);
      } catch (e) {
        console.error('Error loading saved theme:', e);
        this.loadSelectedTheme();
      }
    } else {
      // Load the base theme for the selector
      this.loadSelectedTheme();
    }
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
    
    // Clear any saved customizations from session
    sessionStorage.removeItem('currentTheme');
    
    this.showStatus('Reset to base theme and cleared session customizations', 'success');
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
