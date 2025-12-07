"""Tests for card scheduler API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestCardSchedulerAPI:
    """Test cases for card scheduler API endpoints."""
    
    def test_get_card_scheduler_status(self, api_client):
        """Test getting card scheduler status."""
        response = requests.get(f'{api_client}/api/settings/card-scheduler/status')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'status' in data
        assert 'running' in data['status']
        assert 'enabled' in data['status']
        assert isinstance(data['status']['running'], bool)
        assert isinstance(data['status']['enabled'], bool)
    
    def test_enable_card_scheduler(self, api_client):
        """Test enabling card scheduler."""
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'message' in data
        
        # Verify setting was updated
        status_response = requests.get(f'{api_client}/api/settings/card-scheduler/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True
    
    def test_disable_card_scheduler(self, api_client):
        """Test disabling card scheduler."""
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'message' in data
        
        # Verify setting was updated
        status_response = requests.get(f'{api_client}/api/settings/card-scheduler/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is False
    
    def test_card_scheduler_config_missing_enabled_field(self, api_client):
        """Test that config update fails when enabled field is missing."""
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'enabled field is required' in data['message']
    
    def test_card_scheduler_config_invalid_enabled_type(self, api_client):
        """Test that config update fails when enabled is not a boolean."""
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': 'yes'}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'must be a boolean' in data['message']
    
    def test_card_scheduler_toggle_multiple_times(self, api_client):
        """Test toggling card scheduler multiple times."""
        # Enable
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        
        # Disable
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': False}
        )
        assert response.status_code == 200
        
        # Enable again
        response = requests.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        
        # Verify final state
        status_response = requests.get(f'{api_client}/api/settings/card-scheduler/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True
