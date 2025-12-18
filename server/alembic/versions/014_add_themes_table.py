"""add themes table

Revision ID: 014
Revises: 013
Create Date: 2025-12-17

"""
from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    """Create themes table and migrate existing theme data."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Create themes table if it doesn't exist
    if 'themes' not in inspector.get_table_names():
        op.create_table(
            'themes',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(100), nullable=False, unique=True),
            sa.Column('settings', sa.Text(), nullable=False),  # JSON string
            sa.Column('background_image', sa.String(255), nullable=True),
            sa.Column('system_theme', sa.Boolean(), nullable=False, default=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
        )
        
        # Insert the 4 system themes
        themes_data = [
            {
                'name': 'Default',
                'system_theme': True,
                'background_image': None,
                'settings': json.dumps({
                    'primary-color': '#3498DB',
                    'primary-hover': '#2980B9',
                    'secondary-color': '#95A5A6',
                    'secondary-hover': '#7F8C8D',
                    'success-color': '#28A745',
                    'error-color': '#DC3545',
                    'warning-color': '#FFC107',
                    'text-color': '#2C3E50',
                    'text-bold': '#2C3E50',
                    'text-muted': '#7F8C8D',
                    'text-secondary': '#7F8C8D',
                    'background-light': '#F5F5F5',
                    'page-panel-background': '#FFFFFF',
                    'border-color': '#E0E0E0',
                    'card-bg-color': '#FFFFFF',
                    'header-background': '#2C3E50',
                    'header-text-color': '#FFFFFF',
                    'header-menu-background': '#FFFFFF',
                    'header-menu-hover': '#F5F5F5',
                    'header-menu-text-color': '#2C3E50',
                    'header-button-background': '#404E5C',
                    'header-button-hover': '#384552',
                    'icon-color': '#FFFFFF'
                })
            },
            {
                'name': 'At the Beach',
                'system_theme': True,
                'background_image': None,
                'settings': json.dumps({
                    'primary-color': '#d4a574',
                    'primary-hover': '#b9945f',
                    'secondary-color': '#06B6D4',
                    'secondary-hover': '#0891b2',
                    'success-color': '#14b8a6',
                    'error-color': '#f43f5e',
                    'warning-color': '#fb923c',
                    'text-color': '#0f172a',
                    'text-bold': '#2c3e50',
                    'text-muted': '#64743b',
                    'text-secondary': '#64743b',
                    'background-light': '#f0f9ff',
                    'page-panel-background': '#ffffff',
                    'border-color': '#cbd5e1',
                    'card-bg-color': '#fafaf0',
                    'header-background': '#d4a574',
                    'header-text-color': '#ffffff',
                    'header-menu-background': '#06B6D4',
                    'header-menu-hover': '#0891b2',
                    'header-menu-text-color': '#ffffff',
                    'header-button-background': '#06B6D4',
                    'header-button-hover': '#0891b2',
                    'icon-color': '#ffffff'
                })
            },
            {
                'name': 'Dark Mode',
                'system_theme': True,
                'background_image': None,
                'settings': json.dumps({
                    'primary-color': '#60A5FA',
                    'primary-hover': '#3B82F6',
                    'secondary-color': '#A78BFA',
                    'secondary-hover': '#8B5CF6',
                    'success-color': '#10B981',
                    'error-color': '#EF4444',
                    'warning-color': '#F59E0B',
                    'text-color': '#E5E7EB',
                    'text-bold': '#F9FAFB',
                    'text-muted': '#9CA3AF',
                    'text-secondary': '#9CA3AF',
                    'background-light': '#1F2937',
                    'page-panel-background': '#111827',
                    'border-color': '#374151',
                    'card-bg-color': '#254065',
                    'header-background': '#0F172A',
                    'header-text-color': '#F9FAFB',
                    'header-menu-background': '#1E293B',
                    'header-menu-hover': '#334155',
                    'header-menu-text-color': '#E5E7EB',
                    'header-button-background': '#1E40AF',
                    'header-button-hover': '#1E3A8A',
                    'icon-color': '#F9FAFB'
                })
            },
            {
                'name': 'Welcome to the Jungle',
                'system_theme': True,
                'background_image': None,
                'settings': json.dumps({
                    'primary-color': '#10B981',
                    'primary-hover': '#059669',
                    'secondary-color': '#F59E0B',
                    'secondary-hover': '#D97706',
                    'success-color': '#22C55E',
                    'error-color': '#DC2626',
                    'warning-color': '#FBBF24',
                    'text-color': '#1C3D2C',
                    'text-bold': '#14532D',
                    'text-muted': '#6B7280',
                    'text-secondary': '#6B7280',
                    'background-light': '#F0FDF4',
                    'page-panel-background': '#FFFFFF',
                    'border-color': '#BBF7D0',
                    'card-bg-color': '#ECFDF5',
                    'header-background': '#166534',
                    'header-text-color': '#F0FDF4',
                    'header-menu-background': '#FEF3C7',
                    'header-menu-hover': '#FDE68A',
                    'header-menu-text-color': '#78350F',
                    'header-button-background': '#CA8A04',
                    'header-button-hover': '#A16207',
                    'icon-color': '#F0FDF4'
                })
            }
        ]
        
        # Insert themes
        for theme in themes_data:
            conn.execute(
                sa.text("""
                    INSERT INTO themes (name, settings, background_image, system_theme)
                    VALUES (:name, :settings, :background_image, :system_theme)
                """),
                {
                    'name': theme['name'],
                    'settings': theme['settings'],
                    'background_image': theme['background_image'],
                    'system_theme': theme['system_theme']
                }
            )
    
    # Add selected_theme setting to settings table
    if 'settings' in inspector.get_table_names():
        # Get the default theme ID
        result = conn.execute(sa.text("SELECT id FROM themes WHERE name = 'Default' LIMIT 1"))
        default_theme_row = result.fetchone()
        default_theme_id = default_theme_row[0] if default_theme_row else 1
        
        # Check if the selected_theme setting already exists
        result = conn.execute(sa.text("SELECT COUNT(*) FROM settings WHERE key = 'selected_theme'"))
        count = result.fetchone()[0]
        
        if count == 0:
            # Insert the selected_theme setting
            conn.execute(
                sa.text("INSERT INTO settings (key, value) VALUES ('selected_theme', :theme_id)"),
                {'theme_id': str(default_theme_id)}
            )


def downgrade():
    """Remove themes table and selected_theme setting."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Remove selected_theme setting from settings table
    if 'settings' in inspector.get_table_names():
        op.execute(sa.text("DELETE FROM settings WHERE key = 'selected_theme'"))
    
    # Drop themes table
    if 'themes' in inspector.get_table_names():
        op.drop_table('themes')
