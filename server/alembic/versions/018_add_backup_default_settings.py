"""add backup default settings

Revision ID: 018
Revises: 017
Create Date: 2026-01-25

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    """Add default backup settings to database.
    
    Ensures all required backup settings exist with sensible defaults:
    - Daily backups at midnight
    - 7 days retention
    - 100MB minimum free space
    """
    # Insert backup settings only if they don't exist
    # Using SELECT FROM DUAL pattern to conditionally insert
    
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 'backup_enabled', 'false'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_enabled'
        )
    """)
    
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 'backup_frequency_value', '1'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_frequency_value'
        )
    """)
    
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 'backup_frequency_unit', '"daily"'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_frequency_unit'
        )
    """)
    
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 'backup_start_time', '"00:00"'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_start_time'
        )
    """)
    
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 'backup_retention_count', '7'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_retention_count'
        )
    """)
    
    # Note: backup_minimum_free_space_mb already added in migration 010
    # but we ensure it here as well for completeness
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 'backup_minimum_free_space_mb', '100'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_minimum_free_space_mb'
        )
    """)


def downgrade():
    """Remove backup default settings."""
    op.execute("DELETE FROM settings WHERE `key` = 'backup_enabled'")
    op.execute("DELETE FROM settings WHERE `key` = 'backup_frequency_value'")
    op.execute("DELETE FROM settings WHERE `key` = 'backup_frequency_unit'")
    op.execute("DELETE FROM settings WHERE `key` = 'backup_start_time'")
    op.execute("DELETE FROM settings WHERE `key` = 'backup_retention_count'")
    # Note: Not removing backup_minimum_free_space_mb as it was added in migration 010
