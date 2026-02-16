"""Permission and role definitions for the application."""
import json

# Permission definitions - describes what each permission allows
PERMISSION_DEFINITIONS = {
    # Global admin permissions
    'system.admin': 'Full system administration',
    'admin.system': 'System administration and monitoring',
    'admin.database': 'Database backup and restore operations',
    'user.manage': 'Manage all users',
    'user.role': 'Assign roles to users',
    'role.manage': 'Manage roles and permissions',
    
    # Board permissions
    'board.create': 'Create new boards',
    'board.view': 'View boards',
    'board.edit': 'Edit board details',
    'board.delete': 'Delete boards',
    'board.share': 'Share boards with others',
    
    # Card permissions
    'card.create': 'Create cards',
    'card.view': 'View cards',
    'card.edit': 'Edit cards',
    'card.delete': 'Delete cards',
    'card.assign': 'Assign cards to users',
    'card.archive': 'Archive/unarchive cards',
    
    # Schedule permissions
    'schedule.create': 'Create scheduled cards',
    'schedule.view': 'View scheduled cards',
    'schedule.edit': 'Edit scheduled cards',
    'schedule.delete': 'Delete scheduled cards',
    
    # Settings permissions
    'setting.view': 'View settings',
    'setting.edit': 'Edit settings',
    'settings.view': 'View settings',
    'settings.edit': 'Edit own settings',
    'settings.global.edit': 'Edit global system settings',
    
    # Backup permissions
    'backup.create': 'Create backups',
    'backup.restore': 'Restore from backups',
    'backup.delete': 'Delete backups',
    
    # Theme permissions
    'theme.create': 'Create custom themes',
    'theme.view': 'View themes',
    'theme.edit': 'Edit own themes',
    'theme.delete': 'Delete own themes',
    'theme.system.edit': 'Edit system themes',
}

# Initial system roles with their permissions
INITIAL_ROLES = {
    'administrator': {
        'description': 'Full system access including user and system management',
        'is_system_role': True,
        'permissions': [
            # All permissions
            'system.admin',
            'admin.system',
            'admin.database',
            'user.manage',
            'user.role',
            'role.manage',
            'board.create',
            'board.view',
            'board.edit',
            'board.delete',
            'board.share',
            'card.create',
            'card.view',
            'card.edit',
            'card.delete',
            'card.assign',
            'card.archive',
            'schedule.create',
            'schedule.view',
            'schedule.edit',
            'schedule.delete',
            'setting.view',
            'setting.edit',
            'settings.view',
            'settings.edit',
            'settings.global.edit',
            'backup.create',
            'backup.restore',
            'backup.delete',
            'theme.create',
            'theme.view',
            'theme.edit',
            'theme.delete',
            'theme.system.edit',
        ]
    },
    'board_admin': {
        'description': 'Full access to assigned boards',
        'is_system_role': True,
        'permissions': [
            'user.role',
            'board.view',
            'board.edit',
            'board.delete',
            'board.share',
            'card.create',
            'card.view',
            'card.edit',
            'card.delete',
            'card.assign',
            'card.archive',
            'schedule.create',
            'schedule.edit',
            'schedule.delete',
            'settings.view',
            'settings.edit',
            'theme.create',
            'theme.edit',
            'theme.delete',
        ]
    },
    'editor': {
        'description': 'Can create and edit cards on assigned boards',
        'is_system_role': True,
        'permissions': [
            'board.view',
            'card.create',
            'card.view',
            'card.edit',
            'card.archive',
            'schedule.create',
            'schedule.edit',
            'settings.view',
            'settings.edit',
            'theme.create',
            'theme.edit',
            'theme.delete',
        ]
    },
    'read_only': {
        'description': 'View-only access to assigned boards',
        'is_system_role': True,
        'permissions': [
            'board.view',
            'card.view',
            'settings.view',
        ]
    }
}


def get_role_permissions_json(role_name):
    """Get the permissions for a role as a JSON string."""
    if role_name in INITIAL_ROLES:
        return json.dumps(INITIAL_ROLES[role_name]['permissions'])
    return json.dumps([])


def validate_permission(permission):
    """Check if a permission string is valid."""
    return permission in PERMISSION_DEFINITIONS


def has_permission(user_permissions, required_permission):
    """
    Check if a user has a required permission.
    
    Args:
        user_permissions: Set or list of permission strings
        required_permission: Permission string to check
        
    Returns:
        bool: True if user has the permission or system.admin
    """
    # System admin has all permissions
    if 'system.admin' in user_permissions:
        return True
    
    return required_permission in user_permissions
