from flask import Flask, jsonify
import logging
from database import SessionLocal
from models import Board

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/api/test")
def test_db():
    """Test database connection and schema."""
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
    """Get all boards."""
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
    """Create a new board."""
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