# Database Migration System - Usage Guide

## Overview

Your application now uses **Alembic** for database schema management. This is the industry-standard solution for Python applications, providing:

- ✅ **Automatic schema creation** on first startup
- ✅ **Version control** for database changes
- ✅ **Safe migrations** with upgrade/downgrade support
- ✅ **Auto-detection** of schema changes
- ✅ **Data preservation** during updates

## How It Works

### On Startup (Automatic)

When the container starts, `app.py` automatically:
1. Waits for database to be ready
2. Runs all pending migrations to bring schema up-to-date
3. Creates tables if they don't exist
4. Updates schema if new migrations exist

**No manual intervention needed!** The schema is always synchronized.

### Migration Files

Migrations are stored in `server/alembic/versions/`:
- `001_initial_migration.py` - Creates the `boards` table

Each migration has:
- **upgrade()** - Apply changes (create/modify tables)
- **downgrade()** - Rollback changes (for emergencies)

## Common Tasks

### 1. Adding a New Column to `boards`

**Step 1:** Update the model in `server/models.py`:
```python
class Board(Base):
    __tablename__ = "boards"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500))  # NEW COLUMN
```

**Step 2:** Generate migration (run in server container):
```bash
docker exec -it aft-server python migrate.py create "add description to boards"
```

**Step 3:** Restart container to apply:
```bash
docker-compose restart server
```

The migration will automatically:
- Detect the new column
- Add it to existing tables
- Preserve all existing data

### 2. Creating a New Table

**Step 1:** Create model in `server/models.py`:
```python
class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    board_id = Column(Integer, ForeignKey('boards.id'))
```

**Step 2:** Import in `server/alembic/env.py`:
```python
from models import Board, Task  # Add Task
```

**Step 3:** Generate and apply migration:
```bash
docker exec -it aft-server python migrate.py create "add tasks table"
docker-compose restart server
```

### 3. Manual Migration Management

Inside the container:

```bash
# Show current schema version
docker exec -it aft-server python migrate.py current

# View migration history
docker exec -it aft-server python migrate.py history

# Apply migrations manually
docker exec -it aft-server python migrate.py upgrade

# Rollback last migration (emergency only!)
docker exec -it aft-server python migrate.py downgrade
```

### 4. Testing Migrations Locally

Before deploying:

```bash
# Check what Alembic will generate
docker exec -it aft-server alembic revision --autogenerate -m "test migration" --sql

# Review the generated SQL without applying
```

## File Structure

```
server/
├── app.py                 # Auto-runs migrations on startup
├── database.py            # Database connection config
├── models.py              # Your table definitions (ORM models)
├── migrate.py             # Helper script for migration commands
├── alembic.ini            # Alembic configuration
├── alembic/
│   ├── env.py            # Migration environment setup
│   ├── script.py.mako    # Template for new migrations
│   └── versions/         # All migration files (version controlled!)
│       └── 001_initial_migration.py
```

## Best Practices

1. **Always version control migrations** - Commit `alembic/versions/*.py` files
2. **Test migrations on dev first** - Never apply untested migrations to production
3. **Never edit applied migrations** - Create a new migration to fix issues
4. **Backup before major changes** - Especially for data transformations
5. **Keep migrations small** - One logical change per migration
6. **Review auto-generated migrations** - Alembic is smart but check the SQL

## Current API Endpoints

Your app now has these endpoints:

- `GET /api/test` - Test DB connection + count boards
- `GET /api/boards` - List all boards
- `POST /api/boards` - Create a board (JSON: `{"name": "Board Name"}`)

## Example Workflow: Production Deployment

1. Develop locally and test schema changes
2. Commit migration files to git
3. Deploy new code to production
4. Container auto-runs migrations on startup
5. Schema is updated seamlessly with zero downtime (for additive changes)

## Troubleshooting

**"Migration failed" on startup?**
- Check database is accessible: `docker-compose logs db`
- Verify env variables: `docker exec -it aft-server env | grep MYSQL`

**"Table already exists" error?**
- Database has tables but no migration history
- Solution: `docker exec -it aft-server alembic stamp head` (marks current state)

**Need to start fresh?**
- Stop containers: `docker-compose down`
- Delete data: `rm -rf data/aft_db`
- Start again: `docker-compose up -d` (migrations create everything)

## Advanced: Data Migrations

To transform existing data during migration:

```python
# In a migration file
def upgrade():
    # Add column with default
    op.add_column('boards', sa.Column('status', sa.String(20), default='active'))
    
    # Update existing rows
    op.execute("UPDATE boards SET status = 'active' WHERE status IS NULL")
    
    # Make it non-nullable
    op.alter_column('boards', 'status', nullable=False)
```

---

**You're all set!** Your database schema is now professionally managed with industry-standard tooling.
