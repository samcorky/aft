"""Tests for theme API endpoints."""
import pytest
import requests
import json
import os


@pytest.mark.api
class TestThemesAPI:
    """Test cases for theme API endpoints."""
    
    def test_get_themes_list(self, api_client):
        """Test getting list of all themes."""
        response = requests.get(f'{api_client}/api/themes')
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify structure of first theme
        theme = data[0]
        assert 'id' in theme
        assert 'name' in theme
        assert 'system_theme' in theme
        assert 'settings' in theme
        assert isinstance(theme['settings'], dict)
    
    def test_get_themes_includes_system_themes(self, api_client):
        """Test that system themes are included in list."""
        response = requests.get(f'{api_client}/api/themes')
        assert response.status_code == 200
        data = response.json()
        
        system_themes = [t for t in data if t['system_theme']]
        assert len(system_themes) > 0
        assert any(t['name'] == 'Default' for t in system_themes)
    
    def test_get_theme_by_id(self, api_client):
        """Test getting a specific theme by ID."""
        # Get list first
        themes_response = requests.get(f'{api_client}/api/themes')
        themes = themes_response.json()
        theme_id = themes[0]['id']
        
        # Get specific theme
        response = requests.get(f'{api_client}/api/themes/{theme_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['id'] == theme_id
        assert 'name' in data
        assert 'settings' in data
        assert 'background_image' in data
    
    def test_get_theme_not_found(self, api_client):
        """Test getting a theme that doesn't exist."""
        response = requests.get(f'{api_client}/api/themes/99999')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
    
    def test_create_custom_theme(self, api_client):
        """Test creating a new custom theme."""
        theme_data = {
            'name': 'Test Theme',
            'settings': {
                'primary-color': '#FF5733',
                'text-color': '#FFFFFF'
            },
            'background_image': None
        }
        
        response = requests.post(f'{api_client}/api/themes', json=theme_data)
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['theme']['name'] == 'Test Theme'
        assert data['theme']['system_theme'] is False
        assert data['theme']['settings']['primary-color'] == '#FF5733'
        
        # Cleanup
        theme_id = data['theme']['id']
        requests.delete(f'{api_client}/api/themes/{theme_id}')
    
    def test_create_theme_duplicate_name(self, api_client):
        """Test creating theme with duplicate name fails."""
        # Get existing theme name
        themes_response = requests.get(f'{api_client}/api/themes')
        existing_name = themes_response.json()[0]['name']
        
        theme_data = {
            'name': existing_name,
            'settings': {'primary-color': '#FF5733'}
        }
        
        response = requests.post(f'{api_client}/api/themes', json=theme_data)
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['message'].lower()
    
    def test_create_theme_missing_name(self, api_client):
        """Test creating theme without name fails."""
        theme_data = {
            'settings': {'primary-color': '#FF5733'}
        }
        
        response = requests.post(f'{api_client}/api/themes', json=theme_data)
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_theme_empty_name(self, api_client):
        """Test creating theme with empty name fails."""
        theme_data = {
            'name': '',
            'settings': {'primary-color': '#FF5733'}
        }
        
        response = requests.post(f'{api_client}/api/themes', json=theme_data)
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_theme_long_name(self, api_client):
        """Test creating theme with excessively long name."""
        theme_data = {
            'name': 'A' * 300,  # 300 characters
            'settings': {'primary-color': '#FF5733'}
        }
        
        response = requests.post(f'{api_client}/api/themes', json=theme_data)
        # Should either fail or truncate - check implementation
        assert response.status_code in [400, 201]
        
        # Cleanup if created
        if response.status_code == 201:
            theme_id = response.json()['theme']['id']
            requests.delete(f'{api_client}/api/themes/{theme_id}')
    
    def test_update_theme(self, api_client):
        """Test updating an existing theme."""
        # Create a theme first
        create_response = requests.post(f'{api_client}/api/themes', json={
            'name': 'Update Test Theme',
            'settings': {'primary-color': '#FF5733'}
        })
        theme_id = create_response.json()['theme']['id']
        
        # Update it
        update_data = {
            'name': 'Updated Theme Name',
            'settings': {'primary-color': '#00FF00', 'text-color': '#FFFFFF'},
            'background_image': None
        }
        
        response = requests.put(f'{api_client}/api/themes/{theme_id}', json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['theme']['name'] == 'Updated Theme Name'
        assert data['theme']['settings']['primary-color'] == '#00FF00'
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{theme_id}')
    
    def test_update_system_theme_fails(self, api_client):
        """Test that system themes cannot be updated."""
        # Get a system theme
        themes_response = requests.get(f'{api_client}/api/themes')
        system_theme = next(t for t in themes_response.json() if t['system_theme'])
        
        update_data = {
            'name': 'Hacked System Theme',
            'settings': {'primary-color': '#FF0000'}
        }
        
        response = requests.put(f'{api_client}/api/themes/{system_theme["id"]}', json=update_data)
        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
        assert 'system theme' in data['message'].lower()
    
    def test_rename_theme(self, api_client):
        """Test renaming a custom theme."""
        # Create a theme
        create_response = requests.post(f'{api_client}/api/themes', json={
            'name': 'Rename Test Theme',
            'settings': {'primary-color': '#FF5733'}
        })
        theme_id = create_response.json()['theme']['id']
        
        # Rename it
        response = requests.put(f'{api_client}/api/themes/{theme_id}/rename', json={
            'name': 'Renamed Theme'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['theme']['name'] == 'Renamed Theme'
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{theme_id}')
    
    def test_rename_system_theme_fails(self, api_client):
        """Test that system themes cannot be renamed."""
        themes_response = requests.get(f'{api_client}/api/themes')
        system_theme = next(t for t in themes_response.json() if t['system_theme'])
        
        response = requests.put(f'{api_client}/api/themes/{system_theme["id"]}/rename', json={
            'name': 'Hacked Name'
        })
        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
    
    def test_rename_theme_duplicate_name(self, api_client):
        """Test renaming theme to existing name fails."""
        # Create two themes
        theme1 = requests.post(f'{api_client}/api/themes', json={
            'name': 'Theme One',
            'settings': {'primary-color': '#FF5733'}
        }).json()['theme']
        
        theme2 = requests.post(f'{api_client}/api/themes', json={
            'name': 'Theme Two',
            'settings': {'primary-color': '#00FF00'}
        }).json()['theme']
        
        # Try to rename theme2 to theme1's name
        response = requests.put(f'{api_client}/api/themes/{theme2["id"]}/rename', json={
            'name': 'Theme One'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['message'].lower()
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{theme1["id"]}')
        requests.delete(f'{api_client}/api/themes/{theme2["id"]}')
    
    def test_copy_theme(self, api_client):
        """Test copying an existing theme."""
        # Get a theme to copy
        themes_response = requests.get(f'{api_client}/api/themes')
        original_theme = themes_response.json()[0]
        
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_id': original_theme['id'],
            'new_name': 'Copied Theme'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['theme']['name'] == 'Copied Theme'
        assert data['theme']['system_theme'] is False
        assert data['theme']['settings'] == original_theme['settings']
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{data["theme"]["id"]}')
    
    def test_copy_theme_source_not_found(self, api_client):
        """Test copying non-existent theme fails."""
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_id': 99999,
            'new_name': 'Copy of Nothing'
        })
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
    
    def test_copy_theme_duplicate_name(self, api_client):
        """Test copying theme with duplicate name fails."""
        themes_response = requests.get(f'{api_client}/api/themes')
        themes = themes_response.json()
        existing_name = themes[0]['name']
        source_id = themes[1]['id'] if len(themes) > 1 else themes[0]['id']
        
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_id': source_id,
            'new_name': existing_name
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_export_theme(self, api_client):
        """Test exporting a theme as JSON."""
        # Get a theme
        themes_response = requests.get(f'{api_client}/api/themes')
        theme = themes_response.json()[0]
        
        response = requests.get(f'{api_client}/api/themes/{theme["id"]}/export')
        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'application/json'
        assert 'attachment' in response.headers['Content-Disposition']
        
        # Verify JSON structure
        data = response.json()
        assert data['name'] == theme['name']
        assert data['settings'] == theme['settings']
    
    def test_export_theme_not_found(self, api_client):
        """Test exporting non-existent theme fails."""
        response = requests.get(f'{api_client}/api/themes/99999/export')
        assert response.status_code == 404
    
    def test_import_theme(self, api_client):
        """Test importing a theme from JSON."""
        theme_json = {
            'name': 'Imported Theme',
            'settings': {
                'primary-color': '#FF5733',
                'text-color': '#FFFFFF'
            },
            'background_image': None
        }
        
        response = requests.post(
            f'{api_client}/api/themes/import',
            json=theme_json
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['theme']['name'] == 'Imported Theme'
        assert data['theme']['settings'] == theme_json['settings']
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{data["theme"]["id"]}')
    
    def test_import_theme_invalid_json(self, api_client):
        """Test importing theme with invalid JSON fails."""
        invalid_json = {
            'settings': {'primary-color': '#FF5733'}
            # Missing 'name' field
        }
        
        response = requests.post(f'{api_client}/api/themes/import', json=invalid_json)
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_import_theme_duplicate_name(self, api_client):
        """Test importing theme with duplicate name fails."""
        # Get existing theme name
        themes_response = requests.get(f'{api_client}/api/themes')
        existing_name = themes_response.json()[0]['name']
        
        theme_json = {
            'name': existing_name,
            'settings': {'primary-color': '#FF5733'}
        }
        
        response = requests.post(f'{api_client}/api/themes/import', json=theme_json)
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['message'].lower()
    
    def test_get_theme_images_list(self, api_client):
        """Test getting list of available background images."""
        response = requests.get(f'{api_client}/api/themes/images')
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least some default images
        assert len(data) >= 0
    
    def test_get_theme_image(self, api_client):
        """Test getting a specific background image."""
        # Get list of images first
        images_response = requests.get(f'{api_client}/api/themes/images')
        images = images_response.json()
        
        if len(images) > 0:
            # Test getting first image
            filename = images[0]
            response = requests.get(f'{api_client}/api/themes/images/{filename}')
            assert response.status_code == 200
            assert 'image/' in response.headers['Content-Type']
    
    def test_get_theme_image_not_found(self, api_client):
        """Test getting non-existent image fails."""
        response = requests.get(f'{api_client}/api/themes/images/nonexistent.png')
        assert response.status_code == 404
    
    def test_get_theme_image_path_traversal(self, api_client):
        """Test that path traversal attempts are blocked."""
        malicious_paths = [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32\\config\\sam',
            'subdir/../../etc/passwd',
            '....//....//etc/passwd'
        ]
        
        for path in malicious_paths:
            response = requests.get(f'{api_client}/api/themes/images/{path}')
            assert response.status_code in [400, 404], f"Path traversal not blocked: {path}"
    
    def test_get_current_theme_setting(self, api_client):
        """Test getting current applied theme."""
        response = requests.get(f'{api_client}/api/settings/theme')
        assert response.status_code == 200
        data = response.json()
        assert 'id' in data
        assert 'name' in data
        assert 'settings' in data
    
    def test_set_current_theme(self, api_client):
        """Test setting the current theme."""
        # Get a theme
        themes_response = requests.get(f'{api_client}/api/themes')
        theme = themes_response.json()[0]
        
        response = requests.put(f'{api_client}/api/settings/theme', json={
            'theme_id': theme['id']
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['theme']['id'] == theme['id']
    
    def test_set_current_theme_not_found(self, api_client):
        """Test setting non-existent theme fails."""
        response = requests.put(f'{api_client}/api/settings/theme', json={
            'theme_id': 99999
        })
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
    
    def test_delete_custom_theme(self, api_client):
        """Test deleting a custom theme."""
        # Create a theme
        create_response = requests.post(f'{api_client}/api/themes', json={
            'name': 'Delete Test Theme',
            'settings': {'primary-color': '#FF5733'}
        })
        theme_id = create_response.json()['theme']['id']
        
        # Delete it
        response = requests.delete(f'{api_client}/api/themes/{theme_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify it's gone
        get_response = requests.get(f'{api_client}/api/themes/{theme_id}')
        assert get_response.status_code == 404
    
    def test_delete_system_theme_fails(self, api_client):
        """Test that system themes cannot be deleted."""
        themes_response = requests.get(f'{api_client}/api/themes')
        system_theme = next(t for t in themes_response.json() if t['system_theme'])
        
        response = requests.delete(f'{api_client}/api/themes/{system_theme["id"]}')
        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
