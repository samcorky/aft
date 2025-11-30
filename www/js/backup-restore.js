// Backup & Restore page functionality
class BackupRestore {
  constructor() {
    this.statusElement = document.getElementById('settings-status');
    
    // Manual backup/restore elements
    this.backupBtn = document.getElementById('backup-btn');
    this.restoreBtn = document.getElementById('restore-btn');
    this.restoreFileInput = document.getElementById('restore-file-input');
    this.backupStatus = document.getElementById('backup-status');
    
    // Automatic backup settings elements
    this.backupForm = document.getElementById('backupConfigForm');
    this.backupEnabled = document.getElementById('backupEnabled');
    this.frequencyValue = document.getElementById('frequencyValue');
    this.frequencyUnit = document.getElementById('frequencyUnit');
    this.startTime = document.getElementById('startTime');
    this.retentionCount = document.getElementById('retentionCount');
    this.schedulerStatus = document.getElementById('schedulerStatus');
    this.currentFrequency = document.getElementById('currentFrequency');
    this.currentRetention = document.getElementById('currentRetention');
    this.latestBackup = document.getElementById('latestBackup');
    this.backupWindowStatus = document.getElementById('backupWindowStatus');
    this.saveBackupButton = document.getElementById('saveBackupButton');
    this.resetBackupButton = document.getElementById('resetBackupButton');
    
    // Available backups elements
    this.backupsLoading = document.getElementById('backupsLoading');
    this.backupsEmpty = document.getElementById('backupsEmpty');
    this.backupsList = document.getElementById('backupsList');
    this.restoreStatus = document.getElementById('restoreStatus');
  }

  async init() {
    await this.loadBackupConfig();
    await this.loadBackupStatus();
    await this.loadAvailableBackups();
    this.attachEventListeners();
  }

  attachEventListeners() {
    // Manual backup button
    this.backupBtn.addEventListener('click', () => {
      this.downloadBackup();
    });

    // Restore button opens file picker
    this.restoreBtn.addEventListener('click', () => {
      this.restoreFileInput.click();
    });

    // File input change triggers restore
    this.restoreFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        this.restoreFromFile(e.target.files[0]);
      }
    });

    // Automatic backup settings event listeners
    if (this.backupForm) {
      this.backupForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.saveBackupConfig();
      });
    }

    if (this.resetBackupButton) {
      this.resetBackupButton.addEventListener('click', () => {
        this.loadBackupConfig();
      });
    }

    // Backup enabled toggle
    if (this.backupEnabled) {
      this.backupEnabled.addEventListener('change', async (e) => {
        // Auto-save when toggle changes
        await this.saveBackupConfig();
      });
    }
  }

  async downloadBackup() {
    try {
      this.backupStatus.textContent = 'Creating backup...';
      this.backupStatus.className = 'backup-status info';
      this.backupBtn.disabled = true;

      const response = await fetch('/api/database/backup');
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.message || 'Failed to create backup');
      }

      // Get filename from Content-Disposition header or create default
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = 'aft_backup.sql';
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }

      // Download the file
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      this.backupStatus.textContent = 'Backup downloaded successfully!';
      this.backupStatus.className = 'backup-status success';
      
      setTimeout(() => {
        this.backupStatus.textContent = '';
        this.backupStatus.className = 'backup-status';
      }, 5000);

    } catch (error) {
      console.error('Error creating backup:', error);
      this.backupStatus.textContent = `Error: ${error.message}`;
      this.backupStatus.className = 'backup-status error';
    } finally {
      this.backupBtn.disabled = false;
    }
  }

  async restoreFromFile(file) {
    try {
      // Confirm restore action
      const confirmed = confirm(
        `Are you sure you want to restore from "${file.name}"?\n\n` +
        'This will replace all current data with the backup. This action cannot be undone.'
      );

      if (!confirmed) {
        this.restoreFileInput.value = '';
        return;
      }

      this.backupStatus.textContent = 'Restoring database... This may take a minute.';
      this.backupStatus.className = 'backup-status info';
      this.restoreBtn.disabled = true;

      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/database/restore', {
        method: 'POST',
        body: formData
      });

      // Check if response is JSON
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('Server returned an invalid response. The operation may have timed out. Please check if the restore completed successfully by refreshing the page.');
      }

      const data = await response.json();

      if (data.success) {
        this.backupStatus.textContent = data.message;
        this.backupStatus.className = 'backup-status success';
        
        // Reload page after successful restore
        setTimeout(() => {
          alert('Database restored successfully. The page will now reload.');
          window.location.reload();
        }, 2000);
      } else {
        this.backupStatus.textContent = `Error: ${data.message}`;
        this.backupStatus.className = 'backup-status error';
        this.restoreBtn.disabled = false;
      }

    } catch (error) {
      console.error('Error restoring database:', error);
      this.backupStatus.textContent = `Error: ${error.message}`;
      this.backupStatus.className = 'backup-status error';
      this.restoreBtn.disabled = false;
    } finally {
      this.restoreFileInput.value = '';
    }
  }

  async loadBackupConfig() {
    try {
      const response = await fetch('/api/settings/backup/config');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      if (data.success && data.config) {
        const config = data.config;
        this.backupEnabled.checked = config.enabled || false;
        this.frequencyValue.value = config.frequency_value || 24;
        this.frequencyUnit.value = config.frequency_unit || 'hours';
        this.startTime.value = config.start_time || '02:00';
        this.retentionCount.value = config.retention_count || 7;
      }
    } catch (err) {
      console.error('Error loading backup config:', err);
      this.showStatus('Error loading backup settings: ' + err.message, 'error');
    }
  }

  async saveBackupConfig() {
    try {
      this.saveBackupButton.disabled = true;
      this.showStatus('Saving backup settings...', 'info');

      const config = {
        enabled: this.backupEnabled.checked,
        frequency_value: parseInt(this.frequencyValue.value, 10),
        frequency_unit: this.frequencyUnit.value,
        start_time: this.startTime.value,
        retention_count: parseInt(this.retentionCount.value, 10)
      };

      const response = await fetch('/api/settings/backup/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
      });

      const data = await response.json();

      if (!response.ok) {
        const errorMessage = data.message || `HTTP error! status: ${response.status}`;
        throw new Error(errorMessage);
      }

      if (data.success) {
        this.showStatus('Backup settings saved successfully', 'success');
        
        // Reload status to show updated info
        await this.loadBackupStatus();

        // Clear status after 3 seconds
        setTimeout(() => {
          this.statusElement.textContent = '';
          this.statusElement.className = 'settings-status';
        }, 3000);
      } else {
        this.showStatus('Error: ' + data.message, 'error');
      }
    } catch (err) {
      this.showStatus('Error: ' + err.message, 'error');
    } finally {
      this.saveBackupButton.disabled = false;
    }
  }

  async loadBackupStatus() {
    try {
      const response = await fetch('/api/settings/backup/status');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      if (data.success && data.status) {
        const status = data.status;
        
        // Update status badge - use healthy/unhealthy instead of running/stopped
        if (status.running) {
          this.schedulerStatus.textContent = 'Healthy';
          this.schedulerStatus.className = 'status-badge status-healthy';
        } else {
          this.schedulerStatus.textContent = 'Unhealthy';
          this.schedulerStatus.className = 'status-badge status-unhealthy';
        }
        
        // Update frequency display
        this.currentFrequency.textContent = status.enabled 
          ? status.frequency 
          : 'Disabled';
        
        // Update retention display
        this.currentRetention.textContent = `${status.retention_count} backup${status.retention_count !== 1 ? 's' : ''}`;
        
        // Update latest backup info
        if (status.latest_backup_date) {
          const backupDate = new Date(status.latest_backup_date);
          const now = new Date();
          const diffMs = now - backupDate;
          const diffMins = Math.floor(diffMs / 60000);
          const diffHours = Math.floor(diffMs / 3600000);
          const diffDays = Math.floor(diffMs / 86400000);
          
          let timeAgo;
          if (diffMins < 60) {
            timeAgo = `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
          } else if (diffHours < 24) {
            timeAgo = `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
          } else {
            timeAgo = `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
          }
          
          this.latestBackup.textContent = timeAgo;
        } else {
          this.latestBackup.textContent = 'No backups found';
        }
        
        // Update backup window status
        if (status.enabled) {
          if (status.latest_backup_date && status.backup_within_window) {
            this.backupWindowStatus.innerHTML = '<span class="status-badge status-healthy">Current</span>';
          } else {
            // Overdue if enabled but either no backup exists or backup is outside window
            this.backupWindowStatus.innerHTML = '<span class="status-badge status-unhealthy">Overdue</span>';
          }
        } else {
          this.backupWindowStatus.textContent = 'Disabled';
        }
        
        // Display permission error if present
        const errorDiv = document.getElementById('backupPermissionError');
        if (errorDiv) {
          if (status.permission_error) {
            errorDiv.textContent = status.permission_error;
            errorDiv.style.display = 'block';
          } else {
            errorDiv.style.display = 'none';
          }
        }
      }
    } catch (err) {
      console.error('Error loading backup status:', err);
      this.schedulerStatus.textContent = 'Error';
      this.schedulerStatus.className = 'status-badge';
    }
  }

  async loadAvailableBackups() {
    try {
      this.backupsLoading.style.display = 'block';
      this.backupsEmpty.style.display = 'none';
      this.backupsList.style.display = 'none';
      
      const response = await fetch('/api/database/backups/list');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      if (data.success && data.backups) {
        this.backupsLoading.style.display = 'none';
        
        if (data.backups.length === 0) {
          this.backupsEmpty.style.display = 'block';
        } else {
          this.backupsList.style.display = 'flex';
          this.renderBackupsList(data.backups);
        }
      }
    } catch (err) {
      console.error('Error loading available backups:', err);
      this.backupsLoading.textContent = 'Error loading backups';
    }
  }

  renderBackupsList(backups) {
    this.backupsList.innerHTML = '';
    
    backups.forEach(backup => {
      const backupItem = document.createElement('div');
      backupItem.className = 'backup-item';
      
      // Format date
      const date = new Date(backup.created);
      const formattedDate = date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
      
      // Format size
      const size = backup.size;
      let formattedSize;
      if (size < 1024) {
        formattedSize = `${size} B`;
      } else if (size < 1024 * 1024) {
        formattedSize = `${(size / 1024).toFixed(2)} KB`;
      } else {
        formattedSize = `${(size / (1024 * 1024)).toFixed(2)} MB`;
      }
      
      backupItem.innerHTML = `
        <div class="backup-info">
          <div class="backup-filename">${backup.filename}</div>
          <div class="backup-date">${formattedDate}</div>
        </div>
        <div class="backup-size">${formattedSize}</div>
        <button class="backup-restore-btn" data-filename="${backup.filename}">
          Restore
        </button>
      `;
      
      const restoreBtn = backupItem.querySelector('.backup-restore-btn');
      restoreBtn.addEventListener('click', () => {
        this.restoreFromAutoBackup(backup.filename);
      });
      
      this.backupsList.appendChild(backupItem);
    });
  }

  async restoreFromAutoBackup(filename) {
    // Show confirmation modal
    this.showRestoreConfirmModal(filename);
  }

  showRestoreConfirmModal(filename) {
    const modal = document.getElementById('restoreModal');
    const titleElement = document.getElementById('restoreModalTitle');
    const messageElement = document.getElementById('restoreModalMessage');
    const confirmBtn = document.getElementById('restoreModalConfirmBtn');
    const cancelBtn = document.getElementById('restoreModalCancelBtn');

    // Set confirmation content
    titleElement.textContent = 'Confirm Restore';
    titleElement.style.color = 'var(--warning-color, #f59e0b)';
    messageElement.innerHTML = `Are you sure you want to restore from <strong>"${filename}"</strong>?<br><br>This will replace all current data with the backup. This action cannot be undone.`;
    
    confirmBtn.textContent = 'Restore';
    confirmBtn.style.display = 'inline-block';
    cancelBtn.style.display = 'inline-block';

    modal.classList.add('active');

    // Handle cancel
    const handleCancel = () => {
      modal.classList.remove('active');
      confirmBtn.removeEventListener('click', handleConfirm);
      cancelBtn.removeEventListener('click', handleCancel);
    };

    // Handle confirm
    const handleConfirm = async () => {
      // Remove event listeners
      confirmBtn.removeEventListener('click', handleConfirm);
      cancelBtn.removeEventListener('click', handleCancel);
      
      // Update modal to show progress
      titleElement.textContent = 'Restoring Database';
      titleElement.style.color = 'var(--primary-color)';
      messageElement.textContent = 'Restoring database... This may take a minute.';
      confirmBtn.style.display = 'none';
      cancelBtn.style.display = 'none';

      // Disable all restore buttons
      const restoreButtons = document.querySelectorAll('.backup-restore-btn');
      restoreButtons.forEach(btn => btn.disabled = true);

      try {
        const response = await fetch(`/api/database/backups/restore/${filename}`, {
          method: 'POST'
        });

        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('Server returned an invalid response. The operation may have timed out. Please check if the restore completed successfully by refreshing the page.');
        }

        const data = await response.json();

        if (data.success) {
          // Show success in modal
          this.showRestoreResultInModal('Restore Successful', data.message, true);
        } else {
          // Show error in modal and re-enable buttons
          this.showRestoreResultInModal('Restore Failed', data.message, false);
          restoreButtons.forEach(btn => btn.disabled = false);
        }

      } catch (error) {
        console.error('Error restoring from automatic backup:', error);
        
        // Show error in modal
        this.showRestoreResultInModal('Restore Failed', error.message, false);
        
        // Re-enable buttons on error
        restoreButtons.forEach(btn => btn.disabled = false);
      }
    };

    confirmBtn.addEventListener('click', handleConfirm);
    cancelBtn.addEventListener('click', handleCancel);
  }

  showRestoreResultInModal(title, message, success) {
    const modal = document.getElementById('restoreModal');
    const titleElement = document.getElementById('restoreModalTitle');
    const messageElement = document.getElementById('restoreModalMessage');
    const confirmBtn = document.getElementById('restoreModalConfirmBtn');
    const cancelBtn = document.getElementById('restoreModalCancelBtn');

    titleElement.textContent = title;
    titleElement.style.color = success ? 'var(--success-color)' : 'var(--error-color)';
    messageElement.textContent = message;

    confirmBtn.textContent = 'OK';
    confirmBtn.style.display = 'inline-block';
    cancelBtn.style.display = 'none';

    // OK button handler
    const handleOk = () => {
      modal.classList.remove('active');
      confirmBtn.removeEventListener('click', handleOk);
      
      // Reload page after successful restore
      if (success) {
        window.location.reload();
      }
    };

    confirmBtn.addEventListener('click', handleOk);
  }

  showStatus(message, type = 'info') {
    this.statusElement.textContent = message;
    this.statusElement.className = `settings-status ${type}`;
  }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
  const backupRestore = new BackupRestore();
  backupRestore.init();
});
