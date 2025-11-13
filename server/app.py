from flask import Flask, jsonify
import logging
from flasgger import Swagger
from database import SessionLocal
from models import Board

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure Swagger
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/api/apispec.json',
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "static_url_path": "/api/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "AFT API",
        "description": """
API documentation for AFT application

[← Back to AFT Home](/)
        """,
        "version": "1.0.0"
    },
    "basePath": "/",
    "schemes": ["http", "https"]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)


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
    try:
        db = SessionLocal()
        # Test query
        board_count = db.query(Board).count()
        db.close()
        return jsonify({
            "success": True, 
            "message": "Connected to database",
            "boards_count": board_count
        })
    except Exception as e:
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
    try:
        db = SessionLocal()
        boards = db.query(Board).all()
        db.close()
        return jsonify({
            "success": True,
            "boards": [{"id": b.id, "name": b.name} for b in boards]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/boards", methods=["POST"])
def create_board():
    """Create a new board.
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
    from flask import request
    try:
        data = request.get_json()
        if not data or "name" not in data:
            return jsonify({"success": False, "message": "Name is required"}), 400
        
        db = SessionLocal()
        board = Board(name=data["name"])
        db.add(board)
        db.commit()
        db.refresh(board)
        result = {"id": board.id, "name": board.name}
        db.close()
        
        return jsonify({"success": True, "board": result}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)