"""Tests for backup scheduler permission error handling."""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from backup_scheduler import BackupScheduler


@pytest.mark.unit
class TestBackupSchedulerPermissions:
    """Test cases for backup scheduler permission error handling."""
    
    def test_permission_error_detected_on_directory_creation(self):
        """Test that permission errors are detected when creating backup directory."""
        scheduler = BackupScheduler()
        
        # Create a unique temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set unique lock file path to avoid conflicts
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Ensure lock file doesn't exist
            if scheduler.lock_file.exists():
                scheduler.lock_file.unlink()
            
            # Mock Path.mkdir to raise PermissionError
            original_mkdir = Path.mkdir
            def mock_mkdir(self, *args, **kwargs):
                # Allow lock file directory to be created, but fail on backup directory
                if 'backups' in str(self):
                    raise PermissionError("Permission denied")
                return original_mkdir(self, *args, **kwargs)
            
            with patch('pathlib.Path.mkdir', mock_mkdir):
                scheduler.start()
                
                # Scheduler should not be running
                assert scheduler.running is False
                assert scheduler.thread is None
                
                # Permission error should be stored
                assert scheduler.permission_error is not None
                assert "not writable" in scheduler.permission_error
                assert "sudo chown" in scheduler.permission_error
                
                # Lock file should be cleaned up
                assert not scheduler.lock_file.exists()
    
    def test_permission_error_detected_on_test_file_write(self):
        """Test that permission errors are detected when testing write permissions."""
        scheduler = BackupScheduler()
        
        # Create a unique temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Ensure lock file doesn't exist
            if scheduler.lock_file.exists():
                scheduler.lock_file.unlink()
            
            # Mock touch to fail on test file
            original_touch = Path.touch
            def mock_touch(self, *args, **kwargs):
                if '.write_test' in str(self):
                    raise PermissionError("Permission denied")
                return original_touch(self, *args, **kwargs)
            
            with patch('pathlib.Path.touch', mock_touch):
                scheduler.start()
                
                # Scheduler should not be running
                assert scheduler.running is False
                assert scheduler.thread is None
                
                # Permission error should be stored
                assert scheduler.permission_error is not None
                assert "not writable" in scheduler.permission_error
                
                # Lock file should be cleaned up
                assert not scheduler.lock_file.exists()
    
    def test_generic_exception_during_permission_check(self):
        """Test that generic exceptions during permission check are handled properly."""
        scheduler = BackupScheduler()
        
        # Create a unique temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Ensure lock file doesn't exist
            if scheduler.lock_file.exists():
                scheduler.lock_file.unlink()
            
            # Mock mkdir to raise OSError on backup directory
            original_mkdir = Path.mkdir
            def mock_mkdir(self, *args, **kwargs):
                if 'backups' in str(self):
                    raise OSError("Disk error")
                return original_mkdir(self, *args, **kwargs)
            
            with patch('pathlib.Path.mkdir', mock_mkdir):
                scheduler.start()
                
                # Scheduler should not be running
                assert scheduler.running is False
                assert scheduler.thread is None
                
                # Error should be stored
                assert scheduler.permission_error is not None
                assert "Error checking backup directory permissions" in scheduler.permission_error
                assert "Disk error" in scheduler.permission_error
                
                # Lock file should be cleaned up
                assert not scheduler.lock_file.exists()
    
    def test_permission_error_cleared_on_successful_start(self):
        """Test that permission_error is cleared when scheduler starts successfully."""
        scheduler = BackupScheduler()
        
        # Set an existing permission error
        scheduler.permission_error = "Previous error"
        
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.backup_dir = Path(tmpdir)
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Mock the database operations
            with patch('backup_scheduler.SessionLocal') as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db
                mock_db.query.return_value.filter.return_value.first.return_value = None
                
                scheduler.start()
                
                # Permission error should be cleared
                assert scheduler.permission_error is None
                
                # Clean up
                scheduler.stop()
    
    def test_scheduler_doesnt_start_with_permission_error(self):
        """Test that the scheduler thread doesn't start when permission errors occur."""
        scheduler = BackupScheduler()
        
        # Create a unique temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Ensure lock file doesn't exist
            if scheduler.lock_file.exists():
                scheduler.lock_file.unlink()
            
            # Mock mkdir to raise PermissionError on backup directory
            original_mkdir = Path.mkdir
            def mock_mkdir(self, *args, **kwargs):
                if 'backups' in str(self):
                    raise PermissionError("Permission denied")
                return original_mkdir(self, *args, **kwargs)
            
            with patch('pathlib.Path.mkdir', mock_mkdir):
                scheduler.start()
                
                # Verify the thread was never started
                assert scheduler.thread is None
                assert scheduler.running is False
    
    def test_lock_file_cleanup_on_permission_error(self):
        """Test that lock file is cleaned up when permission error occurs."""
        scheduler = BackupScheduler()
        
        # Create a temporary directory for the lock file
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Mock permission error after lock file is created
            with patch('pathlib.Path.mkdir', side_effect=PermissionError("Permission denied")):
                scheduler.start()
                
                # Lock file should not exist
                assert not scheduler.lock_file.exists()
    
    def test_lock_file_cleanup_on_generic_exception(self):
        """Test that lock file is cleaned up on generic exceptions during permission check."""
        scheduler = BackupScheduler()
        
        # Create a temporary directory for the lock file
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Mock generic exception after lock file is created
            with patch('pathlib.Path.mkdir', side_effect=OSError("Disk failure")):
                scheduler.start()
                
                # Lock file should not exist
                assert not scheduler.lock_file.exists()
    
    def test_permission_error_message_format(self):
        """Test that permission error message contains helpful information."""
        scheduler = BackupScheduler()
        
        # Create a unique temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Ensure lock file doesn't exist
            if scheduler.lock_file.exists():
                scheduler.lock_file.unlink()
            
            # Mock mkdir to raise PermissionError on backup directory
            original_mkdir = Path.mkdir
            def mock_mkdir(self, *args, **kwargs):
                if 'backups' in str(self):
                    raise PermissionError("Permission denied")
                return original_mkdir(self, *args, **kwargs)
            
            with patch('pathlib.Path.mkdir', mock_mkdir):
                scheduler.start()
                
                # Verify error message contains helpful information
                assert scheduler.permission_error is not None
                assert str(scheduler.backup_dir) in scheduler.permission_error
                assert "sudo chown -R 1000:1000" in scheduler.permission_error
                assert "sudo chmod -R 755" in scheduler.permission_error
    
    def test_multiple_start_attempts_with_permission_error(self):
        """Test that multiple start attempts with permission errors don't cause issues."""
        scheduler = BackupScheduler()
        
        # Create a temporary directory for the lock file
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            with patch('pathlib.Path.mkdir', side_effect=PermissionError("Permission denied")):
                # Try starting multiple times
                scheduler.start()
                assert scheduler.permission_error is not None
                assert not scheduler.lock_file.exists()
                
                # Second attempt should also handle properly
                scheduler.start()
                assert scheduler.permission_error is not None
                assert not scheduler.lock_file.exists()
    
    def test_permission_check_happens_before_settings_validation(self):
        """Test that permission check happens before settings validation."""
        scheduler = BackupScheduler()
        
        # Create a unique temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.lock_file = Path(tmpdir) / "test.lock"
            
            # Ensure lock file doesn't exist
            if scheduler.lock_file.exists():
                scheduler.lock_file.unlink()
            
            # Mock invalid settings that would normally cause issues
            with patch('backup_scheduler.SessionLocal') as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db
                
                # Mock getting invalid settings
                mock_db.query.return_value.filter.return_value.first.return_value = None
                
                # Mock permission error
                original_mkdir = Path.mkdir
                def mock_mkdir(self, *args, **kwargs):
                    if 'backups' in str(self):
                        raise PermissionError("Permission denied")
                    return original_mkdir(self, *args, **kwargs)
                
                with patch('pathlib.Path.mkdir', mock_mkdir):
                    scheduler.start()
                    
                    # Should fail on permission check, not reach settings validation
                    assert scheduler.permission_error is not None
                    assert "not writable" in scheduler.permission_error
                    assert scheduler.running is False
                    
                    # Verify settings validation was never called (would have raised ValueError)
                    # The fact that we get permission_error instead of settings error proves this


@pytest.mark.api
class TestBackupPermissionErrorAPI:
    """Test cases for backup permission error in API responses."""
    
    def test_permission_error_in_status_response(self, api_client):
        """Test that permission_error field is present in status API response."""
        import requests
        response = requests.get(f'{api_client}/api/settings/backup/status')
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'permission_error' in data['status']
        
        # permission_error should be either None or a string
        error = data['status']['permission_error']
        assert error is None or isinstance(error, str)
    
    def test_permission_error_updates_in_status(self, api_client):
        """Test that permission_error in status reflects actual scheduler state."""
        import requests
        
        # Get initial status
        response1 = requests.get(f'{api_client}/api/settings/backup/status')
        status1 = response1.json()['status']
        error1 = status1.get('permission_error')
        
        # If there's no permission error initially, we can't test the update
        # This is expected in a properly configured environment
        # The important thing is that the field exists and is properly typed
        assert 'permission_error' in status1
        assert error1 is None or isinstance(error1, str)
        
        # Get status again to ensure consistency
        response2 = requests.get(f'{api_client}/api/settings/backup/status')
        status2 = response2.json()['status']
        error2 = status2.get('permission_error')
        
        # Error state should be consistent across requests
        assert error1 == error2
    
    def test_permission_error_format_in_response(self, api_client):
        """Test that permission_error has expected format when present."""
        import requests
        response = requests.get(f'{api_client}/api/settings/backup/status')
        
        data = response.json()
        error = data['status']['permission_error']
        
        # If error exists, it should contain helpful information
        if error is not None:
            assert isinstance(error, str)
            assert len(error) > 0
            # Should contain helpful instructions
            assert 'sudo' in error.lower() or 'permission' in error.lower()
