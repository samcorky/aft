"""
User management endpoints for administrators.

This module provides admin-only endpoints for:
- Viewing all users
- Approving/rejecting pending users
- Managing user roles
- Activating/deactivating users
"""

from flask import Blueprint, jsonify, request, g
from database import SessionLocal
from models import User, Role, UserRole
from utils import (
    require_permission,
    create_error_response,
    create_success_response,
)
import logging

logger = logging.getLogger(__name__)

# Create blueprint for user management routes
user_mgmt_bp = Blueprint('user_mgmt', __name__, url_prefix='/api/users')


@user_mgmt_bp.route('', methods=['GET'])
@require_permission('user.manage')
def list_users():
    """
    List all users in the system.
    
    Query params:
        status: 'pending', 'approved', 'all' (default: 'all')
        
    Returns:
        200: List of users
    """
    status_filter = request.args.get('status', 'all')
    
    db = SessionLocal()
    try:
        query = db.query(User)
        
        if status_filter == 'pending':
            query = query.filter(User.is_approved == False, User.is_active == True)
        elif status_filter == 'approved':
            query = query.filter(User.is_approved == True)
        
        users = query.order_by(User.created_at.desc()).all()
        
        users_data = []
        for user in users:
            # Get user's roles
            roles = db.query(Role).join(UserRole).filter(
                UserRole.user_id == user.id,
                UserRole.board_id.is_(None)  # Global roles only
            ).all()
            
            users_data.append({
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'display_name': user.display_name,
                'is_active': user.is_active,
                'is_approved': user.is_approved,
                'email_verified': user.email_verified,
                'oauth_provider': user.oauth_provider,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
                'roles': [{'id': r.id, 'name': r.name} for r in roles]
            })
        
        return create_success_response(data={'users': users_data})
        
    finally:
        db.close()


@user_mgmt_bp.route('/pending', methods=['GET'])
@require_permission('user.manage')
def list_pending_users():
    """
    List all pending (unapproved) users.
    
    Returns:
        200: List of pending users
    """
    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.is_approved == False,
            User.is_active == True
        ).order_by(User.created_at.desc()).all()
        
        users_data = [{
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'display_name': user.display_name,
            'created_at': user.created_at.isoformat() if user.created_at else None,
        } for user in users]
        
        return create_success_response(data={
            'users': users_data,
            'count': len(users_data)
        })
        
    finally:
        db.close()


@user_mgmt_bp.route('/<int:user_id>/approve', methods=['POST'])
@require_permission('user.manage')
def approve_user(user_id):
    """
    Approve a pending user account.
    
    Args:
        user_id: ID of user to approve
        
    Returns:
        200: User approved
        404: User not found
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return create_error_response("User not found", 404)
        
        if user.is_approved:
            return create_error_response("User is already approved", 400)
        
        user.is_approved = True
        db.commit()
        
        logger.info(f"User approved: {user.email} (ID: {user.id}) by admin {g.user.id}")
        
        # TODO: Send approval notification email to user
        
        return create_success_response(
            message=f"User {user.username} has been approved"
        )
        
    finally:
        db.close()


@user_mgmt_bp.route('/<int:user_id>/reject', methods=['POST'])
@require_permission('user.manage')
def reject_user(user_id):
    """
    Reject and delete a pending user account.
    
    Args:
        user_id: ID of user to reject
        
    Returns:
        200: User rejected and deleted
        404: User not found
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return create_error_response("User not found", 404)
        
        if user.is_approved:
            return create_error_response(
                "Cannot reject an approved user. Use deactivate instead.",
                400
            )
        
        username = user.username
        email = user.email
        
        db.delete(user)
        db.commit()
        
        logger.info(f"User rejected and deleted: {email} (username: {username}) by admin {g.user.id}")
        
        return create_success_response(
            message=f"User {username} has been rejected and removed"
        )
        
    finally:
        db.close()


@user_mgmt_bp.route('/<int:user_id>/deactivate', methods=['POST'])
@require_permission('user.manage')
def deactivate_user(user_id):
    """
    Deactivate a user account (prevents login).
    
    Args:
        user_id: ID of user to deactivate
        
    Returns:
        200: User deactivated
        404: User not found
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return create_error_response("User not found", 404)
        
        if user.id == g.user.id:
            return create_error_response("Cannot deactivate your own account", 400)
        
        user.is_active = False
        db.commit()
        
        logger.info(f"User deactivated: {user.email} (ID: {user.id}) by admin {g.user.id}")
        
        return create_success_response(
            message=f"User {user.username} has been deactivated"
        )
        
    finally:
        db.close()


@user_mgmt_bp.route('/<int:user_id>/activate', methods=['POST'])
@require_permission('user.manage')
def activate_user(user_id):
    """
    Reactivate a deactivated user account.
    
    Args:
        user_id: ID of user to activate
        
    Returns:
        200: User activated
        404: User not found
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return create_error_response("User not found", 404)
        
        user.is_active = True
        db.commit()
        
        logger.info(f"User activated: {user.email} (ID: {user.id}) by admin {g.user.id}")
        
        return create_success_response(
            message=f"User {user.username} has been activated"
        )
        
    finally:
        db.close()


@user_mgmt_bp.route('/<int:user_id>/roles', methods=['POST'])
@require_permission('role.manage')
def assign_role(user_id):
    """
    Assign a role to a user.
    
    Request body:
        {
            "role_name": "administrator",
            "board_id": null  // optional, for board-specific roles
        }
    
    Returns:
        200: Role assigned
        404: User or role not found
        409: Role already assigned
    """
    data = request.get_json()
    
    if not data or 'role_name' not in data:
        return create_error_response("role_name is required", 400)
    
    role_name = data['role_name']
    board_id = data.get('board_id')
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return create_error_response("User not found", 404)
        
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            return create_error_response(f"Role '{role_name}' not found", 404)
        
        # Check if role already assigned
        existing = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.board_id == board_id
        ).first()
        
        if existing:
            scope = f" on board {board_id}" if board_id else " (global)"
            return create_error_response(
                f"User already has role '{role_name}'{scope}",
                409
            )
        
        user_role = UserRole(
            user_id=user_id,
            role_id=role.id,
            board_id=board_id
        )
        db.add(user_role)
        db.commit()
        
        scope = f" on board {board_id}" if board_id else " (global)"
        logger.info(f"Role '{role_name}' assigned to user {user.email}{scope} by admin {g.user.id}")
        
        return create_success_response(
            message=f"Role '{role_name}' assigned to {user.username}"
        )
        
    finally:
        db.close()


@user_mgmt_bp.route('/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@require_permission('role.manage')
def remove_role(user_id, role_id):
    """
    Remove a role from a user.
    
    Query params:
        board_id: optional, for board-specific roles
    
    Returns:
        200: Role removed
        404: Assignment not found
    """
    board_id = request.args.get('board_id', type=int)
    
    db = SessionLocal()
    try:
        assignment = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.board_id == board_id
        ).first()
        
        if not assignment:
            return create_error_response("Role assignment not found", 404)
        
        db.delete(assignment)
        db.commit()
        
        logger.info(f"Role removed from user {user_id} by admin {g.user.id}")
        
        return create_success_response(message="Role removed successfully")
        
    finally:
        db.close()
