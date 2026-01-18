"""add working_style setting

Revision ID: 016
Revises: 015
Create Date: 2026-01-18

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    """Add working_style setting with default value of 'kanban'."""
    from sqlalchemy.sql import table, column
    from sqlalchemy import String, insert
    
    # Define a minimal settings table for the insert operation
    settings_table = table('settings',
        column('key', String),
        column('value', String)
    )
    
    # Insert working_style setting with default value 'kanban'
    op.execute(
        insert(settings_table).values(
            key='working_style',
            value='"kanban"'  # JSON-encoded string
        )
    )


def downgrade():
    """Remove working_style setting."""
    op.execute("DELETE FROM settings WHERE key = 'working_style'")
