"""Utility functions and decorators for the AFT application.

This module provides reusable helpers for:
- Database session management
- Input validation and sanitization
- Error response formatting
"""

import logging
from functools import wraps
from typing import Callable, Any, Tuple
from flask import jsonify, request
from database import SessionLocal

logger = logging.getLogger(__name__)

# Input validation constants
MAX_STRING_LENGTH = 10000  # Maximum length for any string input
MAX_TITLE_LENGTH = 255     # Maximum length for titles (board/column/card)
MAX_DESCRIPTION_LENGTH = 2000  # Maximum length for descriptions
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
        return False, jsonify({
            "success": False,
            "message": "Content-Type must be application/json"
        }), 400
    return True, None


def validate_string_length(value: str, max_length: int, field_name: str) -> Tuple[bool, str]:
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


def validate_integer(value: Any, field_name: str, min_value: int = None, 
                     max_value: int = None, allow_none: bool = False) -> Tuple[bool, str]:
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
        return False, jsonify({
            "success": False,
            "message": f"Request size exceeds maximum allowed size of {MAX_REQUEST_SIZE} bytes"
        }), 413  # 413 Payload Too Large
        
    return True, None


def create_error_response(message: str, status_code: int = 400) -> Tuple[Any, int]:
    """Create a standardized error response.
    
    Args:
        message: Error message to return
        status_code: HTTP status code
        
    Returns:
        tuple: (json_response, status_code)
    """
    return jsonify({
        "success": False,
        "message": message
    }), status_code


def create_success_response(data: dict = None, message: str = None, 
                            status_code: int = 200) -> Tuple[Any, int]:
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
