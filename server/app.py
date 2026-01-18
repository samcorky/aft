from flask import Flask, jsonify, request, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import logging
import json
import os
import time
import tempfile
import uuid
import threading
from pathlib import Path
from flasgger import Swagger
from database import SessionLocal, engine
from models import Board, BoardColumn, Card, Setting, ScheduledCard, ChecklistItem, Theme
from sqlalchemy import text, func
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
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "2026.1.0"

# Settings schema - defines allowed settings and their validation rules
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
        "description": "Unit for backup frequency (minutes, hours, days)",
        "validate": lambda value: isinstance(value, str) and value in ["minutes", "hours", "days"],
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
        "description": "Working style preference: 'kanban' for traditional kanban board or 'board_task_category' for board as task category with done status",
        "validate": lambda value: isinstance(value, str) and value in ["kanban", "board_task_category"],
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


def validate_safe_url(url):
    """Validate that a URL uses a safe protocol.
    
    Allows:
    - Relative paths starting with /
    - http:// and https:// protocols
    
    Rejects:
    - javascript:, data:, vbscript:, file:, and other dangerous protocols
    - URLs without proper structure
    
    Args:
        url: The URL string to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"
    
    url_lower = url.strip().lower()
    
    # Allow relative paths starting with /
    if url_lower.startswith('/'):
        return True, None
    
    # Allow http and https
    if url_lower.startswith('http://') or url_lower.startswith('https://'):
        return True, None
    
    # Reject all other protocols including dangerous ones
    dangerous_protocols = ['javascript:', 'data:', 'vbscript:', 'file:', 'about:', 'blob:']
    for protocol in dangerous_protocols:
        if url_lower.startswith(protocol):
            return False, f"URL protocol '{protocol}' is not allowed for security reasons"
    
    # Reject anything that doesn't match allowed patterns
    return False, "URL must be a relative path starting with / or use http:// or https:// protocol"


app = Flask(__name__)

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

<a href="/" style="text-decoration: none;">← Back to AFT Home</a>
        """,
        "version": "1.0.0",
    },
    "basePath": "/",
    "schemes": ["http", "https"],
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

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
    dangerous_patterns = [
        (r'\bGRANT\s+', 'GRANT statements (privilege manipulation)'),
        (r'\bCREATE\s+USER\b', 'CREATE USER statements'),
        (r'\bDROP\s+USER\b', 'DROP USER statements'),
        (r'\bALTER\s+USER\b', 'ALTER USER statements'),
        (r'\bINTO\s+OUTFILE\b', 'INTO OUTFILE (file system access)'),
        (r'\bLOAD\s+DATA\b', 'LOAD DATA (file system access)'),
        (r'\bCREATE\s+(PROCEDURE|FUNCTION)\b', 'Stored procedures/functions'),
        (r'\bUSE\s+`?\w+`?\s*', 'USE statements (cross-database operation)'),
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
            'checklist_items',
            'comments',
            'settings',
            'notifications',
            'scheduled_cards',
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


@app.route("/api/version")
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


@app.route("/api/broadcast-status")
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
                    'last_backup': scheduler.last_backup_time.isoformat() if scheduler.last_backup_time else None,
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
                'last_backup': scheduler.last_backup_time.isoformat() if scheduler.last_backup_time else None,
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


@app.route("/api/test")
def test_db():
    """Test database connection and schema.
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
            boards_count:
              type: integer
              example: 0
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
        # Test query
        board_count = db.query(Board).count()
        return jsonify(
            {
                "success": True,
                "message": "Connected to database",
                "boards_count": board_count,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/stats")
def get_stats():
    """Get database statistics.
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
        
        boards_count = db.query(Board).count()
        columns_count = db.query(BoardColumn).count()
        cards_count = db.query(Card).count()
        cards_archived_count = db.query(Card).filter(Card.archived.is_(True)).count()
        
        # Get checklist item counts
        checklist_items_total = db.query(ChecklistItem).count()
        checklist_items_checked = db.query(ChecklistItem).filter(ChecklistItem.checked.is_(True)).count()
        checklist_items_unchecked = db.query(ChecklistItem).filter(ChecklistItem.checked.is_(False)).count()

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

    try:
        # Check if file was uploaded
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Save uploaded file to temporary location
        temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".sql")
        temp_path = temp_file.name
        temp_file.close()
        file.save(temp_path)

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
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Invalid backup file: No Alembic version found",
                    }
                ),
                400,
            )

        # Get current Alembic version (what we would create on restore)
        db = SessionLocal()
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        current_version = row[0] if row else "unknown"
        db.close()

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

        # Drop all existing tables (including alembic_version)
        db = SessionLocal()
        from sqlalchemy import MetaData

        metadata = MetaData()
        metadata.reflect(bind=engine)
        metadata.drop_all(bind=engine)

        # Explicitly drop alembic_version table if it exists
        # (it's not in our models so metadata.reflect won't catch it)
        try:
            db.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Could not drop alembic_version table: {e}")

        db.close()

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
            raise Exception(f"MySQL restore failed: {result.stderr}")

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
            logger.info(
                f"Migrating database from {backup_version} to {current_version}"
            )
            upgrade_result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd="/app",
                capture_output=True,
                text=True,
            )

            if upgrade_result.returncode != 0:
                raise Exception(f"Alembic upgrade failed: {upgrade_result.stderr}")

            logger.info("Database restored and upgraded successfully")
            return jsonify(
                {
                    "success": True,
                    "message": f"Database restored and upgraded from version {backup_version} to {current_version}",
                }
            )
        else:
            logger.info("Database restored successfully")
            return jsonify(
                {"success": True, "message": "Database restored successfully"}
            )

    except Exception as e:
        logger.error(f"Error restoring database: {str(e)}")
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database/backups/list", methods=["GET"])
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
    try:
        from pathlib import Path
        import re
        import os
        import subprocess
        
        # Validate filename to prevent path traversal
        # Allow both auto_backup and manual backup filenames (aft_backup)
        if not re.match(r'^(auto_backup_|aft_backup_)\d{8}_\d{6}\.sql$', filename):
            return jsonify({"success": False, "message": "Invalid backup filename"}), 400
        
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
            return jsonify({"success": False, "message": "Backup file not found"}), 404
        
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
        
        # Get current Alembic version
        db = SessionLocal()
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        current_version = row[0] if row else "unknown"
        db.close()
        
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
        
        # Drop all existing tables
        db = SessionLocal()
        from sqlalchemy import MetaData
        
        metadata = MetaData()
        metadata.reflect(bind=engine)
        metadata.drop_all(bind=engine)
        
        # Drop alembic_version table
        try:
            db.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Could not drop alembic_version table: {e}")
        finally:
            db.close()
        
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
            raise Exception(f"MySQL restore failed: {result.stderr}")
        
        # Run migrations if needed
        if backup_version != current_version:
            logger.info(f"Migrating database from {backup_version} to {current_version}")
            upgrade_result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd="/app",
                capture_output=True,
                text=True,
            )
            
            if upgrade_result.returncode != 0:
                raise Exception(f"Alembic upgrade failed: {upgrade_result.stderr}")
            
            logger.info("Database restored and upgraded successfully")
            return jsonify({
                "success": True,
                "message": f"Database restored from {filename} and upgraded to version {current_version}"
            })
        else:
            logger.info(f"Database restored successfully from {filename}")
            return jsonify({
                "success": True,
                "message": f"Database restored successfully from {filename}"
            })
            
    except Exception as e:
        logger.error(f"Error restoring from automatic backup: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/database/backups/delete/<filename>", methods=["DELETE"])
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
        db = SessionLocal()

        # Drop all tables including alembic_version
        from sqlalchemy import MetaData

        metadata = MetaData()
        metadata.reflect(bind=engine)
        metadata.drop_all(bind=engine)
        db.close()

        # Run Alembic migrations to recreate database with proper version tracking
        import subprocess

        result = subprocess.run(
            ["alembic", "upgrade", "head"], cwd="/app", capture_output=True, text=True
        )

        if result.returncode != 0:
            raise Exception(f"Alembic migration failed: {result.stderr}")

        logger.info(
            "Database deleted and recreated successfully via Alembic migrations"
        )
        return jsonify({"success": True, "message": "Database deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting database: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/schema", methods=["GET"])
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
def get_setting(key):
    """Get a setting value by key with validation.
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
        setting = db.query(Setting).filter(Setting.key == key).first()

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
def set_setting(key):
    """Create or update a setting (upsert).
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

        # Additional validation for default_board: verify board exists
        if key == "default_board" and data["value"] is not None:
            db_check = SessionLocal()
            try:
                board_exists = (
                    db_check.query(Board).filter(Board.id == data["value"]).first()
                )
                if not board_exists:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": f"Board with ID {data['value']} does not exist",
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
            setting = db.query(Setting).filter(Setting.key == key).first()

            if setting:
                # Update existing
                setting.value = value
                message = "Setting updated successfully"
            else:
                # Create new
                setting = Setting(key=key, value=value)
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
        for key in keys:
            setting = db.query(Setting).filter(Setting.key == key).first()
            if setting:
                # Try to parse JSON, otherwise use raw value
                try:
                    config[key.replace("backup_", "")] = json.loads(setting.value)
                except (json.JSONDecodeError, TypeError):
                    config[key.replace("backup_", "")] = setting.value
            else:
                # Default values
                defaults = {
                    "backup_enabled": False,
                    "backup_frequency_value": 1,
                    "backup_frequency_unit": "days",
                    "backup_start_time": "00:00",
                    "backup_retention_count": 7,
                    "backup_minimum_free_space_mb": 100,
                    "backup_last_run": None
                }
                config[key.replace("backup_", "")] = defaults.get(key)
        
        return jsonify({"success": True, "config": config})
    except Exception as e:
        logger.error(f"Error getting backup config: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/settings/backup/config", methods=["PUT"])
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
        
        if errors:
            return jsonify({"success": False, "message": "; ".join(errors)}), 400
        
        # Additional validation: Cannot enable backups if required settings are invalid or missing
        if data.get("enabled") is True:
            # Get current settings for fields not being updated
            current_settings = {}
            for field, key in mapping.items():
                if field not in data:
                    setting = db.query(Setting).filter(Setting.key == key).first()
                    if setting:
                        try:
                            current_settings[field] = json.loads(setting.value)
                        except (json.JSONDecodeError, TypeError):
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
            
            if required_errors:
                return jsonify({
                    "success": False,
                    "message": "Cannot enable backups with invalid settings: " + "; ".join(required_errors)
                }), 400
        
        # Update settings
        for field, key in mapping.items():
            if field in data:
                value = json.dumps(data[field])
                setting = db.query(Setting).filter(Setting.key == key).first()
                
                if setting:
                    setting.value = value
                else:
                    setting = Setting(key=key, value=value)
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
        
        # Update setting
        setting = db.query(Setting).filter(Setting.key == "housekeeping_enabled").first()
        value = json.dumps(enabled)
        
        if setting:
            setting.value = value
        else:
            setting = Setting(key="housekeeping_enabled", value=value)
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
        
        # Get enabled setting
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == "card_scheduler_enabled").first()
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
        
        # Update setting
        setting = db.query(Setting).filter(Setting.key == "card_scheduler_enabled").first()
        value = json.dumps(enabled)
        
        if setting:
            setting.value = value
        else:
            setting = Setting(key="card_scheduler_enabled", value=value)
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
def get_boards():
    """Get all boards.
    ---
    tags:
      - Boards
    responses:
      200:
        description: List of all boards
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
        boards = db.query(Board).all()
        return jsonify(
            {
                "success": True,
                "boards": [
                    {"id": b.id, "name": b.name, "description": b.description}
                    for b in boards
                ],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/boards", methods=["POST"])
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
        board = Board(name=name, description=description)
        db.add(board)
        db.commit()
        db.refresh(board)

        result = {"id": board.id, "name": board.name, "description": board.description}
        return create_success_response({"board": result}, status_code=201)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating board: {str(e)}")
        return create_error_response("Failed to create board", 500)
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>/cards/scheduled", methods=["GET"])
def get_board_scheduled_cards(board_id):
    """Get all scheduled cards for a board with nested structure (board -> columns -> cards).
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
      404:
        description: Board not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import BoardColumn, Card
        
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
        
        # Build nested structure with scheduled cards
        result = {"id": board.id, "name": board.name, "columns": []}

        for column in columns:
            # Get only scheduled template cards for this column
            cards = (
                db.query(Card)
                .filter(Card.column_id == column.id)
                .filter(Card.scheduled.is_(True))
                .order_by(Card.order)
                .all()
            )

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
                    "checklist_items": [
                        {
                            "id": item.id,
                            "card_id": item.card_id,
                            "name": item.name,
                            "checked": item.checked,
                            "order": item.order
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
                "cards": cards_data,
            }
            result["columns"].append(column_data)

        return jsonify({"success": True, "board": result})
        
    except Exception as e:
        logger.error(f"Error getting scheduled cards for board {board_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to get scheduled cards"}), 500
    finally:
        db.close()


@app.route("/api/boards/<int:board_id>", methods=["DELETE"])
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
        board = db.query(Board).filter(Board.id == board_id).first()

        if not board:
            return jsonify({"success": False, "message": "Board not found"}), 404

        # Check if this board is set as default_board
        default_board_setting = (
            db.query(Setting).filter(Setting.key == "default_board").first()
        )
        if default_board_setting:
            try:
                default_board_id = json.loads(default_board_setting.value)
                if default_board_id == board_id:
                    # Reset to null since we're deleting the default board
                    default_board_setting.value = "null"
                    logger.info(
                        f"Reset default_board setting because board {board_id} was deleted"
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

        db.commit()
        db.refresh(board)

        result = {"id": board.id, "name": board.name, "description": board.description}
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
def get_board_columns(board_id):
    """Get all columns for a specific board.
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

        column = BoardColumn(board_id=board_id, name=name, order=order)
        db.add(column)
        db.commit()
        db.refresh(column)

        result = {
            "id": column.id,
            "board_id": column.board_id,
            "name": column.name,
            "order": column.order,
        }

        return create_success_response({"column": result}, status_code=201)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating column for board {board_id}: {str(e)}")
        return create_error_response("Failed to create column", 500)
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>", methods=["DELETE"])
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

        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()

        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404

        db.delete(column)
        db.commit()

        return jsonify({"success": True, "message": "Column deleted successfully"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/columns/<int:column_id>", methods=["PATCH"])
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

        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()

        if not column:
            return create_error_response("Column not found", 404)

        old_order = column.order
        board_id = column.board_id

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

        db.commit()
        db.refresh(column)
        result = {
            "id": column.id,
            "board_id": column.board_id,
            "name": column.name,
            "order": column.order,
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

        # Get archived filter from query parameter (default to false - unarchived only)
        archived_param = request.args.get('archived', 'false').lower()

        # Always filter out scheduled template cards (scheduled=True) from task views
        cards_query = db.query(Card).filter(Card.column_id == column_id).filter(Card.scheduled.is_(False))
        
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
        return jsonify(
            {
                "success": True,
                "cards": cards_data
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/boards/<int:board_id>/cards", methods=["GET"])
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

        # Get archived filter from query parameter (default to false - unarchived only)
        archived_param = request.args.get('archived', 'false').lower()

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

        for column in columns:
            # Get cards for this column with archived filter
            # Always filter out scheduled template cards (scheduled=True) from task views
            cards_query = db.query(Card).filter(Card.column_id == column.id).filter(Card.scheduled.is_(False))
            
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
                    "checklist_items": [
                        {
                            "id": item.id,
                            "card_id": item.card_id,
                            "name": item.name,
                            "checked": item.checked,
                            "order": item.order
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
                "cards": cards_data,
            }
            result["columns"].append(column_data)

        db.close()
        return jsonify({"success": True, "board": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/columns/<int:column_id>/cards", methods=["POST"])
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

        # Verify column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            return create_error_response("Column not found", 404)

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
        card = Card(
            column_id=column_id, 
            title=title, 
            description=description, 
            order=order,
            scheduled=scheduled,
            schedule=schedule
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
            "done": card.done
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

        # Verify column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404

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

        # Verify target column exists
        target_column = db.query(BoardColumn).filter(BoardColumn.id == target_column_id).first()
        if not target_column:
            return jsonify({"success": False, "message": "Target column not found"}), 404

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
def get_card(card_id):
    """Get a single card with its checklist items.
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
      404:
        description: Card not found
    """
    db = SessionLocal()
    try:
        from models import Card
        
        card = db.query(Card).filter(Card.id == card_id).first()
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
            "checklist_items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "checked": item.checked,
                    "order": item.order
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

        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            return create_error_response("Card not found", 404)

        old_column_id = card.column_id
        old_order = card.order

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

        # Update archived status if provided
        if "archived" in data:
            archived = data["archived"]
            if not isinstance(archived, bool):
                return create_error_response("Archived must be a boolean", 400)
            card.archived = archived

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

        db.commit()
        db.refresh(card)

        result = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order,
            "done": card.done,
            "archived": card.archived
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

        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            db.close()
            return jsonify({"success": False, "message": "Card not found"}), 404

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


@app.route("/api/cards/<int:card_id>/archive", methods=["PATCH"])
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
        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404

        board_id = card.column.board_id if card.column else None
        card.archived = True
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
            "done": card.done
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
        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404

        # Get the card's current order and column
        card_order = card.order
        column_id = card.column_id

        # Unarchive the card first
        card.archived = False

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
            "done": card.done
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
def get_card_done_status(card_id):
    """Get the done status of a card.
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
      404:
        description: Card not found
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        card = db.query(Card).filter(Card.id == card_id).first()
        
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
        
        card = db.query(Card).filter(Card.id == card_id).first()
        
        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404
        
        board_id = card.column.board_id if card.column else None
        card.done = done_status
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


@app.route("/api/cards/batch/archive", methods=["POST"])
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

        data = request.get_json()
        card_ids = data.get("card_ids", [])

        if not card_ids:
            return jsonify({"success": False, "message": "card_ids is required"}), 400

        if not isinstance(card_ids, list):
            return jsonify({"success": False, "message": "card_ids must be an array"}), 400

        # Archive all cards with the given IDs
        archived_count = (
            db.query(Card)
            .filter(Card.id.in_(card_ids))
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

        data = request.get_json()
        card_ids = data.get("card_ids", [])

        if not card_ids:
            return jsonify({"success": False, "message": "card_ids is required"}), 400

        if not isinstance(card_ids, list):
            return jsonify({"success": False, "message": "card_ids must be an array"}), 400

        # Get all cards to unarchive with their column and order information
        cards_to_unarchive = (
            db.query(Card)
            .filter(Card.id.in_(card_ids))
            .order_by(Card.column_id, Card.order)
            .all()
        )
        
        if not cards_to_unarchive:
            return jsonify({
                "success": True,
                "message": "No cards found to unarchive",
                "unarchived_count": 0
            }), 200
        
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


# Scheduled Cards API endpoints
@app.route("/api/columns/<int:column_id>/cards/scheduled", methods=["GET"])
def get_scheduled_cards(column_id):
    """Get all scheduled template cards for a specific column.
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
      500:
        description: Server error
    """
    try:
        db = SessionLocal()
        
        # Get only scheduled template cards (scheduled=True)
        cards = (
            db.query(Card)
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
            
            # Handle keep_source_card parameter
            keep_source_card = data.get('keep_source_card', True)
            if keep_source_card:
                # Update ORIGINAL card's schedule reference (but keep scheduled=False so it stays visible)
                card.schedule = schedule.id
            else:
                # Delete the original card
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
        
        # Clear schedule reference from all cards that reference this schedule
        # (including the original source card and any spawned cards)
        created_cards = db.query(Card).filter(Card.schedule == schedule_id).all()
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
        checklist_item = ChecklistItem(
            card_id=card_id,
            name=name,
            checked=checked,
            order=order
        )

        db.add(checklist_item)
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
                    'order': checklist_item.order
                }
            }, column.board_id)

        return jsonify({
            "success": True,
            "checklist_item": {
                "id": checklist_item.id,
                "card_id": checklist_item.card_id,
                "name": checklist_item.name,
                "checked": checklist_item.checked,
                "order": checklist_item.order
            }
        }), 201

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating checklist item for card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/checklist-items/<int:item_id>", methods=["PATCH"])
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

        # Update checked if provided
        if "checked" in data:
            checked = data["checked"]
            if not isinstance(checked, bool):
                return create_error_response("Checked must be a boolean", 400)
            checklist_item.checked = checked

        # Update order if provided
        if "order" in data:
            order = data["order"]
            is_valid, error = validate_integer(order, "Order", allow_none=False, min_value=0)
            if not is_valid:
                return create_error_response(error, 400)
            checklist_item.order = order

        db.commit()
        db.refresh(checklist_item)

        result = {
            "id": checklist_item.id,
            "card_id": checklist_item.card_id,
            "name": checklist_item.name,
            "checked": checklist_item.checked,
            "order": checklist_item.order
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
        from models import ChecklistItem

        checklist_item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()

        if not checklist_item:
            return create_error_response("Checklist item not found", 404)

        db.delete(checklist_item)
        db.commit()

        return jsonify({"success": True, "message": "Checklist item deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting checklist item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/cards/<int:card_id>/comments", methods=["GET"])
def get_card_comments(card_id):
    """Get all comments for a card.
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
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Comment

        comments = (
            db.query(Comment)
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
        from models import Comment

        comment = db.query(Comment).filter(Comment.id == comment_id).first()

        if not comment:
            return create_error_response("Comment not found", 404)

        db.delete(comment)
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
def get_notifications():
    """Get all notifications.
    ---
    tags:
      - Notifications
    responses:
      200:
        description: List of all notifications (newest first)
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
      500:
        description: Server error
    """
    db = SessionLocal()
    try:
        from models import Notification

        notifications = (
            db.query(Notification)
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
            action_url=action_url
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

        notification = db.query(Notification).filter(Notification.id == notification_id).first()

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

        notification = db.query(Notification).filter(Notification.id == notification_id).first()

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

        notification = db.query(Notification).filter(Notification.id == notification_id).first()

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

        # Update all unread notifications
        result = db.query(Notification).filter(Notification.unread.is_(True)).update({"unread": False})
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

        # Delete all notifications
        result = db.query(Notification).delete()
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
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with JSON response for API endpoints."""
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": "Endpoint not found"}), 404
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
    """Remove all scheduler lock files on application startup.
    
    This ensures clean state after container restarts where lock files
    from previous containers may persist but are no longer valid.
    Called once before any scheduler initialization.
    """
    from pathlib import Path
    import tempfile
    
    temp_dir = Path(tempfile.gettempdir())
    lock_files = [
        temp_dir / "aft_backup_scheduler.lock",
        temp_dir / "aft_card_scheduler.lock",
        temp_dir / "aft_housekeeping_scheduler.lock",
    ]
    
    for lock_file in lock_files:
        try:
            if lock_file.exists():
                lock_file.unlink()
                logger.info(f"Cleaned up stale lock file: {lock_file}")
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

# Only initialize schedulers in the first worker to start
# Use a combination of lock file AND worker tracking
init_lock_file = Path(tempfile.gettempdir()) / "aft_scheduler_init.lock"

# Clean up stale init lock files from previous container instances
# This must happen BEFORE trying to acquire the lock
# If the init lock is stale (from a dead container process), we want to remove it
# so this container's worker can acquire it and initialize schedulers
try:
    if init_lock_file.exists():
        # Check if the lock file is stale (older than 5 minutes)
        # In a container, if no worker has refreshed the lock in 5 minutes, assume the container died
        from datetime import datetime
        lock_age = (datetime.now() - datetime.fromtimestamp(init_lock_file.stat().st_mtime)).total_seconds()
        if lock_age > 300:  # 5 minutes
            logger.info(f"Init lock file is stale ({lock_age}s old), removing it")
            init_lock_file.unlink()
except Exception as e:
    logger.warning(f"Failed to clean stale init lock file: {e}")

should_init = False

try:
    # Try to create lock file exclusively (fails if already exists)
    fd = os.open(init_lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    should_init = True
    logger.info(f"Worker PID {os.getpid()}: Acquired scheduler init lock")
except FileExistsError:
    # Lock already exists - another worker is initializing or already initialized
    logger.info(f"Worker PID {os.getpid()}: Init lock exists, skipping scheduler initialization")
    should_init = False

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

@app.route("/api/themes", methods=["GET"])
def get_themes():
    """Retrieve all themes from the database.
    
    Fetches and returns a list of all available themes, including both
    system themes and user-created custom themes. Each theme includes
    its ID, name, settings, background image, and system theme flag.
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with list of theme objects
            - 500: Server error during database query
    
    Example:
        GET /api/themes
        Response: [{"id": 1, "name": "Dark", "settings": {...}, ...}, ...]
    """
    session = SessionLocal()
    try:
        themes = session.query(Theme).all()
        return jsonify([theme.to_dict() for theme in themes]), 200
    except Exception as e:
        logger.error(f"Error getting themes: {str(e)}")
        return create_error_response(f"Error getting themes: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>", methods=["GET"])
def get_theme(theme_id):
    """Retrieve a specific theme by its unique ID.
    
    Fetches detailed information about a single theme including its
    name, color settings, background image, and whether it's a system
    theme. Useful for loading a theme for preview or editing.
    
    Args:
        theme_id (int): The unique identifier of the theme to retrieve
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with theme object
            - 404: Theme with specified ID not found
            - 500: Server error during database query
    
    Example:
        GET /api/themes/5
        Response: {"id": 5, "name": "Custom Blue", "settings": {...}, ...}
    """
    session = SessionLocal()
    try:
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
        if not theme:
            return create_error_response("Theme not found", 404)
        return jsonify(theme.to_dict()), 200
    except Exception as e:
        logger.error(f"Error getting theme {theme_id}: {str(e)}")
        return create_error_response(f"Error getting theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/themes/<int:theme_id>", methods=["PUT"])
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
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
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
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
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
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
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
        data = request.get_json()
        source_id = data.get('source_theme_id')
        new_name = data.get('new_name')
        
        if not source_id or not new_name:
            return create_error_response("source_theme_id and new_name are required", 400)
        
        # Check if source theme exists
        source_theme = session.query(Theme).filter(Theme.id == source_id).first()
        if not source_theme:
            return create_error_response("Source theme not found", 404)
        
        # Check if new name is unique
        existing = session.query(Theme).filter(Theme.name == new_name).first()
        if existing:
            return create_error_response("Theme name already exists", 400)
        
        # Create new theme as copy
        new_theme = Theme(
            name=new_name,
            settings=source_theme.settings,
            background_image=source_theme.background_image,
            system_theme=False  # Copied themes are never system themes
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
            system_theme=False
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
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
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
def get_current_theme():
    """Retrieve the currently active theme for the application.
    
    Looks up the 'selected_theme' setting to determine which theme is
    currently active, then returns the complete theme object. This is
    used by the frontend to apply the active theme on page load.
    
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
        # Get selected_theme setting
        setting = session.query(Setting).filter(Setting.key == 'selected_theme').first()
        if not setting:
            return create_error_response("No theme selected", 404)
        
        theme_id = int(setting.value)
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
        
        if not theme:
            return create_error_response("Selected theme not found", 404)
        
        return jsonify(theme.to_dict()), 200
    except Exception as e:
        logger.error(f"Error getting current theme: {str(e)}")
        return create_error_response(f"Error getting current theme: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/settings/theme", methods=["PUT"])
def update_current_theme():
    """Set the active theme for the application.
    
    Updates the 'selected_theme' setting to change which theme is currently
    active. Validates that the specified theme exists before updating.
    Creates the setting if it doesn't exist. This change affects all users
    of the application.
    
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
        data = request.get_json()
        theme_id = data.get('theme_id')
        
        if not theme_id:
            return create_error_response("theme_id is required", 400)
        
        # Verify theme exists
        theme = session.query(Theme).filter(Theme.id == theme_id).first()
        if not theme:
            return create_error_response("Theme not found", 404)
        
        # Update or create selected_theme setting
        setting = session.query(Setting).filter(Setting.key == 'selected_theme').first()
        if setting:
            setting.value = str(theme_id)
        else:
            setting = Setting()
            setting.key = 'selected_theme'
            setting.value = str(theme_id)
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
def get_working_style():
    """Retrieve the current working style preference.
    
    Looks up the 'working_style' setting to determine which working style
    is currently active ('kanban' or 'board_task_category'). Returns the
    working style value with validation.
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with working_style value
            - 404: No working style setting found
            - 500: Server error during retrieval
    
    Example:
        GET /api/settings/working-style
        Response: {"success": true, "key": "working_style", "value": "kanban"}
    """
    session = SessionLocal()
    try:
        setting = session.query(Setting).filter(Setting.key == 'working_style').first()
        
        if not setting:
            return create_error_response("Working style setting not found", 404)
        
        # Parse the JSON-encoded value
        try:
            import json
            value = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            value = setting.value
        
        return jsonify({
            "success": True,
            "key": "working_style",
            "value": value
        }), 200
    except Exception as e:
        logger.error(f"Error getting working style: {str(e)}")
        return create_error_response(f"Error getting working style: {str(e)}", 500)
    finally:
        session.close()


@app.route("/api/settings/working-style", methods=["PUT"])
def set_working_style():
    """Set the working style preference.
    
    Updates the 'working_style' setting to change the working style preference.
    Valid values are 'kanban' (traditional kanban board) or 'board_task_category'
    (board as task category with done status). Creates the setting if it doesn't exist.
    
    Request Body:
        working_style (str, required): 'kanban' or 'board_task_category'
    
    Returns:
        tuple: (JSON response, HTTP status code)
            - 200: Success with confirmation message
            - 400: Invalid or missing working_style value
            - 500: Server error during update
    
    Example:
        PUT /api/settings/working-style
        Body: {"working_style": "board_task_category"}
        Response: {"success": true, "message": "Working style updated"}
    """
    session = SessionLocal()
    try:
        data = request.get_json()
        
        if not data or "working_style" not in data:
            return create_error_response("working_style is required", 400)
        
        working_style = data.get("working_style")
        
        # Validate working_style value
        if working_style not in ["kanban", "board_task_category"]:
            return create_error_response(
                "Invalid working_style. Must be 'kanban' or 'board_task_category'",
                400
            )
        
        # Update or create working_style setting
        setting = session.query(Setting).filter(Setting.key == 'working_style').first()
        
        if setting:
            setting.value = f'"{working_style}"'  # JSON-encode the value
        else:
            setting = Setting()
            setting.key = 'working_style'
            setting.value = f'"{working_style}"'  # JSON-encode the value
            session.add(setting)
        
        session.commit()
        
        return jsonify({
            "success": True,
            "message": "Working style updated",
            "working_style": working_style
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

@socketio.on('connect')
def handle_connect():
    """Handle client connection to WebSocket.
    
    When REJECT_SOCKETIO_CONNECTIONS is True, immediately reject connections
    to simulate WebSocket failure for testing purposes.
    """
    if REJECT_SOCKETIO_CONNECTIONS:
        logger.info(f"Testing: Rejecting Socket.IO connection from {request.sid}")
        return False  # Reject the connection
    
    logger.info(f"Client connected: {request.sid}")
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
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        join_room(room)
        logger.info(f"Client {request.sid} joined board {board_id}")
        emit('room_joined', {'board_id': board_id, 'message': f'Joined board {board_id}'})


@socketio.on('leave_board')
def on_leave_board(data):
    """Leave a board's WebSocket room.
    
    Args:
        data: Dictionary containing 'board_id'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        leave_room(room)
        logger.info(f"Client {request.sid} left board {board_id}")


@socketio.on('card_moved')
def broadcast_card_moved(data):
    """Broadcast when a card is moved to different position or column.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'from_column_id', 
              'to_column_id', 'from_index', 'to_index'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('card_moved', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted card move for board {board_id}")


@socketio.on('card_updated')
def broadcast_card_updated(data):
    """Broadcast when a card's content or metadata is updated.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', and updated fields
              (title, description, color, etc.)
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('card_updated', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted card update for board {board_id}, card {data.get('card_id')}")


@socketio.on('card_created')
def broadcast_card_created(data):
    """Broadcast when a new card is created.
    
    Args:
        data: Dictionary containing 'board_id', 'column_id', 'card_id', 'card_data'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('card_created', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted card creation for board {board_id}")


@socketio.on('card_deleted')
def broadcast_card_deleted(data):
    """Broadcast when a card is deleted.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'column_id'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('card_deleted', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted card deletion for board {board_id}, card {data.get('card_id')}")


@socketio.on('column_reordered')
def broadcast_column_reordered(data):
    """Broadcast when columns are reordered.
    
    Args:
        data: Dictionary containing 'board_id', 'column_order' (list of column IDs)
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('column_reordered', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted column reorder for board {board_id}")


@socketio.on('checklist_item_added')
def broadcast_checklist_item_added(data):
    """Broadcast when a checklist item is added to a card.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'item_id', 'item_data'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('checklist_item_added', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted checklist item addition for board {board_id}, card {data.get('card_id')}")


@socketio.on('checklist_item_updated')
def broadcast_checklist_item_updated(data):
    """Broadcast when a checklist item is updated.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'item_id', 'updated_fields'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('checklist_item_updated', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted checklist item update for board {board_id}, card {data.get('card_id')}")


@socketio.on('checklist_item_deleted')
def broadcast_checklist_item_deleted(data):
    """Broadcast when a checklist item is deleted.
    
    Args:
        data: Dictionary containing 'board_id', 'card_id', 'item_id'
    """
    board_id = data.get('board_id')
    if board_id:
        room = f'board_{board_id}'
        emit('checklist_item_deleted', data, room=room, skip_sid=request.sid)
        logger.info(f"Broadcasted checklist item deletion for board {board_id}, card {data.get('card_id')}")


# ============================================================================
# WebSocket Handlers for Theme Updates
# ============================================================================

@socketio.on('join_theme')
def on_join_theme():
    """Handle client joining the theme room to receive theme updates."""
    join_room('theme')
    logger.info(f"✓ Client {request.sid} joined theme room")
    
    # Send current theme to the new client
    try:
        session = SessionLocal()
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
        session.close()
    except Exception as e:
        logger.error(f"✗ Error sending current theme to client: {str(e)}")


@socketio.on('leave_theme')
def on_leave_theme():
    """Handle client leaving the theme room."""
    leave_room('theme')
    logger.info(f"Client {request.sid} left theme room")


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)


