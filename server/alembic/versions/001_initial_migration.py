"""Initial migration - create boards table

Revision ID: 001
Revises: 
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create boards table."""
    op.create_table(
        'boards',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_boards_id'), 'boards', ['id'], unique=False)


def downgrade() -> None:
    """Drop boards table."""
    op.drop_index(op.f('ix_boards_id'), table_name='boards')
    op.drop_table('boards')
