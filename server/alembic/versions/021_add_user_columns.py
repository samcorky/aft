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
    
    # ========================================================================
    # Phase 1: Add nullable columns
    # ========================================================================
    
    # Add owner_id to boards (will be required)
    op.add_column('boards', sa.Column('owner_id', sa.Integer(), nullable=True))
    
    # Add created_by_id and assigned_to_id to cards (optional)
    op.add_column('cards', sa.Column('created_by_id', sa.Integer(), nullable=True))
    op.add_column('cards', sa.Column('assigned_to_id', sa.Integer(), nullable=True))
    
    # Add user_id to settings (optional - NULL means global setting)
    op.add_column('settings', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # Add user_id to themes (optional - NULL means system theme)
    op.add_column('themes', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # Add user_id to notifications (will be required)
    op.add_column('notifications', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # ========================================================================
    # Phase 2: Backfill existing data with admin user
    # ========================================================================
    
    # Get the admin user ID
    op.execute("""
        SET @admin_user_id = (SELECT id FROM users WHERE username = 'admin' LIMIT 1);
    """)
    
    # Backfill boards with admin as owner
    op.execute("""
        UPDATE boards SET owner_id = @admin_user_id WHERE owner_id IS NULL;
    """)
    
    # Backfill cards with admin as creator (assigned_to remains NULL)
    op.execute("""
        UPDATE cards SET created_by_id = @admin_user_id WHERE created_by_id IS NULL;
    """)
    
    # Leave settings.user_id as NULL (they are global settings)
    # Leave themes.user_id as NULL (they are system themes)
    
    # Backfill notifications with admin user
    op.execute("""
        UPDATE notifications SET user_id = @admin_user_id WHERE user_id IS NULL;
    """)
    
    # ========================================================================
    # Phase 3: Add foreign key constraints and make required columns NOT NULL
    # ========================================================================
    
    # Make boards.owner_id required and add foreign key
    op.alter_column('boards', 'owner_id', nullable=False, existing_type=sa.Integer())
    op.create_foreign_key('fk_boards_owner_id', 'boards', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_boards_owner_id', 'boards', ['owner_id'])
    
    # Add foreign keys for cards (but keep them nullable)
    op.create_foreign_key('fk_cards_created_by_id', 'cards', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_cards_assigned_to_id', 'cards', 'users', ['assigned_to_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_cards_created_by_id', 'cards', ['created_by_id'])
    op.create_index('ix_cards_assigned_to_id', 'cards', ['assigned_to_id'])
    
    # Add foreign key for settings (nullable - NULL means global)
    op.create_foreign_key('fk_settings_user_id', 'settings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_settings_user_id', 'settings', ['user_id'])
    
    # Add foreign key for themes (nullable - NULL means system theme)
    op.create_foreign_key('fk_themes_user_id', 'themes', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_themes_user_id', 'themes', ['user_id'])
    
    # Make notifications.user_id required and add foreign key
    op.alter_column('notifications', 'user_id', nullable=False, existing_type=sa.Integer())
    op.create_foreign_key('fk_notifications_user_id', 'notifications', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    
    # ========================================================================
    # Phase 4: Update unique constraints for multi-tenant tables
    # ========================================================================
    
    # Drop the old unique constraint on themes.name and create composite unique index
    # System themes (user_id IS NULL) must have unique names globally
    # User themes are unique per user
    op.drop_index('name', 'themes')  # Drop the old UNIQUE constraint
    op.create_index('idx_theme_user_name', 'themes', ['user_id', 'name'], unique=True)
    
    # Drop the old unique constraint on settings.key and create composite unique index
    # Each user can have their own value for each setting key
    op.drop_index('key', 'settings')  # Drop the old UNIQUE constraint
    op.create_index('idx_user_setting_key', 'settings', ['user_id', 'key'], unique=True)


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
    op.drop_index('idx_theme_user_name', 'themes')
    op.drop_index('idx_user_setting_key', 'settings')
    
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
