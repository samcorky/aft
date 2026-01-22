// Global theme loader - applies saved theme to all pages
// This must run IMMEDIATELY in the HEAD to prevent style flash

(function() {
  // Helper to apply theme colors and background
  function applyThemeToDOM(theme) {
    const root = document.documentElement;
    
    if (theme && theme.settings) {
      // Apply all color variables from theme settings
      Object.keys(theme.settings).forEach(key => {
        root.style.setProperty(`--${key}`, theme.settings[key]);
      });
    }
    
    // Apply background image
    if (theme && theme.background_image) {
      root.style.setProperty('--background-image', `url('/images/backgrounds/${theme.background_image}')`);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem('backgroundImage', theme.background_image);
      }
    } else {
      root.style.setProperty('--background-image', 'none');
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem('backgroundImage', 'none');
      }
    }
  }

  // Try to load theme from sessionStorage first (fast path for same-session navigation)
  function applyFromSessionStorage() {
    const savedTheme = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('currentTheme') : null;
    const savedBgImage = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('backgroundImage') : null;
    
    if (savedTheme) {
      try {
        const theme = JSON.parse(savedTheme);
        const root = document.documentElement;
        
        // Apply all CSS variables from cache
        Object.keys(theme).forEach(key => {
          root.style.setProperty(`--${key}`, theme[key]);
        });
        
        return true; // Successfully applied cached theme
      } catch (e) {
        console.warn('Error parsing cached theme:', e);
      }
    }
    
    // Apply cached background if no theme cache
    if (savedBgImage && savedBgImage !== 'none') {
      document.documentElement.style.setProperty('--background-image', `url('/images/backgrounds/${savedBgImage}')`);
    } else {
      document.documentElement.style.setProperty('--background-image', 'none');
    }
    
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
        
        // Update sessionStorage cache
        if (theme && theme.settings && typeof sessionStorage !== 'undefined') {
          sessionStorage.setItem('currentTheme', JSON.stringify(theme.settings));
        }
        
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
  async function init() {
    // First, apply cached theme if available (prevents flash)
    const hasCachedTheme = applyFromSessionStorage();
    
    // Then, load fresh theme from API in background
    // This ensures we always have the latest theme from the database
    await loadThemeFromAPI();
  }

  // Run initialization
  init().catch(error => {
    console.error('Theme loader initialization error:', error);
  });
})();
