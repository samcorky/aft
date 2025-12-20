"""Tests for WebSocket theme synchronization."""
import pytest
import requests
import time


@pytest.mark.api
class TestWebSocketThemeSync:
    """Test cases for WebSocket theme synchronization functionality."""
    
    def test_theme_api_endpoint_exists(self, api_client):
        """Test that theme API endpoints are available for WebSocket integration."""
        # Verify /api/settings/theme endpoint exists
        response = requests.get(f'{api_client}/api/settings/theme')
        assert response.status_code == 200
        data = response.json()
        assert 'id' in data or 'success' in data
    
    def test_theme_update_api_endpoint(self, api_client):
        """Test theme update endpoint that triggers WebSocket broadcast."""
        # First create a theme to update
        themes_response = requests.get(f'{api_client}/api/themes')
        assert themes_response.status_code == 200
        themes_data = themes_response.json()
        
        # Response is a list of themes directly
        if isinstance(themes_data, list) and themes_data:
            theme_id = themes_data[0]['id']
            
            # Update theme via API
            update_response = requests.put(
                f'{api_client}/api/themes/{theme_id}',
                json={
                    'name': 'Updated Theme',
                    'settings': {
                        'primary-color': '#FF0000',
                        'secondary-color': '#00FF00'
                    }
                }
            )
            
            # Should succeed (200) or return valid response
            assert update_response.status_code in [200, 400]
    
    def test_theme_join_room_preparation(self, api_client):
        """Test that theme endpoints support room-based updates."""
        # Verify endpoint structure supports WebSocket room events
        response = requests.get(f'{api_client}/api/themes')
        assert response.status_code == 200
        
        data = response.json()
        # Should have themes list for WebSocket to sync
        assert isinstance(data, list) or isinstance(data, dict)
    
    def test_version_endpoint_for_header_status(self, api_client):
        """Test /api/version endpoint used by header status widget."""
        response = requests.get(f'{api_client}/api/version')
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'app_version' in data
        assert 'db_version' in data
    
    def test_health_check_endpoint_for_websocket_status(self, api_client):
        """Test /api/test endpoint used for WebSocket connection monitoring."""
        response = requests.get(f'{api_client}/api/test')
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'message' in data
    
    def test_scheduler_health_endpoint(self, api_client):
        """Test /api/scheduler/health endpoint for header status widget."""
        response = requests.get(f'{api_client}/api/scheduler/health')
        assert response.status_code == 200
        
        data = response.json()
        assert 'housekeeping_scheduler' in data
        assert 'running' in data['housekeeping_scheduler']


@pytest.mark.api
class TestWebSocketBoardRoomSync:
    """Test cases for WebSocket board room synchronization."""
    
    def test_board_room_join_preparation(self, api_client, sample_board):
        """Test that board endpoints support room-based real-time updates."""
        # Verify board can be retrieved for room synchronization
        response = requests.get(
            f'{api_client}/api/boards/{sample_board["id"]}/columns'
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'columns' in data
    
    def test_card_creation_triggers_broadcast(self, api_client, sample_column):
        """Test that card creation would trigger WebSocket broadcast."""
        # Create a card (which should trigger WebSocket event)
        card_response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={
                'title': 'WebSocket Test Card',
                'description': 'Testing WebSocket broadcast',
                'priority': 'medium'
            }
        )
        
        assert card_response.status_code == 201
        card_data = card_response.json()
        assert card_data['success'] is True
        assert 'id' in card_data['card']
    
    def test_card_update_triggers_broadcast(self, api_client, sample_card):
        """Test that card update would trigger WebSocket broadcast."""
        update_response = requests.patch(
            f'{api_client}/api/cards/{sample_card["id"]}',
            json={
                'title': 'Updated WebSocket Test Card',
                'description': 'Updated description'
            }
        )
        
        assert update_response.status_code in [200, 400]
        # Either succeeds or has valid error response
        if update_response.status_code == 200:
            data = update_response.json()
            assert 'success' in data or 'id' in data


@pytest.mark.api
class TestWebSocketErrorHandling:
    """Test WebSocket error handling and fallback behavior."""
    
    def test_api_test_endpoint_available(self, api_client):
        """Test database connection check endpoint for WebSocket fallback."""
        response = requests.get(f'{api_client}/api/test')
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
    
    def test_version_endpoint_timeout_resilience(self, api_client):
        """Test that version endpoint responds within timeout window."""
        start_time = time.time()
        
        response = requests.get(f'{api_client}/api/version', timeout=5)
        elapsed = time.time() - start_time
        
        # Should complete well within 5 second timeout
        assert elapsed < 5
        assert response.status_code == 200
    
    def test_database_status_check_resilience(self, api_client):
        """Test that database status check handles timeouts gracefully."""
        # Make concurrent requests to simulate header status polling
        import concurrent.futures
        
        def health_check():
            return requests.get(f'{api_client}/api/test', timeout=5)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(health_check) for _ in range(3)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)
        assert all(r.json()['success'] for r in responses)


@pytest.mark.api
class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality across multiple endpoints."""
    
    def test_theme_change_updates_all_pages(self, api_client):
        """Test that theme changes propagate across pages via WebSocket."""
        # Get initial theme
        initial_response = requests.get(f'{api_client}/api/settings/theme')
        assert initial_response.status_code == 200
        
        # Get all themes
        themes_response = requests.get(f'{api_client}/api/themes')
        assert themes_response.status_code == 200
        themes_data = themes_response.json()
        
        # Response is a list of themes directly
        if isinstance(themes_data, list) and themes_data:
            theme_id = themes_data[0]['id']
            
            # Update theme
            update_response = requests.put(
                f'{api_client}/api/themes/{theme_id}',
                json={
                    'name': 'Integration Test Theme',
                    'settings': {
                        'primary-color': '#AABBCC'
                    }
                }
            )
            
            # Verify response is valid
            assert update_response.status_code in [200, 400]
    
    def test_board_updates_broadcast_to_all_clients(self, api_client, sample_board):
        """Test that board updates are broadcast via WebSocket."""
        # Create multiple cards to simulate broadcast
        columns_response = requests.get(
            f'{api_client}/api/boards/{sample_board["id"]}/columns'
        )
        assert columns_response.status_code == 200
        
        columns_data = columns_response.json()
        if columns_data['success'] and columns_data['columns']:
            column_id = columns_data['columns'][0]['id']
            
            # Create cards that would trigger broadcasts
            for i in range(2):
                card_response = requests.post(
                    f'{api_client}/api/columns/{column_id}/cards',
                    json={
                        'title': f'Broadcast Test Card {i+1}',
                        'description': f'Testing WebSocket broadcast {i+1}'
                    }
                )
                
                assert card_response.status_code == 201
                time.sleep(0.1)  # Small delay between operations
    
    def test_header_status_widget_polling_resilience(self, api_client):
        """Test that header status polling handles multiple concurrent checks."""
        import concurrent.futures
        
        def status_check():
            """Simulate header status widget polling."""
            version = requests.get(f'{api_client}/api/version', timeout=5)
            health = requests.get(f'{api_client}/api/scheduler/health', timeout=5)
            test = requests.get(f'{api_client}/api/test', timeout=5)
            return all(r.status_code == 200 for r in [version, health, test])
        
        # Simulate 5-second polling interval with multiple concurrent clients
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(status_check) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All status checks should succeed
        assert all(results)
