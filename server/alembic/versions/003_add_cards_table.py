"""add cards table

Revision ID: 003
Revises: 002
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cards table."""
    op.create_table(
        'cards',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('column_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=2000), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['column_id'], ['columns.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_cards_id'), 'cards', ['id'], unique=False)
    op.create_index(op.f('ix_cards_column_id'), 'cards', ['column_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Drop cards table."""
    op.drop_index(op.f('ix_cards_column_id'), table_name='cards')
    op.drop_index(op.f('ix_cards_id'), table_name='cards')
    op.drop_table('cards')
    # ### end Alembic commands ###
