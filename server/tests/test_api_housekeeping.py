"""Tests for housekeeping API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestHousekeepingAPI:
    """Test cases for housekeeping API endpoints."""
    
    def test_get_housekeeping_status(self, api_client):
        """Test getting housekeeping scheduler status."""
        response = requests.get(f'{api_client}/api/settings/housekeeping/status')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'status' in data
        assert 'running' in data['status']
        assert 'enabled' in data['status']
        assert 'check_interval' in data['status']
        assert 'app_version' in data['status']
        assert isinstance(data['status']['running'], bool)
        assert isinstance(data['status']['enabled'], bool)
        assert isinstance(data['status']['check_interval'], int)
        assert data['status']['check_interval'] == 60  # Thread runs every 60 seconds
    
    def test_enable_housekeeping(self, api_client):
        """Test enabling housekeeping scheduler."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'message' in data
        
        # Verify setting was updated
        status_response = requests.get(f'{api_client}/api/settings/housekeeping/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True
    
    def test_disable_housekeeping(self, api_client):
        """Test disabling housekeeping scheduler."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify setting was updated
        status_response = requests.get(f'{api_client}/api/settings/housekeeping/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is False
    
    def test_toggle_housekeeping_multiple_times(self, api_client):
        """Test toggling housekeeping enabled state multiple times."""
        # Enable
        response1 = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': True}
        )
        assert response1.status_code == 200
        
        # Disable
        response2 = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': False}
        )
        assert response2.status_code == 200
        
        # Enable again
        response3 = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': True}
        )
        assert response3.status_code == 200
        
        # Verify final state
        status_response = requests.get(f'{api_client}/api/settings/housekeeping/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True
    
    def test_housekeeping_config_missing_enabled_field(self, api_client):
        """Test updating housekeeping config without enabled field."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'enabled field is required' in data['message']
    
    def test_housekeeping_config_invalid_enabled_type(self, api_client):
        """Test updating housekeeping config with invalid enabled type."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': 'true'}  # String instead of boolean
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'must be a boolean' in data['message']
    
    def test_housekeeping_config_invalid_enabled_value(self, api_client):
        """Test updating housekeeping config with invalid enabled value."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': 1}  # Integer instead of boolean
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'must be a boolean' in data['message']
    
    def test_housekeeping_config_null_enabled(self, api_client):
        """Test updating housekeeping config with null enabled value."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': None}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_housekeeping_config_extra_fields_ignored(self, api_client):
        """Test that extra fields in housekeeping config are ignored."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={
                'enabled': True,
                'extra_field': 'should be ignored',
                'another_field': 123
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify only enabled was updated
        status_response = requests.get(f'{api_client}/api/settings/housekeeping/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True
    
    def test_housekeeping_config_no_body(self, api_client):
        """Test updating housekeeping config with no request body."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_housekeeping_config_invalid_json(self, api_client):
        """Test updating housekeeping config with invalid JSON."""
        response = requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            data='not valid json',
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_housekeeping_status_returns_scheduler_info(self, api_client):
        """Test that status endpoint returns scheduler information."""
        response = requests.get(f'{api_client}/api/settings/housekeeping/status')
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expected fields are present
        status = data['status']
        assert 'running' in status
        assert 'enabled' in status
        assert 'check_interval' in status
        assert 'app_version' in status
        
        # Verify types
        assert isinstance(status['running'], bool)
        assert isinstance(status['enabled'], bool)
        assert isinstance(status['check_interval'], int)
        assert isinstance(status['app_version'], str)
        
        # Verify reasonable values
        assert status['check_interval'] > 0
        assert len(status['app_version']) > 0
    
    def test_housekeeping_enabled_persists_across_requests(self, api_client):
        """Test that housekeeping enabled setting persists across multiple requests."""
        # Set to False
        requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': False}
        )
        
        # Check multiple times
        for _ in range(3):
            response = requests.get(f'{api_client}/api/settings/housekeeping/status')
            assert response.json()['status']['enabled'] is False
        
        # Set to True
        requests.put(
            f'{api_client}/api/settings/housekeeping/config',
            json={'enabled': True}
        )
        
        # Check multiple times
        for _ in range(3):
            response = requests.get(f'{api_client}/api/settings/housekeeping/status')
            assert response.json()['status']['enabled'] is True
    
    def test_housekeeping_not_in_backup_config(self, api_client):
        """Test that housekeeping settings are not exposed in backup config endpoint."""
        response = requests.get(f'{api_client}/api/settings/backup/config')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify housekeeping_enabled is NOT in backup config
        assert 'housekeeping_enabled' not in data
        # The backup endpoint uses key.replace("backup_", "") so it would be "housekeeping_enabled"
        # without the backup_ prefix if it was incorrectly included
