# Authentication Implementation TODO

This file tracks the work needed to integrate authentication into the existing AFT application.

## Phase 1: Database & Core Setup ✅

- [x] Create User, Role, UserRole models
- [x] Add user_id/owner_id columns to existing tables
- [x] Create permission definitions
- [x] Create secure query helper functions
- [x] Create Alembic migrations
- [x] Write documentation

## Phase 2: Run Migrations 🔲

```bash
cd server
python migrate.py upgrade
```

Expected result:
- New tables: users, roles, user_roles
- Updated tables: boards, cards, settings, themes, notifications
- Default admin user created (username: 'admin', email: 'admin@localhost')
- System roles created: administrator, board_admin, editor, read_only

## Phase 3: Authentication Middleware 🔲

### Files to Create/Modify

**New file: `server/auth.py`**
```python
# Authentication middleware and session management
- load_user_from_session() - Load user into g.user
- create_session() - Create session/JWT after login
- destroy_session() - Logout
- password_hash() - Hash passwords securely
- verify_password() - Verify password hashes
```

**Update: `server/app.py`**
```python
# Add before_request hook
@app.before_request
def load_user():
    # Load user from session/JWT into g.user
    pass

# Add authentication endpoints
@app.route('/api/auth/login', methods=['POST'])
def login():
    pass

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    pass

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    pass
```

## Phase 4: Update API Endpoints 🔲

### Priority 1: Board Endpoints (Critical)

**app.py - Board operations**
- [ ] `GET /api/boards` - Add scoped query
  ```python
  boards = get_user_scoped_query(db, Board, g.user.id).all()
  ```
  
- [ ] `POST /api/boards` - Add `@require_permission('board.create')` and set owner_id
  ```python
  board = Board(name=..., owner_id=g.user.id)
  ```
  
- [ ] `GET /api/boards/<id>` - Add `@require_board_access()` and scoped query
  
- [ ] `PATCH /api/boards/<id>` - Add `@require_board_access()` and `@require_permission('board.edit')`
  
- [ ] `DELETE /api/boards/<id>` - Add `@require_board_access(require_owner=True)`

### Priority 2: Card Endpoints (Critical)

**app.py - Card operations**
- [ ] `GET /api/boards/<board_id>/cards` - Add `@require_board_access()` and scoped query
  
- [ ] `POST /api/boards/<board_id>/cards` - Add permissions and set created_by_id
  ```python
  card = Card(..., created_by_id=g.user.id)
  ```
  
- [ ] `PATCH /api/cards/<id>` - Add board access check and scoped query
  
- [ ] `DELETE /api/cards/<id>` - Add board access check and scoped query
  
- [ ] `POST /api/cards/<id>/move` - Add board access check
  
- [ ] Card reordering endpoints - Add board access check

### Priority 3: Settings Endpoints (Important)

**app.py - Settings operations**
- [ ] `GET /api/settings` - Update to return user-specific settings
  ```python
  # Get user's settings + global settings
  settings = get_user_scoped_query(db, Setting, g.user.id).all()
  ```
  
- [ ] `PUT /api/settings/<key>` - Add user_id when creating/updating
  ```python
  setting = Setting(key=key, value=value, user_id=g.user.id)
  ```
  
### Priority 4: Theme Endpoints (Important)

**app.py - Theme operations**
- [ ] `GET /api/themes` - Return user's themes + system themes
  ```python
  themes = get_user_scoped_query(db, Theme, g.user.id).all()
  ```
  
- [ ] `POST /api/themes` - Add `@require_permission('theme.create')` and set user_id
  ```python
  theme = Theme(..., user_id=g.user.id)
  ```
  
- [ ] `PATCH /api/themes/<id>` - Add scoped query and permission check
  
- [ ] `DELETE /api/themes/<id>` - Add scoped query and permission check

### Priority 5: Other Endpoints (Lower Priority)

**Notifications**
- [ ] `GET /api/notifications` - Add scoped query by user_id
- [ ] `PATCH /api/notifications/<id>` - Add scoped query

**Checklist Items**
- [ ] All checklist endpoints - Verify board access through card

**Comments**
- [ ] All comment endpoints - Verify board access through card

**Scheduled Cards**
- [ ] All schedule endpoints - Verify board access through card
- [ ] Add `@require_permission('schedule.create')` etc.

**Backup/Restore**
- [ ] `GET /api/backups` - Add `@require_permission('backup.view')`

**System Info**
- [ ] Consider if system info should require admin permission

## Phase 5: Frontend Updates 🔲

### Authentication UI
- [ ] Create login page
- [ ] Add logout button to UI
- [ ] Show current user in header
- [ ] Handle 401 responses (redirect to login)
- [ ] Handle 403 responses (show access denied)

### API Client Updates
- [ ] Add authentication headers to API calls
- [ ] Store and send JWT/session token
- [ ] Handle token refresh (if using JWT)
- [ ] Clear token on logout

### Feature Flags
- [ ] Show/hide features based on user permissions
- [ ] Example: Hide "Delete Board" if user lacks permission

## Phase 6: Testing 🔲

### Unit Tests
- [ ] Test query scoping prevents cross-user access
- [ ] Test permission decorators block unauthorized access
- [ ] Test role assignments grant correct permissions
- [ ] Test board sharing (when implemented)

### Integration Tests
- [ ] Test full authentication flow (login → access → logout)
- [ ] Test that endpoints require authentication
- [ ] Test that endpoints check permissions
- [ ] Test that users can't access other users' data

### Security Tests
- [ ] Attempt to access other user's boards
- [ ] Attempt operations without required permissions
- [ ] Attempt to manipulate user_id in requests
- [ ] Test SQL injection prevention (parameterized queries)

## Phase 7: OAuth Integration (Optional) 🔲

- [ ] Install OAuth library (`authlib` or similar)
- [ ] Configure OAuth providers (Google, GitHub, etc.)
- [ ] Add OAuth login endpoints
- [ ] Add OAuth callback handlers
- [ ] Link OAuth accounts to existing users
- [ ] Handle OAuth errors and edge cases

## Phase 8: Production Hardening 🔲

### Security
- [ ] Enable HTTPS only
- [ ] Set secure cookie flags
- [ ] Implement CSRF protection
- [ ] Add rate limiting per user
- [ ] Implement account lockout after failed logins
- [ ] Add password complexity requirements
- [ ] Implement password reset flow
- [ ] Add email verification flow

### Monitoring
- [ ] Log authentication attempts
- [ ] Log authorization failures
- [ ] Monitor for suspicious patterns
- [ ] Alert on repeated failed logins

### Documentation
- [ ] Update API documentation with auth requirements
- [ ] Document permission requirements for each endpoint
- [ ] Create user guide for managing users/roles
- [ ] Document OAuth setup process

## Notes

### Backward Compatibility During Migration

You may want to temporarily allow unauthenticated access during the transition:

```python
@app.before_request
def load_user():
    # Try to load user from session
    user_id = session.get('user_id')
    
    if user_id:
        g.user = db.query(User).get(user_id)
    else:
        # TEMPORARY: Default to admin user if not authenticated
        # Remove this after implementing authentication!
        g.user = db.query(User).filter(User.username == 'admin').first()
```

### Testing During Development

Use the `auth_helpers.py` functions to create test users:

```python
from auth_helpers import create_user, assign_role_to_user

# Create test users
editor = create_user('editor@test.com', 'editor')
assign_role_to_user(editor.id, 'editor')

readonly = create_user('viewer@test.com', 'viewer')
assign_role_to_user(readonly.id, 'read_only')
```

### Default Admin Password

The admin user is created without a password. Options:
1. Implement password reset flow and use it to set admin password
2. Directly set password hash in database (for development only)
3. Use OAuth as primary authentication method

```python
# Option 2 (development only):
from werkzeug.security import generate_password_hash

password_hash = generate_password_hash('your_admin_password')
# UPDATE users SET password_hash = '...' WHERE username = 'admin';
```

## Questions/Decisions Needed

- [ ] Which authentication method to implement first? (Session-based vs JWT)
- [ ] Which OAuth providers to support?
- [ ] Should there be a "public" mode for unauthenticated access?
- [ ] Password requirements (length, complexity)?
- [ ] Session timeout duration?
- [ ] Should existing data be visible to all users or just admin?

## Resources

- [AUTHENTICATION.md](AUTHENTICATION.md) - Detailed implementation guide
- [AUTH_QUICK_REFERENCE.md](AUTH_QUICK_REFERENCE.md) - Quick reference for developers
- [permissions.py](permissions.py) - Permission definitions
- [auth_helpers.py](auth_helpers.py) - Helper functions for user management
