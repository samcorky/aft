# app.py Modularization Plan

## Goal
Reduce `server/app.py` from a monolithic 11k+ line file into smaller, domain-focused modules while preserving behavior and keeping each extraction reviewable, testable, and easy to roll back.

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
- [ ] Record current baseline in commit notes
- [ ] Confirm dev stack is healthy
- [ ] Confirm `server/app.py` still compiles
- [ ] Confirm current test suite baseline before first extraction

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
**Files to create:**
- `server/settings_routes.py`

**Move:**
- settings schema endpoint
- generic setting get/set
- backup/housekeeping/card-scheduler config/status endpoints
- working style setting endpoints if not already moved with helper code

**Verification**
- [ ] Run: `pytest tests/test_api_settings.py -q`
- [ ] Run: `pytest tests/test_api_backup_settings.py -q`
- [ ] Run: `pytest tests/test_api_housekeeping.py -q`
- [ ] Run: `pytest tests/test_api_card_scheduler.py -q`
- [ ] Smoke test settings page in dev instance

**Commit**
- [ ] Commit with message like: `refactor(server): extract settings routes`

---

### Phase 5 — Extract backup and restore flows
**Files to create:**
- `server/backup_routes.py`

**Move:**
- manual backup
- backup listing and deletion
- restore flows
- database reset/delete helpers that belong to the same domain

**Notes**
- This is one of the highest-risk chunks.
- Keep subprocess behavior and existing validation intact.
- Avoid cleanup refactors until after parity is proven.

**Verification**
- [ ] Run: `pytest tests/test_api_database_backups.py -q`
- [ ] Run: `pytest tests/test_api_database_backups_extended.py -q`
- [ ] Run: `pytest tests/test_backup_security.py -q`
- [ ] Run: `pytest tests/test_backup_notifications.py -q`
- [ ] Smoke test manual backup creation from UI
- [ ] Smoke test backup list/delete flow

**Commit**
- [ ] Commit with message like: `refactor(server): extract backup and restore routes`

---

### Phase 6 — Extract board endpoints
**Files to create:**
- `server/board_routes.py`

**Move:**
- board list/create/update/delete
- board import/export
- board-level working style endpoints
- board scheduled card listing if dependency placement makes sense

**Verification**
- [ ] Run: `pytest tests/test_api_boards.py -q`
- [ ] Run: `pytest tests/test_api_permission_independence.py -q`
- [ ] Smoke test board create/edit/delete
- [ ] Smoke test board import/export

**Commit**
- [ ] Commit with message like: `refactor(server): extract board routes`

---

### Phase 7 — Extract column endpoints
**Files to create:**
- `server/column_routes.py`

**Move:**
- board column list/create/update/delete
- bulk move helpers that are clearly column-focused

**Verification**
- [ ] Run the relevant cards/board API tests
- [ ] Smoke test column create/rename/delete and drag ordering

**Commit**
- [ ] Commit with message like: `refactor(server): extract column routes`

---

### Phase 8 — Extract card core endpoints
**Files to create:**
- `server/card_routes.py`

**Move:**
- card CRUD
- assignees
- archive/unarchive
- done-state endpoints
- batch archive/unarchive
- archive-after-period endpoints

**Notes**
- This is likely the single biggest API extraction.
- If needed, split this into two commits:
  1. card CRUD + assignees
  2. batch/archive/done flows

**Verification**
- [ ] Run: `pytest tests/test_api_cards.py -q`
- [ ] Run: `pytest tests/test_api_archive_after.py -q`
- [ ] Smoke test card create/edit/move/archive/unarchive
- [ ] Smoke test assignee filters

**Commit**
- [ ] Commit with message like: `refactor(server): extract card routes`

---

### Phase 9 — Extract schedules, checklist items, and comments
**Files to create:**
- `server/schedule_routes.py`

**Move:**
- schedule CRUD
- scheduled card endpoints
- checklist item endpoints
- comment endpoints

**Verification**
- [ ] Run: `pytest tests/test_scheduled_cards.py -q`
- [ ] Run: `pytest tests/test_api_checklist_items.py -q`
- [ ] Run: `pytest tests/test_api_comments.py -q`
- [ ] Run: `pytest tests/test_api_card_scheduler.py -q`
- [ ] Smoke test schedule create/update/delete
- [ ] Smoke test checklist and comments in dev instance

**Commit**
- [ ] Commit with message like: `refactor(server): extract schedule, checklist, and comment routes`

---

### Phase 10 — Extract websocket handlers and broadcast plumbing
**Files to create:**
- `server/broadcasting.py`
- `server/websocket_handlers.py`

**Move:**
- socket event handlers
- board join/leave handlers
- client-mutation rejection logic
- theme room join/leave handlers
- broadcast helper functions and tracking

**Notes**
- Keep `socketio = SocketIO(...)` itself in `app.py`.
- Import/register websocket handlers from the new module.

**Verification**
- [ ] Run: `pytest tests/test_websocket_security.py -q`
- [ ] Run: `pytest tests/test_websocket_theme_sync.py -q`
- [ ] Smoke test board updates in two browser sessions

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

## Recommended First Actual Extraction
If starting immediately after this planning step, the safest first implementation chunk is:

1. extract `settings_schema.py`
2. extract `datetime_helpers.py`
3. extract `security_validators.py`
4. run focused tests
5. commit

That creates the shared foundation needed for the larger route moves.
