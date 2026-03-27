"""Add card secondary assignees and profile colour defaulting.

Revision ID: 024
Revises: 023
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    """Create secondary assignee table and add non-null profile_colour for users."""

    op.create_table(
        'card_secondary_assignees',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('card_id', sa.Integer(), sa.ForeignKey('cards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=True),
    )
    op.create_index('ix_card_secondary_assignees_card_id', 'card_secondary_assignees', ['card_id'])
    op.create_index('ix_card_secondary_assignees_user_id', 'card_secondary_assignees', ['user_id'])
    op.create_index(
        'idx_card_secondary_assignee_unique',
        'card_secondary_assignees',
        ['card_id', 'user_id'],
        unique=True,
    )

    op.add_column(
        'users',
        sa.Column('profile_colour', sa.String(7), nullable=True, server_default='#90A4AE')
    )
    op.execute("UPDATE users SET profile_colour = '#90A4AE' WHERE profile_colour IS NULL")
    op.alter_column(
        'users',
        'profile_colour',
        existing_type=sa.String(length=7),
        nullable=False,
        server_default='#90A4AE',
    )


def downgrade():
    """Remove secondary assignee table and profile_colour column."""
    op.drop_column('users', 'profile_colour')
    op.drop_index('idx_card_secondary_assignee_unique', table_name='card_secondary_assignees')
    op.drop_index('ix_card_secondary_assignees_user_id', table_name='card_secondary_assignees')
    op.drop_index('ix_card_secondary_assignees_card_id', table_name='card_secondary_assignees')
    op.drop_table('card_secondary_assignees')
