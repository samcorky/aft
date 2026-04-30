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
from board_routes import (
    board_bp,
    configure_board_routes,
    _apply_assignee_card_filters,
  _get_board_eligible_assignee_ids,
    _get_board_assignee_users,
    _parse_assignee_ids_query_param,
    _user_summary,
)
from health_routes import health_bp, configure_health_routes
from theme_routes import theme_bp, configure_theme_routes
from notification_routes import notification_bp
from settings_routes import settings_bp, configure_settings_routes
from backup_routes import backup_bp, configure_backup_routes
from column_routes import column_bp, configure_column_routes
from card_routes import card_bp, configure_card_routes
from schedule_routes import schedule_bp, configure_schedule_routes
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
configure_board_routes(APP_VERSION)
configure_column_routes(broadcast_event)
configure_card_routes(broadcast_event)
configure_schedule_routes(broadcast_event)


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
app.register_blueprint(board_bp)
app.register_blueprint(column_bp)
app.register_blueprint(card_bp)
app.register_blueprint(schedule_bp)

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


# Board routes moved to board_routes.py
# Helper functions (_user_summary, _parse_assignee_ids_query_param, etc.) moved to board_routes.py

# Column routes moved to column_routes.py

# Card routes moved to card_routes.py

# Schedule, checklist, and comment routes moved to schedule_routes.py


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


