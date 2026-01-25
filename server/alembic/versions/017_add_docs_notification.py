"""add documentation notification

Revision ID: 017
Revises: 016
Create Date: 2026-01-18

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    """Add documentation notification with action link."""
    # Insert docs notification only if it doesn't already exist
    op.execute("""
        INSERT INTO notifications (subject, message, unread, created_at, action_title, action_url)
        SELECT 
            'Documentation Available',
            'Full documentation including keyboard shortcuts and features is now available.',
            1,
            NOW(),
            'View Docs',
            '/docs.html'
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM notifications WHERE subject = 'Documentation Available'
        )
    """)


def downgrade():
    """Remove documentation notification."""
    op.execute("DELETE FROM notifications WHERE subject = 'Documentation Available'")
