"""Add board_settings table and rename working style value.

Revision ID: 025
Revises: 024
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    """Create board_settings and normalize legacy working style value."""
    op.create_table(
        'board_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('board_id', sa.Integer(), sa.ForeignKey('boards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
    )
    op.create_index('ix_board_settings_board_id', 'board_settings', ['board_id'])
    op.create_index('ix_board_settings_key', 'board_settings', ['key'])
    op.create_index('idx_board_setting_key', 'board_settings', ['board_id', 'key'], unique=True)

    # Normalize legacy working style naming in user settings.
    op.execute(
        """
        UPDATE settings
        SET `value` = '"agile"'
        WHERE `key` = 'working_style' AND `value` = '"board_task_category"'
        """
    )

    # Populate board_settings for all existing boards using their owner's working style.
    # For each board, insert a working_style setting based on the board owner's user setting.
    op.execute(
        """
        INSERT INTO board_settings (board_id, key, value)
        SELECT 
            b.id,
            'working_style',
            COALESCE(
                (SELECT s.value 
                 FROM settings s 
                 WHERE s.user_id = b.owner_id AND s.key = 'working_style' 
                 LIMIT 1),
                '"agile"'
            )
        FROM boards b
        WHERE b.id NOT IN (
            SELECT DISTINCT board_id FROM board_settings WHERE key = 'working_style'
        )
        """
    )


def downgrade():
    """Drop board_settings and restore legacy working style value naming."""
    op.execute(
        """
        UPDATE settings
        SET `value` = '"board_task_category"'
        WHERE `key` = 'working_style' AND `value` = '"agile"'
        """
    )

    op.drop_index('idx_board_setting_key', table_name='board_settings')
    op.drop_index('ix_board_settings_key', table_name='board_settings')
    op.drop_index('ix_board_settings_board_id', table_name='board_settings')
    op.drop_table('board_settings')
