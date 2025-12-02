"""add minimum free space setting

Revision ID: 010
Revises: 009
Create Date: 2025-12-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    """Add backup_minimum_free_space_mb setting with default of 100MB."""
    # Insert minimum free space setting only if it doesn't exist
    op.execute("""
        INSERT INTO settings (`key`, `value`)
        SELECT 
            'backup_minimum_free_space_mb',
            '100'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM settings WHERE `key` = 'backup_minimum_free_space_mb'
        )
    """)


def downgrade():
    """Remove backup_minimum_free_space_mb setting."""
    op.execute("DELETE FROM settings WHERE `key` = 'backup_minimum_free_space_mb'")
