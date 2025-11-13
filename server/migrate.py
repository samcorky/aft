#!/usr/bin/env python
"""
Database migration management script.

Usage:
    python migrate.py create "description of migration"  # Create a new migration
    python migrate.py upgrade                             # Apply all pending migrations
    python migrate.py downgrade                           # Rollback one migration
    python migrate.py current                             # Show current migration version
    python migrate.py history                             # Show migration history
"""

import sys
from alembic import command
from alembic.config import Config


def main():
    """Main migration management function."""
    alembic_cfg = Config("alembic.ini")
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    action = sys.argv[1].lower()
    
    if action == "create":
        if len(sys.argv) < 3:
            print("Error: Please provide a migration message")
            print('Example: python migrate.py create "add user table"')
            sys.exit(1)
        message = sys.argv[2]
        print(f"Creating new migration: {message}")
        command.revision(alembic_cfg, message=message, autogenerate=True)
        print("Migration created successfully!")
        
    elif action == "upgrade":
        print("Applying migrations...")
        command.upgrade(alembic_cfg, "head")
        print("Migrations applied successfully!")
        
    elif action == "downgrade":
        steps = sys.argv[2] if len(sys.argv) > 2 else "-1"
        print(f"Rolling back {steps} migration(s)...")
        command.downgrade(alembic_cfg, steps)
        print("Rollback completed!")
        
    elif action == "current":
        print("Current migration version:")
        command.current(alembic_cfg)
        
    elif action == "history":
        print("Migration history:")
        command.history(alembic_cfg)
        
    else:
        print(f"Unknown action: {action}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
