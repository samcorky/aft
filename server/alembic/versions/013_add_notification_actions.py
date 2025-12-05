"""add notification actions

Revision ID: 013
Revises: 012
Create Date: 2025-12-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    """Add action_title and action_url columns to notifications table."""
    # Check if columns already exist before adding (idempotent)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if 'notifications' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('notifications')]
        
        if 'action_title' not in columns:
            op.add_column('notifications', sa.Column('action_title', sa.String(100), nullable=True))
        
        if 'action_url' not in columns:
            op.add_column('notifications', sa.Column('action_url', sa.String(500), nullable=True))


def downgrade():
    """Remove action_title and action_url columns from notifications table."""
    op.drop_column('notifications', 'action_url')
    op.drop_column('notifications', 'action_title')
