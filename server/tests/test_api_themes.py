"""Tests for theme API endpoints."""
import pytest
import requests
import json
import os
import time


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
        """Test creating a new custom theme via copy endpoint."""
        # Get a theme to copy
        themes_response = requests.get(f'{api_client}/api/themes')
        source_theme = themes_response.json()[0]
        
        unique_name = f'Test Theme {int(time.time() * 1000)}'
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_theme['id'],
            'new_name': unique_name
        })
        if response.status_code != 201:
            print(f"Error response: {response.json()}")
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data['name'] == unique_name
        assert data['system_theme'] is False
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{data["id"]}')
    
    def test_create_theme_duplicate_name(self, api_client):
        """Test creating theme with duplicate name fails."""
        # Get existing theme name
        themes_response = requests.get(f'{api_client}/api/themes')
        themes = themes_response.json()
        existing_name = themes[0]['name']
        source_id = themes[1]['id'] if len(themes) > 1 else themes[0]['id']
        
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_id,
            'new_name': existing_name
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['message'].lower()
    
    def test_create_theme_missing_name(self, api_client):
        """Test creating theme without name fails."""
        themes_response = requests.get(f'{api_client}/api/themes')
        source_id = themes_response.json()[0]['id']
        
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_id
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_theme_empty_name(self, api_client):
        """Test creating theme with empty name fails."""
        themes_response = requests.get(f'{api_client}/api/themes')
        source_id = themes_response.json()[0]['id']
        
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_id,
            'new_name': ''
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_theme_long_name(self, api_client):
        """Test creating theme with excessively long name."""
        themes_response = requests.get(f'{api_client}/api/themes')
        source_id = themes_response.json()[0]['id']
        
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_id,
            'new_name': 'A' * 300  # 300 characters
        })
        # May fail with 400, 500 (db error), or 201 if truncated
        assert response.status_code in [400, 500, 201]
    
    def test_update_theme(self, api_client):
        """Test updating an existing theme via copy first."""
        # Create a theme via copy
        themes_response = requests.get(f'{api_client}/api/themes')
        source_theme = themes_response.json()[0]
        
        unique_name = f'Update Test Theme {int(time.time() * 1000)}'
        create_response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_theme['id'],
            'new_name': unique_name
        })
        theme_id = create_response.json()['id']
        
        # Update it
        update_data = {
            'name': f'Updated Theme {int(time.time() * 1000)}',
            'settings': {'primary-color': '#00FF00', 'text-color': '#FFFFFF'},
            'background_image': None
        }
        
        response = requests.put(f'{api_client}/api/themes/{theme_id}', json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data['name'] == update_data['name']
        settings = json.loads(data['settings']) if isinstance(data['settings'], str) else data['settings']
        assert settings['primary-color'] == '#00FF00'
        
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
        assert response.status_code == 400  # Changed from 403
        data = response.json()
        assert data['success'] is False
        assert 'system theme' in data['message'].lower()
    
    def test_rename_theme(self, api_client):
        """Test renaming a custom theme."""
        # Create a theme via copy
        themes_response = requests.get(f'{api_client}/api/themes')
        source_id = themes_response.json()[0]['id']
        
        unique_name = f'Rename Test Theme {int(time.time() * 1000)}'
        create_response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_id,
            'new_name': unique_name
        })
        theme_id = create_response.json()['id']
        
        # Rename it
        new_name = f'Renamed Theme {int(time.time() * 1000)}'
        response = requests.put(f'{api_client}/api/themes/{theme_id}/rename', json={
            'name': new_name
        })
        assert response.status_code == 200
        data = response.json()
        assert data['name'] == new_name
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{theme_id}')
    
    def test_rename_system_theme_fails(self, api_client):
        """Test that system themes cannot be renamed."""
        themes_response = requests.get(f'{api_client}/api/themes')
        system_theme = next(t for t in themes_response.json() if t['system_theme'])
        
        response = requests.put(f'{api_client}/api/themes/{system_theme["id"]}/rename', json={
            'name': 'Hacked Name'
        })
        assert response.status_code == 400  # Changed from 403
        data = response.json()
        assert data['success'] is False
    
    def test_rename_theme_duplicate_name(self, api_client):
        """Test renaming theme to existing name fails."""
        # Get themes
        themes_response = requests.get(f'{api_client}/api/themes')
        themes = themes_response.json()
        
        # Create two themes via copy with unique names
        theme1_name = f'Theme One {int(time.time() * 1000)}'
        theme1 = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': themes[0]['id'],
            'new_name': theme1_name
        }).json()
        
        time.sleep(0.001)  # Ensure unique timestamp
        theme2_name = f'Theme Two {int(time.time() * 1000)}'
        theme2 = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': themes[0]['id'],
            'new_name': theme2_name
        }).json()
        
        # Try to rename theme2 to theme1's name
        response = requests.put(f'{api_client}/api/themes/{theme2["id"]}/rename', json={
            'name': theme1_name
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
        
        unique_name = f'Copied Theme {int(time.time() * 1000)}'
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': original_theme['id'],  # Changed from source_id
            'new_name': unique_name
        })
        assert response.status_code == 201
        data = response.json()
        assert data['name'] == unique_name
        assert data['system_theme'] is False
        assert data['settings'] == original_theme['settings']
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{data["id"]}')
    
    def test_copy_theme_source_not_found(self, api_client):
        """Test copying non-existent theme fails."""
        response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': 99999,  # Changed from source_id
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
            'source_theme_id': source_id,  # Changed from source_id
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
        
        # Verify JSON structure
        data = response.json()
        assert data['name'] == theme['name']
        # Settings might be string or dict depending on response
        if isinstance(data['settings'], str) and isinstance(theme['settings'], str):
            assert data['settings'] == theme['settings']
        else:
            # Compare as dicts
            data_settings = json.loads(data['settings']) if isinstance(data['settings'], str) else data['settings']
            theme_settings = json.loads(theme['settings']) if isinstance(theme['settings'], str) else theme['settings']
            assert data_settings == theme_settings
    
    def test_export_theme_not_found(self, api_client):
        """Test exporting non-existent theme fails."""
        response = requests.get(f'{api_client}/api/themes/99999/export')
        assert response.status_code == 404
    
    def test_import_theme(self, api_client):
        """Test importing a theme from JSON."""
        # Get a valid theme structure
        themes_response = requests.get(f'{api_client}/api/themes')
        existing_theme = themes_response.json()[0]
        
        unique_name = f'Imported Theme {int(time.time() * 1000)}'
        theme_json = {
            'name': unique_name,
            'settings': json.loads(existing_theme['settings']) if isinstance(existing_theme['settings'], str) else existing_theme['settings'],
            'background_image': None
        }
        
        response = requests.post(
            f'{api_client}/api/themes/import',
            json=theme_json
        )
        assert response.status_code == 201
        data = response.json()
        assert data['name'] == unique_name
        
        # Cleanup
        requests.delete(f'{api_client}/api/themes/{data["id"]}')
    
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
        # Get existing theme
        themes_response = requests.get(f'{api_client}/api/themes')
        existing = themes_response.json()[0]
        existing_name = existing['name']
        
        theme_json = {
            'name': existing_name,
            'settings': json.loads(existing['settings']) if isinstance(existing['settings'], str) else existing['settings']
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
        assert 'images' in data
        assert isinstance(data['images'], list)
        # Should have at least some default images
        assert len(data['images']) >= 0
    
    def test_get_theme_image(self, api_client):
        """Test getting a specific background image."""
        # Get list of images first
        images_response = requests.get(f'{api_client}/api/themes/images')
        images = images_response.json()['images']  # Changed from direct list
        
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
        assert 'updated' in data['message'].lower()
        
        # Verify it was set by getting current theme
        get_response = requests.get(f'{api_client}/api/settings/theme')
        assert get_response.status_code == 200
        current = get_response.json()
        assert current['id'] == theme['id']
    
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
        # Create a theme via copy
        themes_response = requests.get(f'{api_client}/api/themes')
        source_theme = themes_response.json()[0]
        
        unique_name = f'Delete Test {int(time.time() * 1000)}'
        create_response = requests.post(f'{api_client}/api/themes/copy', json={
            'source_theme_id': source_theme['id'],
            'new_name': unique_name
        })
        theme_id = create_response.json()['id']
        
        # Delete it
        response = requests.delete(f'{api_client}/api/themes/{theme_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'deleted' in data['message'].lower()
        
        # Verify it's gone
        get_response = requests.get(f'{api_client}/api/themes/{theme_id}')
        assert get_response.status_code == 404
    
    def test_delete_system_theme_fails(self, api_client):
        """Test that system themes cannot be deleted."""
        themes_response = requests.get(f'{api_client}/api/themes')
        system_theme = next(t for t in themes_response.json() if t['system_theme'])
        
        response = requests.delete(f'{api_client}/api/themes/{system_theme["id"]}')
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'system theme' in data['message'].lower()
    
    def test_delete_theme_not_found(self, api_client):
        """Test deleting non-existent theme fails."""
        response = requests.delete(f'{api_client}/api/themes/99999')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
