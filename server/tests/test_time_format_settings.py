"""Tests for time format settings API."""
import pytest
import requests


@pytest.mark.api
class TestTimeFormatSettings:
    """Test time format preference setting endpoints."""
    
    def test_get_time_format_default(self, api_client):
        """Test that time_format has a default value of '24'."""
        response = requests.get(f'{api_client}/api/settings/time_format')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['key'] == 'time_format'
        # Value should be either '12' or '24' (valid time format)
        assert data['value'] in ['12', '24']
    
    def test_set_time_format_to_12_hour(self, api_client):
        """Test setting time format to 12-hour."""
        response = requests.put(
            f'{api_client}/api/settings/time_format',
            json={'value': '12'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] == '12'
        
        # Verify it persists
        get_response = requests.get(f'{api_client}/api/settings/time_format')
        assert get_response.json()['value'] == '12'
    
    def test_set_time_format_to_24_hour(self, api_client):
        """Test setting time format to 24-hour."""
        response = requests.put(
            f'{api_client}/api/settings/time_format',
            json={'value': '24'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] == '24'
        
        # Verify it persists
        get_response = requests.get(f'{api_client}/api/settings/time_format')
        assert get_response.json()['value'] == '24'
    
    def test_invalid_time_format_value(self, api_client):
        """Test that invalid time format values are rejected."""
        invalid_values = ['16', '0', 'AM/PM', 'invalid', '', 12, 24]
        
        for invalid_value in invalid_values:
            response = requests.put(
                f'{api_client}/api/settings/time_format',
                json={'value': invalid_value}
            )
            assert response.status_code == 400
            data = response.json()
            assert data['success'] is False
            assert 'invalid' in data['message'].lower() or 'must be' in data['message'].lower() or 'cannot be null' in data['message'].lower()
    
    def test_time_format_in_schema(self, api_client):
        """Test that time_format is included in the settings schema."""
        response = requests.get(f'{api_client}/api/settings/schema')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'time_format' in data['schema']
        
        time_format_schema = data['schema']['time_format']
        assert time_format_schema['type'] == 'string'
        assert time_format_schema['nullable'] is False
        assert 'time format preference' in time_format_schema['description'].lower()
    
    def test_time_format_toggle(self, api_client):
        """Test toggling between 12 and 24 hour formats multiple times."""
        # Set to 12-hour
        response = requests.put(
            f'{api_client}/api/settings/time_format',
            json={'value': '12'}
        )
        assert response.status_code == 200
        assert response.json()['value'] == '12'
        
        # Set to 24-hour
        response = requests.put(
            f'{api_client}/api/settings/time_format',
            json={'value': '24'}
        )
        assert response.status_code == 200
        assert response.json()['value'] == '24'
        
        # Set back to 12-hour
        response = requests.put(
            f'{api_client}/api/settings/time_format',
            json={'value': '12'}
        )
        assert response.status_code == 200
        assert response.json()['value'] == '12'
        
        # Verify final state
        get_response = requests.get(f'{api_client}/api/settings/time_format')
        assert get_response.json()['value'] == '12'
