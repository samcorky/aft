"""add user, role, and user_role tables for authentication and authorization

Revision ID: 020
Revises: 019
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func
import json

# revision identifiers, used by Alembic.
revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade():
    """Add users, roles, and user_roles tables."""
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('oauth_provider', sa.String(50), nullable=True),
        sa.Column('oauth_sub', sa.String(255), nullable=True),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes on users table
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_oauth_sub', 'users', ['oauth_sub'])
    op.create_index('ix_users_is_active', 'users', ['is_active'])
    op.create_index('idx_oauth_provider_sub', 'users', ['oauth_provider', 'oauth_sub'], unique=True)
    
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system_role', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('permissions', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes on roles table
    op.create_index('ix_roles_id', 'roles', ['id'])
    op.create_index('ix_roles_name', 'roles', ['name'], unique=True)
    
    # Create user_roles table (junction table)
    op.create_table(
        'user_roles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('board_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['board_id'], ['boards.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes on user_roles table
    op.create_index('ix_user_roles_id', 'user_roles', ['id'])
    op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'])
    op.create_index('ix_user_roles_board_id', 'user_roles', ['board_id'])
    op.create_index('idx_user_role_board', 'user_roles', ['user_id', 'role_id', 'board_id'], unique=True)
    
    # Insert initial roles
    from permissions import INITIAL_ROLES, get_role_permissions_json
    
    roles_data = []
    for role_name, role_info in INITIAL_ROLES.items():
        roles_data.append({
            'name': role_name,
            'description': role_info['description'],
            'is_system_role': role_info['is_system_role'],
            'permissions': get_role_permissions_json(role_name)
        })
    
    # Insert roles
    op.bulk_insert(
        sa.table('roles',
            sa.column('name', sa.String),
            sa.column('description', sa.Text),
            sa.column('is_system_role', sa.Boolean),
            sa.column('permissions', sa.Text)
        ),
        roles_data
    )
    
    # Create default admin user
    # Password will need to be set by the administrator on first login
    op.execute("""
        INSERT INTO users (email, username, display_name, is_active, email_verified)
        VALUES ('admin@localhost', 'admin', 'System Administrator', 1, 1)
    """)
    
    # Assign administrator role to the admin user
    op.execute("""
        INSERT INTO user_roles (user_id, role_id, board_id)
        SELECT u.id, r.id, NULL
        FROM users u
        CROSS JOIN roles r
        WHERE u.username = 'admin' AND r.name = 'administrator'
    """)


def downgrade():
    """Remove user_roles, roles, and users tables."""
    
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('user_roles')
    op.drop_table('roles')
    op.drop_table('users')
