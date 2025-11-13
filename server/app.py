from flask import Flask, jsonify, request
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

<a href="/" style="text-decoration: none;">← Back to AFT Home</a>
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
    """Update a column's name.
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
          required:
            - name
          properties:
            name:
              type: string
              example: "In Progress"
              description: The new name for the column
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
        if not data or "name" not in data:
            return jsonify({"success": False, "message": "Name is required"}), 400
        
        db = SessionLocal()
        from models import BoardColumn
        column = db.query(BoardColumn).filter(BoardColumn.id == column_id).first()
        
        if not column:
            db.close()
            return jsonify({"success": False, "message": "Column not found"}), 404
        
        column.name = data["name"]
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
        
        # Get next available order
        max_order = db.query(Card).filter(Card.column_id == column_id).count()
        
        # Create card
        card = Card(
            column_id=column_id,
            title=data["title"],
            description=data.get("description", ""),
            order=max_order
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


@app.route("/api/cards/<int:card_id>", methods=["PATCH"])
def update_card(card_id):
    """Update a card's title and description.
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
        from models import Card
        card = db.query(Card).filter(Card.id == card_id).first()
        
        if not card:
            db.close()
            return jsonify({"success": False, "message": "Card not found"}), 404
        
        # Update fields if provided
        if "title" in data:
            card.title = data["title"]
        if "description" in data:
            card.description = data["description"]
        
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