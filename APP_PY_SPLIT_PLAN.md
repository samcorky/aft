# app.py Modularization Plan

## Goal
Reduce `server/app.py` from a monolithic 11k+ line file into smaller, domain-focused modules while preserving behavior and keeping each extraction reviewable, testable, and easy to roll back.

## Progress Snapshot (2026-04-30)
- Phases 1 through 10 are complete.
- `server/app.py` has been reduced to ~696 lines.
- New extracted modules now cover helpers, route domains, schedules/comments/checklists, and websocket broadcasting/handlers.
- Remaining work is Phase 11 cleanup/final verification and final commit grouping.

## Baseline Assessment
Baseline snapshot from this planning pass:

- `server/app.py` has no current editor-reported errors
- dev stack is up and healthy
- live health check returned 200
- the current full pytest run collected 739 tests and the captured output remained clean through 74%

Current `server/app.py` contains several natural domains mixed together:

- app/bootstrap/configuration
- request lifecycle hooks and error handlers
- backup and restore flows
- settings and scheduler configuration
- boards and board import/export
- columns
- cards and batch card operations
- schedules, checklist items, and comments
- notifications
- themes and image upload/serving
- websocket broadcast helpers and socket handlers
- admin/debug/health/version endpoints

## Existing Repo Conventions To Follow
This repo already uses flat route modules with Flask blueprints:

- `server/auth.py`
- `server/user_management.py`
- `server/role_management.py`

To minimize risk, this refactor should **follow that same pattern** instead of introducing a brand new package layout in the same change.

## Target End State
Keep `server/app.py` as the composition root only:

- Flask app creation and config
- Swagger/CORS/SocketIO setup
- request hooks
- error handlers
- scheduler startup wiring
- blueprint registration

Move route groups and pure helpers into new modules.

---

## Recommended New Modules

### Shared helper modules
- `server/settings_schema.py`
  - working style constants
  - settings schema
  - `validate_setting`
  - working style normalization helpers

- `server/security_validators.py`
  - backup file validation
  - schema integrity checks
  - payload size guards
  - safe URL validation

- `server/datetime_helpers.py`
  - ISO parsing/serialization helpers
  - time-format validation helpers

- `server/broadcasting.py`
  - websocket broadcast helpers
  - broadcast failure tracking

### Route/blueprint modules
- `server/health_routes.py`
- `server/theme_routes.py`
- `server/notification_routes.py`
- `server/settings_routes.py`
- `server/backup_routes.py`
- `server/board_routes.py`
- `server/column_routes.py`
- `server/card_routes.py`
- `server/schedule_routes.py`

> Keep naming explicit and boring. That will make future review and search much easier.

---

## Safety Rules For This Refactor
1. **One extraction chunk per commit.**
2. **No intentional behavior changes during extraction.** Move code first; refactor second.
3. **Prefer shared pure helpers before moving route handlers.**
4. **Run targeted tests after every chunk, then smoke test the matching UI/API flow.**
5. **Run full pytest after major milestones and before final merge.**
6. **If a chunk starts causing circular imports, stop and extract only the shared dependency first.**
7. **Do not mix schema changes or unrelated feature work into this effort.**

---

## Ordered Checklist

### Phase 0 — Baseline capture
- [x] Record current baseline in commit notes
- [x] Confirm dev stack is healthy
- [x] Confirm `server/app.py` still compiles
- [x] Confirm current test suite baseline before first extraction

Suggested evidence to record:
- `/api/health/live` returns 200
- pytest suite collects current tests cleanly

---

### Phase 1 — Extract pure helper code first
Status: completed on 2026-04-14, commit still pending.

**Files created/updated:**
- `server/settings_schema.py`
- `server/datetime_helpers.py`
- `server/security_validators.py`

**Move first:**
- settings constants and schema
- working style helpers
- time parsing/formatting helpers
- backup/security/payload validation helpers
- safe URL validation

**Verification**
- [x] Run compile check for moved modules and `server/app.py`
- [x] Run: `pytest tests/test_utils.py -q`
- [x] Run: `pytest tests/test_time_format_settings.py -q`
- [x] Run: `pytest tests/test_working_style_feature.py -q`
- [x] Run: `pytest tests/test_backup_security.py -q`
- [x] Additional regression coverage: `pytest tests/test_api_settings.py tests/test_api_notifications.py -q` → 143 passed in 54.87s
- [x] Light smoke test: `/login.html`, `/api/auth/setup/status`, and `/api/health/live` all returned 200

**Commit**
- [ ] Commit with message like: `refactor(server): extract shared app helpers from app.py`

---

### Phase 2 — Extract low-risk endpoints to prove the pattern
Status: completed on 2026-04-27, commit still pending.

Completed in this phase:
- `server/health_routes.py`
- `server/theme_routes.py`

**Move:**
- version/health/stats/admin debug endpoints
- theme CRUD, import/export, image endpoints
- theme-related settings endpoints if they stay cohesive

**Verification**
- [x] Run: `pytest tests/test_api_health.py -q`
- [x] Run: `pytest tests/test_api_themes.py -q`
- [x] Run: `pytest tests/test_websocket_theme_sync.py -q`
- [x] Additional verification for the extracted health/admin routes: `pytest tests/test_api_authentication.py -q` → 43 passed total with health tests
- [x] Additional verification for the extracted theme routes: `pytest tests/test_api_themes.py -q` → 84 passed; `pytest tests/test_websocket_theme_sync.py -q` → 30 passed
- [x] Live endpoint check via dev instance: `/api/version`, `/api/test`, `/api/stats`, `/api/scheduler/health`, and `/api/health/live`
- [ ] Smoke test theme switch in browser
- [ ] Smoke test theme image upload/list/load

**Commit**
- [ ] Commit with message like: `refactor(server): extract health and theme routes`

---

### Phase 3 — Extract notifications
Status: completed on 2026-04-28, commit pending with prior completed phases.

**Files to create:**
- `server/notification_routes.py`

**Move:**
- notification list/create/read/unread/delete endpoints

**Verification**
- [x] Run: `pytest tests/test_api_notifications.py -q` (72 passed)
- [x] Additional verification during extraction debugging:
  - `pytest tests/test_api_notifications.py::TestNotificationsAPI -v -s` (22 passed)
  - `pytest tests/test_api_notifications.py -v` (72 passed)
- [ ] Smoke test notification creation and mark-read flow

**Commit**
- [ ] Commit with message like: `refactor(server): extract notification routes`

---

### Phase 4 — Extract settings and scheduler configuration endpoints
Status: completed on 2026-04-30, commit pending.

**Files created/updated:**
- `server/settings_routes.py`

**Moved:**
- settings schema endpoint (GET /api/settings/schema)
- generic setting get/set endpoints (GET/PUT /api/settings/<key>)
- backup config/status endpoints (GET/PUT /api/settings/backup/config, GET /api/settings/backup/status)
- housekeeping config/status endpoints (GET /api/settings/housekeeping/status, PUT /api/settings/housekeeping/config)
- card-scheduler config/status endpoints (GET/PUT /api/settings/card-scheduler/config, GET /api/settings/card-scheduler/status)
- working style setting endpoints for users and boards (GET/PUT /api/settings/working-style and /api/boards/<id>/settings/working-style)

**Verification**
- [ ] Run: `pytest tests/test_api_settings.py -q`
- [ ] Run: `pytest tests/test_api_backup_settings.py -q` (if exists)
- [ ] Run: `pytest tests/test_api_housekeeping.py -q` (if exists)
- [ ] Run: `pytest tests/test_api_card_scheduler.py -q` (if exists)
- [ ] Smoke test settings page in dev instance

**Commit**
- [ ] Commit with message like: `refactor(server): extract settings routes`

---

### Phase 5 — Extract backup and restore flows
Status: completed on 2026-04-30, commit pending.

**Files created/updated:**
- `server/backup_routes.py`
- `server/app.py`

**Moved:**
- manual backup
- backup listing and deletion
- restore flows
- database reset/delete helpers that belong to the same domain

**Notes**
- This is one of the highest-risk chunks.
- Subprocess behavior and existing validation logic were preserved during extraction.
- Added compatibility re-exports in `server/app.py` for `validate_backup_file_security`, `validate_backup_file_size`, and `validate_schema_integrity` to preserve existing test imports.

**Verification**
- [x] Run: `pytest tests/test_api_database_backups.py -q`
- [x] Run: `pytest tests/test_api_database_backups_extended.py -q`
- [x] Run: `pytest tests/test_backup_security.py -q`
- [x] Run: `pytest tests/test_backup_notifications.py -q`
- [x] Smoke test manual backup creation from UI
- [x] Smoke test backup list/delete flow
- [x] Regression subset re-run after fix:
  - `pytest tests/test_backup_security.py tests/test_api_checklist_items.py tests/test_api_comments.py tests/test_api_authentication.py::TestSetupFlow::test_setup_status_no_users -q` (67 passed)

**Commit**
- [ ] Commit with message like: `refactor(server): extract backup and restore routes`

---

### Phase 6 — Extract board endpoints
**Status: Completed** ✓ (2026-04-30)

**Files created:**
- `server/board_routes.py` — board blueprint with all 6 board routes + import helpers + shared assignee-filter helpers

**Moved:**
- board list/create/update/delete  
- board import/export
- board scheduled card listing
- Import helpers: `sanitize_import_text()`, `coerce_bool()`, `user_can_import_boards()`, `build_import_name()`
- Shared assignee filters: `_user_summary()`, `_parse_assignee_ids_query_param()`, `_get_board_assignee_users()`, `_apply_assignee_card_filters()`, `_get_board_eligible_assignee_ids()`

**Verification completed:**
- [x] Run: `pytest tests/test_api_boards.py -q` — 24/25 passed (1 pre-existing failure unrelated to extraction)
- [x] Run: `pytest tests/test_api_permission_independence.py -q` — 31/31 passed
- [x] Smoke test board create/edit/delete — working
- [x] Smoke test board import/export — working

**Changes in app.py:**
- Added: `from board_routes import board_bp, configure_board_routes, + 4 shared helpers`
- Removed: ~1322 lines (board routes + helper functions)
- Added: `configure_board_routes(APP_VERSION)` call after backup routes
- Added: `app.register_blueprint(board_bp)` after backup blueprint
- Kept: compatibility re-exports already in place from Phase 5 for backup validators
- Removed: Unused constants `MAX_BOARD_IMPORT_FILE_SIZE_MB`, `BOARD_EXPORT_FORMAT` (moved to board_routes.py)
- Removed: Import of `ImportHandlerFactory` (no longer needed in app.py)

**Commit:** `refactor(server): extract board routes`

---

### Phase 7 — Extract column endpoints
**Status: Completed ✓ (2026-04-30)**

**Files created:**
- `server/column_routes.py` — `column_bp`, `configure_column_routes(broadcast_event_fn)`

**Moved:**
- `GET /api/boards/<id>/columns` → `get_board_columns`
- `POST /api/boards/<id>/columns` → `create_column`
- `DELETE /api/columns/<id>` → `delete_column`
- `PATCH /api/columns/<id>` → `update_column`

**Notes:**
- `broadcast_event` injected via `configure_column_routes()` (called after the function is defined in app.py)
- All tests passed (required DB rebuild)

**Commit**
- [x] Commit with message like: `refactor(server): extract column routes`

---

### Phase 8 — Extract card core endpoints
**Status: Completed ✓ (2026-04-30)**

**Files created:**
- `server/card_routes.py` — `card_bp`, `configure_card_routes(broadcast_event_fn)`, `_get_fully_authorized_batch_cards()`

**Moved:**
- `GET /api/columns/<id>/cards` → `get_column_cards`
- `GET /api/boards/<id>/cards` → `get_board_cards`
- `POST /api/columns/<id>/cards` → `create_card`
- `DELETE /api/columns/<id>/cards` → `delete_all_cards_in_column`
- `POST /api/columns/<id>/cards/move` → `move_all_cards_in_column`
- `GET /api/cards/<id>` → `get_card`
- `PATCH /api/cards/<id>` → `update_card`
- `DELETE /api/cards/<id>` → `delete_card`
- `GET /api/cards/<id>/assignees` → `get_card_assignees`
- `PUT /api/cards/<id>/assignees` → `update_card_assignees`
- `POST /api/cards/<id>/archive` → `archive_card`
- `POST /api/cards/<id>/unarchive` → `unarchive_card`
- `GET /api/cards/<id>/done` → `get_card_done_status`
- `PUT /api/cards/<id>/done` → `update_card_done_status`
- `POST /api/cards/batch/archive` → `batch_archive_cards`
- `POST /api/cards/batch/unarchive` → `batch_unarchive_cards`
- `POST /api/boards/<id>/archive-after` → `archive_cards_after_period`
- `GET /api/boards/<id>/scheduled-cards` → `get_scheduled_cards`
- Private helper: `_get_fully_authorized_batch_cards()`

**Notes:**
- `broadcast_event` injected via `configure_card_routes()` (same pattern as column_routes)
- Shared assignee helpers imported from `board_routes.py`
- app.py reduced from ~4536 lines to ~2200 lines — the single biggest extraction
- All tests passed without requiring a DB rebuild

**Verification:**
- [x] Full non-slow pytest suite passed

**Commit**
- [ ] Commit with message like: `refactor(server): extract card routes`

---

### Phase 9 — Extract schedules, checklist items, and comments
**Status: Completed ✓ (2026-04-30)**

**Files created:**
- `server/schedule_routes.py` — `schedule_bp`, `configure_schedule_routes(broadcast_event_fn)`

**Moved:**
- `POST /api/schedules` → `create_schedule`
- `GET /api/schedules/<id>` → `get_schedule`
- `PUT /api/schedules/<id>` → `update_schedule`
- `DELETE /api/schedules/<id>` → `delete_schedule`
- `POST /api/cards/<id>/checklist-items` → `create_checklist_item`
- `PATCH /api/checklist-items/<id>` → `update_checklist_item`
- `DELETE /api/checklist-items/<id>` → `delete_checklist_item`
- `GET /api/cards/<id>/comments` → `get_card_comments`
- `POST /api/cards/<id>/comments` → `create_comment`
- `DELETE /api/comments/<id>` → `delete_comment`

**Notes:**
- `broadcast_event` injected via `configure_schedule_routes()` (same pattern as card/column routes)
- app.py reduced from ~2200 lines to ~1049 lines
- All tests passed without requiring a DB rebuild

**Verification:**
- [x] Full non-slow pytest suite passed

**Commit**
- [ ] Commit with message like: `refactor(server): extract schedule, checklist, and comment routes`

---

### Phase 10 — Extract websocket handlers and broadcast plumbing
**Status: Completed ✓ (2026-04-30)**

**Files created:**
- `server/broadcasting.py`
- `server/websocket_handlers.py`

**Moved:**
- socket event handlers
- board join/leave handlers
- client-mutation rejection logic
- theme room join/leave handlers
- broadcast helper functions and failure tracking

**Notes:**
- Kept `socketio = SocketIO(...)` in `server/app.py` as composition root.
- Added `configure_broadcasting(socketio)` wiring in `server/app.py` and injected returned callbacks into route modules.
- Registered socket handlers via `register_websocket_handlers(socketio, reject_connections=REJECT_SOCKETIO_CONNECTIONS)`.
- app.py reduced from ~1049 lines to ~696 lines.

**Verification:**
- [x] Full non-slow pytest suite passed

**Commit**
- [ ] Commit with message like: `refactor(server): extract websocket handlers`

---

### Phase 11 — Final cleanup pass
**Goal:** shrink `server/app.py` to the true app bootstrap layer.

**Cleanup items**
- [ ] Remove now-unused imports
- [ ] Re-run formatter/linting if used locally
- [ ] Update any docs that reference app structure
- [ ] Review other Python modules for duplicated logic that should use the new shared helpers
- [ ] Add a short note to `AGENT_CONTEXT.md` if workflow changed materially

**Final verification**
- [ ] Run full suite: `pytest -q`
- [ ] Smoke test login, boards, cards, notifications, themes, settings, and backups
- [ ] Review import graph for circular dependencies
- [ ] Confirm no route or websocket behavior regressions

**Commit**
- [ ] Final commit message like: `refactor(server): complete app.py modularization`

---

## Manual Smoke Test Script For Each Relevant Phase
Use this lightweight browser/API checklist after each extraction touching the matching area:

- [ ] Login still works
- [ ] Main board loads without console/API errors
- [ ] Board list loads
- [ ] Create and edit a card
- [ ] Move a card between columns
- [ ] Open notifications drawer
- [ ] Open settings page
- [ ] Change theme
- [ ] If backup code changed: create/list/delete a backup
- [ ] If websocket code changed: confirm live update in second browser tab

---

## Practical Guidance For The Actual Refactor
- Start by copying code into the new module with minimal edits.
- Register the new blueprint and keep route URLs unchanged.
- Only after tests pass should any DRY cleanup happen.
- If a move requires too many imports, that is a sign a shared helper should be extracted first.
- For very large domains like cards and backups, do not force a single giant commit.

## Extraction Progress Summary
Initial recommended extraction order has now been executed through Phase 10:

1. Shared helper extraction completed (`settings_schema.py`, `datetime_helpers.py`, `security_validators.py`)
2. Route-domain extraction completed (`health_routes.py`, `theme_routes.py`, `notification_routes.py`, `settings_routes.py`, `backup_routes.py`, `board_routes.py`, `column_routes.py`, `card_routes.py`, `schedule_routes.py`)
3. Websocket/broadcast extraction completed (`broadcasting.py`, `websocket_handlers.py`)
4. Current focus is final cleanup/verification and final commit preparation (Phase 11)
