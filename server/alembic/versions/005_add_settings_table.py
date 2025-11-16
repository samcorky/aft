"""add settings table

Revision ID: 005
Revises: 004
Create Date: 2025-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create settings table with default settings."""
    # Check if table already exists
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    if 'settings' not in tables:
        op.create_table(
            'settings',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('key', sa.String(length=255), nullable=False),
            sa.Column('value', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('key')
        )
        op.create_index(op.f('ix_settings_id'), 'settings', ['id'], unique=False)
        op.create_index(op.f('ix_settings_key'), 'settings', ['key'], unique=True)
        
        # Insert default settings using parameterized query for portability and security
        # Note: 'key' is a MySQL reserved word, so we quote it with backticks
        op.execute(
            sa.text("INSERT INTO settings (`key`, `value`) VALUES (:key, :value)").bindparams(
                key='default_board',
                value='null'
            )
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Drop settings table."""
    # Check if table exists before dropping
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    if 'settings' in tables:
        op.drop_index(op.f('ix_settings_key'), table_name='settings')
        op.drop_index(op.f('ix_settings_id'), table_name='settings')
        op.drop_table('settings')
    # ### end Alembic commands ###
