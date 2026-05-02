"""Add Fresh Green system theme and set as default for new users.

Revision ID: 026
Revises: 025
Create Date: 2026-05-02

"""
from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None

FRESH_GREEN_SETTINGS = {
    'primary-color':            '#5bbb9f',
    'primary-hover':            '#4aa88e',
    'secondary-color':          '#89a8a2',
    'secondary-hover':          '#7a9892',
    'success-color':            '#2e9e67',
    'error-color':              '#d94f4f',
    'warning-color':            '#e8922e',
    'text-color':               '#1e3832',
    'text-bold':                '#142820',
    'text-muted':               '#6b8882',
    'background-light':         '#f0faf7',
    'page-panel-background':    '#ffffff',
    'border-color':             '#c0e0d8',
    'card-bg-color':            '#ffffff',
    'header-background':        '#2a5248',
    'header-text-color':        '#ffffff',
    'header-menu-background':   '#ffffff',
    'header-menu-hover':        '#f0faf7',
    'header-menu-text-color':   '#1e3832',
    'header-button-background': '#3d7a6a',
    'header-button-hover':      '#2e6558',
    'icon-color':               '#ffffff',
}


def upgrade():
    conn = op.get_bind()

    # 1. Remove any user-owned "Fresh Green" theme (created via API during development)
    conn.execute(sa.text(
        "DELETE FROM themes WHERE name = 'Fresh Green' AND (system_theme = 0 OR system_theme IS NULL)"
    ))

    # 2. Insert Fresh Green as a system theme if it doesn't already exist
    result = conn.execute(sa.text(
        "SELECT id FROM themes WHERE name = 'Fresh Green' AND system_theme = 1 LIMIT 1"
    ))
    row = result.fetchone()

    if row is None:
        conn.execute(sa.text("""
            INSERT INTO themes (name, settings, background_image, system_theme, user_id)
            VALUES (:name, :settings, NULL, 1, NULL)
        """), {
            'name': 'Fresh Green',
            'settings': json.dumps(FRESH_GREEN_SETTINGS),
        })

    # 3. Retrieve the canonical system theme ID
    result = conn.execute(sa.text(
        "SELECT id FROM themes WHERE name = 'Fresh Green' AND system_theme = 1 LIMIT 1"
    ))
    fresh_green_id = result.fetchone()[0]

    # 4. Update the selected_theme setting for all existing users to Fresh Green
    conn.execute(sa.text("""
        UPDATE settings
        SET `value` = :theme_id
        WHERE `key` = 'selected_theme'
    """), {'theme_id': str(fresh_green_id)})


def downgrade():
    conn = op.get_bind()

    # Restore selected_theme for all users back to the Default theme (id=1)
    conn.execute(sa.text("""
        UPDATE settings
        SET `value` = '1'
        WHERE `key` = 'selected_theme'
    """))

    # Remove the Fresh Green system theme
    conn.execute(sa.text(
        "DELETE FROM themes WHERE name = 'Fresh Green' AND system_theme = 1"
    ))
