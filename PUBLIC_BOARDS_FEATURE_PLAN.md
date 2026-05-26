# Public Boards Feature Plan

Temporary working document for the public-boards feature. Remove this file when the feature is complete.

## Goal

Allow selected boards to be viewed without authentication in a strictly read-only mode.

Public boards should:
- Be viewable at a public web path using a short, non-guessable public slug.
- Render only the board data needed for display.
- Never allow edits, mutations, or privilege escalation.
- Preserve the existing authenticated experience for private boards.

## Implementation Status (Updated 2026-05-26)

This section tracks what is complete on branch `415-make-selected-boards-publicly-accessible` and what is still outstanding.

### Completed tasks

- [x] Board data model includes `is_public` and `public_slug`.
- [x] Migration exists for public board visibility fields (defaults existing boards to private).
- [x] Public slug generation is implemented when a board is toggled public.
- [x] Board update API supports toggling public/private and revokes slug when private.
- [x] Public read-only endpoint exists: `GET /api/public/boards/<slug>`.
- [x] Public endpoint enforces public-only lookup and returns not found for private/revoked slugs.
- [x] Public payload redaction is in place (no owner identity, no assignee metadata, no comment author identity fields).
- [x] Public payload excludes scheduled cards/metadata in first phase.
- [x] Anonymous writes remain denied on private write endpoints.
- [x] API tests added for anonymous read, revoked access behavior, and denied writes.
- [x] Public board page created at `/public-board.html` with slug-based loading.
- [x] Public board frontend mode skips `PermissionManager.init()` and websocket setup.
- [x] Public board UI renders as read-only (no edit controls).
- [x] Public mode loads from public endpoint rather than authenticated board endpoints.
- [x] Public mode hides scheduled view/components.
- [x] Header has public page minimal mode and anonymous login call-to-action.
- [x] Authenticated users viewing public boards see a public badge with copy-link action.
- [x] Public page uses a Fresh Green default theme variable set.
- [x] Public endpoint adds crawler-dissuasion header (`X-Robots-Tag`) and explicit cache-control response header.
- [x] Public slug remains stable across private/public toggles.
- [x] Explicit public-link rotation endpoint exists (`POST /api/boards/<id>/public-link/rotate`).
- [x] Settings menu includes explicit visibility toggle confirmations and rotate-link confirmation.

### Outstanding tasks (full list)

- [ ] Add server-side rate limiting/throttling for public board endpoints.
- [ ] Add reverse proxy throttling rules for public routes (deployment config level).
- [ ] Add/verify tests that explicitly validate robots/crawler headers across deployed nginx path.
- [ ] Perform full regression run on clean DB and resolve any environment-specific integration failures.
- [ ] Final UX copy/design pass for public-indicator wording and any visual refinements.
- [ ] Decide whether to keep or remove this plan file once feature is considered complete.

## Recommended Design

Use an explicit board visibility flag on the board record rather than a special anonymous user.

Recommended state:
- `is_public = true|false`
- `public_slug` as a short public alias for the board URL.

Why this approach:
- Clearer security model than impersonating an anonymous user.
- Easier to audit and query.
- Cleanly separates authentication from visibility.
- Avoids mixing read-only anonymous access with RBAC semantics.

## UX Shape

### Public board view
- Public board URLs should use a short slug alias rather than an easily iterable identifier.
- Authenticated board navigation should continue to use `board=x` style navigation.
- When an authenticated user is viewing a public board, the header should show a clear text label indicating that the board is public.
- Clicking that public-indicator label should copy the board's public URL to the clipboard.
- Public boards should allow task view and archived/done views according to the board's working-style configuration.
- Public boards should never expose scheduled view or scheduled components.
- Public boards should preserve column order exactly as stored.
- Public boards should render with the fresh green theme as the default appearance.
- Public boards do not need websocket support in the first version.
- Public boards will not contain any filtering capability

### Authenticated area
- Private boards continue to use the current authenticated routes.
- Logged-in users should still be able to access public boards normally.
- If a board is private, unauthenticated users should be sent to `/login.html`.

## Backend Changes Needed

### Data model
- Add public visibility to `Board`.
- Generate and store a short public slug for each public board.
- Add migration and default all existing boards to private.

### API
Create a dedicated anonymous-read path rather than weakening existing private endpoints.

Likely endpoints:
- `GET /api/public/boards/<slug>`
- Optional later: `GET /api/public/boards/<slug>/cards` and `GET /api/public/boards/<slug>/columns` if we want the route split out for caching or maintainability

Policy requirements:
- Public endpoints must be read-only.
- Any write endpoint must remain auth-gated.
- Public responses should be redacted and minimal.
- Public board lookup should return `404` or a generic denial, not a distinct leak-prone error.

### Response shaping
Public payloads should exclude:
- Owner identity details.
- Assigned-to data.
- Comment author identity or commenter identity.
- User list and assignee filter metadata.
- Internal admin-only metadata.
- Anything that is not needed to render the board.

Safe to include:
- Board id or slug.
- Board name and description.
- Columns.
- Cards.
- Card title, description, timestamps, archived state, and done state.
- Column order.
- Checklist items with titles, checked state, and timestamps.
- Comments authored by authenticated users, with no commenter identity fields in the public payload.

Public endpoints should not allow unauthenticated users to create, edit, or delete comments.
Public payloads should not expose schedule-related identifiers or scheduled metadata.

### Authentication rules
- Keep current authenticated session checks for private endpoints.
- Public endpoints must not require `g.user`.
- Existing board/card decorators should stay unchanged for private APIs.
- Add a separate public access check that only allows boards marked public.

### WebSocket
Recommended first phase:
- Do not expose public websocket access.
- Use polling/HTTP only for public boards.

If realtime becomes necessary later:
- Use a separate public room model.
- Keep server-only event broadcast.
- Never allow client-originated mutation events.
- Do not reuse the authenticated board room join flow unchanged.

## Frontend Changes Needed

### Routing
- Add a public board view page.
- Keep `/board.html?id=...` for authenticated/private use unless we intentionally unify routes later.

### Header behavior
- On public pages, show a minimal header with login action.
- Hide authenticated-only menus, settings, and notification widgets.
- Avoid loading auth-only bootstrap logic on public routes.
- When viewing a public board while authenticated, show a clear public-board badge and a copy-link action in the header.

### Board page behavior
- Support a public mode that skips `PermissionManager.init()` and authenticated websocket setup.
- Public mode should render without edit controls.
- Board loading should call public endpoints instead of private authenticated endpoints.

### Navigation
- Public board page should keep normal browsing feel but not expose edit affordances.

## Security Requirements

This feature must remain read-only and deny-by-default.

Mandatory controls:
- No public write endpoints.
- No public batch operations.
- No public role, settings, notifications, backup, theme, or admin endpoints.
- No public websocket mutation channel.
- No sensitive metadata in public payloads.
- Strong server-side filtering even if the frontend hides controls.
- Add sensible public-route rate limiting and request throttling at the reverse proxy layer where feasible.
- Add crawler dissuasion headers and robots controls for public board routes.
- Rate limiting on public endpoints if feasible.
- Audit logging when visibility changes.
- For now, toggling public/private mode should update the board `updated_at` timestamp; detailed action classification is deferred until audit logging is implemented.

Important checks:
- Anonymous access to a private board must fail.
- Anonymous access to a public board must succeed only for read endpoints.
- Anonymous POST/PATCH/DELETE must fail everywhere.
- Turning a board private must immediately revoke anonymous access.

## Usability Considerations

- Public boards should be obviously read-only.
- The UI should clearly distinguish public board browsing from logged-in editing.
- If a visitor is not logged in, the header should make the login action obvious.
- Public board URLs should be easy to type and share.
- Public boards should not expose scheduled components or comment composition controls.

## Open Decisions

Need to decide:
- No additional metadata candidates are in scope for the first iteration.
- Theme handling remains fixed to fresh green for public boards.
- Public users will not receive filter metadata or filter persistence support.
- Public-indicator visual refinements and URL-copy UX wording will be reviewed after first implementation render.
- Any additional sharing metadata is deferred until there is a concrete need.

## Public Slug Stability and Rotation Proposal

### Current behavior (as implemented)
- Public slug is generated randomly when a board is made public.
- When a board is switched to private, `public_slug` is cleared.
- If later switched back to public, a new slug is generated.

Impact:
- Better accidental-link invalidation by default.
- Existing shared URLs break after private->public cycles, which is disruptive for widely distributed links.

### Proposed behavior
- Keep a board's public slug stable across `is_public` toggles.
- Switching to private should disable anonymous access via `is_public = false` but should not automatically rotate the slug.
- Add explicit "Rotate Public Link" action to deliberately invalidate old links and generate a new slug.

### Token generation options
- Option A (recommended): Continue using random slug generation, persist slug until explicit rotation.
- Option B (possible but not preferred): Deterministic salted hash/HMAC-derived slug.

Why Option A is preferred:
- Simpler operational model and easier incident handling.
- Avoids coupling link stability to server-secret lifecycle.
- Rotation remains explicit and auditable.

### API and UI shape for proposal
- Keep existing `PATCH /api/boards/<id>` toggle for `is_public`.
- Change toggle semantics so private mode no longer clears `public_slug`.
- Add explicit rotate endpoint or flag, for example:
	- `POST /api/boards/<id>/public-link/rotate`, or
	- `PATCH /api/boards/<id>` with `rotate_public_slug: true`.
- Add Settings menu action "Rotate Public Link" with confirmation dialog.

### Security and ops notes
- Private mode still immediately blocks anonymous access because lookup requires `is_public = true`.
- Rotating slug should immediately revoke old URL access.
- Rotation should be rate-limited and recorded in audit logs once audit actions are available.

### Tests to add/update
- Toggle public->private->public keeps same slug unless rotate is explicitly requested.
- Explicit rotate invalidates old slug and activates new slug.
- Public endpoint remains inaccessible while `is_public = false` even if slug is retained.

## Suggested Delivery Phases

### Phase 1: Data and API
- Add board visibility field and migration.
- Add public read-only endpoints.
- Add tests for anonymous read and denied writes.

### Phase 2: UI
- Add public board view mode.
- Update header/navigation for public pages.

### Phase 3: Hardening
- Redact payloads further if needed.
- Add audit logging and rate limiting.
- Add any required cache-control or SEO headers.

### Phase 4: Realtime decision
- Decide whether public boards need polling or websocket support.
- Implement only if justified.

## Working Rule

Treat this as a temporary design note while the feature is being built. Update it as decisions are made, and remove it once the implementation is complete.
