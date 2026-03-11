// Profile page functionality

class ProfileManager {
  constructor() {
    this.profileForm = null;
    this.passwordForm = null;
    this.currentUser = null;
  }

  async init() {
    // Wait for header to load
    await this.waitForHeader();

    // Get form elements
    this.profileForm = document.getElementById('profile-form');
    this.passwordForm = document.getElementById('password-form');

    // Load current user data
    await this.loadUserData();

    // Setup form handlers
    this.setupFormHandlers();
  }

  async waitForHeader() {
    // Wait for header to initialize
    while (!window.header) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }

  async loadUserData() {
    try {
      const response = await fetch('/api/auth/me');
      
      if (!response.ok) {
        this.showMessage('profile-status', 'Failed to load user data', 'error');
        return;
      }

      const data = await response.json();
      if (data.user) {
        this.currentUser = data.user;
        this.populateForm();
      } else {
        this.showMessage('profile-status', 'User not logged in', 'error');
        // Redirect to login after 2 seconds
        setTimeout(() => {
          window.location.href = '/login.html';
        }, 2000);
      }
    } catch (error) {
      console.error('Error loading user data:', error);
      this.showMessage('profile-status', 'Error loading user data', 'error');
    }
  }

  populateForm() {
    if (!this.currentUser) return;

    // Populate form fields
    document.getElementById('display-name').value = this.currentUser.display_name || '';
    document.getElementById('username').value = this.currentUser.username || '';
    document.getElementById('email').value = this.currentUser.email || '';

    // Disable email if OAuth user
    if (this.currentUser.oauth_provider) {
      const emailInput = document.getElementById('email');
      emailInput.disabled = true;
      const emailHelp = emailInput.previousElementSibling;
      if (emailHelp && emailHelp.classList.contains('field-help')) {
        emailHelp.textContent = 'Email cannot be changed for OAuth accounts.';
      }

      // Also disable password form for OAuth users
      const passwordSection = this.passwordForm.closest('.profile-section');
      if (passwordSection) {
        const passwordHelp = passwordSection.querySelector('h3');
        if (passwordHelp) {
          passwordHelp.innerHTML = 'Change Password <span style="color: var(--text-muted); font-size: 14px; font-weight: normal;">(Not available for OAuth accounts)</span>';
        }
        this.passwordForm.querySelectorAll('input').forEach(input => {
          input.disabled = true;
        });
        this.passwordForm.querySelector('button').disabled = true;
      }
    }
  }

  setupFormHandlers() {
    // Profile form submission
    this.profileForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.handleProfileUpdate();
    });

    // Password form submission
    this.passwordForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.handlePasswordChange();
    });
  }

  async handleProfileUpdate() {
    const saveBtn = document.getElementById('save-profile-btn');
    const statusEl = document.getElementById('profile-status');

    // Get form values
    const displayName = document.getElementById('display-name').value.trim();
    const username = document.getElementById('username').value.trim();
    const email = document.getElementById('email').value.trim();

    // Basic validation
    if (!username) {
      this.showMessage('profile-status', 'Username is required', 'error');
      return;
    }

    if (!email) {
      this.showMessage('profile-status', 'Email is required', 'error');
      return;
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      this.showMessage('profile-status', 'Please enter a valid email address', 'error');
      return;
    }

    // Disable button during submission
    saveBtn.disabled = true;
    this.showMessage('profile-status', 'Saving...', 'info');

    try {
      const response = await fetch('/api/auth/profile', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          display_name: displayName,
          username: username,
          email: email
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        this.showMessage('profile-status', 'Profile updated successfully', 'success');
        
        // Update cached user data
        sessionStorage.removeItem('currentUser');
        
        // Reload user data and update header
        await this.loadUserData();
        if (window.header) {
          await window.header.loadCurrentUser();
        }
      } else {
        this.showMessage('profile-status', data.error || 'Failed to update profile', 'error');
      }
    } catch (error) {
      console.error('Error updating profile:', error);
      this.showMessage('profile-status', 'Error updating profile', 'error');
    } finally {
      saveBtn.disabled = false;
    }
  }

  async handlePasswordChange() {
    const changeBtn = document.getElementById('change-password-btn');
    const statusEl = document.getElementById('password-status');

    // Get form values
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-password').value;

    // Validation
    if (!currentPassword) {
      this.showMessage('password-status', 'Current password is required', 'error');
      return;
    }

    if (!newPassword) {
      this.showMessage('password-status', 'New password is required', 'error');
      return;
    }

    if (newPassword.length < 8) {
      this.showMessage('password-status', 'Password must be at least 8 characters', 'error');
      return;
    }

    if (newPassword !== confirmPassword) {
      this.showMessage('password-status', 'Passwords do not match', 'error');
      return;
    }

    // Disable button during submission
    changeBtn.disabled = true;
    this.showMessage('password-status', 'Changing password...', 'info');

    try {
      const response = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        this.showMessage('password-status', 'Password changed successfully', 'success');
        
        // Clear form
        this.passwordForm.reset();
      } else {
        this.showMessage('password-status', data.error || 'Failed to change password', 'error');
      }
    } catch (error) {
      console.error('Error changing password:', error);
      this.showMessage('password-status', 'Error changing password', 'error');
    } finally {
      changeBtn.disabled = false;
    }
  }

  showMessage(elementId, message, type) {
    const statusEl = document.getElementById(elementId);
    if (!statusEl) return;

    statusEl.textContent = message;
    statusEl.className = `status-message ${type} show`;

    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
      setTimeout(() => {
        statusEl.classList.remove('show');
      }, 5000);
    }
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
  const profileManager = new ProfileManager();
  await profileManager.init();
});
