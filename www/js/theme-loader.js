// Global theme loader - applies saved theme to all pages
// This must run IMMEDIATELY in the HEAD to prevent style flash

(function() {
  const SAFE_THEME_SETTING_NAME = /^[A-Za-z0-9-]+$/;
  const colorValidationElement = document.createElement('span');

  function getSafeBackgroundImage(filename) {
    if (typeof filename !== 'string') {
      return null;
    }

    const trimmedFilename = filename.trim();
    if (!trimmedFilename || trimmedFilename === 'none') {
      return null;
    }

    return /^[A-Za-z0-9_.-]+$/.test(trimmedFilename) ? trimmedFilename : null;
  }

  function applyBackgroundImage(root, filename) {
    const safeFilename = getSafeBackgroundImage(filename);

    if (safeFilename) {
      root.style.setProperty('--background-image', `url('/images/backgrounds/${safeFilename}')`);
      return safeFilename;
    }

    root.style.setProperty('--background-image', 'none');
    return null;
  }

  function isSafeThemeSettingValue(value) {
    if (typeof value !== 'string') {
      return false;
    }

    const trimmedValue = value.trim();
    if (!trimmedValue) {
      return false;
    }

    if (typeof CSS !== 'undefined' && typeof CSS.supports === 'function') {
      return CSS.supports('color', trimmedValue);
    }

    colorValidationElement.style.color = '';
    colorValidationElement.style.color = trimmedValue;
    return colorValidationElement.style.color !== '';
  }

  function getSafeThemeSettings(settings) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
      return null;
    }

    const safeSettings = {};

    Object.entries(settings).forEach(([key, value]) => {
      if (!SAFE_THEME_SETTING_NAME.test(key) || !isSafeThemeSettingValue(value)) {
        return;
      }

      safeSettings[key] = value.trim();
    });

    return Object.keys(safeSettings).length > 0 ? safeSettings : null;
  }

  function applyThemeSettings(root, settings) {
    const safeSettings = getSafeThemeSettings(settings);

    if (!safeSettings) {
      return null;
    }

    Object.entries(safeSettings).forEach(([key, value]) => {
      root.style.setProperty(`--${key}`, value);
    });

    return safeSettings;
  }

  // Helper to apply theme colors and background
  function applyThemeToDOM(theme) {
    const root = document.documentElement;
    
    const safeThemeSettings = theme && theme.settings ? applyThemeSettings(root, theme.settings) : null;
    
    // Apply background image
    const safeBackgroundImage = applyBackgroundImage(root, theme && theme.background_image);
    if (typeof sessionStorage !== 'undefined') {
      if (safeThemeSettings) {
        sessionStorage.setItem('currentTheme', JSON.stringify(safeThemeSettings));
      }

      if (safeBackgroundImage) {
        sessionStorage.setItem('backgroundImage', safeBackgroundImage);
      } else {
        sessionStorage.setItem('backgroundImage', 'none');
      }
    }

    return !!safeThemeSettings;
  }

  // Try to load theme from sessionStorage first (fast path for same-session navigation)
  function applyFromSessionStorage() {
    const savedTheme = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('currentTheme') : null;
    const savedBgImage = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('backgroundImage') : null;
    
    if (savedTheme) {
      try {
        // Note: savedTheme is already the settings object (not wrapped in .settings)
        // because sessionStorage stores JSON.stringify(theme.settings) directly
        const theme = JSON.parse(savedTheme);
        const root = document.documentElement;
        const safeThemeSettings = applyThemeSettings(root, theme);

        if (!safeThemeSettings) {
          return false;
        }
        
        // Also apply the cached background image
        applyBackgroundImage(root, savedBgImage);
        
        return true; // Successfully applied cached theme
      } catch (e) {
        console.warn('Error parsing cached theme:', e);
      }
    }
    
    // Apply cached background if no theme cache
    applyBackgroundImage(document.documentElement, savedBgImage);
    
    return false; // No cached theme available
  }

  // Load theme from backend API - will override any cached theme
  async function loadThemeFromAPI() {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      
      const response = await fetch('/api/settings/theme', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        const theme = await response.json();
        
        // Apply theme from API
        applyThemeToDOM(theme);
        
        return true; // Successfully loaded from API
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.warn('Failed to load theme from API:', error.message);
      }
    }
    
    return false; // API call failed
  }

  // Initialize theme loading
  function init() {
    // First, apply cached theme if available (prevents flash)
    const hasCachedTheme = applyFromSessionStorage();
    
    // Only load from API if we don't have a cached theme
    // This reduces unnecessary API calls for same-session navigation
    if (!hasCachedTheme) {
      // Load fresh theme from API in background without blocking
      // Don't await - let it run asynchronously while page continues loading
      // This ensures we always have the latest theme from the database
      loadThemeFromAPI().catch(error => {
        // Silently handle API errors - cached theme or defaults are already applied
        console.debug('Background theme API update failed:', error.message);
      });
    }
  }

  // Run initialization
  init();
})();
