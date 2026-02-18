"""Utility functions and decorators for the AFT application.

This module provides reusable helpers for:
- Database session management
- Input validation and sanitization
- Error response formatting
- User authentication and authorization
"""

import logging
import json
from functools import wraps
from typing import Callable, Any, Tuple
from flask import jsonify, request, g, abort
from database import SessionLocal

logger = logging.getLogger(__name__)

# Input validation constants
MAX_STRING_LENGTH = 10000  # Maximum length for any string input
MAX_TITLE_LENGTH = 255  # Maximum length for titles (board/column/card)
MAX_DESCRIPTION_LENGTH = 2000  # Maximum length for descriptions
MAX_COMMENT_LENGTH = 50000  # Maximum length for comments (50K chars for large notes)
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB max request size


def db_session(func: Callable) -> Callable:
    """Decorator to handle database session lifecycle automatically.

    This decorator:
    1. Creates a database session
    2. Passes it to the decorated function
    3. Commits on success
    4. Rolls back on error
    5. Always closes the session

    Usage:
        @db_session
        def my_endpoint():
            # db parameter is automatically injected
            pass

    Args:
        func: The function to decorate

    Returns:
        Wrapped function with automatic session management
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        db = SessionLocal()
        try:
            # Inject db session as keyword argument
            result = func(*args, db=db, **kwargs)
            # If function succeeded and no explicit commit/rollback, commit
            if not db.is_active:
                # Session was already committed or rolled back
                pass
            else:
                db.commit()
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"Error in {func.__name__}: {str(e)}")
            raise
        finally:
            db.close()

    return wrapper


def validate_json_content_type() -> Tuple[bool, Any]:
    """Validate that request has proper JSON content type.

    Returns:
        tuple: (is_valid, error_response or None)
    """
    if not request.is_json and request.data:
        return (
            False,
            jsonify(
                {"success": False, "message": "Content-Type must be application/json"}
            ),
            400,
        )
    return True, None


def validate_string_length(
    value: str, max_length: int, field_name: str
) -> Tuple[bool, str]:
    """Validate string length.

    Args:
        value: The string to validate
        max_length: Maximum allowed length
        field_name: Name of the field for error messages

    Returns:
        tuple: (is_valid, error_message or None)
    """
    if value is None:
        return True, None

    if not isinstance(value, str):
        return False, f"{field_name} must be a string"

    if len(value) > max_length:
        return False, f"{field_name} exceeds maximum length of {max_length} characters"

    return True, None


def validate_integer(
    value: Any,
    field_name: str,
    min_value: int = None,
    max_value: int = None,
    allow_none: bool = False,
) -> Tuple[bool, str]:
    """Validate integer value.

    Args:
        value: The value to validate
        field_name: Name of the field for error messages
        min_value: Minimum allowed value (optional)
        max_value: Maximum allowed value (optional)
        allow_none: Whether None is allowed

    Returns:
        tuple: (is_valid, error_message or None)
    """
    if value is None:
        if allow_none:
            return True, None
        return False, f"{field_name} is required"

    # Reject boolean values (True/False are instances of int in Python)
    if isinstance(value, bool):
        return False, f"{field_name} must be an integer, not boolean"

    if not isinstance(value, int):
        return False, f"{field_name} must be an integer"

    if min_value is not None and value < min_value:
        return False, f"{field_name} must be at least {min_value}"

    if max_value is not None and value > max_value:
        return False, f"{field_name} must be at most {max_value}"

    return True, None


def sanitize_string(value: str) -> str:
    """Sanitize string input by removing potentially dangerous characters.

    This is a basic sanitization. SQL injection is prevented by using
    SQLAlchemy's parameterized queries. This mainly prevents XSS if
    the API responses are rendered in HTML without escaping.

    Args:
        value: The string to sanitize

    Returns:
        Sanitized string
    """
    if value is None:
        return None

    # Strip leading/trailing whitespace
    value = value.strip()

    # Additional sanitization can be added here if needed
    # For now, we rely on proper escaping on the frontend

    return value


def validate_request_size() -> Tuple[bool, Any]:
    """Validate request size to prevent DoS attacks.

    Returns:
        tuple: (is_valid, error_response or None)
    """
    content_length = request.content_length

    if content_length and content_length > MAX_REQUEST_SIZE:
        return (
            False,
            jsonify(
                {
                    "success": False,
                    "message": f"Request size exceeds maximum allowed size of {MAX_REQUEST_SIZE} bytes",
                }
            ),
            413,
        )  # 413 Payload Too Large

    return True, None


def create_error_response(message: str, status_code: int = 400) -> Tuple[Any, int]:
    """Create a standardized error response.

    Args:
        message: Error message to return
        status_code: HTTP status code

    Returns:
        tuple: (json_response, status_code)
    """
    return jsonify({"success": False, "message": message}), status_code


def create_success_response(
    data: dict = None, message: str = None, status_code: int = 200
) -> Tuple[Any, int]:
    """Create a standardized success response.

    Args:
        data: Data to include in response
        message: Optional success message
        status_code: HTTP status code

    Returns:
        tuple: (json_response, status_code)
    """
    response = {"success": True}

    if message:
        response["message"] = message

    if data:
        response.update(data)

    return jsonify(response), status_code


# ============================================================================
# User Authentication and Authorization Functions
# ============================================================================

def get_user_scoped_query(db, model, user_id):
    """
    Get a query for a model automatically scoped to user.
    This is the PRIMARY defense against cross-user data access.
    
    CRITICAL: Always use this function when querying user-owned data.
    This prevents accidental data leaks across users.
    
    Args:
        db: Database session
        model: SQLAlchemy model class
        user_id: ID of the current user
        
    Returns:
        SQLAlchemy query scoped to the user
        
    Raises:
        ValueError: If model scoping is not defined (fail secure)
    """
    # Import here to avoid circular imports
    from models import Board, BoardColumn, Card, ChecklistItem, Comment, Setting, Theme, Notification, ScheduledCard, UserRole
    
    query = db.query(model)
    
    # Models with direct user_id column
    if hasattr(model, 'user_id'):
        # For settings and themes, user_id can be NULL for system/global items
        # Include both user's items AND global items (where user_id IS NULL)
        if model.__name__ in ['Setting', 'Theme']:
            return query.filter((model.user_id == user_id) | (model.user_id.is_(None)))
        # For notifications, only show user's own
        return query.filter(model.user_id == user_id)
    
    # Models with owner_id (like Board) - include owned boards AND boards where user has a role
    if hasattr(model, 'owner_id'):
        # Board can be accessed if user owns it OR has a role on it
        owned = query.filter(model.owner_id == user_id)
        role_based = query.join(UserRole).filter(UserRole.user_id == user_id)
        return owned.union(role_based)
    
    # Models that inherit permissions through relationships
    # Card inherits from Board through Column - include owned boards AND role-assigned boards
    if model.__name__ == 'Card':
        return query.join(BoardColumn).join(Board).filter(
            (Board.owner_id == user_id) | 
            (Board.id.in_(
                db.query(UserRole.board_id).filter(UserRole.user_id == user_id)
            ))
        )
    
    if model.__name__ == 'BoardColumn':
        return query.join(Board).filter(
            (Board.owner_id == user_id) | 
            (Board.id.in_(
                db.query(UserRole.board_id).filter(UserRole.user_id == user_id)
            ))
        )
    
    if model.__name__ == 'ChecklistItem':
        return query.join(Card).join(BoardColumn).join(Board).filter(
            (Board.owner_id == user_id) | 
            (Board.id.in_(
                db.query(UserRole.board_id).filter(UserRole.user_id == user_id)
            ))
        )
    
    if model.__name__ == 'Comment':
        return query.join(Card).join(BoardColumn).join(Board).filter(
            (Board.owner_id == user_id) | 
            (Board.id.in_(
                db.query(UserRole.board_id).filter(UserRole.user_id == user_id)
            ))
        )
    
    if model.__name__ == 'ScheduledCard':
        return query.join(Card).join(BoardColumn).join(Board).filter(
            (Board.owner_id == user_id) | 
            (Board.id.in_(
                db.query(UserRole.board_id).filter(UserRole.user_id == user_id)
            ))
        )
    
    # Fail secure: if we don't know how to scope it, raise an error
    logger.error(f"No scoping rule defined for model {model.__name__}. This is a security issue!")
    raise ValueError(f"Cannot scope queries for model {model.__name__}. Access denied.")


def get_current_user_id():
    """
    Get the current user's ID from Flask's g object.
    
    Returns:
        int: User ID or None if not authenticated
    """
    user = g.get('user')
    return user.id if user else None


def require_permission(permission):
    """
    Decorator to check if current user has required permission.
    
    Usage:
        @require_permission('board.edit')
        def edit_board(board_id):
            ...
    
    Args:
        permission: Permission string to require (e.g., 'board.edit')
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.get('user'):
                abort(401, description="Authentication required")
            
            user_permissions = get_user_permissions(g.user.id)
            
            # Check if user has the required permission
            from permissions import has_permission
            if not has_permission(user_permissions, permission):
                abort(403, description=f"Permission denied: {permission}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_permission(*permissions):
    """
    Decorator to check if current user has ANY of the required permissions.
    
    Usage:
        @require_any_permission('role.manage', 'user.role')
        def get_roles():
            ...
    
    Args:
        permissions: Variable number of permission strings
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.get('user'):
                abort(401, description="Authentication required")
            
            user_permissions = get_user_permissions(g.user.id)
            
            # Check if user has any of the required permissions
            from permissions import has_permission
            has_any = any(has_permission(user_permissions, perm) for perm in permissions)
            
            if not has_any:
                perms_str = ' or '.join(permissions)
                abort(403, description=f"Permission denied: requires {perms_str}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_board_access(require_owner=False):
    """
    Decorator to check if user can access a board.
    Expects board_id as a parameter to the decorated function.
    
    Usage:
        @require_board_access()
        def get_board(board_id):
            ...
            
        @require_board_access(require_owner=True)
        def delete_board(board_id):
            ...
    
    Args:
        require_owner: If True, user must be the board owner (default: False)
        
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.get('user'):
                abort(401, description="Authentication required")
            
            # Get board_id from kwargs or args
            board_id = kwargs.get('board_id')
            if board_id is None and len(args) > 0:
                board_id = args[0]
            
            if board_id is None:
                abort(400, description="Board ID required")
            
            # Check access
            has_access, is_owner = can_access_board(g.user.id, board_id)
            
            if not has_access:
                abort(403, description="Access denied to this board")
            
            if require_owner and not is_owner:
                abort(403, description="Board owner access required")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_user_permissions(user_id, board_id=None):
    """
    Get all permissions for a user, optionally scoped to a board.
    
    Args:
        user_id: User ID
        board_id: Optional board ID to get board-specific permissions
        
    Returns:
        set: Set of permission strings
    """
    from models import Role, UserRole
    
    db = SessionLocal()
    try:
        query = db.query(Role.permissions).join(UserRole).filter(
            UserRole.user_id == user_id
        )
        
        if board_id:
            # Get board-specific + global roles
            query = query.filter(
                (UserRole.board_id == board_id) | (UserRole.board_id.is_(None))
            )
        else:
            # Global roles only
            query = query.filter(UserRole.board_id.is_(None))
        
        all_perms = set()
        for (perms_json,) in query.all():
            perms = json.loads(perms_json)
            all_perms.update(perms)
        
        return all_perms
    finally:
        db.close()


def can_access_board(user_id, board_id):
    """
    Check if user can access a board (owns it or has a role on it).
    
    Args:
        user_id: User ID
        board_id: Board ID
        
    Returns:
        tuple: (has_access: bool, is_owner: bool)
    """
    from models import Board, UserRole
    
    db = SessionLocal()
    try:
        board = db.query(Board).filter(Board.id == board_id).first()
        if not board:
            return False, False
        
        # Owner always has access
        if board.owner_id == user_id:
            return True, True
        
        # Check if user has any role on this board
        has_role = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.board_id == board_id
        ).first() is not None
        
        return has_role, False
    finally:
        db.close()


def require_authentication(f):
    """
    Decorator to require authentication but not specific permissions.
    
    Usage:
        @require_authentication
        def my_endpoint():
            # g.user is guaranteed to exist
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('user'):
            abort(401, description="Authentication required")
        return f(*args, **kwargs)
    return decorated_function
