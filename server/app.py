from flask import Flask, jsonify, request
import logging
import json
from flasgger import Swagger
from database import SessionLocal, engine
from models import Board, BoardColumn, Card, Setting
from sqlalchemy import text, func
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
APP_VERSION = "1.1.2"

# Settings schema - defines allowed settings and their validation rules
SETTINGS_SCHEMA = {
    "default_board": {
        "type": "integer",
        "nullable": True,
        "description": "ID of the board to load by default on application startup",
        "validate": lambda value: value is None
        or (isinstance(value, int) and not isinstance(value, bool) and value > 0),
    }
}


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


app = Flask(__name__)

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


# Request size limit (10MB)
MAX_REQUEST_SIZE = 10 * 1024 * 1024


@app.before_request
def validate_request():
    """Validate incoming requests for security.

    This runs before every request to:
    1. Check request size to prevent DoS attacks
    2. Validate Content-Type for JSON requests
    """
    # Check request size
    if request.content_length and request.content_length > MAX_REQUEST_SIZE:
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
        return jsonify({"success": False, "message": str(e)}), 500


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
        if backup_version > current_version:
            os.unlink(temp_path)
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Backup is from a newer database version ({backup_version}). Please update the application to at least database version {backup_version} before restoring.",
                    }
                ),
                400,
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

        # If backup version is older than current, run migrations to upgrade
        if backup_version < current_version:
            logger.info(
                f"Upgrading database from {backup_version} to {current_version}"
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

        cards_query = db.query(Card).filter(Card.column_id == column_id)
        
        # Apply archived filter
        if archived_param == 'true':
            cards_query = cards_query.filter(Card.archived == True)
        elif archived_param == 'false':
            cards_query = cards_query.filter(Card.archived == False)
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
            cards_query = db.query(Card).filter(Card.column_id == column.id)
            
            # Apply archived filter
            if archived_param == 'true':
                cards_query = cards_query.filter(Card.archived == True)
            elif archived_param == 'false':
                cards_query = cards_query.filter(Card.archived == False)
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

        # Create card
        card = Card(
            column_id=column_id, title=title, description=description, order=order
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
        }

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
        }

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
        from models import Card

        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            db.close()
            return jsonify({"success": False, "message": "Card not found"}), 404

        db.delete(card)
        db.commit()
        db.close()

        return jsonify({"success": True, "message": "Card deleted successfully"}), 200
    except Exception as e:
        db.rollback()
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
        from models import Card

        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            return jsonify({"success": False, "message": "Card not found"}), 404

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
            "archived": card.archived
        }

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
        from models import Card

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
            "archived": card.archived
        }

        return jsonify({"success": True, "message": "Card unarchived successfully", "card": card_dict}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Error unarchiving card {card_id}: {str(e)}")
        return jsonify({"success": False, "message": "Failed to unarchive card"}), 500
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

        from models import Card, ChecklistItem

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

        return jsonify({
            "success": True,
            "checklist_item": {
                "id": checklist_item.id,
                "card_id": checklist_item.card_id,
                "name": checklist_item.name,
                "checked": checklist_item.checked,
                "order": checklist_item.order
            }
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
