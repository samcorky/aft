"""add scheduled cards

Revision ID: 011
Revises: 010
Create Date: 2025-12-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    """Create scheduled_cards table and add scheduling columns to cards table."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Create scheduled_cards table if it doesn't exist
    if 'scheduled_cards' not in inspector.get_table_names():
        op.create_table(
            'scheduled_cards',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('card_id', sa.Integer(), nullable=False),
            sa.Column('run_every', sa.Integer(), nullable=False),
            sa.Column('unit', sa.String(10), nullable=False),
            sa.Column('start_datetime', sa.DateTime(), nullable=False),
            sa.Column('end_datetime', sa.DateTime(), nullable=True),
            sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('allow_duplicates', sa.Boolean(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['card_id'], ['cards.id'], ondelete='CASCADE')
        )
        op.create_index('ix_scheduled_cards_id', 'scheduled_cards', ['id'])
        op.create_index('ix_scheduled_cards_card_id', 'scheduled_cards', ['card_id'])
        op.create_index('ix_scheduled_cards_enabled', 'scheduled_cards', ['schedule_enabled'])
    
    # Add scheduled and schedule columns to cards table if they don't exist
    existing_columns = [col['name'] for col in inspector.get_columns('cards')]
    
    if 'scheduled' not in existing_columns:
        op.add_column('cards', sa.Column('scheduled', sa.Boolean(), nullable=False, server_default='0'))
        op.create_index('ix_cards_scheduled', 'cards', ['scheduled'])
    
    if 'schedule' not in existing_columns:
        op.add_column('cards', sa.Column('schedule', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_cards_schedule', 'cards', 'scheduled_cards', ['schedule'], ['id'], ondelete='SET NULL')
        op.create_index('ix_cards_schedule', 'cards', ['schedule'])


def downgrade():
    """Drop scheduled_cards table and remove scheduling columns from cards table."""
    # Drop foreign key and indexes from cards table
    op.drop_index('ix_cards_schedule', table_name='cards')
    op.drop_constraint('fk_cards_schedule', 'cards', type_='foreignkey')
    op.drop_column('cards', 'schedule')
    
    op.drop_index('ix_cards_scheduled', table_name='cards')
    op.drop_column('cards', 'scheduled')
    
    # Drop scheduled_cards table
    op.drop_index('ix_scheduled_cards_enabled', table_name='scheduled_cards')
    op.drop_index('ix_scheduled_cards_card_id', table_name='scheduled_cards')
    op.drop_index('ix_scheduled_cards_id', table_name='scheduled_cards')
    op.drop_table('scheduled_cards')
