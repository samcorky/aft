# AFT Security Review

Date: 2026-03-15  
Reviewer: GitHub Copilot (GPT-5.3-Codex)

## Scope and Method
This review focused on exploitability in increasing order of ease and complexity, with emphasis on gaining unauthorized data access without known usernames/passwords.

Work performed included:
- Static code review of authentication, authorization, setup/bootstrap, notifications, themes, batch card operations, and websocket handlers.
- Live API probing against the running local instance.
- Live websocket probing and event injection tests.
- Session forgery validation using the configured/default Flask secret behavior.

## Executive Summary
Multiple critical and high-severity authorization flaws were confirmed. The most severe chain allows no-password authentication bypass through forged session cookies when the default Flask secret is in use, combined with missing approval checks in session loading. The websocket unauthenticated join and client event-injection issue has now been remediated by enforcing authenticated Socket.IO connections, board-scoped join authorization, and server-only mutation broadcasts. Additional IDOR and scoping flaws were confirmed in notifications, batch card archive operations, and theme operations.

## Findings (Ordered by Severity)

### 1) Critical: No-password authentication bypass via default secret + session approval gap
Status: **Fixed (2026-03-15)**

What was observed:
- Registered a new user (pending approval).
- Normal login was blocked as expected (403 pending approval).
- Forged a valid session cookie offline using the default secret fallback and the returned user id/email hash.
- Authenticated endpoints accepted the forged session (200).

Primary code references:
- server/app.py:215 (default secret fallback)
- server/auth.py:81 (session loader)
- server/auth.py:99-103 (session user lookup checks active, but not approved)
- server/auth.py:699 and server/auth.py:839-848 (register response includes user id and pending status)

Impact:
- Approval workflow can be bypassed.
- Enables credential-less authenticated access.
- Could escalate to account impersonation if user id/email are known for privileged users.

Recommendations:
- ~~Remove secret fallback and fail startup if secret is missing.~~ **FIXED**: `app.py` now raises `RuntimeError` at startup if `SECRET_KEY` env var is absent. The hardcoded fallback `'dev-secret-key-change-in-production'` has been removed.
- **ACTION REQUIRED — Rotate `SECRET_KEY`**: Add a freshly generated value to every `.env` file in all environments. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`. All current sessions will be invalidated on restart (expected behaviour after a key compromise).
- ~~Enforce is_approved in session-based loading path (same policy as login).~~ **FIXED**: `auth.py` `load_user_from_session()` now filters `User.is_approved == True` alongside `User.is_active == True`. Unapproved users are rejected at session load on every authenticated request.
- ~~Consider server-side session store with opaque ids rather than trustable client-signed user identifiers.~~ **IMPLEMENTED (Feature Flag)**: Redis-backed server-side sessions are now available via `ENABLE_SERVER_SIDE_SESSIONS=true`. This stores session data server-side and sends only an opaque session identifier cookie to clients.

---

### 2) Critical: Unauthenticated websocket room join and event injection
Status: **Fixed (2026-03-15)**

What was observed:
- Socket.IO connection succeeded without authentication.
- join_board accepted arbitrary board id and returned room_joined.
- Unauthenticated client emitted card_updated; second client in same room received spoofed event.

Primary code references:
- server/auth.py:127 (`get_authenticated_socket_user`)
- server/app.py:9607 (`handle_connect`)
- server/app.py:9633 (`on_join_board`)
- server/app.py:9666 (`on_leave_board`)
- server/app.py:9566 (`_reject_client_originated_mutation`)
- server/app.py:9702, 9713, 9723 (client-emitted card mutation events)
- server/app.py:9777 and 9812 (`join_theme` / `leave_theme`)
- server/tests/test_websocket_security.py:29-90 (websocket regression coverage)

Impact:
- Unauthorized realtime data observation risk.
- UI integrity risk from forged events (confusion, spoofed activity, trust erosion).

Actions taken:
- Added a shared session-resolution helper so Socket.IO handlers can reuse the same active/approved session validation model as HTTP request authentication.
- Changed Socket.IO `connect` to reject unauthenticated clients before a websocket session is established.
- Changed `join_board` and `leave_board` to validate `board_id` and authorize board membership with the existing server-side `can_access_board(...)` policy.
- Changed `join_theme` and `leave_theme` to require an authenticated websocket session.
- Replaced client-originated mutation broadcasts with explicit rejection responses; realtime updates now continue to flow only from server-side validated REST handlers via the existing broadcast path.
- Added websocket security regression tests covering unauthenticated connect rejection, authorized/denied board join, and blocked rebroadcast of client-emitted mutation events.

Recommendations:
- ~~Require websocket authentication at connect.~~ **FIXED**: `handle_connect()` now resolves the current session user and returns `False` for unauthenticated socket connections.
- ~~Authorize board membership on join_board using server-side board access checks.~~ **FIXED**: `join_board` / `leave_board` now validate the supplied `board_id` and enforce `can_access_board(...)` before room membership changes are allowed.
- ~~Reject client-originated mutation events; only broadcast server-originated validated events.~~ **FIXED**: client-emitted mutation events now return an explicit rejection payload, and server-side route handlers remain the only broadcast source for board mutations.

---

### 3) High: Notification authorization IDOR (cross-user mutation)
Status: **Fixed (2026-03-15)**

What was observed:
- User A created a notification.
- User B successfully marked User A notification as read by id.
- Endpoints update/delete by notification id without user ownership filter.

Primary code references:
- server/app.py:8249 and server/app.py:8283 (mark read)
- server/app.py:8302 and server/app.py:8336 (mark unread)
- server/app.py:8389 (delete one)
- server/app.py:8438 (mark all read globally)
- server/app.py:8486 (delete all globally)
- server/tests/test_api_notifications.py (cross-user IDOR regression tests)

Impact:
- Horizontal privilege abuse (cross-user data/state manipulation).

Actions taken:
- Added user ownership filtering (`Notification.user_id == get_current_user_id()`) for:
   - `PUT /api/notifications/<id>/read`
   - `PUT /api/notifications/<id>/unread`
   - `DELETE /api/notifications/<id>`
- Scoped bulk operations to current user:
   - `PUT /api/notifications/mark-all-read`
   - `DELETE /api/notifications/delete-all`
- Added regression coverage for cross-user mutation attempts (mark read/unread, delete one, mark-all-read, delete-all) to ensure User B cannot mutate User A notifications.

Recommendations:
- ~~Scope all notification queries by current user id.~~ **FIXED**
- ~~Scope bulk operations by current user id.~~ **FIXED**
- ~~Add tests for cross-user notification access/mutation denial.~~ **FIXED**

---

### 4) High: Batch card archive/unarchive lacks user scoping
Status: **Fixed in code (2026-03-15)**; regression tests added, but local execution was blocked by the existing non-fresh test database.

What was observed:
- Batch endpoints disable required board context.
- They update by card id set directly, without user-scoped query.

Primary code references:
- server/app.py:6476-6477 (batch archive route/decorator)
- server/app.py:6551 (id-based update)
- server/app.py:6570-6571 (batch unarchive route/decorator)
- server/app.py:6645 (id-based query)

Impact:
- Users with card.archive may archive/unarchive cards outside authorized boards by submitting foreign ids.

Actions taken:
- Added a shared batch-authorization helper that loads requested card ids through `get_user_scoped_query(...)` for the current user and compares the full requested set against the fully authorized set before any mutation runs.
- Changed batch archive and batch unarchive to fail closed if any requested card id is missing or out of scope; no partial success is allowed.
- Returned explicit user-facing failure messages that state no cards were archived/unarchived when the request is rejected.
- Updated the board UI batch archive/unarchive handlers to show the server-provided rejection message directly.
- Added regression coverage for nonexistent ids, mixed valid/invalid ids, and mixed own/foreign ids for both archive and unarchive paths.

Recommendations:
- ~~Require board context or derive and validate board access for every provided card id.~~ **FIXED**: batch handlers now validate every submitted card id against the current user's scoped card set before mutating.
- ~~Use user-scoped query selection first, then update only scoped records.~~ **FIXED**
- ~~Fail closed if any requested id is out of scope.~~ **FIXED**

---

### 5) High: Theme ownership/scoping flaws and unintended global theme creation
Status: Confirmed by code path review.

What was observed:
- Several theme operations query by id without user scoping.
- Theme copy/import create new themes without user_id, likely making them global.

Primary code references:
- server/app.py:8793, 8869, 8927, 9107, 9318, 9369 (id-based unscoped theme queries)
- server/app.py:8994 and 9064 (theme creation without user_id)

Impact:
- Possible cross-user theme operations.
- User-created assets may unintentionally become globally visible/manageable.

Recommendations:
- Use user-scoped theme lookup consistently for all theme CRUD/export paths.
- Set user_id to current user for user-created themes.
- Keep system themes immutable and separated from user-owned themes.

---

### 6) Medium: Unauthenticated reconnaissance and bootstrap exposure
Status: Confirmed in live testing and code review.

What was observed:
- Public test endpoint returned database connectivity and board count.
- Setup status endpoint reveals initialization state.
- Setup admin endpoint is intentionally unauthenticated when setup incomplete.

Primary code references:
- server/app.py:1360 and 1395 (public test endpoint with board count)
- server/auth.py:993 (setup status)
- server/auth.py:1031 (setup admin)

Impact:
- Recon information disclosure.
- Increased first-deploy takeover risk if instance is exposed during bootstrap.

Recommendations:
- Restrict/disable public health details in production.
- Protect bootstrap route via one-time setup token and narrow exposure window.
- Auto-disable setup route after first successful bootstrap.

---

### 7) Medium: Production-accessible test-admin creation path with known credentials
Status: Confirmed by code review.

What was observed:
- Endpoint can create/delete known test admin account credentials.
- Protected by permissions, but still risky operationally in production.

Primary code references:
- server/app.py:799 (route)
- server/app.py:892 (hardcoded password)
- server/app.py:922 (password exposed in response message)

Impact:
- Elevated blast radius if role assignment controls fail or are abused.

Recommendations:
- Remove endpoint from production build.
- At minimum, hard-gate with explicit environment controls and deny in production.

## Exploit Attempts Performed (Easy to Hard)
1. Unauthenticated API recon:
   - GET /api/test
   - GET /api/auth/setup/status
2. Unauthenticated websocket access:
   - Connect and join_board without session.
3. Unauthenticated websocket injection:
   - Emit card_updated from unauthenticated client and verify reception by another client.
4. Session forgery bypass:
   - Register pending user, forge cookie with default secret, access authenticated endpoints.
5. Horizontal notification IDOR:
   - User B marks User A notification as read by id.

## Permissioning Architecture Recommendations
- Deny-by-default with strict resource ownership filters on every read/write path.
- Centralize authorization policy in one reusable abstraction and prohibit direct unscoped ORM queries in handlers.
- Enforce consistent policy parity across login, session load, websocket connect/join, and background-event channels.
- Require server-authenticated realtime channels and remove trust in client-emitted mutation events.
- Separate global/system resources from user-owned resources at schema and query policy levels.
- Use security regression tests for each previously exploited path.

## Fix Priority Plan
1. Immediate: secret handling + session loader approval enforcement + key rotation.
2. Immediate: websocket authentication and board authorization on join/events. **Completed (2026-03-15)**
3. Near-term: notification user scoping and batch card scope enforcement. **Implemented for both issues (2026-03-15)**
4. Near-term: theme ownership scoping and user_id ownership guarantees.
5. Near-term: bootstrap and test-only route hardening for production.

## What Was Tested
- Confirmed tested directly:
  - API behavior (HTTP endpoints)
  - Realtime websocket channel behavior (Socket.IO)
   - Post-fix Socket.IO validation for unauthenticated connect rejection, authorized/denied room joins, and blocked client-originated mutation rebroadcast
   - Basic browser UI smoke testing for restricted-user board visibility after permission-based control removal
- Not fully tested in this review:
  - End-to-end browser UI flows and visual behaviors in the web interface
  - Manual click-path UX regression testing
   - New Issue 4 API regression tests could not be executed in this workspace because the pytest authentication fixture requires a fresh database and the current local data already contains users

So this review did test backend API and realtime channel behavior, but it did not perform a full manual browser UI penetration run.
