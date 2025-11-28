# AFT
Atlassian Free Trello.

## What?
Kanban style task organisation.

## Why?
Trello was great, then Atlassian bought it.

## How?
- Clone the repo to a machine running docker
- Edit .env to have more secure passwords
- `docker compose up -d`
- Navigate to http(s)://{docker-host-ip}

### Backup Storage
Automatic backups are stored on the host filesystem at `./backups/` (relative to the docker-compose.yml location). This directory is automatically created by Docker and persists across container restarts. You can include this directory in your host backup solution for additional data protection.

**Permission Requirements**: The container runs as a non-root user (UID 1000). If the `./backups/` directory is not writable, backups will fail with a permission error displayed in the UI. To fix this, run:
```bash
sudo chown -R 1000:1000 ./backups
sudo chmod -R 755 ./backups
```

## When?
In one evening for version 1.
That's right this is entirely copilot generated with my general guidance.
I know what it all does, I have no idea what code was written to achieve it.
Use at your own risk.

## Features

### 📋 Board Management
- **Create Multiple Boards** - Organize different projects with separate Kanban boards
- **Update Board Details** - Rename boards and modify their properties
- **Delete Boards** - Remove boards when projects are complete
- **Default Board Setting** - Set a default board to load on startup
- **Board Statistics** - View counts of boards, columns, and cards

![Board List](images/boards.png)

### 📊 Column Management
- **Flexible Columns** - Create custom columns for your workflow (e.g., To Do, In Progress, Done)
- **Reorder Columns** - Drag and rearrange columns to match your process
- **Column Operations** - Add, edit, or delete columns as your workflow evolves
- **Column Menu** - Access column actions via three-dots menu:
  - **Move All Cards** - Batch move all cards from one column to another (top or bottom position)
  - **Archive All Cards** - Archive all active cards in a column at once
  - **Unarchive All Cards** - Unarchive all archived cards in a column (visible in archive view)
  - **Delete All Cards** - Remove all cards from a column
  - **Delete Column** - Remove the entire column

![Kanban Board](images/board.png)

### 🎴 Card Management
- **Create Cards** - Add task cards with titles and descriptions
- **Move Cards** - Drag cards between columns to track progress
- **Update Cards** - Edit card details, titles, and descriptions
- **Delete Cards** - Remove completed or cancelled tasks
- **Card Filtering** - View cards by column or across entire boards
- **Archive Cards** - Archive completed cards to declutter your board while preserving history
- **Unarchive Cards** - Restore archived cards back to active view when needed
- **Toggle Archive View** - Switch between active and archived cards using the header toggle
- **Batch Operations** - Archive or unarchive multiple cards at once via column menu

![Card Detail](images/card_detail.png)
![Archive View](images/archive_screen.png)

### ✅ Checklist Items
- **Task Breakdown** - Add checklist items to cards for subtasks
- **Track Progress** - Check off items as you complete them
- **Update Checklists** - Modify checklist item text and completion status
- **Remove Items** - Delete checklist items when no longer needed

### 💬 Comments
- **Card Discussion** - Add comments to cards for collaboration
- **Comment History** - View all comments on a card with timestamps
- **Delete Comments** - Remove outdated or incorrect comments

### ⚙️ Settings & Configuration
- **Customizable Settings** - Configure application preferences including default board
- **Automatic Database Backups** - Schedule recurring backups to protect your data
  - Configurable frequency (minutes, hours, or days)
  - Flexible start time alignment for backup scheduling
  - Automatic retention management (keep 1-100 most recent backups)
  - Backup health monitoring with status indicators
  - Overdue backup detection
  - Backups saved to host filesystem via bind mount (`./backups/`)
- **Settings Schema** - View available settings and validation rules
- **Persistent Configuration** - Settings saved to database

![Settings](images/settings.png)

### 🔧 Database Management
- **Manual Backup** - Download on-demand database backups
- **Automatic Backups** - Scheduled backups running in the background
  - Files saved to `./backups/` directory on host
  - Viewable backup module status on system information page
- **Restore Database** - Upload and restore from backup files
- **Reset Database** - Clear all data for fresh start
- **Version Tracking** - Monitor application and database schema versions

![Database Statistics](images/db_stats.png)

### 🔌 API Documentation
- **Interactive API Docs** - Built-in Swagger UI at `/api/docs`
- **RESTful API** - Full API access for integrations and automation
- **Health Checks** - Database connectivity and version endpoints

![API Documentation](images/api_docs.png)