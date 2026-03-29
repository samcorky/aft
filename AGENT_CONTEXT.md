# Agent Context (Portable)

Purpose
- Keep high-signal repo facts that should be available to any Copilot agent on any machine.
- Prefer stable conventions and known pitfalls over temporary task chatter.

How to use
- Read this file at the start of security or testing work.
- Update only when behavior or workflow changes.
- Keep entries short and factual.

Current high-value context
- Notification rendering in www/js/notifications.js uses DOM node construction for list rendering to reduce DOM-XSS risk from template-string HTML assembly.
- Notification action URLs are validated server-side by validate_safe_url in server/app.py and include protocol restrictions plus unsafe-character checks.
- Focused notification URL security tests live in server/tests/test_api_notifications.py.
- Integration pytest calls in server/tests hit the running Docker stack. Rebuild containers after app.py/runtime changes before retesting.
- Board import API at /api/boards/import enforces JSON size caps, strict format/schema validation, and relationship integrity checks before writes.
- Imported card assignees are intentionally not mapped by user id across instances; imported cards are created by the importing user and left unassigned.

Security workflow
- Run Snyk Code after modifying first-party code in supported languages.
- If issues are introduced, fix and rescan until no new issues are reported for changed paths.

Useful commands
- Rebuild runtime: docker compose down; docker compose up -d --build
- Focused notification tests:
  - from server/: ..\\.venv\\Scripts\\python.exe -m pytest tests/test_api_notifications.py -k "attribute_breakout or relative_url or https_url or javascript_protocol" -q
- Focused Snyk scan:
  - path: c:\\git\\aft\\www\\js\\notifications.js

What does not belong here
- Secrets, credentials, tokens, or environment-specific private data.
- One-off debugging notes that will be stale next week.
