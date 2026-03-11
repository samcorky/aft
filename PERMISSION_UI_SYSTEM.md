# Permission-Based UI Rendering System

## Overview

The Permission-Based UI Rendering System provides a centralized, extensible approach to managing UI element visibility based on user permissions. The system ensures that users only see and interact with UI elements they have permission to use.

## Architecture

The system consists of three main components:

### 1. Backend API Endpoint (`/api/permissions/mapping`)

Located in `server/app.py`, this endpoint provides:
- A comprehensive mapping of API endpoints to their required permissions
- The current user's permissions (global and board-specific)

**Response Format:**
```json
{
  "success": true,
  "endpoint_permissions": {
    "POST /api/boards/:id/columns": {
      "permission": "column.create",
      "description": "Create column"
    },
    "POST /api/columns/:id/cards": {
      "permission": "card.create",
      "description": "Create card"
    }
    // ... more endpoints
  },
  "user_permissions": [
    "board.view",
    "card.view",
    "card.create"
    // ... more permissions
  ],
  "board_id": 123
}
```

### 2. Frontend Permission Manager (`www/js/permission-manager.js`)

A JavaScript module that:
- Loads permission mappings on page load
- Caches permissions in memory for fast lookups
- Provides utility methods for permission checks
- Handles conditional DOM rendering

### 3. Page Integration

Pages integrate the system by:
1. Loading the permission-manager.js script
2. Initializing the PermissionManager before rendering
3. Using permission checks to conditionally render UI elements

## Usage Guide

### Basic Setup (Board Page Example)

#### 1. Include the Script in HTML

```html
<!-- In board.html -->
<script src="/js/utils.js"></script>
<script src="/js/permission-manager.js"></script> <!-- Load before other page scripts -->
<script src="/js/board.js"></script>
```

#### 2. Initialize in JavaScript

```javascript
// In board.js or page-specific script
async init() {
  const boardId = this.getBoardId(); // Get board ID from URL or context
  
  // Initialize PermissionManager with board context
  const success = await PermissionManager.init(boardId);
  
  if (!success) {
    console.warn('Failed to initialize permissions - some features may not be available');
  }
  
  // Continue with rest of initialization
  this.render();
  // ...
}
```

#### 3. Apply Permission-Based Rendering

```javascript
// After rendering UI elements, apply permission checks
applyPermissionBasedRendering() {
  if (!PermissionManager.initialized) {
    console.log('PermissionManager not available');
    return;
  }
  
  // Remove buttons if user lacks permissions
  if (!PermissionManager.hasPermission('column.create')) {
    document.querySelectorAll('.add-column-btn').forEach(btn => btn.remove());
  }
  
  if (!PermissionManager.hasPermission('card.create')) {
    document.querySelectorAll('.add-card-btn').forEach(btn => btn.remove());
  }
  
  // More permission checks...
}
```

## API Reference

### PermissionManager Methods

#### `init(boardId)`
Initialize the permission manager by loading permissions from the API.

**Parameters:**
- `boardId` (number|null): Optional board ID for board-specific permissions

**Returns:** `Promise<boolean>` - True if initialization succeeded

**Example:**
```javascript
await PermissionManager.init(123);
```

#### `hasPermission(permission)`
Check if the user has a specific permission.

**Parameters:**
- `permission` (string): Permission to check (e.g., 'card.create')

**Returns:** `boolean` - True if user has the permission

**Example:**
```javascript
if (PermissionManager.hasPermission('card.create')) {
  showAddCardButton();
}
```

#### `canCallEndpoint(method, endpoint)`
Check if the user can call a specific API endpoint.

**Parameters:**
- `method` (string): HTTP method (GET, POST, PATCH, DELETE, etc.)
- `endpoint` (string): API endpoint path (can include :id placeholders)

**Returns:** `boolean` - True if user has permission to call this endpoint

**Example:**
```javascript
if (PermissionManager.canCallEndpoint('POST', '/api/boards/:id/columns')) {
  renderAddColumnButton();
}
```

#### `renderIfAllowed(element, method, endpoint, mode)`
Conditionally render a DOM element based on endpoint permission.

**Parameters:**
- `element` (HTMLElement): DOM element to conditionally render
- `method` (string): HTTP method
- `endpoint` (string): API endpoint path
- `mode` (string): 'remove' (default) or 'hide' - how to handle no permission

**Returns:** `boolean` - True if element should be/is rendered

**Example:**
```javascript
const addButton = document.getElementById('add-column-btn');
PermissionManager.renderIfAllowed(addButton, 'POST', '/api/boards/:id/columns');
```

#### `renderIfHasPermission(element, permission, mode)`
Conditionally render a DOM element based on specific permission.

**Parameters:**
- `element` (HTMLElement): DOM element to conditionally render
- `permission` (string): Permission to check
- `mode` (string): 'remove' (default) or 'hide'

**Returns:** `boolean` - True if element should be/is rendered

**Example:**
```javascript
const editButton = document.getElementById('edit-card-btn');
PermissionManager.renderIfHasPermission(editButton, 'card.edit');
```

#### `applyToElements(selector, container)`
Apply permission checks to multiple elements using data attributes.

**Parameters:**
- `selector` (string): CSS selector (defaults to '[data-permission-method]')
- `container` (HTMLElement): Container to search within (defaults to document)

**Example:**
```html
<button data-permission-method="POST" 
        data-permission-endpoint="/api/boards/:id/columns">
  Add Column
</button>
```

```javascript
// Apply to all elements with data attributes
PermissionManager.applyToElements();
```

#### `wrapHandler(handler, method, endpoint)`
Create a wrapper function for event handlers that only executes if the user has permission.

**Parameters:**
- `handler` (Function): Event handler function
- `method` (string): HTTP method
- `endpoint` (string): API endpoint

**Returns:** `Function` - Wrapped handler

**Example:**
```javascript
const deleteHandler = PermissionManager.wrapHandler(
  () => deleteCard(cardId),
  'DELETE',
  '/api/cards/:id'
);

deleteButton.addEventListener('click', deleteHandler);
```

#### `reload(boardId)`
Reload permissions (e.g., after board change or role assignment change).

**Parameters:**
- `boardId` (number|null): Optional board ID

**Returns:** `Promise<boolean>` - True if reload succeeded

**Example:**
```javascript
// After switching boards
await PermissionManager.reload(newBoardId);
```

#### `getUserPermissions()`
Get all user permissions.

**Returns:** `Array<string>` - Array of permission strings

**Example:**
```javascript
const perms = PermissionManager.getUserPermissions();
console.log('User permissions:', perms);
```

#### `getEndpointInfo(method, endpoint)`
Get information about an endpoint (permission required, description).

**Parameters:**
- `method` (string): HTTP method
- `endpoint` (string): API endpoint path

**Returns:** `object|null` - Endpoint info or null if not found

**Example:**
```javascript
const info = PermissionManager.getEndpointInfo('POST', '/api/boards/:id/columns');
console.log(info); // { permission: 'column.create', description: 'Create column' }
```

## Extending to Other Pages

To extend this system to other pages (settings, role management, etc.):

### 1. Update the Backend Mapping

Add new endpoint->permission mappings in `server/app.py`:

```python
endpoint_mapping = {
    # ... existing mappings
    
    # New page endpoints
    'GET /api/my-feature': {'permission': 'my.permission', 'description': 'Get my feature'},
    'POST /api/my-feature': {'permission': 'my.create', 'description': 'Create my feature'},
}
```

### 2. Load Permission Manager in Page HTML

```html
<!-- In my-page.html -->
<script src="/js/utils.js"></script>
<script src="/js/permission-manager.js"></script>
<script src="/js/my-page.js"></script>
```

### 3. Initialize in Page JavaScript

```javascript
// In my-page.js
document.addEventListener('DOMContentLoaded', async () => {
  // Initialize permission manager (no board context for global pages)
  await PermissionManager.init();
  
  // Render page
  renderPage();
  
  // Apply permissions
  applyPermissions();
});

function applyPermissions() {
  // Hide/remove elements based on permissions
  if (!PermissionManager.hasPermission('my.create')) {
    document.getElementById('create-button').remove();
  }
}
```

### 4. Use Data Attributes for Declarative Rendering

```html
<!-- Buttons with permission data attributes -->
<button id="create-btn" 
        data-permission-method="POST" 
        data-permission-endpoint="/api/my-feature"
        data-permission-mode="hide">
  Create Feature
</button>

<button id="delete-btn"
        data-permission-method="DELETE"
        data-permission-endpoint="/api/my-feature/:id">
  Delete Feature
</button>
```

```javascript
// Apply all permissions at once
PermissionManager.applyToElements();
```

## Best Practices

### 1. Initialize Early
Always initialize PermissionManager before rendering UI elements:

```javascript
// ✅ Good
await PermissionManager.init(boardId);
renderUI();

// ❌ Bad
renderUI();
await PermissionManager.init(boardId); // Too late!
```

### 2. Check Permissions Before API Calls
Even though the backend enforces permissions, check on frontend for better UX:

```javascript
async function deleteCard(cardId) {
  if (!PermissionManager.canCallEndpoint('DELETE', '/api/cards/:id')) {
    showNotification('You do not have permission to delete cards', 'error');
    return;
  }
  
  // Proceed with API call
  await fetch(`/api/cards/${cardId}`, { method: 'DELETE' });
}
```

### 3. Use Specific Permissions Over Endpoint Checks
When checking general capabilities, use `hasPermission()`:

```javascript
// ✅ Good - checks general permission
if (PermissionManager.hasPermission('card.create')) {
  showAddCardOption();
}

// ❌ Less flexible - tied to specific endpoint
if (PermissionManager.canCallEndpoint('POST', '/api/columns/:id/cards')) {
  showAddCardOption();
}
```

### 4. Handle Missing Permissions Gracefully
Always provide fallback behavior:

```javascript
if (!PermissionManager.initialized) {
  console.warn('Permissions not loaded - using default behavior');
  // Show read-only UI or error message
}
```

### 5. Reload After Permission Changes
When user roles change, reload permissions:

```javascript
async function assignRole(userId, roleId) {
  await fetch('/api/users/' + userId + '/roles', {
    method: 'POST',
    body: JSON.stringify({ role_id: roleId })
  });
  
  // Reload permissions if it's the current user
  if (userId === currentUserId) {
    await PermissionManager.reload();
    // Re-render UI with new permissions
    renderUI();
  }
}
```

## Security Considerations

### Frontend Checks Are Not Security
- The frontend permission system is for UX only
- **Always** enforce permissions on the backend
- Hiding UI elements does not prevent API access
- Users can bypass frontend checks via developer tools

### Backend Enforcement
All API endpoints must use permission decorators:

```python
@app.route("/api/boards/<int:board_id>/columns", methods=["POST"])
@require_permission('column.create')
def create_column(board_id):
    # Backend enforces permission
    ...
```

## Troubleshooting

### Permissions Not Loading

**Problem:** `PermissionManager.initialized` is `false`

**Solutions:**
1. Check browser console for errors
2. Verify user is logged in
3. Check API endpoint `/api/permissions/mapping` is accessible
4. Ensure `permission-manager.js` is loaded before page scripts

### Buttons Still Visible Without Permission

**Problem:** Buttons show even though user lacks permission

**Solutions:**
1. Ensure `applyPermissionBasedRendering()` is called after DOM is rendered
2. Check if button selector matches in permission check code
3. Verify permission mapping in backend includes the endpoint
4. Check browser console for permission check results

### Board-Specific Permissions Not Working

**Problem:** User has global permissions but not board-specific

**Solutions:**
1. Pass `boardId` to `PermissionManager.init(boardId)`
2. Check user's board-specific roles in database
3. Verify board ownership in backend logic

## Examples

### Board Detail Page Integration

See [board.js](www/js/board.js) for the complete implementation on the board detail page.

### Boards List Page Integration

The boards list page demonstrates a hybrid approach where:
- Backend calculates board-specific permissions (ownership + board-specific roles)
- Frontend uses PermissionManager for consistent rendering pattern
- Falls back gracefully if PermissionManager is unavailable

**Key Implementation** ([boards.js](www/js/boards.js)):

```javascript
class BoardsManager {
  async init() {
    // Initialize PermissionManager without board context (global permissions)
    await PermissionManager.init();
    
    // Load and render boards
    await this.loadBoards();
  }
  
  renderBoardsList() {
    // Always render edit/delete buttons in HTML
    // Mark cards with backend permission flags as data attributes
    listContainer.innerHTML = this.boards.map(board => `
      <div class="board-card" 
           data-board-id="${board.id}"
           data-can-edit="${board.can_edit}"
           data-can-delete="${board.can_delete}">
        <button class="board-edit-btn">✎</button>
        <button class="board-delete-btn">×</button>
        <h4>${board.name}</h4>
      </div>
    `).join('');
    
    // Apply permission-based rendering after DOM is ready
    this.applyPermissionBasedRendering();
  }
  
  applyPermissionBasedRendering() {
    // For each board card, check backend permission flags
    document.querySelectorAll('.board-card').forEach(card => {
      const canEdit = card.getAttribute('data-can-edit') === 'true';
      const canDelete = card.getAttribute('data-can-delete') === 'true';
      
      // Remove buttons if no permission
      if (!canEdit) {
        card.querySelector('.board-edit-btn')?.remove();
      }
      if (!canDelete) {
        card.querySelector('.board-delete-btn')?.remove();
      }
    });
    
    // Check global permission for creating boards
    if (!PermissionManager.hasPermission('board.create')) {
      document.getElementById('add-board-btn')?.remove();
    }
  }
}
```

**Why This Approach?**

Board permissions are complex because they depend on:
- Board ownership (board owners have full control)
- Board-specific role assignments
- Global role permissions

The backend already calculates these per-board in the `/api/boards` endpoint:

```python
# Backend calculates board-specific permissions
for board in boards:
    board_permissions = get_user_permissions(user_id, board_id=board.id)
    can_delete = 'board.delete' in board_permissions
    can_edit = 'board.edit' in board_permissions
    # Return flags to frontend
```

The frontend then uses a consistent pattern (via PermissionManager) to apply these permissions, while also checking global permissions for actions like "Create New Board".

### Complete Page Integration Example

```javascript
// example-page.js
class ExamplePageManager {
  constructor() {
    this.data = [];
  }
  
  async init() {
    // Initialize permissions first
    await PermissionManager.init();
    
    // Load data
    await this.loadData();
    
    // Render UI
    this.render();
    
    // Apply permission-based rendering
    this.applyPermissions();
  }
  
  render() {
    const container = document.getElementById('content');
    container.innerHTML = `
      <button id="create-btn">Create Item</button>
      <button id="delete-btn">Delete Item</button>
      <button id="edit-btn">Edit Item</button>
    `;
    
    // Add event listeners
    document.getElementById('create-btn')?.addEventListener('click', () => this.createItem());
    document.getElementById('delete-btn')?.addEventListener('click', () => this.deleteItem());
    document.getElementById('edit-btn')?.addEventListener('click', () => this.editItem());
  }
  
  applyPermissions() {
    // Remove buttons based on permissions
    if (!PermissionManager.hasPermission('item.create')) {
      document.getElementById('create-btn')?.remove();
    }
    if (!PermissionManager.hasPermission('item.delete')) {
      document.getElementById('delete-btn')?.remove();
    }
    if (!PermissionManager.hasPermission('item.edit')) {
      document.getElementById('edit-btn')?.remove();
    }
  }
  
  async createItem() {
    if (!PermissionManager.canCallEndpoint('POST', '/api/items')) {
      showNotification('No permission', 'error');
      return;
    }
    // API call...
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
  const manager = new ExamplePageManager();
  await manager.init();
});
```

## Maintenance

### Adding New Permissions

1. **Update `permissions.py`** - Add new permission to `PERMISSION_DEFINITIONS`
2. **Update `app.py`** - Add endpoint->permission mapping
3. **Update frontend** - Use permission in UI rendering logic

### Adding New API Endpoints

1. **Create endpoint in `app.py`** with `@require_permission()` decorator
2. **Add to mapping** in `/api/permissions/mapping` endpoint
3. **Update frontend** to check permission before API call

## Summary

The Permission-Based UI Rendering System provides:
- ✅ Centralized permission management
- ✅ Consistent UI/API permission enforcement
- ✅ Extensible to all pages
- ✅ Easy to add new permissions and endpoints
- ✅ Better user experience (hide unavailable features)
- ✅ Reduced errors (prevent unauthorized actions)

By following this system, you ensure that users only see and interact with features they're authorized to use, while maintaining a clean and maintainable codebase.
