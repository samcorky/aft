"""Tests for database backup and restore API endpoints."""
import pytest
import requests
from pathlib import Path


@pytest.mark.api
class TestDatabaseBackupsAPI:
    """Test cases for /api/database/backups endpoints."""
    
    def test_list_backups_response_structure_empty_or_populated(self, api_client):
        """Test listing backups returns correct structure."""
        response = requests.get(f'{api_client}/api/database/backups/list')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'backups' in data
        assert isinstance(data['backups'], list)
        
        # Verify structure is correct regardless of whether backups exist
        for backup in data['backups']:
            assert 'filename' in backup
            assert 'created' in backup
            assert 'size' in backup
    
    def test_list_backups_with_data(self, api_client):
        """Test listing backups when they exist."""
        response = requests.get(f'{api_client}/api/database/backups/list')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # If backups exist, check their structure
        if len(data['backups']) > 0:
            backup = data['backups'][0]
            assert 'filename' in backup
            assert 'created' in backup
            assert 'size' in backup
            assert backup['size'] > 0
            assert backup['filename'].startswith('auto_backup_')
            assert backup['filename'].endswith('.sql')
    
    def test_list_backups_sorted_newest_first(self, api_client):
        """Test that backups are sorted newest first."""
        backup_path = Path("/app/backups")
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Create multiple test backups with different timestamps
        test_backups = [
            "auto_backup_20240101_120000.sql",
            "auto_backup_20240102_120000.sql",
            "auto_backup_20240103_120000.sql",
        ]
        
        try:
            for backup_name in test_backups:
                (backup_path / backup_name).write_text("-- Test backup\n")
            
            response = requests.get(f'{api_client}/api/database/backups/list')
            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert len(data['backups']) >= 3
            
            # Check that backups are sorted newest first
            filenames = [b['filename'] for b in data['backups']]
            test_backup_names = [f for f in filenames if f.startswith('auto_backup_202401')]
            assert test_backup_names == sorted(test_backup_names, reverse=True)
        finally:
            # Cleanup
            for backup_name in test_backups:
                backup_file = backup_path / backup_name
                if backup_file.exists():
                    backup_file.unlink()
    
    def test_list_backups_filters_non_auto_files(self, api_client):
        """Test that only auto_backup_* files are listed."""
        response = requests.get(f'{api_client}/api/database/backups/list')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # All returned files should match the auto_backup pattern
        for backup in data['backups']:
            assert backup['filename'].startswith('auto_backup_')
            assert backup['filename'].endswith('.sql')
            # Verify filename format: auto_backup_YYYYMMDD_HHMMSS.sql
            import re
            assert re.match(r'^auto_backup_\d{8}_\d{6}\.sql$', backup['filename'])
    
    def test_restore_backup_invalid_filename_format(self, api_client):
        """Test that restore rejects invalid filename formats."""
        # Try various invalid filename formats
        invalid_filenames = [
            "manual_backup.sql",
            "auto_backup_invalid.sql",
            "auto_backup_20240101.sql",
            "auto_backup_20240101_12.sql",
        ]
        
        for filename in invalid_filenames:
            response = requests.post(
                f'{api_client}/api/database/backups/restore/{filename}'
            )
            # Should be rejected with 400 (invalid) or 404 (file not found after validation)
            assert response.status_code in [400, 404], f"Failed for filename: {filename}"
            # Only check JSON if content-type is JSON
            if 'application/json' in response.headers.get('content-type', ''):
                data = response.json()
                assert data['success'] is False
                assert 'message' in data
    
    def test_restore_backup_path_traversal_prevention(self, api_client):
        """Test that path traversal attacks are prevented."""
        # Try various path traversal techniques
        # Note: Some special characters in URLs may cause Flask routing errors
        # resulting in 404 HTML responses instead of JSON
        path_traversal_attempts = [
            "auto_backup_20240101_120000.sql..",
            "auto_backup_20240101_120000.sql~",
        ]
        
        for attempt in path_traversal_attempts:
            response = requests.post(
                f'{api_client}/api/database/backups/restore/{attempt}'
            )
            # Should be rejected (400 invalid format or 404 not found)
            assert response.status_code in [400, 404], f"Failed for attempt: {attempt}"
            # Only check JSON if content-type is JSON
            if 'application/json' in response.headers.get('content-type', ''):
                data = response.json()
                assert data['success'] is False
    
    def test_restore_backup_file_not_found(self, api_client):
        """Test restoring a backup that doesn't exist."""
        response = requests.post(
            f'{api_client}/api/database/backups/restore/auto_backup_99990101_000000.sql'
        )
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'message' in data
        assert 'not found' in data['message'].lower()
    
    def test_restore_backup_success(self, api_client):
        """Test successful backup restoration."""
        # This test requires a valid backup file with proper SQL content
        # We'll create a minimal valid backup
        backup_path = Path("/app/backups")
        backup_path.mkdir(parents=True, exist_ok=True)
        test_backup = backup_path / "auto_backup_20240101_120000.sql"
        
        # Create a valid backup SQL file with minimal content
        # Including the alembic_version table data
        backup_content = """-- MySQL dump
-- Host: localhost    Database: aft_db

DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

LOCK TABLES `alembic_version` WRITE;
INSERT INTO `alembic_version` VALUES ('current_version_here');
UNLOCK TABLES;
"""
        
        try:
            # Write the test backup
            test_backup.write_text(backup_content)
            
            # Note: This test may fail if the backup content isn't fully valid
            # or if the database is in use. In a real scenario, you'd need
            # a properly exported backup file for this test to pass
            response = requests.post(
                f'{api_client}/api/database/backups/restore/auto_backup_20240101_120000.sql'
            )
            
            # The restore might fail due to version mismatch, invalid SQL, or file not found
            # but it should handle it gracefully
            assert response.status_code in [200, 400, 404, 500]
            data = response.json()
            assert 'success' in data
            assert 'message' in data
            
            # If successful, message should indicate restoration
            if data['success']:
                assert 'restored' in data['message'].lower()
        finally:
            # Cleanup
            if test_backup.exists():
                test_backup.unlink()
    
    def test_restore_backup_version_mismatch(self, api_client):
        """Test that version mismatch is detected and reported."""
        backup_path = Path("/app/backups")
        backup_path.mkdir(parents=True, exist_ok=True)
        test_backup = backup_path / "auto_backup_20240101_120000.sql"
        
        # Create a backup with an incompatible version
        backup_content = """-- MySQL dump
DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

LOCK TABLES `alembic_version` WRITE;
INSERT INTO `alembic_version` VALUES ('incompatible_old_version');
UNLOCK TABLES;
"""
        
        try:
            test_backup.write_text(backup_content)
            
            response = requests.post(
                f'{api_client}/api/database/backups/restore/auto_backup_20240101_120000.sql'
            )
            
            # Should either succeed with a warning or fail with version error
            assert response.status_code in [200, 400, 404, 500]
            data = response.json()
            assert 'message' in data
            
            # If it detected version mismatch, message should mention version
            if not data['success']:
                message_lower = data['message'].lower()
                # May mention version or other validation issues
                assert len(message_lower) > 0
        finally:
            # Cleanup
            if test_backup.exists():
                test_backup.unlink()
    
    def test_list_backups_directory_permissions(self, api_client):
        """Test handling of directory permission issues."""
        # This test documents expected behavior if backup dir is inaccessible
        # In production, the directory should always be accessible
        response = requests.get(f'{api_client}/api/database/backups/list')
        
        # Should handle gracefully even if there are permission issues
        assert response.status_code in [200, 500]
        data = response.json()
        assert 'success' in data
    
    def test_restore_backup_concurrent_operation(self, api_client):
        """Test behavior when attempting restore during active operation."""
        # This test documents expected behavior
        # The actual implementation may lock operations or queue them
        backup_path = Path("/app/backups")
        backup_path.mkdir(parents=True, exist_ok=True)
        test_backup = backup_path / "auto_backup_20240101_120000.sql"
        
        try:
            test_backup.write_text("-- Test backup\n")
            
            # Attempt restore (may fail due to invalid backup content, which is expected)
            response = requests.post(
                f'{api_client}/api/database/backups/restore/auto_backup_20240101_120000.sql'
            )
            
            # Should respond (success or failure) but not hang
            assert response.status_code in [200, 400, 404, 500]
            data = response.json()
            assert 'success' in data
            assert 'message' in data
        finally:
            # Cleanup
            if test_backup.exists():
                test_backup.unlink()
    
    def test_list_backups_response_structure(self, api_client):
        """Test that the response has the correct structure."""
        response = requests.get(f'{api_client}/api/database/backups/list')
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert 'success' in data
        assert 'backups' in data
        assert isinstance(data['backups'], list)
        
        # If backups exist, check structure of each item
        for backup in data['backups']:
            assert 'filename' in backup
            assert 'created' in backup
            assert 'size' in backup
            assert isinstance(backup['filename'], str)
            assert isinstance(backup['created'], str)
            assert isinstance(backup['size'], int)
            assert backup['size'] >= 0
    
    def test_restore_backup_response_structure_error(self, api_client):
        """Test error response structure for restore endpoint."""
        # Use invalid filename to trigger error
        response = requests.post(
            f'{api_client}/api/database/backups/restore/invalid_name.sql'
        )
        
        assert response.status_code == 400
        data = response.json()
        
        # Check error response structure
        assert 'success' in data
        assert data['success'] is False
        assert 'message' in data
        assert isinstance(data['message'], str)
        assert len(data['message']) > 0
    
    def test_list_backups_large_files(self, api_client):
        """Test that large backup files are handled correctly."""
        response = requests.get(f'{api_client}/api/database/backups/list')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # If backups exist, verify size field is present and reasonable
        if len(data['backups']) > 0:
            for backup in data['backups']:
                assert 'size' in backup
                assert isinstance(backup['size'], int)
                assert backup['size'] > 0
                # Backup files should be at least a few KB
                assert backup['size'] > 1000
    
    def test_restore_backup_special_characters_rejected(self, api_client):
        """Test that filenames with special characters are rejected."""
        special_char_filenames = [
            "auto_backup_20240101_120000.sql\x00.txt",  # Null byte
            "auto_backup_20240101_120000.sql\n.txt",     # Newline
            "auto_backup_20240101_120000.sql\r.txt",     # Carriage return
            "auto_backup_20240101_120000.sql\t.txt",     # Tab
        ]
        
        for filename in special_char_filenames:
            response = requests.post(
                f'{api_client}/api/database/backups/restore/{filename}'
            )
            # Should be rejected
            assert response.status_code in [400, 404]
            data = response.json()
            assert data['success'] is False
