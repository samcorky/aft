"""add notifications table

Revision ID: 009
Revises: 008
Create Date: 2025-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    """Create notifications table and add welcome notification."""
    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('unread', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_notifications_id', 'notifications', ['id'])
    op.create_index('ix_notifications_unread', 'notifications', ['unread'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
    
    # Insert welcome notification only if no notifications exist
    # This prevents duplicates if migration is run multiple times (testing, manual upgrade/downgrade cycles)
    op.execute("""
        INSERT INTO notifications (subject, message, unread, created_at)
        SELECT 
            'Welcome to AFT',
            'This is your notification area. Click a message to mark it as read, click mark as unread to read again later, or click delete to remove the message entirely',
            1,
            NOW()
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM notifications WHERE subject = 'Welcome to AFT'
        )
    """)


def downgrade():
    """Drop notifications table."""
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_unread', table_name='notifications')
    op.drop_index('ix_notifications_id', table_name='notifications')
    op.drop_table('notifications')
