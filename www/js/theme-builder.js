// Theme Builder functionality - Database-backed version

class ThemeBuilder {
  constructor() {
    this.themeSelect = null;
    this.saveBtn = null;
    this.statusDiv = null;
    this.colorInputs = {};
    this.themes = {}; // Will be loaded from API
    this.currentTheme = null;
    this.currentThemeData = null;
  }
  
  /**
   * Safely parse JSON response, handling non-JSON errors
   * @param {Response} response - Fetch response object
   * @returns {Promise<Object>} Parsed JSON data or error object
   */
  async parseResponse(response) {
    try {
      const data = await response.json();
      if (!response.ok) {
        // Response parsed successfully but HTTP status indicates error
        return data;
      }
      return data;
    } catch (error) {
      // JSON parsing failed
      return {
        success: false,
        message: response.ok 
          ? `Invalid JSON response from server` 
          : `HTTP error! status: ${response.status}`
      };
    }
  }
  
  /**
   * Show error toast notification
   */
  showErrorToast(message) {
    if (window.header && typeof window.header.showErrorToast === 'function') {
      window.header.showErrorToast(message);
    } else {
      this.showStatus(message, 'error');
    }
  }
  
  /**
   * Show success toast notification
   */
  showSuccessToast(message) {
    if (window.header && typeof window.header.showSuccessToast === 'function') {
      window.header.showSuccessToast(message);
    } else {
      this.showStatus(message, 'success');
    }
  }
  
  async init() {
    this.themeSelect = document.getElementById('theme-builder-select');
    this.saveBtn = document.getElementById('save-theme-btn');
    this.applyBtn = document.getElementById('apply-theme-btn');
    this.statusDiv = document.getElementById('theme-status');
    this.backgroundSelect = document.getElementById('background-image-select');
    
    // Initialize all color inputs
    this.initColorInputs();
    
    // Load themes and background images from API
    await Promise.all([
      this.loadThemes(),
      this.loadBackgroundImages()
    ]);
    
    // Set up event listeners
    this.themeSelect.addEventListener('change', () => this.onThemeChange());
    this.saveBtn.addEventListener('click', () => this.saveTheme());
    this.applyBtn.addEventListener('click', () => this.applyTheme());
    this.backgroundSelect.addEventListener('change', () => this.onBackgroundChange());
    
    // Copy theme functionality
    document.getElementById('copy-theme-btn').addEventListener('click', () => this.showCopyModal());
    document.getElementById('copy-theme-close').addEventListener('click', () => this.hideCopyModal());
    document.getElementById('copy-theme-cancel').addEventListener('click', () => this.hideCopyModal());
    document.getElementById('copy-theme-confirm').addEventListener('click', () => this.confirmCopyTheme());
    
    // Rename theme functionality
    document.getElementById('rename-theme-btn').addEventListener('click', () => this.showRenameModal());
    document.getElementById('rename-theme-close').addEventListener('click', () => this.hideRenameModal());
    document.getElementById('rename-theme-cancel').addEventListener('click', () => this.hideRenameModal());
    document.getElementById('rename-theme-confirm').addEventListener('click', () => this.confirmRenameTheme());
    
    // Import/Export
    document.getElementById('import-theme-btn').addEventListener('click', () => this.importTheme());
    document.getElementById('export-theme-btn').addEventListener('click', () => this.exportTheme());
    
    // Background image
    document.getElementById('upload-bg-btn').addEventListener('click', () => this.uploadBackground());
    document.getElementById('download-bg-btn').addEventListener('click', () => this.downloadBackground());
    document.getElementById('bg-image-input').addEventListener('change', (e) => this.handleBackgroundUpload(e));
    document.getElementById('import-theme-input').addEventListener('change', (e) => this.handleThemeImport(e));
    
    // Check for theme parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const themeParam = urlParams.get('theme');
    if (themeParam && this.themes[themeParam]) {
      this.themeSelect.value = themeParam;
    }
    
    // Load initial theme
    if (this.themeSelect.value) {
      await this.onThemeChange();
    }
  }
  
  initColorInputs() {
    // Get all color inputs
    const colorInputs = document.querySelectorAll('input[type="color"]');
    
    colorInputs.forEach(input => {
      const variableName = input.id;
      const textInput = input.nextElementSibling;
      
      this.colorInputs[variableName] = { colorInput: input, textInput };
      
      // Sync color picker with text input
      input.addEventListener('input', (e) => {
        textInput.value = e.target.value.toUpperCase();
        this.applyThemePreview();
      });
      
      // Sync text input with color picker
      textInput.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-F]{6}$/i.test(value)) {
          input.value = value;
          this.applyThemePreview();
        }
      });
    });
  }
  
  async loadThemes() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch('/api/themes', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const themes = await this.parseResponse(response);
      
      if (!response.ok || (themes.success === false)) {
        throw new Error(themes.message || themes.error || 'Failed to load themes');
      }
      this.themes = {};
      
      // Split into user and system themes
      const userThemes = themes.filter(t => !t.system_theme).sort((a, b) => a.name.localeCompare(b.name));
      const systemThemes = themes.filter(t => t.system_theme).sort((a, b) => a.name.localeCompare(b.name));
      
      // Clear existing options
      this.themeSelect.innerHTML = '';
      
      // Add user themes first
      if (userThemes.length > 0) {
        const userGroup = document.createElement('optgroup');
        userGroup.label = 'User Themes';
        userThemes.forEach(theme => {
          this.themes[theme.id] = theme;
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
          this.themes[theme.id] = theme;
          const option = document.createElement('option');
          option.value = theme.id;
          option.textContent = theme.name;
          systemGroup.appendChild(option);
        });
        this.themeSelect.appendChild(systemGroup);
      }
      
      // Only load current theme selection if no URL parameter
      const urlParams = new URLSearchParams(window.location.search);
      const themeParam = urlParams.get('theme');
      
      if (!themeParam) {
        // Load current theme selection from settings
        const settingsController = new AbortController();
        const settingsTimeoutId = setTimeout(() => settingsController.abort(), 5000);
        
        try {
          const settingsResponse = await fetch('/api/settings/theme', {
            signal: settingsController.signal
          });
          
          clearTimeout(settingsTimeoutId);
          
          if (settingsResponse.ok) {
            const currentTheme = await this.parseResponse(settingsResponse);
            if (currentTheme.id) {
              this.themeSelect.value = currentTheme.id;
            }
          }
        } catch (err) {
          clearTimeout(settingsTimeoutId);
          if (err.name === 'AbortError') {
            console.error('Settings fetch timed out');
          } else {
            console.error('Error fetching settings:', err);
          }
        }
      }
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        console.error('Themes fetch timed out after 5 seconds');
        this.showErrorToast('Request timed out. Check your connection.');
      } else {
        console.error('Error loading themes:', error);
        this.showErrorToast('Error loading themes: ' + error.message);
      }
    }
  }
  
  async loadBackgroundImages() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch('/api/themes/images', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const data = await this.parseResponse(response);
      
      if (!response.ok || (data.success === false)) {
        throw new Error(data.message || data.error || 'Failed to load background images');
      }
      const images = data.images || [];
      
      // Clear existing options except "None"
      this.backgroundSelect.innerHTML = '<option value="none">None (Use Colors)</option>';
      
      // Add image options
      images.forEach(filename => {
        const option = document.createElement('option');
        option.value = filename;
        option.textContent = filename;
        this.backgroundSelect.appendChild(option);
      });
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        console.error('Background images fetch timed out after 5 seconds');
        this.showErrorToast('Request timed out. Check your connection.');
      } else {
        console.error('Error loading background images:', error);
        this.showErrorToast('Error loading background images: ' + error.message);
      }
    }
  }
  
  onBackgroundChange() {
    const selectedValue = this.backgroundSelect.value;
    
    // Don't update currentThemeData - keep original for comparison
    // The change will be saved when user clicks Save
    
    // Apply the background change immediately to preview
    this.applyThemePreview();
    
    // Update download button state
    const downloadBtn = document.getElementById('download-bg-btn');
    downloadBtn.disabled = selectedValue === 'none';
  }
  
  async onThemeChange() {
    const themeId = parseInt(this.themeSelect.value);
    const theme = this.themes[themeId];
    
    if (!theme) {
      console.error('Theme not found:', themeId);
      return;
    }
    
    this.currentTheme = themeId;
    this.currentThemeData = theme;
    
    // Load theme colors into inputs
    this.loadThemeColors(theme.settings);
    
    // Update background image display
    this.updateBackgroundDisplay(theme.background_image);
    
    // Apply theme preview
    this.applyThemePreview();
    
    // Update save button state
    this.updateSaveButtonState(theme.system_theme);
  }
  
  loadThemeColors(settings) {
    for (const [key, value] of Object.entries(settings)) {
      if (this.colorInputs[key]) {
        this.colorInputs[key].colorInput.value = value;
        this.colorInputs[key].textInput.value = value.toUpperCase();
      }
    }
  }
  
  updateBackgroundDisplay(filename) {
    // Set background selector value
    if (filename) {
      this.backgroundSelect.value = filename;
    } else {
      this.backgroundSelect.value = 'none';
    }
    
    // Update download button state
    const downloadBtn = document.getElementById('download-bg-btn');
    downloadBtn.disabled = !filename;
  }
  
  updateSaveButtonState(isSystemTheme) {
    const renameBtn = document.getElementById('rename-theme-btn');
    
    if (isSystemTheme) {
      this.saveBtn.disabled = true;
      this.saveBtn.title = 'System themes cannot be modified. Create a copy to edit.';
      renameBtn.disabled = true;
      renameBtn.title = 'System themes cannot be renamed. Create a copy to edit.';
      
      // Disable all color inputs
      for (const inputs of Object.values(this.colorInputs)) {
        inputs.colorInput.disabled = true;
        inputs.textInput.disabled = true;
      }
      
      // Disable background selector and upload
      this.backgroundSelect.disabled = true;
      document.getElementById('upload-bg-btn').disabled = true;
    } else {
      this.saveBtn.disabled = false;
      this.saveBtn.title = 'Save changes to this theme';
      renameBtn.disabled = false;
      renameBtn.title = 'Rename the selected theme';
      
      // Enable all color inputs
      for (const inputs of Object.values(this.colorInputs)) {
        inputs.colorInput.disabled = false;
        inputs.textInput.disabled = false;
      }
      
      // Enable background selector and upload
      this.backgroundSelect.disabled = false;
      document.getElementById('upload-bg-btn').disabled = false;
    }
  }
  
  applyThemePreview() {
    // Apply current color values to CSS variables for live preview
    const root = document.documentElement;
    
    for (const [variableName, inputs] of Object.entries(this.colorInputs)) {
      root.style.setProperty(`--${variableName}`, inputs.colorInput.value);
    }
    
    // Apply background image
    const bgValue = this.backgroundSelect.value;
    if (bgValue && bgValue !== 'none') {
      root.style.setProperty('--background-image', `url('/images/backgrounds/${bgValue}')`);
    } else {
      root.style.setProperty('--background-image', 'none');
    }
  }
  
  async applyTheme() {
    if (!this.currentTheme || !this.currentThemeData) {
      this.showStatus('No theme selected', 'error');
      return;
    }
    
    // System themes can't have changes (inputs are disabled), so apply directly
    if (this.currentThemeData.system_theme) {
      await this.doApplyTheme();
      return;
    }
    
    // For user themes, check if there are unsaved changes
    if (this.hasUnsavedChanges()) {
      this.showUnsavedChangesModal();
      return;
    }
    
    // No unsaved changes, apply the theme from database
    await this.doApplyTheme();
  }
  
  hasUnsavedChanges() {
    // Check if any color has changed
    for (const [key, value] of Object.entries(this.currentThemeData.settings)) {
      if (this.colorInputs[key]) {
        const currentValue = this.colorInputs[key].colorInput.value.toUpperCase();
        const savedValue = value.toUpperCase();
        if (currentValue !== savedValue) {
          console.log(`Color changed: ${key} from ${savedValue} to ${currentValue}`);
          return true;
        }
      }
    }
    
    // Check if background image has changed
    const currentBg = this.backgroundSelect.value === 'none' ? null : this.backgroundSelect.value;
    const savedBg = this.currentThemeData.background_image || null;
    if (currentBg !== savedBg) {
      console.log(`Background changed from ${savedBg} to ${currentBg}`);
      return true;
    }
    
    return false;
  }
  
  showUnsavedChangesModal() {
    const modal = document.getElementById('unsaved-changes-modal');
    modal.style.display = 'flex';
    
    // Set up event listeners (remove old ones first)
    const closeBtn = document.getElementById('unsaved-changes-close');
    const discardBtn = document.getElementById('unsaved-discard');
    const saveBtn = document.getElementById('unsaved-save');
    const cancelBtn = document.getElementById('unsaved-cancel');
    
    const close = () => { modal.style.display = 'none'; };
    const discard = async () => {
      modal.style.display = 'none';
      await this.doApplyTheme();
    };
    const save = async () => {
      modal.style.display = 'none';
      await this.saveTheme();
      if (!this.lastSaveError) {
        await this.doApplyTheme();
      }
    };
    
    closeBtn.onclick = close;
    discardBtn.onclick = discard;
    saveBtn.onclick = save;
    cancelBtn.onclick = close;
  }
  
  async doApplyTheme() {
    // Check database connection
    if (!window.header || !window.header.dbConnected) {
      this.showErrorToast('Cannot apply theme: Database not connected');
      return;
    }
    
    const applyBtn = this.applyBtn;
    const originalText = applyBtn.textContent;
    
    // Add loading state with delay
    const loadingTimeout = setTimeout(() => {
      applyBtn.textContent = 'Applying...';
      applyBtn.disabled = true;
    }, 500);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      // Save theme selection to settings (apply to session)
      const response = await fetch('/api/settings/theme', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme_id: this.currentTheme }),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const result = await this.parseResponse(response);
      
      if (!response.ok || (result.success === false)) {
        throw new Error(result.message || result.error || 'Failed to apply theme');
      }
      
      // Fetch and apply theme from database
      await this.loadAndApplyTheme();
      
      // Reload the theme data into currentThemeData
      const themeController = new AbortController();
      const themeTimeoutId = setTimeout(() => themeController.abort(), 5000);
      
      try {
        const themeResponse = await fetch('/api/settings/theme', {
          signal: themeController.signal
        });
        
        clearTimeout(themeTimeoutId);
        
        if (themeResponse.ok) {
          const theme = await this.parseResponse(themeResponse);
          
          if (theme && theme.settings) {
            this.currentThemeData = theme;
            
            // Reload theme colors into inputs to discard any unsaved changes
            this.loadThemeColors(theme.settings);
            this.updateBackgroundDisplay(theme.background_image);
          }
        }
      } catch (err) {
        clearTimeout(themeTimeoutId);
        console.error('Error reloading theme data:', err);
      }
      
      clearTimeout(loadingTimeout);
      applyBtn.textContent = originalText;
      applyBtn.disabled = false;
      
      this.showSuccessToast('Theme applied to session successfully');
    } catch (error) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      applyBtn.textContent = originalText;
      applyBtn.disabled = false;
      
      if (error.name === 'AbortError') {
        console.error('Apply theme request timed out after 5 seconds');
        this.showErrorToast('Request timed out. Check your connection.');
      } else {
        console.error('Error applying theme:', error);
        this.showErrorToast('Error applying theme: ' + error.message);
      }
    }
  }
  
  async loadAndApplyTheme() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      // Fetch the current theme from settings
      const response = await fetch('/api/settings/theme', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const theme = await this.parseResponse(response);
      
      if (!response.ok || (theme.success === false)) {
        throw new Error(theme.message || theme.error || 'Failed to load theme');
      }
      const root = document.documentElement;
      const settings = theme.settings;
      
      // Apply all color variables
      Object.keys(settings).forEach(key => {
        root.style.setProperty(`--${key}`, settings[key]);
      });
      
      // Apply background image
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
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        console.error('Load theme request timed out after 5 seconds');
        throw new Error('Request timed out. Check your connection.');
      }
      
      console.error('Error loading and applying theme:', error);
      throw error;
    }
  }
  
  async saveTheme() {
    if (!this.currentTheme || !this.currentThemeData) {
      this.showErrorToast('No theme selected');
      this.lastSaveError = true;
      return;
    }
    
    if (this.currentThemeData.system_theme) {
      this.showErrorToast('Cannot save system themes');
      this.lastSaveError = true;
      return;
    }
    
    // Check database connection
    if (!window.header || !window.header.dbConnected) {
      this.showErrorToast('Cannot save theme: Database not connected');
      this.lastSaveError = true;
      return;
    }
    
    const saveBtn = this.saveBtn;
    const originalText = saveBtn.textContent;
    
    // Add loading state with delay
    const loadingTimeout = setTimeout(() => {
      saveBtn.textContent = 'Saving...';
      saveBtn.disabled = true;
    }, 500);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      this.lastSaveError = false;
      
      // Collect current color values
      const settings = {};
      for (const [variableName, inputs] of Object.entries(this.colorInputs)) {
        settings[variableName] = inputs.colorInput.value;
      }
      
      // Get background image
      const bgValue = this.backgroundSelect.value;
      const background_image = bgValue === 'none' ? null : bgValue;
      
      // Save to API
      const response = await fetch(`/api/themes/${this.currentTheme}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          settings,
          background_image
        }),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const updatedTheme = await this.parseResponse(response);
      
      if (!response.ok || (updatedTheme.success === false)) {
        throw new Error(updatedTheme.message || updatedTheme.error || 'Failed to save theme');
      }
      this.themes[this.currentTheme] = updatedTheme;
      this.currentThemeData = updatedTheme;
      
      clearTimeout(loadingTimeout);
      saveBtn.textContent = originalText;
      saveBtn.disabled = false;
      
      this.showSuccessToast('Theme saved successfully');
      
      // If this is the currently active theme, apply the changes to the session
      await this.applyIfCurrentTheme();
    } catch (error) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      saveBtn.textContent = originalText;
      saveBtn.disabled = false;
      
      if (error.name === 'AbortError') {
        console.error('Save theme request timed out after 5 seconds');
        this.showErrorToast('Request timed out. Check your connection.');
      } else {
        console.error('Error saving theme:', error);
        this.showErrorToast('Error saving theme: ' + error.message);
      }
      this.lastSaveError = true;
    }
  }
  
  async applyIfCurrentTheme() {
    try {
      // Fetch the current active theme
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      const response = await fetch('/api/settings/theme', {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const activeTheme = await this.parseResponse(response);
      
      if (response.ok && activeTheme.id === this.currentTheme) {
        // The saved theme is the currently active theme, apply the changes
        await this.loadAndApplyTheme();
      }
    } catch (error) {
      // Silent fail - this is a bonus feature, don't interrupt the save flow
      console.log('Could not check/apply current theme:', error);
    }
  }
  
  showCopyModal() {
    // Check database connection
    if (!window.header || !window.header.dbConnected) {
      this.showErrorToast('Cannot copy theme: Database not connected');
      return;
    }
    
    const modal = document.getElementById('copy-theme-modal');
    const nameInput = document.getElementById('copy-theme-name');
    const errorDiv = document.getElementById('copy-theme-error');
    
    nameInput.value = this.currentThemeData ? `${this.currentThemeData.name} Copy` : '';
    errorDiv.style.display = 'none';
    modal.style.display = 'flex';
    nameInput.focus();
  }
  
  hideCopyModal() {
    document.getElementById('copy-theme-modal').style.display = 'none';
  }
  
  async confirmCopyTheme() {
    const nameInput = document.getElementById('copy-theme-name');
    const errorDiv = document.getElementById('copy-theme-error');
    const confirmBtn = document.getElementById('copy-theme-confirm');
    const newName = nameInput.value.trim();
    
    if (!newName) {
      errorDiv.textContent = 'Theme name is required';
      errorDiv.style.display = 'block';
      return;
    }
    
    const originalText = confirmBtn.textContent;
    
    // Add loading state with delay
    const loadingTimeout = setTimeout(() => {
      confirmBtn.textContent = 'Copying...';
      confirmBtn.disabled = true;
    }, 500);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch('/api/themes/copy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_theme_id: this.currentTheme,
          new_name: newName
        }),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const newTheme = await this.parseResponse(response);
      
      if (!response.ok || (newTheme.success === false)) {
        throw new Error(newTheme.message || newTheme.error || 'Failed to copy theme');
      }
      
      // Add to themes list
      this.themes[newTheme.id] = newTheme;
      
      // Add to select
      const option = document.createElement('option');
      option.value = newTheme.id;
      option.textContent = newTheme.name;
      this.themeSelect.appendChild(option);
      
      // Select the new theme
      this.themeSelect.value = newTheme.id;
      await this.onThemeChange();
      
      clearTimeout(loadingTimeout);
      confirmBtn.textContent = originalText;
      confirmBtn.disabled = false;
      
      this.hideCopyModal();
      this.showSuccessToast('Theme copied successfully');
    } catch (error) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      confirmBtn.textContent = originalText;
      confirmBtn.disabled = false;
      
      if (error.name === 'AbortError') {
        console.error('Copy theme request timed out after 5 seconds');
        errorDiv.textContent = 'Request timed out. Check your connection.';
      } else {
        console.error('Error copying theme:', error);
        errorDiv.textContent = error.message;
      }
      errorDiv.style.display = 'block';
    }
  }
  
  showRenameModal() {
    if (!this.currentThemeData) {
      this.showErrorToast('No theme selected');
      return;
    }
    
    if (this.currentThemeData.system_theme) {
      this.showErrorToast('Cannot rename system themes');
      return;
    }
    
    // Check database connection
    if (!window.header || !window.header.dbConnected) {
      this.showErrorToast('Cannot rename theme: Database not connected');
      return;
    }
    
    const modal = document.getElementById('rename-theme-modal');
    const nameInput = document.getElementById('rename-theme-name');
    const errorDiv = document.getElementById('rename-theme-error');
    
    nameInput.value = this.currentThemeData.name;
    errorDiv.style.display = 'none';
    modal.style.display = 'flex';
    nameInput.focus();
    nameInput.select();
  }
  
  hideRenameModal() {
    document.getElementById('rename-theme-modal').style.display = 'none';
  }
  
  async confirmRenameTheme() {
    const nameInput = document.getElementById('rename-theme-name');
    const errorDiv = document.getElementById('rename-theme-error');
    const confirmBtn = document.getElementById('rename-theme-confirm');
    const newName = nameInput.value.trim();
    
    if (!newName) {
      errorDiv.textContent = 'Theme name is required';
      errorDiv.style.display = 'block';
      return;
    }
    
    if (newName === this.currentThemeData.name) {
      this.hideRenameModal();
      return;
    }
    
    const originalText = confirmBtn.textContent;
    
    // Add loading state with delay
    const loadingTimeout = setTimeout(() => {
      confirmBtn.textContent = 'Renaming...';
      confirmBtn.disabled = true;
    }, 500);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/themes/${this.currentTheme}/rename`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const updatedTheme = await this.parseResponse(response);
      
      if (!response.ok || (updatedTheme.success === false)) {
        throw new Error(updatedTheme.message || updatedTheme.error || 'Failed to rename theme');
      }
      
      // Update themes list
      this.themes[this.currentTheme] = updatedTheme;
      this.currentThemeData = updatedTheme;
      
      // Update select option
      const option = this.themeSelect.querySelector(`option[value="${this.currentTheme}"]`);
      if (option) {
        option.textContent = updatedTheme.name;
      }
      
      clearTimeout(loadingTimeout);
      confirmBtn.textContent = originalText;
      confirmBtn.disabled = false;
      
      this.hideRenameModal();
      this.showSuccessToast('Theme renamed successfully');
    } catch (error) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      confirmBtn.textContent = originalText;
      confirmBtn.disabled = false;
      
      if (error.name === 'AbortError') {
        console.error('Rename theme request timed out after 5 seconds');
        errorDiv.textContent = 'Request timed out. Check your connection.';
      } else {
        console.error('Error renaming theme:', error);
        errorDiv.textContent = error.message;
      }
      errorDiv.style.display = 'block';
    }
  }
  
  showImportWarning(message) {
    const modal = document.getElementById('import-warning-modal');
    const messageDiv = document.getElementById('import-warning-message');
    const closeBtn = document.getElementById('import-warning-close');
    const okBtn = document.getElementById('import-warning-ok');
    const header = modal.querySelector('.modal-header');
    
    messageDiv.textContent = message;
    header.classList.add('error');
    modal.style.display = 'flex';
    
    const close = () => {
      modal.style.display = 'none';
      header.classList.remove('error');
    };
    closeBtn.onclick = close;
    okBtn.onclick = close;
  }
  
  importTheme() {
    document.getElementById('import-theme-input').click();
  }
  
  async handleThemeImport(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    try {
      const text = await file.text();
      const themeData = JSON.parse(text);
      
      // Validate theme data
      if (!themeData.name || !themeData.settings) {
        throw new Error('Invalid theme file format');
      }
      
      // Check database connection
      if (!window.header || !window.header.dbConnected) {
        this.showErrorToast('Cannot import theme: Database not connected');
        return;
      }
      
      // Import via API
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      const response = await fetch('/api/themes/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(themeData),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const newTheme = await this.parseResponse(response);
      
      if (!response.ok || (newTheme.success === false)) {
        const errorMessage = newTheme.message || newTheme.error || 'Failed to import theme';
        console.log('Import error:', errorMessage);
        this.showImportWarning(errorMessage);
        return;
      }
      
      // Add to themes list
      this.themes[newTheme.id] = newTheme;
      
      // Add to select
      const option = document.createElement('option');
      option.value = newTheme.id;
      option.textContent = newTheme.name;
      this.themeSelect.appendChild(option);
      
      // Select the new theme
      this.themeSelect.value = newTheme.id;
      await this.onThemeChange();
      
      this.showSuccessToast('Theme imported successfully');
    } catch (error) {
      if (error.name === 'AbortError') {
        console.error('Import theme request timed out after 5 seconds');
        this.showImportWarning('Request timed out. Check your connection.');
      } else {
        console.error('Error importing theme:', error);
        this.showImportWarning(error.message || 'Failed to import theme');
      }
    }
    
    // Reset file input
    event.target.value = '';
  }
  
  async exportTheme() {
    if (!this.currentTheme) {
      this.showErrorToast('No theme selected');
      return;
    }
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(`/api/themes/${this.currentTheme}/export`, {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const themeData = await this.parseResponse(response);
      
      if (!response.ok || (themeData.success === false)) {
        throw new Error(themeData.message || themeData.error || 'Failed to export theme');
      }
      
      // Create download link
      const blob = new Blob([JSON.stringify(themeData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${themeData.name.replace(/\s+/g, '_')}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      this.showSuccessToast('Theme exported successfully');
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        console.error('Export theme request timed out after 5 seconds');
        this.showErrorToast('Request timed out. Check your connection.');
      } else {
        console.error('Error exporting theme:', error);
        this.showErrorToast('Error exporting theme: ' + error.message);
      }
    }
  }
  
  uploadBackground() {
    document.getElementById('bg-image-input').click();
  }
  
  async handleBackgroundUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Check database connection
    if (!window.header || !window.header.dbConnected) {
      this.showErrorToast('Cannot upload background: Database not connected');
      event.target.value = '';
      return;
    }
    
    const uploadBtn = document.getElementById('upload-bg-btn');
    const originalText = uploadBtn.textContent;
    
    // Add loading state with delay
    const loadingTimeout = setTimeout(() => {
      uploadBtn.textContent = 'Uploading...';
      uploadBtn.disabled = true;
    }, 500);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const formData = new FormData();
      formData.append('image', file);
      
      const response = await fetch('/api/themes/upload-image', {
        method: 'POST',
        body: formData,
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      const result = await this.parseResponse(response);
      
      if (!response.ok || (result.success === false)) {
        throw new Error(result.message || result.error || 'Failed to upload image');
      }
      
      // Reload background images list
      await this.loadBackgroundImages();
      
      // Update the selector to the new image
      this.backgroundSelect.value = result.filename;
      
      // Update current theme data
      if (this.currentThemeData) {
        this.currentThemeData.background_image = result.filename;
      }
      
      // Apply the background change immediately
      this.applyThemePreview();
      
      clearTimeout(loadingTimeout);
      uploadBtn.textContent = originalText;
      uploadBtn.disabled = false;
      
      this.showSuccessToast('Background image uploaded successfully');
    } catch (error) {
      clearTimeout(timeoutId);
      clearTimeout(loadingTimeout);
      
      uploadBtn.textContent = originalText;
      uploadBtn.disabled = false;
      
      let errorMessage = 'Failed to upload background image';
      if (error.name === 'AbortError') {
        console.error('Upload background request timed out after 5 seconds');
        errorMessage = 'Request timed out. Check your connection.';
      } else {
        console.error('Error uploading background:', error);
        errorMessage = error.message;
      }
      
      // Show error modal instead of toast
      this.showImportWarning(errorMessage);
    }
    
    // Reset file input
    event.target.value = '';
  }
  
  async downloadBackground() {
    const bgValue = this.backgroundSelect.value;
    
    if (!bgValue || bgValue === 'none') {
      this.showErrorToast('No background image selected');
      return;
    }
    
    try {
      const url = `/images/backgrounds/${bgValue}`;
      
      // Create download link
      const a = document.createElement('a');
      a.href = url;
      a.download = bgValue;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      
      this.showSuccessToast('Background image downloaded');
    } catch (error) {
      console.error('Error downloading background:', error);
      this.showErrorToast('Error downloading background: ' + error.message);
    }
  }
  
  showStatus(message, type) {
    this.statusDiv.textContent = message;
    this.statusDiv.className = `settings-status ${type}`;
    this.statusDiv.style.display = 'block';
    
    setTimeout(() => {
      this.statusDiv.style.display = 'none';
    }, 5000);
  }
}

// Initialize when DOM is ready
// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const themeBuilder = new ThemeBuilder();
  themeBuilder.init();
});
