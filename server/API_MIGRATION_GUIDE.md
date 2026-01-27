# API Migration Guide

This guide explains how to migrate existing API endpoints to require authentication using the tracking system.

## Current Status

**As of last update:**
- ✅ Migration tracking system implemented (`api_migration_tracker.py`)
- ✅ All 75 API endpoints marked with `@track_endpoint(protected=False, reason="Not yet migrated")`
- ✅ Migration dashboard available at `/api/migration-status?format=html`
- ✅ Link to dashboard added to System Info page
- ⏳ 0/75 endpoints migrated (0% complete)
- ⚙️ Enforcement mode: **OFF** (set to True when migration complete)

**Key Files:**
- `server/api_migration_tracker.py` - Tracking system and enforcement
- `server/app.py` - All endpoints marked with @track_endpoint decorator
- `server/utils.py` - Security helpers (get_user_scoped_query, require_permission, etc.)
- `server/permissions.py` - Permission definitions and roles

## Overview

The API migration tracker helps you:
- **Track progress**: See which endpoints are protected vs unprotected
- **Gradual migration**: Migrate endpoints one at a time without breaking functionality
- **Enforcement mode**: Once migration is complete, enforce auth on ALL endpoints
- **Visual dashboard**: View migration status at `/api/migration-status?format=html`

## Migration Process

### Step 1: Mark Unprotected Endpoints

When you haven't migrated an endpoint yet, mark it as unprotected to track it:

```python
from api_migration_tracker import track_endpoint

@app.route('/api/boards', methods=['GET'])
@track_endpoint(protected=False, reason='Not yet migrated - needs user scoping')
def get_boards():
    # Existing code - no changes yet
    ...
```

### Step 2: Migrate the Endpoint

When you migrate an endpoint, follow this pattern:

```python
from api_migration_tracker import track_endpoint
from utils import require_permission, get_user_scoped_query
from flask import g

@app.route('/api/boards', methods=['GET'])
@track_endpoint(protected=True, reason='Requires authentication')
@require_permission('board.view')  # Add permission check
def get_boards():
    """Get all boards for the current user."""
    db = SessionLocal()
    try:
        # OLD: boards = db.query(Board).all()
        # NEW: Use user-scoped query
        boards = get_user_scoped_query(db, Board, g.user['id']).all()
        
        return jsonify({
            'success': True,
            'boards': [board.to_dict() for board in boards]
        })
    finally:
        db.close()
```

### Step 3: Check Migration Status

Visit the migration dashboard to see progress:
- **JSON API**: `http://localhost:5000/api/migration-status`
- **HTML Dashboard**: `http://localhost:5000/api/migration-status?format=html`

The dashboard shows:
- Total endpoints, protected, and unprotected counts
- Progress percentage
- List of all endpoints grouped by status
- Which endpoints still need migration

### Step 4: Enable Enforcement (When Complete)

Once all endpoints are migrated and tested, enable enforcement mode in [api_migration_tracker.py](api_migration_tracker.py#L19):

```python
# Change this from False to True
ENFORCE_AUTH_ON_ALL_APIS = True
```

**In enforcement mode:**
- ALL `/api/*` endpoints require authentication
- Unauthenticated requests return 401
- No endpoints can be accidentally left unprotected
- Exceptions: `/api/auth/*`, `/api/test`, `/api/migration-status`

## Migration Patterns

### Pattern 1: List/Get Operations

```python
@app.route('/api/boards', methods=['GET'])
@track_endpoint(protected=True, reason='User-specific data')
@require_permission('board.view')
def get_boards():
    db = SessionLocal()
    try:
        # Scope query to current user
        boards = get_user_scoped_query(db, Board, g.user['id']).all()
        return jsonify({'success': True, 'boards': [b.to_dict() for b in boards]})
    finally:
        db.close()
```

### Pattern 2: Create Operations

```python
@app.route('/api/boards', methods=['POST'])
@track_endpoint(protected=True, reason='Creates user-owned resource')
@require_permission('board.create')
def create_board():
    db = SessionLocal()
    try:
        data = request.get_json()
        
        # Set the owner to current user
        board = Board(
            name=data['name'],
            owner_id=g.user['id']  # Assign owner
        )
        
        db.add(board)
        db.commit()
        return jsonify({'success': True, 'board': board.to_dict()})
    finally:
        db.close()
```

### Pattern 3: Update/Delete Operations

```python
@app.route('/api/boards/<int:board_id>', methods=['PUT', 'DELETE'])
@track_endpoint(protected=True, reason='Requires board ownership')
@require_board_access(permission='board.edit')  # Checks ownership
def update_board(board_id):
    db = SessionLocal()
    try:
        # Query will fail if user doesn't own the board (RLS)
        board = get_user_scoped_query(db, Board, g.user['id']).filter_by(id=board_id).first()
        
        if not board:
            return jsonify({'success': False, 'error': 'Board not found'}), 404
        
        # Update or delete
        if request.method == 'DELETE':
            db.delete(board)
        else:
            data = request.get_json()
            board.name = data.get('name', board.name)
        
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()
```

### Pattern 4: Global Settings (User-Specific or Global)

```python
@app.route('/api/settings/<key>', methods=['GET'])
@track_endpoint(protected=True, reason='User-specific settings')
@require_permission('setting.view')
def get_setting(key):
    db = SessionLocal()
    try:
        # Get user setting, fallback to global
        setting = db.query(Setting).filter_by(
            key=key,
            user_id=g.user['id']
        ).first()
        
        if not setting:
            # Fallback to global setting
            setting = db.query(Setting).filter_by(key=key, user_id=None).first()
        
        return jsonify({'success': True, 'setting': setting.to_dict() if setting else None})
    finally:
        db.close()
```

## Migration Checklist

For each endpoint:

- [ ] Add `@track_endpoint(protected=True, reason='...')` decorator
- [ ] Add `@require_permission('resource.action')` decorator
- [ ] Replace `db.query(Model)` with `get_user_scoped_query(db, Model, g.user['id'])`
- [ ] Set `owner_id` or `created_by_id` on CREATE operations
- [ ] Verify user access on UPDATE/DELETE operations
- [ ] Test with multiple users to ensure isolation
- [ ] Update frontend to handle 401 responses
- [ ] Check migration dashboard for progress

## Common Issues

### Issue: "No user in context"
**Cause**: Endpoint called before user is loaded from session  
**Fix**: Ensure `load_user_from_session()` runs in `before_request` middleware

### Issue: "User can see other users' data"
**Cause**: Forgot to use `get_user_scoped_query()`  
**Fix**: Replace all `db.query(Model)` with scoped query helper

### Issue: "401 Unauthorized on test endpoint"
**Cause**: Health check endpoint blocked by enforcement mode  
**Fix**: Endpoint is already excluded - check if user session exists

### Issue: "Frontend broken after migration"
**Cause**: Frontend not handling 401 responses  
**Fix**: Add global auth check and 401 handler in frontend JavaScript

## Testing Migration

After migrating an endpoint, test:

1. **Authenticated requests work**: Log in and verify functionality
2. **Unauthenticated requests blocked**: Try without session, expect 401
3. **User isolation works**: Create data with user A, verify user B can't access it
4. **Permissions enforced**: Test with different roles (admin vs read-only)

## Progress Tracking

Use the migration dashboard to track progress:

```bash
# View in browser
open http://localhost:5000/api/migration-status?format=html

# Or get JSON
curl http://localhost:5000/api/migration-status
```

The dashboard shows:
- **Green**: Protected endpoints (migration complete)
- **Orange**: Unprotected endpoints (still to migrate)
- **Progress bar**: Visual progress indicator
- **Enforcement status**: Whether all APIs require auth

## Next Steps

1. **Mark all existing endpoints** with `@track_endpoint(protected=False)` to see full inventory
2. **Migrate critical endpoints first**: Boards, Cards (user data)
3. **Migrate administrative endpoints**: Settings, System info
4. **Update frontend**: Add auth checks and 401 handlers
5. **Enable enforcement mode**: Set `ENFORCE_AUTH_ON_ALL_APIS = True`
6. **Test thoroughly**: Verify all functionality works with multiple users

## Example Migration Session

```python
# BEFORE (unprotected endpoint)
@app.route('/api/cards', methods=['GET'])
def get_cards():
    db = SessionLocal()
    try:
        board_id = request.args.get('board_id')
        cards = db.query(Card).filter_by(board_id=board_id).all()
        return jsonify({'success': True, 'cards': [c.to_dict() for c in cards]})
    finally:
        db.close()

# AFTER (protected endpoint)
@app.route('/api/cards', methods=['GET'])
@track_endpoint(protected=True, reason='User-scoped card data')
@require_permission('card.view')
def get_cards():
    db = SessionLocal()
    try:
        board_id = request.args.get('board_id')
        
        # Verify user has access to this board
        board = get_user_scoped_query(db, Board, g.user['id']).filter_by(id=board_id).first()
        if not board:
            return jsonify({'success': False, 'error': 'Board not found'}), 404
        
        # Get cards (user owns board, so can see cards)
        cards = db.query(Card).filter_by(board_id=board_id).all()
        return jsonify({'success': True, 'cards': [c.to_dict() for c in cards]})
    finally:
        db.close()
```

## Quick Start for Next Session

To resume API migration in a new conversation:

1. **Check current status**: Visit `http://localhost/api/migration-status?format=html`
2. **Review this guide**: Read the migration patterns above
3. **Start migrating**: Pick an endpoint category (boards, cards, settings, etc.)
4. **Update decorators**: Change `protected=False` to `protected=True` and add permission checks
5. **Add user scoping**: Use `get_user_scoped_query()` for data isolation
6. **Test**: Verify with multiple users that data is properly isolated
7. **Track progress**: Check dashboard after each migration batch

**When all 75 endpoints are migrated:**
- Set `ENFORCE_AUTH_ON_ALL_APIS = True` in [api_migration_tracker.py](api_migration_tracker.py#L19)
- Remove this migration card from system-info.html
- Celebrate! 🎉

## Summary

The migration tracker ensures:
- ✅ **Visibility**: Know which endpoints are protected
- ✅ **Safety**: Gradual migration without breaking functionality
- ✅ **Enforcement**: Guarantee all endpoints require auth when ready
- ✅ **Tracking**: Never lose track of what's done and what's remaining

Visit `/api/migration-status?format=html` to see your progress!

        cards = db.query(Card).filter_by(board_id=board_id).all()
        return jsonify({'success': True, 'cards': [c.to_dict() for c in cards]})
    finally:
        db.close()
```

## Summary

The migration tracker ensures:
- ✅ **Visibility**: Know which endpoints are protected
- ✅ **Safety**: Gradual migration without breaking functionality
- ✅ **Enforcement**: Guarantee all endpoints require auth when ready
- ✅ **Tracking**: Never lose track of what's done and what's remaining

Visit `/api/migration-status?format=html` to see your progress!
