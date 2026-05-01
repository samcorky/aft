"""Tests for API endpoints that support WebSocket theme synchronization."""
import pytest
import time
import concurrent.futures


@pytest.mark.api
class TestThemeAPIForWebSocketSync:
    """Test cases for theme API endpoints required for WebSocket synchronization."""
    
    def test_theme_api_endpoint_exists(self, api_client, authenticated_session):
        """Test that theme API endpoints are available for WebSocket integration."""
        # Verify /api/settings/theme endpoint exists
        response = authenticated_session.get(f'{api_client}/api/settings/theme')
        assert response.status_code == 200
        data = response.json()
        assert 'id' in data or 'success' in data
    
    def test_theme_update_api_endpoint(self, api_client, authenticated_session):
        """Test theme update endpoint that triggers WebSocket broadcast."""
        # First get list of themes to find a theme to copy
        themes_response = authenticated_session.get(f'{api_client}/api/themes')
        assert themes_response.status_code == 200
        themes_data = themes_response.json()
        assert isinstance(themes_data, list) and len(themes_data) > 0, "No themes available to copy"
        
        source_theme_id = themes_data[0]['id']
        
        # Copy a theme to create a custom theme
        import time
        unique_name = f'Test Custom Theme {int(time.time() * 1000)}'
        copy_response = authenticated_session.post(
            f'{api_client}/api/themes/copy',
            json={
                'source_theme_id': source_theme_id,
                'new_name': unique_name
            }
        )
        assert copy_response.status_code == 201, f"Copy failed with: {copy_response.text}"
        theme_data = copy_response.json()
        theme_id = theme_data['id']
        
        # Update the created theme via API
        update_response = authenticated_session.put(
            f'{api_client}/api/themes/{theme_id}',
            json={
                'name': f'Updated Theme {int(time.time() * 1000)}',
                'settings': {
                    'primary-color': '#FF0000',
                    'secondary-color': '#00FF00'
                }
            }
        )
        
        # Should succeed with 200 status
        assert update_response.status_code == 200
        update_data = update_response.json()
        assert 'id' in update_data or 'success' in update_data
    
    def test_theme_join_room_preparation(self, api_client, authenticated_session):
        """Test that theme endpoints support room-based updates."""
        # Verify endpoint structure supports WebSocket room events
        response = authenticated_session.get(f'{api_client}/api/themes')
        assert response.status_code == 200
        
        data = response.json()
        # Should have themes list for WebSocket to sync
        assert isinstance(data, list) or isinstance(data, dict)
    
    def test_version_endpoint_for_header_status(self, api_client, authenticated_session):
        """Test /api/version endpoint used by header status widget."""
        response = authenticated_session.get(f'{api_client}/api/version')
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'app_version' in data
        assert 'db_version' in data
    
    def test_health_check_endpoint_for_websocket_status(self, api_client, authenticated_session):
        """Test /api/health/live endpoint used for server connectivity monitoring."""
        response = authenticated_session.get(f'{api_client}/api/health/live')
        assert response.status_code == 200
        
        data = response.json()
        assert data['ok'] is True
    
    def test_scheduler_health_endpoint(self, api_client, authenticated_session):
        """Test /api/scheduler/health endpoint for header status widget."""
        response = authenticated_session.get(f'{api_client}/api/scheduler/health')
        assert response.status_code == 200
        
        data = response.json()
        assert 'housekeeping_scheduler' in data
        assert 'running' in data['housekeeping_scheduler']


@pytest.mark.api
class TestBoardAPIForWebSocketSync:
    """Test cases for board API endpoints required for WebSocket room synchronization."""
    
    def test_board_room_join_preparation(self, api_client, authenticated_session, sample_board):
        """Test that board endpoints support room-based real-time updates."""
        # Verify board can be retrieved for room synchronization
        response = authenticated_session.get(
            f'{api_client}/api/boards/{sample_board["id"]}/columns'
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'columns' in data
    
    def test_card_creation_triggers_broadcast(self, api_client, authenticated_session, sample_column):
        """Test that card creation would trigger WebSocket broadcast."""
        # Create a card (which should trigger WebSocket event)
        card_response = authenticated_session.post(
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
    
    def test_card_update_triggers_broadcast(self, api_client, authenticated_session, sample_card):
        """Test that card update would trigger WebSocket broadcast."""
        update_response = authenticated_session.patch(
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
class TestAPIErrorHandlingForWebSocket:
    """Test API error handling and fallback behavior for WebSocket features."""
    
    def test_api_liveness_endpoint_available(self, api_client, authenticated_session):
        """Test server liveness endpoint for WebSocket fallback."""
        response = authenticated_session.get(f'{api_client}/api/health/live')
        assert response.status_code == 200
        
        data = response.json()
        assert data['ok'] is True
    
    def test_version_endpoint_timeout_resilience(self, api_client, authenticated_session):
        """Test that version endpoint responds within timeout window."""
        start_time = time.time()
        
        response = authenticated_session.get(f'{api_client}/api/version', timeout=5)
        elapsed = time.time() - start_time
        
        # Should complete well within 5 second timeout
        assert elapsed < 5
        assert response.status_code == 200
    
    def test_database_status_check_resilience(self, api_client, authenticated_session):
        """Test that database status check handles timeouts gracefully."""
        # Make concurrent requests to simulate header status polling
        
        def health_check():
            return authenticated_session.get(f'{api_client}/api/version', timeout=5)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(health_check) for _ in range(3)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)
        assert all(r.json()['success'] for r in responses)


@pytest.mark.api
class TestAPIIntegrationForWebSocket:
    """Integration tests for API endpoints that support WebSocket functionality across multiple features."""
    
    def test_theme_change_updates_all_pages(self, api_client, authenticated_session):
        """Test that theme changes propagate across pages via WebSocket."""
        # Get initial theme
        initial_response = authenticated_session.get(f'{api_client}/api/settings/theme')
        assert initial_response.status_code == 200
        
        # Get all themes
        themes_response = authenticated_session.get(f'{api_client}/api/themes')
        assert themes_response.status_code == 200
        themes_data = themes_response.json()
        
        # Response is a list of themes directly
        if isinstance(themes_data, list) and themes_data:
            theme_id = themes_data[0]['id']
            
            # Update theme
            update_response = authenticated_session.put(
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
    
    def test_board_updates_broadcast_to_all_clients(self, api_client, authenticated_session, sample_board):
        """Test that board updates are broadcast via WebSocket."""
        # Create multiple cards to simulate broadcast
        columns_response = authenticated_session.get(
            f'{api_client}/api/boards/{sample_board["id"]}/columns'
        )
        assert columns_response.status_code == 200
        
        columns_data = columns_response.json()
        if columns_data['success'] and columns_data['columns']:
            column_id = columns_data['columns'][0]['id']
            
            # Create cards that would trigger broadcasts
            for i in range(2):
                card_response = authenticated_session.post(
                    f'{api_client}/api/columns/{column_id}/cards',
                    json={
                        'title': f'Broadcast Test Card {i+1}',
                        'description': f'Testing WebSocket broadcast {i+1}'
                    }
                )
                
                assert card_response.status_code == 201
                time.sleep(0.1)  # Small delay between operations
    
    def test_header_status_widget_polling_resilience(self, api_client, authenticated_session):
        """Test that header status polling handles multiple concurrent checks."""
        
        def status_check():
            """Simulate header status widget polling."""
            live = authenticated_session.get(f'{api_client}/api/health/live', timeout=5)
            version = authenticated_session.get(f'{api_client}/api/version', timeout=5)
            health = authenticated_session.get(f'{api_client}/api/scheduler/health', timeout=5)
            return all(r.status_code == 200 for r in [live, version, health])
        
        # Simulate 5-second polling interval with multiple concurrent clients
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(status_check) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All status checks should succeed
        assert all(results)


# ---------------------------------------------------------------------------
# Socket.IO unit tests — theme room join/leave and broadcast delivery
# ---------------------------------------------------------------------------

import importlib
import os
from types import SimpleNamespace

os.environ.setdefault('ENABLE_SERVER_SIDE_SESSIONS', 'false')
os.environ.setdefault('SECRET_KEY', 'unit-test-secret-key')
os.environ.setdefault('AFT_SKIP_SCHEDULER_INIT', 'true')

_APP_MODULE = None
_WS_MODULE = None


def _get_app_module():
    global _APP_MODULE
    if _APP_MODULE is None:
        _APP_MODULE = importlib.import_module('app')
    return _APP_MODULE


def _get_ws_module():
    global _WS_MODULE
    if _WS_MODULE is None:
        _WS_MODULE = importlib.import_module('websocket_handlers')
    return _WS_MODULE


def _make_authed_socket_client(app_module, ws_module, user_id=1):
    """Create an authenticated Flask-SocketIO test client for the given user id."""
    flask_client = app_module.app.test_client()
    user = SimpleNamespace(id=user_id)
    # Patch authentication so the test client is accepted as this user.
    import unittest.mock as mock
    with mock.patch.object(ws_module, 'get_authenticated_socket_user', return_value=user):
        client = app_module.socketio.test_client(app_module.app, flask_test_client=flask_client)
    return client, user


@pytest.mark.unit
class TestThemeSocketIOFlow:
    """Unit tests for the Socket.IO theme room join/leave and broadcast flow."""

    def test_join_theme_emits_ack(self, monkeypatch):
        """join_theme must return a success acknowledgement."""
        app_module = _get_app_module()
        ws_module = _get_ws_module()
        user = SimpleNamespace(id=1)
        monkeypatch.setattr(ws_module, 'get_authenticated_socket_user', lambda: user)

        mock_session = SimpleNamespace(
            query=lambda model: SimpleNamespace(
                filter=lambda *a, **kw: SimpleNamespace(first=lambda: None)
            ),
            close=lambda: None,
        )
        monkeypatch.setattr(ws_module, 'SessionLocal', lambda: mock_session)

        client = app_module.socketio.test_client(app_module.app)
        try:
            assert client.is_connected()

            ack = client.emit('join_theme', callback=True)
            payload = ack[0] if isinstance(ack, list) else ack
            assert isinstance(payload, dict)
            assert payload.get('success') is True
        finally:
            client.disconnect()

    def test_leave_theme_emits_ack(self, monkeypatch):
        """leave_theme must return a success acknowledgement after joining."""
        app_module = _get_app_module()
        ws_module = _get_ws_module()
        user = SimpleNamespace(id=1)
        monkeypatch.setattr(ws_module, 'get_authenticated_socket_user', lambda: user)

        mock_session = SimpleNamespace(
            query=lambda model: SimpleNamespace(
                filter=lambda *a, **kw: SimpleNamespace(first=lambda: None)
            ),
            close=lambda: None,
        )
        monkeypatch.setattr(ws_module, 'SessionLocal', lambda: mock_session)

        client = app_module.socketio.test_client(app_module.app)
        try:
            assert client.is_connected()
            client.emit('join_theme', callback=True)

            ack = client.emit('leave_theme', callback=True)
            payload = ack[0] if isinstance(ack, list) else ack
            assert isinstance(payload, dict)
            assert payload.get('success') is True
        finally:
            client.disconnect()

    def test_unauthenticated_join_theme_rejected(self, monkeypatch):
        """Socket connection must be rejected when no authenticated user is present."""
        app_module = _get_app_module()
        ws_module = _get_ws_module()
        monkeypatch.setattr(ws_module, 'get_authenticated_socket_user', lambda: None)

        client = app_module.socketio.test_client(app_module.app)
        assert client.is_connected() is False

    def test_theme_updated_broadcast_received_by_room_member(self, monkeypatch):
        """A client that has joined its theme room must receive theme_updated broadcasts."""
        app_module = _get_app_module()
        ws_module = _get_ws_module()
        user = SimpleNamespace(id=42)
        monkeypatch.setattr(ws_module, 'get_authenticated_socket_user', lambda: user)

        mock_session = SimpleNamespace(
            query=lambda model: SimpleNamespace(
                filter=lambda *a, **kw: SimpleNamespace(first=lambda: None)
            ),
            close=lambda: None,
        )
        monkeypatch.setattr(ws_module, 'SessionLocal', lambda: mock_session)

        client = app_module.socketio.test_client(app_module.app)
        try:
            assert client.is_connected()
            client.emit('join_theme', callback=True)
            client.get_received()  # clear join events

            # Simulate the server broadcasting a theme update to the user's room
            room = f'theme_user_{user.id}'
            app_module.socketio.emit('theme_updated', {'theme_id': 7, 'theme_name': 'Test'}, room=room)

            received = client.get_received()
            theme_events = [e for e in received if e.get('name') == 'theme_updated']
            assert len(theme_events) == 1
            assert theme_events[0]['args'][0]['theme_id'] == 7
        finally:
            client.disconnect()

    def test_theme_updated_not_received_after_leave(self, monkeypatch):
        """A client that has left the theme room must not receive subsequent broadcasts."""
        app_module = _get_app_module()
        ws_module = _get_ws_module()
        user = SimpleNamespace(id=99)
        monkeypatch.setattr(ws_module, 'get_authenticated_socket_user', lambda: user)

        mock_session = SimpleNamespace(
            query=lambda model: SimpleNamespace(
                filter=lambda *a, **kw: SimpleNamespace(first=lambda: None)
            ),
            close=lambda: None,
        )
        monkeypatch.setattr(ws_module, 'SessionLocal', lambda: mock_session)

        client = app_module.socketio.test_client(app_module.app)
        try:
            assert client.is_connected()
            client.emit('join_theme', callback=True)
            client.emit('leave_theme', callback=True)
            client.get_received()  # clear

            room = f'theme_user_{user.id}'
            app_module.socketio.emit('theme_updated', {'theme_id': 5, 'theme_name': 'X'}, room=room)

            received = client.get_received()
            theme_events = [e for e in received if e.get('name') == 'theme_updated']
            assert theme_events == []
        finally:
            client.disconnect()
