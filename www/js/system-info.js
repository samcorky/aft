// System Info page functionality

const CONFIRMATION_TEXT = "Yes I am sure I want to delete all of my data!";

class SystemInfo {
  constructor() {
    this.modal = null;
    this.deleteBtn = null;
    this.confirmInput = null;
    this.errorMessage = null;
    this.backupToggle = null;
    this.housekeepingToggle = null;
    this.cardSchedulerToggle = null;
  }

  async init() {
    // Get element references
    this.modal = document.getElementById('delete-modal');
    this.deleteBtn = document.getElementById('delete-db-btn');
    this.confirmInput = document.getElementById('delete-confirmation-input');
    this.errorMessage = document.getElementById('delete-error');
    this.backupToggle = document.getElementById('backupToggle');
    this.housekeepingToggle = document.getElementById('housekeepingToggle');
    this.cardSchedulerToggle = document.getElementById('cardSchedulerToggle');
    
    // Set up event listeners
    this.setupEventListeners();
    
    // Load data
    await this.loadSystemInfo();
  }

  setupEventListeners() {
    // Delete button opens modal
    this.deleteBtn.addEventListener('click', () => {
      this.openDeleteModal();
    });

    // Cancel button closes modal
    document.getElementById('cancel-delete-btn').addEventListener('click', () => {
      this.closeDeleteModal();
    });

    // Confirm delete button
    document.getElementById('confirm-delete-btn').addEventListener('click', () => {
      this.confirmDelete();
    });

    // Clear error when typing
    this.confirmInput.addEventListener('input', () => {
      this.errorMessage.textContent = '';
    });

    // Close modal on background click
    this.modal.addEventListener('click', (e) => {
      if (e.target === this.modal) {
        this.closeDeleteModal();
      }
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal.classList.contains('active')) {
        this.closeDeleteModal();
      }
    });

    // Backup toggle
    if (this.backupToggle) {
      this.backupToggle.addEventListener('change', async (e) => {
        await this.toggleBackup(e.target.checked);
      });
    }

    // Housekeeping toggle
    if (this.housekeepingToggle) {
      this.housekeepingToggle.addEventListener('change', async (e) => {
        await this.toggleHousekeeping(e.target.checked);
      });
    }

    // Card scheduler toggle
    if (this.cardSchedulerToggle) {
      this.cardSchedulerToggle.addEventListener('change', async (e) => {
        await this.toggleCardScheduler(e.target.checked);
      });
    }
  }

  async loadSystemInfo() {
    try {
      // Fetch all data in parallel
      const [testResponse, versionResponse, statsResponse, backupStatusResponse, housekeepingStatusResponse, cardSchedulerStatusResponse, schedulerHealthResponse] = await Promise.all([
        fetch('/api/test'),
        fetch('/api/version'),
        fetch('/api/stats'),
        fetch('/api/settings/backup/status'),
        fetch('/api/settings/housekeeping/status'),
        fetch('/api/settings/card-scheduler/status'),
        fetch('/api/scheduler/health')
      ]);

      const testData = await testResponse.json();
      const versionData = await versionResponse.json();
      const statsData = await statsResponse.json();
      const backupStatusData = await backupStatusResponse.json();
      const housekeepingStatusData = await housekeepingStatusResponse.json();
      const cardSchedulerStatusData = await cardSchedulerStatusResponse.json();
      const schedulerHealthData = await schedulerHealthResponse.json();

      // Update connection status
      const connectionElement = document.getElementById('db-connection');
      if (testData.success) {
        connectionElement.innerHTML = `
          <span class="status-icon success"></span>
          <span>Connected</span>
        `;
      } else {
        connectionElement.innerHTML = `
          <span class="status-icon error"></span>
          <span>Error</span>
        `;
      }

      // Update version info
      if (versionData.success) {
        document.getElementById('app-version').textContent = `v${versionData.app_version}`;
        document.getElementById('db-version').textContent = versionData.db_version;
      }

      // Update statistics
      if (statsData.success) {
        document.getElementById('boards-count').textContent = statsData.boards_count;
        document.getElementById('columns-count').textContent = statsData.columns_count;
        document.getElementById('cards-count').textContent = statsData.cards_count;
        document.getElementById('cards-archived-count').textContent = statsData.cards_archived_count || 0;
        document.getElementById('checklist-items-total').textContent = statsData.checklist_items_total || 0;
        document.getElementById('checklist-items-checked').textContent = statsData.checklist_items_checked || 0;
        document.getElementById('checklist-items-unchecked').textContent = statsData.checklist_items_unchecked || 0;
      }

      // Update backup module status with scheduler health
      this.updateBackupModuleStatus(backupStatusData, schedulerHealthData.backup_scheduler);
      
      // Update housekeeping module status with scheduler health
      this.updateHousekeepingModuleStatus(housekeepingStatusData, schedulerHealthData.housekeeping_scheduler);
      
      // Update card scheduler status
      this.updateCardSchedulerStatus(cardSchedulerStatusData, schedulerHealthData.card_scheduler);
      
    } catch (error) {
      console.error('Error loading system info:', error);
      const connectionElement = document.getElementById('db-connection');
      connectionElement.innerHTML = `
        <span class="status-icon error"></span>
        <span>Error</span>
      `;
    }
  }
  
  updateBackupModuleStatus(backupStatusData, schedulerHealth) {
    if (backupStatusData.success && backupStatusData.status) {
      const status = backupStatusData.status;
      const healthBadge = document.getElementById('backup-module-health');
      
      if (healthBadge) {
        // Update health status based on scheduler health
        const isHealthy = schedulerHealth && schedulerHealth.running && schedulerHealth.thread_alive;
        
        if (isHealthy) {
          healthBadge.textContent = 'Healthy';
          healthBadge.className = 'status-badge status-healthy';
        } else {
          healthBadge.textContent = 'Unhealthy';
          healthBadge.className = 'status-badge status-unhealthy';
        }
      }
      
      // Update toggle state
      if (this.backupToggle) {
        this.backupToggle.checked = status.enabled;
        // Show toggle wrapper after data loads
        document.getElementById('backup-toggle-wrapper').style.display = 'block';
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
      
      // Update scheduler details
      if (schedulerHealth && !schedulerHealth.error) {
        document.getElementById('backup-scheduler-details').style.display = 'block';
        
        // Populate tooltip with full health data
        const tooltip = document.getElementById('backup-tooltip');
        tooltip.textContent = 'Full Health Data:\n' + JSON.stringify(schedulerHealth, null, 2);
        
        // Thread status
        const threadStatus = schedulerHealth.thread_alive ? '✓ Running' : '✗ Stopped';
        document.getElementById('backup-thread-status').textContent = threadStatus;
        document.getElementById('backup-thread-status').style.color = schedulerHealth.thread_alive ? '#27ae60' : '#e74c3c';
        
        // Last backup
        if (schedulerHealth.last_backup) {
          const lastBackup = new Date(schedulerHealth.last_backup);
          document.getElementById('backup-last-run').textContent = this.formatDateTime(lastBackup);
        } else {
          document.getElementById('backup-last-run').textContent = 'Never';
        }
        
        // Heartbeat age
        if (schedulerHealth.lock_file_age_seconds !== undefined) {
          const age = Math.round(schedulerHealth.lock_file_age_seconds);
          document.getElementById('backup-heartbeat').textContent = `${age}s ago`;
          document.getElementById('backup-heartbeat').style.color = age < 120 ? '#27ae60' : '#e67e22';
        } else {
          document.getElementById('backup-heartbeat').textContent = 'Unknown';
        }
        
        // Container ID
        document.getElementById('backup-container').textContent = schedulerHealth.lock_container || 'Unknown';
      }
    }
  }
  
  updateHousekeepingModuleStatus(housekeepingStatusData, schedulerHealth) {
    if (housekeepingStatusData.success && housekeepingStatusData.status) {
      const status = housekeepingStatusData.status;
      const healthBadge = document.getElementById('housekeeping-module-health');
      
      if (healthBadge) {
        // Update health status based on scheduler health
        const isHealthy = schedulerHealth && schedulerHealth.running && schedulerHealth.thread_alive;
        
        if (isHealthy) {
          healthBadge.textContent = 'Healthy';
          healthBadge.className = 'status-badge status-healthy';
        } else {
          healthBadge.textContent = 'Unhealthy';
          healthBadge.className = 'status-badge status-unhealthy';
        }
      }
      
      // Update toggle state
      if (this.housekeepingToggle) {
        this.housekeepingToggle.checked = status.enabled;
        // Show toggle wrapper after data loads
        document.getElementById('housekeeping-toggle-wrapper').style.display = 'block';
      }
      
      // Update scheduler details
      if (schedulerHealth && !schedulerHealth.error) {
        document.getElementById('housekeeping-scheduler-details').style.display = 'block';
        
        // Populate tooltip with full health data
        const tooltip = document.getElementById('housekeeping-tooltip');
        tooltip.textContent = 'Full Health Data:\n' + JSON.stringify(schedulerHealth, null, 2);
        
        // Thread status
        const threadStatus = schedulerHealth.thread_alive ? '✓ Running' : '✗ Stopped';
        document.getElementById('housekeeping-thread-status').textContent = threadStatus;
        document.getElementById('housekeeping-thread-status').style.color = schedulerHealth.thread_alive ? '#27ae60' : '#e74c3c';
        
        // Heartbeat age
        if (schedulerHealth.lock_file_age_seconds !== undefined) {
          const age = Math.round(schedulerHealth.lock_file_age_seconds);
          document.getElementById('housekeeping-heartbeat').textContent = `${age}s ago`;
          document.getElementById('housekeeping-heartbeat').style.color = age < 7200 ? '#27ae60' : '#e67e22'; // 2 hour threshold
        } else {
          document.getElementById('housekeeping-heartbeat').textContent = 'Unknown';
        }
        
        // Container ID
        document.getElementById('housekeeping-container').textContent = schedulerHealth.lock_container || 'Unknown';
      }
    }
  }
  
  updateCardSchedulerStatus(cardSchedulerStatusData, schedulerHealth) {
    const healthBadge = document.getElementById('card-module-health');
    
    if (healthBadge) {
      if (schedulerHealth && !schedulerHealth.error) {
        const isHealthy = schedulerHealth.running && schedulerHealth.thread_alive;
        
        if (isHealthy) {
          healthBadge.textContent = 'Healthy';
          healthBadge.className = 'status-badge status-healthy';
        } else {
          healthBadge.textContent = 'Unhealthy';
          healthBadge.className = 'status-badge status-unhealthy';
        }
        
        // Update toggle state
        if (this.cardSchedulerToggle && cardSchedulerStatusData.success && cardSchedulerStatusData.status) {
          this.cardSchedulerToggle.checked = cardSchedulerStatusData.status.enabled;
          // Show toggle wrapper after data loads
          document.getElementById('card-toggle-wrapper').style.display = 'block';
        }
        
        // Update scheduler details
        document.getElementById('card-scheduler-details').style.display = 'block';
        
        // Populate tooltip with full health data
        const tooltip = document.getElementById('card-tooltip');
        tooltip.textContent = 'Full Health Data:\n' + JSON.stringify(schedulerHealth, null, 2);
        
        // Thread status
        const threadStatus = schedulerHealth.thread_alive ? '✓ Running' : '✗ Stopped';
        document.getElementById('card-thread-status').textContent = threadStatus;
        document.getElementById('card-thread-status').style.color = schedulerHealth.thread_alive ? '#27ae60' : '#e74c3c';
        
        // Heartbeat age
        if (schedulerHealth.lock_file_age_seconds !== undefined) {
          const age = Math.round(schedulerHealth.lock_file_age_seconds);
          document.getElementById('card-heartbeat').textContent = `${age}s ago`;
          document.getElementById('card-heartbeat').style.color = age < 120 ? '#27ae60' : '#e67e22';
        } else {
          document.getElementById('card-heartbeat').textContent = 'Unknown';
        }
        
        // Container ID
        document.getElementById('card-container').textContent = schedulerHealth.lock_container || 'Unknown';
      } else {
        healthBadge.textContent = 'Error';
        healthBadge.className = 'status-badge status-unhealthy';
      }
    }
  }
  
  formatDateTime(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    
    return date.toLocaleString();
  }

  openDeleteModal() {
    this.modal.classList.add('active');
    this.confirmInput.value = '';
    this.errorMessage.textContent = '';
    this.confirmInput.focus();
  }

  closeDeleteModal() {
    this.modal.classList.remove('active');
    this.confirmInput.value = '';
    this.errorMessage.textContent = '';
  }

  confirmDelete() {
    const input = this.confirmInput.value.trim();
    
    // Check if input matches (case insensitive)
    if (input.toLowerCase() !== CONFIRMATION_TEXT.toLowerCase()) {
      this.errorMessage.textContent = 'Confirmation text does not match. Please type exactly: "Yes I am sure I want to delete all of my data!"';
      return;
    }

    // Perform delete
    this.deleteDatabase();
  }

  async deleteDatabase() {
    try {
      const response = await fetch('/api/database', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      const data = await response.json();

      if (data.success) {
        // Close modal
        this.closeDeleteModal();
        
        // Show success message
        await showAlert('Database deleted successfully. The page will now reload.', 'Success');
        
        // Reload page
        window.location.reload();
      } else {
        this.errorMessage.textContent = `Error: ${data.message}`;
      }
    } catch (error) {
      console.error('Error deleting database:', error);
      this.errorMessage.textContent = `Error: ${error.message}`;
    }
  }

  async toggleBackup(enabled) {
    try {
      const response = await fetch('/api/settings/backup/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled })
      });

      const data = await response.json();

      if (!data.success) {
        // Revert toggle on error
        this.backupToggle.checked = !enabled;
        
        // Check if error is about missing configuration
        if (data.message && data.message.includes('must be set before enabling')) {
          await showAlert(
            'Backup configuration is incomplete. Please configure backup settings on the Backup & Restore page before enabling.\n\nGo to: Backup & Restore → Automatic Backup Settings',
            'Configuration Required'
          );
        } else {
          await showAlert(data.message, 'Error');
        }
      }
    } catch (error) {
      console.error('Error toggling backup:', error);
      // Revert toggle on error
      this.backupToggle.checked = !enabled;
      await showAlert(error.message, 'Error');
    }
  }

  async toggleHousekeeping(enabled) {
    try {
      const response = await fetch('/api/settings/housekeeping/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled })
      });

      const data = await response.json();

      if (!data.success) {
        // Revert toggle on error
        this.housekeepingToggle.checked = !enabled;
        await showAlert(data.message, 'Error');
      }
    } catch (error) {
      console.error('Error toggling housekeeping:', error);
      // Revert toggle on error
      this.housekeepingToggle.checked = !enabled;
      await showAlert(error.message, 'Error');
    }
  }

  async toggleCardScheduler(enabled) {
    try {
      const response = await fetch('/api/settings/card-scheduler/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled })
      });

      const data = await response.json();

      if (!data.success) {
        // Revert toggle on error
        this.cardSchedulerToggle.checked = !enabled;
        await showAlert(data.message, 'Error');
      }
    } catch (error) {
      console.error('Error toggling card scheduler:', error);
      // Revert toggle on error
      this.cardSchedulerToggle.checked = !enabled;
      await showAlert(error.message, 'Error');
    }
  }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
  const systemInfo = new SystemInfo();
  systemInfo.init();
});
