from flask import Flask, jsonify, request, send_file, g
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import logging
import json
import io
import os
import re
import secrets
import time
import tempfile
import subprocess
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from flasgger import Swagger
from database import SessionLocal, engine
from models import Board, BoardColumn, BoardSetting, Card, CardSecondaryAssignee, Setting, ScheduledCard, ChecklistItem, Comment, Theme, User, Role, UserRole
from sqlalchemy import text, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import OperationalError, ProgrammingError
from werkzeug.routing import BaseConverter
from werkzeug.exceptions import BadRequest
from utils import (
    validate_string_length,
    validate_integer,
    sanitize_string,
    create_error_response,
    create_success_response,
    MAX_TITLE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_COMMENT_LENGTH,
    get_user_scoped_query,
    get_user_permissions,
    require_permission,
    require_any_permission,
    require_board_access,
    require_authentication,
    get_current_user_id,
    can_access_board,
)
from auth import auth_bp, load_user_from_session, get_authenticated_socket_user
from user_management import user_mgmt_bp
from role_management import role_mgmt_bp
from board_import_handlers import ImportHandlerFactory
from health_routes import health_bp, configure_health_routes
from theme_routes import theme_bp, configure_theme_routes
from notification_routes import notification_bp
from settings_routes import settings_bp, configure_settings_routes
from backup_routes import backup_bp, configure_backup_routes
from settings_schema import (
    SETTINGS_SCHEMA,
    WORKING_STYLE_ALLOWED_VALUES,
    get_board_working_style,
    get_user_default_working_style,
    normalize_working_style,
    validate_setting,
)
from datetime_helpers import parse_iso_datetime, serialize_datetime
from security_validators import (
  validate_backup_file_security,
  validate_backup_file_size,
    validate_json_import_payload_size,
    validate_safe_url,
  validate_schema_integrity,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "2026.3.3"

app = Flask(__name__)

# Configure session
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 7  # 7 days

if not app.config['SESSION_COOKIE_SECURE']:
    logger.warning(
        'SESSION_COOKIE_SECURE is set to false. Session cookies may be transmitted over plain HTTP. '
        'Use only in controlled local development scenarios.'
    )

# Custom path converter that allows safe filenames (validation happens in the endpoint)
class SafeFilenameConverter(BaseConverter):
    """Converter for image filenames - matches filenames with a restricted safe character set.
    
    The actual security validation (preventing .. traversal) is done in the endpoint
    function itself, not in the regex. The regex here ensures only safe characters are
    accepted in the path segment.
    """
    regex = r'[a-zA-Z0-9._-]+'  # Only allow alphanumerics, dot, underscore, and hyphen

app.url_map.converters['safe_filename'] = SafeFilenameConverter

# Initialize CORS for HTTP and WebSocket endpoints
# Parse CORS allowed origins from environment variable
# Controls which origins can connect via HTTP/HTTPS and WebSocket
cors_origins_env = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost')
cors_allowed_origins = [origin.strip() for origin in cors_origins_env.split(',')]

# Initialize Flask-CORS for HTTP/HTTPS endpoints
# Flask-CORS validates all cross-origin requests (requests with Origin header) against
# the configured origins list. Requests without an Origin header are processed normally
# (same-origin requests in browsers, or requests from non-browser clients).
# For disallowed origins, Flask-CORS will not add CORS headers to the response,
# which causes the browser to reject the cross-origin request.
CORS(
    app,
    origins=cors_allowed_origins,
    supports_credentials=True,
    methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH']
)

# Initialize SocketIO for WebSocket support with Redis message queue for multi-worker support
# Redis allows multiple gunicorn workers to communicate WebSocket events to each other
redis_url = os.getenv('REDIS_URL')
server_side_sessions_enabled = os.getenv('ENABLE_SERVER_SIDE_SESSIONS', 'false').lower() == 'true'
redis_configured = bool(redis_url)

_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    raise RuntimeError(
        'SECRET_KEY environment variable is not set. '
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
        'and add it to your .env file. Never use a hardcoded or default secret in production.'
    )
app.config['SECRET_KEY'] = _secret_key

if server_side_sessions_enabled:
    if not redis_url:
        raise RuntimeError(
            'ENABLE_SERVER_SIDE_SESSIONS=true requires REDIS_URL to be configured.'
        )

    try:
        import redis
        from flask_session import Session as ServerSideSession
    except ImportError as e:
        raise RuntimeError(
            'ENABLE_SERVER_SIDE_SESSIONS=true requires flask-session and redis packages. '
            'Install with: pip install -r server/requirements.txt'
        ) from e

    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_REDIS'] = redis.from_url(redis_url)
    app.config['SESSION_KEY_PREFIX'] = 'aft:session:'
    app.config['SESSION_PERMANENT'] = True
    app.config['SESSION_USE_SIGNER'] = True
    ServerSideSession(app)
    logger.info(
        'Session mode: server-side (Redis). feature_flag=ENABLE_SERVER_SIDE_SESSIONS:true redis_configured=%s',
        redis_configured,
    )
else:
    logger.info(
        'Session mode: client-side (Flask signed cookie). feature_flag=ENABLE_SERVER_SIDE_SESSIONS:false redis_configured=%s',
        redis_configured,
    )

# Validate Redis configuration for multi-worker deployment
if not redis_url:
    logger.warning(
        "⚠️  REDIS_URL not configured. WebSocket broadcasts will NOT work across multiple gunicorn workers. "
        "Real-time updates may be lost if requests are routed to different workers. "
        "Set REDIS_URL environment variable to enable cross-worker WebSocket communication."
    )

socketio = SocketIO(
    app, 
    cors_allowed_origins=cors_allowed_origins,
    async_mode='threading',
    message_queue=redis_url  # Connect to Redis for message queue (None if not configured)
)

# Thread-safe dictionary to track recent broadcast failures
# Format: {room_name: {event_name: error_message, timestamp: datetime}}
# Used for debugging and monitoring WebSocket broadcast issues
# Protected by lock for concurrent access in multi-worker/multi-threaded environment
# IMPORTANT: All access to broadcast_failures must occur within a "with broadcast_failures_lock:" block
# to prevent race conditions in multi-threaded environments
broadcast_failures = {}
broadcast_failures_lock = threading.Lock()
configure_health_routes(APP_VERSION, broadcast_failures, broadcast_failures_lock)

def record_broadcast_failure(room_name, event_name, error_message):
    """Thread-safe helper to record a broadcast failure.
    
    Args:
        room_name: Name of the room where broadcast failed
        event_name: Name of the event that failed
        error_message: Error message to record
    """
    with broadcast_failures_lock:
        if room_name not in broadcast_failures:
            broadcast_failures[room_name] = {}
        broadcast_failures[room_name][event_name] = error_message

def clear_broadcast_failure(room_name, event_name):
    """Thread-safe helper to clear a broadcast failure record.
    
    Args:
        room_name: Name of the room
        event_name: Name of the event
    """
    with broadcast_failures_lock:
        if room_name in broadcast_failures:
            broadcast_failures[room_name].pop(event_name, None)

# ============================================================================
# TESTING FLAG: WebSocket Connection Rejection
# ============================================================================
# Set to True to test WebSocket disconnection scenarios (header shows "WebSocket Disconnected")
# All Socket.IO connection attempts will be rejected, forcing clients to reconnect
#
# WARNING: This must NEVER be enabled (True) in production deployments.
# To use for local/testing purposes, set the environment variable
# REJECT_SOCKETIO_CONNECTIONS=true. It defaults to False when unset.
REJECT_SOCKETIO_CONNECTIONS = os.getenv("REJECT_SOCKETIO_CONNECTIONS", "false").lower() == "true"

# Helper function to broadcast WebSocket events from route handlers
def broadcast_event(event_name, data, board_id, skip_sid=None):
    """Broadcast a WebSocket event to all clients in a board room.
    
    Args:
        event_name: Name of the event to broadcast
        data: Event data to send
        board_id: Board ID to broadcast to (determines the room)
        skip_sid: Optional Socket.IO session ID to exclude from broadcast (usually request.sid)
    
    Note: Broadcasts happen asynchronously in background tasks. Failures are logged but
    do not affect the API response. The calling route should implement client-side
    refresh logic as a fallback (e.g., client reloads board on reconnection).
    """
    room_name = f'board_{board_id}'
    
    def do_emit():
        try:
            logger.info(f"Broadcasting {event_name} to room {room_name} with data: {data}")
            # Use socketio.emit to broadcast to all clients in the room
            # skip_sid prevents the originating client from receiving a duplicate update
            socketio.emit(event_name, data, room=room_name, skip_sid=skip_sid, namespace='/')
            logger.info(f"✓ Successfully emitted {event_name}")
            # Clear any previous failure for this event
            clear_broadcast_failure(room_name, event_name)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error broadcasting {event_name} to {room_name}: {error_msg}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Track the failure for debugging
            record_broadcast_failure(room_name, event_name, error_msg)
    
    # Use background task to ensure proper context
    socketio.start_background_task(do_emit)


# Register websocket broadcaster callback for the scheduler without importing app from scheduler.
try:
    from card_scheduler import set_broadcast_event_callback

    set_broadcast_event_callback(broadcast_event)
except Exception as callback_err:
    logger.warning(f"Failed to register scheduler broadcast callback: {callback_err}")


# Configure settings routes with APP_VERSION
configure_settings_routes(app, APP_VERSION)
configure_backup_routes(APP_VERSION)


def broadcast_theme_event(event_name, data):
    """Broadcast a WebSocket event to all clients in the theme room.
    
    Note: Broadcasts happen asynchronously in background tasks. Failures are logged but
    do not affect the API response. Clients should implement refresh logic as fallback.
    """
    room_name = 'theme'
    
    def do_emit():
        try:
            logger.info(f"📢 Broadcasting {event_name} to theme room with data: {data}")
            # Use socketio.emit to broadcast to all clients in the theme room
            socketio.emit(event_name, data, room=room_name, namespace='/')
            logger.info(f"✓ Successfully emitted {event_name} to theme room")
            # Clear any previous failure for this event
            clear_broadcast_failure(room_name, event_name)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"✗ Error broadcasting {event_name} to theme room: {error_msg}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Track the failure for debugging
            record_broadcast_failure(room_name, event_name, error_msg)
    
    # Use background task to ensure proper context
    socketio.start_background_task(do_emit)


configure_theme_routes(broadcast_theme_event)

# Configure maximum upload size (110MB)
app.config["MAX_CONTENT_LENGTH"] = 110 * 1024 * 1024

MAX_BOARD_IMPORT_FILE_SIZE_MB = 25

# Allowed value for board import file metadata
BOARD_EXPORT_FORMAT = "aft-board"

# Configure Swagger
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/api/apispec.json",
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "static_url_path": "/api/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs",
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "AFT API",
        "description": """
API documentation for AFT application

**Authentication:** This API uses session-based authentication. To test authenticated endpoints in Swagger UI:

### Recommended Workflow
1. **First, validate your credentials**: Call `/api/auth/validate` (POST) with your credentials to verify they work
2. **Then, set up authentication**: 
   - Click the "Authorise" button (🔓) at the top right
   - Enter your credentials in the BasicAuth section (use email as username)
   - Click "Authorise"
3. **Test endpoints**: Your credentials will be sent with each request

⚠️ **Important**: The Authorise modal will say "Authorized" even with invalid credentials. 
This is a Swagger limitation - credentials are only validated when you actually call an endpoint.
Always use `/api/auth/validate` first to verify your credentials are correct.

### Alternative: Session-Based Login
1. Call `/api/auth/login` (POST) with your email and password
2. The session cookie will be automatically set and used for all requests
3. No need to use the Authorise button

### Default Test Credentials
- Email: `test-admin@localhost`
- Password: `TestAdmin123!`

<a href="/" style="text-decoration: none;">← Back to AFT Home</a>
        """,
        "version": "1.0.0",
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "securityDefinitions": {
        "SessionAuth": {
            "type": "apiKey",
            "name": "session",
            "in": "cookie",
            "description": "Session-based authentication. Login via `/api/auth/login` to obtain a session cookie."
        },
        "BasicAuth": {
            "type": "basic",
            "description": "⚠️ Basic Auth for testing. Modal accepts any input - credentials are validated when calling endpoints. Use /api/auth/validate to test credentials first."
        }
    },
    "security": [
        {"SessionAuth": []},
        {"BasicAuth": []}
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# ============================================================================
# Authentication Setup
# ============================================================================

# Register authentication and shared route blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(user_mgmt_bp)
app.register_blueprint(role_mgmt_bp)
app.register_blueprint(health_bp)
app.register_blueprint(theme_bp)
app.register_blueprint(notification_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(backup_bp)

# Load user from session before each request
@app.before_request
def before_request():
    """Load authenticated user into Flask g object and check setup status."""
    # Skip setup check for setup/auth endpoints, health checks, and static files
    if (
        request.path.startswith('/api/auth/setup') or
        request.path == '/api/test' or  # Legacy health endpoint
        request.path == '/api/health/live' or
        request.path == '/api/health/ready' or
        request.path.startswith('/setup.html') or
        request.path.startswith('/css/') or
        request.path.startswith('/js/') or
        request.path.startswith('/images/')
    ):
        load_user_from_session()
        return
    
    # Check if initial setup is complete (any active user with password exists)
    from models import User
    db = SessionLocal()
    try:
      try:
        has_users = db.query(User).filter(
          User.is_active == True,
          User.password_hash.isnot(None)
        ).count() > 0
      except (ProgrammingError, OperationalError) as error:
        # During /api/database resets, tables are briefly absent while Alembic
        # recreates the schema. Let reset/restore routes continue so their own
        # locking and wait logic can finish the operation.
        logger.info(f"Setup check skipped during transient database reset: {error}")

        if request.path.startswith('/api/database'):
          load_user_from_session()
          return

        if request.path.startswith('/api/'):
          return jsonify({
            'success': False,
            'message': 'Initial setup required',
            'redirect': '/setup.html'
          }), 503

        if request.path != '/setup.html':
          from flask import redirect
          return redirect('/setup.html', code=302)
        return
        
        if not has_users:
            # Redirect to setup page for HTML requests
            if not request.path.startswith('/api/'):
                if request.path != '/setup.html':
                    from flask import redirect
                    return redirect('/setup.html', code=302)
            # For API requests, return a specific error
            else:
                return jsonify({
                    'success': False,
                    'message': 'Initial setup required',
                    'redirect': '/setup.html'
                }), 503
    finally:
        db.close()
    
    load_user_from_session()

# Close database session after each request if it was opened
@app.teardown_request
def teardown_request(exception=None):
    """Close database session if it was opened."""
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception as e:
            # Connection may have been killed during restore operations
            # This is expected and can be safely ignored
            logger.debug(f"Error closing database session in teardown (connection may have been killed): {e}")

# Request size limit (110MB) for non-file-upload endpoints
MAX_REQUEST_SIZE = 110 * 1024 * 1024


@app.before_request
def validate_request():
    """Validate incoming requests for security.

    This runs before every request to:
    1. Check request size to prevent DoS attacks (except file uploads)
    2. Validate Content-Type for JSON requests
    """
    # Exclude restore endpoints from size check (they use Flask's MAX_CONTENT_LENGTH instead)
    restore_endpoints = ['/api/database/restore', '/api/database/backups/restore/']
    is_restore_endpoint = any(request.path.startswith(endpoint) for endpoint in restore_endpoints)
    
    # Check request size for non-restore endpoints
    if not is_restore_endpoint and request.content_length and request.content_length > MAX_REQUEST_SIZE:
        return create_error_response(
            f"Request size exceeds maximum of {MAX_REQUEST_SIZE} bytes", 413
        )

    # Validate Content-Type for requests with body
    if request.method in ["POST", "PUT", "PATCH"]:
        if request.data and not request.is_json:
            # Allow multipart/form-data for file uploads
            if not request.content_type or not request.content_type.startswith(
                "multipart/form-data"
            ):
                return create_error_response(
                    "Content-Type must be application/json for JSON requests", 400
                )


# Security validation helpers are defined in security_validators.py


def sanitize_import_text(value, field_name, max_length, allow_none=False):
    """Sanitize and validate imported text fields for safe persistence."""
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required")

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    cleaned = sanitize_string(value)
    if "\x00" in cleaned:
        raise ValueError(f"{field_name} contains invalid null characters")

    is_valid, error = validate_string_length(cleaned, max_length, field_name)
    if not is_valid:
        raise ValueError(error)

    return cleaned


def coerce_bool(value, default=False):
    """Coerce value to boolean with a safe default."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def user_can_import_boards(user_id, db):
    """Check whether a user can import boards.

    Import is allowed for users with global board.create/board.edit permissions,
    or users who hold at least one board-scoped role that grants board.edit.
    """
    user_permissions = get_user_permissions(user_id)
    if "system.admin" in user_permissions or "board.create" in user_permissions or "board.edit" in user_permissions:
        return True

    board_roles = (
        db.query(UserRole, Role)
        .join(Role, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id, UserRole.board_id.isnot(None))
        .all()
    )
    for _, role in board_roles:
        try:
            role_permissions = set(json.loads(role.permissions))
        except (TypeError, json.JSONDecodeError):
            continue
        if "board.edit" in role_permissions:
            return True
    return False


def build_import_name(db, source_name, strategy):
    """Resolve imported board name according to duplicate handling strategy."""
    existing = db.query(Board.id).filter(func.lower(Board.name) == source_name.lower()).first()
    if not existing:
        return source_name, False

    if strategy != "append_suffix":
        return source_name, True

    base_name = f"{source_name} (imported)"
    candidate = base_name
    counter = 2
    while db.query(Board.id).filter(func.lower(Board.name) == candidate.lower()).first():
        candidate = f"{base_name} {counter}"
        counter += 1

    return candidate, True


# Health and admin diagnostic routes moved to health_routes.py
# Backup/restore routes moved to backup_routes.py



@app.route("/api/boards", methods=["GET"])
@require_authentication
def get_boards():
    """Get all boards accessible by the current user (owned or shared via roles).
    
    Accessible by users with board.view OR board.create permission.
    Users with board.create can see empty boards list and create new boards.
    ---
    tags:
      - Boards
    responses:
      200:
        description: List of all boards accessible by the user
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            boards:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                    example: 1
                  name:
                    type: string
                    example: "My Board"
      401:
        description: Authentication required
      403:
        description: Permission denied
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        user_id = g.user.id
        
        # Check if user is a system administrator - they can see ALL boards
        from utils import get_user_permissions
        from permissions import has_permission
        user_perms = get_user_permissions(user_id)

        # Allow board list access when user has global board permissions OR
        # any board-specific assignment (e.g., board_viewer/board_editor).
        can_view_boards = has_permission(user_perms, 'board.view')
        can_create_boards = has_permission(user_perms, 'board.create')
        has_global_board_perm = can_view_boards or can_create_boards
        has_board_assignment = db.query(UserRole.id).filter(
          UserRole.user_id == user_id,
          UserRole.board_id.isnot(None)
        ).first() is not None

        if not has_global_board_perm and not has_board_assignment:
            return jsonify(
                {
                    "success": False,
                    "error": "boards_access_denied",
                    "message": "You do not have access to any existing boards and you do not have permission to create a new board. Ask an administrator to grant board.view access or the board_creator role.",
                    "details": {
                        "can_create_board": False,
                        "has_board_access": False,
                    },
                }
            ), 403
        
        if has_permission(user_perms, 'system.admin'):
            # Admins see all boards in the system
            boards = db.query(Board).order_by(Board.name).all()
        else:
            # Regular users: Get boards owned by user OR where user has a role assignment
            owned_boards = db.query(Board).filter(Board.owner_id == user_id)
            role_boards = db.query(Board).join(UserRole).filter(UserRole.user_id == user_id)
            
            # Combine both queries and remove duplicates
            boards = owned_boards.union(role_boards).all()
        
        # Build board list with per-board permissions
        boards_data = []
        for b in boards:
            # Get board-specific permissions for this user
            board_permissions = get_user_permissions(user_id, board_id=b.id)
            can_delete = 'board.delete' in board_permissions
            can_edit = 'board.edit' in board_permissions
            can_export = 'board.view' in board_permissions
            
            boards_data.append({
                "id": b.id, 
                "name": b.name, 
                "description": b.description,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                "can_delete": can_delete,
                "can_edit": can_edit,
                "can_export": can_export,
            })
        
        return jsonify(
            {
                "success": True,
                "boards": boards_data,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/boards", methods=["POST"])
@require_permission('board.create')
def create_board():
    """Create a new board with input validation.

    This endpoint creates a new board after validating:
    - Name is provided and is a string
    - Name does not exceed maximum length
    - Description (if provided) does not exceed maximum length

    ---
    tags:
      - Boards
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: "My New Board"
              description: The name of the board to create
    responses:
      201:
        description: Board created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            board:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                name:
                  type: string
                  example: "My New Board"
      400:
        description: Bad request - missing name
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Name is required"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data or "name" not in data:
            return create_error_response("Name is required", 400)

        # Validate name
        name = data.get("name")
        if not isinstance(name, str):
            return create_error_response("Name must be a string", 400)

        # Sanitize and validate length
        name = sanitize_string(name)
        if not name:  # Empty after sanitization
            return create_error_response("Name cannot be empty", 400)

        is_valid, error = validate_string_length(name, MAX_TITLE_LENGTH, "Name")
        if not is_valid:
            return create_error_response(error, 400)

        # Validate description if provided
        description = data.get("description")
        if description is not None:
            if not isinstance(description, str):
                return create_error_response("Description must be a string", 400)

            description = sanitize_string(description)
            is_valid, error = validate_string_length(
                description, MAX_DESCRIPTION_LENGTH, "Description"
            )
            if not is_valid:
                return create_error_response(error, 400)

        # Create board
        from datetime import datetime
        now = datetime.utcnow()
        user_id = get_current_user_id()
        board = Board(name=name, description=description, owner_id=user_id, updated_at=now)
        db.add(board)

        # Create a board-level working style using the user's current default.
        db.flush()
        working_style = get_user_default_working_style(db, user_id)
        db.add(
          BoardSetting(
            board_id=board.id,
            key='working_style',
            value=json.dumps(working_style),
          )
        )

        db.commit()
        db.refresh(board)

        result = {
            "id": board.id, 
            "name": board.name, 
            "description": board.description,
            "created_at": board.created_at.isoformat() if board.created_at else None,
            "updated_at": board.updated_at.isoformat() if board.updated_at else None
        }
        return create_success_response({"board": result}, status_code=201)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating board: {str(e)}")
        return create_error_response("Failed to create board", 500)
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>/export", methods=["GET"])
@require_board_access()
@require_permission('board.view')
def export_board(board_id):
    """Export a single board and all board-related data as JSON."""
    db = SessionLocal()
    try:
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            return create_error_response("Board not found", 404)

        columns = (
            db.query(BoardColumn)
            .filter(BoardColumn.board_id == board_id)
            .order_by(BoardColumn.order)
            .all()
        )
        column_ids = [column.id for column in columns]

        cards = []
        if column_ids:
            cards = (
                db.query(Card)
                .options(
                    selectinload(Card.checklist_items),
                    selectinload(Card.comments),
                    selectinload(Card.secondary_assignees),
                )
                .filter(Card.column_id.in_(column_ids))
                .order_by(Card.column_id, Card.order, Card.id)
                .all()
            )

        card_ids = [card.id for card in cards]
        board_settings = (
            db.query(BoardSetting)
            .filter(BoardSetting.board_id == board_id)
            .order_by(BoardSetting.id)
            .all()
        )

        scheduled_cards = []
        if card_ids:
            scheduled_cards = (
                db.query(ScheduledCard)
                .filter(ScheduledCard.card_id.in_(card_ids))
                .order_by(ScheduledCard.id)
                .all()
            )

        export_payload = {
            "export": {
                "format": BOARD_EXPORT_FORMAT,
                "format_version": "1.0",
                "app_version": APP_VERSION,
                "exported_at": serialize_datetime(datetime.utcnow()),
                "exported_by_user_id": g.user.id,
                "source_board_id": board.id,
                "features_exported": [
                    "board",
                    "board_settings",
                    "columns",
                    "cards",
                    "card_secondary_assignees",
                    "checklists",
                    "comments",
                    "scheduled_cards",
                ],
            },
            "board": {
                "id": board.id,
                "name": board.name,
                "description": board.description,
                "owner_id": board.owner_id,
                "created_at": serialize_datetime(board.created_at),
                "updated_at": serialize_datetime(board.updated_at),
            },
            "board_settings": [
                {
                    "id": setting.id,
                    "board_id": setting.board_id,
                    "key": setting.key,
                    "value": setting.value,
                }
                for setting in board_settings
            ],
            "columns": [
                {
                    "id": column.id,
                    "board_id": column.board_id,
                    "name": column.name,
                    "order": column.order,
                    "created_at": serialize_datetime(column.created_at),
                    "updated_at": serialize_datetime(column.updated_at),
                }
                for column in columns
            ],
            "cards": [
                {
                    "id": card.id,
                    "column_id": card.column_id,
                    "title": card.title,
                    "description": card.description,
                    "order": card.order,
                    "archived": card.archived,
                    "scheduled": card.scheduled,
                    "schedule": card.schedule,
                    "done": card.done,
                    "created_by_id": card.created_by_id,
                    "assigned_to_id": card.assigned_to_id,
                    "created_at": serialize_datetime(card.created_at),
                    "updated_at": serialize_datetime(card.updated_at),
                }
                for card in cards
            ],
            "card_secondary_assignees": [
                {
                    "id": secondary.id,
                    "card_id": secondary.card_id,
                    "user_id": secondary.user_id,
                    "created_at": serialize_datetime(secondary.created_at),
                }
                for card in cards
                for secondary in card.secondary_assignees
            ],
            "checklists": [
                {
                    "id": item.id,
                    "card_id": item.card_id,
                    "name": item.name,
                    "checked": item.checked,
                    "order": item.order,
                    "created_at": serialize_datetime(item.created_at),
                    "updated_at": serialize_datetime(item.updated_at),
                }
                for card in cards
                for item in card.checklist_items
            ],
            "comments": [
                {
                    "id": comment.id,
                    "card_id": comment.card_id,
                    "comment": comment.comment,
                    "order": comment.order,
                    "created_at": serialize_datetime(comment.created_at),
                }
                for card in cards
                for comment in card.comments
            ],
            "scheduled_cards": [
                {
                    "id": schedule.id,
                    "card_id": schedule.card_id,
                    "run_every": schedule.run_every,
                    "unit": schedule.unit,
                    "start_datetime": serialize_datetime(schedule.start_datetime),
                    "end_datetime": serialize_datetime(schedule.end_datetime),
                    "schedule_enabled": schedule.schedule_enabled,
                    "allow_duplicates": schedule.allow_duplicates,
                }
                for schedule in scheduled_cards
            ],
        }

        board_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", board.name or "board").strip("_") or "board"
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"aft_board_{board_slug}_{timestamp}.json"
        file_content = json.dumps(export_payload, ensure_ascii=True, indent=2)

        return send_file(
            io.BytesIO(file_content.encode("utf-8")),
            mimetype="application/json",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.error(f"Error exporting board {board_id}: {str(e)}")
        return create_error_response("Failed to export board", 500)
    finally:
        db.close()


@app.route("/api/boards/import", methods=["POST"])
@require_authentication
def import_board_from_export():
    """Import a board from an AFT JSON export file."""
    db = SessionLocal()
    try:
        user_id = g.user.id
        if not user_can_import_boards(user_id, db):
            return create_error_response(
                "Permission denied: importing boards requires board editor access",
                403,
            )

        if "file" not in request.files:
            return create_error_response("No file uploaded", 400)

        file_obj = request.files["file"]
        if file_obj.filename == "":
            return create_error_response("No file selected", 400)

        payload_bytes = file_obj.read()
        if not payload_bytes:
            return create_error_response("Import file is empty", 400)

        try:
            payload_text = payload_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return create_error_response("Import file must be valid UTF-8 JSON", 400)

        is_valid_size, size_error = validate_json_import_payload_size(
            payload_text,
            max_size_mb=MAX_BOARD_IMPORT_FILE_SIZE_MB,
        )
        if not is_valid_size:
            return create_error_response(size_error, 400)

        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return create_error_response("Import file is not valid JSON", 400)

        handler = ImportHandlerFactory.get_handler(payload)
        if not handler:
            return create_error_response(
                "Unsupported import format. Only AFT-formatted JSON exports are currently supported.",
                400,
            )

        validation_result = handler.validate(payload)
        if not validation_result.is_valid:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Import validation failed",
                        "errors": validation_result.errors,
                    }
                ),
                400,
            )

        import_data = handler.parse(payload)
        board_data = import_data["board"]

        duplicate_strategy = (request.form.get("duplicate_strategy") or "cancel").strip().lower()
        if duplicate_strategy not in {"cancel", "append_suffix"}:
            return create_error_response(
                "duplicate_strategy must be one of: cancel, append_suffix",
                400,
            )

        source_board_name = sanitize_import_text(
            board_data.get("name"),
            "Board name",
            MAX_TITLE_LENGTH,
            allow_none=False,
        )
        resolved_board_name, had_name_conflict = build_import_name(
            db,
            source_board_name,
            duplicate_strategy,
        )

        if had_name_conflict and duplicate_strategy == "cancel":
            suggested_name, _ = build_import_name(db, source_board_name, "append_suffix")
            return (
                jsonify(
                    {
                        "success": False,
                        "message": (
                            "A board with this name already exists. Overwriting is not supported. "
                            "Delete the existing board first, or import with an automatic suffix."
                        ),
                        "requires_confirmation": True,
                        "conflict_type": "board_name_exists",
                        "board_name": source_board_name,
                        "suggested_board_name": suggested_name,
                    }
                ),
                409,
            )

        board_description = sanitize_import_text(
            board_data.get("description"),
            "Board description",
            MAX_DESCRIPTION_LENGTH,
            allow_none=True,
        )

        # User identity differs between instances. For safety, assignee mapping is
        # intentionally disabled until explicit user-mapping support is added.
        ignored_primary_assignees_count = sum(
            1
            for card in import_data["cards"]
            if isinstance(card.get("assigned_to_id"), int) and card.get("assigned_to_id") > 0
        )
        ignored_secondary_assignees_count = sum(
            1
            for assignee in import_data["card_secondary_assignees"]
            if isinstance(assignee.get("user_id"), int) and assignee.get("user_id") > 0
        )

        new_board = Board(
            name=resolved_board_name,
            description=board_description,
            owner_id=user_id,
            updated_at=datetime.utcnow(),
        )
        db.add(new_board)
        db.flush()

        old_to_new_column_id = {}
        old_to_new_card_id = {}
        old_to_new_schedule_id = {}
        pending_schedule_references = {}

        for setting in import_data["board_settings"]:
            setting_key = sanitize_import_text(
                setting.get("key"),
                "Board setting key",
                255,
                allow_none=False,
            )
            setting_value = setting.get("value")
            if setting_value is not None and not isinstance(setting_value, str):
                setting_value = json.dumps(setting_value)

            db.add(
                BoardSetting(
                    board_id=new_board.id,
                    key=setting_key,
                    value=setting_value,
                )
            )

        sorted_columns = sorted(
            import_data["columns"],
            key=lambda col: (int(col.get("order") or 0), int(col.get("id") or 0)),
        )
        for column in sorted_columns:
            source_column_id = column.get("id")
            if not isinstance(source_column_id, int):
                continue

            column_name = sanitize_import_text(
                column.get("name"),
                "Column name",
                MAX_TITLE_LENGTH,
                allow_none=False,
            )

            raw_order = column.get("order", 0)
            if isinstance(raw_order, bool):
                raw_order = 0
            if not isinstance(raw_order, int):
                raw_order = 0
            column_order = raw_order if raw_order >= 0 else 0

            new_column = BoardColumn(
                board_id=new_board.id,
                name=column_name,
                order=column_order,
                updated_at=datetime.utcnow(),
            )
            db.add(new_column)
            db.flush()
            old_to_new_column_id[source_column_id] = new_column.id

        sorted_cards = sorted(
            import_data["cards"],
            key=lambda card: (
                int(card.get("column_id") or 0),
                int(card.get("order") or 0),
                int(card.get("id") or 0),
            ),
        )
        for card in sorted_cards:
            source_card_id = card.get("id")
            source_column_id = card.get("column_id")
            if not isinstance(source_card_id, int) or source_column_id not in old_to_new_column_id:
                continue

            title = sanitize_import_text(
                card.get("title"),
                "Card title",
                MAX_TITLE_LENGTH,
                allow_none=False,
            )
            description = sanitize_import_text(
                card.get("description"),
                "Card description",
                MAX_DESCRIPTION_LENGTH,
                allow_none=True,
            )

            raw_order = card.get("order", 0)
            if isinstance(raw_order, bool):
                raw_order = 0
            if not isinstance(raw_order, int):
                raw_order = 0
            card_order = raw_order if raw_order >= 0 else 0

            # Preserve import attribution to the importing user, and leave assignees
            # unassigned until explicit mapping support is available.
            created_by_id = user_id
            assigned_to_id = None

            new_card = Card(
                column_id=old_to_new_column_id[source_column_id],
                title=title,
                description=description,
                order=card_order,
                archived=coerce_bool(card.get("archived"), default=False),
                scheduled=coerce_bool(card.get("scheduled"), default=False),
                done=coerce_bool(card.get("done"), default=False),
                schedule=None,
                created_by_id=created_by_id,
                assigned_to_id=assigned_to_id,
                updated_at=datetime.utcnow(),
            )
            db.add(new_card)
            db.flush()

            old_to_new_card_id[source_card_id] = new_card.id

            source_schedule_id = card.get("schedule")
            if isinstance(source_schedule_id, int) and source_schedule_id > 0:
                pending_schedule_references[new_card.id] = source_schedule_id

        sorted_checklists = sorted(
            import_data["checklists"],
            key=lambda item: (
                int(item.get("card_id") or 0),
                int(item.get("order") or 0),
                int(item.get("id") or 0),
            ),
        )
        for item in sorted_checklists:
            source_card_id = item.get("card_id")
            if source_card_id not in old_to_new_card_id:
                continue

            item_name = sanitize_import_text(
                item.get("name"),
                "Checklist item name",
                500,
                allow_none=False,
            )

            raw_order = item.get("order", 0)
            if isinstance(raw_order, bool):
                raw_order = 0
            if not isinstance(raw_order, int):
                raw_order = 0

            db.add(
                ChecklistItem(
                    card_id=old_to_new_card_id[source_card_id],
                    name=item_name,
                    checked=coerce_bool(item.get("checked"), default=False),
                    order=raw_order if raw_order >= 0 else 0,
                    updated_at=datetime.utcnow(),
                )
            )

        sorted_comments = sorted(
            import_data["comments"],
            key=lambda comment: (
                int(comment.get("card_id") or 0),
                int(comment.get("order") or 0),
                int(comment.get("id") or 0),
            ),
        )
        for comment in sorted_comments:
            source_card_id = comment.get("card_id")
            if source_card_id not in old_to_new_card_id:
                continue

            comment_text = sanitize_import_text(
                comment.get("comment"),
                "Comment",
                MAX_COMMENT_LENGTH,
                allow_none=False,
            )
            raw_order = comment.get("order", 0)
            if isinstance(raw_order, bool):
                raw_order = 0
            if not isinstance(raw_order, int):
                raw_order = 0

            db.add(
                Comment(
                    card_id=old_to_new_card_id[source_card_id],
                    comment=comment_text,
                    order=raw_order if raw_order >= 0 else 0,
                )
            )

        sorted_schedules = sorted(
            import_data["scheduled_cards"],
            key=lambda schedule: int(schedule.get("id") or 0),
        )
        for schedule in sorted_schedules:
            source_schedule_id = schedule.get("id")
            source_template_card_id = schedule.get("card_id")
            if source_template_card_id not in old_to_new_card_id:
                continue

            run_every = schedule.get("run_every")
            if isinstance(run_every, bool) or not isinstance(run_every, int) or run_every < 1:
                run_every = 1

            unit = schedule.get("unit")
            allowed_units = {"minute", "hour", "day", "week", "month", "year"}
            if not isinstance(unit, str) or unit not in allowed_units:
                unit = "day"

            start_datetime = parse_iso_datetime(schedule.get("start_datetime")) or datetime.utcnow()
            end_datetime = parse_iso_datetime(schedule.get("end_datetime"))

            new_schedule = ScheduledCard(
                card_id=old_to_new_card_id[source_template_card_id],
                run_every=run_every,
                unit=unit,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                schedule_enabled=coerce_bool(schedule.get("schedule_enabled"), default=True),
                allow_duplicates=coerce_bool(schedule.get("allow_duplicates"), default=False),
            )
            db.add(new_schedule)
            db.flush()

            if isinstance(source_schedule_id, int):
                old_to_new_schedule_id[source_schedule_id] = new_schedule.id

        for imported_card_id, imported_schedule_id in pending_schedule_references.items():
            mapped_schedule_id = old_to_new_schedule_id.get(imported_schedule_id)
            if not mapped_schedule_id:
                continue

            db.query(Card).filter(Card.id == imported_card_id).update({"schedule": mapped_schedule_id})

        # Secondary assignees are currently not imported by user ID.

        db.commit()

        return jsonify(
            {
                "success": True,
                "message": "Board imported successfully",
                "board": {
                    "id": new_board.id,
                    "name": new_board.name,
                    "description": new_board.description,
                },
                "import_meta": {
                    "source_board_name": source_board_name,
                    "name_conflict_resolved": had_name_conflict,
                    "import_format": import_data.get("import_format", BOARD_EXPORT_FORMAT),
                    "import_format_version": import_data.get("import_format_version", "1.0"),
                    "assignee_mapping": "not_mapped",
                    "ignored_primary_assignees_count": ignored_primary_assignees_count,
                    "ignored_secondary_assignees_count": ignored_secondary_assignees_count,
                },
            }
        ), 201
    except ValueError as validation_error:
        db.rollback()
        return create_error_response(str(validation_error), 400)
    except Exception as e:
        db.rollback()
        logger.error(f"Error importing board: {str(e)}")
        return create_error_response("Failed to import board", 500)
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>/cards/scheduled", methods=["GET"])
@require_board_access()
def get_board_scheduled_cards(board_id):
    """Get all scheduled cards for a board with nested structure (user must have access).
    Returns only scheduled template cards (scheduled=True) organized by column.
    ---
    tags:
      - Cards
    parameters:
      - name: board_id
        in: path
        type: integer
        required: true
        description: The ID of the board
    responses:
      200:
        description: Board with columns and scheduled cards
      401:
        description: Authentication required
      403:
        description: Access denied to this board
      404:
        description: Board not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import BoardColumn, Card
        
        # Access already validated by @require_board_access decorator
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            return jsonify({"success": False, "message": "Board not found"}), 404
        
        # Get columns for the board
        columns = (
            db.query(BoardColumn)
            .filter(BoardColumn.board_id == board_id)
            .order_by(BoardColumn.order)
            .all()
        )
        
        selected_assignee_ids = _parse_assignee_ids_query_param(request.args.get('assignee_ids'))
        include_unassigned = request.args.get('include_unassigned', 'false').lower() == 'true'
        include_secondary_assignees = request.args.get('include_secondary_assignees', 'false').lower() == 'true'

        # Build nested structure with scheduled cards
        result = {"id": board.id, "name": board.name, "columns": []}

        eligible_users = _get_board_assignee_users(db, board_id)
        result["assignee_filter_users"] = [_user_summary(u) for u in eligible_users]

        for column in columns:
            # Get only scheduled template cards for this column
            cards = (
                db.query(Card)
                .options(selectinload(Card.assigned_to))
                .filter(Card.column_id == column.id)
                .filter(Card.scheduled.is_(True))
            )

            cards = _apply_assignee_card_filters(
              cards,
              selected_assignee_ids,
              include_unassigned,
              include_secondary_assignees,
            ).order_by(Card.order).all()

            # Serialize cards with checklist items and comments
            cards_data = [
                {
                    "id": card.id,
                    "title": card.title,
                    "description": card.description,
                    "order": card.order,
                    "archived": card.archived,
                    "done": card.done,
                    "scheduled": card.scheduled,
                    "schedule": card.schedule,
                    "created_at": card.created_at.isoformat() if card.created_at else None,
                    "updated_at": card.updated_at.isoformat() if card.updated_at else None,
                    "assigned_to": {
                        "id": card.assigned_to.id,
                        "display_name": card.assigned_to.display_name,
                        "username": card.assigned_to.username,
                        "profile_colour": card.assigned_to.profile_colour,
                    } if card.assigned_to else None,
                    "checklist_items": [
                        {
                            "id": item.id,
                            "card_id": item.card_id,
                            "name": item.name,
                            "checked": item.checked,
                            "order": item.order,
                            "created_at": item.created_at.isoformat() if item.created_at else None,
                            "updated_at": item.updated_at.isoformat() if item.updated_at else None
                        }
                        for item in card.checklist_items
                    ],
                    "comments": [
                        {
                            "id": comment.id,
                            "card_id": comment.card_id,
                            "comment": comment.comment,
                            "order": comment.order,
                            "created_at": comment.created_at.isoformat() if comment.created_at else None
                        }
                        for comment in card.comments
                    ]
                }
                for card in cards
            ]

            column_data = {
                "id": column.id,
                "name": column.name,
                "order": column.order,
                "created_at": column.created_at.isoformat() if column.created_at else None,
                "updated_at": column.updated_at.isoformat() if column.updated_at else None,
                "cards": cards_data,
            }
            result["columns"].append(column_data)

        # Check if user has edit permissions for this board
        user_permissions = get_user_permissions(g.user.id, board_id)
        edit_permissions = ['card.create', 'card.edit', 'card.update', 'card.delete', 'card.archive', 'board.edit']
        can_edit = any(perm in user_permissions for perm in edit_permissions)
        result["can_edit"] = can_edit

        return jsonify({"success": True, "board": result})
        
    except Exception as e:
        logger.error(f"Error getting scheduled cards for board {board_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to get scheduled cards"}), 500
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>", methods=["DELETE"])
@require_board_access()
@require_permission('board.delete')
def delete_board(board_id):
    """Delete a board by ID.
    ---
    tags:
      - Boards
    parameters:
      - name: board_id
        in: path
        type: integer
        required: true
        description: The ID of the board to delete
    responses:
      200:
        description: Board deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Board deleted successfully"
      404:
        description: Board not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Board not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Access already validated by @require_board_access decorator
        board = db.query(Board).filter(Board.id == board_id).first()

        if not board:
            return jsonify({"success": False, "message": "Board not found"}), 404

        # Check if this board is set as default_board for the current user
        user_id = g.user.id
        from utils import get_user_scoped_query
        default_board_setting = (
            get_user_scoped_query(db, Setting, user_id).filter(Setting.key == "default_board").first()
        )
        if default_board_setting:
            try:
                default_board_id = json.loads(default_board_setting.value)
                if default_board_id == board_id:
                    # Reset to null since we're deleting the default board
                    default_board_setting.value = "null"
                    logger.info(
                        f"Reset default_board setting for user {user_id} because board {board_id} was deleted"
                    )
            except (json.JSONDecodeError, ValueError):
                # Ignore if setting value is malformed - we're deleting the board anyway
                pass

        db.delete(board)
        db.commit()

        return jsonify({"success": True, "message": "Board deleted successfully"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>", methods=["PATCH"])
@require_board_access()
@require_permission('board.edit')
def update_board(board_id):
    """Update a board's name and/or description with validation.

    This endpoint updates a board after validating:
    - At least one field (name or description) is provided
    - Name (if provided) is a string and within length limits
    - Description (if provided) is a string and within length limits

    ---
    tags:
      - Boards
    parameters:
      - name: board_id
        in: path
        type: integer
        required: true
        description: The ID of the board to update
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: "Updated Board Name"
              description: The new name for the board
            description:
              type: string
              example: "Updated board description"
              description: The new description for the board
    responses:
      200:
        description: Board updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            board:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                name:
                  type: string
                  example: "Updated Board Name"
                description:
                  type: string
                  example: "Updated board description"
            message:
              type: string
              example: "Board updated successfully"
      400:
        description: Bad request - no valid fields provided
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "At least one field (name or description) is required"
      404:
        description: Board not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Board not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data or ("name" not in data and "description" not in data):
            return create_error_response(
                "At least one field (name or description) is required", 400
            )

        # Access already validated by @require_board_access decorator
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            return create_error_response("Board not found", 404)

        # Update and validate name if provided
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                return create_error_response("Name must be a string", 400)

            name = sanitize_string(name)
            if not name:
                return create_error_response("Name cannot be empty", 400)

            is_valid, error = validate_string_length(name, MAX_TITLE_LENGTH, "Name")
            if not is_valid:
                return create_error_response(error, 400)

            board.name = name

        # Update and validate description if provided
        if "description" in data:
            description = data["description"]
            if description is not None:
                if not isinstance(description, str):
                    return create_error_response("Description must be a string", 400)

                description = sanitize_string(description)
                is_valid, error = validate_string_length(
                    description, MAX_DESCRIPTION_LENGTH, "Description"
                )
                if not is_valid:
                    return create_error_response(error, 400)

            board.description = description

        # Set updated_at timestamp
        from datetime import datetime
        board.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(board)

        result = {
            "id": board.id, 
            "name": board.name, 
            "description": board.description,
            "created_at": board.created_at.isoformat() if board.created_at else None,
            "updated_at": board.updated_at.isoformat() if board.updated_at else None
        }
        return create_success_response(
            {"board": result, "message": "Board updated successfully"}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating board {board_id}: {str(e)}")
        return create_error_response("Failed to update board", 500)
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>/columns", methods=["GET"])
@require_board_access()
def get_board_columns(board_id):
    """Get all columns for a specific board (user must have access).
    ---
    tags:
      - Columns
    parameters:
      - name: board_id
        in: path
        type: integer
        required: true
        description: The ID of the board
    responses:
      200:
        description: List of columns for the board
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            columns:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                    example: 1
                  board_id:
                    type: integer
                    example: 1
                  name:
                    type: string
                    example: "To Do"
                  order:
                    type: integer
                    example: 0
      401:
        description: Authentication required
      403:
        description: Access denied to this board
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        from models import BoardColumn

        # Access already validated by @require_board_access decorator
        columns = (
            db.query(BoardColumn)
            .filter(BoardColumn.board_id == board_id)
            .order_by(BoardColumn.order)
            .all()
        )
        return jsonify(
            {
                "success": True,
                "columns": [
                    {
                        "id": c.id,
                        "board_id": c.board_id,
                        "name": c.name,
                        "order": c.order,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None
                    }
                    for c in columns
                ],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>/columns", methods=["POST"])
@require_board_access()
@require_permission('column.create')
def create_column(board_id):
    """Create a new column for a board with input validation.

    This endpoint creates a new column after validating:
    - Name is provided, is a string, and within length limits
    - Order (if provided) is a valid non-negative integer
    - Board exists

    ---
    tags:
      - Columns
    parameters:
      - name: board_id
        in: path
        type: integer
        required: true
        description: The ID of the board
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: "To Do"
              description: The name of the column to create
            order:
              type: integer
              example: 0
              description: The order position of the column (optional, defaults to last)
    responses:
      201:
        description: Column created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            column:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                board_id:
                  type: integer
                  example: 1
                name:
                  type: string
                  example: "To Do"
                order:
                  type: integer
                  example: 0
      400:
        description: Bad request - missing name
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Name is required"
      404:
        description: Board not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Board not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data or "name" not in data:
            return create_error_response("Name is required", 400)

        # Verify board exists
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            return create_error_response("Board not found", 404)

        # Validate and sanitize name
        name = data.get("name")
        if not isinstance(name, str):
            return create_error_response("Name must be a string", 400)

        name = sanitize_string(name)
        if not name:
            return create_error_response("Name cannot be empty", 400)

        is_valid, error = validate_string_length(name, MAX_TITLE_LENGTH, "Name")
        if not is_valid:
            return create_error_response(error, 400)

        # If order not specified, add to end
        from models import BoardColumn

        if "order" in data:
            order = data["order"]
            is_valid, error = validate_integer(order, "Order", min_value=0)
            if not is_valid:
                return create_error_response(error, 400)
        else:
            max_order = (
                db.query(BoardColumn).filter(BoardColumn.board_id == board_id).count()
            )
            order = max_order

        from datetime import datetime
        now = datetime.utcnow()
        column = BoardColumn(board_id=board_id, name=name, order=order, updated_at=now)
        db.add(column)
        db.commit()
        db.refresh(column)

        result = {
            "id": column.id,
            "board_id": column.board_id,
            "name": column.name,
            "order": column.order,
            "created_at": column.created_at.isoformat() if column.created_at else None,
            "updated_at": column.updated_at.isoformat() if column.updated_at else None
        }

        # Broadcast column creation so other connected clients can refresh immediately.
        broadcast_event('column_created', {
          'board_id': board_id,
          'column_id': column.id,
          'column_data': result
        }, board_id)

        return create_success_response({"column": result}, status_code=201)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating column for board {board_id}: {str(e)}")
        return create_error_response("Failed to create column", 500)
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>", methods=["DELETE"])
@require_permission('column.delete')
def delete_column(column_id):
    """Delete a column by ID.
    ---
    tags:
      - Columns
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: The ID of the column to delete
    responses:
      200:
        description: Column deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Column deleted successfully"
      404:
        description: Column not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Column not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        from models import BoardColumn

        user_id = get_current_user_id()
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()

        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404

        # Verify user owns the board this column belongs to
        board = get_user_scoped_query(db, Board, user_id).filter(Board.id == column.board_id).first()
        if not board:
            return jsonify({"success": False, "message": "Access denied"}), 403

        board_id = column.board_id

        db.delete(column)
        db.commit()

        # Broadcast column deletion so other clients can refresh immediately.
        broadcast_event('column_deleted', {
          'board_id': board_id,
          'column_id': column_id
        }, board_id)

        return jsonify({"success": True, "message": "Column deleted successfully"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>", methods=["PATCH"])
@require_permission('column.update')
def update_column(column_id):
    """Update a column's name and/or order.
    ---
    tags:
      - Columns
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: The ID of the column to update
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: "In Progress"
              description: The new name for the column
            order:
              type: integer
              example: 1
              description: The new order position (columns >= this order will be incremented)
    responses:
      200:
        description: Column updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            column:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                board_id:
                  type: integer
                  example: 1
                name:
                  type: string
                  example: "In Progress"
                order:
                  type: integer
                  example: 0
      400:
        description: Bad request
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
      404:
        description: Column not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Column not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data:
            return create_error_response("No data provided", 400)

        from models import BoardColumn

        user_id = get_current_user_id()
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()

        if not column:
            return create_error_response("Column not found", 404)

        # Verify user owns the board this column belongs to
        board = get_user_scoped_query(db, Board, user_id).filter(Board.id == column.board_id).first()
        if not board:
            return create_error_response("Access denied", 403)

        old_order = column.order
        board_id = column.board_id
        
        # Track if user changed the name (not just reordering)
        name_changed = False

        # Update and validate name if provided
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                return create_error_response("Name must be a string", 400)

            name = sanitize_string(name)
            if not name:
                return create_error_response("Name cannot be empty", 400)

            is_valid, error = validate_string_length(name, MAX_TITLE_LENGTH, "Name")
            if not is_valid:
                return create_error_response(error, 400)

            column.name = name
            name_changed = True

        # Handle order change if provided
        if "order" in data:
            new_order = data["order"]

            is_valid, error = validate_integer(new_order, "Order", min_value=0)
            if not is_valid:
                return create_error_response(error, 400)

            if new_order != old_order:
                if new_order < old_order:
                    # Moving left: increment columns between new and old position
                    columns_to_update = (
                        db.query(BoardColumn)
                        .filter(
                            BoardColumn.board_id == board_id,
                            BoardColumn.order >= new_order,
                            BoardColumn.order < old_order,
                        )
                        .all()
                    )
                    for col in columns_to_update:
                        col.order += 1
                else:
                    # Moving right: decrement columns between old and new position
                    columns_to_update = (
                        db.query(BoardColumn)
                        .filter(
                            BoardColumn.board_id == board_id,
                            BoardColumn.order > old_order,
                            BoardColumn.order <= new_order,
                        )
                        .all()
                    )
                    for col in columns_to_update:
                        col.order -= 1

                column.order = new_order
        
        # Set updated_at timestamp only if name changed (not just reordering)
        if name_changed:
            from datetime import datetime
            column.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(column)
        result = {
            "id": column.id,
            "board_id": column.board_id,
            "name": column.name,
            "order": column.order,
            "created_at": column.created_at.isoformat() if column.created_at else None,
            "updated_at": column.updated_at.isoformat() if column.updated_at else None
        }

        # Broadcast column update event
        broadcast_event('column_updated', {
            'board_id': board_id,
            'column_id': column.id,
            'column_data': result
        }, board_id)

        return jsonify({"success": True, "column": result}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>/cards", methods=["GET"])
@require_permission('card.view')
def get_column_cards(column_id):
    """Get all cards for a specific column.
    ---
    tags:
      - Cards
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: The ID of the column
      - name: archived
        in: query
        type: string
        required: false
        description: Filter by archived status - 'true' for archived, 'false' for unarchived, 'both' for all (default is 'false')
        enum: ['true', 'false', 'both']
        default: 'false'
    responses:
      200:
        description: List of cards for the column
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            cards:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                    example: 1
                  column_id:
                    type: integer
                    example: 1
                  title:
                    type: string
                    example: "Task title"
                  description:
                    type: string
                    example: "Task description"
                  order:
                    type: integer
                    example: 0
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    try:
        db = SessionLocal()
        from models import Card

        user_id = g.user.id
        # Get archived filter from query parameter (default to false - unarchived only)
        archived_param = request.args.get('archived', 'false').lower()

        # Always filter out scheduled template cards (scheduled=True) from task views
        cards_query = get_user_scoped_query(db, Card, user_id).filter(Card.column_id == column_id).filter(Card.scheduled.is_(False))
        
        # Apply archived filter
        if archived_param == 'true':
            cards_query = cards_query.filter(Card.archived.is_(True))
        elif archived_param == 'false':
            cards_query = cards_query.filter(Card.archived.is_(False))
        # If 'both', don't add archived filter
        
        cards = cards_query.order_by(Card.order).all()
        
        # Serialize cards before closing session to access relationships
        cards_data = [
            {
                "id": c.id,
                "column_id": c.column_id,
                "title": c.title,
                "description": c.description,
                "order": c.order,
                "archived": c.archived,
                "done": c.done,
                "scheduled": c.scheduled,
                "schedule": c.schedule,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "checklist_items": [
                    {
                        "id": item.id,
                        "card_id": item.card_id,
                        "name": item.name,
                        "checked": item.checked,
                        "order": item.order,
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                        "updated_at": item.updated_at.isoformat() if item.updated_at else None
                    }
                    for item in c.checklist_items
                ]
            }
            for c in cards
        ]
        
        db.close()
        return jsonify(
            {
                "success": True,
                "cards": cards_data
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/boards/<int:board_id>/cards", methods=["GET"])
@require_board_access()
def get_board_cards(board_id):
    """Get all cards for a board with nested structure (board -> columns -> cards).
    ---
    tags:
      - Cards
    parameters:
      - name: board_id
        in: path
        type: integer
        required: true
        description: The ID of the board
      - name: archived
        in: query
        type: string
        required: false
        description: Filter by archived status - 'true' for archived, 'false' for unarchived, 'both' for all (default is 'false')
        enum: ['true', 'false', 'both']
        default: 'false'
    responses:
      200:
        description: Nested structure of board with columns and cards
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            board:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                name:
                  type: string
                  example: "My Board"
                columns:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: integer
                        example: 1
                      name:
                        type: string
                        example: "To Do"
                      order:
                        type: integer
                        example: 0
                      cards:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: integer
                              example: 1
                            title:
                              type: string
                              example: "Task title"
                            description:
                              type: string
                              example: "Task description"
                            order:
                              type: integer
                              example: 0
      404:
        description: Board not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Board not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    try:
        db = SessionLocal()
        from models import BoardColumn, Card

        # Access already validated by @require_board_access decorator
        # Get archived filter from query parameter (default to false - unarchived only)
        archived_param = request.args.get('archived', 'false').lower()

        selected_assignee_ids = _parse_assignee_ids_query_param(request.args.get('assignee_ids'))
        include_unassigned = request.args.get('include_unassigned', 'false').lower() == 'true'
        include_secondary_assignees = request.args.get('include_secondary_assignees', 'false').lower() == 'true'

        # Get board
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            db.close()
            return jsonify({"success": False, "message": "Board not found"}), 404

        # Get columns for board
        columns = (
            db.query(BoardColumn)
            .filter(BoardColumn.board_id == board_id)
            .order_by(BoardColumn.order)
            .all()
        )

        # Build nested structure
        result = {"id": board.id, "name": board.name, "columns": []}
        eligible_users = _get_board_assignee_users(db, board_id)
        result["assignee_filter_users"] = [_user_summary(u) for u in eligible_users]

        for column in columns:
            # Get cards for this column with archived filter
            # Always filter out scheduled template cards (scheduled=True) from task views
            cards_query = db.query(Card).filter(Card.column_id == column.id).filter(Card.scheduled.is_(False))
            cards_query = cards_query.options(selectinload(Card.assigned_to))

            cards_query = _apply_assignee_card_filters(
              cards_query,
              selected_assignee_ids,
              include_unassigned,
              include_secondary_assignees,
            )
            
            # Apply archived filter
            if archived_param == 'true':
                cards_query = cards_query.filter(Card.archived.is_(True))
            elif archived_param == 'false':
                cards_query = cards_query.filter(Card.archived.is_(False))
            # If 'both', don't add archived filter
            
            cards = cards_query.order_by(Card.order).all()

            # Serialize cards with checklist items and comments while session is active
            cards_data = [
                {
                    "id": card.id,
                    "title": card.title,
                    "description": card.description,
                    "order": card.order,
                    "archived": card.archived,
                    "done": card.done,
                    "scheduled": card.scheduled,
                    "schedule": card.schedule,
                    "created_at": card.created_at.isoformat() if card.created_at else None,
                    "updated_at": card.updated_at.isoformat() if card.updated_at else None,
                    "assigned_to": {
                        "id": card.assigned_to.id,
                        "display_name": card.assigned_to.display_name,
                        "username": card.assigned_to.username,
                        "profile_colour": card.assigned_to.profile_colour,
                    } if card.assigned_to else None,
                    "checklist_items": [
                        {
                            "id": item.id,
                            "card_id": item.card_id,
                            "name": item.name,
                            "checked": item.checked,
                            "order": item.order,
                            "created_at": item.created_at.isoformat() if item.created_at else None,
                            "updated_at": item.updated_at.isoformat() if item.updated_at else None
                        }
                        for item in card.checklist_items
                    ],
                    "comments": [
                        {
                            "id": comment.id,
                            "card_id": comment.card_id,
                            "comment": comment.comment,
                            "order": comment.order,
                            "created_at": comment.created_at.isoformat() if comment.created_at else None
                        }
                        for comment in card.comments
                    ]
                }
                for card in cards
            ]

            column_data = {
                "id": column.id,
                "name": column.name,
                "order": column.order,
                "created_at": column.created_at.isoformat() if column.created_at else None,
                "updated_at": column.updated_at.isoformat() if column.updated_at else None,
                "cards": cards_data,
            }
            result["columns"].append(column_data)

        # Check if user has edit permissions for this board
        user_permissions = get_user_permissions(g.user.id, board_id)
        edit_permissions = ['card.create', 'card.edit', 'card.update', 'card.delete', 'card.archive', 'board.edit']
        can_edit = any(perm in user_permissions for perm in edit_permissions)
        result["can_edit"] = can_edit

        db.close()
        return jsonify({"success": True, "board": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


def _user_summary(user):
    return {
        "id": user.id,
        "display_name": user.display_name,
        "username": user.username,
        "profile_colour": user.profile_colour,
    }


def _parse_assignee_ids_query_param(raw_value):
    if not raw_value:
        return []

    selected_ids = []
    for part in str(raw_value).split(','):
        candidate = part.strip()
        if not candidate:
            continue
        if not candidate.isdigit():
            continue
        parsed = int(candidate)
        if parsed > 0:
            selected_ids.append(parsed)

    # Preserve order while deduplicating
    return list(dict.fromkeys(selected_ids))


def _get_board_eligible_assignee_ids(db, board_id, board=None):
    if not board_id:
        return set()

    eligible_ids = set()
    if board is None:
        board = db.query(Board).filter(Board.id == board_id).first()
    if board and board.owner and getattr(board.owner, "is_active", True):
        eligible_ids.add(board.owner.id)

    view_perms = {'card.view', 'card.update', 'card.edit', 'card.create'}

    board_roles = (
        db.query(UserRole, Role)
        .join(Role, UserRole.role_id == Role.id)
        .filter(UserRole.board_id == board_id)
        .all()
    )
    for ur, role in board_roles:
        role_perms = set(json.loads(role.permissions))
        if role_perms & view_perms:
            eligible_ids.add(ur.user_id)

    global_roles = (
        db.query(UserRole, Role)
        .join(Role, UserRole.role_id == Role.id)
        .filter(UserRole.board_id.is_(None))
        .all()
    )
    for ur, role in global_roles:
        role_perms = set(json.loads(role.permissions))
        if 'system.admin' in role_perms:
            eligible_ids.add(ur.user_id)

    return eligible_ids


def _get_board_assignee_users(db, board_id, board=None):
    eligible_ids = _get_board_eligible_assignee_ids(db, board_id, board=board)
    if not eligible_ids:
        return []

    return (
        db.query(User)
        .filter(User.id.in_(eligible_ids), User.is_active.is_(True))
        .order_by(User.username)
        .all()
    )


def _apply_assignee_card_filters(cards_query, selected_assignee_ids, include_unassigned, include_secondary_assignees):
    selected_ids = [int(uid) for uid in selected_assignee_ids if isinstance(uid, int) and uid > 0]
    has_selected_users = len(selected_ids) > 0

    if not has_selected_users and not include_unassigned:
        return cards_query

    filters = []

    if has_selected_users:
        filters.append(Card.assigned_to_id.in_(selected_ids))
        if include_secondary_assignees:
            secondary_card_ids = (
                cards_query.session.query(CardSecondaryAssignee.card_id)
                .filter(CardSecondaryAssignee.user_id.in_(selected_ids))
            )
            filters.append(Card.id.in_(secondary_card_ids))

    if include_unassigned:
        filters.append(Card.assigned_to_id.is_(None))

    return cards_query.filter(or_(*filters))


@app.route("/api/columns/<int:column_id>/cards", methods=["POST"])
@require_permission('card.create')
def create_card(column_id):
    """Create a new card in a column with input validation.

    This endpoint creates a new card after validating:
    - Title is provided, is a string, and within length limits
    - Description (if provided) is a string and within length limits
    - Order (if provided) is a valid non-negative integer
    - Column exists

    ---
    tags:
      - Cards
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: The ID of the column
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - title
          properties:
            title:
              type: string
              example: "New task"
              description: The title of the card
            description:
              type: string
              example: "Task details"
              description: The description of the card (optional)
            order:
              type: integer
              example: 0
              description: The order position (optional, defaults to end)
            scheduled:
              type: boolean
              example: false
              description: Whether this is a template card (optional, defaults to false)
    responses:
      201:
        description: Card created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            card:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                column_id:
                  type: integer
                  example: 1
                title:
                  type: string
                  example: "New task"
                description:
                  type: string
                  example: "Task details"
                order:
                  type: integer
                  example: 0
      400:
        description: Bad request - missing title
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Title is required"
      404:
        description: Column not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Column not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data or "title" not in data:
            return create_error_response("Title is required", 400)

        from models import BoardColumn, Card

        user_id = g.user.id
        
        # Verify column exists and user has access to its board
        column = get_user_scoped_query(db, BoardColumn, user_id).filter(BoardColumn.id == column_id).first()
        if not column:
            return create_error_response("Column not found or access denied", 404)

        # Validate and sanitize title
        title = data.get("title")
        if not isinstance(title, str):
            return create_error_response("Title must be a string", 400)

        title = sanitize_string(title)
        if not title:
            return create_error_response("Title cannot be empty", 400)

        is_valid, error = validate_string_length(title, MAX_TITLE_LENGTH, "Title")
        if not is_valid:
            return create_error_response(error, 400)

        # Validate and sanitize description if provided
        description = data.get("description", "")
        if description is not None:
            if not isinstance(description, str):
                return create_error_response("Description must be a string", 400)

            description = sanitize_string(description)
            is_valid, error = validate_string_length(
                description, MAX_DESCRIPTION_LENGTH, "Description"
            )
            if not is_valid:
                return create_error_response(error, 400)

        # Validate order if provided
        if "order" in data:
            order = data["order"]
            is_valid, error = validate_integer(order, "Order", min_value=0)
            if not is_valid:
                return create_error_response(error, 400)

            # Increment order of existing cards >= this order
            existing_cards = (
                db.query(Card)
                .filter(Card.column_id == column_id, Card.order >= order)
                .all()
            )
            for card_to_update in existing_cards:
                card_to_update.order += 1
        else:
            # Add at the end
            order = db.query(Card).filter(Card.column_id == column_id).count()

        # Validate scheduled parameter if provided
        scheduled = data.get("scheduled", False)
        if scheduled is not None and not isinstance(scheduled, bool):
            return create_error_response("Scheduled must be a boolean", 400)

        # Validate schedule parameter if provided
        schedule = data.get("schedule")
        if schedule is not None:
            if not isinstance(schedule, int):
                return create_error_response("Schedule must be an integer", 400)

        # Create card
        from datetime import datetime
        now = datetime.utcnow()
        card = Card(
            column_id=column_id, 
            title=title, 
            description=description, 
            order=order,
            scheduled=scheduled,
            schedule=schedule,
            updated_at=now,
            created_by_id=g.user.id,
            assigned_to_id=None,
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        result = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order,
            "scheduled": card.scheduled,
            "schedule": card.schedule,
            "archived": card.archived,
            "done": card.done,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None
        }

        # Get board_id for WebSocket broadcast
        board_id = column.board_id
        if board_id is not None:
            broadcast_event('card_created', {
                'board_id': board_id,
                'column_id': column_id,
                'card_id': card.id,
                'card_data': result
            }, board_id)
        else:
            logger.warning(f"Skipping card_created broadcast for card {card.id}: column {column_id} has no board_id")

        return create_success_response({"card": result}, status_code=201)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating card in column {column_id}: {str(e)}")
        return create_error_response("Failed to create card", 500)
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>/cards", methods=["DELETE"])
@require_permission('card.delete')
def delete_all_cards_in_column(column_id):
    """Delete all cards in a column.
    ---
    tags:
      - Cards
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: The ID of the column whose cards should be deleted
    responses:
      200:
        description: All cards deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Deleted 5 cards"
            deleted_count:
              type: integer
              example: 5
      404:
        description: Column not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Column not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        from models import BoardColumn, Card

        user_id = get_current_user_id()
        
        # Verify column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404
        
        # Verify user owns the board this column belongs to
        board = get_user_scoped_query(db, Board, user_id).filter(Board.id == column.board_id).first()
        if not board:
            return jsonify({"success": False, "message": "Access denied"}), 403

        # Delete all cards in the column
        deleted_count = (
            db.query(Card)
            .filter(Card.column_id == column_id)
            .delete(synchronize_session=False)
        )
        db.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Deleted {deleted_count} cards",
                    "deleted_count": deleted_count,
                }
            ),
            200,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting cards from column {column_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/columns/<int:source_column_id>/cards/move", methods=["POST"])
@require_permission('card.edit')
def move_all_cards_in_column(source_column_id):
    """Move all cards from one column to another in a single transaction.
    ---
    tags:
      - Cards
    parameters:
      - name: source_column_id
        in: path
        type: integer
        required: true
        description: The ID of the source column
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - target_column_id
            - position
          properties:
            target_column_id:
              type: integer
              description: The ID of the target column
              example: 2
            position:
              type: string
              enum: [top, bottom]
              description: Where to place cards in target column
              example: "bottom"
            include_archived:
              type: boolean
              description: Whether to include archived cards in the move
              example: false
              default: false
    responses:
      200:
        description: All cards moved successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Moved 5 cards"
            moved_count:
              type: integer
              example: 5
      400:
        description: Invalid request
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Invalid position value"
      404:
        description: Column not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Source column not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        from models import BoardColumn, Card

        user_id = get_current_user_id()
        
        data = request.get_json()
        target_column_id = data.get("target_column_id")
        position = data.get("position", "bottom")
        include_archived = data.get("include_archived", False)

        # Validate inputs
        if not target_column_id:
            return jsonify({"success": False, "message": "target_column_id is required"}), 400
        
        if position not in ["top", "bottom"]:
            return jsonify({"success": False, "message": "Invalid position value. Must be 'top' or 'bottom'"}), 400

        # Verify source column exists
        source_column = db.query(BoardColumn).filter(BoardColumn.id == source_column_id).first()
        if not source_column:
            return jsonify({"success": False, "message": "Source column not found"}), 404
        
        # Verify user owns the board this source column belongs to
        board = get_user_scoped_query(db, Board, user_id).filter(Board.id == source_column.board_id).first()
        if not board:
            return jsonify({"success": False, "message": "Access denied to source board"}), 403

        # Verify target column exists
        target_column = db.query(BoardColumn).filter(BoardColumn.id == target_column_id).first()
        if not target_column:
            return jsonify({"success": False, "message": "Target column not found"}), 404
        
        # Verify user owns the board this target column belongs to
        target_board = get_user_scoped_query(db, Board, user_id).filter(Board.id == target_column.board_id).first()
        if not target_board:
            return jsonify({"success": False, "message": "Access denied to target board"}), 403

        # Get cards from source column, optionally filtering out archived cards
        source_query = db.query(Card).filter(Card.column_id == source_column_id)
        if not include_archived:
            source_query = source_query.filter(Card.archived.is_(False))
        source_cards = source_query.order_by(Card.order).all()

        if not source_cards:
            return jsonify({"success": True, "message": "No cards to move", "moved_count": 0}), 200

        # Get cards in target column to calculate new order values
        target_cards = (
            db.query(Card)
            .filter(Card.column_id == target_column_id)
            .order_by(Card.order)
            .all()
        )

        # Calculate new order values based on position
        if position == "top":
            # Move existing target cards down to make room
            for i, card in enumerate(target_cards):
                card.order = i + len(source_cards)
            
            # Place source cards at top (maintain original order)
            for i, card in enumerate(source_cards):
                card.column_id = target_column_id
                card.order = i
        else:  # bottom
            # Target cards keep their order
            # Source cards go after target cards
            start_order = len(target_cards)
            for i, card in enumerate(source_cards):
                card.column_id = target_column_id
                card.order = start_order + i

        db.commit()

        # Broadcast column reorder/move event to both affected boards
        if source_column.board_id:
            broadcast_event('cards_moved', {
                'board_id': source_column.board_id,
                'source_column_id': source_column_id,
                'target_column_id': target_column_id,
                'moved_count': len(source_cards),
                'position': position
            }, source_column.board_id)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Moved {len(source_cards)} cards",
                    "moved_count": len(source_cards),
                }
            ),
            200,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error moving cards from column {source_column_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>", methods=["GET"])
@require_permission('card.view')
def get_card(card_id):
    """Get a single card with its checklist items (user must have access).
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card to retrieve
    responses:
      200:
        description: Card data retrieved successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            card:
              type: object
              properties:
                id:
                  type: integer
                title:
                  type: string
                description:
                  type: string
                column_id:
                  type: integer
                order:
                  type: integer
                checklist_items:
                  type: array
                  items:
                    type: object
      401:
        description: Authentication required
      403:
        description: Permission denied
      404:
        description: Card not found
    """
    db = SessionLocal()
    try:
        from models import Card
        
        user_id = g.user.id
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()
        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404
        
        # Serialize card with checklist items and comments
        card_data = {
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "column_id": card.column_id,
            "order": card.order,
            "archived": card.archived,
            "done": card.done,
            "scheduled": card.scheduled,
            "schedule": card.schedule,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None,
            "checklist_items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "checked": item.checked,
                    "order": item.order,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None
                }
                for item in sorted(card.checklist_items, key=lambda x: x.order)
            ],
            "comments": [
                {
                    "id": comment.id,
                    "card_id": comment.card_id,
                    "comment": comment.comment,
                    "order": comment.order,
                    "created_at": comment.created_at.isoformat() if comment.created_at else None
                }
                for comment in card.comments
            ]
        }
        
        return jsonify({"success": True, "card": card_data})
    except Exception as e:
        logger.error(f"Error getting card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>", methods=["PATCH"])
@require_permission('card.update')
def update_card(card_id):
    """Update a card's title, description, column, and/or order.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card to update
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            title:
              type: string
              example: "Updated task title"
              description: The new title for the card
            description:
              type: string
              example: "Updated task description"
              description: The new description for the card
            column_id:
              type: integer
              example: 2
              description: The new column ID if moving the card
            order:
              type: integer
              example: 1
              description: The new order position (cards >= this order will be incremented)
    responses:
      200:
        description: Card updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            card:
              type: object
              properties:
                id:
                  type: integer
                  example: 1
                column_id:
                  type: integer
                  example: 1
                title:
                  type: string
                  example: "Updated task title"
                description:
                  type: string
                  example: "Updated task description"
                order:
                  type: integer
                  example: 0
      404:
        description: Card not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Card not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data:
            return create_error_response("No data provided", 400)

        from models import Card, BoardColumn

        user_id = g.user.id
        
        # Verify card exists and user has access to its board
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()

        if not card:
            return create_error_response("Card not found or access denied", 404)

        old_column_id = card.column_id
        old_order = card.order
        
        # Track if user made content changes (not just reordering within same column)
        user_content_changed = False

        # Update and validate title if provided
        if "title" in data:
            title = data["title"]
            if not isinstance(title, str):
                return create_error_response("Title must be a string", 400)

            title = sanitize_string(title)
            if not title:
                return create_error_response("Title cannot be empty", 400)

            is_valid, error = validate_string_length(title, MAX_TITLE_LENGTH, "Title")
            if not is_valid:
                return create_error_response(error, 400)

            card.title = title
            user_content_changed = True

        # Update and validate description if provided
        if "description" in data:
            description = data["description"]
            if description is not None:
                if not isinstance(description, str):
                    return create_error_response("Description must be a string", 400)

                description = sanitize_string(description)
                is_valid, error = validate_string_length(
                    description, MAX_DESCRIPTION_LENGTH, "Description"
                )
                if not is_valid:
                    return create_error_response(error, 400)

            card.description = description
            user_content_changed = True

        # Update archived status if provided
        if "archived" in data:
            archived = data["archived"]
            if not isinstance(archived, bool):
                return create_error_response("Archived must be a boolean", 400)
            card.archived = archived
            user_content_changed = True

        # Handle column and order changes
        if "column_id" in data or "order" in data:
            new_column_id = data.get("column_id", card.column_id)
            new_order = data.get("order", card.order)

            # Validate column_id if provided
            if "column_id" in data:
                is_valid, error = validate_integer(
                    new_column_id, "Column ID", min_value=1
                )
                if not is_valid:
                    return create_error_response(error, 400)

            # Validate order if provided
            if "order" in data:
                is_valid, error = validate_integer(new_order, "Order", min_value=0)
                if not is_valid:
                    return create_error_response(error, 400)

            # Verify new column exists if changing columns
            if new_column_id != old_column_id:
                column = (
                    db.query(BoardColumn)
                    .filter(BoardColumn.id == new_column_id)
                    .first()
                )
                if not column:
                    return create_error_response("Target column not found", 404)
                
                # Moving to different column is a state change - update timestamp
                user_content_changed = True

            # If moving to a different column
            if new_column_id != old_column_id:
                # Decrement order of cards after old position in old column (excluding archived)
                db.query(Card).filter(
                    Card.column_id == old_column_id, 
                    Card.order > old_order,
                    Card.archived == False
                ).update({Card.order: Card.order - 1})

                # Increment order of cards >= new position in new column (excluding archived)
                db.query(Card).filter(
                    Card.column_id == new_column_id, 
                    Card.order >= new_order,
                    Card.archived == False
                ).update({Card.order: Card.order + 1})

                card.column_id = new_column_id
                card.order = new_order

            # If reordering within the same column
            elif new_order != old_order:
                if new_order < old_order:
                    # Moving up: increment cards between new and old position (excluding archived)
                    db.query(Card).filter(
                        Card.column_id == old_column_id,
                        Card.order >= new_order,
                        Card.order < old_order,
                        Card.archived == False
                    ).update({Card.order: Card.order + 1})
                else:
                    # Moving down: decrement cards between old and new position (excluding archived)
                    db.query(Card).filter(
                        Card.column_id == old_column_id,
                        Card.order > old_order,
                        Card.order <= new_order,
                        Card.archived == False
                    ).update({Card.order: Card.order - 1})

                card.order = new_order
        
        # Set updated_at timestamp if user made content changes
        if user_content_changed:
            from datetime import datetime
            card.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(card)

        result = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order,
            "done": card.done,
            "archived": card.archived,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None
        }

        # Get board_id for WebSocket broadcast
        column = db.query(BoardColumn).filter(BoardColumn.id == card.column_id).first()
        if column:
            broadcast_event('card_updated', {
                'board_id': column.board_id,
                'card_id': card.id,
                'column_id': card.column_id,
                'card_data': result,
                'moved': old_column_id != card.column_id or old_order != card.order
            }, column.board_id, getattr(request, "sid", None))

        return create_success_response({"card": result})

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating card {card_id}: {str(e)}")
        return create_error_response("Failed to update card", 500)
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>", methods=["DELETE"])
@require_permission('card.delete')
def delete_card(card_id):
    """Delete a card by ID.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card to delete
    responses:
      200:
        description: Card deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Card deleted successfully"
      404:
        description: Card not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "Card not found"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    try:
        db = SessionLocal()
        from models import Card, BoardColumn

        user_id = g.user.id
        
        # Verify card exists and user has access to its board
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()

        if not card:
            db.close()
            return jsonify({"success": False, "message": "Card not found or access denied"}), 404

        # Get board_id for WebSocket broadcast before deleting
        column = db.query(BoardColumn).filter(BoardColumn.id == card.column_id).first()
        board_id = column.board_id if column else None

        db.delete(card)
        db.commit()
        db.close()

        # Broadcast card deletion
        if board_id:
            broadcast_event('card_deleted', {
                'board_id': board_id,
                'card_id': card_id,
                'column_id': card.column_id
            }, board_id)
        else:
            logger.warning(f"⚠️  Failed to broadcast card_deleted for card {card_id}: column or board_id not found")

        return jsonify({"success": True, "message": "Card deleted successfully"}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting card {card_id}: {str(e)}")
        logger.exception(e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/cards/<int:card_id>/assignees", methods=["GET"])
@require_permission('card.view')
def get_card_assignees(card_id):
    """Get primary assignee, secondary assignees, and available users for a card.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
    responses:
      200:
        description: Assignee info retrieved successfully
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Card, BoardColumn

        user_id = g.user.id
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()
        if not card:
            return create_error_response("Card not found or access denied", 404)

        # Resolve board_id
        column = db.query(BoardColumn).filter(BoardColumn.id == card.column_id).first()
        board_id = column.board_id if column else None

        # Primary assignee
        primary_assignee = _user_summary(card.assigned_to) if card.assigned_to else None

        # Secondary assignees
        secondary_assignees = [_user_summary(sa.user) for sa in card.secondary_assignees]

        # Build list of users with access to the card's board (for selection)
        available_users = [_user_summary(u) for u in _get_board_assignee_users(db, board_id)]

        return create_success_response({
            "primary_assignee": primary_assignee,
            "secondary_assignees": secondary_assignees,
            "available_users": available_users,
        })
    except Exception as e:
        logger.error(f"Error getting card assignees for card {card_id}: {str(e)}")
        return create_error_response("Failed to get card assignees", 500)
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/assignees", methods=["PUT"])
@require_permission('card.update')
def update_card_assignees(card_id):
    """Set the primary assignee and secondary assignees of a card.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            assigned_to_id:
              type: integer
              nullable: true
              description: User ID of the primary assignee, or null to clear
            secondary_assignee_ids:
              type: array
              items:
                type: integer
              description: Full list of user IDs to set as secondary assignees
    responses:
      200:
        description: Assignees updated successfully
      400:
        description: Invalid request data
      404:
        description: Card or user not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        try:
            data = request.get_json()
        except Exception:
            data = None
        if data is None:
            return create_error_response("No data provided", 400)

        from models import Card, CardSecondaryAssignee, User, BoardColumn

        user_id = g.user.id
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()
        if not card:
            return create_error_response("Card not found or access denied", 404)

        column = db.query(BoardColumn).filter(BoardColumn.id == card.column_id).first()
        board_id = column.board_id if column else None

        eligible_assignee_ids = _get_board_eligible_assignee_ids(db, board_id)

        # Validate and set primary assignee
        if "assigned_to_id" in data:
            new_assigned_to_id = data["assigned_to_id"]
            if new_assigned_to_id is not None:
                if not isinstance(new_assigned_to_id, int) or new_assigned_to_id < 1:
                    return create_error_response("assigned_to_id must be a positive integer or null", 400)
                assignee_user = db.query(User).filter(User.id == new_assigned_to_id, User.is_active.is_(True)).first()
                if not assignee_user:
                    return create_error_response("Assigned user not found", 404)
                if new_assigned_to_id not in eligible_assignee_ids:
                  return create_error_response("Assigned user does not have access to this board", 400)
            card.assigned_to_id = new_assigned_to_id

        # Validate and replace secondary assignees
        if "secondary_assignee_ids" in data:
            secondary_assignee_ids = data["secondary_assignee_ids"]
            if not isinstance(secondary_assignee_ids, list):
                return create_error_response("secondary_assignee_ids must be a list", 400)
            for uid in secondary_assignee_ids:
                if not isinstance(uid, int) or uid < 1:
                    return create_error_response("Each secondary_assignee_id must be a positive integer", 400)
            if secondary_assignee_ids:
                valid_users = db.query(User.id).filter(
                    User.id.in_(secondary_assignee_ids),
                    User.is_active.is_(True)
                ).all()
                valid_ids = {row.id for row in valid_users}
                invalid = set(secondary_assignee_ids) - valid_ids
                if invalid:
                    return create_error_response(f"User IDs not found or inactive: {sorted(invalid)}", 400)

            ineligible = set(secondary_assignee_ids) - eligible_assignee_ids
            if ineligible:
                return create_error_response(
                    f"User IDs do not have access to this board: {sorted(ineligible)}",
                    400,
                )

            # Remove all existing secondary assignees and replace
            db.query(CardSecondaryAssignee).filter(CardSecondaryAssignee.card_id == card_id).delete()
            primary_assignee_id = card.assigned_to_id
            unique_secondary_ids = {uid for uid in secondary_assignee_ids if uid != primary_assignee_id}
            for uid in unique_secondary_ids:
                db.add(CardSecondaryAssignee(card_id=card_id, user_id=uid))

        db.commit()
        db.refresh(card)

        primary_assignee = None
        if card.assigned_to:
            primary_assignee = {
                "id": card.assigned_to.id,
                "display_name": card.assigned_to.display_name,
                "username": card.assigned_to.username,
                "profile_colour": card.assigned_to.profile_colour,
            }
        secondary_assignees = [
            {
                "id": sa.user.id,
                "display_name": sa.user.display_name,
                "username": sa.user.username,
                "profile_colour": sa.user.profile_colour,
            }
            for sa in card.secondary_assignees
        ]

        return create_success_response({
          "primary_assignee": primary_assignee,
          "secondary_assignees": secondary_assignees,
        })
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating card assignees for card {card_id}: {str(e)}")
        return create_error_response("Failed to update card assignees", 500)
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/archive", methods=["PATCH"])
@require_permission('card.archive')
def archive_card(card_id):
    """Archive a card by ID.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card to archive
    responses:
      200:
        description: Card archived successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Card archived successfully"
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        user_id = g.user.id
        
        # Verify card exists and user has access to its board
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()

        if not card:
            return jsonify({"success": False, "message": "Card not found or access denied"}), 404

        board_id = card.column.board_id if card.column else None
        card.archived = True
        
        # Set updated_at timestamp
        from datetime import datetime
        card.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Refresh and serialize the card
        db.refresh(card)
        card_dict = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order,
            "archived": card.archived,
            "done": card.done,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None
        }

        # Broadcast card archived event
        if board_id:
            broadcast_event('card_archived', {
                'board_id': board_id,
                'card_id': card.id,
                'column_id': card.column_id,
                'card_data': card_dict
            }, board_id)

        return jsonify({"success": True, "message": "Card archived successfully", "card": card_dict}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error archiving card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to archive card"}), 500
    finally:
        db.close()

@app.route("/api/cards/<int:card_id>/unarchive", methods=["PATCH"])
@require_permission('card.archive')
def unarchive_card(card_id):
    """Unarchive a card by ID.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card to unarchive
    responses:
      200:
        description: Card unarchived successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Card unarchived successfully"
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        user_id = g.user.id
        
        # Verify card exists and user has access to its board
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()

        if not card:
            return jsonify({"success": False, "message": "Card not found or access denied"}), 404

        # Get the card's current order and column
        card_order = card.order
        column_id = card.column_id

        # Unarchive the card first
        card.archived = False
        
        # Set updated_at timestamp
        from datetime import datetime
        card.updated_at = datetime.utcnow()

        # Increment order of all active cards at this position and above
        # This ensures the unarchived card is inserted at its order position
        db.query(Card).filter(
            Card.column_id == column_id,
            Card.order >= card_order,
            Card.id != card_id,
            Card.archived == False
        ).update({Card.order: Card.order + 1}, synchronize_session=False)

        db.commit()
        
        # Refresh and serialize the card
        db.refresh(card)
        card_dict = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order,
            "archived": card.archived,
            "done": card.done,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None
        }

        # Get board_id for broadcast
        board_id = card.column.board_id if card.column else None
        if board_id:
            broadcast_event('card_unarchived', {
                'board_id': board_id,
                'card_id': card.id,
                'column_id': card.column_id,
                'card_data': card_dict
            }, board_id)

        return jsonify({"success": True, "message": "Card unarchived successfully", "card": card_dict}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error unarchiving card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to unarchive card"}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/done", methods=["GET"])
@require_permission('card.view')
def get_card_done_status(card_id):
    """Get the done status of a card (user must have access).
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
    responses:
      200:
        description: Card done status retrieved successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            card_id:
              type: integer
              example: 1
            done:
              type: boolean
              example: false
      401:
        description: Authentication required
      403:
        description: Permission denied
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        user_id = g.user.id
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()
        
        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404
        
        return jsonify({
            "success": True,
            "card_id": card.id,
            "done": card.done
        }), 200
    except Exception as e:
        logger.error(f"Error getting card done status {card_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to get card done status"}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/done", methods=["PATCH"])
@require_permission('card.update')
def update_card_done_status(card_id):
    """Update the done status of a card.
    ---
    tags:
      - Cards
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - done
          properties:
            done:
              type: boolean
              example: true
              description: The new done status
    responses:
      200:
        description: Card done status updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Card done status updated successfully"
            card_id:
              type: integer
              example: 1
            done:
              type: boolean
              example: true
      400:
        description: Invalid request
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        data = request.get_json()
        
        if data is None or "done" not in data:
            return jsonify({"success": False, "message": "done status is required"}), 400
        
        done_status = data.get("done")
        if not isinstance(done_status, bool):
            return jsonify({"success": False, "message": "done must be a boolean"}), 400
        
        user_id = g.user.id
        
        # Verify card exists and user has access to its board
        card = get_user_scoped_query(db, Card, user_id).filter(Card.id == card_id).first()
        
        if not card:
            return jsonify({"success": False, "message": "Card not found or access denied"}), 404
        
        board_id = card.column.board_id if card.column else None
        card.done = done_status
        
        # Set updated_at timestamp
        from datetime import datetime
        card.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Refresh card
        db.refresh(card)
        card_dict = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order,
            "archived": card.archived,
            "done": card.done
        }
        
        # Broadcast card done status change event
        if board_id:
            broadcast_event('card_done_status_changed', {
                'board_id': board_id,
                'card_id': card.id,
                'column_id': card.column_id,
                'done': done_status,
                'card_data': card_dict
            }, board_id)
        
        return jsonify({
            "success": True,
            "message": "Card done status updated successfully",
            "card_id": card.id,
            "done": card.done
        }), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating card done status {card_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to update card done status"}), 500
    finally:
        db.close()


def _get_fully_authorized_batch_cards(db, user_id, card_ids, *, order_by=None):
    from models import Card

    unique_card_ids = list(dict.fromkeys(card_ids))
    query = get_user_scoped_query(db, Card, user_id).filter(Card.id.in_(unique_card_ids))

    if order_by is not None:
        query = query.order_by(*order_by)

    cards = query.all()
    authorized_ids = {card.id for card in cards}
    requested_ids = set(unique_card_ids)

    if authorized_ids != requested_ids:
        return None, unique_card_ids

    return cards, unique_card_ids


@app.route("/api/cards/batch/archive", methods=["POST"])
@require_permission('card.archive', require_board_context=False)
def batch_archive_cards():
    """Archive multiple cards in a single transaction.
    ---
    tags:
      - Cards
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - card_ids
          properties:
            card_ids:
              type: array
              items:
                type: integer
              description: List of card IDs to archive
              example: [1, 2, 3]
    responses:
      200:
        description: Cards archived successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Archived 3 cards"
            archived_count:
              type: integer
              example: 3
      400:
        description: Invalid request
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "card_ids is required"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        from models import Card

        data = request.get_json(silent=True) or {}
        card_ids = data.get("card_ids", [])

        if not card_ids:
            return jsonify({"success": False, "message": "card_ids is required"}), 400

        if not isinstance(card_ids, list):
            return jsonify({"success": False, "message": "card_ids must be an array"}), 400

        user_id = g.user.id
        scoped_cards, scoped_card_ids = _get_fully_authorized_batch_cards(db, user_id, card_ids)

        if scoped_cards is None:
            return jsonify({
                "success": False,
                "message": "One or more selected cards were not found or are no longer accessible. No cards were archived."
            }), 404

        # Archive all authorized cards only after the full request passes validation.
        archived_count = (
            get_user_scoped_query(db, Card, user_id)
            .filter(Card.id.in_(scoped_card_ids))
            .update({Card.archived: True}, synchronize_session=False)
        )
        
        db.commit()

        return jsonify({
            "success": True,
            "message": f"Archived {archived_count} cards",
            "archived_count": archived_count
        }), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error batch archiving cards: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/cards/batch/unarchive", methods=["POST"])
@require_permission('card.archive', require_board_context=False)
def batch_unarchive_cards():
    """Unarchive multiple cards in a single transaction.
    ---
    tags:
      - Cards
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - card_ids
          properties:
            card_ids:
              type: array
              items:
                type: integer
              description: List of card IDs to unarchive
              example: [1, 2, 3]
    responses:
      200:
        description: Cards unarchived successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Unarchived 3 cards"
            unarchived_count:
              type: integer
              example: 3
      400:
        description: Invalid request
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: "card_ids is required"
      500:
        description: Server error
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    db = SessionLocal()
    try:
        from models import Card

        data = request.get_json(silent=True) or {}
        card_ids = data.get("card_ids", [])

        if not card_ids:
            return jsonify({"success": False, "message": "card_ids is required"}), 400

        if not isinstance(card_ids, list):
            return jsonify({"success": False, "message": "card_ids must be an array"}), 400

        user_id = g.user.id
        cards_to_unarchive, _ = _get_fully_authorized_batch_cards(
            db,
            user_id,
            card_ids,
            order_by=(Card.column_id, Card.order)
        )

        if cards_to_unarchive is None:
            return jsonify({
                "success": False,
                "message": "One or more selected cards were not found or are no longer accessible. No cards were unarchived."
            }), 404

        if not cards_to_unarchive:
            return jsonify({"success": True, "message": "No cards found to unarchive", "unarchived_count": 0}), 200
        
        # Group cards by column for efficient order management
        cards_by_column = {}
        for card in cards_to_unarchive:
            if card.column_id not in cards_by_column:
                cards_by_column[card.column_id] = []
            cards_by_column[card.column_id].append(card)
        
        # Process each column separately to handle order conflicts
        for column_id, column_cards in cards_by_column.items():
            # Sort cards by their order
            column_cards.sort(key=lambda c: c.order)
            
            # For each card being unarchived, shift active cards to make room
            for card in column_cards:
                card_order = card.order
                
                # Increment order of all active cards at this position and above
                # This ensures the unarchived card can be inserted at its order position
                db.query(Card).filter(
                    Card.column_id == column_id,
                    Card.order >= card_order,
                    Card.id != card.id,
                    Card.archived.is_(False)
                ).update({Card.order: Card.order + 1}, synchronize_session=False)
                
                # Unarchive the card
                card.archived = False
                
                # Set updated_at timestamp
                from datetime import datetime
                card.updated_at = datetime.utcnow()
        
        db.commit()

        return jsonify({
            "success": True,
            "message": f"Unarchived {len(cards_to_unarchive)} cards",
            "unarchived_count": len(cards_to_unarchive)
        }), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error batch unarchiving cards: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>/archive-after", methods=["POST"])
@require_permission('card.archive')
def archive_cards_after_period(column_id):
    """Archive cards in a column that haven't been updated within a specified time period.
    ---
    tags:
      - Cards
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: ID of the column
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - quantity
            - period
          properties:
            quantity:
              type: integer
              description: Numeric value for the time period
              example: 7
            period:
              type: string
              description: Time unit (minutes, hours, days, weeks)
              enum: [minutes, hours, days, weeks]
              example: days
            dry_run:
              type: boolean
              description: If true, only return preview data without archiving
              example: true
    responses:
      200:
        description: Cards archived successfully or preview returned
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Archived 5 cards"
            archived_count:
              type: integer
              example: 5
            affected_count:
              type: integer
              description: Number of cards that would be archived (dry run only)
              example: 5
            most_recent_card:
              type: object
              description: Details of the most recent card to be archived (dry run only)
              properties:
                id:
                  type: integer
                title:
                  type: string
                updated_at:
                  type: string
                created_at:
                  type: string
      400:
        description: Invalid request
      404:
        description: Column not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Card
        from datetime import datetime, timedelta

        # Validate column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Request body is required"}), 400
        
        quantity = data.get("quantity")
        period = data.get("period")
        dry_run = data.get("dry_run", False)

        # Validate inputs
        if quantity is None:
            return jsonify({"success": False, "message": "quantity is required"}), 400
        
        if not isinstance(quantity, int) or quantity < 1:
            return jsonify({"success": False, "message": "quantity must be a positive integer"}), 400

        if not period:
            return jsonify({"success": False, "message": "period is required"}), 400
        if period not in ["minutes", "hours", "days", "weeks"]:
            return jsonify({"success": False, "message": "period must be one of: minutes, hours, days, weeks"}), 400

        # Calculate the cutoff datetime
        now = datetime.utcnow()
        if period == "minutes":
            cutoff = now - timedelta(minutes=quantity)
        elif period == "hours":
            cutoff = now - timedelta(hours=quantity)
        elif period == "days":
            cutoff = now - timedelta(days=quantity)
        elif period == "weeks":
            cutoff = now - timedelta(weeks=quantity)

        # Find cards that meet the criteria:
        # - In the specified column
        # - Not already archived
        # - updated_at (or created_at if updated_at is null) is older than cutoff
        query = db.query(Card).filter(
            Card.column_id == column_id,
            Card.archived == False
        )
        
        # Use COALESCE to handle null updated_at by falling back to created_at
        query = query.filter(
            func.coalesce(Card.updated_at, Card.created_at) < cutoff
        )

        if dry_run:
            # For dry run, get the count and the most recent card
            affected_cards = query.all()
            affected_count = len(affected_cards)
            
            if affected_count > 0:
                # Sort by updated_at (or created_at) descending to get most recent
                most_recent = max(
                    affected_cards,
                    key=lambda c: c.updated_at or c.created_at
                )
                
                return jsonify({
                    "success": True,
                    "affected_count": affected_count,
                    "most_recent_card": {
                        "id": most_recent.id,
                        "title": most_recent.title,
                        "updated_at": most_recent.updated_at.isoformat() if most_recent.updated_at else None,
                        "created_at": most_recent.created_at.isoformat() if most_recent.created_at else None
                    }
                }), 200
            else:
                return jsonify({
                    "success": True,
                    "affected_count": 0,
                    "most_recent_card": None
                }), 200
        else:
            # Actually archive the cards
            archived_count = query.update({Card.archived: True}, synchronize_session=False)
            db.commit()

            return jsonify({
                "success": True,
                "message": f"Archived {archived_count} cards",
                "archived_count": archived_count
            }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error archiving cards after period: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# Scheduled Cards API endpoints
@app.route("/api/columns/<int:column_id>/cards/scheduled", methods=["GET"])
@require_permission('card.view')
def get_scheduled_cards(column_id):
    """Get all scheduled template cards for a specific column (user must have access).
    ---
    tags:
      - Scheduled Cards
    parameters:
      - name: column_id
        in: path
        type: integer
        required: true
        description: The ID of the column
    responses:
      200:
        description: List of scheduled template cards for the column
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            cards:
              type: array
      401:
        description: Authentication required
      403:
        description: Permission denied
      500:
        description: Server error
    """
    try:
        db = SessionLocal()
        
        user_id = g.user.id
        # Get only scheduled template cards (scheduled=True)
        cards = (
            get_user_scoped_query(db, Card, user_id)
            .filter(Card.column_id == column_id)
            .filter(Card.scheduled.is_(True))
            .order_by(Card.order)
            .all()
        )
        
        cards_data = [
            {
                "id": c.id,
                "column_id": c.column_id,
                "title": c.title,
                "description": c.description,
                "order": c.order,
                "scheduled": c.scheduled,
                "schedule": c.schedule,
                "checklist_items": [
                    {
                        "id": item.id,
                        "card_id": item.card_id,
                        "name": item.name,
                        "checked": item.checked,
                        "order": item.order
                    }
                    for item in c.checklist_items
                ]
            }
            for c in cards
        ]
        
        db.close()
        return jsonify({"success": True, "cards": cards_data})
    except Exception as e:
        logger.error(f"Error getting scheduled cards: {str(e)}")
        return jsonify({"success": False, "message": "Failed to get scheduled cards"}), 500


@app.route("/api/schedules", methods=["POST"])
@require_permission('schedule.create')
def create_schedule():
    """Create a new schedule for a card.
    ---
    tags:
      - Scheduled Cards
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - card_id
            - run_every
            - unit
            - start_date
            - start_time
          properties:
            card_id:
              type: integer
            run_every:
              type: integer
            unit:
              type: string
              enum: [minute, hour, day, week, month, year]
            start_date:
              type: string
              format: date
            start_time:
              type: string
              format: time
            end_date:
              type: string
              format: date
            end_time:
              type: string
              format: time
            schedule_enabled:
              type: boolean
            allow_duplicates:
              type: boolean
            keep_source_card:
              type: boolean
    responses:
      201:
        description: Schedule created successfully
      400:
        description: Invalid input
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from datetime import datetime
        
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "message": "Request body is required"}), 400
        
        # Validate required fields
        required_fields = ['card_id', 'run_every', 'unit', 'start_datetime']
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "message": f"{field} is required"}), 400
        
        card_id = data['card_id']
        run_every = data['run_every']
        unit = data['unit']
        
        # Validate unit
        if unit not in ['minute', 'hour', 'day', 'week', 'month', 'year']:
            return jsonify({"success": False, "message": "Invalid unit"}), 400
        
        # Validate run_every
        if not isinstance(run_every, int) or run_every < 1:
            return jsonify({"success": False, "message": "run_every must be a positive integer"}), 400
        
        # Check if card exists
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404
        
        # Check if card already has a schedule reference
        if card.schedule is not None:
            return jsonify({"success": False, "message": "Card is already scheduled"}), 400
        
        # Parse datetimes
        try:
            # Handle ISO format with 'Z' timezone suffix
            # Convert to naive datetime (strip timezone) since we store as naive in DB
            start_datetime_str = data['start_datetime'].replace('Z', '+00:00')
            start_datetime = datetime.fromisoformat(start_datetime_str)
            if start_datetime.tzinfo is not None:
                start_datetime = start_datetime.replace(tzinfo=None)
            
            end_datetime = None
            if 'end_datetime' in data and data['end_datetime']:
                end_datetime_str = data['end_datetime'].replace('Z', '+00:00')
                end_datetime = datetime.fromisoformat(end_datetime_str)
                if end_datetime.tzinfo is not None:
                    end_datetime = end_datetime.replace(tzinfo=None)
        except (ValueError, TypeError) as e:
            return jsonify({"success": False, "message": f"Invalid datetime format: {str(e)}"}), 400
        
        # Capture board context for websocket broadcasts after commit.
        board_id = None
        column = db.query(BoardColumn).filter(BoardColumn.id == card.column_id).first()
        if column:
            board_id = column.board_id

        created_template_card = None
        updated_source_card = None
        deleted_source_card_id = None
        deleted_source_column_id = None

        # Check if card is already a template (scheduled=True)
        # If so, just create the schedule and link it - don't create a duplicate template
        if card.scheduled:
            # This card is already a template, just create and link the schedule
            schedule = ScheduledCard(
                card_id=card.id,
                run_every=run_every,
                unit=unit,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                schedule_enabled=data.get('schedule_enabled', True),
                allow_duplicates=data.get('allow_duplicates', False)
            )
            
            db.add(schedule)
            db.flush()
            
            # Update card's schedule reference
            card.schedule = schedule.id
            updated_source_card = card
        else:
            # Create a NEW card as the template (hidden from task views)
            template_card = Card(
                column_id=card.column_id,
                title=card.title,
                description=card.description,
                order=card.order,
                archived=False,
                scheduled=True,  # This marks it as a template (hidden from task views)
                schedule=None
            )
            db.add(template_card)
            db.flush()  # Get the new card ID
            
            # Copy checklist items to template
            for item in card.checklist_items:
                new_item = ChecklistItem(
                    card_id=template_card.id,
                    name=item.name,
                    checked=item.checked,
                    order=item.order
                )
                db.add(new_item)
            
            # Create schedule
            schedule = ScheduledCard(
                card_id=template_card.id,
                run_every=run_every,
                unit=unit,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                schedule_enabled=data.get('schedule_enabled', True),
                allow_duplicates=data.get('allow_duplicates', False)
            )
            
            db.add(schedule)
            db.flush()
            
            # Update template card's schedule reference
            template_card.schedule = schedule.id
            created_template_card = template_card
            
            # Handle keep_source_card parameter
            keep_source_card = data.get('keep_source_card', True)
            if keep_source_card:
                # Update ORIGINAL card's schedule reference (but keep scheduled=False so it stays visible)
                card.schedule = schedule.id
                updated_source_card = card
            else:
                # Delete the original card
                deleted_source_card_id = card.id
                deleted_source_column_id = card.column_id
                db.delete(card)
        
        db.commit()
        
        # Calculate next runs for response
        from schedule_utils import calculate_next_runs
        
        next_runs = calculate_next_runs(
            run_every=run_every,
            unit=unit,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            max_results=4
        )

        # Broadcast related card changes so other clients update without page refresh.
        if board_id is not None:
            if created_template_card is not None:
                broadcast_event('card_created', {
                    'board_id': board_id,
                    'column_id': created_template_card.column_id,
                    'card_id': created_template_card.id,
                    'card_data': {
                        'id': created_template_card.id,
                        'column_id': created_template_card.column_id,
                        'title': created_template_card.title,
                        'description': created_template_card.description,
                        'order': created_template_card.order,
                        'scheduled': created_template_card.scheduled,
                        'schedule': created_template_card.schedule,
                        'archived': created_template_card.archived,
                        'done': created_template_card.done,
                        'created_at': created_template_card.created_at.isoformat() if created_template_card.created_at else None,
                        'updated_at': created_template_card.updated_at.isoformat() if created_template_card.updated_at else None
                    }
                }, board_id)

            if updated_source_card is not None:
                broadcast_event('card_updated', {
                    'board_id': board_id,
                    'card_id': updated_source_card.id,
                    'updated_fields': {
                        'schedule': updated_source_card.schedule
                    }
                }, board_id)

            if deleted_source_card_id is not None:
                broadcast_event('card_deleted', {
                    'board_id': board_id,
                    'card_id': deleted_source_card_id,
                'column_id': deleted_source_column_id
                }, board_id)
        else:
            logger.warning(f"Skipping schedule-related broadcasts for schedule {schedule.id}: card {card_id} column has no board_id")
        
        return jsonify({
            "success": True,
            "message": "Schedule created successfully",
            "schedule": {
                "id": schedule.id,
                "card_id": schedule.card_id,
                "run_every": schedule.run_every,
                "unit": schedule.unit,
                "start_datetime": schedule.start_datetime.isoformat(),
                "end_datetime": schedule.end_datetime.isoformat() if schedule.end_datetime else None,
                "schedule_enabled": schedule.schedule_enabled,
                "allow_duplicates": schedule.allow_duplicates,
                "next_runs": next_runs
            }
        }), 201
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating schedule: {str(e)}")
        return jsonify({"success": False, "message": "Failed to create schedule"}), 500
    finally:
        db.close()


@app.route("/api/schedules/<int:schedule_id>", methods=["GET"])
@require_permission('schedule.view')
def get_schedule(schedule_id):
    """Get a schedule by ID with next run times.
    ---
    tags:
      - Scheduled Cards
    parameters:
      - name: schedule_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Schedule details
      404:
        description: Schedule not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        schedule = db.query(ScheduledCard).filter(ScheduledCard.id == schedule_id).first()
        
        if not schedule:
            return jsonify({"success": False, "message": "Schedule not found"}), 404
        
        # Calculate next runs
        from schedule_utils import calculate_next_runs
        
        next_runs = calculate_next_runs(
            run_every=schedule.run_every,
            unit=schedule.unit,
            start_datetime=schedule.start_datetime,
            end_datetime=schedule.end_datetime,
            max_results=4
        )
        
        return jsonify({
            "success": True,
            "schedule": {
                "id": schedule.id,
                "card_id": schedule.card_id,
                "run_every": schedule.run_every,
                "unit": schedule.unit,
                "start_datetime": schedule.start_datetime.isoformat(),
                "end_datetime": schedule.end_datetime.isoformat() if schedule.end_datetime else None,
                "schedule_enabled": schedule.schedule_enabled,
                "allow_duplicates": schedule.allow_duplicates,
                "next_runs": next_runs
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting schedule: {str(e)}")
        return jsonify({"success": False, "message": "Failed to get schedule"}), 500
    finally:
        db.close()


@app.route("/api/schedules/<int:schedule_id>", methods=["PUT"])
@require_permission('schedule.edit')
def update_schedule(schedule_id):
    """Update a schedule.
    ---
    tags:
      - Scheduled Cards
    parameters:
      - name: schedule_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
    responses:
      200:
        description: Schedule updated successfully
      404:
        description: Schedule not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from datetime import datetime
        
        schedule = db.query(ScheduledCard).filter(ScheduledCard.id == schedule_id).first()
        
        if not schedule:
            return jsonify({"success": False, "message": "Schedule not found"}), 404
        
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "message": "Request body is required"}), 400
        
        # Update fields if provided
        if 'run_every' in data:
            if not isinstance(data['run_every'], int) or data['run_every'] < 1:
                return jsonify({"success": False, "message": "run_every must be a positive integer"}), 400
            schedule.run_every = data['run_every']
        
        if 'unit' in data:
            if data['unit'] not in ['minute', 'hour', 'day', 'week', 'month', 'year']:
                return jsonify({"success": False, "message": "Invalid unit"}), 400
            schedule.unit = data['unit']
        
        if 'start_datetime' in data:
            try:
                # Handle ISO format with 'Z' timezone suffix
                # Convert to naive datetime (strip timezone) since we store as naive in DB
                start_datetime_str = data['start_datetime'].replace('Z', '+00:00')
                parsed_dt = datetime.fromisoformat(start_datetime_str)
                if parsed_dt.tzinfo is not None:
                    parsed_dt = parsed_dt.replace(tzinfo=None)
                schedule.start_datetime = parsed_dt
            except (ValueError, TypeError):
                return jsonify({"success": False, "message": "Invalid start_datetime format"}), 400
        
        if 'end_datetime' in data:
            if data['end_datetime']:
                try:
                    # Handle ISO format with 'Z' timezone suffix
                    # Convert to naive datetime (strip timezone) since we store as naive in DB
                    end_datetime_str = data['end_datetime'].replace('Z', '+00:00')
                    parsed_dt = datetime.fromisoformat(end_datetime_str)
                    if parsed_dt.tzinfo is not None:
                        parsed_dt = parsed_dt.replace(tzinfo=None)
                    schedule.end_datetime = parsed_dt
                except (ValueError, TypeError):
                    return jsonify({"success": False, "message": "Invalid end_datetime format"}), 400
            else:
                schedule.end_datetime = None
        
        if 'schedule_enabled' in data:
            schedule.schedule_enabled = bool(data['schedule_enabled'])
        
        if 'allow_duplicates' in data:
            schedule.allow_duplicates = bool(data['allow_duplicates'])
        
        db.commit()
        
        # Calculate next runs for response
        from schedule_utils import calculate_next_runs
        
        next_runs = calculate_next_runs(
            run_every=schedule.run_every,
            unit=schedule.unit,
            start_datetime=schedule.start_datetime,
            end_datetime=schedule.end_datetime,
            max_results=4
        )
        
        return jsonify({
            "success": True,
            "message": "Schedule updated successfully",
            "schedule": {
                "id": schedule.id,
                "card_id": schedule.card_id,
                "run_every": schedule.run_every,
                "unit": schedule.unit,
                "start_datetime": schedule.start_datetime.isoformat(),
                "end_datetime": schedule.end_datetime.isoformat() if schedule.end_datetime else None,
                "schedule_enabled": schedule.schedule_enabled,
                "allow_duplicates": schedule.allow_duplicates,
                "next_runs": next_runs
            }
        })
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating schedule: {str(e)}")
        return jsonify({"success": False, "message": "Failed to update schedule"}), 500
    finally:
        db.close()


@app.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
@require_permission('schedule.delete')
def delete_schedule(schedule_id):
    """Delete a schedule and update related cards.
    ---
    tags:
      - Scheduled Cards
    parameters:
      - name: schedule_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Schedule deleted successfully
      404:
        description: Schedule not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        schedule = db.query(ScheduledCard).filter(ScheduledCard.id == schedule_id).first()
        
        if not schedule:
            return jsonify({"success": False, "message": "Schedule not found"}), 404
        
        template_card_id = schedule.card_id

        # Gather board context and cards impacted so we can broadcast after commit.
        impacted_card_ids = []
        template_card_column_id = None
        board_id = None

        template_card = db.query(Card).filter(Card.id == template_card_id).first()
        if template_card:
            template_card_column_id = template_card.column_id
            template_column = db.query(BoardColumn).filter(BoardColumn.id == template_card.column_id).first()
            if template_column:
                board_id = template_column.board_id
        
        # Clear schedule reference from all cards that reference this schedule
        # (including the original source card and any spawned cards)
        created_cards = db.query(Card).filter(Card.schedule == schedule_id).all()
        impacted_card_ids = [c.id for c in created_cards if c.id != template_card_id]
        for card in created_cards:
            card.schedule = None
        
        # Delete the schedule FIRST (to avoid foreign key constraint)
        db.delete(schedule)
        db.flush()
        
        # Then delete the template card (the hidden duplicate)
        template_card = db.query(Card).filter(Card.id == template_card_id).first()
        if template_card:
            db.delete(template_card)
        
        db.commit()

        # Broadcast card changes so clients in normal/scheduled views stay in sync.
        if board_id is not None:
            for impacted_card_id in impacted_card_ids:
                broadcast_event('card_updated', {
                    'board_id': board_id,
                    'card_id': impacted_card_id,
                    'updated_fields': {
                        'schedule': None
                    }
                }, board_id)

            if template_card_column_id is not None:
                broadcast_event('card_deleted', {
                    'board_id': board_id,
                    'card_id': template_card_id,
                    'column_id': template_card_column_id
                }, board_id)
        else:
            logger.warning(f"Skipping schedule deletion broadcasts for schedule {schedule_id}: template card board_id not found")
        
        return jsonify({
            "success": True,
            "message": "Schedule deleted successfully"
        })
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting schedule: {str(e)}")
        return jsonify({"success": False, "message": "Failed to delete schedule"}), 500
    finally:
        db.close()


# Checklist Items API endpoints
@app.route("/api/cards/<int:card_id>/checklist-items", methods=["POST"])
@require_permission('card.update')
def create_checklist_item(card_id):
    """Create a new checklist item for a card.
    ---
    tags:
      - Checklist Items
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: "Review documentation"
              description: The name of the checklist item
            checked:
              type: boolean
              example: false
              description: Whether the item is checked
            order:
              type: integer
              example: 0
              description: The order position
    responses:
      201:
        description: Checklist item created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            checklist_item:
              type: object
              properties:
                id:
                  type: integer
                card_id:
                  type: integer
                name:
                  type: string
                checked:
                  type: boolean
                order:
                  type: integer
      400:
        description: Bad request - missing name
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data or "name" not in data:
            return create_error_response("Name is required", 400)

        from models import Card, ChecklistItem, BoardColumn

        # Verify card exists
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            return create_error_response("Card not found", 404)

        # Validate name
        name = data.get("name")
        if not isinstance(name, str):
            return create_error_response("Name must be a string", 400)

        # Sanitize and validate length
        name = sanitize_string(name)
        if not name:
            return create_error_response("Name cannot be empty", 400)

        is_valid, error = validate_string_length(name, 500, "Name")
        if not is_valid:
            return create_error_response(error, 400)

        # Validate checked if provided
        checked = data.get("checked", False)
        if not isinstance(checked, bool):
            return create_error_response("Checked must be a boolean", 400)

        # Validate order if provided
        if "order" in data:
            order = data["order"]
            is_valid, error = validate_integer(order, "Order", min_value=0)
            if not is_valid:
                return create_error_response(error, 400)
            
            # Increment order of existing items >= this order to make room
            existing_items = (
                db.query(ChecklistItem)
                .filter(ChecklistItem.card_id == card_id, ChecklistItem.order >= order)
                .all()
            )
            for item_to_update in existing_items:
                item_to_update.order += 1
        else:
            # Add at the end
            order = db.query(ChecklistItem).filter(ChecklistItem.card_id == card_id).count()

        # Create checklist item
        from datetime import datetime
        now = datetime.utcnow()
        checklist_item = ChecklistItem(
            card_id=card_id,
            name=name,
            checked=checked,
            order=order,
            updated_at=now
        )

        db.add(checklist_item)
        
        # Update parent card's updated_at timestamp
        card.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(checklist_item)

        # Get board_id for WebSocket broadcast
        column = db.query(BoardColumn).filter(BoardColumn.id == card.column_id).first()
        if column:
            broadcast_event('checklist_item_added', {
                'board_id': column.board_id,
                'card_id': card_id,
                'item_id': checklist_item.id,
                'item_data': {
                    'id': checklist_item.id,
                    'name': checklist_item.name,
                    'checked': checklist_item.checked,
                    'order': checklist_item.order,
                    'created_at': checklist_item.created_at.isoformat() if checklist_item.created_at else None,
                    'updated_at': checklist_item.updated_at.isoformat() if checklist_item.updated_at else None
                }
            }, column.board_id)

        return jsonify({
            "success": True,
            "checklist_item": {
                "id": checklist_item.id,
                "card_id": checklist_item.card_id,
                "name": checklist_item.name,
                "checked": checklist_item.checked,
                "order": checklist_item.order,
                "created_at": checklist_item.created_at.isoformat() if checklist_item.created_at else None,
                "updated_at": checklist_item.updated_at.isoformat() if checklist_item.updated_at else None
            }
        }), 201

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating checklist item for card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/checklist-items/<int:item_id>", methods=["PATCH"])
@require_permission('card.update')
def update_checklist_item(item_id):
    """Update a checklist item's name, checked status, and/or order.
    ---
    tags:
      - Checklist Items
    parameters:
      - name: item_id
        in: path
        type: integer
        required: true
        description: The ID of the checklist item to update
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: "Updated item name"
            checked:
              type: boolean
              example: true
            order:
              type: integer
              example: 1
    responses:
      200:
        description: Checklist item updated successfully
      400:
        description: Bad request - no data provided or validation error
      404:
        description: Checklist item not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from datetime import datetime
        
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data:
            return create_error_response("No data provided", 400)

        from models import ChecklistItem

        checklist_item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()

        if not checklist_item:
            return create_error_response("Checklist item not found", 404)
        
        # Track if user made content changes (not just reordering)
        content_changed = False

        # Update name if provided
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                return create_error_response("Name must be a string", 400)

            name = sanitize_string(name)
            if not name:
                return create_error_response("Name cannot be empty", 400)

            is_valid, error = validate_string_length(name, 500, "Name")
            if not is_valid:
                return create_error_response(error, 400)

            checklist_item.name = name
            content_changed = True

        # Update checked if provided
        if "checked" in data:
            checked = data["checked"]
            if not isinstance(checked, bool):
                return create_error_response("Checked must be a boolean", 400)
            checklist_item.checked = checked
            content_changed = True

        # Update order if provided
        if "order" in data:
            order = data["order"]
            is_valid, error = validate_integer(order, "Order", allow_none=False, min_value=0)
            if not is_valid:
                return create_error_response(error, 400)
            checklist_item.order = order
        
        # Set updated_at timestamp for checklist item only if content changed (not just reordering)
        if content_changed:
            checklist_item.updated_at = datetime.utcnow()
        
        # Update parent card's updated_at timestamp for any checklist change (including reordering)
        from models import Card
        card = db.query(Card).filter(Card.id == checklist_item.card_id).first()
        if card:
            card.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(checklist_item)

        result = {
            "id": checklist_item.id,
            "card_id": checklist_item.card_id,
            "name": checklist_item.name,
            "checked": checklist_item.checked,
            "order": checklist_item.order,
            "created_at": checklist_item.created_at.isoformat() if checklist_item.created_at else None,
            "updated_at": checklist_item.updated_at.isoformat() if checklist_item.updated_at else None
        }

        # Get board_id for broadcast
        from models import Card
        card = db.query(Card).filter(Card.id == checklist_item.card_id).first()
        if card and card.column:
            board_id = card.column.board_id
            broadcast_event('checklist_item_updated', {
                'board_id': board_id,
                'card_id': checklist_item.card_id,
                'item_id': checklist_item.id,
                'item_data': result
            }, board_id)

        return jsonify({
            "success": True,
            "checklist_item": result
        }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating checklist item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/checklist-items/<int:item_id>", methods=["DELETE"])
@require_permission('card.update')
def delete_checklist_item(item_id):
    """Delete a checklist item by ID.
    ---
    tags:
      - Checklist Items
    parameters:
      - name: item_id
        in: path
        type: integer
        required: true
        description: The ID of the checklist item to delete
    responses:
      200:
        description: Checklist item deleted successfully
      404:
        description: Checklist item not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import ChecklistItem, Card

        checklist_item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()

        if not checklist_item:
            return create_error_response("Checklist item not found", 404)
        
        # Get card_id before deleting
        card_id = checklist_item.card_id

        db.delete(checklist_item)
        
        # Update parent card's updated_at timestamp
        from datetime import datetime
        card = db.query(Card).filter(Card.id == card_id).first()
        if card:
            card.updated_at = datetime.utcnow()
        
        db.commit()

        return jsonify({"success": True, "message": "Checklist item deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting checklist item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/comments", methods=["GET"])
@require_permission('card.view')
def get_card_comments(card_id):
    """Get all comments for a card (user must have access).
    ---
    tags:
      - Comments
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
    responses:
      200:
        description: List of comments for the card
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            comments:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  card_id:
                    type: integer
                  comment:
                    type: string
                  order:
                    type: integer
                  created_at:
                    type: string
                    format: date-time
      401:
        description: Authentication required
      403:
        description: Permission denied
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Comment

        user_id = g.user.id
        comments = (
            get_user_scoped_query(db, Comment, user_id)
            .filter(Comment.card_id == card_id)
            .order_by(Comment.order.desc())  # Newest first
            .all()
        )

        return jsonify(
            {
                "success": True,
                "comments": [
                    {
                        "id": c.id,
                        "card_id": c.card_id,
                        "comment": c.comment,
                        "order": c.order,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in comments
                ],
            }
        )
    except Exception as e:
        logger.error(f"Error getting comments for card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/comments", methods=["POST"])
@require_permission('card.update')
def create_comment(card_id):
    """Create a new comment for a card.
    ---
    tags:
      - Comments
    parameters:
      - name: card_id
        in: path
        type: integer
        required: true
        description: The ID of the card
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - comment
          properties:
            comment:
              type: string
              example: "This is a journal entry for the card"
              description: The comment text
    responses:
      201:
        description: Comment created successfully
      400:
        description: Bad request - missing comment or validation error
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if not data or "comment" not in data:
            return create_error_response("Comment text is required", 400)

        # Verify card exists
        from models import Card, Comment

        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            return create_error_response("Card not found", 404)

        # Validate and sanitize comment
        comment_text = data.get("comment")
        if not isinstance(comment_text, str):
            return create_error_response("Comment must be a string", 400)

        comment_text = sanitize_string(comment_text)
        if not comment_text:
            return create_error_response("Comment cannot be empty", 400)

        is_valid, error = validate_string_length(
            comment_text, MAX_COMMENT_LENGTH, "Comment"
        )
        if not is_valid:
            return create_error_response(error, 400)

        # Get next order number (max + 1) with row-level locking to prevent race conditions
        # FOR UPDATE locks the row until the transaction commits, ensuring sequential order assignment
        max_order = (
            db.query(func.max(Comment.order))
            .filter(Comment.card_id == card_id)
            .with_for_update()
            .scalar()
        )
        next_order = (max_order + 1) if max_order is not None else 0

        # Create comment
        comment = Comment(
            card_id=card_id,
            comment=comment_text,
            order=next_order
        )
        db.add(comment)
        
        # Update parent card's updated_at timestamp
        from datetime import datetime
        card.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(comment)

        result = {
            "id": comment.id,
            "card_id": comment.card_id,
            "comment": comment.comment,
            "order": comment.order,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        }

        return create_success_response({"comment": result}, status_code=201)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating comment for card {card_id}: {str(e)}")
        return create_error_response("Failed to create comment", 500)
    finally:
        db.close()


@app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
@require_permission('card.update')
def delete_comment(comment_id):
    """Delete a comment by ID.
    
    Note: The order field is preserved in the database to maintain conversation history.
    Deleted comments leave gaps in the order sequence.
    ---
    tags:
      - Comments
    parameters:
      - name: comment_id
        in: path
        type: integer
        required: true
        description: The ID of the comment to delete
    responses:
      200:
        description: Comment deleted successfully
      404:
        description: Comment not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Comment, Card

        comment = db.query(Comment).filter(Comment.id == comment_id).first()

        if not comment:
            return create_error_response("Comment not found", 404)
        
        # Get card_id before deleting
        card_id = comment.card_id

        db.delete(comment)
        
        # Update parent card's updated_at timestamp
        from datetime import datetime
        card = db.query(Card).filter(Card.id == card_id).first()
        if card:
            card.updated_at = datetime.utcnow()
        
        db.commit()

        return jsonify({"success": True, "message": "Comment deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting comment {comment_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# Error handlers to ensure API endpoints return JSON
@app.errorhandler(401)
def unauthorized_error(error):
    """Handle 401 errors with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        return jsonify({
            "success": False, 
            "message": str(error.description) if hasattr(error, 'description') else "Authentication required"
        }), 401
    return error


@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        return jsonify({
            "success": False, 
            "message": str(error.description) if hasattr(error, 'description') else "Access forbidden"
        }), 403
    return error


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        # Check if error has a custom description (e.g., "Column not found")
        message = str(error.description) if hasattr(error, 'description') and error.description else "Endpoint not found"
        return jsonify({"success": False, "message": message}), 404
    # For non-API routes, return default Flask 404
    return error


@app.errorhandler(405)
def method_not_allowed_error(error):
    """Handle 405 errors with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": "Method not allowed"}), 405
    return error


@app.errorhandler(413)
def request_entity_too_large_error(error):
    """Handle 413 errors (Request Entity Too Large) with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        return jsonify({
            "success": False, 
            "message": f"File size exceeds maximum allowed size of {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)}MB"
        }), 413
    return error


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        logger.error(f"Internal server error: {str(error)}")
        return jsonify({"success": False, "message": "Internal server error"}), 500
    return error


# Initialize backup scheduler on app startup
def cleanup_stale_scheduler_locks():
    """Remove stale scheduler lock files on application startup.

    Active lock owners are preserved to avoid forcing duplicate schedulers.
    """
    from pathlib import Path
    import tempfile
    from scheduler_lock import is_scheduler_lock_stale

    temp_dir = Path(tempfile.gettempdir())
    lock_files = [
        (temp_dir / "aft_backup_scheduler.lock", "backup"),
        (temp_dir / "aft_card_scheduler.lock", "card"),
        (temp_dir / "aft_housekeeping_scheduler.lock", "housekeeping"),
    ]

    for lock_file, scheduler_type in lock_files:
        try:
            if not lock_file.exists():
                continue

            if is_scheduler_lock_stale(lock_file, scheduler_type, stale_after_seconds=300):
                lock_file.unlink()
                logger.info("Cleaned up stale scheduler lock file: %s", lock_file)
            else:
                logger.info("Keeping active scheduler lock file: %s", lock_file)
        except Exception as e:
            logger.warning(f"Failed to clean lock file {lock_file}: {e}")


def init_backup_scheduler():
    """Initialize and start the backup scheduler."""
    try:
        from backup_scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.start()
        logger.info("Backup scheduler initialization attempted")
    except Exception as e:
        logger.error(f"Failed to initialize backup scheduler: {str(e)}")

# Initialize card scheduler on app startup
def init_card_scheduler():
    """Initialize and start the card scheduler."""
    try:
        from card_scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.start()
        logger.info("Card scheduler initialization attempted")
    except Exception as e:
        logger.error(f"Failed to initialize card scheduler: {str(e)}")

# Initialize housekeeping scheduler on app startup
def init_housekeeping_scheduler():
    """Initialize and start the housekeeping scheduler."""
    try:
        from housekeeping_scheduler import start_housekeeping_scheduler
        start_housekeeping_scheduler(APP_VERSION)
        logger.info("Housekeeping scheduler initialization attempted")
    except Exception as e:
        logger.error(f"Failed to initialize housekeeping scheduler: {str(e)}")

# Start schedulers when module is loaded
# Use file lock to ensure only one worker initializes schedulers
# This prevents race conditions with Gunicorn multi-worker setup

skip_scheduler_init = os.getenv('AFT_SKIP_SCHEDULER_INIT', 'false').lower() == 'true'
if skip_scheduler_init:
    logger.info("Skipping scheduler initialization because AFT_SKIP_SCHEDULER_INIT=true")

# Only initialize schedulers in the first worker to start.
# The init lock must use process-aware stale detection to avoid false stale evictions.
init_lock_file = Path(tempfile.gettempdir()) / "aft_scheduler_init.lock"

from scheduler_lock import acquire_scheduler_lock

if skip_scheduler_init:
    acquired_init_lock, init_lock_details = False, {"reason": "skipped_by_env"}
    should_init = False
else:
    acquired_init_lock, init_lock_details = acquire_scheduler_lock(
        lock_file=init_lock_file,
        scheduler_type="scheduler_init",
        stale_after_seconds=300,
    )
    should_init = acquired_init_lock

if should_init:
    logger.info(
        "Worker PID %s: Acquired scheduler init lock (%s)",
        os.getpid(),
        init_lock_details,
    )
else:
    logger.info(
        "Worker PID %s: Init lock is held, skipping scheduler initialization (%s)",
        os.getpid(),
        init_lock_details,
    )

if should_init:
    try:
        logger.info(f"Worker PID {os.getpid()}: Initializing schedulers")
        
        # Clean up any stale lock files from previous container instances
        # This must happen AFTER acquiring init lock to prevent race conditions
        cleanup_stale_scheduler_locks()
        
        # Now start all schedulers
        init_backup_scheduler()
        init_card_scheduler()
        init_housekeeping_scheduler()  # Housekeeping also monitors other schedulers' health
        
        # Give schedulers a moment to create their lock files
        time.sleep(0.5)
    except Exception as e:
        logger.error(f"Error initializing schedulers: {e}")
else:
    logger.info(f"Worker PID {os.getpid()}: Waiting for first worker to initialize schedulers")
    # Wait for the first worker to finish initializing
    time.sleep(2)


# ============================================================================
# WebSocket Event Handlers for Real-Time Board Updates
# ============================================================================

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

@socketio.on('connect')
def handle_connect(auth=None):
    """Handle client connection to WebSocket.
    
    When REJECT_SOCKETIO_CONNECTIONS is True, immediately reject connections
    to simulate WebSocket failure for testing purposes.
    """
    if REJECT_SOCKETIO_CONNECTIONS:
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


@socketio.on('card_moved')
def broadcast_card_moved(data):
    """Broadcast when a card is moved to different position or column.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'from_column_id', 
              'to_column_id', 'from_index', 'to_index'
    """
    return _reject_client_originated_mutation('card_moved')


@socketio.on('card_updated')
def broadcast_card_updated(data):
    """Broadcast when a card's content or metadata is updated.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', and updated fields
              (title, description, color, etc.)
    """
    return _reject_client_originated_mutation('card_updated')


@socketio.on('card_created')
def broadcast_card_created(data):
    """Broadcast when a new card is created.
    
    Args:
        data: Dictionary containing 'board_id', 'column_id', 'card_id', 'card_data'
    """
    return _reject_client_originated_mutation('card_created')


@socketio.on('card_deleted')
def broadcast_card_deleted(data):
    """Broadcast when a card is deleted.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'column_id'
    """
    return _reject_client_originated_mutation('card_deleted')


@socketio.on('column_reordered')
def broadcast_column_reordered(data):
    """Broadcast when columns are reordered.
    
    Args:
        data: Dictionary containing 'board_id', 'column_order' (list of column IDs)
    """
    return _reject_client_originated_mutation('column_reordered')


@socketio.on('checklist_item_added')
def broadcast_checklist_item_added(data):
    """Broadcast when a checklist item is added to a card.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'item_id', 'item_data'
    """
    return _reject_client_originated_mutation('checklist_item_added')


@socketio.on('checklist_item_updated')
def broadcast_checklist_item_updated(data):
    """Broadcast when a checklist item is updated.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'item_id', 'updated_fields'
    """
    return _reject_client_originated_mutation('checklist_item_updated')


@socketio.on('checklist_item_deleted')
def broadcast_checklist_item_deleted(data):
    """Broadcast when a checklist item is deleted.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'item_id'
    """
    return _reject_client_originated_mutation('checklist_item_deleted')


# ============================================================================
# WebSocket Handlers for Theme Updates
# ============================================================================

@socketio.on('join_theme')
def on_join_theme():
    """Handle client joining the theme room to receive theme updates."""
    user = get_authenticated_socket_user()
    if not user:
        return {'success': False, 'message': 'Authentication required'}

    join_room('theme')
    logger.info(f"✓ Client {request.sid} (user_id={user.id}) joined theme room")

    # Send current theme to the new client
    session = SessionLocal()
    try:
        setting = session.query(Setting).filter(Setting.key == 'selected_theme').first()
        if setting:
            try:
                theme_id = int(setting.value)
                logger.info(f"📢 Sending current theme {theme_id} to client {request.sid}")
                # Emit current theme to this client only
                emit('theme_changed', {
                    'theme_id': theme_id
                })
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

    leave_room('theme')
    logger.info(f"Client {request.sid} (user_id={user.id}) left theme room")
    return {'success': True}


import re as _re

_HEX_COLOUR_RE = _re.compile(r'^#[0-9A-Fa-f]{6}$')


@app.route("/api/users/me/profile-colour", methods=["PUT"])
def update_profile_colour():
    """Update the current user's profile colour.
    ---
    tags:
      - Users
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - profile_colour
          properties:
            profile_colour:
              type: string
              description: RGB hex colour string e.g. '#E57373'
    responses:
      200:
        description: Profile colour updated successfully
      400:
        description: Invalid colour value
      500:
        description: Server error
    """
    try:
        data = request.get_json()
    except Exception:
        data = None
    if not g.get('user'):
      return create_error_response("Not authenticated", 401)
    if not data:
        return create_error_response("No data provided", 400)

    colour = data.get('profile_colour')
    if not colour or not isinstance(colour, str) or not _HEX_COLOUR_RE.match(colour):
        return create_error_response("profile_colour must be a valid RGB hex string e.g. '#A1B2C3'", 400)

    db = SessionLocal()
    try:
        from models import User
        user = db.query(User).filter(User.id == g.user.id).first()
        if not user:
            return create_error_response("User not found", 404)
        user.profile_colour = colour
        db.commit()
        return create_success_response({'profile_colour': colour})
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating profile colour for user {g.user.id}: {str(e)}")
        return create_error_response("Failed to update profile colour", 500)
    finally:
        db.close()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)


