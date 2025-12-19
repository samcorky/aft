// Global theme loader - applies saved theme to all pages

(function() {
  // Load and apply theme as early as possible to prevent flash
  function loadTheme() {
    const savedTheme = sessionStorage.getItem('currentTheme');
    
    if (savedTheme) {
      try {
        const theme = JSON.parse(savedTheme);
        const root = document.documentElement;
        
        // Apply all CSS variables
        Object.keys(theme).forEach(key => {
          root.style.setProperty(`--${key}`, theme[key]);
        });
      } catch (e) {
        console.error('Error loading theme:', e);
      }
    }

    // Load and apply background image
    const savedBgImage = sessionStorage.getItem('backgroundImage');
    if (savedBgImage && savedBgImage !== 'none') {
      const imageUrl = `/images/backgrounds/${savedBgImage}`;
      document.documentElement.style.setProperty('--background-image', `url('${imageUrl}')`);
    } else {
      document.documentElement.style.setProperty('--background-image', 'none');
    }
  }

  // Apply immediately if DOM is already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadTheme);
  } else {
    loadTheme();
  }
})();
