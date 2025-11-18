"""add comments table

Revision ID: 007
Revises: 006
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    """Create comments table for card journal comments."""
    op.create_table(
        'comments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['card_id'], ['cards.id'], ondelete='CASCADE'),
    )
    
    # Create indexes
    op.create_index('ix_comments_id', 'comments', ['id'])
    op.create_index('ix_comments_card_id', 'comments', ['card_id'])
    op.create_index('ix_comments_order', 'comments', ['order'])


def downgrade():
    """Drop comments table."""
    op.drop_index('ix_comments_order', table_name='comments')
    op.drop_index('ix_comments_card_id', table_name='comments')
    op.drop_index('ix_comments_id', table_name='comments')
    op.drop_table('comments')
