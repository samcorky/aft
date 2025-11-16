"""Tests for settings API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestSettingsAPI:
    """Test cases for settings API endpoints."""
    
    def test_get_settings_schema(self, api_client):
        """Test getting settings schema."""
        response = requests.get(f'{api_client}/api/settings/schema')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'default_board' in data['schema']
        assert data['schema']['default_board']['type'] == 'integer'
    
    def test_get_setting_not_found(self, api_client):
        """Test getting a setting that doesn't exist."""
        response = requests.get(f'{api_client}/api/settings/default_board')
        # May be 404 or 200 with null depending on whether setting exists
        # Just check it doesn't error
        assert response.status_code in [200, 404]
    
    def test_create_setting(self, api_client, sample_board):
        """Test creating a new setting."""
        response = requests.put(f'{api_client}/api/settings/default_board', json={
            'value': sample_board['id']
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] == sample_board['id']
        
        # Cleanup
        requests.put(f'{api_client}/api/settings/default_board', json={'value': None})
    
    def test_create_setting_null_value(self, api_client):
        """Test creating a setting with null value."""
        response = requests.put(f'{api_client}/api/settings/default_board', json={
            'value': None
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] is None
    
    def test_update_setting(self, api_client, sample_board):
        """Test updating an existing setting."""
        # Create setting
        requests.put(f'{api_client}/api/settings/default_board', json={'value': sample_board['id']})
        
        # Update to null
        response = requests.put(f'{api_client}/api/settings/default_board', json={'value': None})
        assert response.status_code == 200
        data = response.json()
        assert data['value'] is None
    
    def test_setting_invalid_key(self, api_client):
        """Test creating a setting with invalid key."""
        response = requests.put(f'{api_client}/api/settings/invalid_key', json={
            'value': 'some_value'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'not allowed' in data['message']
    
    def test_setting_invalid_board_id(self, api_client):
        """Test setting default_board to non-existent board."""
        response = requests.put(f'{api_client}/api/settings/default_board', json={
            'value': 9999
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'does not exist' in data['message']
    
    def test_setting_invalid_type(self, api_client):
        """Test setting default_board with invalid type."""
        response = requests.put(f'{api_client}/api/settings/default_board', json={
            'value': 'not_an_integer'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        
        # Cleanup
        requests.put(f'{api_client}/api/settings/default_board', json={'value': None})
    
    def test_get_setting_after_create(self, api_client, sample_board):
        """Test retrieving a setting after creating it."""
        # Create setting
        requests.put(f'{api_client}/api/settings/default_board', json={'value': sample_board['id']})
        
        # Get setting
        response = requests.get(f'{api_client}/api/settings/default_board')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] == sample_board['id']
        
        # Cleanup
        requests.put(f'{api_client}/api/settings/default_board', json={'value': None})
