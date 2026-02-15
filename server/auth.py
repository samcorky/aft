"""
Authentication endpoints and middleware for AFT.

This module provides:
- Login/logout endpoints
- Session management
- Password hashing/verification
- User registration
- Authentication middleware
"""

import hashlib
import secrets
from flask import Blueprint, request, jsonify, session, g
from sqlalchemy.sql import func
from database import SessionLocal
from models import User, Role, UserRole
from utils import (
    validate_string_length,
    create_error_response,
    create_success_response,
    MAX_TITLE_LENGTH
)
import logging

logger = logging.getLogger(__name__)

# Create blueprint for auth routes
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Session configuration constants
SESSION_LIFETIME_HOURS = 24 * 7  # 7 days
REMEMBER_ME_LIFETIME_DAYS = 30


def hash_password(password: str) -> str:
    """
    Hash a password using PBKDF2-HMAC-SHA256.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password in format: salt$hash
    """
    salt = secrets.token_hex(32)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        password: Plain text password to verify
        password_hash: Stored hash in format: salt$hash
        
    Returns:
        True if password matches
    """
    try:
        salt, stored_hash = password_hash.split('$')
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return pwd_hash.hex() == stored_hash
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def load_user_from_session():
    """
    Middleware to load user from session or Basic Auth into Flask g object.
    Call this in app.before_request.
    
    Supports:
    1. Session-based authentication (primary method)
    2. HTTP Basic Authentication (for Swagger UI testing)
    """
    user_id = session.get('user_id')
    stored_email_hash = session.get('user_email_hash')
    
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).filter(
                User.id == user_id,
                User.is_active == True
            ).first()
            
            if user:
                # Validate session is for this specific user (prevents old sessions from
                # accessing new users with same ID after database reset)
                current_email_hash = hashlib.sha256(user.email.encode()).hexdigest()[:16]
                if stored_email_hash != current_email_hash:
                    # Session email hash doesn't match - clear session
                    logger.warning(f"Session email hash mismatch for user_id={user_id}, clearing session")
                    session.clear()
                    g.user = None
                    g.db = None
                    db.close()
                    return
                
                g.user = user
                g.db = db  # Make db available for the request
                return  # Successfully authenticated via session
            else:
                # User not found or inactive, clear session
                session.clear()
                g.user = None
                g.db = None
                db.close()
        except Exception as e:
            logger.error(f"Error loading user from session: {e}")
            g.user = None
            g.db = None
            db.close()
    
    # If no session auth, try Basic Auth (for Swagger UI)
    auth = request.authorization
    if auth and auth.username and auth.password:
        db = SessionLocal()
        try:
            from sqlalchemy.sql import func
            # Try email first, then username
            user = db.query(User).filter(
                func.lower(User.email) == auth.username.lower()
            ).first()
            
            if not user:
                user = db.query(User).filter(
                    func.lower(User.username) == auth.username.lower()
                ).first()
            
            if user and user.is_active and user.is_approved and user.password_hash:
                if verify_password(auth.password, user.password_hash):
                    g.user = user
                    g.db = db
                    return
            
            # Invalid Basic Auth
            g.user = None
            g.db = None
            db.close()
        except Exception as e:
            logger.error(f"Error loading user from Basic Auth: {e}")
            g.user = None
            g.db = None
            db.close()
    else:
        g.user = None
        g.db = None


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint.
    
    Request body:
        {
            "email": "user@example.com",  // or username
            "password": "password123",
            "remember_me": false  // optional
        }
    
    Returns:
        200: Login successful with user data
        401: Invalid credentials
        400: Validation error
    """
    try:
        data = request.get_json()
        
        if not data:
            return create_error_response("Request body required", 400)
        
        email_or_username = data.get('email', '').strip()
        password = data.get('password', '')
        remember_me = data.get('remember_me', False)
        
        # Validate inputs
        if not email_or_username or not password:
            return create_error_response("Email/username and password are required", 400)
        
        # Find user by email or username
        db = SessionLocal()
        try:
            # Try to find user by email first (case-insensitive)
            user = db.query(User).filter(
                func.lower(User.email) == email_or_username.lower()
            ).first()
            
            # If not found by email, try by username (case-insensitive)
            if not user:
                user = db.query(User).filter(
                    func.lower(User.username) == email_or_username.lower()
                ).first()
            
            if not user:
                # Don't reveal whether user exists
                return create_error_response("Invalid email/username or password", 401)
            
            # Check if user has a password (might be OAuth only)
            if not user.password_hash:
                return create_error_response(
                    "This account uses OAuth login. Please use the appropriate login method.",
                    400
                )
            
            # Verify password
            if not verify_password(password, user.password_hash):
                return create_error_response("Invalid email/username or password", 401)
            
            # Check if account is active
            if not user.is_active:
                return create_error_response("Account is disabled", 403)
            
            # Check if account is approved
            if not user.is_approved:
                return create_error_response(
                    "Your account is pending administrator approval. You will be notified when approved.",
                    403
                )
            
            # Create session
            session.clear()
            session['user_id'] = user.id
            session['user_email_hash'] = hashlib.sha256(user.email.encode()).hexdigest()[:16]
            session.permanent = remember_me
            
            # Update last login
            user.last_login_at = func.now()
            db.commit()
            
            # Return user data (without sensitive fields)
            user_data = {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'display_name': user.display_name,
                'email_verified': user.email_verified
            }
            
            logger.info(f"User logged in: {user.email} (ID: {user.id})")
            
            return create_success_response(
                data={'user': user_data},
                message="Login successful"
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return create_error_response("An error occurred during login", 500)


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    Logout endpoint.
    
    Returns:
        200: Logout successful
    """
    user_id = session.get('user_id')
    session.clear()
    
    if user_id:
        logger.info(f"User logged out: ID {user_id}")
    
    return create_success_response(message="Logout successful")


@auth_bp.route('/validate', methods=['POST'])
def validate_credentials():
    """
    Validate credentials without creating a session.
    Used by Swagger UI to test credentials.
    
    Request body:
        {
            "email": "user@example.com",  // or username
            "password": "password123"
        }
    
    Returns:
        200: Credentials valid
        401: Invalid credentials
        400: Validation error
    """
    try:
        data = request.get_json()
        
        if not data:
            return create_error_response("Request body required", 400)
        
        email_or_username = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email_or_username or not password:
            return create_error_response("Email/username and password are required", 400)
        
        db = SessionLocal()
        try:
            # Try email first, then username
            user = db.query(User).filter(
                func.lower(User.email) == email_or_username.lower()
            ).first()
            
            if not user:
                user = db.query(User).filter(
                    func.lower(User.username) == email_or_username.lower()
                ).first()
            
            if not user:
                return create_error_response("Invalid email/username or password", 401)
            
            if not user.password_hash:
                return create_error_response(
                    "This account uses OAuth login",
                    400
                )
            
            if not verify_password(password, user.password_hash):
                return create_error_response("Invalid email/username or password", 401)
            
            if not user.is_active:
                return create_error_response("Account is disabled", 403)
            
            if not user.is_approved:
                return create_error_response(
                    "Account pending approval",
                    403
                )
            
            # Credentials are valid
            return create_success_response(
                message="Credentials valid",
                data={
                    'email': user.email,
                    'username': user.username
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Credential validation error: {e}")
        return create_error_response("Validation failed", 500)


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """
    Get current authenticated user information.
    
    Returns:
        200: User data
        401: Not authenticated
    """
    if not g.get('user'):
        return create_error_response("Not authenticated", 401)
    
    user = g.user
    
    # Get user's roles
    db = SessionLocal()
    try:
        roles = db.query(Role).join(UserRole).filter(
            UserRole.user_id == user.id,
            UserRole.board_id.is_(None)  # Global roles only
        ).all()
        
        user_data = {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'display_name': user.display_name,
            'email_verified': user.email_verified,
            'oauth_provider': user.oauth_provider,
            'roles': [{'id': r.id, 'name': r.name, 'description': r.description} for r in roles]
        }
        
        return create_success_response(data={'user': user_data})
        
    finally:
        db.close()


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user account.
    
    Request body:
        {
            "email": "user@example.com",
            "username": "username",
            "password": "password123",
            "display_name": "Display Name"  // optional
        }
    
    Returns:
        201: User created
        400: Validation error
        409: User already exists
    """
    try:
        data = request.get_json()
        
        if not data:
            return create_error_response("Request body required", 400)
        
        email = data.get('email', '').strip().lower()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        display_name = data.get('display_name', '').strip()
        
        # Validate inputs
        if not email:
            return create_error_response("Email is required", 400)
        
        if not username:
            return create_error_response("Username is required", 400)
        
        if not password:
            return create_error_response("Password is required", 400)
        
        if len(password) < 8:
            return create_error_response("Password must be at least 8 characters", 400)
        
        # Validate string lengths
        is_valid, error = validate_string_length(email, MAX_TITLE_LENGTH, "Email")
        if not is_valid:
            return create_error_response(error, 400)
        
        is_valid, error = validate_string_length(username, 100, "Username")
        if not is_valid:
            return create_error_response(error, 400)
        
        # Check if user already exists
        db = SessionLocal()
        try:
            existing_email = db.query(User).filter(
                func.lower(User.email) == email
            ).first()
            
            if existing_email:
                return create_error_response("Email already registered", 409)
            
            existing_username = db.query(User).filter(
                func.lower(User.username) == func.lower(username)
            ).first()
            
            if existing_username:
                return create_error_response("Username already taken", 409)
            
            # Create user
            user = User(
                email=email,
                username=username,
                display_name=display_name or username,
                password_hash=hash_password(password),
                is_active=True,
                is_approved=False,  # Requires admin approval
                email_verified=False  # TODO: Send verification email
            )
            
            db.add(user)
            db.flush()  # Get user ID
            
            # Assign default 'editor' role
            editor_role = db.query(Role).filter(Role.name == 'editor').first()
            if editor_role:
                user_role = UserRole(
                    user_id=user.id,
                    role_id=editor_role.id,
                    board_id=None  # Global role
                )
                db.add(user_role)
            
            db.commit()
            
            logger.info(f"New user registered: {user.email} (ID: {user.id})")
            
            # Don't auto-login - user needs admin approval
            # Return success but explain approval is needed
            user_data = {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'display_name': user.display_name,
                'requires_approval': True
            }
            
            return create_success_response(
                data={'user': user_data},
                message="Registration successful! Your account is pending administrator approval. You will be able to log in once approved.",
                status_code=201
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return create_error_response("An error occurred during registration", 500)


@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """
    Change password for current user.
    
    Request body:
        {
            "current_password": "oldpassword",
            "new_password": "newpassword"
        }
    
    Returns:
        200: Password changed
        401: Not authenticated or invalid current password
        400: Validation error
    """
    if not g.get('user'):
        return create_error_response("Not authenticated", 401)
    
    try:
        data = request.get_json()
        
        if not data:
            return create_error_response("Request body required", 400)
        
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return create_error_response("Current and new password are required", 400)
        
        if len(new_password) < 8:
            return create_error_response("New password must be at least 8 characters", 400)
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == g.user.id).first()
            
            if not user or not user.password_hash:
                return create_error_response("Cannot change password for this account", 400)
            
            # Verify current password
            if not verify_password(current_password, user.password_hash):
                return create_error_response("Current password is incorrect", 401)
            
            # Update password
            user.password_hash = hash_password(new_password)
            db.commit()
            
            logger.info(f"Password changed for user: {user.email} (ID: {user.id})")
            
            return create_success_response(message="Password changed successfully")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Change password error: {e}")
        return create_error_response("An error occurred while changing password", 500)


@auth_bp.route('/check', methods=['GET'])
def check_auth():
    """
    Check if user is authenticated.
    
    Returns:
        200: User is authenticated with user data
        401: Not authenticated
    """
    if g.get('user'):
        return jsonify({
            'authenticated': True,
            'user': {
                'id': g.user.id,
                'email': g.user.email,
                'username': g.user.username,
                'display_name': g.user.display_name
            }
        })
    
    return jsonify({'authenticated': False}), 401


@auth_bp.route('/setup/status', methods=['GET'])
def setup_status():
    """
    Check if initial setup is complete.
    
    Returns:
        200: Setup status
            {
                "setup_complete": true/false,
                "has_users": true/false
            }
    """
    db = SessionLocal()
    try:
        # Check if any active users with passwords exist
        user_count = db.query(User).filter(
            User.is_active == True,
            User.password_hash.isnot(None)
        ).count()
        
        setup_complete = user_count > 0
        
        return jsonify({
            'setup_complete': setup_complete,
            'has_users': user_count > 0
        })
    finally:
        db.close()


@auth_bp.route('/setup/admin', methods=['POST'])
def setup_admin():
    """
    Create the first administrator account during initial setup.
    This endpoint only works if no users exist yet.
    
    Request body:
        {
            "email": "admin@example.com",
            "username": "admin",
            "password": "securepassword",
            "display_name": "Administrator"
        }
    
    Returns:
        201: Admin user created successfully
        400: Validation error
        403: Setup already complete
    """
    try:
        db = SessionLocal()
        
        try:
            # Check if setup is already complete
            existing_users = db.query(User).filter(
                User.is_active == True,
                User.password_hash.isnot(None)
            ).count()
            
            if existing_users > 0:
                return create_error_response(
                    "Setup is already complete. Please use the login page.",
                    403
                )
            
            data = request.get_json()
            
            if not data:
                return create_error_response("Request body required", 400)
            
            email = data.get('email', '').strip().lower()
            username = data.get('username', '').strip()
            password = data.get('password', '')
            display_name = data.get('display_name', '').strip()
            
            # Validate inputs
            if not email:
                return create_error_response("Email is required", 400)
            
            if not username:
                return create_error_response("Username is required", 400)
            
            if not password:
                return create_error_response("Password is required", 400)
            
            if len(password) < 8:
                return create_error_response("Password must be at least 8 characters", 400)
            
            # Validate string lengths
            is_valid, error = validate_string_length(email, MAX_TITLE_LENGTH, "Email")
            if not is_valid:
                return create_error_response(error, 400)
            
            is_valid, error = validate_string_length(username, 100, "Username")
            if not is_valid:
                return create_error_response(error, 400)
            
            # Check if default admin user exists (from migration)
            existing_admin = db.query(User).filter(
                User.username == 'admin',
                User.email == 'admin@localhost'
            ).first()
            
            if existing_admin and not existing_admin.password_hash:
                # Update the existing admin user from migration
                existing_admin.email = email
                existing_admin.username = username
                existing_admin.display_name = display_name or username
                existing_admin.password_hash = hash_password(password)
                existing_admin.email_verified = True
                existing_admin.is_approved = True  # Admin is auto-approved
                
                db.commit()
                
                user = existing_admin
                logger.info(f"Updated default admin user: {user.email} (ID: {user.id})")
            else:
                # Create new admin user
                user = User(
                    email=email,
                    username=username,
                    display_name=display_name or username,
                    password_hash=hash_password(password),
                    is_active=True,
                    is_approved=True,  # Admin is auto-approved
                    email_verified=True
                )
                
                db.add(user)
                db.flush()  # Get user ID
                
                # Assign administrator role
                admin_role = db.query(Role).filter(Role.name == 'administrator').first()
                if admin_role:
                    user_role = UserRole(
                        user_id=user.id,
                        role_id=admin_role.id,
                        board_id=None  # Global role
                    )
                    db.add(user_role)
                
                db.commit()
                
                logger.info(f"Created first admin user: {user.email} (ID: {user.id})")
            
            # Auto-login after setup
            session['user_id'] = user.id
            session['user_email_hash'] = hashlib.sha256(user.email.encode()).hexdigest()[:16]
            
            user_data = {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'display_name': user.display_name
            }
            
            return create_success_response(
                data={'user': user_data},
                message="Setup complete! Welcome to AFT.",
                status_code=201
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Setup error: {e}")
        return create_error_response("An error occurred during setup", 500)
