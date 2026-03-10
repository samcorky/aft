# Simplified Permission Model

## Overview

The permission system has been simplified to make it clearer how board access and permissions work.

## Key Concepts

### 1. Board Ownership
- **When you create a board, you OWN it**
- Board owners have **full control** over their boards automatically
- Owners can:
  - View, edit, delete the board
  - Manage all cards, columns, and schedules
  - Share the board (grant access to other users)
- **No role assignment needed** - ownership gives you everything

### 2. Board Access for Non-Owners
Board access is granted through **board-specific role assignments only**:
- There is NO "global editor" or "global read only"
- Non-owners must be explicitly granted a role on each board
- Two board-specific roles available:
  - **board_editor** - Full control of that specific board
  - **board_viewer** - Read-only access to that specific board

### 3. Creating New Boards
- Users need the **board.create** permission to create boards
- Assign the **board_creator** role (global) to allow board creation
- When they create a board, they automatically become the owner with full control

## Role Structure

### Global Roles (UserRole.board_id = NULL)

| Role | Description | Use Case |
|------|-------------|----------|
| **administrator** | Full system admin | System management, can see ALL boards |
| **board_creator** | Can create new boards | Regular users who should be able to create their own boards |

### Board-Specific Roles (UserRole.board_id = <board_id>)

| Role | Description | Use Case |
|------|-------------|----------|
| **board_editor** | Full control of the board | Share full access to a specific board |
| **board_viewer** | Read-only access | Share read-only access to a specific board |

## Examples

### Example 1: Regular User Who Creates Boards
```
User: Alice
Global Role: board_creator
Board 1 (owned by Alice): Full control (automatic via ownership)
Board 2 (owned by Bob): No access unless Bob grants a board-specific role
```

### Example 2: Sharing a Board
```
User: Bob (owns Board 2)
Bob wants to share Board 2 with Alice

Option A: Grant Alice full control
  -> Assign "board_editor" role to Alice on Board 2

Option B: Grant Alice read-only access
  -> Assign "board_viewer" role to Alice on Board 2
```

### Example 3: Read-Only User on One Board, Editor on Another
```
User: Charlie
Global Role: (none)
Board 3 (owned by David): Assigned "board_viewer" -> Can only view Board 3
Board 4 (owned by Eve): Assigned "board_editor" -> Full control of Board 4
```

### Example 4: User Who Cannot Create Boards
```
User: Dana
Global Role: (none)
Board 5 (owned by Dana): Can't create this - needs board_creator role first

To fix: Administrator assigns "board_creator" role globally to Dana
Now Dana can create boards which she will own
```

## UI Expectations

### Assigning Roles in the UI
1. **Global roles** (no board selected):
   - `administrator` - System admin only
   - `board_creator` - Regular users who should create boards

2. **Board-specific roles** (board selected):
   - `board_editor` - Full control of that board
   - `board_viewer` - Read-only access to that board

### Role Assignment Rules
- Users can only grant roles on boards they have access to
- Board owners can grant any role on their boards
- Users with `user.role` permission can grant roles they themselves have
- Administrators can grant any role

## Summary

✅ **Simple**: Only 4 roles total (2 global, 2 board-specific)  
✅ **Clear**: Board owners have full control, others need explicit access  
✅ **Secure**: No confusing "global editor" that doesn't grant access  
✅ **Flexible**: Can share boards with fine-grained control  
