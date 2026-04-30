"""WebSocket event handlers for real-time board and theme updates.

Call register_websocket_handlers(socketio_instance) from app.py after
creating the SocketIO instance to register all handlers.
"""

import json
import logging

from flask import request
from flask_socketio import emit, join_room, leave_room

from auth import get_authenticated_socket_user
from database import SessionLocal
from models import Setting
from utils import can_access_board, get_user_scoped_query

logger = logging.getLogger(__name__)

# Set by register_websocket_handlers — used by handle_connect to honour the testing flag
_REJECT_SOCKETIO_CONNECTIONS = False


def register_websocket_handlers(socketio, reject_connections: bool = False):
    """Register all Socket.IO event handlers on *socketio*.

    Args:
        socketio: The Flask-SocketIO instance from app.py.
        reject_connections: When True, all new connections are rejected
            (used for WebSocket-failure testing via REJECT_SOCKETIO_CONNECTIONS env var).
    """
    global _REJECT_SOCKETIO_CONNECTIONS
    _REJECT_SOCKETIO_CONNECTIONS = reject_connections

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @socketio.on('connect')
    def handle_connect(auth=None):
        """Handle client connection to WebSocket.

        When reject_connections is True, immediately reject connections to
        simulate WebSocket failure for testing purposes.
        """
        if _REJECT_SOCKETIO_CONNECTIONS:
            logger.info(f"Testing: Rejecting Socket.IO connection from {request.sid}")
            return False  # Reject the connection

        user = get_authenticated_socket_user()
        if not user:
            logger.warning("Rejecting unauthenticated Socket.IO connection from %s", request.sid)
            return False

        logger.info("Authenticated client connected: sid=%s user_id=%s", request.sid, user.id)
        emit('connected', {'data': 'Connected to board server'})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection from WebSocket."""
        logger.info(f"Client disconnected: {request.sid}")

    # ------------------------------------------------------------------
    # Board room join / leave
    # ------------------------------------------------------------------

    @socketio.on('join_board')
    def on_join_board(data):
        """Join a board's WebSocket room for real-time updates.

        Args:
            data: Dictionary containing 'board_id'
        """
        user = get_authenticated_socket_user()
        if not user:
            logger.warning("Unauthorized join_board attempt: sid=%s", request.sid)
            return {'success': False, 'message': 'Authentication required'}

        board_id = _extract_board_id(data)
        if board_id is None:
            return {'success': False, 'message': 'Valid board_id is required'}

        has_access, _ = can_access_board(user.id, board_id)
        if not has_access:
            logger.warning(
                "Denied join_board: sid=%s user_id=%s board_id=%s",
                request.sid,
                user.id,
                board_id,
            )
            return {'success': False, 'message': 'Access denied to this board'}

        room = f'board_{board_id}'
        join_room(room)
        logger.info("Client %s (user_id=%s) joined board %s", request.sid, user.id, board_id)
        emit('room_joined', {'board_id': board_id, 'message': f'Joined board {board_id}'})
        return {'success': True, 'board_id': board_id}

    @socketio.on('leave_board')
    def on_leave_board(data):
        """Leave a board's WebSocket room.

        Args:
            data: Dictionary containing 'board_id'
        """
        user = get_authenticated_socket_user()
        if not user:
            return {'success': False, 'message': 'Authentication required'}

        board_id = _extract_board_id(data)
        if board_id is None:
            return {'success': False, 'message': 'Valid board_id is required'}

        has_access, _ = can_access_board(user.id, board_id)
        if not has_access:
            return {'success': False, 'message': 'Access denied to this board'}

        room = f'board_{board_id}'
        leave_room(room)
        logger.info("Client %s (user_id=%s) left board %s", request.sid, user.id, board_id)
        return {'success': True, 'board_id': board_id}

    # ------------------------------------------------------------------
    # Client-originated mutation rejection handlers
    # ------------------------------------------------------------------

    @socketio.on('card_moved')
    def broadcast_card_moved(data):
        """Reject client-originated card_moved events."""
        return _reject_client_originated_mutation('card_moved')

    @socketio.on('card_updated')
    def broadcast_card_updated(data):
        """Reject client-originated card_updated events."""
        return _reject_client_originated_mutation('card_updated')

    @socketio.on('card_created')
    def broadcast_card_created(data):
        """Reject client-originated card_created events."""
        return _reject_client_originated_mutation('card_created')

    @socketio.on('card_deleted')
    def broadcast_card_deleted(data):
        """Reject client-originated card_deleted events."""
        return _reject_client_originated_mutation('card_deleted')

    @socketio.on('column_reordered')
    def broadcast_column_reordered(data):
        """Reject client-originated column_reordered events."""
        return _reject_client_originated_mutation('column_reordered')

    @socketio.on('checklist_item_added')
    def broadcast_checklist_item_added(data):
        """Reject client-originated checklist_item_added events."""
        return _reject_client_originated_mutation('checklist_item_added')

    @socketio.on('checklist_item_updated')
    def broadcast_checklist_item_updated(data):
        """Reject client-originated checklist_item_updated events."""
        return _reject_client_originated_mutation('checklist_item_updated')

    @socketio.on('checklist_item_deleted')
    def broadcast_checklist_item_deleted(data):
        """Reject client-originated checklist_item_deleted events."""
        return _reject_client_originated_mutation('checklist_item_deleted')

    # ------------------------------------------------------------------
    # Theme room join / leave
    # ------------------------------------------------------------------

    @socketio.on('join_theme')
    def on_join_theme():
        """Handle client joining the theme room to receive theme updates."""
        user = get_authenticated_socket_user()
        if not user:
            return {'success': False, 'message': 'Authentication required'}

        room_name = f'theme_user_{user.id}'
        join_room(room_name)
        logger.info(f"✓ Client {request.sid} (user_id={user.id}) joined theme room {room_name}")

        # Send current theme to the new client
        session = SessionLocal()
        try:
            setting = get_user_scoped_query(session, Setting, user.id).filter(
                Setting.key == 'selected_theme',
                Setting.user_id == user.id,
            ).first()
            if setting:
                try:
                    theme_id = int(setting.value)
                    logger.info(f"📢 Sending current theme {theme_id} to client {request.sid}")
                    emit('theme_changed', {'theme_id': theme_id})
                    logger.info(f"✓ Emitted theme_changed to client {request.sid}")
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(f"✗ Error parsing theme_id: {str(e)}")
            else:
                logger.info("ℹ No selected_theme setting found")
        except Exception as e:
            logger.error(f"✗ Error sending current theme to client: {str(e)}")
        finally:
            session.close()

        return {'success': True}

    @socketio.on('leave_theme')
    def on_leave_theme():
        """Handle client leaving the theme room."""
        user = get_authenticated_socket_user()
        if not user:
            return {'success': False, 'message': 'Authentication required'}

        room_name = f'theme_user_{user.id}'
        leave_room(room_name)
        logger.info(f"Client {request.sid} (user_id={user.id}) left theme room {room_name}")
        return {'success': True}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _reject_client_originated_mutation(event_name):
    """Reject client-originated mutation events.

    Mutations must flow through authenticated/authorized API endpoints so the
    server remains the single source of truth for realtime broadcasts.
    """
    user = get_authenticated_socket_user()
    user_id = user.id if user else None
    logger.warning(
        "Rejected client-originated websocket mutation: event=%s sid=%s user_id=%s",
        event_name,
        request.sid,
        user_id,
    )
    return {
        'success': False,
        'message': 'Client-originated mutation events are disabled. Use REST API endpoints.',
        'event': event_name,
    }


def _extract_board_id(payload):
    """Safely extract and validate board_id from socket event payload."""
    if not isinstance(payload, dict):
        return None

    raw_board_id = payload.get('board_id')
    if raw_board_id is None:
        return None

    try:
        board_id = int(raw_board_id)
    except (TypeError, ValueError):
        return None

    if board_id <= 0:
        return None

    return board_id
