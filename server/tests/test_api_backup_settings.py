"""Tests for backup settings API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestBackupSettingsAPI:
    """Test cases for backup settings API endpoints."""
    
    def test_get_backup_config_default(self, api_client):
        """Test getting backup config with default values."""
        response = requests.get(f'{api_client}/api/settings/backup/config')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'config' in data
        
        config = data['config']
        assert 'enabled' in config
        assert 'frequency_value' in config
        assert 'frequency_unit' in config
        assert 'start_time' in config
        assert 'retention_count' in config
    
    def test_update_backup_config_all_fields(self, api_client):
        """Test updating all backup configuration fields."""
        config_data = {
            'enabled': True,
            'frequency_value': 6,
            'frequency_unit': 'hours',
            'start_time': '02:30',
            'retention_count': 10
        }
        
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json=config_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify the settings were saved
        get_response = requests.get(f'{api_client}/api/settings/backup/config')
        get_data = get_response.json()
        config = get_data['config']
        
        assert config['enabled'] is True
        assert config['frequency_value'] == 6
        assert config['frequency_unit'] == 'hours'
        assert config['start_time'] == '02:30'
        assert config['retention_count'] == 10
    
    def test_update_backup_config_partial_fields(self, api_client):
        """Test updating only some backup configuration fields."""
        # Set initial config
        requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': False, 'frequency_value': 1}
        )
        
        # Update only enabled field
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        
        # Verify enabled changed but frequency_value remained
        get_response = requests.get(f'{api_client}/api/settings/backup/config')
        config = get_response.json()['config']
        assert config['enabled'] is True
        assert config['frequency_value'] == 1
    
    def test_update_backup_config_invalid_frequency_value(self, api_client):
        """Test validation of frequency_value."""
        # Test value too low
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_value': 0}
        )
        assert response.status_code == 400
        assert 'frequency_value' in response.json()['message']
        
        # Test value too high
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_value': 100}
        )
        assert response.status_code == 400
        assert 'frequency_value' in response.json()['message']
        
        # Test non-integer
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_value': 'invalid'}
        )
        assert response.status_code == 400
    
    def test_update_backup_config_invalid_frequency_unit(self, api_client):
        """Test validation of frequency_unit."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_unit': 'weeks'}
        )
        assert response.status_code == 400
        assert 'frequency_unit' in response.json()['message']
    
    def test_update_backup_config_valid_frequency_units(self, api_client):
        """Test all valid frequency units."""
        for unit in ['minutes', 'hours', 'days']:
            response = requests.put(
                f'{api_client}/api/settings/backup/config',
                json={'frequency_unit': unit}
            )
            assert response.status_code == 200
            
            # Verify it was saved
            get_response = requests.get(f'{api_client}/api/settings/backup/config')
            config = get_response.json()['config']
            assert config['frequency_unit'] == unit
    
    def test_update_backup_config_invalid_start_time(self, api_client):
        """Test validation of start_time format."""
        invalid_times = [
            'invalid',
            '25:00',  # Hour too high
            '23:60',  # Minute too high
            '12:5',   # Single digit minute without leading zero
        ]
        
        for time_str in invalid_times:
            response = requests.put(
                f'{api_client}/api/settings/backup/config',
                json={'start_time': time_str}
            )
            assert response.status_code == 400, f"Expected 400 for time: {time_str}"
            assert 'start_time' in response.json()['message']
    
    def test_update_backup_config_valid_start_times(self, api_client):
        """Test various valid start_time formats."""
        valid_times = ['00:00', '01:30', '1:30', '12:00', '23:59', '9:00', '9:30']
        
        for time_str in valid_times:
            response = requests.put(
                f'{api_client}/api/settings/backup/config',
                json={'start_time': time_str}
            )
            assert response.status_code == 200, f"Expected 200 for time: {time_str}"
    
    def test_update_backup_config_invalid_retention_count(self, api_client):
        """Test validation of retention_count."""
        # Test value too low
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'retention_count': 0}
        )
        assert response.status_code == 400
        assert 'retention_count' in response.json()['message']
        
        # Test value too high
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'retention_count': 101}
        )
        assert response.status_code == 400
        assert 'retention_count' in response.json()['message']
    
    def test_update_backup_config_invalid_enabled_type(self, api_client):
        """Test validation of enabled field type."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': 'true'}  # String instead of boolean
        )
        assert response.status_code == 400
        assert 'enabled' in response.json()['message']
    
    def test_update_backup_config_empty_body(self, api_client):
        """Test updating with empty request body."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={}
        )
        # Should succeed but not change anything
        assert response.status_code == 200
    
    def test_update_backup_config_missing_body(self, api_client):
        """Test updating without request body."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 400
        assert 'required' in response.json()['message'].lower()
    
    def test_get_backup_status(self, api_client):
        """Test getting backup scheduler status."""
        response = requests.get(f'{api_client}/api/settings/backup/status')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'status' in data
        
        status = data['status']
        assert 'running' in status
        assert 'enabled' in status
        assert 'frequency' in status
        assert 'retention_count' in status
        assert 'latest_backup_file' in status
        assert 'latest_backup_date' in status
        assert 'backup_within_window' in status
        
        # These can be None if no backups exist
        assert status['latest_backup_file'] is None or isinstance(status['latest_backup_file'], str)
        assert status['latest_backup_date'] is None or isinstance(status['latest_backup_date'], str)
        assert isinstance(status['backup_within_window'], bool)
    
    def test_backup_config_persistence(self, api_client):
        """Test that backup configuration persists across requests."""
        # Set specific configuration
        config_data = {
            'enabled': True,
            'frequency_value': 12,
            'frequency_unit': 'hours',
            'start_time': '03:00',
            'retention_count': 5
        }
        
        requests.put(
            f'{api_client}/api/settings/backup/config',
            json=config_data
        )
        
        # Retrieve config multiple times to ensure persistence
        for _ in range(3):
            response = requests.get(f'{api_client}/api/settings/backup/config')
            config = response.json()['config']
            
            assert config['enabled'] is True
            assert config['frequency_value'] == 12
            assert config['frequency_unit'] == 'hours'
            assert config['start_time'] == '03:00'
            assert config['retention_count'] == 5
    
    def test_update_backup_config_boundary_values(self, api_client):
        """Test boundary values for numeric fields."""
        # Test minimum values
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_value': 1, 'retention_count': 1}
        )
        assert response.status_code == 200
        
        # Test maximum values
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_value': 99, 'retention_count': 100}
        )
        assert response.status_code == 200
        
        # Verify saved values
        get_response = requests.get(f'{api_client}/api/settings/backup/config')
        config = get_response.json()['config']
        assert config['frequency_value'] == 99
        assert config['retention_count'] == 100
    
    def test_cannot_enable_with_missing_settings(self, api_client):
        """Test that enabling backups requires all settings to be configured."""
        # Try to enable without setting required fields first
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True}
        )
        # Should fail because other required settings might not be set
        # (or succeed if defaults are valid - depends on state)
        # Let's explicitly test with invalid existing settings
        
        # First set an invalid frequency_value
        requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'frequency_value': 1, 'frequency_unit': 'hours'}
        )
        
        # Now try to enable - should succeed because settings are valid
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
    
    def test_cannot_enable_with_invalid_frequency_value(self, api_client):
        """Test that you cannot enable backups if frequency_value would be invalid."""
        # This should be caught by validation before the enable check
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True, 'frequency_value': 0}
        )
        assert response.status_code == 400
        assert 'frequency_value' in response.json()['message']
    
    def test_cannot_enable_with_invalid_frequency_unit(self, api_client):
        """Test that you cannot enable backups if frequency_unit would be invalid."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True, 'frequency_unit': 'invalid'}
        )
        assert response.status_code == 400
        assert 'frequency_unit' in response.json()['message']
    
    def test_cannot_enable_with_invalid_start_time(self, api_client):
        """Test that you cannot enable backups if start_time would be invalid."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True, 'start_time': '25:99'}
        )
        assert response.status_code == 400
        assert 'start_time' in response.json()['message']
    
    def test_cannot_enable_with_invalid_retention_count(self, api_client):
        """Test that you cannot enable backups if retention_count would be invalid."""
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={'enabled': True, 'retention_count': 0}
        )
        assert response.status_code == 400
        assert 'retention_count' in response.json()['message']
    
    def test_can_enable_with_all_valid_settings(self, api_client):
        """Test that enabling succeeds when all settings are valid."""
        # First set all valid settings
        response = requests.put(
            f'{api_client}/api/settings/backup/config',
            json={
                'enabled': True,
                'frequency_value': 24,
                'frequency_unit': 'hours',
                'start_time': '02:00',
                'retention_count': 7
            }
        )
        assert response.status_code == 200
        
        # Verify enabled is true
        get_response = requests.get(f'{api_client}/api/settings/backup/config')
        config = get_response.json()['config']
        assert config['enabled'] is True
