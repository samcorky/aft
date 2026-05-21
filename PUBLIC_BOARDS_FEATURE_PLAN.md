# Public Boards Feature Plan

Temporary working document for the public-boards feature. Remove this file when the feature is complete.

## Goal

Allow selected boards to be viewed without authentication in a strictly read-only mode.

Public boards should:
- Be viewable at a public web path using a short, non-guessable public slug.
- Render only the board data needed for display.
- Never allow edits, mutations, or privilege escalation.
- Preserve the existing authenticated experience for private boards.

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
