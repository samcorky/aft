"""add is_approved column to users for admin approval workflow

Revision ID: 022
Revises: 021
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    """Add is_approved column to users table."""
    bind = op.get_bind()

    inspector = sa.inspect(bind)
    user_columns = {col.get('name') for col in inspector.get_columns('users')}
    user_indexes = {idx.get('name') for idx in inspector.get_indexes('users')}
    
    # Add is_approved column (nullable initially)
    if 'is_approved' not in user_columns:
        op.add_column('users', sa.Column('is_approved', sa.Boolean(), nullable=True, server_default='0'))
    
    # Create index on is_approved for fast filtering of pending users
    if 'ix_users_is_approved' not in user_indexes:
        op.create_index('ix_users_is_approved', 'users', ['is_approved'])
    
    # Set existing users (admin from setup) to approved
    op.execute("""
        UPDATE users SET is_approved = 1 WHERE is_approved IS NULL OR is_approved = 0;
    """)
    
    # Make column NOT NULL after backfilling
    op.alter_column('users', 'is_approved', nullable=False, existing_type=sa.Boolean())


def downgrade():
    """Remove is_approved column from users table."""
    
    # Drop index
    op.drop_index('ix_users_is_approved', 'users')
    
    # Drop column
    op.drop_column('users', 'is_approved')
