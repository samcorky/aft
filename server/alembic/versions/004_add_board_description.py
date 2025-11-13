"""add board description

Revision ID: 004
Revises: 003
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add description column to boards table."""
    # Check if column already exists
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('boards')]
    
    if 'description' not in columns:
        op.add_column('boards', sa.Column('description', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Remove description column from boards table."""
    op.drop_column('boards', 'description')
    # ### end Alembic commands ###
