# Alembic Migration Guide

## Creating New Migrations

### Method 1: Autogenerate (Recommended)

When you add/modify models in `models.py`:

1. **Update `alembic/env.py`** - Add your new model to the imports:
   ```python
   from models import Board, BoardColumn, Card, YourNewModel
   ```

2. **Generate migration** inside the running container:
   ```bash
   docker exec -it aft-server alembic revision --autogenerate -m "description"
   ```

3. **Copy migration to local workspace**:
   ```bash
   # Find the generated file name from the output
   docker cp aft-server:/app/alembic/versions/XXXXX_description.py ./server/alembic/versions/
   ```

4. **Rename to sequential format**:
   ```bash
   # Rename from hash-based to sequential: 003_description.py
   ```

5. **Update migration file** - Fix revision IDs:
   ```python
   revision: str = '003'  # Change from hash to sequential number
   down_revision: Union[str, None] = '002'  # Previous migration number
   ```

6. **Review the migration** - Check the upgrade/downgrade functions are correct

7. **Rebuild containers** to apply:
   ```bash
   docker compose down
   docker compose up --build -d
   ```

### Method 2: Manual Migration

For complex changes or when autogenerate doesn't work:

1. **Create file** named `00X_description.py` in `alembic/versions/`

2. **Use this template**:
   ```python
   """description
   
   Revision ID: 003
   Revises: 002
   Create Date: YYYY-MM-DD
   
   """
   from typing import Sequence, Union
   from alembic import op
   import sqlalchemy as sa
   
   revision: str = '003'
   down_revision: Union[str, None] = '002'
   branch_labels: Union[str, Sequence[str], None] = None
   depends_on: Union[str, Sequence[str], None] = None
   
   def upgrade() -> None:
       """Description of upgrade."""
       # Your upgrade code here
       
   def downgrade() -> None:
       """Description of downgrade."""
       # Your downgrade code here
   ```

3. **Rebuild containers** to apply

## Migration Naming Convention

- Use sequential numbers: `001`, `002`, `003`, etc.
- Format: `{number}_{description}.py`
- Examples:
  - `001_initial_migration.py`
  - `002_add_columns_table.py`
  - `003_add_cards_table.py`

## Checking Migration Status

```bash
# Current migration version
docker exec -it aft-server alembic current

# Migration history
docker exec -it aft-server alembic history

# Upgrade to latest (done automatically on container start)
docker exec -it aft-server alembic upgrade head

# Downgrade one version
docker exec -it aft-server alembic downgrade -1
```

## Common Issues

### Autogenerate doesn't detect changes
- **Cause**: Model not imported in `alembic/env.py`
- **Fix**: Add model to imports in `env.py`

### Migration created inside container
- **Cause**: Running alembic inside container
- **Fix**: Copy file out and rename to sequential format

### Foreign key constraints fail
- **Cause**: Tables created in wrong order
- **Fix**: Ensure parent tables are created before child tables in migration

### Schema validation fails with "Unexpected tables found in backup"
- **Cause**: New table added but not registered in schema validation
- **Fix**: Update the `expected_tables` list in `app.py`'s `validate_schema_integrity()` function (around line 315)
- **Location**: `server/app.py`, function `validate_schema_integrity()`
- **Example**:
  ```python
  if expected_tables is None:
      expected_tables = [
          'boards',
          'columns',
          'cards',
          'checklist_items',
          'comments',
          'settings',
          'notifications',  # Add new table here
          'alembic_version'
      ]
  ```

## Important: Schema Validation Updates

**⚠️ CRITICAL**: When adding a new table via migration, you MUST update the schema validation function to avoid backup/restore failures.

**Steps after creating a new table migration:**

1. Open `server/app.py`
2. Find the `validate_schema_integrity()` function (around line 295)
3. Add your new table name to the `expected_tables` list
4. Test backup and restore functionality to ensure it works

**Why this matters**: The backup/restore system validates that only expected tables are present in backup files for security. New tables will be rejected unless explicitly added to the allowed list.
