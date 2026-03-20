"""add user_id and owner_id columns to existing tables for multi-tenant support

Revision ID: 021
Revises: 020
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    """Add user_id/owner_id columns to existing tables and backfill with admin user.
    
    Phase 1: Add columns as NULLABLE
    Phase 2: Backfill with admin user ID
    Phase 3: Make columns NOT NULL where appropriate
    """
    bind = op.get_bind()

    def table_exists(table_name):
        inspector = sa.inspect(bind)
        return table_name in inspector.get_table_names()

    def column_exists(table_name, column_name):
        if not table_exists(table_name):
            return False
        inspector = sa.inspect(bind)
        return any(col.get('name') == column_name for col in inspector.get_columns(table_name))

    def index_exists(table_name, index_name):
        if not table_exists(table_name):
            return False
        inspector = sa.inspect(bind)
        return any(idx.get('name') == index_name for idx in inspector.get_indexes(table_name))

    def fk_exists(table_name, fk_name):
        if not table_exists(table_name):
            return False
        inspector = sa.inspect(bind)
        return any(fk.get('name') == fk_name for fk in inspector.get_foreign_keys(table_name))
    
    # ========================================================================
    # Phase 1: Add nullable columns
    # ========================================================================
    
    # Add owner_id to boards (will be required)
    if table_exists('boards') and not column_exists('boards', 'owner_id'):
        op.add_column('boards', sa.Column('owner_id', sa.Integer(), nullable=True))
    
    # Add created_by_id and assigned_to_id to cards (optional)
    if table_exists('cards') and not column_exists('cards', 'created_by_id'):
        op.add_column('cards', sa.Column('created_by_id', sa.Integer(), nullable=True))
    if table_exists('cards') and not column_exists('cards', 'assigned_to_id'):
        op.add_column('cards', sa.Column('assigned_to_id', sa.Integer(), nullable=True))
    
    # Add user_id to settings (optional - NULL means global setting)
    if table_exists('settings') and not column_exists('settings', 'user_id'):
        op.add_column('settings', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # Add user_id to themes (optional - NULL means system theme)
    if table_exists('themes') and not column_exists('themes', 'user_id'):
        op.add_column('themes', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # Add user_id to notifications (will be required)
    if table_exists('notifications') and not column_exists('notifications', 'user_id'):
        op.add_column('notifications', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # ========================================================================
    # Phase 2: Backfill existing data with admin user
    # ========================================================================
    
    # Get the admin user ID
    if table_exists('users') and column_exists('users', 'id'):
        op.execute("""
            SET @admin_user_id = (SELECT id FROM users WHERE username = 'admin' LIMIT 1);
        """)
    
    # Backfill boards with admin as owner
    if table_exists('boards') and column_exists('boards', 'owner_id'):
        op.execute("""
            UPDATE boards SET owner_id = @admin_user_id WHERE owner_id IS NULL;
        """)
    
    # Backfill cards with admin as creator (assigned_to remains NULL)
    if table_exists('cards') and column_exists('cards', 'created_by_id'):
        op.execute("""
            UPDATE cards SET created_by_id = @admin_user_id WHERE created_by_id IS NULL;
        """)
    
    # Backfill user-specific settings (from settings.html page) with admin user
    # Backup, housekeeping, and card scheduler settings remain global (user_id = NULL)
    if table_exists('settings') and column_exists('settings', 'user_id'):
        op.execute("""
            UPDATE settings 
            SET user_id = @admin_user_id 
            WHERE user_id IS NULL
            AND `key` IN ('default_board', 'time_format', 'working_style', 'selected_theme');
        """)
    
    # Leave themes.user_id as NULL (they are system themes)
    
    # Backfill notifications with admin user
    if table_exists('notifications') and column_exists('notifications', 'user_id'):
        op.execute("""
            UPDATE notifications SET user_id = @admin_user_id WHERE user_id IS NULL;
        """)
    
    # ========================================================================
    # Phase 3: Add foreign key constraints and make required columns NOT NULL
    # ========================================================================
    
    # Make boards.owner_id required and add foreign key
    if table_exists('boards') and column_exists('boards', 'owner_id'):
        op.alter_column('boards', 'owner_id', nullable=False, existing_type=sa.Integer())
        if not fk_exists('boards', 'fk_boards_owner_id'):
            op.create_foreign_key('fk_boards_owner_id', 'boards', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
        if not index_exists('boards', 'ix_boards_owner_id'):
            op.create_index('ix_boards_owner_id', 'boards', ['owner_id'])
    
    # Add foreign keys for cards (but keep them nullable)
    if table_exists('cards') and column_exists('cards', 'created_by_id'):
        if not fk_exists('cards', 'fk_cards_created_by_id'):
            op.create_foreign_key('fk_cards_created_by_id', 'cards', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')
        if not index_exists('cards', 'ix_cards_created_by_id'):
            op.create_index('ix_cards_created_by_id', 'cards', ['created_by_id'])
    if table_exists('cards') and column_exists('cards', 'assigned_to_id'):
        if not fk_exists('cards', 'fk_cards_assigned_to_id'):
            op.create_foreign_key('fk_cards_assigned_to_id', 'cards', 'users', ['assigned_to_id'], ['id'], ondelete='SET NULL')
        if not index_exists('cards', 'ix_cards_assigned_to_id'):
            op.create_index('ix_cards_assigned_to_id', 'cards', ['assigned_to_id'])
    
    # Add foreign key for settings (nullable - NULL means global)
    if table_exists('settings') and column_exists('settings', 'user_id'):
        if not fk_exists('settings', 'fk_settings_user_id'):
            op.create_foreign_key('fk_settings_user_id', 'settings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        if not index_exists('settings', 'ix_settings_user_id'):
            op.create_index('ix_settings_user_id', 'settings', ['user_id'])
    
    # Add foreign key for themes (nullable - NULL means system theme)
    if table_exists('themes') and column_exists('themes', 'user_id'):
        if not fk_exists('themes', 'fk_themes_user_id'):
            op.create_foreign_key('fk_themes_user_id', 'themes', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        if not index_exists('themes', 'ix_themes_user_id'):
            op.create_index('ix_themes_user_id', 'themes', ['user_id'])
    
    # Make notifications.user_id required and add foreign key
    if table_exists('notifications') and column_exists('notifications', 'user_id'):
        op.alter_column('notifications', 'user_id', nullable=False, existing_type=sa.Integer())
        if not fk_exists('notifications', 'fk_notifications_user_id'):
            op.create_foreign_key('fk_notifications_user_id', 'notifications', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        if not index_exists('notifications', 'ix_notifications_user_id'):
            op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    
    # ========================================================================
    # Phase 4: Update unique constraints for multi-tenant tables
    # ========================================================================
    
    # Drop the old unique constraint on themes.name and create scope-normalized unique index.
    # COALESCE(user_id, 0) ensures system themes (NULL user_id) are globally unique by name.
    if table_exists('themes') and index_exists('themes', 'name'):
        op.drop_index('name', 'themes')  # Drop old UNIQUE constraint variant
    if table_exists('themes') and index_exists('themes', 'ix_themes_name'):
        op.drop_index('ix_themes_name', 'themes')  # Drop old UNIQUE constraint variant
    if table_exists('themes') and index_exists('themes', 'idx_theme_user_name'):
        op.drop_index('idx_theme_user_name', 'themes')
    if table_exists('themes') and not index_exists('themes', 'idx_theme_owner_scope_name'):
        op.create_index(
            'idx_theme_owner_scope_name',
            'themes',
            [sa.text('(coalesce(user_id, 0))'), 'name'],
            unique=True,
        )
    
    # Drop the old unique constraint on settings.key and create scope-normalized unique index.
    # COALESCE(user_id, 0) ensures global settings (NULL user_id) are unique per key.
    if table_exists('settings') and index_exists('settings', 'key'):
        op.drop_index('key', 'settings')  # Drop old UNIQUE constraint variant
    if table_exists('settings') and index_exists('settings', 'ix_settings_key'):
        op.drop_index('ix_settings_key', 'settings')  # Drop old UNIQUE constraint variant
    if table_exists('settings') and index_exists('settings', 'idx_user_setting_key'):
        op.drop_index('idx_user_setting_key', 'settings')
    if table_exists('settings') and not index_exists('settings', 'idx_setting_scope_key'):
        op.create_index(
            'idx_setting_scope_key',
            'settings',
            [sa.text('(coalesce(user_id, 0))'), 'key'],
            unique=True,
        )
    
    # ========================================================================
    # Phase 5: Create default settings for all non-admin users
    # ========================================================================
    
    # Copy only user-specific settings (from settings.html page) to other users
    # Backup, housekeeping, and card scheduler settings remain global (user_id = NULL)
    if table_exists('users') and table_exists('settings') and column_exists('settings', 'user_id'):
        op.execute("""
            INSERT IGNORE INTO settings (`key`, `value`, user_id)
            SELECT s.`key`, s.`value`, u.id
            FROM users u
            CROSS JOIN (
                SELECT DISTINCT `key`, `value` 
                FROM settings 
                WHERE user_id = @admin_user_id
                AND `key` IN ('default_board', 'time_format', 'working_style', 'selected_theme')
            ) s
            WHERE u.username != 'admin'
            AND NOT EXISTS (
                SELECT 1 FROM settings s2 
                WHERE s2.user_id = u.id AND s2.`key` = s.`key`
            )
        """)


def downgrade():
    """Remove user_id/owner_id columns and restore original constraints."""
    
    # Drop foreign keys and indexes
    op.drop_constraint('fk_boards_owner_id', 'boards', type_='foreignkey')
    op.drop_index('ix_boards_owner_id', 'boards')
    
    op.drop_constraint('fk_cards_created_by_id', 'cards', type_='foreignkey')
    op.drop_constraint('fk_cards_assigned_to_id', 'cards', type_='foreignkey')
    op.drop_index('ix_cards_created_by_id', 'cards')
    op.drop_index('ix_cards_assigned_to_id', 'cards')
    
    op.drop_constraint('fk_settings_user_id', 'settings', type_='foreignkey')
    op.drop_index('ix_settings_user_id', 'settings')
    
    op.drop_constraint('fk_themes_user_id', 'themes', type_='foreignkey')
    op.drop_index('ix_themes_user_id', 'themes')
    
    op.drop_constraint('fk_notifications_user_id', 'notifications', type_='foreignkey')
    op.drop_index('ix_notifications_user_id', 'notifications')
    
    # Drop composite indexes
    op.drop_index('idx_theme_owner_scope_name', 'themes')
    op.drop_index('idx_setting_scope_key', 'settings')
    
    # Restore original unique constraints
    op.create_index('name', 'themes', ['name'], unique=True)
    op.create_index('key', 'settings', ['key'], unique=True)
    
    # Drop columns
    op.drop_column('boards', 'owner_id')
    op.drop_column('cards', 'created_by_id')
    op.drop_column('cards', 'assigned_to_id')
    op.drop_column('settings', 'user_id')
    op.drop_column('themes', 'user_id')
    op.drop_column('notifications', 'user_id')
