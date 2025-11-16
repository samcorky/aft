from flask import Flask, jsonify, request
import logging
import json
from flasgger import Swagger
from database import SessionLocal, engine
from models import Board, BoardColumn, Card, Setting
from sqlalchemy import text
from utils import (
    validate_string_length,
    validate_integer,
    sanitize_string,
    create_error_response,
    create_success_response,
    MAX_TITLE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "1.0.0"

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
        boards_count = db.query(Board).count()
        columns_count = db.query(BoardColumn).count()
        cards_count = db.query(Card).count()

        return jsonify(
            {
                "success": True,
                "boards_count": boards_count,
                "columns_count": columns_count,
                "cards_count": cards_count,
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
        data = request.get_json()
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
        data = request.get_json()
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
        data = request.get_json()
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
    """Create a new column for a board.
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
        data = request.get_json()
        if not data or "name" not in data:
            return jsonify({"success": False, "message": "Name is required"}), 400

        # Verify board exists
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            return jsonify({"success": False, "message": "Board not found"}), 404

        # If order not specified, add to end
        from models import BoardColumn

        if "order" not in data:
            max_order = (
                db.query(BoardColumn).filter(BoardColumn.board_id == board_id).count()
            )
            order = max_order
        else:
            order = data["order"]

        column = BoardColumn(board_id=board_id, name=data["name"], order=order)
        db.add(column)
        db.commit()
        db.refresh(column)
        result = {
            "id": column.id,
            "board_id": column.board_id,
            "name": column.name,
            "order": column.order,
        }

        return jsonify({"success": True, "column": result}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
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
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400

        from models import BoardColumn

        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()

        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404

        old_order = column.order
        board_id = column.board_id

        # Update name if provided
        if "name" in data:
            column.name = data["name"]

        # Handle order change if provided
        if "order" in data:
            new_order = data["order"]

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

        cards = (
            db.query(Card)
            .filter(Card.column_id == column_id)
            .order_by(Card.order)
            .all()
        )
        db.close()
        return jsonify(
            {
                "success": True,
                "cards": [
                    {
                        "id": c.id,
                        "column_id": c.column_id,
                        "title": c.title,
                        "description": c.description,
                        "order": c.order,
                    }
                    for c in cards
                ],
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
            # Get cards for this column
            cards = (
                db.query(Card)
                .filter(Card.column_id == column.id)
                .order_by(Card.order)
                .all()
            )

            column_data = {
                "id": column.id,
                "name": column.name,
                "order": column.order,
                "cards": [
                    {
                        "id": card.id,
                        "title": card.title,
                        "description": card.description,
                        "order": card.order,
                    }
                    for card in cards
                ],
            }
            result["columns"].append(column_data)

        db.close()
        return jsonify({"success": True, "board": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/columns/<int:column_id>/cards", methods=["POST"])
def create_card(column_id):
    """Create a new card in a column.
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
        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"success": False, "message": "Title is required"}), 400

        from models import BoardColumn, Card

        # Verify column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            return jsonify({"success": False, "message": "Column not found"}), 404

        # Get order from request or use max order
        if "order" in data:
            order = data["order"]
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
            column_id=column_id,
            title=data["title"],
            description=data.get("description", ""),
            order=order,
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

        return jsonify({"success": True, "card": result}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400

        db = SessionLocal()
        from models import Card, BoardColumn

        card = db.query(Card).filter(Card.id == card_id).first()

        if not card:
            db.close()
            return jsonify({"success": False, "message": "Card not found"}), 404

        old_column_id = card.column_id
        old_order = card.order

        # Update title and description if provided
        if "title" in data:
            card.title = data["title"]
        if "description" in data:
            card.description = data["description"]

        # Handle column and order changes
        if "column_id" in data or "order" in data:
            new_column_id = data.get("column_id", card.column_id)
            new_order = data.get("order", card.order)

            # Verify new column exists if changing columns
            if new_column_id != old_column_id:
                column = (
                    db.query(BoardColumn)
                    .filter(BoardColumn.id == new_column_id)
                    .first()
                )
                if not column:
                    db.close()
                    return (
                        jsonify(
                            {"success": False, "message": "Target column not found"}
                        ),
                        404,
                    )

            # If moving to a different column
            if new_column_id != old_column_id:
                # Decrement order of cards after old position in old column
                db.query(Card).filter(
                    Card.column_id == old_column_id, Card.order > old_order
                ).update({Card.order: Card.order - 1})

                # Increment order of cards >= new position in new column
                db.query(Card).filter(
                    Card.column_id == new_column_id, Card.order >= new_order
                ).update({Card.order: Card.order + 1})

                card.column_id = new_column_id
                card.order = new_order

            # If reordering within the same column
            elif new_order != old_order:
                if new_order < old_order:
                    # Moving up: increment cards between new and old position
                    db.query(Card).filter(
                        Card.column_id == old_column_id,
                        Card.order >= new_order,
                        Card.order < old_order,
                    ).update({Card.order: Card.order + 1})
                else:
                    # Moving down: decrement cards between old and new position
                    db.query(Card).filter(
                        Card.column_id == old_column_id,
                        Card.order > old_order,
                        Card.order <= new_order,
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
        db.close()

        return jsonify({"success": True, "card": result}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
