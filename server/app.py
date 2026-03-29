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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "2026.3.2"

TEST_USER_EMAIL = "test-admin@localhost"
TEST_USER_USERNAME = "test-admin"
TEST_USER_DISPLAY_NAME = "Test Admin"

# Settings schema - defines allowed settings and their validation rules
WORKING_STYLE_KANBAN = "kanban"
WORKING_STYLE_AGILE = "agile"
WORKING_STYLE_LEGACY_BOARD_TASK_CATEGORY = "board_task_category"
WORKING_STYLE_ALLOWED_VALUES = [WORKING_STYLE_KANBAN, WORKING_STYLE_AGILE]

SETTINGS_SCHEMA = {
    "default_board": {
        "type": "integer",
        "nullable": True,
        "description": "ID of the board to load by default on application startup",
        "validate": lambda value: value is None
        or (isinstance(value, int) and not isinstance(value, bool) and value > 0),
    },
    "backup_enabled": {
        "type": "boolean",
        "nullable": False,
        "description": "Enable or disable automatic database backups",
        "validate": lambda value: isinstance(value, bool),
    },
    "backup_frequency_value": {
        "type": "integer",
        "nullable": False,
        "description": "Numeric value for backup frequency (1-99)",
        "validate": lambda value: isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 99,
    },
    "backup_frequency_unit": {
        "type": "string",
        "nullable": False,
        "description": "Unit for backup frequency (minutes, hours, daily)",
        "validate": lambda value: isinstance(value, str) and value in ["minutes", "hours", "daily"],
    },
    "backup_start_time": {
        "type": "string",
        "nullable": False,
        "description": "Time when daily backups should run (HH:MM format)",
        "validate": lambda value: isinstance(value, str) and _validate_time_format(value),
    },
    "backup_retention_count": {
        "type": "integer",
        "nullable": False,
        "description": "Number of backup files to retain (1-100)",
        "validate": lambda value: isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 100,
    },
    "backup_minimum_free_space_mb": {
        "type": "integer",
        "nullable": False,
        "description": "Minimum free disk space in MB required before creating a backup (1-10485760)",
        "validate": lambda value: isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 10485760,
    },
    "backup_last_run": {
        "type": "string",
        "nullable": True,
        "description": "ISO timestamp of the last backup run",
        "validate": lambda value: value is None or isinstance(value, str),
    },
    "housekeeping_enabled": {
        "type": "boolean",
        "nullable": False,
        "description": "Enable or disable housekeeping scheduler for version checks",
        "validate": lambda value: isinstance(value, bool),
    },
    "time_format": {
        "type": "string",
        "nullable": False,
        "description": "Time format preference: '12' for 12-hour or '24' for 24-hour",
        "validate": lambda value: isinstance(value, str) and value in ["12", "24"],
    },
    "working_style": {
        "type": "string",
        "nullable": False,
      "description": "Working style preference: 'kanban' for traditional kanban board or 'agile' for board-level done tracking",
      "validate": lambda value: isinstance(value, str) and value in WORKING_STYLE_ALLOWED_VALUES,
    },
}


def _validate_time_format(time_str):
    """Validate HH:MM time format."""
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            return False
        hours_str, minutes_str = parts[0], parts[1]
        
        # Minutes must be exactly 2 digits
        if len(minutes_str) != 2:
            return False
        
        hours, minutes = int(hours_str), int(minutes_str)
        return 0 <= hours <= 23 and 0 <= minutes <= 59
    except (ValueError, AttributeError):
        return False


def validate_setting(key, value):
    """Validate a setting key and value against the schema.

    Args:
        key: The setting key
        value: The setting value

    Returns:
        tuple: (is_valid, error_message)
    """
    if key not in SETTINGS_SCHEMA:
        return (
            False,
            f"Setting '{key}' is not allowed. Allowed settings: {', '.join(SETTINGS_SCHEMA.keys())}",
        )

    schema = SETTINGS_SCHEMA[key]

    # Check if null is allowed
    if value is None:
        if not schema.get("nullable", False):
            return False, f"Setting '{key}' cannot be null"
        return True, None

    # Validate using custom validator if provided
    if "validate" in schema:
        if not schema["validate"](value):
            return (
                False,
                f"Invalid value for setting '{key}'. {schema.get('description', '')}",
            )

    return True, None


def normalize_working_style(value):
    """Normalize legacy working style value names to current values."""
    if value == WORKING_STYLE_LEGACY_BOARD_TASK_CATEGORY:
        return WORKING_STYLE_AGILE
    return value


def parse_json_setting_value(raw_value):
    """Parse a JSON-encoded setting value with safe fallback."""
    try:
        return json.loads(raw_value) if raw_value is not None else None
    except (TypeError, json.JSONDecodeError):
        return raw_value


def get_user_default_working_style(db, user_id):
    """Resolve the user's default working style, normalized and validated."""
    setting = get_user_scoped_query(db, Setting, user_id).filter(Setting.key == 'working_style').first()
    if not setting:
        return WORKING_STYLE_KANBAN

    value = normalize_working_style(parse_json_setting_value(setting.value))
    if value not in WORKING_STYLE_ALLOWED_VALUES:
        return WORKING_STYLE_KANBAN
    return value


def get_board_working_style(db, board_id, fallback_user_id=None):
    """Resolve board working style from board-level setting only.
    
    Once a board is created with a working style, that setting is stored
    at the board level and should not change when the owner's user preference
    changes. This ensures boards maintain their style independently.
    
    Args:
        db: Database session
        board_id: Board ID to look up
        fallback_user_id: Unused; kept for API compatibility
    
    Returns:
        Working style string ('agile' or 'kanban')
    """
    board_setting = db.query(BoardSetting).filter(
        BoardSetting.board_id == board_id,
        BoardSetting.key == 'working_style'
    ).first()
    if board_setting:
        value = normalize_working_style(parse_json_setting_value(board_setting.value))
        if value in WORKING_STYLE_ALLOWED_VALUES:
            return value

    # If no board-level setting exists (should not happen for boards created
    # after migration), default to kanban to avoid unexpected behavior changes.
    return WORKING_STYLE_KANBAN


def validate_safe_url(url):
    """Validate that a URL uses a safe protocol.
    
    Allows:
    - Relative paths starting with /
    - http:// and https:// protocols
    
    Rejects:
    - javascript:, data:, vbscript:, file:, and other dangerous protocols
    - URL values containing characters that can break HTML attributes
    - URLs without proper structure
    
    Args:
        url: The URL string to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    url = url.strip()
    url_lower = url.lower()

    # Reject all dangerous protocols first for clearer error messages
    dangerous_protocols = ['javascript:', 'data:', 'vbscript:', 'file:', 'about:', 'blob:']
    for protocol in dangerous_protocols:
      if url_lower.startswith(protocol):
        return False, f"URL protocol '{protocol}' is not allowed for security reasons"

    # Defense in depth: reject characters that can break out of HTML attributes
    unsafe_attribute_chars = ['"', "'", '<', '>', '`']
    if any(char in url for char in unsafe_attribute_chars):
        return False, "URL contains unsafe characters"

    # Reject control characters that can cause parser confusion in HTML/headers
    if any(char in url for char in ['\r', '\n', '\t']):
        return False, "URL contains disallowed control characters"
    
    # Allow relative paths starting with /
    if url_lower.startswith('/'):
        return True, None
    
    # Allow http and https
    if url_lower.startswith('http://') or url_lower.startswith('https://'):
        return True, None

    # Reject anything that doesn't match allowed patterns
    return False, "URL must be a relative path starting with / or use http:// or https:// protocol"


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

# Configure maximum upload size (110MB)
app.config["MAX_CONTENT_LENGTH"] = 110 * 1024 * 1024

# Maximum backup file size for validation (MB) - actual content size limit
MAX_BACKUP_FILE_SIZE_MB = 100
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

# Register authentication blueprint
app.register_blueprint(auth_bp)
app.register_blueprint(user_mgmt_bp)
app.register_blueprint(role_mgmt_bp)

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


# Security validation functions for SQL backups
def validate_backup_file_security(file_path):
    """Validate backup file for dangerous SQL patterns.

    This function checks for SQL patterns that could be used for:
    - Privilege escalation (GRANT, CREATE USER)
    - File system access (INTO OUTFILE, LOAD DATA)
    - Stored procedures/functions (potential for code execution)
    - Cross-database operations (USE statements)
    - MySQL shell commands

    Args:
        file_path: Path to the SQL backup file

    Returns:
        tuple: (is_valid, error_message)
    """
    import re

    # Patterns that indicate potentially dangerous SQL
    # Note: Patterns must be specific to SQL commands, not matching text in data
    dangerous_patterns = [
        (r'\bGRANT\s+', 'GRANT statements (privilege manipulation)'),
        (r'\bCREATE\s+USER\b', 'CREATE USER statements'),
        (r'\bDROP\s+USER\b', 'DROP USER statements'),
        (r'\bALTER\s+USER\b', 'ALTER USER statements'),
        (r'\bINTO\s+OUTFILE\b', 'INTO OUTFILE (file system access)'),
        (r'\bLOAD\s+DATA\b', 'LOAD DATA (file system access)'),
        (r'\bCREATE\s+(PROCEDURE|FUNCTION)\b', 'Stored procedures/functions'),
        # USE must be at start of statement (after comments/whitespace) followed by db name and semicolon
        (r'^\s*USE\s+[`\']?\w+[`\']?\s*;', 'USE statements (cross-database operation)'),
        (r'\\!', 'MySQL shell commands'),
        (r'\bSELECT\s+.+?\bINTO\s+@', 'Variable assignment with SELECT'),
        (r'\bEXECUTE\s+', 'Dynamic SQL execution'),
        (r'\bPREPARE\s+', 'Prepared statement (potential SQL injection)'),
    ]

    try:
        line_num = 0
        in_multiline_comment = False
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_num += 1
                stripped = line.strip()
                
                # Handle multi-line comment state
                if in_multiline_comment:
                    # Check if multi-line comment ends on this line
                    if '*/' in line:
                        in_multiline_comment = False
                        # Check content after the closing */ if any
                        after_comment = line.split('*/', 1)[1].strip()
                        if not after_comment or after_comment.startswith('--'):
                            continue
                        # Continue to check the rest of the line
                        stripped = after_comment
                    else:
                        # Still inside multi-line comment, skip entire line
                        continue
                
                # Check if multi-line comment starts on this line
                if '/*' in stripped:
                    # Get content before the comment
                    before_comment = stripped.split('/*', 1)[0].strip()
                    
                    # Check if comment closes on same line
                    if '*/' in line:
                        # Extract any content after the closing */
                        after_comment = line.split('*/', 1)[1].strip()
                        # Only check non-comment parts
                        stripped = before_comment + ' ' + after_comment
                    else:
                        # Multi-line comment starts but doesn't end
                        in_multiline_comment = True
                        stripped = before_comment
                
                # Skip single-line comments and empty lines
                if not stripped or stripped.startswith('--'):
                    continue

                # Check each dangerous pattern
                for pattern, description in dangerous_patterns:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        return (
                            False,
                            f"Dangerous SQL pattern detected on line {line_num}: {description}"
                        )

        return True, None

    except Exception as e:
        return False, f"Error reading backup file: {str(e)}"


def validate_schema_integrity(file_path, expected_tables=None):
    """Validate that backup only contains expected database tables.

    This function ensures that:
    - Only expected tables are being created
    - No unauthorized schema modifications
    - Table structures match expected patterns

    Args:
        file_path: Path to the SQL backup file
        expected_tables: List of expected table names (optional)

    Returns:
        tuple: (is_valid, error_message)
    """
    import re

    # Default expected tables based on our models
    if expected_tables is None:
        expected_tables = [
            'boards',
            'columns',
            'cards',
            'card_secondary_assignees',
            'board_settings',
            'checklist_items',
            'comments',
            'settings',
            'notifications',
            'scheduled_cards',
            'themes',
            'roles',
            'users',
            'user_roles',
            'alembic_version'
        ]

    found_tables = set()
    unexpected_tables = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Look for CREATE TABLE statements
                # Pattern matches: CREATE TABLE [IF NOT EXISTS] [`tablename`] or "tablename" or tablename
                match = re.match(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"]?([^`"\s(]+)[`"]?', line, re.IGNORECASE)
                if match:
                    table_name = match.group(1)
                    found_tables.add(table_name)
                    if table_name not in expected_tables:
                        unexpected_tables.append(table_name)

        # Check for unexpected tables
        if unexpected_tables:
            return (
                False,
                f"Unexpected tables found in backup: {', '.join(unexpected_tables)}"
            )

        # Check if we found at least some core tables (boards, cards, columns)
        core_tables = {'boards', 'columns', 'cards'}
        if not core_tables.intersection(found_tables):
            return (
                False,
                "Backup does not appear to contain valid AFT database schema"
            )

        return True, None

    except Exception as e:
        return False, f"Error validating schema: {str(e)}"


def validate_backup_file_size(file_path, max_size_mb=100):
    """Validate backup file size to prevent DoS attacks.

    Args:
        file_path: Path to the SQL backup file
        max_size_mb: Maximum allowed file size in megabytes (default 100MB)

    Returns:
        tuple: (is_valid, error_message)
    """
    import os

    try:
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024

        if file_size > max_size_bytes:
            size_mb = file_size / (1024 * 1024)
            return (
                False,
                f"File size ({size_mb:.1f}MB) exceeds maximum allowed size ({max_size_mb}MB)"
            )

        return True, None

    except Exception as e:
        return False, f"Error checking file size: {str(e)}"


def validate_json_import_payload_size(payload_text, max_size_mb=25):
    """Validate JSON import payload size before parsing.

    Args:
        payload_text: Raw JSON text content
        max_size_mb: Maximum file size in MB

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        payload_size = len(payload_text.encode("utf-8"))
        max_size_bytes = max_size_mb * 1024 * 1024
        if payload_size > max_size_bytes:
            size_mb = payload_size / (1024 * 1024)
            return (
                False,
                f"Import file size ({size_mb:.1f}MB) exceeds maximum allowed size ({max_size_mb}MB)",
            )
        return True, None
    except Exception as e:
        return False, f"Error checking import size: {str(e)}"


def parse_iso_datetime(value):
    """Parse an ISO-8601 datetime string into a datetime object."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"

    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def serialize_datetime(value):
    """Serialize datetime to ISO string with timezone when available."""
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.isoformat()


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


def create_database_with_retry(db_host, db_root_password, db_name, max_retries=5, retry_delay_seconds=2):
    """Create database with retry for transient MySQL schema-directory race conditions.

    MySQL 9 can transiently report ERROR 3678 (schema directory already exists)
    immediately after a DROP DATABASE while filesystem cleanup is still settling.
    """
    create_db_cmd = [
        "mysql",
        f"-h{db_host}",
        "-uroot",
        f"-p{db_root_password}",
        "--skip-ssl",
        "-e",
        f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    ]

    last_stderr = ""
    for attempt in range(1, max_retries + 1):
        try:
            result = subprocess.run(create_db_cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise Exception("Timeout while creating database")

        if result.returncode == 0:
            logger.info(f"Database {db_name} created successfully")
            return

        stderr = (result.stderr or "").strip()
        last_stderr = stderr
        is_schema_directory_race = (
            "ERROR 3678" in stderr
            and "Schema directory" in stderr
            and "already exists" in stderr
        )

        if is_schema_directory_race and attempt < max_retries:
            logger.warning(
                f"Database create attempt {attempt}/{max_retries} hit MySQL schema directory race; "
                f"retrying in {retry_delay_seconds}s"
            )
            time.sleep(retry_delay_seconds)
            continue

        logger.error(f"Failed to create database: {stderr}")
        raise Exception(f"Failed to create database: {stderr}")

    logger.error(f"Failed to create database after {max_retries} attempts: {last_stderr}")
    raise Exception(f"Failed to create database after {max_retries} attempts: {last_stderr}")


@app.route("/api/version")
@require_authentication
def get_version():
    """Get application and database schema version.
    ---
    tags:
      - Health
    responses:
      200:
        description: Version information
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            app_version:
              type: string
              example: "1.0.0"
            db_version:
              type: string
              example: "003"
      500:
        description: Failed to get version
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
        # Get current Alembic revision from database
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        db_version = row[0] if row else "unknown"

        return jsonify(
            {"success": True, "app_version": APP_VERSION, "db_version": db_version}
        )
    except Exception as e:
        logger.error(f"Error getting version: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


def _find_known_test_user(db):
  return db.query(User).filter(
    User.email == TEST_USER_EMAIL,
    User.username == TEST_USER_USERNAME,
  ).first()


@app.route("/api/admin/test-user", methods=["GET"])
@require_any_permission('user.manage', 'user.role')
def get_test_user_status():
  """Get known test user status and test compatibility guidance.

  This endpoint does not create or elevate any user. It only reports whether the
  known test account is present and whether it matches the current test suite
  expectations.
  ---
  tags:
    - Administration
  responses:
    200:
      description: Known test user status
    403:
      description: Forbidden - requires user.manage or user.role
  """
  from permissions import has_permission

  db = SessionLocal()
  try:
    test_user = _find_known_test_user(db)
    user_permissions = get_user_permissions(g.user.id)
    can_remove = has_permission(user_permissions, 'user.manage')

    detected_user = None
    if test_user:
      detected_user = {
        "id": test_user.id,
        "email": test_user.email,
        "username": test_user.username,
        "display_name": test_user.display_name,
        "is_active": test_user.is_active,
        "is_approved": test_user.is_approved,
      }

    return jsonify({
      "success": True,
      "test_user_present": test_user is not None,
      "test_user_compatible": bool(
        test_user and test_user.is_active and test_user.is_approved
      ),
      "clean_database_compatible": True,
      "expected_user": {
        "email": TEST_USER_EMAIL,
        "username": TEST_USER_USERNAME,
        "display_name": TEST_USER_DISPLAY_NAME,
      },
      "detected_user": detected_user,
      "permissions": {
        "can_remove": can_remove,
      },
    })
  finally:
    db.close()


@app.route("/api/admin/test-user", methods=["DELETE"])
@require_permission('user.manage')
def remove_test_user():
  """Remove the known test user if it is present.

  This endpoint intentionally supports cleanup only. It does not create the
  account or assign the administrator role.
  ---
  tags:
    - Administration
  responses:
    200:
      description: Test user removed
    404:
      description: Known test user not found
    403:
      description: Forbidden - requires user.manage
    500:
      description: Server error
  """
  db = SessionLocal()
  try:
    test_user = _find_known_test_user(db)
    if not test_user:
      return jsonify({
        "success": False,
        "message": "Known test user was not found",
      }), 404

    deleted_current_user = test_user.id == g.user.id
    user_id = test_user.id
    username = test_user.username

    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    db.delete(test_user)
    db.commit()

    logger.info(
      f"Known test user deleted: {username} (ID: {user_id}) by user {g.user.id}"
    )

    return jsonify({
      "success": True,
      "action": "deleted",
      "deleted_current_user": deleted_current_user,
      "message": f"Known test user '{username}' has been deleted",
    })
  except Exception as e:
    db.rollback()
    logger.error(f"Error deleting known test user: {e}")
    return jsonify({
      "success": False,
      "message": f"Failed to delete known test user: {str(e)}",
    }), 500
  finally:
    db.close()


@app.route("/api/debug/permissions")
@require_authentication
def debug_user_permissions():
    """Debug endpoint to check user permissions for a board.
    
    Query Parameters:
        board_id (optional): Board ID to check board-specific permissions
    """
    board_id = request.args.get('board_id', type=int)
    
    db = SessionLocal()
    try:
        from utils import get_user_permissions
        
        # Get global permissions
        global_perms = get_user_permissions(g.user.id, board_id=None)
        
        # Get board-specific permissions if board_id provided
        board_perms = None
        if board_id:
            board_perms = get_user_permissions(g.user.id, board_id=board_id)
        
        # Get all user's role assignments
        role_assignments = db.query(UserRole, Role).join(
            Role, UserRole.role_id == Role.id
        ).filter(
            UserRole.user_id == g.user.id
        ).all()
        
        roles_data = []
        for user_role, role in role_assignments:
            roles_data.append({
                'role_name': role.name,
                'role_id': role.id,
                'board_id': user_role.board_id,
                'permissions': json.loads(role.permissions) if isinstance(role.permissions, str) else role.permissions
            })
        
        return jsonify({
            'success': True,
            'user_id': g.user.id,
            'username': g.user.username,
            'checked_board_id': board_id,
            'global_permissions': sorted(list(global_perms)),
            'board_specific_permissions': sorted(list(board_perms)) if board_perms else None,
            'all_role_assignments': roles_data
        })
        
    finally:
        db.close()


@app.route("/api/permissions/mapping")
@require_authentication
def get_permissions_mapping():
    """Get mapping of API endpoints to required permissions and user's current permissions.
    
    This endpoint returns:
    1. A mapping of all API endpoints to their required permissions
    2. The current user's permissions (global and board-specific if board_id provided)
    
    This enables the frontend to implement permission-based UI rendering,
    showing/hiding elements based on what the user can actually do.
    
    Query Parameters:
        board_id (optional): Board ID to include board-specific permissions
    ---
    tags:
      - Permissions
    responses:
      200:
        description: Permission mapping and user permissions
        schema:
          type: object
          properties:
            success:
              type: boolean
            endpoint_permissions:
              type: object
              description: Map of API endpoint patterns to required permissions
            user_permissions:
              type: array
              items:
                type: string
              description: Current user's permissions
    """
    board_id = request.args.get('board_id', type=int)
    db = SessionLocal()
    
    try:
        from utils import get_user_permissions

        # Get user's permissions (board-specific if board_id provided)
        user_perms = get_user_permissions(g.user.id, board_id=board_id)

        # Detect whether user has any board-scoped assignment. This is needed
        # for composite endpoint rules like GET /api/boards.
        has_board_assignment = db.query(UserRole.id).filter(
            UserRole.user_id == g.user.id,
            UserRole.board_id.isnot(None)
        ).first() is not None

        has_board_edit_assignment = False
        if has_board_assignment:
          board_role_assignments = (
            db.query(UserRole, Role)
            .join(Role, UserRole.role_id == Role.id)
            .filter(
              UserRole.user_id == g.user.id,
              UserRole.board_id.isnot(None),
            )
            .all()
          )
          for _, role in board_role_assignments:
            try:
              role_permissions = set(json.loads(role.permissions))
            except (TypeError, json.JSONDecodeError):
              continue
            if 'board.edit' in role_permissions:
              has_board_edit_assignment = True
              break

        # Comprehensive mapping of API endpoints to required permissions.
        endpoint_mapping = {
            # Board management
            'GET /api/boards': {
                'mode': 'composite',
                'any_permissions': ['board.view', 'board.create'],
                'allow_board_assignment': True,
                'description': 'View boards list (global board permission OR board assignment)'
            },
            'POST /api/boards': {'permission': 'board.create', 'description': 'Create new board'},
            'POST /api/boards/import': {
              'mode': 'composite',
              'any_permissions': ['board.create', 'board.edit'],
              'allow_board_edit_assignment': True,
              'description': 'Import board from AFT JSON export'
            },
            'DELETE /api/boards/:id': {'permission': 'board.delete', 'description': 'Delete board'},
            'PATCH /api/boards/:id': {'permission': 'board.edit', 'description': 'Edit board'},
            'GET /api/boards/:id/export': {'permission': 'board.view', 'description': 'Export board as JSON'},
            'GET /api/boards/:id/cards/scheduled': {'permission': 'schedule.view', 'description': 'View scheduled cards'},
            'GET /api/boards/:id/cards': {'permission': 'card.view', 'description': 'View board cards'},
            'GET /api/boards/:id/settings/working-style': {'permission': 'board.view', 'description': 'View board working style'},
            'PUT /api/boards/:id/settings/working-style': {'permission': 'board.edit', 'description': 'Update board working style'},

            # Column management
            'GET /api/boards/:id/columns': {'permission': 'board.view', 'description': 'View board columns'},
            'POST /api/boards/:id/columns': {'permission': 'column.create', 'description': 'Create column'},
            'DELETE /api/columns/:id': {'permission': 'column.delete', 'description': 'Delete column'},
            'PATCH /api/columns/:id': {'permission': 'column.update', 'description': 'Update column'},
            'GET /api/columns/:id/cards': {'permission': 'card.view', 'description': 'View column cards'},
            'GET /api/columns/:id/cards/scheduled': {'permission': 'schedule.view', 'description': 'View scheduled cards in column'},
            'POST /api/columns/:id/archive-after': {'permission': 'card.archive', 'description': 'Archive cards after position'},

            # Card management
            'POST /api/columns/:id/cards': {'permission': 'card.create', 'description': 'Create card'},
            'DELETE /api/columns/:id/cards': {'permission': 'card.delete', 'description': 'Delete all cards in column'},
            'POST /api/columns/:source_id/cards/move': {'permission': 'card.update', 'description': 'Move card between columns'},
            'GET /api/cards/:id': {'permission': 'card.view', 'description': 'View card details'},
            'PATCH /api/cards/:id': {'permission': 'card.update', 'description': 'Update card'},
            'DELETE /api/cards/:id': {'permission': 'card.delete', 'description': 'Delete card'},
            'PATCH /api/cards/:id/archive': {'permission': 'card.archive', 'description': 'Archive card'},
            'PATCH /api/cards/:id/unarchive': {'permission': 'card.archive', 'description': 'Unarchive card'},
            'GET /api/cards/:id/done': {'permission': 'card.view', 'description': 'Get card done status'},
            'PATCH /api/cards/:id/done': {'permission': 'card.update', 'description': 'Update card done status'},
            'GET /api/cards/:id/assignees': {'permission': 'card.view', 'description': 'Get card assignees'},
            'PUT /api/cards/:id/assignees': {'permission': 'card.update', 'description': 'Set card assignees'},
            'POST /api/cards/batch/archive': {'permission': 'card.archive', 'description': 'Batch archive cards'},
            'POST /api/cards/batch/unarchive': {'permission': 'card.archive', 'description': 'Batch unarchive cards'},

            # Schedule management
            'POST /api/schedules': {'permission': 'schedule.create', 'description': 'Create scheduled card'},
            'GET /api/schedules/:id': {'permission': 'schedule.view', 'description': 'View schedule details'},
            'PUT /api/schedules/:id': {'permission': 'schedule.edit', 'description': 'Update schedule'},
            'DELETE /api/schedules/:id': {'permission': 'schedule.delete', 'description': 'Delete schedule'},

            # Settings
            'GET /api/settings/schema': {'permission': 'setting.view', 'description': 'View settings schema'},
            'GET /api/settings/:key': {'permission': 'setting.view', 'description': 'View setting'},
            'PUT /api/settings/:key': {'permission': 'setting.edit', 'description': 'Update setting'},
            'GET /api/settings/backup/config': {'permission': 'setting.view', 'description': 'View backup config'},
            'PUT /api/settings/backup/config': {'permission': 'setting.edit', 'description': 'Update backup config'},
            'GET /api/settings/backup/status': {'permission': 'setting.view', 'description': 'View backup status'},
            'GET /api/settings/housekeeping/status': {'permission': 'setting.view', 'description': 'View housekeeping status'},
            'PUT /api/settings/housekeeping/config': {'permission': 'setting.edit', 'description': 'Update housekeeping config'},
            'GET /api/settings/card-scheduler/status': {'permission': 'setting.view', 'description': 'View scheduler status'},
            'PUT /api/settings/card-scheduler/config': {'permission': 'setting.edit', 'description': 'Update scheduler config'},

            # Database backups
            'GET /api/database/backup': {'permission': 'admin.database', 'description': 'Download database backup'},
            'POST /api/database/backup/manual': {'permission': 'admin.database', 'description': 'Create manual backup'},
            'POST /api/database/restore': {'permission': 'admin.database', 'description': 'Restore database'},
            'GET /api/database/backups/list': {'permission': 'admin.database', 'description': 'List all backups'},
            'POST /api/database/backups/restore/:filename': {'permission': 'admin.database', 'description': 'Restore specific backup'},
            'DELETE /api/database/backups/delete/:filename': {'permission': 'admin.database', 'description': 'Delete backup'},
            'POST /api/database/backups/delete-multiple': {'permission': 'admin.database', 'description': 'Delete multiple backups'},
            'DELETE /api/database': {'permission': 'admin.database', 'description': 'Reset database'},

            # Known test user guidance
            'GET /api/admin/test-user': {'permission': 'user.manage or user.role', 'description': 'View known test user status'},
            'DELETE /api/admin/test-user': {'permission': 'user.manage', 'description': 'Remove known test user'},

            # User management (from user_management.py blueprint)
            'GET /api/users': {'permission': 'user.manage', 'description': 'List all users'},
            'GET /api/users/:id': {'permission': 'user.manage', 'description': 'Get user details'},
            'PATCH /api/users/:id': {'permission': 'user.manage', 'description': 'Update user'},
            'DELETE /api/users/:id': {'permission': 'user.manage', 'description': 'Delete user'},
            'PATCH /api/users/:id/active': {'permission': 'user.manage', 'description': 'Toggle user active status'},
            'POST /api/users/:id/roles': {'permission': 'user.role', 'description': 'Assign user role'},
            'DELETE /api/users/:id/roles/:role_id': {'permission': 'user.role', 'description': 'Remove user role'},
            'PUT /api/users/me/profile-colour': {'mode': 'authenticated', 'description': 'Update current user avatar/profile colour'},

            # Role management (from role_management.py blueprint)
            'GET /api/roles': {'permission': 'role.manage', 'description': 'List all roles'},
            'POST /api/roles': {'permission': 'role.manage', 'description': 'Create role'},
            'GET /api/roles/:id': {'permission': 'role.manage', 'description': 'Get role details'},
            'PATCH /api/roles/:id': {'permission': 'role.manage', 'description': 'Update role'},
            'DELETE /api/roles/:id': {'permission': 'role.manage', 'description': 'Delete role'},
            'GET /api/roles/permission-model': {'mode': 'public', 'description': 'Get permission model (public)'},

            # Theme management
            'GET /api/themes': {'permission': 'theme.view', 'description': 'List themes'},
            'POST /api/themes': {'permission': 'theme.create', 'description': 'Create theme'},
            'GET /api/themes/:id': {'permission': 'theme.view', 'description': 'Get theme details'},
            'PUT /api/themes/:id': {'permission': 'theme.edit', 'description': 'Update theme'},
            'PUT /api/themes/:id/rename': {'permission': 'theme.edit', 'description': 'Rename theme'},
            'DELETE /api/themes/:id': {'permission': 'theme.delete', 'description': 'Delete theme'},

            # System/Monitoring
            'GET /api/stats': {'permission': 'board.view', 'description': 'View statistics'},
            'GET /api/scheduler/health': {'permission': 'setting.view', 'description': 'View scheduler health'},
            'GET /api/broadcast-status': {'permission': 'monitoring.system', 'description': 'View broadcast status'},
        }

        return jsonify({
            'success': True,
            'endpoint_permissions': endpoint_mapping,
            'user_permissions': sorted(list(user_perms)),
            'user_context': {
              'has_board_assignment': has_board_assignment,
              'has_board_edit_assignment': has_board_edit_assignment,
            },
            'board_id': board_id
        })
        
    except Exception as e:
        logger.error(f"Error getting permissions mapping: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to get permissions mapping: {str(e)}'
        }), 500
    finally:
      db.close()


@app.route("/api/broadcast-status")
@require_permission('monitoring.system')
def get_broadcast_status():
    """Get WebSocket broadcast error status for debugging.
    
    Returns recent broadcast failures tracked by the system. Useful for monitoring
    whether WebSocket events are being delivered to connected clients.
    ---
    tags:
      - Health
    responses:
      200:
        description: Broadcast status information
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            broadcast_failures:
              type: object
              description: Map of room names to recent errors
              example: {"board_1": {"card_updated": "Connection timeout"}}
            total_failure_rooms:
              type: integer
              example: 0
      500:
        description: Failed to get broadcast status
    """
    with broadcast_failures_lock:
        # Create a copy to avoid holding the lock during serialization
        failures_copy = dict(broadcast_failures)
        total_rooms = len(broadcast_failures)
    
    return jsonify({
        "success": True,
        "broadcast_failures": failures_copy,
        "total_failure_rooms": total_rooms
    })


@app.route("/api/scheduler/health")
@require_permission('setting.view')
def get_scheduler_health():
    """Get health status of all background schedulers.
    ---
    tags:
      - Health
    responses:
      200:
        description: Scheduler health information
        schema:
          type: object
          properties:
            backup_scheduler:
              type: object
            card_scheduler:
              type: object
            housekeeping_scheduler:
              type: object
    """
    import json
    from datetime import datetime
    from pathlib import Path
    
    health = {}
    
    # Backup scheduler
    try:
        from backup_scheduler import get_scheduler
        scheduler = get_scheduler()
        
        # Get status which includes latest_backup_date from filesystem (consistent with /api/settings/backup/status)
        status = scheduler.get_status()
        last_backup_iso = status.get('latest_backup_date')  # Already in ISO format from get_status()
        
        # In multi-worker setup, check lock file for true health status
        lock_file_exists = scheduler.lock_file.exists()
        is_healthy = False
        lock_age = None
        
        if lock_file_exists:
            try:
                lock_data = json.loads(scheduler.lock_file.read_text())
                last_heartbeat = datetime.fromisoformat(lock_data['last_heartbeat'])
                lock_age = (datetime.now() - last_heartbeat).total_seconds()
                # Consider healthy if heartbeat is less than 2.5 minutes old (2.5x the 60s loop interval)
                is_healthy = lock_age < 150
                
                health['backup_scheduler'] = {
                    'running': is_healthy,
                    'thread_alive': is_healthy,  # Use lock file freshness instead of thread.is_alive() for multi-worker
                    'last_backup': last_backup_iso,
                    'lock_file_exists': True,
                    'lock_file_age_seconds': lock_age,
                    'lock_pid': lock_data.get('pid'),
                    'lock_container': lock_data.get('container_id'),
                    'permission_error': scheduler.permission_error
                }
            except Exception as e:
                health['backup_scheduler'] = {
                    'running': False,
                    'thread_alive': False,
                    'lock_file_exists': True,
                    'lock_file_error': str(e),
                    'permission_error': scheduler.permission_error
                }
        else:
            health['backup_scheduler'] = {
                'running': False,
                'thread_alive': False,
                'last_backup': last_backup_iso,
                'lock_file_exists': False,
                'permission_error': scheduler.permission_error
            }
    except Exception as e:
        health['backup_scheduler'] = {'error': str(e)}
    
    # Card scheduler
    try:
        from card_scheduler import get_scheduler as get_card_scheduler
        scheduler = get_card_scheduler()
        
        # In multi-worker setup, check lock file for true health status
        lock_file_exists = scheduler.lock_file.exists()
        is_healthy = False
        lock_age = None
        
        if lock_file_exists:
            try:
                lock_data = json.loads(scheduler.lock_file.read_text())
                last_heartbeat = datetime.fromisoformat(lock_data['last_heartbeat'])
                lock_age = (datetime.now() - last_heartbeat).total_seconds()
                # Consider healthy if heartbeat is less than 2.5 minutes old (2.5x the 60s loop interval for consistency)
                is_healthy = lock_age < 150
                
                health['card_scheduler'] = {
                    'running': is_healthy,
                    'thread_alive': is_healthy,  # Use lock file freshness instead of thread.is_alive() for multi-worker
                    'lock_file_exists': True,
                    'lock_file_age_seconds': lock_age,
                    'lock_pid': lock_data.get('pid'),
                    'lock_container': lock_data.get('container_id')
                }
            except Exception as e:
                health['card_scheduler'] = {
                    'running': False,
                    'thread_alive': False,
                    'lock_file_exists': True,
                    'lock_file_error': str(e)
                }
        else:
            health['card_scheduler'] = {
                'running': False,
                'thread_alive': False,
                'lock_file_exists': False
            }
    except Exception as e:
        health['card_scheduler'] = {'error': str(e)}
    
    # Housekeeping scheduler
    try:
        from housekeeping_scheduler import get_housekeeping_scheduler
        scheduler = get_housekeeping_scheduler(APP_VERSION)
        
        # In multi-worker setup, check lock file for true health status
        lock_file_exists = scheduler.lock_file.exists()
        is_healthy = False
        lock_age = None
        
        if lock_file_exists:
            try:
                lock_data = json.loads(scheduler.lock_file.read_text())
                last_heartbeat = datetime.fromisoformat(lock_data['last_heartbeat'])
                lock_age = (datetime.now() - last_heartbeat).total_seconds()
                # Consider healthy if heartbeat is less than 2.5 minutes old (2.5x the 60s loop interval)
                is_healthy = lock_age < 150
                
                health['housekeeping_scheduler'] = {
                    'running': is_healthy,
                    'thread_alive': is_healthy,  # Use lock file freshness instead of thread.is_alive() for multi-worker
                    'lock_file_exists': True,
                    'lock_file_age_seconds': lock_age,
                    'lock_pid': lock_data.get('pid'),
                    'lock_container': lock_data.get('container_id')
                }
            except Exception as e:
                health['housekeeping_scheduler'] = {
                    'running': False,
                    'thread_alive': False,
                    'lock_file_exists': True,
                    'lock_file_error': str(e)
                }
        else:
            health['housekeeping_scheduler'] = {
                'running': False,
                'thread_alive': False,
                'lock_file_exists': False
            }
    except Exception as e:
        health['housekeeping_scheduler'] = {'error': str(e)}
    
    return jsonify(health), 200


def _healthcheck_allowed_source_ips():
    """Return the configured set of source IPs allowed for readiness checks."""
    allowed_raw = os.getenv('HEALTHCHECK_ALLOWED_SOURCE_IP', '127.0.0.1')
    allowed_ips = {ip.strip() for ip in allowed_raw.split(',') if ip.strip()}
    if '127.0.0.1' in allowed_ips:
        allowed_ips.add('::1')
    return allowed_ips


def _is_internal_readiness_request_authorized():
    """Validate token + source IP for the internal readiness endpoint."""
    expected_token = os.getenv('HEALTHCHECK_TOKEN', '').strip()
    provided_token = request.headers.get('X-Health-Token', '').strip()

    if not expected_token:
        logger.warning('HEALTHCHECK_TOKEN is not set; readiness request denied')
        return False

    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        return False

    remote_addr = (request.remote_addr or '').strip()
    return remote_addr in _healthcheck_allowed_source_ips()


@app.route("/api/health/live")
def health_live():
    """Public liveness endpoint with minimal disclosure.
    ---
    tags:
      - Health
    responses:
      200:
        description: API process is reachable
        schema:
          type: object
          properties:
            ok:
              type: boolean
              example: true
    """
    return jsonify({"ok": True}), 200


@app.route("/api/health/ready")
def health_ready():
    """Internal readiness endpoint for compose health checks.
    ---
    tags:
      - Health
    responses:
      200:
        description: API and database are ready
      404:
        description: Request is not authorized for readiness checks
      503:
        description: API is up but dependencies are not ready
    """
    if not _is_internal_readiness_request_authorized():
        return jsonify({"ok": False}), 404

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.warning(f"Readiness check failed: {e}")
        return jsonify({"ok": False}), 503
    finally:
        db.close()


@app.route("/api/test")
@require_authentication
def test_db():
    """Test database connectivity (legacy endpoint).
    ---
    tags:
      - Health
    responses:
      200:
        description: Database connection successful
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Connected to database"
      500:
        description: Database connection failed
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
        db.execute(text("SELECT 1"))
        return jsonify({"success": True, "message": "Connected to database"})
    except Exception as e:
        logger.error(f"Legacy health check failed: {e}")
        return jsonify({"success": False, "message": "Database not reachable"}), 500
    finally:
        db.close()


@app.route("/api/stats")
@require_permission('board.view')
def get_stats():
    """Get database statistics for the current user.
    ---
    tags:
      - Health
    responses:
      200:
        description: Database statistics
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            boards_count:
              type: integer
              example: 5
            columns_count:
              type: integer
              example: 15
            cards_count:
              type: integer
              example: 42
            cards_archived_count:
              type: integer
              example: 8
            checklist_items_total:
              type: integer
              example: 28
            checklist_items_checked:
              type: integer
              example: 15
            checklist_items_unchecked:
              type: integer
              example: 13
      401:
        description: Authentication required
      403:
        description: Permission denied
      500:
        description: Failed to get statistics
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
        from models import ChecklistItem
        user_id = g.user.id
        
        boards_count = get_user_scoped_query(db, Board, user_id).count()
        columns_count = get_user_scoped_query(db, BoardColumn, user_id).count()
        cards_count = get_user_scoped_query(db, Card, user_id).count()
        cards_archived_count = get_user_scoped_query(db, Card, user_id).filter(Card.archived.is_(True)).count()
        
        # Get checklist item counts (scoped to user's cards)
        checklist_items_total = get_user_scoped_query(db, ChecklistItem, user_id).count()
        checklist_items_checked = get_user_scoped_query(db, ChecklistItem, user_id).filter(ChecklistItem.checked.is_(True)).count()
        checklist_items_unchecked = get_user_scoped_query(db, ChecklistItem, user_id).filter(ChecklistItem.checked.is_(False)).count()

        return jsonify(
            {
                "success": True,
                "boards_count": boards_count,
                "columns_count": columns_count,
                "cards_count": cards_count,
                "cards_archived_count": cards_archived_count,
                "checklist_items_total": checklist_items_total,
                "checklist_items_checked": checklist_items_checked,
                "checklist_items_unchecked": checklist_items_unchecked,
            }
        )
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/database/backup", methods=["GET"])
@require_permission('admin.database')
def backup_database():
    """Create a database backup with version information.
    ---
    tags:
      - Database
    responses:
      200:
        description: Database backup file
        content:
          application/sql:
            schema:
              type: string
              format: binary
      500:
        description: Failed to create backup
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    import subprocess
    import os
    import tempfile
    from datetime import datetime
    from flask import send_file

    try:
        # Get current Alembic version
        db = SessionLocal()
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        db_version = row[0] if row else "unknown"
        db.close()

        # Get database credentials from environment
        db_user = os.environ.get("MYSQL_USER")
        db_password = os.environ.get("MYSQL_PASSWORD")
        db_name = os.environ.get("MYSQL_DATABASE")
        db_host = "db"

        # Create temporary file for backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"aft_backup_{timestamp}.sql"
        temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".sql")
        temp_path = temp_file.name
        temp_file.close()

        # Write version comment to file
        with open(temp_path, "w") as f:
            f.write(f"-- AFT Database Backup\n")
            f.write(f"-- App Version: {APP_VERSION}\n")
            f.write(f"-- Alembic Version: {db_version}\n")
            f.write(f"-- Backup Date: {datetime.now().isoformat()}\n")
            f.write(f"--\n\n")

        # Run mysqldump and append to file
        mysqldump_cmd = [
            "mysqldump",
            "-h",
            db_host,
            "-u",
            db_user,
            f"-p{db_password}",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--skip-ssl",
            db_name,
        ]

        with open(temp_path, "a") as f:
            result = subprocess.run(
                mysqldump_cmd, stdout=f, stderr=subprocess.PIPE, text=True
            )

        if result.returncode != 0:
            os.unlink(temp_path)
            raise Exception(f"mysqldump failed: {result.stderr}")

        logger.info(f"Database backup created successfully: {backup_filename}")

        # Send file and delete after sending
        return send_file(
            temp_path,
            mimetype="application/sql",
            as_attachment=True,
            download_name=backup_filename,
        )

    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        create_notification_internal(
            subject="⚠️ Database Backup Failed",
            message=f"Failed to create database backup: {str(e)}\n\nCheck server logs for details."
        )
        return jsonify({"success": False, "message": "Failed to create database backup"}), 500


@app.route("/api/database/backup/manual", methods=["POST"])
@require_permission('admin.database')
def create_manual_backup():
    """Create a manual backup and save to backups folder.
    ---
    tags:
      - Database
    responses:
      200:
        description: Backup created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
            filename:
              type: string
      500:
        description: Failed to create backup
    """
    import subprocess
    import os
    from pathlib import Path
    from datetime import datetime

    try:
        # Get current Alembic version
        db = SessionLocal()
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        db_version = row[0] if row else "unknown"
        db.close()

        # Get database credentials from environment
        db_user = os.environ.get("MYSQL_USER")
        db_password = os.environ.get("MYSQL_PASSWORD")
        db_name = os.environ.get("MYSQL_DATABASE")
        db_host = "db"

        # Create backup in the backups folder
        backup_dir = Path("/app/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"aft_backup_{timestamp}.sql"
        backup_path = backup_dir / backup_filename

        # Write version comment to file
        with open(backup_path, "w") as f:
            f.write(f"-- AFT Database Backup\n")
            f.write(f"-- App Version: {APP_VERSION}\n")
            f.write(f"-- Alembic Version: {db_version}\n")
            f.write(f"-- Backup Date: {datetime.now().isoformat()}\n")
            f.write(f"--\n\n")

        # Run mysqldump and append to file
        mysqldump_cmd = [
            "mysqldump",
            "-h",
            db_host,
            "-u",
            db_user,
            f"-p{db_password}",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--skip-ssl",
            db_name,
        ]

        with open(backup_path, "a") as f:
            result = subprocess.run(
                mysqldump_cmd, stdout=f, stderr=subprocess.PIPE, text=True
            )

        if result.returncode != 0:
            backup_path.unlink()
            raise Exception(f"mysqldump failed: {result.stderr}")

        logger.info(f"Manual database backup created successfully: {backup_filename}")

        return jsonify({
            "success": True,
            "message": f"Backup created successfully: {backup_filename}",
            "filename": backup_filename
        })

    except Exception as e:
        logger.error(f"Error creating manual backup: {str(e)}")
        create_notification_internal(
            subject="⚠️ Manual Backup Failed",
            message=f"Failed to create manual backup: {str(e)}\n\nCheck database connection and mysqldump availability in server logs."
        )
        return jsonify({"success": False, "message": "Failed to create manual backup"}), 500


@app.route("/api/database/restore", methods=["POST"])
@require_permission('admin.database')
def restore_database():
    """Restore database from backup file with version checking.
    ---
    tags:
      - Database
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: SQL backup file to restore
    responses:
      200:
        description: Database restored successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
      400:
        description: Invalid file or version mismatch
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
      500:
        description: Failed to restore database
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
    """
    import subprocess
    import os
    import tempfile
    import re

    logger.info(f"=== Starting manual restore from uploaded file ===")
    try:
        # Check if file was uploaded
        logger.info(f"Step 1: Validating file upload")
        if "file" not in request.files:
            logger.error("No file uploaded in request")
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            logger.error("Empty filename provided")
            return jsonify({"success": False, "message": "No file selected"}), 400

        logger.info(f"Uploaded file: {file.filename}")
        logger.info(f"Step 2: Saving uploaded file to temporary location")
        # Save uploaded file to temporary location
        temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".sql")
        temp_path = temp_file.name
        temp_file.close()
        file.save(temp_path)
        logger.info(f"File saved to: {temp_path}")

        logger.info(f"Step 3: Validating file size and security")
        # File size validation: Check for reasonable size
        is_valid_size, size_error = validate_backup_file_size(temp_path, max_size_mb=MAX_BACKUP_FILE_SIZE_MB)
        if not is_valid_size:
            os.unlink(temp_path)
            logger.warning(f"File size validation failed: {size_error}")
            return jsonify({
                "success": False,
                "message": f"File size validation failed: {size_error}"
            }), 400

        # Security validation: Check for dangerous SQL patterns
        is_secure, security_error = validate_backup_file_security(temp_path)
        if not is_secure:
            os.unlink(temp_path)
            logger.warning(f"Security validation failed: {security_error}")
            return jsonify({
                "success": False,
                "message": f"Security validation failed: {security_error}"
            }), 400

        # Schema validation: Ensure only expected tables
        is_valid_schema, schema_error = validate_schema_integrity(temp_path)
        if not is_valid_schema:
            os.unlink(temp_path)
            logger.warning(f"Schema validation failed: {schema_error}")
            return jsonify({
                "success": False,
                "message": f"Schema validation failed: {schema_error}"
            }), 400

        logger.info(f"Step 4: Reading backup file to extract version information")
        # Read first few lines to get version info
        backup_version = None
        with open(temp_path, "r") as f:
            for line in f:
                if line.startswith("-- Alembic Version:"):
                    backup_version = line.split(":", 1)[1].strip()
                    break
                # Stop reading after comments section
                if not line.startswith("--") and line.strip():
                    break

        if not backup_version:
            os.unlink(temp_path)
            logger.error("No Alembic version found in backup file")
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Invalid backup file: No Alembic version found",
                    }
                ),
                400,
            )

        logger.info(f"Backup version: {backup_version}")
        logger.info(f"Step 5: Checking current database version")
        # Get current Alembic version (what we would create on restore)
        db = SessionLocal()
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        current_version = row[0] if row else "unknown"
        db.close()
        logger.info(f"Current version: {current_version}")

        # Check version compatibility
        # Note: Alembic versions are revision IDs, not semantic versions
        # We can only reliably check equality; different versions require migration
        if backup_version != current_version:
            logger.warning(
                f"Backup version ({backup_version}) differs from current version ({current_version}). "
                "Will attempt to restore and upgrade."
            )

        # Get database credentials
        db_user = os.environ.get("MYSQL_USER")
        db_password = os.environ.get("MYSQL_PASSWORD")
        db_name = os.environ.get("MYSQL_DATABASE")
        db_host = "db"

        logger.info(f"Step 6: Dropping all existing tables")
        
        # Close any existing database sessions in this request context to avoid connection issues
        logger.info(f"Step 6.0: Closing request database sessions before killing connections")
        from flask import g
        request_db = g.pop('db', None)
        if request_db:
            try:
                request_db.close()
                logger.info(f"Closed request database session")
            except Exception as e:
                logger.warning(f"Error closing request database session: {e}")
        
        # Dispose of SQLAlchemy engine connection pool so it creates fresh connections
        try:
            engine.dispose()
            logger.info(f"Disposed SQLAlchemy engine connection pool")
        except Exception as e:
            logger.warning(f"Error disposing engine pool: {e}")
        
        # Kill all other database connections first to release locks
        logger.info(f"Step 6.0.1: Killing all other database connections to release locks")
        get_pids_cmd = [
            "mysql",
            f"-h{db_host}",
            f"-u{db_user}",
            f"-p{db_password}",
            "--skip-ssl",
            "-N",
            "-e",
            f"SELECT id FROM INFORMATION_SCHEMA.PROCESSLIST WHERE db = '{db_name}' AND id != CONNECTION_ID();"
        ]
        
        try:
            result = subprocess.run(get_pids_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                pids = [pid.strip() for pid in result.stdout.strip().split('\n') if pid.strip()]
                logger.info(f"Found {len(pids)} active connections to kill: {pids}")
                
                for pid in pids:
                    logger.info(f"Killing connection: {pid}")
                    kill_cmd = [
                        "mysql",
                        f"-h{db_host}",
                        f"-u{db_user}",
                        f"-p{db_password}",
                        "--skip-ssl",
                        "-e",
                        f"KILL {pid};"
                    ]
                    try:
                        subprocess.run(kill_cmd, capture_output=True, text=True, timeout=5)
                        logger.info(f"Killed connection: {pid}")
                    except Exception as e:
                        logger.warning(f"Could not kill connection {pid}: {e}")
                
                logger.info(f"Step 6.0.2: Waiting 2 seconds for connections to terminate")
                import time
                time.sleep(2)
            else:
                logger.info(f"No active connections to kill")
        except Exception as e:
            logger.warning(f"Error killing connections: {e}")
        
        # Use DROP DATABASE / CREATE DATABASE for a completely clean slate
        logger.info(f"Step 6.1: Using DROP DATABASE / CREATE DATABASE for clean slate")
        
        # Get root credentials for database operations
        db_root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
        
        # Drop and recreate the database - this is the most reliable way to clear everything
        logger.info(f"Step 6.1.1: Dropping database {db_name}")
        drop_db_cmd = [
            "mysql",
            f"-h{db_host}",
            "-uroot",
            f"-p{db_root_password}",
            "--skip-ssl",
            "-e",
            f"DROP DATABASE IF EXISTS `{db_name}`;"
        ]
        
        try:
            result = subprocess.run(drop_db_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to drop database: {result.stderr}")
                raise Exception(f"Failed to drop database: {result.stderr}")
            logger.info(f"Database {db_name} dropped successfully")
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout while dropping database")
            raise Exception("Timeout while dropping database")
        
        # Recreate the database
        logger.info(f"Step 6.1.2: Creating fresh database {db_name}")
        create_database_with_retry(db_host, db_root_password, db_name)
        
        # Grant permissions to the application user
        logger.info(f"Step 6.1.3: Granting permissions to user {db_user}")
        grant_cmd = [
            "mysql",
            f"-h{db_host}",
            "-uroot",
            f"-p{db_root_password}",
            "--skip-ssl",
            "-e",
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'%'; FLUSH PRIVILEGES;"
        ]
        
        try:
            result = subprocess.run(grant_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.warning(f"Failed to grant permissions: {result.stderr}")
                # Don't fail here, permissions might already exist
            else:
                logger.info(f"Permissions granted successfully")
        except Exception as e:
            logger.warning(f"Error granting permissions: {e}")
        
        logger.info(f"Step 6.2: Database completely reset and ready for restore")
        
        # Give a moment for database to be ready
        logger.info(f"Step 6.3: Waiting 2 seconds for database to be ready")
        import time
        time.sleep(2)

        logger.info(f"Step 7: Restoring data from backup file using mysql command")
        logger.info(f"Restoring database from backup (version {backup_version})")

        # Restore from SQL file
        mysql_cmd = [
            "mysql",
            "-h",
            db_host,
            "-u",
            db_user,
            f"-p{db_password}",
            "--skip-ssl",
            db_name,
        ]

        with open(temp_path, "r") as f:
            result = subprocess.run(
                mysql_cmd, stdin=f, stderr=subprocess.PIPE, text=True
            )

        os.unlink(temp_path)

        if result.returncode != 0:
            logger.error(f"MySQL restore failed with return code {result.returncode}: {result.stderr}")
            raise Exception(f"MySQL restore failed: {result.stderr}")

        logger.info(f"MySQL restore completed successfully")
        
        # Verify database connection is working after restore
        logger.info(f"Step 7.1: Verifying database connection after restore")
        max_retries = 10
        retry_delay = 2
        connected = False
        
        for attempt in range(1, max_retries + 1):
            try:
                test_db = SessionLocal()
                test_db.execute(text("SELECT 1"))
                test_db.close()
                logger.info(f"Database connection verified on attempt {attempt}")
                connected = True
                break
            except Exception as e:
                logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(retry_delay)
                else:
                    raise Exception(f"Failed to verify database connection after {max_retries} attempts")
        
        logger.info(f"Step 7.5: Cleaning up scheduler lock files after restore")
        # Clean up stale scheduler lock files after successful restore
        # This forces the scheduler threads to create fresh lock files with current timestamps
        # Otherwise the system info page will show stale heartbeat ages from before the restore
        logger.info("Cleaning up scheduler lock files after restore")
        temp_dir = Path(tempfile.gettempdir())
        lock_files_to_clean = [
            temp_dir / "aft_backup_scheduler.lock",
            temp_dir / "aft_card_scheduler.lock",
            temp_dir / "aft_housekeeping_scheduler.lock",
        ]
        
        for lock_file in lock_files_to_clean:
            try:
                if lock_file.exists():
                    lock_file.unlink()
                    logger.info(f"Cleaned up scheduler lock file after restore: {lock_file}")
            except Exception as e:
                logger.warning(f"Failed to clean lock file {lock_file}: {e}")

        # If backup version differs from current, run migrations to upgrade
        if backup_version != current_version:
            logger.info(f"Step 8: Running Alembic migrations from {backup_version} to {current_version}")
            logger.info(
                f"Migrating database from {backup_version} to {current_version}"
            )
            # Use stdout=None, stderr=None to avoid subprocess deadlock from filled pipes
            # Output will flow to parent process logs
            upgrade_result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd="/app",
                stdout=None,
                stderr=None,
                text=True,
            )

            if upgrade_result.returncode != 0:
                logger.error(f"Alembic upgrade failed with return code {upgrade_result.returncode}")
                raise Exception(f"Alembic upgrade failed - check server logs for details")

            logger.info(f"Alembic migrations completed successfully")
            logger.info(f"=== Manual restore completed successfully (with migration) ===")
            return jsonify(
                {
                    "success": True,
                    "message": f"Database restored and upgraded from version {backup_version} to {current_version}",
                }
            )
        else:
            logger.info(f"Step 8: No migration needed, versions match")
            logger.info(f"=== Manual restore completed successfully (no migration) ===")
            logger.info("Database restored successfully")
            return jsonify(
                {"success": True, "message": "Database restored successfully"}
            )

    except Exception as e:
        import traceback
        logger.error(f"=== Manual restore FAILED ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database/backups/list", methods=["GET"])
@require_permission('admin.database')
def list_backups():
    """List all available backup files (both automatic and manual).
    ---
    tags:
      - Database
    responses:
      200:
        description: List of available backups
        schema:
          type: object
          properties:
            success:
              type: boolean
            backups:
              type: array
              items:
                type: object
                properties:
                  filename:
                    type: string
                  created:
                    type: string
                  size:
                    type: integer
                  is_manual:
                    type: boolean
                    description: True if manually created, False if automatic
      500:
        description: Failed to list backups
    """
    try:
        from pathlib import Path
        from datetime import datetime
        
        backup_dir = Path("/app/backups")
        
        if not backup_dir.exists():
            return jsonify({"success": True, "backups": []})
        
        backups = []
        for backup_file in backup_dir.glob("*.sql"):
            stat = backup_file.stat()
            is_manual = not backup_file.name.startswith("auto_backup_")
            backups.append({
                "filename": backup_file.name,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size": stat.st_size,
                "is_manual": is_manual,
                "mtime": stat.st_mtime  # For sorting
            })
        
        # Sort by modification time, newest first
        backups.sort(key=lambda x: x["mtime"], reverse=True)
        
        # Remove mtime from response
        for backup in backups:
            del backup["mtime"]
        
        return jsonify({"success": True, "backups": backups})
        
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database/backups/restore/<filename>", methods=["POST"])
@require_permission('admin.database')
def restore_backup_from_file(filename):
    """Restore from a specific backup file (automatic or manual).
    ---
    tags:
      - Database
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: The backup filename to restore from
    responses:
      200:
        description: Database restored successfully
      400:
        description: Invalid backup file
      404:
        description: Backup file not found
      500:
        description: Failed to restore backup
    """
    logger.info(f"=== Starting restore from backup: {filename} ===")
    try:
        from pathlib import Path
        import re
        import os
        import subprocess
        
        # Validate filename to prevent path traversal
        # Allow both auto_backup and manual backup filenames (aft_backup)
        logger.info(f"Step 1: Validating filename format")
        if not re.match(r'^(auto_backup_|aft_backup_)\d{8}_\d{6}\.sql$', filename):
            logger.error(f"Invalid filename format: {filename}")
            return jsonify({"success": False, "message": "Invalid backup filename"}), 400
        
        logger.info(f"Step 2: Checking backup file exists and is not a symlink")
        backup_dir = Path("/app/backups")
        backup_path = backup_dir / filename
        
        # Check for symlinks before resolving (security: prevent symlink-based path traversal)
        if backup_path.is_symlink():
            logger.warning(f"Attempted to restore from symlink: {filename}")
            return jsonify({"success": False, "message": "Symlinks are not allowed"}), 400
        
        # Resolve path and ensure it's strictly within backup_dir (no traversal)
        resolved_backup_path = backup_path.resolve()
        resolved_backup_dir = backup_dir.resolve()
        try:
            resolved_backup_path.relative_to(resolved_backup_dir)
        except ValueError:
            logger.warning(f"Path traversal attempt detected: {filename}")
            return jsonify({"success": False, "message": "Invalid backup file path"}), 400
        
        if not resolved_backup_path.exists():
            logger.error(f"Backup file not found: {resolved_backup_path}")
            return jsonify({"success": False, "message": "Backup file not found"}), 404
        
        logger.info(f"Step 3: Validating file size and security")
        # File size validation
        is_valid_size, size_error = validate_backup_file_size(resolved_backup_path, max_size_mb=MAX_BACKUP_FILE_SIZE_MB)
        if not is_valid_size:
            logger.warning(f"File size validation failed for {filename}: {size_error}")
            return jsonify({
                "success": False,
                "message": f"File size validation failed: {size_error}"
            }), 400

        # Security validation: Check for dangerous SQL patterns
        is_secure, security_error = validate_backup_file_security(resolved_backup_path)
        if not is_secure:
            logger.warning(f"Security validation failed for {filename}: {security_error}")
            return jsonify({
                "success": False,
                "message": f"Security validation failed: {security_error}"
            }), 400

        # Schema validation: Ensure only expected tables
        is_valid_schema, schema_error = validate_schema_integrity(resolved_backup_path)
        if not is_valid_schema:
            logger.warning(f"Schema validation failed for {filename}: {schema_error}")
            return jsonify({
                "success": False,
                "message": f"Schema validation failed: {schema_error}"
            }), 400

        logger.info(f"Step 4: Reading backup file to extract version information")
        # Read and validate the backup file
        with open(resolved_backup_path, 'r') as f:
            content = f.read(10000)  # Read first 10KB to find version
            
        # Extract Alembic version from backup
        version_match = re.search(r"-- Alembic Version: (\S+)", content)
        if not version_match:
            return jsonify({
                "success": False,
                "message": "Invalid backup file: No Alembic version found"
            }), 400
            
        backup_version = version_match.group(1)
        logger.info(f"Backup version: {backup_version}")
        
        # Get current Alembic version
        logger.info(f"Step 5: Checking current database version")
        db = SessionLocal()
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        current_version = row[0] if row else "unknown"
        db.close()
        logger.info(f"Current version: {current_version}")
        
        # Check version compatibility
        # Note: Alembic versions are revision IDs, not semantic versions
        # We can only reliably check equality; different versions require migration
        if backup_version != current_version:
            logger.warning(
                f"Backup version ({backup_version}) differs from current version ({current_version}). "
                "Will attempt to restore and upgrade."
            )
        
        # Get database credentials
        db_user = os.environ.get("MYSQL_USER")
        db_password = os.environ.get("MYSQL_PASSWORD")
        db_name = os.environ.get("MYSQL_DATABASE")
        db_host = "db"
        
        logger.info(f"Step 6: Dropping all existing tables")
        
        # Close any existing database sessions in this request context to avoid connection issues
        logger.info(f"Step 6.0: Closing request database sessions before killing connections")
        from flask import g
        request_db = g.pop('db', None)
        if request_db:
            try:
                request_db.close()
                logger.info(f"Closed request database session")
            except Exception as e:
                logger.warning(f"Error closing request database session: {e}")
        
        # Dispose of SQLAlchemy engine connection pool so it creates fresh connections
        try:
            engine.dispose()
            logger.info(f"Disposed SQLAlchemy engine connection pool")
        except Exception as e:
            logger.warning(f"Error disposing engine pool: {e}")
        
        # Kill all other database connections first to release locks
        logger.info(f"Step 6.0.1: Killing all other database connections to release locks")
        get_pids_cmd = [
            "mysql",
            f"-h{db_host}",
            f"-u{db_user}",
            f"-p{db_password}",
            "--skip-ssl",
            "-N",
            "-e",
            f"SELECT id FROM INFORMATION_SCHEMA.PROCESSLIST WHERE db = '{db_name}' AND id != CONNECTION_ID();"
        ]
        
        try:
            result = subprocess.run(get_pids_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                pids = [pid.strip() for pid in result.stdout.strip().split('\n') if pid.strip()]
                logger.info(f"Found {len(pids)} active connections to kill: {pids}")
                
                for pid in pids:
                    logger.info(f"Killing connection: {pid}")
                    kill_cmd = [
                        "mysql",
                        f"-h{db_host}",
                        f"-u{db_user}",
                        f"-p{db_password}",
                        "--skip-ssl",
                        "-e",
                        f"KILL {pid};"
                    ]
                    try:
                        subprocess.run(kill_cmd, capture_output=True, text=True, timeout=5)
                        logger.info(f"Killed connection: {pid}")
                    except Exception as e:
                        logger.warning(f"Could not kill connection {pid}: {e}")
                
                logger.info(f"Step 6.0.2: Waiting 2 seconds for connections to terminate")
                time.sleep(2)
            else:
                logger.info(f"No active connections to kill")
        except Exception as e:
            logger.warning(f"Error killing connections: {e}")
        
        # Use DROP DATABASE / CREATE DATABASE for a completely clean slate
        logger.info(f"Step 6.1: Using DROP DATABASE / CREATE DATABASE for clean slate")
        
        # Get root credentials for database operations
        db_root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
        
        # Drop and recreate the database - this is the most reliable way to clear everything
        logger.info(f"Step 6.1.1: Dropping database {db_name}")
        drop_db_cmd = [
            "mysql",
            f"-h{db_host}",
            "-uroot",
            f"-p{db_root_password}",
            "--skip-ssl",
            "-e",
            f"DROP DATABASE IF EXISTS `{db_name}`;"
        ]
        
        try:
            result = subprocess.run(drop_db_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to drop database: {result.stderr}")
                raise Exception(f"Failed to drop database: {result.stderr}")
            logger.info(f"Database {db_name} dropped successfully")
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout while dropping database")
            raise Exception("Timeout while dropping database")
        
        # Recreate the database
        logger.info(f"Step 6.1.2: Creating fresh database {db_name}")
        create_database_with_retry(db_host, db_root_password, db_name)
        
        # Grant permissions to the application user
        logger.info(f"Step 6.1.3: Granting permissions to user {db_user}")
        grant_cmd = [
            "mysql",
            f"-h{db_host}",
            "-uroot",
            f"-p{db_root_password}",
            "--skip-ssl",
            "-e",
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'%'; FLUSH PRIVILEGES;"
        ]
        
        try:
            result = subprocess.run(grant_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.warning(f"Failed to grant permissions: {result.stderr}")
                # Don't fail here, permissions might already exist
            else:
                logger.info(f"Permissions granted successfully")
        except Exception as e:
            logger.warning(f"Error granting permissions: {e}")
        
        logger.info(f"Step 6.2: Database completely reset and ready for restore")
        
        # Give a moment for database to be ready
        logger.info(f"Step 6.3: Waiting 2 seconds for database to be ready")
        time.sleep(2)
        
        logger.info(f"Step 7: Restoring data from backup file using mysql command")
        # Restore from backup file
        mysql_cmd = [
            "mysql",
            f"-h{db_host}",
            f"-u{db_user}",
            f"-p{db_password}",
            "--skip-ssl",
            db_name,
        ]
        
        with open(resolved_backup_path, 'r') as f:
            result = subprocess.run(
                mysql_cmd, stdin=f, stderr=subprocess.PIPE, text=True
            )
        
        if result.returncode != 0:
            logger.error(f"MySQL restore failed with return code {result.returncode}: {result.stderr}")
            raise Exception(f"MySQL restore failed: {result.stderr}")
        
        logger.info(f"MySQL restore completed successfully")
        
        # Clean up stale scheduler lock files after successful restore
        # This forces the scheduler threads to create fresh lock files with current timestamps
        logger.info(f"Step 7.5: Cleaning up scheduler lock files after restore")
        import tempfile
        temp_dir = Path(tempfile.gettempdir())
        lock_files_to_clean = [
            temp_dir / "aft_backup_scheduler.lock",
            temp_dir / "aft_card_scheduler.lock",
            temp_dir / "aft_housekeeping_scheduler.lock",
        ]
        
        for lock_file in lock_files_to_clean:
            try:
                if lock_file.exists():
                    lock_file.unlink()
                    logger.info(f"Cleaned up scheduler lock file: {lock_file}")
            except Exception as e:
                logger.warning(f"Failed to clean lock file {lock_file}: {e}")
        
        # Run migrations if needed
        if backup_version != current_version:
            logger.info(f"Step 8: Running Alembic migrations from {backup_version} to {current_version}")
            # Use stdout=None, stderr=None to avoid subprocess deadlock from filled pipes
            # Output will flow to parent process logs
            upgrade_result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd="/app",
                stdout=None,
                stderr=None,
                text=True,
            )
            
            if upgrade_result.returncode != 0:
                logger.error(f"Alembic upgrade failed with return code {upgrade_result.returncode}")
                raise Exception(f"Alembic upgrade failed - check server logs for details")
            
            logger.info(f"Alembic migrations completed successfully")
            
            logger.info(f"=== Restore completed successfully: {filename} (with migration) ===")
            return jsonify({
                "success": True,
                "message": f"Database restored from {filename} and upgraded to version {current_version}"
            })
        else:
            logger.info(f"Step 8: No migration needed, versions match")
            logger.info(f"=== Restore completed successfully: {filename} (no migration) ===")
            return jsonify({
                "success": True,
                "message": f"Database restored successfully from {filename}"
            })
            
    except Exception as e:
        import traceback
        logger.error(f"=== Restore FAILED for {filename} ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database/backups/delete/<filename>", methods=["DELETE"])
@require_permission('admin.database')
def delete_backup(filename):
    """Delete a specific backup file.
    ---
    tags:
      - Database
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: The backup filename to delete
    responses:
      200:
        description: Backup deleted successfully
      400:
        description: Invalid backup file
      404:
        description: Backup file not found
      500:
        description: Failed to delete backup
    """
    try:
        from pathlib import Path
        import re
        
        # Validate filename to prevent path traversal
        # Allow both auto_backup and manual backup filenames (aft_backup)
        if not re.match(r'^(auto_backup_|aft_backup_)\d{8}_\d{6}\.sql$', filename):
            return jsonify({"success": False, "message": "Invalid backup filename"}), 400
        
        backup_dir = Path("/app/backups")
        backup_path = backup_dir / filename
        
        if not backup_path.exists():
            return jsonify({"success": False, "message": "Backup file not found"}), 404
        
        # Delete the backup file
        backup_path.unlink()
        
        logger.info(f"Backup deleted successfully: {filename}")
        return jsonify({
            "success": True,
            "message": f"Backup {filename} deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"Error deleting backup: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database/backups/delete-multiple", methods=["POST"])
@require_permission('admin.database')
def delete_multiple_backups():
    """Delete multiple backup files.
    ---
    tags:
      - Database
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - filenames
          properties:
            filenames:
              type: array
              items:
                type: string
              description: Array of backup filenames to delete
    responses:
      200:
        description: Backups deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            deleted:
              type: integer
              description: Number of backups successfully deleted
            failed:
              type: integer
              description: Number of backups that failed to delete
            errors:
              type: array
              items:
                type: string
              description: List of error messages for failed deletions
      400:
        description: Invalid request
      500:
        description: Failed to delete backups
    """
    try:
        from pathlib import Path
        import re
        
        data = request.get_json()
        
        if not data or 'filenames' not in data:
            return jsonify({"success": False, "message": "Missing filenames array"}), 400
        
        filenames = data['filenames']
        
        if not isinstance(filenames, list):
            return jsonify({"success": False, "message": "filenames must be an array"}), 400
        
        if len(filenames) == 0:
            return jsonify({"success": False, "message": "filenames array is empty"}), 400
        
        if len(filenames) > 100:
            return jsonify({"success": False, "message": "Cannot delete more than 100 backups at once"}), 400
        
        backup_dir = Path("/app/backups")
        deleted_count = 0
        failed_count = 0
        errors = []
        
        for filename in filenames:
            try:
                # Validate filename to prevent path traversal
                if not re.match(r'^(auto_backup_|aft_backup_)\d{8}_\d{6}\.sql$', filename):
                    errors.append(f"{filename}: Invalid backup filename")
                    failed_count += 1
                    continue
                
                backup_path = backup_dir / filename
                
                if not backup_path.exists():
                    errors.append(f"{filename}: File not found")
                    failed_count += 1
                    continue
                
                # Delete the backup file
                backup_path.unlink()
                deleted_count += 1
                
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
                failed_count += 1
        
        logger.info(f"Bulk delete completed: {deleted_count} deleted, {failed_count} failed")
        
        return jsonify({
            "success": True,
            "deleted": deleted_count,
            "failed": failed_count,
            "errors": errors,
            "message": f"Deleted {deleted_count} backup(s)" + (f", {failed_count} failed" if failed_count > 0 else "")
        })
        
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database", methods=["DELETE"])
@require_permission('admin.database')
def delete_database():
    """Delete all data from the database.
    ---
    tags:
      - Database
    responses:
      200:
        description: Database deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Database deleted successfully"
      500:
        description: Failed to delete database
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
        # Get database credentials
        db_user = os.environ.get("MYSQL_USER")
        db_password = os.environ.get("MYSQL_PASSWORD")
        db_name = os.environ.get("MYSQL_DATABASE")
        db_root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
        db_host = "db"

        if not db_user or not db_password or not db_name:
            raise Exception("Missing required database environment variables")

        lock_path = "/tmp/aft_db_reset.lock"
        lock_fd = None

        def acquire_reset_lock(timeout_seconds=60):
          start = time.time()
          while True:
            try:
              return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
              # Recover from stale lock files left by terminated processes.
              try:
                if time.time() - os.path.getmtime(lock_path) > 600:
                  os.remove(lock_path)
                  continue
              except FileNotFoundError:
                continue

              if time.time() - start > timeout_seconds:
                return None
              time.sleep(0.2)

        def wait_for_schema_ready(timeout_seconds=120):
          """Wait for critical tables to appear when another reset is running."""
          start = time.time()
          while time.time() - start <= timeout_seconds:
            check_cmd = [
              "mysql",
              f"-h{db_host}",
              f"-u{db_user}",
              f"-p{db_password}",
              "--skip-ssl",
              db_name,
              "-N",
              "-e",
              "SHOW TABLES LIKE 'users'; SHOW TABLES LIKE 'settings';"
            ]

            check_result = subprocess.run(
              check_cmd,
              capture_output=True,
              text=True,
              timeout=10
            )

            if check_result.returncode == 0:
              table_lines = {line.strip() for line in check_result.stdout.splitlines() if line.strip()}
              if "users" in table_lines and "settings" in table_lines:
                return

            time.sleep(1)

          raise Exception("Timed out waiting for in-progress database reset to complete")

        def release_reset_lock(fd):
          try:
            if fd is not None:
              os.close(fd)
          finally:
            try:
              os.remove(lock_path)
            except FileNotFoundError:
              pass

        def ensure_database_exists_with_root():
          if not db_root_password:
            return

          create_if_missing_cmd = [
            "mysql",
            f"-h{db_host}",
            "-uroot",
            f"-p{db_root_password}",
            "--skip-ssl",
            "-e",
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
          ]

          create_result = subprocess.run(
            create_if_missing_cmd,
            capture_output=True,
            text=True,
            timeout=30
          )
          if create_result.returncode != 0:
            raise Exception(f"Failed to ensure database exists: {create_result.stderr}")

          grant_cmd = [
            "mysql",
            f"-h{db_host}",
            "-uroot",
            f"-p{db_root_password}",
            "--skip-ssl",
            "-e",
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'%'; FLUSH PRIVILEGES;"
          ]

          grant_result = subprocess.run(
            grant_cmd,
            capture_output=True,
            text=True,
            timeout=30
          )
          if grant_result.returncode != 0:
            logger.warning(f"Failed to grant permissions during reset: {grant_result.stderr}")

        def drop_all_tables_with_app_user():
          """Drop all tables in the target schema using the app DB user."""
          get_tables_cmd = [
            "mysql",
            f"-h{db_host}",
            f"-u{db_user}",
            f"-p{db_password}",
            "--skip-ssl",
            db_name,
            "-N",
            "-e",
            "SHOW TABLES;"
          ]

          tables_result = subprocess.run(
            get_tables_cmd,
            capture_output=True,
            text=True,
            timeout=30
          )

          if tables_result.returncode != 0:
            raise Exception(f"Failed to list tables: {tables_result.stderr}")

          tables = [t.strip() for t in tables_result.stdout.strip().split('\n') if t.strip()]
          logger.info(f"Found {len(tables)} tables to delete")

          if tables:
            drop_statements = "SET FOREIGN_KEY_CHECKS = 0; "
            for table in tables:
              drop_statements += f"DROP TABLE IF EXISTS `{table}`; "
            drop_statements += "SET FOREIGN_KEY_CHECKS = 1;"

            drop_cmd = [
              "mysql",
              f"-h{db_host}",
              f"-u{db_user}",
              f"-p{db_password}",
              "--skip-ssl",
              db_name,
              "-e",
              drop_statements
            ]

            drop_result = subprocess.run(
              drop_cmd,
              capture_output=True,
              text=True,
              timeout=120
            )

            if drop_result.returncode != 0:
              raise Exception(f"Failed to drop tables: {drop_result.stderr}")

        lock_fd = acquire_reset_lock()
        if lock_fd is None:
          logger.info("Database reset already in progress; waiting for completion")
          wait_for_schema_ready()
          return jsonify({"success": True, "message": "Database reset completed by another request"})

        os.write(lock_fd, str(os.getpid()).encode("utf-8"))

        # Reset connection pools before destructive DB operations.
        try:
            engine.dispose()
            logger.info("Disposed SQLAlchemy engine connection pool")
        except Exception as e:
            logger.warning(f"Error disposing engine pool: {e}")

        # Kill active database connections to prevent metadata lock timeouts.
        try:
            get_pids_cmd = [
                "mysql",
                f"-h{db_host}",
                f"-u{db_user}",
                f"-p{db_password}",
                "--skip-ssl",
                "-N",
                "-e",
                f"SELECT id FROM INFORMATION_SCHEMA.PROCESSLIST WHERE db = '{db_name}' AND id != CONNECTION_ID();"
            ]

            pids_result = subprocess.run(
                get_pids_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if pids_result.returncode == 0 and pids_result.stdout.strip():
                pids = [pid.strip() for pid in pids_result.stdout.strip().split('\n') if pid.strip()]
                logger.info(f"Found {len(pids)} active connections to kill: {pids}")

                for pid in pids:
                    kill_cmd = [
                        "mysql",
                        f"-h{db_host}",
                        f"-u{db_user}",
                        f"-p{db_password}",
                        "--skip-ssl",
                        "-e",
                        f"KILL {pid};"
                    ]
                    try:
                        subprocess.run(kill_cmd, capture_output=True, text=True, timeout=5)
                    except Exception as e:
                        logger.warning(f"Could not kill connection {pid}: {e}")

                time.sleep(1)
            else:
                logger.info("No active connections to kill")
        except Exception as e:
            logger.warning(f"Error killing connections before reset: {e}")

        # Keep schema in place and reset at table-level to avoid drop/create races.
        ensure_database_exists_with_root()
        drop_all_tables_with_app_user()

        # Run Alembic migrations to recreate database with proper version tracking
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd="/app",
            capture_output=True,
            text=True,
          timeout=300
        )

        if result.returncode != 0:
            raise Exception(f"Alembic migration failed: {result.stderr}")

        logger.info("Database deleted and recreated successfully via Alembic migrations")
        return jsonify({"success": True, "message": "Database deleted successfully"})
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout while deleting database")
        return jsonify({"success": False, "message": "Timeout while deleting database"}), 500
    except Exception as e:
        logger.error(f"Error deleting database: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if lock_fd is not None:
            release_reset_lock(lock_fd)


@app.route("/api/settings/schema", methods=["GET"])
@require_permission('setting.view')
def get_settings_schema():
    """Get the settings schema showing all allowed settings and their validation rules.
    ---
    tags:
      - Settings
    responses:
      200:
        description: Settings schema
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            schema:
              type: object
              description: Map of setting keys to their schema definitions
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
        # Build schema response without the validate functions (not JSON serializable)
        schema_response = {}
        for key, schema in SETTINGS_SCHEMA.items():
            schema_response[key] = {
                "type": schema["type"],
                "nullable": schema.get("nullable", False),
                "description": schema.get("description", ""),
            }

        return jsonify({"success": True, "schema": schema_response})
    except Exception as e:
        logger.error(f"Error getting settings schema: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/<key>", methods=["GET"])
@require_permission('setting.view')
def get_setting(key):
    """Get a setting value by key (user-specific or global) with validation.
    ---
    tags:
      - Settings
    parameters:
      - name: key
        in: path
        type: string
        required: true
        description: The setting key to retrieve
    responses:
      200:
        description: Setting value (validated)
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            key:
              type: string
              example: "default_board"
            value:
              description: JSON parsed value
              example: null
      401:
        description: Authentication required
      403:
        description: Permission denied
      404:
        description: Setting not found
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
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
        # Use user-scoped query which gets user's settings + global settings (where user_id IS NULL)
        setting = get_user_scoped_query(db, Setting, user_id).filter(Setting.key == key).first()

        if not setting:
            return (
                jsonify({"success": False, "message": f"Setting '{key}' not found"}),
                404,
            )

        # Parse JSON value
        try:
            value = json.loads(setting.value) if setting.value else None
        except json.JSONDecodeError:
            value = setting.value

        # Special validation for default_board
        if key == "default_board" and value is not None:
            # Check if board exists
            board = db.query(Board).filter(Board.id == value).first()
            if not board:
                # Board doesn't exist, auto-correct to null
                logger.warning(f"Default board {value} not found, resetting to null")
                setting.value = "null"
                db.commit()
                value = None

        return jsonify({"success": True, "key": key, "value": value})
    except Exception as e:
        db.rollback()
        logger.error(f"Error getting setting: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/<key>", methods=["PUT"])
@require_permission('setting.edit')
def set_setting(key):
    """Create or update a user-specific setting (upsert).
    ---
    tags:
      - Settings
    parameters:
      - name: key
        in: path
        type: string
        required: true
        description: The setting key to set
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - value
          properties:
            value:
              description: The value to store (will be JSON stringified)
              example: 123
    responses:
      200:
        description: Setting updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Setting updated successfully"
            key:
              type: string
            value:
              description: The stored value
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
    try:
        # Handle case where get_json() might raise an exception for empty body
        try:
            data = request.get_json()
        except Exception:
            data = None
            
        if data is None or "value" not in data:
            return jsonify({"success": False, "message": "Value is required"}), 400

        # Validate setting key and value against schema
        is_valid, error_message = validate_setting(key, data["value"])
        if not is_valid:
            return jsonify({"success": False, "message": error_message}), 400

        user_id = g.user.id
        
        # Additional validation for default_board: verify board exists and user owns it
        if key == "default_board" and data["value"] is not None:
            db_check = SessionLocal()
            try:
                board_exists = (
                    get_user_scoped_query(db_check, Board, user_id).filter(Board.id == data["value"]).first()
                )
                if not board_exists:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": f"Board with ID {data['value']} does not exist or you don't have access",
                            }
                        ),
                        400,
                    )
            finally:
                db_check.close()

        # Convert value to JSON string
        value = json.dumps(data["value"])

        db = SessionLocal()
        try:
            # Query user-specific setting
            setting = db.query(Setting).filter(Setting.key == key, Setting.user_id == user_id).first()

            if setting:
                # Update existing user setting
                setting.value = value
                message = "Setting updated successfully"
            else:
                # Create new user-specific setting
                setting = Setting(key=key, value=value, user_id=user_id)
                db.add(setting)
                message = "Setting created successfully"

            db.commit()
            db.refresh(setting)

            # Parse back for response
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                parsed_value = value

            return jsonify(
                {"success": True, "message": message, "key": key, "value": parsed_value}
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error setting setting: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/backup/config", methods=["GET"])
@require_permission('setting.view')
def get_backup_config():
    """Get all backup configuration settings.
    ---
    tags:
      - Settings
    responses:
      200:
        description: Backup configuration retrieved successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            config:
              type: object
              properties:
                enabled:
                  type: boolean
                frequency_value:
                  type: integer
                frequency_unit:
                  type: string
                start_time:
                  type: string
                retention_count:
                  type: integer
                last_run:
                  type: string
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        keys = [
            "backup_enabled",
            "backup_frequency_value",
            "backup_frequency_unit",
            "backup_start_time",
            "backup_retention_count",
            "backup_minimum_free_space_mb",
            "backup_last_run"
        ]
        
        config = {}
        # Backup settings are global (user_id = NULL)
        for key in keys:
            setting = db.query(Setting).filter(Setting.key == key, Setting.user_id.is_(None)).first()
            if setting:
                # Try to parse JSON, otherwise use raw value
                try:
                    config[key.replace("backup_", "")] = json.loads(setting.value)
                except (json.JSONDecodeError, TypeError):
                    config[key.replace("backup_", "")] = setting.value
            else:
                # No default - return None if setting doesn't exist
                config[key.replace("backup_", "")] = None
        
        return jsonify({"success": True, "config": config})
    except Exception as e:
        logger.error(f"Error getting backup config: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/backup/config", methods=["PUT"])
@require_permission('setting.edit')
def update_backup_config():
    """Update backup configuration settings.
    ---
    tags:
      - Settings
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            enabled:
              type: boolean
              example: true
            frequency_value:
              type: integer
              example: 1
              minimum: 1
              maximum: 99
            frequency_unit:
              type: string
              example: "days"
              enum: ["minutes", "hours", "days"]
            start_time:
              type: string
              example: "02:00"
              pattern: "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
            retention_count:
              type: integer
              example: 7
              minimum: 1
              maximum: 100
    responses:
      200:
        description: Backup configuration updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
      400:
        description: Invalid input
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"success": False, "message": "Request body is required"}), 400
        
        # Allow empty body - just return success without updating anything
        if not data:
            return jsonify({"success": True, "message": "No settings to update"})
        
        # Map frontend field names to setting keys
        mapping = {
            "enabled": "backup_enabled",
            "frequency_value": "backup_frequency_value",
            "frequency_unit": "backup_frequency_unit",
            "start_time": "backup_start_time",
            "retention_count": "backup_retention_count",
            "minimum_free_space_mb": "backup_minimum_free_space_mb"
        }
        
        # Validate all provided fields using the settings schema
        errors = []
        for field, key in mapping.items():
            if field in data:
                is_valid, error_msg = validate_setting(key, data[field])
                if not is_valid:
                    errors.append(error_msg)
        
        # Additional validation: If frequency_unit is "daily", frequency_value must be 1
        if "frequency_unit" in data and data.get("frequency_unit") == "daily":
            freq_value = data.get("frequency_value")
            # If frequency_value not in request, check the existing database value
            if freq_value is None:
                # Backup settings are global (user_id = NULL)
                setting = db.query(Setting).filter(Setting.key == "backup_frequency_value", Setting.user_id.is_(None)).first()
                if setting:
                    try:
                        freq_value = json.loads(setting.value)
                    except (json.JSONDecodeError, TypeError):
                        freq_value = None
            
            # Now validate that frequency_value is 1 if daily
            if freq_value is not None and freq_value != 1:
                errors.append("Daily backups must have frequency_value of 1 (not configurable)")
        
        if errors:
            return jsonify({"success": False, "message": "; ".join(errors)}), 400
        
        # Additional validation: Cannot enable backups if required settings are invalid or missing
        if data.get("enabled") is True:
            # Get current settings for fields not being updated
            current_settings = {}
            for field, key in mapping.items():
                if field not in data:
                    # Backup settings are global (user_id = NULL)
                    setting = db.query(Setting).filter(Setting.key == key, Setting.user_id.is_(None)).first()
                    if setting:
                        try:
                            current_settings[field] = json.loads(setting.value)
                        except (json.JSONDecodeError, TypeError):
                            current_settings[field] = None
                    else:
                        current_settings[field] = None
            
            # Merge with new data
            final_settings = {**current_settings, **data}
            
            # Validate all required settings are present and valid
            required_errors = []
            for field in ["frequency_value", "frequency_unit", "start_time", "retention_count", "minimum_free_space_mb"]:
                key = mapping[field]
                value = final_settings.get(field)
                if value is None:
                    required_errors.append(f"{field} must be set before enabling backups")
                else:
                    is_valid, error_msg = validate_setting(key, value)
                    if not is_valid:
                        required_errors.append(error_msg)
            
            # Additional validation: If frequency_unit is daily, frequency_value must be 1
            if final_settings.get("frequency_unit") == "daily" and final_settings.get("frequency_value") != 1:
                required_errors.append("Daily backups require frequency_value of 1")
            
            if required_errors:
                return jsonify({
                    "success": False,
                    "message": "Cannot enable backups with invalid settings: " + "; ".join(required_errors)
                }), 400
        
        # Update global backup settings (user_id = NULL)
        for field, key in mapping.items():
            if field in data:
                value = json.dumps(data[field])
                setting = db.query(Setting).filter(Setting.key == key, Setting.user_id.is_(None)).first()
                
                if setting:
                    setting.value = value
                else:
                    # Create as global setting (user_id = NULL)
                    setting = Setting(key=key, value=value, user_id=None)
                    db.add(setting)
        
        db.commit()
        
        return jsonify({"success": True, "message": "Backup configuration updated successfully"})
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating backup config: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/backup/status", methods=["GET"])
@require_permission('setting.view')
def get_backup_status():
    """Get backup scheduler status.
    ---
    tags:
      - Settings
    responses:
      200:
        description: Backup scheduler status
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            status:
              type: object
    """
    try:
        from backup_scheduler import get_scheduler
        scheduler = get_scheduler()
        
        # Attempt to restart scheduler if it failed due to permissions that were fixed
        scheduler.retry_start_if_permission_fixed()
        
        status = scheduler.get_status()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error getting backup status: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/housekeeping/status", methods=["GET"])
@require_permission('setting.view')
def get_housekeeping_status():
    """Get housekeeping scheduler status.
    ---
    tags:
      - Settings
    responses:
      200:
        description: Housekeeping scheduler status
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            status:
              type: object
    """
    try:
        from housekeeping_scheduler import get_housekeeping_scheduler
        scheduler = get_housekeeping_scheduler(APP_VERSION)
        status = scheduler.get_status()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error getting housekeeping status: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/housekeeping/config", methods=["PUT"])
@require_permission('setting.edit')
def update_housekeeping_config():
    """Update housekeeping scheduler configuration.
    ---
    tags:
      - Settings
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            enabled:
              type: boolean
    responses:
      200:
        description: Configuration updated successfully
      400:
        description: Bad request
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        data = request.get_json(silent=True)
        if data is None or "enabled" not in data:
            return jsonify({"success": False, "message": "enabled field is required"}), 400
        
        enabled = data["enabled"]
        if not isinstance(enabled, bool):
            return jsonify({"success": False, "message": "enabled must be a boolean"}), 400
        
        # Update global housekeeping setting (user_id = NULL)
        setting = db.query(Setting).filter(Setting.key == "housekeeping_enabled", Setting.user_id.is_(None)).first()
        value = json.dumps(enabled)
        
        if setting:
            setting.value = value
        else:
            # Create as global setting (user_id = NULL)
            setting = Setting(key="housekeeping_enabled", value=value, user_id=None)
            db.add(setting)
        
        db.commit()
        
        return jsonify({"success": True, "message": "Housekeeping configuration updated successfully"})
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating housekeeping config: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/card-scheduler/status", methods=["GET"])
@require_permission('setting.view')
def get_card_scheduler_status():
    """Get card scheduler status.
    ---
    tags:
      - Settings
    responses:
      200:
        description: Card scheduler status
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            status:
              type: object
    """
    try:
        from card_scheduler import get_scheduler as get_card_scheduler
        scheduler = get_card_scheduler()
        
        # Get global card scheduler enabled setting (user_id = NULL)
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == "card_scheduler_enabled", Setting.user_id.is_(None)).first()
            if setting is not None and setting.value is not None:
                enabled = json.loads(str(setting.value))
            else:
                enabled = True  # Default to enabled
        finally:
            db.close()
        
        status = {
            "running": scheduler.running,
            "enabled": enabled
        }
        
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error getting card scheduler status: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/card-scheduler/config", methods=["PUT"])
@require_permission('setting.edit')
def update_card_scheduler_config():
    """Update card scheduler configuration.
    ---
    tags:
      - Settings
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            enabled:
              type: boolean
    responses:
      200:
        description: Configuration updated successfully
      400:
        description: Bad request
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        data = request.get_json(silent=True)
        if data is None or "enabled" not in data:
            return jsonify({"success": False, "message": "enabled field is required"}), 400
        
        enabled = data["enabled"]
        if not isinstance(enabled, bool):
            return jsonify({"success": False, "message": "enabled must be a boolean"}), 400
        
        # Update global card scheduler setting (user_id = NULL)
        setting = db.query(Setting).filter(Setting.key == "card_scheduler_enabled", Setting.user_id.is_(None)).first()
        value = json.dumps(enabled)
        
        if setting:
            setting.value = value
        else:
            # Create as global setting (user_id = NULL)
            setting = Setting(key="card_scheduler_enabled", value=value, user_id=None)
            db.add(setting)
        
        db.commit()
        
        return jsonify({"success": True, "message": "Card scheduler configuration updated successfully"})
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating card scheduler config: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


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


@app.route("/api/boards/<int:board_id>/settings/working-style", methods=["GET"])
@require_board_access()
@require_permission('board.view')
def get_board_working_style_setting(board_id):
    """Get the working style for a specific board."""
    db = SessionLocal()
    try:
        value = get_board_working_style(db, board_id)
        board_permissions = get_user_permissions(g.user.id, board_id)

        from permissions import has_permission
        can_edit = has_permission(board_permissions, 'board.edit')

        return jsonify(
            {
                "success": True,
                "board_id": board_id,
                "key": "working_style",
                "value": value,
                "can_edit": can_edit,
            }
        ), 200
    except Exception as e:
        logger.error(f"Error getting board working style for board {board_id}: {str(e)}")
        return create_error_response("Failed to get board working style", 500)
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>/settings/working-style", methods=["PUT"])
@require_board_access()
@require_permission('board.edit')
def set_board_working_style_setting(board_id):
    """Set the working style for a specific board."""
    db = SessionLocal()
    try:
        data = request.get_json(silent=True)
        if data is None or "value" not in data:
            return create_error_response("value is required", 400)

        working_style = normalize_working_style(data.get("value"))
        if working_style not in WORKING_STYLE_ALLOWED_VALUES:
            return create_error_response(
                f"Invalid working_style. Must be one of: {', '.join(WORKING_STYLE_ALLOWED_VALUES)}",
                400,
            )

        setting = db.query(BoardSetting).filter(
            BoardSetting.board_id == board_id,
            BoardSetting.key == 'working_style'
        ).first()

        value = json.dumps(working_style)
        if setting:
            setting.value = value
            message = "Board working style updated"
        else:
            db.add(
                BoardSetting(
                    board_id=board_id,
                    key='working_style',
                    value=value,
                )
            )
            message = "Board working style created"

        db.commit()

        return jsonify(
            {
                "success": True,
                "message": message,
                "board_id": board_id,
                "key": "working_style",
                "value": working_style,
            }
        ), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting board working style for board {board_id}: {str(e)}")
        return create_error_response("Failed to set board working style", 500)
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


# ============================================================================
# Notification Routes
# ============================================================================


@app.route("/api/notifications", methods=["GET"])
@require_authentication
def get_notifications():
    """Get all notifications for the current user.
    ---
    tags:
      - Notifications
    responses:
      200:
        description: List of all notifications for the user (newest first)
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            notifications:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  subject:
                    type: string
                  message:
                    type: string
                  unread:
                    type: boolean
                  created_at:
                    type: string
                    format: date-time
      401:
        description: Authentication required
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        user_id = g.user.id
        notifications = (
            get_user_scoped_query(db, Notification, user_id)
            .order_by(Notification.created_at.desc())  # Newest first
            .all()
        )

        return jsonify(
            {
                "success": True,
                "notifications": [
                    {
                        "id": n.id,
                        "subject": n.subject,
                        "message": n.message,
                        "unread": n.unread,
                        "created_at": n.created_at.isoformat() if n.created_at else None,
                        "action_title": n.action_title,
                        "action_url": n.action_url,
                    }
                    for n in notifications
                ],
            }
        ), 200

    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        return jsonify({"success": False, "message": "Failed to retrieve notifications"}), 500
    finally:
        db.close()


# Import notification utility with alias to avoid conflict with API route
from notification_utils import create_notification as create_notification_internal


@app.route("/api/notifications", methods=["POST"])
@require_authentication
def create_notification():
    """Create a new notification.
    ---
    tags:
      - Notifications
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - subject
            - message
          properties:
            subject:
              type: string
              description: Subject of the notification
              example: "New Feature Available"
            message:
              type: string
              description: Message content of the notification
              example: "Check out our new dark mode feature!"
            action_title:
              type: string
              description: Optional action button title (recommended max 50 chars, hard limit 100)
              example: "Learn More"
            action_url:
              type: string
              description: Optional action button URL (max 500 chars)
              example: "/settings"
    responses:
      201:
        description: Notification created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            notification:
              type: object
              properties:
                id:
                  type: integer
                subject:
                  type: string
                message:
                  type: string
                unread:
                  type: boolean
                created_at:
                  type: string
                  format: date-time
                action_title:
                  type: string
                action_url:
                  type: string
      400:
        description: Invalid request
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        
        # Validate required fields
        if not subject or not message:
            return jsonify({"success": False, "message": "Subject and message are required"}), 400
        
        # Validate length limits (matching database column constraints)
        if len(subject) > 255:
            return jsonify({"success": False, "message": "Subject must be 255 characters or less"}), 400
        
        if len(message) > 65535:
            return jsonify({"success": False, "message": "Message must be 65535 characters or less"}), 400

        # Process optional action fields
        action_title = data.get('action_title', '').strip() or None if 'action_title' in data else None
        action_url = data.get('action_url', '').strip() or None if 'action_url' in data else None
        
        # Validate action fields if provided
        if action_title is not None:
            if len(action_title) > 100:
                return jsonify({"success": False, "message": "Action title must be 100 characters or less"}), 400
            # Recommend max 50 chars for better UX
            if len(action_title) > 50:
                logger.warning(f"Action title exceeds recommended length of 50 chars: {len(action_title)} chars")
            
        if action_url is not None:
            if len(action_url) > 500:
                return jsonify({"success": False, "message": "Action URL must be 500 characters or less"}), 400
            # Validate URL safety
            is_valid, error_msg = validate_safe_url(action_url)
            if not is_valid:
                return jsonify({"success": False, "message": f"Invalid action URL: {error_msg}"}), 400

        # Create notification
        notification = Notification(
            subject=subject,
            message=message,
            unread=True,
            action_title=action_title,
            action_url=action_url,
            user_id=get_current_user_id()  # Associate with authenticated user
        )
        
        db.add(notification)
        db.commit()
        db.refresh(notification)

        logger.info(f"Created notification: {notification.id}")
        
        return jsonify({
            "success": True,
            "notification": {
                "id": notification.id,
                "subject": notification.subject,
                "message": notification.message,
                "unread": notification.unread,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
                "action_title": notification.action_title,
                "action_url": notification.action_url,
            }
        }), 201

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating notification: {str(e)}")
        return jsonify({"success": False, "message": "Failed to create notification"}), 500
    finally:
        db.close()


@app.route("/api/notifications/<int:notification_id>/read", methods=["PUT"])
@require_authentication
def mark_notification_read(notification_id):
    """Mark a notification as read.
    ---
    tags:
      - Notifications
    parameters:
      - name: notification_id
        in: path
        type: integer
        required: true
        description: The ID of the notification
    responses:
      200:
        description: Notification marked as read
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Notification marked as read"
      404:
        description: Notification not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == get_current_user_id()
        ).first()

        if not notification:
            return create_error_response("Notification not found", 404)

        notification.unread = False
        db.commit()

        logger.info(f"Notification {notification_id} marked as read")
        return jsonify({"success": True, "message": "Notification marked as read"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking notification {notification_id} as read: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/notifications/<int:notification_id>/unread", methods=["PUT"])
@require_authentication
def mark_notification_unread(notification_id):
    """Mark a notification as unread.
    ---
    tags:
      - Notifications
    parameters:
      - name: notification_id
        in: path
        type: integer
        required: true
        description: The ID of the notification
    responses:
      200:
        description: Notification marked as unread
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Notification marked as unread"
      404:
        description: Notification not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == get_current_user_id()
        ).first()

        if not notification:
            return create_error_response("Notification not found", 404)

        notification.unread = True
        db.commit()

        logger.info(f"Notification {notification_id} marked as unread")
        return jsonify({"success": True, "message": "Notification marked as unread"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking notification {notification_id} as unread: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/notifications/<int:notification_id>", methods=["DELETE"])
@require_authentication
def delete_notification(notification_id):
    """Delete a notification.
    ---
    tags:
      - Notifications
    parameters:
      - name: notification_id
        in: path
        type: integer
        required: true
        description: The ID of the notification
    responses:
      200:
        description: Notification deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "Notification deleted successfully"
      404:
        description: Notification not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == get_current_user_id()
        ).first()

        if not notification:
            return create_error_response("Notification not found", 404)

        db.delete(notification)
        db.commit()

        logger.info(f"Notification {notification_id} deleted")
        return jsonify({"success": True, "message": "Notification deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting notification {notification_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/notifications/mark-all-read", methods=["PUT"])
@require_authentication
def mark_all_notifications_read():
    """Mark all notifications as read.
    ---
    tags:
      - Notifications
    responses:
      200:
        description: All notifications marked as read
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "All notifications marked as read"
            count:
              type: integer
              description: Number of notifications marked as read
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        # Update all unread notifications belonging to the current user
        current_user_id = get_current_user_id()
        result = db.query(Notification).filter(
            Notification.unread.is_(True),
            Notification.user_id == current_user_id
        ).update({"unread": False})
        db.commit()

        logger.info(f"Marked {result} notifications as read")
        return jsonify({
            "success": True, 
            "message": "All notifications marked as read",
            "count": result
        }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking all notifications as read: {str(e)}")
        return jsonify({"success": False, "message": "Failed to mark all notifications as read"}), 500
    finally:
        db.close()


@app.route("/api/notifications/delete-all", methods=["DELETE"])
@require_authentication
def delete_all_notifications():
    """Delete all notifications.
    ---
    tags:
      - Notifications
    responses:
      200:
        description: All notifications deleted
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: "All notifications deleted"
            count:
              type: integer
              description: Number of notifications deleted
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        # Delete all notifications belonging to the current user
        current_user_id = get_current_user_id()
        result = db.query(Notification).filter(
            Notification.user_id == current_user_id
        ).delete()
        db.commit()

        logger.info(f"Deleted {result} notifications")
        return jsonify({
            "success": True, 
            "message": "All notifications deleted",
            "count": result
        }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting all notifications: {str(e)}")
        return jsonify({"success": False, "message": "Failed to delete all notifications"}), 500
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
# Theme API Endpoints
# ============================================================================


def _get_user_accessible_theme(session, user_id, theme_id):
    """Return a theme only if it is visible to the current user."""
    return get_user_scoped_query(session, Theme, user_id).filter(Theme.id == theme_id).first()

@app.route("/api/themes", methods=["GET"])
@require_permission('theme.view')
def get_themes():
    """Retrieve all themes accessible to the user.
    
    Fetches and returns a list of all available themes, including both
    system themes (global) and user-created custom themes. Each theme includes
    its ID, name, settings, background image, and system theme flag.
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with list of theme objects
            - 401: Authentication required
            - 403: Permission denied
            - 500: Server error during database query
    
    Example:
        GET /api/themes
        Response: [{"id": 1, "name": "Dark", "settings": {...}, ...}, ...]
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        # Use user-scoped query which gets user's themes + system themes (where user_id IS NULL)
        themes = get_user_scoped_query(session, Theme, user_id).all()
        return jsonify([theme.to_dict() for theme in themes]), 200
    except Exception as e:
        logger.error(f"Error getting themes: {str(e)}")
        return create_error_response(f"Error getting themes: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>", methods=["GET"])
@require_permission('theme.view')
def get_theme(theme_id):
    """Retrieve a specific theme by its unique ID (user must have access).
    
    Fetches detailed information about a single theme including its
    name, color settings, background image, and whether it's a system
    theme. Useful for loading a theme for preview or editing.
    
    Args:
        theme_id (int): The unique identifier of the theme to retrieve
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with theme object
            - 401: Authentication required
            - 403: Permission denied
            - 404: Theme with specified ID not found
            - 500: Server error during database query
    
    Example:
        GET /api/themes/5
        Response: {"id": 5, "name": "Custom Blue", "settings": {...}, ...}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        theme = get_user_scoped_query(session, Theme, user_id).filter(Theme.id == theme_id).first()
        if not theme:
            return create_error_response("Theme not found", 404)
        return jsonify(theme.to_dict()), 200
    except Exception as e:
        logger.error(f"Error getting theme {theme_id}: {str(e)}")
        return create_error_response(f"Error getting theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>", methods=["PUT"])
@require_permission('theme.edit')
def update_theme(theme_id):
    """Update an existing custom theme's properties.
    
    Modifies one or more properties of a user-created theme. System themes
    cannot be modified. Supports partial updates - only specified fields
    are changed. When updating the name, uniqueness is validated.
    
    Args:
        theme_id (int): The unique identifier of the theme to update
    
    Request Body:
        name (str, optional): New name for the theme (must be unique)
        settings (dict, optional): Theme color settings and configurations
        background_image (str, optional): Filename of background image
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with updated theme object
            - 400: Cannot update system theme or name already exists
            - 404: Theme with specified ID not found
            - 500: Server error during update
    
    Raises:
        Exception: Database errors during commit are caught and rolled back
    
    Example:
        PUT /api/themes/5
        Body: {"name": "Updated Theme", "settings": {"primary-color": "#3498db"}}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        theme = _get_user_accessible_theme(session, user_id, theme_id)
        if not theme:
            return create_error_response("Theme not found", 404)
        
        if theme.system_theme:
            return create_error_response("Cannot update system themes", 400)
        
        try:
            data = request.get_json(silent=True)
        except BadRequest:
            data = None
        
        if not data or not isinstance(data, dict):
            return create_error_response("Request body must contain valid JSON object", 400)
        
        if 'name' in data:
            # Check if name is unique
            existing = session.query(Theme).filter(Theme.name == data['name'], Theme.id != theme_id).first()
            if existing:
                return create_error_response("Theme name already exists", 400)
            theme.name = data['name']
        
        if 'settings' in data:
            theme.settings = json.dumps(data['settings'])
        
        if 'background_image' in data:
            theme.background_image = data['background_image']
        
        session.commit()
        
        # Broadcast theme change to all connected clients
        broadcast_theme_event('theme_updated', {
            'theme_id': theme_id,
            'theme_name': theme.name
        })
        
        return jsonify(theme.to_dict()), 200
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating theme {theme_id}: {str(e)}")
        return create_error_response(f"Error updating theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>/rename", methods=["PUT"])
@require_permission('theme.edit')
def rename_theme(theme_id):
    """Change the name of an existing custom theme.
    
    Provides a dedicated endpoint for renaming themes. System themes
    cannot be renamed. The new name must be unique across all themes.
    This is a convenience endpoint that performs only name updates.
    
    Args:
        theme_id (int): The unique identifier of the theme to rename
    
    Request Body:
        name (str, required): The new name for the theme
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with updated theme object
            - 400: Missing name, cannot rename system theme, or name exists
            - 404: Theme with specified ID not found
            - 500: Server error during update
    
    Raises:
        Exception: Database errors during commit are caught and rolled back
    
    Example:
        PUT /api/themes/5/rename
        Body: {"name": "My Blue Theme"}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        theme = _get_user_accessible_theme(session, user_id, theme_id)
        if not theme:
            return create_error_response("Theme not found", 404)
        
        if theme.system_theme:
            return create_error_response("Cannot rename system themes", 400)
        
        data = request.get_json()
        new_name = data.get('name')
        
        if not new_name:
            return create_error_response("name is required", 400)
        
        # Check if name is unique
        existing = session.query(Theme).filter(Theme.name == new_name, Theme.id != theme_id).first()
        if existing:
            return create_error_response("Theme name already exists", 400)
        
        theme.name = new_name
        session.commit()
        
        return jsonify(theme.to_dict()), 200
    except Exception as e:
        session.rollback()
        logger.error(f"Error renaming theme {theme_id}: {str(e)}")
        return create_error_response(f"Error renaming theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>", methods=["DELETE"])
@require_permission('theme.delete')
def delete_theme(theme_id):
    """Delete a custom theme.
    
    Removes a theme from the database. System themes cannot be deleted.
    If the deleted theme is currently selected, the selected_theme setting
    will become invalid and should be updated by the client.
    
    Args:
        theme_id (int): The unique identifier of the theme to delete
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with confirmation message
            - 400: Cannot delete system themes
            - 404: Theme with specified ID not found
            - 500: Server error during deletion
    
    Raises:
        Exception: Database errors during commit are caught and rolled back
    
    Example:
        DELETE /api/themes/5
        Response: {"success": true, "message": "Theme deleted successfully"}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        theme = _get_user_accessible_theme(session, user_id, theme_id)
        if not theme:
            return create_error_response("Theme not found", 404)
        
        if theme.system_theme:
            return create_error_response("Cannot delete system themes", 400)
        
        session.delete(theme)
        session.commit()
        
        return create_success_response(message="Theme deleted successfully")
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting theme {theme_id}: {str(e)}")
        return create_error_response(f"Error deleting theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/copy", methods=["POST"])
@require_permission('theme.create')
def copy_theme():
    """Create a duplicate of an existing theme with a new name.
    
    Copies all settings and properties from a source theme to create a new
    independent theme. This is useful for customizing existing themes without
    modifying the original. The copy is always created as a custom (non-system)
    theme, even if the source is a system theme.
    
    Request Body:
        source_theme_id (int, required): ID of the theme to duplicate
        new_name (str, required): Unique name for the new theme
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 201: Success with newly created theme object
            - 400: Missing required fields or name already exists
            - 404: Source theme with specified ID not found
            - 500: Server error during creation
    
    Raises:
        Exception: Database errors during commit are caught and rolled back
    
    Example:
        POST /api/themes/copy
        Body: {"source_theme_id": 1, "new_name": "My Custom Dark"}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        data = request.get_json()
        source_id = data.get('source_theme_id')
        new_name = data.get('new_name')
        
        if not source_id or not new_name:
            return create_error_response("source_theme_id and new_name are required", 400)
        
        # Check if source theme exists
        source_theme = _get_user_accessible_theme(session, user_id, source_id)
        if not source_theme:
            return create_error_response("Source theme not found", 404)

        # Users can only create persistent custom themes by copying system themes.
        if not source_theme.system_theme:
          return create_error_response("Only system themes can be copied", 400)
        
        # Check if new name is unique
        existing = session.query(Theme).filter(Theme.name == new_name).first()
        if existing:
            return create_error_response("Theme name already exists", 400)
        
        # Create new theme as copy
        new_theme = Theme(
            name=new_name,
            settings=source_theme.settings,
            background_image=source_theme.background_image,
            system_theme=False,  # Copied themes are never system themes
            user_id=user_id,
        )
        session.add(new_theme)
        session.commit()
        
        return jsonify(new_theme.to_dict()), 201
    except Exception as e:
        session.rollback()
        logger.error(f"Error copying theme: {str(e)}")
        return create_error_response(f"Error copying theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/import", methods=["POST"])
@require_permission('theme.create')
def import_theme():
    """Import a theme from external JSON data.
    
    Creates a new theme from JSON configuration, typically from an exported
    theme file. Validates that the settings object contains required color
    properties. The imported theme is created as a custom (non-system) theme
    with a unique name.
    
    Request Body:
        name (str, required): Unique name for the imported theme
        settings (dict, required): Theme configuration with required keys:
            - primary-color: Main UI color
            - text-color: Text color
            - background-light: Light background color
            - card-bg-color: Card background color
        background_image (str, optional): Background image filename
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 201: Success with newly created theme object
            - 400: Missing fields, invalid structure, or name already exists
            - 500: Server error during creation
    
    Raises:
        Exception: Database errors during commit are caught and rolled back
    
    Example:
        POST /api/themes/import
        Body: {"name": "Imported", "settings": {"primary-color": "#3498db", ...}}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        data = request.get_json()
        name = data.get('name')
        settings = data.get('settings')
        
        if not name or not settings:
            return create_error_response("name and settings are required", 400)
        
        # Validate settings structure - should have color properties
        required_keys = ['primary-color', 'text-color', 'background-light', 'card-bg-color']
        if not all(key in settings for key in required_keys):
            return create_error_response("Invalid theme settings structure", 400)
        
        # Check if name is unique
        existing = session.query(Theme).filter(Theme.name == name).first()
        if existing:
            return create_error_response("Theme name already exists", 400)
        
        # Create new theme
        new_theme = Theme(
            name=name,
            settings=json.dumps(settings),
            background_image=data.get('background_image'),
            system_theme=False,
            user_id=user_id,
        )
        session.add(new_theme)
        session.commit()
        
        return jsonify(new_theme.to_dict()), 201
    except Exception as e:
        session.rollback()
        logger.error(f"Error importing theme: {str(e)}")
        return create_error_response(f"Error importing theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>/export", methods=["GET"])
@require_permission('theme.view')
def export_theme(theme_id):
    """Export a theme configuration as JSON data.
    
    Retrieves a theme and formats it as a JSON object suitable for export
    and sharing. The exported data includes the theme name, all settings,
    and background image reference. This data can be imported on other
    installations using the import_theme endpoint.
    
    Args:
        theme_id (int): The unique identifier of the theme to export
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with exportable theme object (name, settings, background_image)
            - 404: Theme with specified ID not found
            - 500: Server error during retrieval
    
    Example:
        GET /api/themes/5/export
        Response: {"name": "My Theme", "settings": {...}, "background_image": "..."}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        theme = _get_user_accessible_theme(session, user_id, theme_id)
        if not theme:
            return create_error_response("Theme not found", 404)
        
        export_data = {
            'name': theme.name,
            'settings': json.loads(theme.settings) if isinstance(theme.settings, str) else theme.settings,
            'background_image': theme.background_image
        }
        
        return jsonify(export_data), 200
    except Exception as e:
        logger.error(f"Error exporting theme {theme_id}: {str(e)}")
        return create_error_response(f"Error exporting theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/upload-image", methods=["POST"])
@require_permission('theme.edit')
def upload_theme_image():
    """Upload a background image file for use in themes.
    
    Accepts image file uploads via multipart form data and saves them to
    the backgrounds directory. Generates a unique filename combining timestamp
    and UUID to prevent collisions. Only common image formats are accepted.
    
    Form Data:
        image (file, required): Image file to upload
            Allowed formats: .jpg, .jpeg, .png, .gif, .webp
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with generated filename {"filename": "theme_bg_1234567890.jpg"}
            - 400: No file provided, empty filename, or invalid file type
            - 500: Server error during file save
    
    Example:
        POST /api/themes/upload-image
        Content-Type: multipart/form-data
        image: [binary file data]
        Response: {"filename": "theme_bg_1702839123.jpg"}
    """
    try:
        if 'image' not in request.files:
            return create_error_response("No image file provided", 400)
        
        file = request.files['image']
        if file.filename == '':
            return create_error_response("No file selected", 400)
        
        # Validate file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return create_error_response(f"Invalid file type. Allowed: {', '.join(allowed_extensions)}", 400)
        
        # Create backgrounds directory if it doesn't exist
        backgrounds_dir = Path('/var/www/images/backgrounds')
        backgrounds_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename with timestamp and UUID to prevent collisions
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        filename = f"theme_bg_{timestamp}_{unique_id}{file_ext}"
        filepath = backgrounds_dir / filename
        
        # Save file
        file.save(str(filepath))
        
        return jsonify({'filename': filename}), 200
    except Exception as e:
        logger.error(f"Error uploading theme image: {str(e)}")
        return create_error_response(f"Error uploading image: {str(e)}", 500)


@app.route("/api/themes/images", methods=["GET"])
@require_permission('theme.view')
def list_theme_images():
    """List all available background images in the backgrounds directory.
    
    Scans the backgrounds directory and returns a sorted list of all image
    files that can be used as theme backgrounds. Creates the directory if
    it doesn't exist. Only files with supported image extensions are included.
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with object containing images array
                {"images": ["theme_bg_123.jpg", "custom_bg.png", ...]}
            - 500: Server error during directory scan
    
    Example:
        GET /api/themes/images
        Response: {"images": ["bg1.jpg", "bg2.png", "theme_bg_1702839123.webp"]}
    """
    try:
        backgrounds_dir = Path('/var/www/images/backgrounds')
        backgrounds_dir.mkdir(parents=True, exist_ok=True)
        
        # List all image files
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        images = []
        
        for file in backgrounds_dir.iterdir():
            if file.is_file() and file.suffix.lower() in allowed_extensions:
                images.append(file.name)
        
        # Sort alphabetically
        images.sort()
        
        return jsonify({'images': images}), 200
    except Exception as e:
        logger.error(f"Error listing theme images: {str(e)}")
        return create_error_response(f"Error listing images: {str(e)}", 500)


@app.route("/api/themes/images/<safe_filename:filename>", methods=["GET"])
@require_permission('theme.view')
def get_theme_image(filename):
    """Retrieve a specific background image file.
    
    Downloads a background image from the backgrounds directory. Includes
    security validation to prevent directory traversal attacks - the resolved
    path must be within the backgrounds directory. Returns the image file
    with appropriate content type headers.
    
    Args:
        filename (str): Name of the image file to retrieve
    
    Returns:
        tuple: (File or JSON response, HTTP status code)
            - 200: Success with image file data
            - 400: Invalid file path (security violation)
            - 404: Image file not found
            - 500: Server error during file retrieval
    
    Example:
        GET /api/themes/images/theme_bg_1702839123.jpg
        Response: [binary image data with appropriate content-type]
    """
    try:
        logger.info(f"get_theme_image called with filename: {repr(filename)}")
        
        # Security: reject paths containing .. (path traversal attempts)
        # Note: SafeFilenameConverter regex r'[^/]+' already prevents forward slashes
        # Backslash check is not needed since Flask URL routing filters path separators
        if '..' in filename:
            logger.warning(f"Path traversal attempt blocked: {repr(filename)}")
            return create_error_response("Invalid file path", 400)
        
        backgrounds_dir = Path('/var/www/images/backgrounds')
        filepath = backgrounds_dir / filename
        
        # Security check - ensure file is in backgrounds directory
        # Use os.path.commonpath as additional safety check
        try:
            common = os.path.commonpath([str(filepath.resolve()), str(backgrounds_dir.resolve())])
            if common != str(backgrounds_dir.resolve()):
                logger.warning(f"Path outside backgrounds directory: {filepath.resolve()}")
                return create_error_response("Invalid file path", 400)
        except ValueError:
            # Paths on different drives (Windows)
            logger.warning(f"Paths on different drives: {filepath.resolve()}")
            return create_error_response("Invalid file path", 400)
        
        if not filepath.exists():
            logger.info(f"Image file not found: {filepath}")
            return create_error_response("Image not found", 404)
        
        if not filepath.is_file():
            logger.warning(f"Path is not a file: {filepath}")
            return create_error_response("Invalid file path", 400)
        
        logger.info(f"Serving image file: {filepath}")
        return send_file(str(filepath))
    except Exception as e:
        logger.error(f"Error getting theme image {filename}: {str(e)}")
        return create_error_response(f"Error getting image: {str(e)}", 500)


@app.route("/api/settings/theme", methods=["GET"])
@require_permission('setting.view')
def get_current_theme():
    """Retrieve the currently active theme for the current user.
    
    Looks up the 'selected_theme' setting to determine which theme is
    currently active for the logged-in user, then returns the complete 
    theme object. This is used by the frontend to apply the active theme 
    on page load.
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with active theme object
            - 404: No theme selected in settings or selected theme not found
            - 500: Server error during retrieval
    
    Example:
        GET /api/settings/theme
        Response: {"id": 1, "name": "Dark", "settings": {...}, ...}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        
        # Get user's selected_theme setting using user-scoped query
        from utils import get_user_scoped_query
        setting = get_user_scoped_query(session, Setting, user_id).filter(Setting.key == 'selected_theme').first()
        if not setting:
            return create_error_response("No theme selected", 404)
        
        theme_id = int(setting.value)
        theme = _get_user_accessible_theme(session, user_id, theme_id)
        
        if not theme:
            return create_error_response("Selected theme not found", 404)
        
        return jsonify(theme.to_dict()), 200
    except Exception as e:
        logger.error(f"Error getting current theme: {str(e)}")
        return create_error_response(f"Error getting current theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/settings/theme", methods=["PUT"])
@require_permission('setting.edit')
def update_current_theme():
    """Set the active theme for the current user.
    
    Updates the 'selected_theme' setting to change which theme is currently
    active for the logged-in user. Validates that the specified theme exists 
    before updating. Creates the setting if it doesn't exist. This change 
    affects only the current user.
    
    Request Body:
        theme_id (int, required): ID of the theme to activate
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with confirmation message
            - 400: Missing theme_id in request body
            - 404: Theme with specified ID not found
            - 500: Server error during update
    
    Raises:
        Exception: Database errors during commit are caught and rolled back
    
    Example:
        PUT /api/settings/theme
        Body: {"theme_id": 5}
        Response: {"status": "success", "message": "Theme selection updated"}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        data = request.get_json()
        theme_id = data.get('theme_id')
        
        if not theme_id:
            return create_error_response("theme_id is required", 400)
        
        # Verify theme exists
        theme = _get_user_accessible_theme(session, user_id, theme_id)
        if not theme:
            return create_error_response("Theme not found", 404)
        
        # Update or create user's selected_theme setting
        from utils import get_user_scoped_query
        setting = get_user_scoped_query(session, Setting, user_id).filter(Setting.key == 'selected_theme').first()
        if setting:
            setting.value = str(theme_id)
        else:
            setting = Setting(
                key='selected_theme',
                value=str(theme_id),
                user_id=user_id
            )
            session.add(setting)
        
        session.commit()
        
        # Broadcast theme change to all connected clients
        broadcast_theme_event('theme_changed', {
            'theme_id': theme_id,
            'theme_name': theme.name
        })
        
        return create_success_response(message="Theme selection updated")
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating current theme: {str(e)}")
        return create_error_response(f"Error updating theme selection: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/settings/working-style", methods=["GET"])
@require_permission('setting.view')
def get_working_style():
    """Retrieve the current working style preference for the logged-in user.
    
    Looks up the 'working_style' setting to determine which working style
    is currently active for this user ('kanban' or 'agile').
    Returns the working style value with validation.
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with working_style value
            - 404: No working style setting found
            - 500: Server error during retrieval
    
    Example:
        GET /api/settings/working-style
        Response: {"success": true, "value": "kanban"}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        
        value = get_user_default_working_style(session, user_id)
        
        return jsonify({
            "success": True,
            "value": value
        }), 200
    except Exception as e:
        logger.error(f"Error getting working style: {str(e)}")
        return create_error_response(f"Error getting working style: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/settings/working-style", methods=["PUT"])
@require_permission('setting.edit')
def set_working_style():
    """Set the working style preference for the logged-in user.
    
    Updates the 'working_style' setting to change the working style preference
    for the current user. Valid values are 'kanban' (traditional kanban board)
    or 'agile' (board-level done tracking).
    Creates the setting if it doesn't exist.
    
    Request Body:
        value (str, required): 'kanban' or 'agile'
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with confirmation message
            - 400: Invalid or missing value
            - 500: Server error during update
    
    Example:
        PUT /api/settings/working-style
        Body: {"value": "agile"}
        Response: {"success": true, "message": "Working style updated"}
    """
    session = SessionLocal()
    try:
        user_id = g.user.id
        data = request.get_json()
        
        if not data or "value" not in data:
            return create_error_response("value is required", 400)
        
        working_style = normalize_working_style(data.get("value"))
        
        # Validate working_style value
        if working_style not in WORKING_STYLE_ALLOWED_VALUES:
            return create_error_response(
            f"Invalid working_style. Must be one of: {', '.join(WORKING_STYLE_ALLOWED_VALUES)}",
                400
            )
        
        # Update or create user's working_style setting
        from utils import get_user_scoped_query
        setting = get_user_scoped_query(session, Setting, user_id).filter(Setting.key == 'working_style').first()
        
        if setting:
            setting.value = json.dumps(working_style)
        else:
            setting = Setting(
                key='working_style',
              value=json.dumps(working_style),
                user_id=user_id
            )
            session.add(setting)
        
        session.commit()
        
        return jsonify({
            "success": True,
            "message": "Working style updated",
            "value": working_style
        }), 200
    except Exception as e:
        session.rollback()
        logger.error(f"Error setting working style: {str(e)}")
        return create_error_response(f"Error setting working style: {str(e)}", 500)
    finally:
        session.close()


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


