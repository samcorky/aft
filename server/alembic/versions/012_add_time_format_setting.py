"""add time format setting

Revision ID: 012
Revises: 011
Create Date: 2025-12-05

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    """Add time_format setting with default value of '24'."""
    from sqlalchemy.sql import table, column
    from sqlalchemy import String, insert
    
    # Define a minimal settings table for the insert operation
    settings_table = table('settings',
        column('key', String),
        column('value', String)
    )
    
    # Insert time_format setting with default value '24' (24-hour format)
    op.execute(
        insert(settings_table).values(
            key='time_format',
            value='"24"'  # JSON-encoded string
        )
    )


def downgrade():
    """Remove time_format setting."""
    op.execute("DELETE FROM settings WHERE key = 'time_format'")
