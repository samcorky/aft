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

## Relationships and Foreign Keys

### Adding Related Models

When creating a model with relationships to existing models:

#### 1. Define Foreign Key Column

```python
schedule_id = Column(Integer, ForeignKey('scheduled_cards.id', ondelete='SET NULL'), nullable=True, index=True)
```

**Key Points:**
- Use `ForeignKey()` to reference the parent table
- Specify `ondelete` behavior (see Cascade Behavior section)
- Set `nullable=True` if relationship is optional
- **Always add `index=True`** for query performance

#### 2. Add Relationship on Both Sides

```python
# In parent model (ScheduledCard)
class ScheduledCard(Base):
    __tablename__ = 'scheduled_cards'
    id = Column(Integer, primary_key=True)
    # ... other columns ...
    
    # Relationship to created cards
    created_cards = relationship(
        'Card',
        back_populates='schedule',
        foreign_keys='Card.schedule_id'
    )

# In child model (Card)
class Card(Base):
    __tablename__ = 'cards'
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey('scheduled_cards.id', ondelete='SET NULL'), nullable=True, index=True)
    # ... other columns ...
    
    # Relationship to schedule that created it
    schedule = relationship(
        'ScheduledCard',
        back_populates='created_cards',
        foreign_keys=[schedule_id]
    )
```

#### 3. Cascade Behavior

Choose appropriate `ondelete` behavior:

- **`CASCADE`**: Delete children when parent deleted
  - Use for: Comments on cards, checklist items on cards
  - Example: When card deleted, delete all its comments
  ```python
  card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'), nullable=False)
  ```

- **`SET NULL`**: Keep children, null out reference
  - Use for: Cards created by schedules, optional relationships
  - Example: When schedule deleted, keep created cards but null the reference
  ```python
  schedule_id = Column(Integer, ForeignKey('scheduled_cards.id', ondelete='SET NULL'), nullable=True)
  ```

- **`RESTRICT`**: Prevent deletion if children exist (rarely used)
  - Use for: Critical relationships that must be manually cleaned up

### Migration for Relationships

#### Adding FK to Existing Table

```python
def upgrade() -> None:
    """Add schedule relationship to cards table."""
    # Add foreign key column to existing table
    with op.batch_alter_table('cards') as batch_op:
        # 1. Add the column
        batch_op.add_column(
            sa.Column('schedule_id', sa.Integer(), nullable=True)
        )
        
        # 2. Create the foreign key constraint
        batch_op.create_foreign_key(
            'fk_cards_schedule_id',  # Constraint name
            'scheduled_cards',        # Referenced table
            ['schedule_id'],          # Local column
            ['id'],                   # Referenced column
            ondelete='SET NULL'
        )
        
        # 3. Create index for performance
        batch_op.create_index(
            'ix_cards_schedule_id',
            ['schedule_id']
        )

def downgrade() -> None:
    """Remove schedule relationship from cards table."""
    with op.batch_alter_table('cards') as batch_op:
        # Remove in reverse order
        batch_op.drop_index('ix_cards_schedule_id')
        batch_op.drop_constraint('fk_cards_schedule_id', type_='foreignkey')
        batch_op.drop_column('schedule_id')
```

#### Creating New Table with FK

```python
def upgrade() -> None:
    """Create scheduled_cards table with relationships."""
    # Create parent table first
    op.create_table(
        'scheduled_cards',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('card_title', sa.String(length=255), nullable=False),
        # ... other columns
    )
    
    # Then add FK to existing table (as shown above)
    with op.batch_alter_table('cards') as batch_op:
        # Add FK column and constraint
        ...
```

### Testing Relationships

```python
def test_relationship_cascade(self, api_client):
    """Test that cascade behavior works correctly."""
    # Create parent
    parent_response = requests.post(
        f'{api_client}/api/schedules',
        json={"card_title": "Test"}
    )
    schedule_id = parent_response.json()['id']
    
    # Create child (via API that references parent)
    # ... 
    
    # Delete parent
    delete_response = requests.delete(
        f'{api_client}/api/schedules/{schedule_id}'
    )
    assert delete_response.status_code == 200
    
    # Verify child behavior based on cascade setting
    # SET NULL: child still exists, FK is null
    # CASCADE: child is deleted
```

### Common Pitfalls

1. **Forgetting Index**: Always add `index=True` to foreign key columns
2. **Wrong Order**: Create parent table before adding FK to child
3. **Circular Dependencies**: Use `foreign_keys` parameter if models reference each other
4. **Missing back_populates**: Always define relationship on both sides
5. **Wrong Cascade**: Carefully choose CASCADE vs SET NULL vs RESTRICT
