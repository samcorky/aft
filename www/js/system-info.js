// System Info page functionality

const CONFIRMATION_TEXT = "Yes I am sure I want to delete all of my data!";

class SystemInfo {
  constructor() {
    this.modal = null;
    this.deleteBtn = null;
    this.confirmInput = null;
    this.errorMessage = null;
    this.backupBtn = null;
    this.restoreBtn = null;
    this.restoreFileInput = null;
    this.backupStatus = null;
  }

  async init() {
    // Get element references
    this.modal = document.getElementById('delete-modal');
    this.deleteBtn = document.getElementById('delete-db-btn');
    this.confirmInput = document.getElementById('delete-confirmation-input');
    this.errorMessage = document.getElementById('delete-error');
    this.backupBtn = document.getElementById('backup-btn');
    this.restoreBtn = document.getElementById('restore-btn');
    this.restoreFileInput = document.getElementById('restore-file-input');
    this.backupStatus = document.getElementById('backup-status');
    
    // Set up event listeners
    this.setupEventListeners();
    
    // Load data
    await this.loadSystemInfo();
  }

  setupEventListeners() {
    // Backup button
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
  }

  async loadSystemInfo() {
    try {
      // Fetch all data in parallel
      const [testResponse, versionResponse, statsResponse] = await Promise.all([
        fetch('/api/test'),
        fetch('/api/version'),
        fetch('/api/stats')
      ]);

      const testData = await testResponse.json();
      const versionData = await versionResponse.json();
      const statsData = await statsResponse.json();

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
    } catch (error) {
      console.error('Error loading system info:', error);
      const connectionElement = document.getElementById('db-connection');
      connectionElement.innerHTML = `
        <span class="status-icon error"></span>
        <span>Error</span>
      `;
    }
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
        alert('Database deleted successfully. The page will now reload.');
        
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
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
  const systemInfo = new SystemInfo();
  systemInfo.init();
});
