"""
Role Management API endpoints.

This module provides:
- List all available roles
- Get role details and permissions
- Assign roles to users
- Remove roles from users
- Get user role assignments
"""

import logging
import json
from flask import Blueprint, request, g
from database import SessionLocal
from models import User, Role, UserRole, Board
from utils import (
    create_error_response,
    create_success_response,
    require_permission
)
from permissions import PERMISSION_DEFINITIONS

logger = logging.getLogger(__name__)

# Create blueprint for role management routes
role_mgmt_bp = Blueprint('role_management', __name__, url_prefix='/api/roles')


@role_mgmt_bp.route('', methods=['GET'])
@require_permission('role.manage')
def get_all_roles():
    """
    Get all available roles with their descriptions and permissions.
    ---
    tags:
      - Role Management
    responses:
      200:
        description: List of all roles
        schema:
          type: object
          properties:
            success:
              type: boolean
            roles:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  description:
                    type: string
                  is_system_role:
                    type: boolean
                  permissions:
                    type: array
                    items:
                      type: string
                  created_at:
                    type: string
      403:
        description: Forbidden - requires role.manage permission
    """
    db = SessionLocal()
    try:
        roles = db.query(Role).order_by(Role.name).all()
        
        role_list = []
        for role in roles:
            permissions = json.loads(role.permissions) if isinstance(role.permissions, str) else role.permissions
            role_list.append({
                'id': role.id,
                'name': role.name,
                'description': role.description,
                'is_system_role': role.is_system_role,
                'permissions': permissions,
                'created_at': role.created_at.isoformat() if hasattr(role.created_at, 'isoformat') else None
            })
        
        return create_success_response(data={'roles': role_list})
        
    finally:
        db.close()


@role_mgmt_bp.route('/permissions', methods=['GET'])
@require_permission('role.manage')
def get_all_permissions():
    """
    Get all available permissions with their descriptions.
    ---
    tags:
      - Role Management
    responses:
      200:
        description: List of all permissions
        schema:
          type: object
          properties:
            success:
              type: boolean
            permissions:
              type: object
              description: Object mapping permission names to descriptions
      403:
        description: Forbidden - requires role.manage permission
    """
    return create_success_response(data={'permissions': PERMISSION_DEFINITIONS})


@role_mgmt_bp.route('/users', methods=['GET'])
@require_permission('role.manage')
def get_user_roles():
    """
    Get all active users with their role assignments.
    ---
    tags:
      - Role Management
    responses:
      200:
        description: List of users with their roles
        schema:
          type: object
          properties:
            success:
              type: boolean
            users:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  username:
                    type: string
                  email:
                    type: string
                  is_active:
                    type: boolean
                  roles:
                    type: array
                    items:
                      type: object
                      properties:
                        role_id:
                          type: integer
                        role_name:
                          type: string
                        board_id:
                          type: integer
                          nullable: true
                        board_name:
                          type: string
                          nullable: true
                        assigned_at:
                          type: string
      403:
        description: Forbidden - requires role.manage permission
    """
    db = SessionLocal()
    try:
        # Get all active users
        users = db.query(User).filter(User.is_active).order_by(User.username).all()
        
        user_list = []
        for user in users:
            # Get all role assignments for this user
            role_assignments = db.query(UserRole, Role, Board).join(
                Role, UserRole.role_id == Role.id
            ).outerjoin(
                Board, UserRole.board_id == Board.id
            ).filter(
                UserRole.user_id == user.id
            ).order_by(Role.name).all()
            
            roles = []
            for user_role, role, board in role_assignments:
                roles.append({
                    'role_id': role.id,
                    'role_name': role.name,
                    'board_id': board.id if board else None,
                    'board_name': board.name if board else None,
                    'assigned_at': user_role.created_at.isoformat() if user_role.created_at else None
                })
            
            user_list.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'roles': roles
            })
        
        return create_success_response(data={'users': user_list})
        
    finally:
        db.close()


@role_mgmt_bp.route('/assign', methods=['POST'])
@require_permission('role.manage')
def assign_role_to_user():
    """
    Assign a role to a user.
    ---
    tags:
      - Role Management
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - user_id
            - role_id
          properties:
            user_id:
              type: integer
              description: ID of the user
            role_id:
              type: integer
              description: ID of the role to assign
            board_id:
              type: integer
              description: Optional board ID for board-specific roles
    responses:
      200:
        description: Role assigned successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid request
      403:
        description: Forbidden - requires role.manage permission
      404:
        description: User or role not found
      409:
        description: Role already assigned
    """
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'role_id' not in data:
        return create_error_response("user_id and role_id are required", 400)
    
    user_id = data['user_id']
    role_id = data['role_id']
    board_id = data.get('board_id')
    
    db = SessionLocal()
    try:
        # Verify user exists and is active
        user = db.query(User).filter(User.id == user_id, User.is_active).first()
        if not user:
            return create_error_response("User not found or inactive", 404)
        
        # Verify role exists
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return create_error_response("Role not found", 404)
        
        # Verify board exists if board_id provided
        if board_id:
            board = db.query(Board).filter(Board.id == board_id).first()
            if not board:
                return create_error_response("Board not found", 404)
        
        # Check if role already assigned
        existing = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.board_id == board_id
        ).first()
        
        if existing:
            scope = f" on board {board_id}" if board_id else " (global)"
            return create_error_response(
                f"User already has role '{role.name}'{scope}",
                409
            )
        
        # Create new role assignment
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            board_id=board_id
        )
        db.add(user_role)
        db.commit()
        
        scope = f" on board {board_id}" if board_id else " (global)"
        logger.info(f"Role '{role.name}' assigned to user {user.email}{scope} by admin {g.user.id}")
        
        return create_success_response(
            message=f"Role '{role.name}' assigned to {user.username}"
        )
        
    finally:
        db.close()


@role_mgmt_bp.route('/remove', methods=['POST'])
@require_permission('role.manage')
def remove_role_from_user():
    """
    Remove a role from a user.
    ---
    tags:
      - Role Management
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - user_id
            - role_id
          properties:
            user_id:
              type: integer
              description: ID of the user
            role_id:
              type: integer
              description: ID of the role to remove
            board_id:
              type: integer
              description: Optional board ID for board-specific roles (must match the assignment)
    responses:
      200:
        description: Role removed successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid request
      403:
        description: Forbidden - requires role.manage permission
      404:
        description: User, role, or role assignment not found
    """
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'role_id' not in data:
        return create_error_response("user_id and role_id are required", 400)
    
    user_id = data['user_id']
    role_id = data['role_id']
    board_id = data.get('board_id')
    
    db = SessionLocal()
    try:
        # Verify user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return create_error_response("User not found", 404)
        
        # Verify role exists
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return create_error_response("Role not found", 404)
        
        # Find the role assignment
        user_role = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.board_id == board_id
        ).first()
        
        if not user_role:
            scope = f" on board {board_id}" if board_id else " (global)"
            return create_error_response(
                f"User does not have role '{role.name}'{scope}",
                404
            )
        
        # Remove the role assignment
        db.delete(user_role)
        db.commit()
        
        scope = f" on board {board_id}" if board_id else " (global)"
        logger.info(f"Role '{role.name}' removed from user {user.email}{scope} by admin {g.user.id}")
        
        return create_success_response(
            message=f"Role '{role.name}' removed from {user.username}"
        )
        
    finally:
        db.close()


@role_mgmt_bp.route('/boards', methods=['GET'])
@require_permission('role.manage')
def get_boards_for_roles():
    """
    Get all boards for board-specific role assignments.
    ---
    tags:
      - Role Management
    responses:
      200:
        description: List of all boards
        schema:
          type: object
          properties:
            success:
              type: boolean
            boards:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
      403:
        description: Forbidden - requires role.manage permission
    """
    db = SessionLocal()
    try:
        boards = db.query(Board).order_by(Board.name).all()
        
        board_list = []
        for board in boards:
            board_list.append({
                'id': board.id,
                'name': board.name
            })
        
        return create_success_response(data={'boards': board_list})
        
    finally:
        db.close()
