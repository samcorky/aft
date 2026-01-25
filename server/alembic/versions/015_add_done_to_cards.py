"""add done column to cards

Revision ID: 015
Revises: 014
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    """Add done column to cards table with default value of False."""
    op.add_column('cards', sa.Column('done', sa.Boolean(), nullable=False, server_default='0', index=True))


def downgrade():
    """Remove done column from cards table."""
    op.drop_column('cards', 'done')
