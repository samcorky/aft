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
    bind = op.get_bind()

    def table_exists(table_name):
        inspector = sa.inspect(bind)
        return table_name in inspector.get_table_names()

    def index_exists(table_name, index_name):
        inspector = sa.inspect(bind)
        return any(idx.get('name') == index_name for idx in inspector.get_indexes(table_name))

    def column_exists(table_name, column_name):
        inspector = sa.inspect(bind)
        return any(col.get('name') == column_name for col in inspector.get_columns(table_name))
    
    # Create users table
    if not table_exists('users'):
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
    if table_exists('users') and not index_exists('users', 'ix_users_id'):
        op.create_index('ix_users_id', 'users', ['id'])
    if table_exists('users') and not index_exists('users', 'ix_users_email'):
        op.create_index('ix_users_email', 'users', ['email'], unique=True)
    if table_exists('users') and not index_exists('users', 'ix_users_username'):
        op.create_index('ix_users_username', 'users', ['username'], unique=True)
    if table_exists('users') and not index_exists('users', 'ix_users_oauth_sub'):
        op.create_index('ix_users_oauth_sub', 'users', ['oauth_sub'])
    if table_exists('users') and not index_exists('users', 'ix_users_is_active'):
        op.create_index('ix_users_is_active', 'users', ['is_active'])
    if table_exists('users') and not index_exists('users', 'idx_oauth_provider_sub'):
        op.create_index('idx_oauth_provider_sub', 'users', ['oauth_provider', 'oauth_sub'], unique=True)
    
    # Create roles table
    if not table_exists('roles'):
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
    if table_exists('roles') and not index_exists('roles', 'ix_roles_id'):
        op.create_index('ix_roles_id', 'roles', ['id'])
    if table_exists('roles') and not index_exists('roles', 'ix_roles_name'):
        op.create_index('ix_roles_name', 'roles', ['name'], unique=True)
    
    # Create user_roles table (junction table)
    if not table_exists('user_roles'):
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
    if table_exists('user_roles') and not index_exists('user_roles', 'ix_user_roles_id'):
        op.create_index('ix_user_roles_id', 'user_roles', ['id'])
    if table_exists('user_roles') and not index_exists('user_roles', 'ix_user_roles_user_id'):
        op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    if table_exists('user_roles') and not index_exists('user_roles', 'ix_user_roles_role_id'):
        op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'])
    if table_exists('user_roles') and not index_exists('user_roles', 'ix_user_roles_board_id'):
        op.create_index('ix_user_roles_board_id', 'user_roles', ['board_id'])
    if table_exists('user_roles') and not index_exists('user_roles', 'idx_user_role_board'):
        op.create_index('idx_user_role_board', 'user_roles', ['user_id', 'role_id', 'board_id'], unique=True)
    
    # Insert initial roles
    # Define roles statically to avoid import path issues during migration
    INITIAL_ROLES = {
        'administrator': {
            'description': '[GLOBAL] Full system administration - can see and manage everything',
            'is_system_role': True,
            'permissions': [
                'system.admin', 'monitoring.system', 'admin.database', 'user.manage',
                'user.role', 'role.manage', 'board.create', 'board.view', 'board.edit',
                'board.delete', 'card.create', 'card.view', 'card.edit', 'card.update',
                'card.delete', 'card.archive', 'column.create', 'column.update',
                'column.delete', 'schedule.create', 'schedule.view', 'schedule.edit',
                'schedule.delete', 'setting.view', 'setting.edit', 'theme.create',
                'theme.view', 'theme.edit', 'theme.delete',
            ]
        },
        'board_creator': {
            'description': '[GLOBAL] Can create new boards (and automatically owns them with full control)',
            'is_system_role': True,
            'permissions': [
                'board.create', 'theme.create', 'theme.view', 'theme.edit',
                'theme.delete', 'setting.view', 'setting.edit',
            ]
        },
        'board_editor': {
            'description': '[BOARD-SPECIFIC] Full control of the assigned board - can manage everything on it',
            'is_system_role': True,
            'permissions': [
                'board.view', 'board.edit', 'board.delete', 'card.create', 'card.view',
                'card.edit', 'card.update', 'card.delete', 'card.archive', 'column.create',
                'column.update', 'column.delete', 'schedule.create', 'schedule.view',
                'schedule.edit', 'schedule.delete', 'setting.view', 'setting.edit',
                'theme.create', 'theme.view', 'theme.edit', 'theme.delete',
            ]
        },
        'board_viewer': {
            'description': '[BOARD-SPECIFIC] Read-only access to the assigned board - cannot edit anything',
            'is_system_role': True,
            'permissions': [
                'board.view', 'card.view', 'schedule.view', 'setting.view', 'theme.view',
            ]
        }
    }
    
    roles_data = []
    for role_name, role_info in INITIAL_ROLES.items():
        roles_data.append({
            'name': role_name,
            'description': role_info['description'],
            'is_system_role': role_info['is_system_role'],
            'permissions': json.dumps(role_info['permissions'])
        })
    
    # Insert roles idempotently
    for role in roles_data:
        bind.execute(
            sa.text(
                """
                INSERT INTO roles (name, description, is_system_role, permissions)
                SELECT :name, :description, :is_system_role, :permissions
                WHERE NOT EXISTS (
                    SELECT 1 FROM roles WHERE name = :name
                )
                """
            ),
            role
        )
    
    # Create default admin user
    # Password will need to be set by the administrator on first login
    if column_exists('users', 'is_approved'):
        op.execute("""
            INSERT INTO users (email, username, display_name, is_active, email_verified, is_approved)
            SELECT 'admin@localhost', 'admin', 'System Administrator', 1, 1, 1
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin')
        """)
    else:
        op.execute("""
            INSERT INTO users (email, username, display_name, is_active, email_verified)
            SELECT 'admin@localhost', 'admin', 'System Administrator', 1, 1
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin')
        """)
    
    # Assign administrator role to the admin user
    op.execute("""
        INSERT INTO user_roles (user_id, role_id, board_id)
        SELECT u.id, r.id, NULL
        FROM users u
        CROSS JOIN roles r
        WHERE u.username = 'admin' AND r.name = 'administrator'
        AND NOT EXISTS (
            SELECT 1
            FROM user_roles ur
            WHERE ur.user_id = u.id AND ur.role_id = r.id AND ur.board_id IS NULL
        )
    """)


def downgrade():
    """Remove user_roles, roles, and users tables."""
    
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('user_roles')
    op.drop_table('roles')
    op.drop_table('users')
