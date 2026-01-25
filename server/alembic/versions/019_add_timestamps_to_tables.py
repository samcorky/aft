"""add timestamps to boards, columns, cards, and checklist_items

Revision ID: 019
Revises: 018
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    """Add created_at and updated_at timestamps to boards, columns, cards, and checklist_items.
    
    Existing records will have NULL timestamps to accurately represent that we don't know
    when they were created/updated. New records will automatically get timestamps.
    """
    
    # Add timestamps to boards table (nullable for existing records)
    op.add_column('boards', sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=True))
    op.add_column('boards', sa.Column('updated_at', sa.DateTime(), server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=True))
    # Set existing records to NULL
    op.execute('UPDATE boards SET created_at = NULL, updated_at = NULL')
    
    # Add timestamps to columns table (nullable for existing records)
    op.add_column('columns', sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=True))
    op.add_column('columns', sa.Column('updated_at', sa.DateTime(), server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=True))
    # Set existing records to NULL
    op.execute('UPDATE columns SET created_at = NULL, updated_at = NULL')
    
    # Add timestamps to cards table (nullable for existing records)
    op.add_column('cards', sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=True))
    op.add_column('cards', sa.Column('updated_at', sa.DateTime(), server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=True))
    # Set existing records to NULL
    op.execute('UPDATE cards SET created_at = NULL, updated_at = NULL')
    
    # Add timestamps to checklist_items table (nullable for existing records)
    op.add_column('checklist_items', sa.Column('created_at', sa.DateTime(), server_default=func.current_timestamp(), nullable=True))
    op.add_column('checklist_items', sa.Column('updated_at', sa.DateTime(), server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=True))
    # Set existing records to NULL
    op.execute('UPDATE checklist_items SET created_at = NULL, updated_at = NULL')


def downgrade():
    """Remove created_at and updated_at timestamps from boards, columns, cards, and checklist_items."""
    
    # Remove timestamps from checklist_items table
    op.drop_column('checklist_items', 'updated_at')
    op.drop_column('checklist_items', 'created_at')
    
    # Remove timestamps from cards table
    op.drop_column('cards', 'updated_at')
    op.drop_column('cards', 'created_at')
    
    # Remove timestamps from columns table
    op.drop_column('columns', 'updated_at')
    op.drop_column('columns', 'created_at')
    
    # Remove timestamps from boards table
    op.drop_column('boards', 'updated_at')
    op.drop_column('boards', 'created_at')
