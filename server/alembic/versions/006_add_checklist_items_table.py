"""add checklist_items table

Revision ID: 006
Revises: 005
Create Date: 2025-11-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create checklist_items table."""
    # Check if table already exists
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    if 'checklist_items' not in tables:
        op.create_table(
            'checklist_items',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('card_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=500), nullable=False),
            sa.Column('checked', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
            sa.ForeignKeyConstraint(['card_id'], ['cards.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_checklist_items_id'), 'checklist_items', ['id'], unique=False)
        op.create_index(op.f('ix_checklist_items_card_id'), 'checklist_items', ['card_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Drop checklist_items table."""
    # Check if table exists before dropping
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    if 'checklist_items' in tables:
        op.drop_index(op.f('ix_checklist_items_card_id'), table_name='checklist_items')
        op.drop_index(op.f('ix_checklist_items_id'), table_name='checklist_items')
        op.drop_table('checklist_items')
    # ### end Alembic commands ###
