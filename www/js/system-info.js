// System Info page functionality

const CONFIRMATION_TEXT = "Yes I am sure I want to delete all of my data!";

class SystemInfo {
  constructor() {
    this.modal = null;
    this.cardRegenerateModal = null;
    this.deleteBtn = null;
    this.openCardRegenerateBtn = null;
    this.cardRegenerateStartInput = null;
    this.cardRegenerateEndInput = null;
    this.cardRegenerateError = null;
    this.cardRegeneratePreviewCount = null;
    this.cardRegeneratePreviewMeta = null;
    this.cardRegeneratePreviewList = null;
    this.cardRegenerateConfirmBtn = null;
    this.cardRegeneratePreviewDebounce = null;
    this.confirmInput = null;
    this.errorMessage = null;
    this.backupToggle = null;
    this.housekeepingToggle = null;
    this.cardSchedulerToggle = null;
    this.canRemoveTestUser = false;
    this.testUserDetected = false;
  }

  async init() {
    // Get element references
    this.modal = document.getElementById('delete-modal');
    this.cardRegenerateModal = document.getElementById('card-regenerate-modal');
    this.deleteBtn = document.getElementById('delete-db-btn');
    this.openCardRegenerateBtn = document.getElementById('open-card-regenerate-modal');
    this.cardRegenerateStartInput = document.getElementById('card-regenerate-start');
    this.cardRegenerateEndInput = document.getElementById('card-regenerate-end');
    this.cardRegenerateError = document.getElementById('card-regenerate-inline-error');
    this.cardRegeneratePreviewCount = document.getElementById('card-regenerate-preview-count');
    this.cardRegeneratePreviewMeta = document.getElementById('card-regenerate-preview-meta');
    this.cardRegeneratePreviewList = document.getElementById('card-regenerate-preview-list');
    this.cardRegenerateConfirmBtn = document.getElementById('confirm-card-regenerate-btn');
    this.confirmInput = document.getElementById('delete-confirmation-input');
    this.errorMessage = document.getElementById('delete-error');
    this.backupToggle = document.getElementById('backupToggle');
    this.housekeepingToggle = document.getElementById('housekeepingToggle');
    this.cardSchedulerToggle = document.getElementById('cardSchedulerToggle');
    
    // Set up event listeners
    this.setupEventListeners();
    
    // Load data
    await this.loadSystemInfo();
    
    // Check permissions and handle test user management section
    this.handleTestUserManagementPermissions();
  }

  handleTestUserManagementPermissions() {
    // Wait for user data to be ready (loaded by header.js)
    if (!window.userDataReady) {
      setTimeout(() => this.handleTestUserManagementPermissions(), 100);
      return;
    }
    
    // Check if user has either user.manage or user.role permission
    const hasUserManage = typeof hasPermission === 'function' && hasPermission('user.manage');
    const hasUserRole = typeof hasPermission === 'function' && hasPermission('user.role');
    
    const testUserCard = document.getElementById('test-user-card');
    
    if (!hasUserManage && !hasUserRole) {
      if (testUserCard) {
        testUserCard.style.display = 'none';
      }
    } else {
      this.canRemoveTestUser = hasUserManage;
      this.checkTestUserStatus();
    }
    
    // Check if user has admin.database permission for danger zone
    this.handleDangerZonePermissions();
  }

  handleDangerZonePermissions() {
    // Check if user has admin.database permission
    const hasAdminDatabase = typeof hasPermission === 'function' && hasPermission('admin.database');
    const hasSystemAdmin = typeof hasPermission === 'function' && hasPermission('system.admin');
    
    const dangerZoneCard = document.getElementById('danger-zone-card');
    const regenerateRow = document.getElementById('card-regenerate-row');
    
    if (!hasAdminDatabase) {
      // Hide the danger zone card entirely
      if (dangerZoneCard) {
        dangerZoneCard.style.display = 'none';
      }
    }

    if (regenerateRow) {
      regenerateRow.style.display = hasSystemAdmin ? 'flex' : 'none';
    }
  }

  setupEventListeners() {
    // Delete button opens modal
    if (this.deleteBtn) {
      this.deleteBtn.addEventListener('click', () => {
        this.openDeleteModal();
      });
    }

    if (this.openCardRegenerateBtn) {
      this.openCardRegenerateBtn.addEventListener('click', () => {
        this.openCardRegenerateModal();
      });
    }

    // Cancel button closes modal
    document.getElementById('cancel-delete-btn').addEventListener('click', () => {
      this.closeDeleteModal();
    });

    // Confirm delete button
    document.getElementById('confirm-delete-btn').addEventListener('click', () => {
      this.confirmDelete();
    });

    const cancelRegenerateBtn = document.getElementById('cancel-card-regenerate-btn');
    if (cancelRegenerateBtn) {
      cancelRegenerateBtn.addEventListener('click', () => {
        this.closeCardRegenerateModal();
      });
    }

    if (this.cardRegenerateConfirmBtn) {
      this.cardRegenerateConfirmBtn.addEventListener('click', async () => {
        await this.confirmCardRegenerate();
      });
    }

    // Clear error when typing
    this.confirmInput.addEventListener('input', () => {
      this.errorMessage.textContent = '';
    });

    if (this.cardRegenerateStartInput) {
      this.cardRegenerateStartInput.addEventListener('input', () => {
        this.scheduleCardRegeneratePreview();
      });
    }

    if (this.cardRegenerateEndInput) {
      this.cardRegenerateEndInput.addEventListener('input', () => {
        this.scheduleCardRegeneratePreview();
      });
    }

    // Close modal on background click
    this.modal.addEventListener('click', (e) => {
      if (e.target === this.modal) {
        this.closeDeleteModal();
      }
    });

    if (this.cardRegenerateModal) {
      this.cardRegenerateModal.addEventListener('click', (e) => {
        if (e.target === this.cardRegenerateModal) {
          this.closeCardRegenerateModal();
        }
      });
    }

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal && this.modal.classList.contains('active')) {
        this.closeDeleteModal();
      }
      if (e.key === 'Escape' && this.cardRegenerateModal && this.cardRegenerateModal.classList.contains('active')) {
        this.closeCardRegenerateModal();
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

    // Test user button
    const testUserBtn = document.getElementById('test-user-btn');
    if (testUserBtn) {
      testUserBtn.addEventListener('click', async () => {
        await this.removeTestUser();
      });
    }
  }

  async loadSystemInfo() {
    try {
      // Fetch all data in parallel
      const [liveResponse, versionResponse, statsResponse, backupStatusResponse, housekeepingStatusResponse, cardSchedulerStatusResponse, schedulerHealthResponse] = await Promise.all([
        fetch('/api/health/live'),
        fetch('/api/version'),
        fetch('/api/stats'),
        fetch('/api/settings/backup/status'),
        fetch('/api/settings/housekeeping/status'),
        fetch('/api/settings/card-scheduler/status'),
        fetch('/api/scheduler/health')
      ]);

      const liveData = await liveResponse.json();
      const versionData = await versionResponse.json();
      const statsData = await statsResponse.json();
      const backupStatusData = await backupStatusResponse.json();
      const housekeepingStatusData = await housekeepingStatusResponse.json();
      const cardSchedulerStatusData = await cardSchedulerStatusResponse.json();
      const schedulerHealthData = await schedulerHealthResponse.json();

      // Update connection status
      const connectionElement = document.getElementById('db-connection');
      if (liveData.ok && versionData.success) {
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

  formatDateTimeLocalInput(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  }

  openCardRegenerateModal() {
    if (!this.cardRegenerateModal) {
      return;
    }

    const now = new Date();
    const oneDayAgo = new Date(now.getTime() - (24 * 60 * 60 * 1000));

    if (this.cardRegenerateStartInput) {
      this.cardRegenerateStartInput.value = this.formatDateTimeLocalInput(oneDayAgo);
    }
    if (this.cardRegenerateEndInput) {
      this.cardRegenerateEndInput.value = this.formatDateTimeLocalInput(now);
    }

    if (this.cardRegenerateError) {
      this.cardRegenerateError.textContent = '';
    }

    if (this.cardRegeneratePreviewCount) {
      this.cardRegeneratePreviewCount.textContent = 'Preview: loading...';
    }
    if (this.cardRegeneratePreviewMeta) {
      this.cardRegeneratePreviewMeta.textContent = '';
    }
    if (this.cardRegeneratePreviewList) {
      this.cardRegeneratePreviewList.innerHTML = '<div class="scheduler-preview-subtitle">Loading preview...</div>';
    }

    this.cardRegenerateModal.classList.add('active');
    setupModalEscapeClose(this.cardRegenerateModal, () => this.closeCardRegenerateModal());
    this.scheduleCardRegeneratePreview(true);
  }

  closeCardRegenerateModal() {
    if (!this.cardRegenerateModal) {
      return;
    }

    this.cardRegenerateModal.classList.remove('active');
    if (this.cardRegeneratePreviewDebounce) {
      clearTimeout(this.cardRegeneratePreviewDebounce);
      this.cardRegeneratePreviewDebounce = null;
    }
  }

  buildCardRegenerateRangePayload() {
    const startValue = this.cardRegenerateStartInput ? this.cardRegenerateStartInput.value : '';
    const endValue = this.cardRegenerateEndInput ? this.cardRegenerateEndInput.value : '';

    if (!startValue || !endValue) {
      return null;
    }

    const startDate = new Date(startValue);
    const endDate = new Date(endValue);

    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      return null;
    }

    if (endDate < startDate) {
      return null;
    }

    return {
      start_datetime: startDate.toISOString(),
      end_datetime: endDate.toISOString()
    };
  }

  scheduleCardRegeneratePreview(immediate = false) {
    if (this.cardRegeneratePreviewDebounce) {
      clearTimeout(this.cardRegeneratePreviewDebounce);
      this.cardRegeneratePreviewDebounce = null;
    }

    if (immediate) {
      this.loadCardRegeneratePreview();
      return;
    }

    this.cardRegeneratePreviewDebounce = setTimeout(() => {
      this.loadCardRegeneratePreview();
    }, 250);
  }

  renderCardRegeneratePreview(preview) {
    const escapeHtml = (value) => {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    };

    const cards = Array.isArray(preview.cards) ? preview.cards : [];
    const count = Number(preview.would_generate_count || 0);
    const runsConsidered = Number(preview.runs_considered || 0);

    if (this.cardRegeneratePreviewCount) {
      this.cardRegeneratePreviewCount.textContent = `Preview: ${count} card${count === 1 ? '' : 's'}`;
    }

    if (this.cardRegeneratePreviewMeta) {
      this.cardRegeneratePreviewMeta.textContent = `${runsConsidered} run${runsConsidered === 1 ? '' : 's'} considered`;
    }

    if (!this.cardRegeneratePreviewList) {
      return;
    }

    if (cards.length === 0) {
      this.cardRegeneratePreviewList.innerHTML = '<div class="scheduler-preview-subtitle">No cards will be generated for this range.</div>';
      return;
    }

    this.cardRegeneratePreviewList.innerHTML = cards.map((card) => {
      const runAt = card.run_at ? new Date(card.run_at).toLocaleString() : 'Unknown run time';
      const boardName = escapeHtml(card.board_name || 'Unknown board');
      const columnName = escapeHtml(card.column_name || 'Unknown column');
      const title = escapeHtml(card.template_card_title || 'Untitled template');
      const scheduleId = escapeHtml(card.schedule_id || 'n/a');
      return `
        <div class="scheduler-preview-item">
          <div class="scheduler-preview-title">${title}</div>
          <div class="scheduler-preview-subtitle">Run: ${escapeHtml(runAt)}</div>
          <div class="scheduler-preview-subtitle">Board: ${boardName} | Column: ${columnName} | Schedule #${scheduleId}</div>
        </div>
      `;
    }).join('');
  }

  async loadCardRegeneratePreview() {
    const payload = this.buildCardRegenerateRangePayload();
    if (!payload) {
      if (this.cardRegenerateError) {
        this.cardRegenerateError.textContent = 'Provide a valid start and end time, and ensure end is at or after start.';
      }
      if (this.cardRegeneratePreviewList) {
        this.cardRegeneratePreviewList.innerHTML = '<div class="scheduler-preview-subtitle">Preview unavailable with invalid range.</div>';
      }
      if (this.cardRegeneratePreviewCount) {
        this.cardRegeneratePreviewCount.textContent = 'Preview: 0 cards';
      }
      return;
    }

    if (this.cardRegenerateError) {
      this.cardRegenerateError.textContent = '';
    }

    try {
      const response = await fetch('/api/schedules/regenerate/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || `Preview request failed (${response.status})`);
      }

      this.renderCardRegeneratePreview(data.preview || {});
    } catch (error) {
      console.error('Error loading scheduler regeneration preview:', error);
      if (this.cardRegenerateError) {
        this.cardRegenerateError.textContent = error.message || 'Failed to load preview.';
      }
      if (this.cardRegeneratePreviewList) {
        this.cardRegeneratePreviewList.innerHTML = '<div class="scheduler-preview-subtitle">Failed to load preview.</div>';
      }
      if (this.cardRegeneratePreviewCount) {
        this.cardRegeneratePreviewCount.textContent = 'Preview: 0 cards';
      }
    }
  }

  async confirmCardRegenerate() {
    const payload = this.buildCardRegenerateRangePayload();
    if (!payload) {
      if (this.cardRegenerateError) {
        this.cardRegenerateError.textContent = 'Provide a valid start and end time, and ensure end is at or after start.';
      }
      return;
    }

    if (this.cardRegenerateError) {
      this.cardRegenerateError.textContent = '';
    }

    if (this.cardRegenerateConfirmBtn) {
      this.cardRegenerateConfirmBtn.disabled = true;
      this.cardRegenerateConfirmBtn.textContent = 'Generating...';
    }

    try {
      const response = await fetch('/api/schedules/regenerate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || `Generate request failed (${response.status})`);
      }

      const generatedCount = data.result && typeof data.result.generated_count === 'number'
        ? data.result.generated_count
        : 0;

      await showAlert(`Generated ${generatedCount} scheduled card${generatedCount === 1 ? '' : 's'}.`, 'Scheduler');

      this.closeCardRegenerateModal();
      await this.loadSystemInfo();
    } catch (error) {
      console.error('Error generating scheduled cards:', error);
      if (this.cardRegenerateError) {
        this.cardRegenerateError.textContent = error.message || 'Failed to generate scheduled cards.';
      }
    } finally {
      if (this.cardRegenerateConfirmBtn) {
        this.cardRegenerateConfirmBtn.disabled = false;
        this.cardRegenerateConfirmBtn.textContent = 'Generate';
      }
    }
  }

  openDeleteModal() {
    this.modal.classList.add('active');
    setupModalEscapeClose(this.modal, () => this.closeDeleteModal());
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

  async checkTestUserStatus() {
    const btn = document.getElementById('test-user-btn');
    const btnText = document.getElementById('test-user-btn-text');
    const presence = document.getElementById('test-user-presence');
    const compatibility = document.getElementById('test-user-compatibility');
    const actionNote = document.getElementById('test-user-action-note');
    
    if (!btn || !btnText || !presence || !compatibility || !actionNote) {
      return;
    }
    
    try {
      const response = await fetch('/api/admin/test-user');
      
      if (!response.ok) {
        throw new Error(`Status check failed (${response.status})`);
      }

      const data = await response.json();
      const detectedUser = data.detected_user;

      this.testUserDetected = Boolean(detectedUser);
      this.canRemoveTestUser = Boolean(data.permissions?.can_remove);

      if (detectedUser) {
        presence.textContent = data.test_user_compatible
          ? 'Known test user detected and matches the current test suite expectations.'
          : 'Known test user detected, but it is not active and approved. Tests may still fail until it is fixed or removed.';

        compatibility.textContent = data.test_user_compatible
          ? 'A clean database also works. Remove this account when testing is complete or when the environment should no longer contain known credentials.'
          : 'A clean database is compatible. On a non-clean database, the known test user must be active and approved to satisfy the current test suite.';
      } else {
        presence.textContent = 'No known test user detected.';
        compatibility.textContent = 'A clean database is already compatible with the tests. If tests must run against an existing database, create the approved administrator account shown above outside this page.';
      }

      if (this.canRemoveTestUser && this.testUserDetected) {
        btn.style.display = 'inline-flex';
        btn.disabled = false;
        btnText.textContent = 'Remove Known Test User';
        btn.style.background = '#ef4444';
        actionNote.textContent = 'Removal is available because you have user.manage.';
      } else {
        btn.style.display = 'none';
        actionNote.textContent = this.testUserDetected
          ? 'A user with user.manage should remove this account when it is no longer required.'
          : 'This page no longer creates the known test user.';
      }
    } catch (error) {
      console.error('Error checking test user status:', error);
      this.testUserDetected = false;
      btn.style.display = 'none';
      presence.textContent = 'Unable to verify known test user status right now.';
      compatibility.textContent = 'A clean database is still compatible with the tests.';
      actionNote.textContent = 'Retry the page if you need to re-check the known test user.';
    }
  }

  async removeTestUser() {
    const btn = document.getElementById('test-user-btn');
    const btnText = document.getElementById('test-user-btn-text');
    const statusDiv = document.getElementById('test-user-status');
    
    if (!btn || !btnText || !statusDiv) {
      return;
    }

    if (!this.testUserDetected || !this.canRemoveTestUser) {
      return;
    }
    
    btn.disabled = true;
    const originalText = btnText.textContent;
    btnText.textContent = 'Processing...';
    
    try {
      const response = await fetch('/api/admin/test-user', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      const data = await response.json();

      if (data.success) {
        statusDiv.style.display = 'block';
        statusDiv.style.background = '#d1fae5';
        statusDiv.style.color = '#065f46';
        statusDiv.innerHTML = '<strong>✓ Known test user removed successfully</strong>';

        if (data.deleted_current_user) {
          statusDiv.innerHTML = '<strong>✓ Known test user removed successfully</strong><br>Redirecting to login...';
          setTimeout(() => {
            window.location.href = '/login.html';
          }, 1200);
          return;
        }

        await this.checkTestUserStatus();

        setTimeout(() => {
          statusDiv.style.display = 'none';
        }, 5000);
      } else {
        statusDiv.style.display = 'block';
        statusDiv.style.background = '#fee2e2';
        statusDiv.style.color = '#991b1b';
        statusDiv.textContent = `Error: ${data.message}`;
        btnText.textContent = originalText;
      }
    } catch (error) {
      console.error('Error removing known test user:', error);
      statusDiv.style.display = 'block';
      statusDiv.style.background = '#fee2e2';
      statusDiv.style.color = '#991b1b';
      statusDiv.textContent = `Error: ${error.message}`;
      btnText.textContent = originalText;
    } finally {
      btn.disabled = false;
    }
  }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
  const systemInfo = new SystemInfo();
  systemInfo.init();
});
