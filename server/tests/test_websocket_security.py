"""Security regression tests for Socket.IO authentication and authorization."""

from types import SimpleNamespace

import pytest

import app as app_module


pytestmark = [pytest.mark.unit, pytest.mark.security]


def _make_socket_client():
    """Create a Flask-SocketIO test client."""
    flask_client = app_module.app.test_client()
    return app_module.socketio.test_client(app_module.app, flask_test_client=flask_client)


def _ack_payload(ack_response):
    """Normalize Socket.IO callback payload shape for assertions."""
    payload = ack_response
    if isinstance(payload, list) and len(payload) == 1:
        payload = payload[0]

    assert isinstance(payload, dict)
    return payload


class TestWebSocketSecurity:
    """Regression tests for websocket auth and event-injection controls."""

    def test_unauthenticated_socket_connect_is_rejected(self, monkeypatch):
        """Critical #2 regression: unauthenticated Socket.IO connect must fail."""
        monkeypatch.setattr(app_module, 'get_authenticated_socket_user', lambda: None)

        client = _make_socket_client()
        assert client.is_connected() is False

    def test_authenticated_join_board_requires_authorized_access(self, monkeypatch):
        """join_board must enforce server-side board authorization."""
        user = SimpleNamespace(id=1)
        monkeypatch.setattr(app_module, 'get_authenticated_socket_user', lambda: user)

        def _mock_can_access_board(user_id, board_id):
            return board_id == 123, False

        monkeypatch.setattr(app_module, 'can_access_board', _mock_can_access_board)

        client = _make_socket_client()
        try:
            assert client.is_connected() is True

            allowed_ack = _ack_payload(client.emit('join_board', {'board_id': 123}, callback=True))
            assert allowed_ack['success'] is True
            assert allowed_ack['board_id'] == 123

            denied_ack = _ack_payload(client.emit('join_board', {'board_id': 999}, callback=True))
            assert denied_ack['success'] is False
            assert denied_ack['message'] == 'Access denied to this board'
        finally:
            client.disconnect()

    def test_client_mutation_event_is_rejected_and_not_rebroadcast(self, monkeypatch):
        """Client-emitted mutation events must be rejected by the server."""
        user = SimpleNamespace(id=1)
        monkeypatch.setattr(app_module, 'get_authenticated_socket_user', lambda: user)
        monkeypatch.setattr(app_module, 'can_access_board', lambda user_id, board_id: (True, False))

        sender = _make_socket_client()
        receiver = _make_socket_client()
        try:
            assert sender.is_connected() is True
            assert receiver.is_connected() is True

            sender.emit('join_board', {'board_id': 321}, callback=True)
            receiver.emit('join_board', {'board_id': 321}, callback=True)
            receiver.get_received()  # Clear connect/join events before mutation test.

            mutation_ack = _ack_payload(
                sender.emit(
                    'card_updated',
                    {'board_id': 321, 'card_id': 77, 'title': 'spoofed'},
                    callback=True,
                )
            )
            assert mutation_ack['success'] is False
            assert mutation_ack['event'] == 'card_updated'

            broadcast_events = [
                event for event in receiver.get_received() if event.get('name') == 'card_updated'
            ]
            assert broadcast_events == []
        finally:
            sender.disconnect()
            receiver.disconnect()
