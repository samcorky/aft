"""add archived column to cards

Revision ID: 008
Revises: 007
Create Date: 2025-11-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Add archived boolean column to cards table."""
    op.add_column('cards', sa.Column('archived', sa.Boolean(), nullable=False, server_default='0'))
    
    # Create index on archived column for efficient filtering
    op.create_index('ix_cards_archived', 'cards', ['archived'])


def downgrade():
    """Remove archived column from cards table."""
    op.drop_index('ix_cards_archived', table_name='cards')
    op.drop_column('cards', 'archived')
