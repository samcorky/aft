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


