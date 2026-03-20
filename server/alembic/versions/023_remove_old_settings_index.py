"""Remove old ix_settings_key index

Revision ID: 023
Revises: 022
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    """Remove the old ix_settings_key unique index that conflicts with user-specific settings."""
    # Drop the old unique index on key column only
    # The correct index idx_setting_scope_key (on COALESCE(user_id, 0), key) already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    index_names = {idx.get('name') for idx in inspector.get_indexes('settings')}
    if 'ix_settings_key' in index_names:
        op.drop_index('ix_settings_key', table_name='settings')


def downgrade():
    """Re-create the old index if downgrading."""
    op.create_index('ix_settings_key', 'settings', ['key'], unique=True)
