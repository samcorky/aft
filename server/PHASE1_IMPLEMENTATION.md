# Phase 1 Implementation Guide: Authentication & API Migration

This guide walks through implementing authentication and migrating existing APIs to use the new user system.

## Overview

The authentication system is now set up with:
- ✅ User, Role, and UserRole models
- ✅ Session-based authentication
- ✅ Login/logout/register endpoints
- ✅ Login and registration pages
- ✅ Security helper functions

## How It Works

### 1. Authentication Flow

```
User → login.html → POST /api/auth/login → Creates session → Redirects to /
                                                ↓
                                          Sets session cookie
                                                ↓
                                    All subsequent requests include cookie
                                                ↓
                                      Middleware loads g.user automatically
```

### 2. Session Management

- **Session Storage**: Server-side sessions using Flask session
- **Cookie**: HTTPOnly, Secure (in production), SameSite=Lax
- **Lifetime**: 7 days (or 30 days with "Remember Me")
- **Security**: User loaded from database on each request

### 3. API Request Flow

```
Client Request → @app.before_request (loads user) → API endpoint → @app.teardown_request
                          ↓                                ↓
                    Loads g.user                   Checks @require_permission
                    from session                   Uses get_user_scoped_query()
                                                   Sets owner_id on creates
```

## Implementation Phases

### Phase 1: Set Up Authentication (Ready!)

✅ Database migrations created (020, 021)
✅ Authentication endpoints (/api/auth/*)
✅ Login and registration pages
✅ Session middleware configured

**Next Steps:**
1. Run migrations (see below)
2. Test login/registration
3. Set SECRET_KEY environment variable for production

### Phase 2: Protect Existing APIs (Next!)

The existing APIs currently work without authentication. We need to:

1. **Add authentication requirement** to each endpoint
2. **Use scoped queries** to filter data by user
3. **Set owner_id/created_by_id** when creating resources

#### Example Migration Pattern

**Before (Insecure):**
```python
@app.route('/api/boards', methods=['GET'])
def get_boards():
    db = SessionLocal()
    boards = db.query(Board).all()  # ❌ Returns ALL boards
    return jsonify([b.to_dict() for b in boards])
```

**After (Secure):**
```python
@app.route('/api/boards', methods=['GET'])
@require_authentication  # ✅ Require login
def get_boards():
    user_id = g.user.id
    db = SessionLocal()
    boards = get_user_scoped_query(db, Board, user_id).all()  # ✅ Only user's boards
    return jsonify([b.to_dict() for b in boards])
```

**For Creates:**
```python
@app.route('/api/boards', methods=['POST'])
@require_permission('board.create')  # ✅ Check permission
def create_board():
    user_id = g.user.id  # ✅ Get from session, not request
    data = request.get_json()
    
    board = Board(
        name=data['name'],
        owner_id=user_id  # ✅ Set owner
    )
    # ... rest of logic
```

### Phase 3: Update Frontend

1. **Add logout button** to main UI
2. **Redirect to login** when not authenticated
3. **Handle 401 responses** globally
4. **Show user info** in header

## Running Migrations

```bash
cd server

# Run the migrations
python migrate.py upgrade

# This will:
# - Create users, roles, user_roles tables
# - Add user_id/owner_id columns to existing tables
# - Create default admin user
# - Assign all existing data to admin user
```

### Default Admin User

After migration:
- **Email**: admin@localhost
- **Username**: admin
- **Password**: Not set (must be set manually)

**To set admin password:**

```python
# In Python shell or create a script:
from database import SessionLocal
from auth import hash_password
from models import User

db = SessionLocal()
admin = db.query(User).filter(User.username == 'admin').first()
admin.password_hash = hash_password('your-secure-password')
db.commit()
db.close()
```

Or use the registration page to create a new admin user.

## Environment Variables

Add these to your environment (docker-compose.yml or .env):

```yaml
environment:
  # REQUIRED for production - random string for session encryption
  SECRET_KEY: "change-this-to-a-random-string-in-production"
  
  # Use secure cookies in production (requires HTTPS)
  SESSION_COOKIE_SECURE: "false"  # Set to "true" with HTTPS
```

**Generate a secure SECRET_KEY:**
```python
import secrets
print(secrets.token_hex(32))
```

## Testing Authentication

### 1. Test Registration
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "password123",
    "display_name": "Test User"
  }'
```

### 2. Test Login
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

### 3. Test Authenticated Request
```bash
curl http://localhost:5000/api/auth/me \
  -b cookies.txt
```

## API Endpoint Migration Checklist

For each existing endpoint, apply these changes:

### Read Endpoints (GET)
- [ ] Add `@require_authentication` decorator
- [ ] Use `get_user_scoped_query(db, Model, g.user.id)` instead of `db.query(Model)`
- [ ] For specific resources, verify user can access (e.g., `@require_board_access()`)

### Create Endpoints (POST)
- [ ] Add `@require_permission('resource.create')` decorator
- [ ] Get `user_id = g.user.id` (never from request body)
- [ ] Set `owner_id` or `created_by_id` on new resources
- [ ] Use scoped queries to verify parent resources (e.g., board exists and user owns it)

### Update Endpoints (PUT/PATCH)
- [ ] Add `@require_permission('resource.edit')` decorator
- [ ] Use scoped query to get resource (ensures user owns it)
- [ ] Return 404 if resource not found (don't reveal it exists)

### Delete Endpoints (DELETE)
- [ ] Add `@require_permission('resource.delete')` decorator
- [ ] For boards, use `@require_board_access(require_owner=True)`
- [ ] Use scoped query to get resource
- [ ] Return 404 if resource not found

## Example: Migrating Board Endpoints

### GET /api/boards
```python
@app.route('/api/boards', methods=['GET'])
@require_authentication
def get_boards():
    """Get all boards for current user."""
    user_id = g.user.id
    db = SessionLocal()
    try:
        boards = get_user_scoped_query(db, Board, user_id).all()
        return jsonify([{
            'id': b.id,
            'name': b.name,
            'description': b.description,
            'is_owner': b.owner_id == user_id
        } for b in boards])
    finally:
        db.close()
```

### POST /api/boards
```python
@app.route('/api/boards', methods=['POST'])
@require_permission('board.create')
def create_board():
    """Create a new board."""
    user_id = g.user.id
    data = request.get_json()
    
    # Validate
    is_valid, error = validate_string_length(data.get('name'), MAX_TITLE_LENGTH, 'Board name')
    if not is_valid:
        return create_error_response(error, 400)
    
    db = SessionLocal()
    try:
        board = Board(
            name=sanitize_string(data['name']),
            description=sanitize_string(data.get('description')),
            owner_id=user_id  # Set owner
        )
        db.add(board)
        db.commit()
        db.refresh(board)
        
        return jsonify({'id': board.id, 'name': board.name}), 201
    finally:
        db.close()
```

### GET /api/boards/<board_id>
```python
@app.route('/api/boards/<int:board_id>', methods=['GET'])
@require_board_access()
def get_board(board_id):
    """Get a specific board."""
    user_id = g.user.id
    db = SessionLocal()
    try:
        board = get_user_scoped_query(db, Board, user_id).filter(
            Board.id == board_id
        ).first()
        
        if not board:
            return create_error_response("Board not found", 404)
        
        return jsonify({
            'id': board.id,
            'name': board.name,
            'description': board.description,
            'owner_id': board.owner_id,
            'is_owner': board.owner_id == user_id
        })
    finally:
        db.close()
```

### DELETE /api/boards/<board_id>
```python
@app.route('/api/boards/<int:board_id>', methods=['DELETE'])
@require_board_access(require_owner=True)
@require_permission('board.delete')
def delete_board(board_id):
    """Delete a board."""
    user_id = g.user.id
    db = SessionLocal()
    try:
        board = get_user_scoped_query(db, Board, user_id).filter(
            Board.id == board_id
        ).first()
        
        if not board:
            return create_error_response("Board not found", 404)
        
        db.delete(board)
        db.commit()
        
        return create_success_response(message="Board deleted")
    finally:
        db.close()
```

## Frontend Authentication Check

Add this to your main app page (index.html):

```javascript
// Check authentication on page load
async function checkAuth() {
    try {
        const response = await fetch('/api/auth/check', {
            credentials: 'include'
        });
        
        if (!response.ok) {
            // Not authenticated, redirect to login
            window.location.href = '/login.html';
            return;
        }
        
        const data = await response.json();
        if (!data.authenticated) {
            window.location.href = '/login.html';
            return;
        }
        
        // Store user info
        window.currentUser = data.user;
        
        // Update UI with user info
        document.getElementById('userName').textContent = data.user.display_name;
        
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login.html';
    }
}

// Run on page load
checkAuth();

// Handle 401 responses globally
document.addEventListener('DOMContentLoaded', () => {
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        
        if (response.status === 401) {
            // Session expired, redirect to login
            window.location.href = '/login.html';
        }
        
        return response;
    };
});
```

## Troubleshooting

### "Not authenticated" errors
- Check that session cookie is being sent (`credentials: 'include'` in fetch)
- Verify SECRET_KEY is set
- Check browser console for CORS issues

### Can't log in
- Verify migrations ran successfully
- Check that user exists in database
- Verify password hashing is working

### Data not showing up
- Ensure you're using `get_user_scoped_query()`
- Check that resources have `owner_id` set
- Verify user has appropriate permissions

## Next Steps

1. **Run migrations** to create user tables
2. **Set admin password** or register a new user
3. **Test authentication** endpoints work
4. **Migrate one API at a time** (start with boards)
5. **Update frontend** to handle authentication
6. **Test thoroughly** with multiple users

See [AUTH_QUICK_REFERENCE.md](AUTH_QUICK_REFERENCE.md) for quick reference on common patterns.
