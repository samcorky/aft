"""add columns table

Revision ID: 002
Revises: 001
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create columns table."""
    op.create_table(
        'columns',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('board_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['board_id'], ['boards.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_columns_id'), 'columns', ['id'], unique=False)
    op.create_index(op.f('ix_columns_board_id'), 'columns', ['board_id'], unique=False)


def downgrade() -> None:
    """Drop columns table."""
    op.drop_index(op.f('ix_columns_board_id'), table_name='columns')
    op.drop_index(op.f('ix_columns_id'), table_name='columns')
    op.drop_table('columns')
