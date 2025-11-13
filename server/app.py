from flask import Flask, jsonify, request
import logging
from flasgger import Swagger
from database import SessionLocal
from models import Board
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "0.1.0"

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

<a href="/" style="text-decoration: none;">← Back to AFT Home</a>
        """,
        "version": "1.0.0"
    },
    "basePath": "/",
    "schemes": ["http", "https"]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)


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
    try:
        db = SessionLocal()
        # Get current Alembic revision from database
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        db_version = row[0] if row else "unknown"
        db.close()
        
        return jsonify({
            "success": True,
            "app_version": APP_VERSION,
            "db_version": db_version
        })
    except Exception as e:
        logger.error(f"Error getting version: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


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
    try:
        db = SessionLocal()
        board = db.query(Board).filter(Board.id == board_id).first()
        
        if not board:
            db.close()
            return jsonify({"success": False, "message": "Board not found"}), 404
        
        db.delete(board)
        db.commit()
        db.close()
        
        return jsonify({"success": True, "message": "Board deleted successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
    try:
        db = SessionLocal()
        from models import BoardColumn
        columns = db.query(BoardColumn).filter(BoardColumn.board_id == board_id).order_by(BoardColumn.order).all()
        db.close()
        return jsonify({
            "success": True,
            "columns": [{"id": c.id, "board_id": c.board_id, "name": c.name, "order": c.order} for c in columns]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
    try:
        data = request.get_json()
        if not data or "name" not in data:
            return jsonify({"success": False, "message": "Name is required"}), 400
        
        db = SessionLocal()
        
        # Verify board exists
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            db.close()
            return jsonify({"success": False, "message": "Board not found"}), 404
        
        # If order not specified, add to end
        from models import BoardColumn
        if "order" not in data:
            max_order = db.query(BoardColumn).filter(BoardColumn.board_id == board_id).count()
            order = max_order
        else:
            order = data["order"]
        
        column = BoardColumn(board_id=board_id, name=data["name"], order=order)
        db.add(column)
        db.commit()
        db.refresh(column)
        result = {"id": column.id, "board_id": column.board_id, "name": column.name, "order": column.order}
        db.close()
        
        return jsonify({"success": True, "column": result}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
    try:
        db = SessionLocal()
        from models import BoardColumn
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        
        if not column:
            db.close()
            return jsonify({"success": False, "message": "Column not found"}), 404
        
        db.delete(column)
        db.commit()
        db.close()
        
        return jsonify({"success": True, "message": "Column deleted successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        db = SessionLocal()
        from models import BoardColumn
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        
        if not column:
            db.close()
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
                    columns_to_update = db.query(BoardColumn).filter(
                        BoardColumn.board_id == board_id,
                        BoardColumn.order >= new_order,
                        BoardColumn.order < old_order
                    ).all()
                    for col in columns_to_update:
                        col.order += 1
                else:
                    # Moving right: decrement columns between old and new position
                    columns_to_update = db.query(BoardColumn).filter(
                        BoardColumn.board_id == board_id,
                        BoardColumn.order > old_order,
                        BoardColumn.order <= new_order
                    ).all()
                    for col in columns_to_update:
                        col.order -= 1
                
                column.order = new_order
        
        db.commit()
        db.refresh(column)
        result = {"id": column.id, "board_id": column.board_id, "name": column.name, "order": column.order}
        db.close()
        
        return jsonify({"success": True, "column": result}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
        cards = db.query(Card).filter(Card.column_id == column_id).order_by(Card.order).all()
        db.close()
        return jsonify({
            "success": True,
            "cards": [{"id": c.id, "column_id": c.column_id, "title": c.title, "description": c.description, "order": c.order} for c in cards]
        })
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
        columns = db.query(BoardColumn).filter(BoardColumn.board_id == board_id).order_by(BoardColumn.order).all()
        
        # Build nested structure
        result = {
            "id": board.id,
            "name": board.name,
            "columns": []
        }
        
        for column in columns:
            # Get cards for this column
            cards = db.query(Card).filter(Card.column_id == column.id).order_by(Card.order).all()
            
            column_data = {
                "id": column.id,
                "name": column.name,
                "order": column.order,
                "cards": [
                    {
                        "id": card.id,
                        "title": card.title,
                        "description": card.description,
                        "order": card.order
                    }
                    for card in cards
                ]
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
    try:
        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"success": False, "message": "Title is required"}), 400
        
        db = SessionLocal()
        from models import BoardColumn, Card
        
        # Verify column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            db.close()
            return jsonify({"success": False, "message": "Column not found"}), 404
        
        # Get order from request or use max order
        if "order" in data:
            order = data["order"]
            # Increment order of existing cards >= this order
            existing_cards = db.query(Card).filter(
                Card.column_id == column_id,
                Card.order >= order
            ).all()
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
            order=order
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        result = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order
        }
        db.close()
        
        return jsonify({"success": True, "card": result}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
    try:
        db = SessionLocal()
        from models import BoardColumn, Card
        
        # Verify column exists
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        if not column:
            db.close()
            return jsonify({"success": False, "message": "Column not found"}), 404
        
        # Delete all cards in the column
        deleted_count = db.query(Card).filter(Card.column_id == column_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        
        return jsonify({
            "success": True, 
            "message": f"Deleted {deleted_count} cards",
            "deleted_count": deleted_count
        }), 200
    except Exception as e:
        if 'db' in locals():
            db.close()
        logger.error(f"Error deleting cards from column {column_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


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
                column = db.query(BoardColumn).filter(BoardColumn.id == new_column_id).first()
                if not column:
                    db.close()
                    return jsonify({"success": False, "message": "Target column not found"}), 404
            
            # If moving to a different column
            if new_column_id != old_column_id:
                # Decrement order of cards after old position in old column
                db.query(Card).filter(
                    Card.column_id == old_column_id,
                    Card.order > old_order
                ).update({Card.order: Card.order - 1})
                
                # Increment order of cards >= new position in new column
                db.query(Card).filter(
                    Card.column_id == new_column_id,
                    Card.order >= new_order
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
                        Card.order < old_order
                    ).update({Card.order: Card.order + 1})
                else:
                    # Moving down: decrement cards between old and new position
                    db.query(Card).filter(
                        Card.column_id == old_column_id,
                        Card.order > old_order,
                        Card.order <= new_order
                    ).update({Card.order: Card.order - 1})
                
                card.order = new_order
        
        db.commit()
        db.refresh(card)
        result = {
            "id": card.id,
            "column_id": card.column_id,
            "title": card.title,
            "description": card.description,
            "order": card.order
        }
        db.close()
        
        return jsonify({"success": True, "card": result}), 200
    except Exception as e:
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
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)