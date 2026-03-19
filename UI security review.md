# AFT UI Security Review

Date: 2026-03-17  
Reviewer: GitHub Copilot

## Scope and Method
This review focused on client-side security risks in the AFT web interface, including XSS/DOM injection vulnerabilities, session/credential management, client-side authorization implementations, and browser security hardening.

Work performed included:
- Static code review of frontend JavaScript (vanilla JS, no framework) focusing on DOM manipulation, user input handling, and dynamic HTML rendering.
- Session storage and cookie handling analysis.
- Automated SAST scanning (Snyk Code) on www/js directory with manual validation of reported issues.
- Tracing of data flows from HTTP responses through to DOM rendering.
- Configuration review of session cookies (Flask/app.py) and web server headers (nginx).
- Analysis of client-side permission caching and early-return optimizations.

## Executive Summary
Four distinct security findings were identified during UI review. The highest UI finding (notification URL XSS sink) has now been remediated by removing template-string HTML rendering in notifications and enforcing safer DOM construction plus URL hardening checks. The session cookie transport security finding has also been remediated by enforcing secure cookies by default and adding HTTP→HTTPS redirect protection for non-loopback traffic. The session cache stale-state behavior has now been formally assessed and accepted as an intentional trade-off for current expected use, with no near-term code adjustments planned. The missing browser hardening headers finding has now been remediated by implementing the recommended baseline header set in nginx for HTTPS responses. No fundamental architectural issues were identified.

## Findings (Ordered by Severity)

### 1) Medium: Notification action URL XSS via missing href attribute escaping
**Severity:** Medium  
**Status:** **Fixed (2026-03-17)**  
**CVSS Estimate:** 6.1 (CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N)

#### What was observed:
The notification system implemented URL protocol validation at the server level (`validate_safe_url()` in [server/app.py](server/app.py#L179-L218)) but previously rendered notifications with template-string HTML in a way that allowed href attribute breakout.

Before remediation, [www/js/notifications.js](www/js/notifications.js#L211) inserted untrusted notification values into `innerHTML`-built markup, including `href` values.

#### Pre-fix attack vector:
A URL value like `/x" onclick="alert(1)" data-x="` passed protocol validation (starts with `/`) but broke attribute boundaries when interpolated into HTML.

#### Actions taken:
- Replaced template-string/`innerHTML` notification list rendering with DOM node construction in [www/js/notifications.js](www/js/notifications.js#L211).
- Set notification action URLs through DOM property assignment (`actionLink.href = notification.action_url`) after existing `isSafeUrl()` checks in [www/js/notifications.js](www/js/notifications.js#L253).
- Removed `innerHTML`-based error rendering and switched to `textContent` in [www/js/notifications.js](www/js/notifications.js#L601).
- Added server-side defense-in-depth URL hardening in [server/app.py](server/app.py#L204) and [server/app.py](server/app.py#L210) to reject dangerous protocols and unsafe attribute-breakout characters.
- Added regression tests for attribute-breakout payloads in [server/tests/test_api_notifications.py](server/tests/test_api_notifications.py#L966) and [server/tests/test_api_notifications.py](server/tests/test_api_notifications.py#L982).

#### Primary code references:
- [www/js/notifications.js](www/js/notifications.js#L211): Notification rendering now uses DOM APIs instead of `innerHTML` template assembly
- [www/js/notifications.js](www/js/notifications.js#L253): Action links are created as DOM nodes and `href` is assigned via property
- [www/js/notifications.js](www/js/notifications.js#L601): Error rendering now uses `textContent`
- [server/app.py](server/app.py#L179): `validate_safe_url()` still enforces allowed protocols
- [server/app.py](server/app.py#L204): Dangerous protocol checks
- [server/app.py](server/app.py#L210): Unsafe attribute character checks
- [server/tests/test_api_notifications.py](server/tests/test_api_notifications.py#L779): Existing protocol rejection test
- [server/tests/test_api_notifications.py](server/tests/test_api_notifications.py#L966): Double-quote attribute-breakout regression test
- [server/tests/test_api_notifications.py](server/tests/test_api_notifications.py#L982): Single-quote attribute-breakout regression test

#### Impact:
Pre-fix impact:
- **Execution scope:** Client browser within authenticated session context
- **Trust boundary broken:** Attacker with link data modification capability (e.g., via compromised API response or man-in-the-middle on unencrypted HTTP) can inject arbitrary JavaScript into notification action links
- **Exposure:** Affects all users who click on notifications with attacker-crafted action_url values
- **Privilege escalation:** Execution context is the current authenticated user's session; could exfiltrate session tokens, modify board state, or perform actions as that user

#### Recommendations:
- ~~Replace template-string href insertion with safe attribute escaping or DOM API rendering.~~ **FIXED**: notification list rendering now uses DOM APIs and avoids template-string `innerHTML` assembly for link nodes.
- ~~Keep URL protocol validation in place as a precondition.~~ **FIXED**: existing `isSafeUrl()` and server `validate_safe_url()` checks are still enforced.
- ~~Add regression tests for attribute-breakout payloads.~~ **FIXED**: protocol and attribute-breakout tests are in `test_api_notifications.py`.

#### Validation performed:
- Focused pytest notification URL security tests passed (`6 passed`) including protocol and attribute-breakout cases.
- Focused Snyk scan on [www/js/notifications.js](www/js/notifications.js) reported `issueCount: 0`.
- Full Snyk scan on `www/js` reported `21` medium findings overall, with no current finding in `notifications.js`.

---

### 2) Medium: Session cookie transport security defaults (SESSION_COOKIE_SECURE not enforced)
**Severity:** Medium  
**Status:** **Fixed (2026-03-19)**  
**CVSS Estimate:** 5.3 (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N)

#### What was observed:
Before remediation, the Flask session cookie configuration in [server/app.py](server/app.py#L233-L235) set session security properties with an insecure default:

```python
# server/app.py pre-fix
SESSION_COOKIE_HTTPONLY = True  # Good: prevents JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax'  # Good: limits CSRF scope
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'  # Problem
```

The `SESSION_COOKIE_SECURE` flag defaulted to `'False'` when the environment variable was unset. Because of the `.lower() == 'true'` check, this evaluated to `False`, meaning session cookies could be sent over **unencrypted HTTP** in environments where the env var was not explicitly set to `true`.

#### Actions taken:
- Changed secure-cookie default to true in [server/app.py](server/app.py#L233) so session cookies are HTTPS-only unless explicitly opted out.
- Added startup warning when secure cookies are explicitly disabled in [server/app.py](server/app.py#L238) and [server/app.py](server/app.py#L240).
- Added HTTP→HTTPS redirect enforcement for non-loopback direct traffic in [server/nginx.conf](server/nginx.conf#L3), [server/nginx.conf](server/nginx.conf#L11), and [server/nginx.conf](server/nginx.conf#L18) with `X-Forwarded-Proto` loop protection.
- Updated environment template to explicitly document secure-cookie defaults in [.env.example](.env.example#L27) and [.env.example](.env.example#L30).

#### Primary code references:
- [server/app.py](server/app.py#L233): `SESSION_COOKIE_SECURE` now defaults to `True`
- [server/app.py](server/app.py#L238): Warning emitted when `SESSION_COOKIE_SECURE=false`
- [server/nginx.conf](server/nginx.conf#L3): Redirect-skip map for upstream HTTPS and loopback host handling
- [server/nginx.conf](server/nginx.conf#L11): HTTP listener remains active for reverse proxy and local workflows
- [server/nginx.conf](server/nginx.conf#L19): HTTP redirects to HTTPS for non-loopback direct traffic
- [.env.example](.env.example#L30): `SESSION_COOKIE_SECURE=true` explicitly documented

#### Risk context:
- Pre-fix risk was highest when HTTP was reachable and secure cookies were not enforced.
- Current implementation reduces accidental insecure deployment by defaulting cookies to secure and redirecting non-loopback HTTP traffic to HTTPS.
- Reverse-proxy TLS termination remains supported via `X-Forwarded-Proto=https` loop-protection logic.

#### Impact:
Pre-fix impact:
- **Transport breach:** Session cookie transmitted over HTTP (if redirect not enforced upstream)
- **Scope:** Deployments where HTTP was exposed and `SESSION_COOKIE_SECURE` was unset or false
- **Privilege escalation:** Attacker could impersonate any user whose session cookie was captured on the network
- **Session lifetime:** Captured cookie valid until expiry/invalidation
- **Mitigation already in place:** `HTTPONLY` and `SAMESITE=Lax` helped against script/CSRF vectors but not network interception

#### Why this is a real risk:
While HTTPS should be enforced upstream (at load balancer or firewall), relying on external enforcement introduces an operational risk: if a single engineer misconfigures the load balancer or if the application is exposed to a non-HTTPS network segment for debugging, session cookies become vulnerable. The application should enforce the secure flag by default and require explicit opt-out, not the reverse.

#### Recommendations:
- ~~Change the default to secure cookies (`SESSION_COOKIE_SECURE=True`).~~ **FIXED**: secure cookie default is now enforced in `app.py`.
- ~~Add startup validation warning when secure cookies are disabled.~~ **FIXED**: warning is emitted at startup for explicit insecure opt-out.
- ~~Enable HTTP→HTTPS redirect in nginx for direct HTTP traffic.~~ **FIXED**: non-loopback direct HTTP traffic is redirected to HTTPS with reverse-proxy loop protection.

#### Validation performed:
- Full backend test suite passed (`696 passed, 6 deselected`) after secure-cookie hardening and test-path adjustments.
- Manual redirect validation confirmed non-loopback hostnames return HTTP `301` to HTTPS and upstream `X-Forwarded-Proto=https` requests are not re-redirected.
- Current `.env.example` explicitly sets `SESSION_COOKIE_SECURE=true` for secure-by-default deployments.

#### Priority:
**HIGH** – Session hijacking is a critical attack; this is a low-lift fix with broad impact.

#### Deployment checklist:
Before rolling this change to production:
1. Verify HTTPS certificates are valid and installed on all instances.
2. Confirm load balancers are also enforcing HTTPS (upstream redirect).
3. After deployment, invalidate all existing sessions (restart nginx/Flask or clear session store) because existing cookies issued before the flag change will be rejected if they lack the Secure flag.

---

### 3) Low-Medium: Session cache stale-state window (permission changes not reflected until next API call fails)
**Severity:** Low-Medium  
**Status:** **Accepted trade-off (2026-03-19); no adjustments planned for current expected use**  
**CVSS Estimate:** 4.2 (CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N)

#### What was observed:
The client-side session manager in [www/js/header.js](www/js/header.js#L325-L346) implements an early-return optimization when the currentUser is cached in sessionStorage:

```javascript
// header.js lines 325-346
const cachedUser = sessionStorage.getItem('currentUser');
if (cachedUser) {
  try {
    const userData = JSON.parse(cachedUser);
    if (userData.id && userData.permissions) {
      window.currentUser = userData;
      // ...
      return; // Skip server revalidation if cache exists
    }
  } catch (e) {
    logger.error('Error parsing cached user:', e);
  }
}
```

This optimization works correctly for improving UI responsiveness on page reload. However, it introduces a stale-state window: if a user's permissions are modified on the server (e.g., admin revokes `board.view` permission), the client cache is not immediately invalidated. The user continues to see cached permissions until:
1. They refresh the page (cache is re-fetched from `/api/auth/me`), OR
2. An API request fails with 401/403, triggering the global error handler in [www/js/utils.js](www/js/utils.js#L20-L30) which clears the cache

#### Primary code references:
- [www/js/header.js](www/js/header.js#L325-L346): Early-return cache optimization
- [www/js/utils.js](www/js/utils.js#L20-L30): Fetch wrapper that clears cache on 401
- [www/js/board.js](www/js/board.js#L820-L850): Uses `window.currentUser.permissions` for rendering decisions

#### Impact:
- **Scope:** Users whose permissions are revoked remotely do not immediately lose UI access
- **Duration:** Stale state persists until page refresh or until user attempts a server action that triggers 401/403
- **Risk level:** Low to Medium depending on deployment frequency and how quickly admins need permission changes to take effect
- **Visibility:** The attack surface is primarily visible if:
  - An admin quickly revokes a user's permission and expects them to be locked out immediately
  - A user is compromised and permission revocation should be instantaneous
  - Compliance audits require immediate permission enforcement

#### Why this is a design trade-off (not a critical bug):
The cache-first strategy improves UX significantly on page reload and navigation, reducing the `/api/auth/me` call overhead. The trade-off accepts a brief stale window in exchange for faster page loads. This is a common pattern in SPAs (single-page applications) and is acceptable if:
- Admins communicate that permission changes take effect on next page refresh
- The application operates in low-risk environments (e.g., internal tools where users are not adversarial)

However, in scenarios where immediate permission revocation is a requirement (e.g., Insider threat response), the stale window is unacceptable.

#### Options for remediation:

**Option A: Always revalidate (safest, worst UX)**
```javascript
// header.js – remove early return, always fetch
const resp = await fetch('/api/auth/me');
if (resp.status === 401) {
  clearSessionCache();
  return;
}
const userData = await resp.json();
window.currentUser = userData;
sessionStorage.setItem('currentUser', JSON.stringify(userData));
```
**Impact:** Every page load/navigation triggers an HTTP request; network latency will be visible in UI.

**Option B: Cache with TTL (balanced)**
```javascript
// header.js – only trust cache if <5 min old
const cachedUser = sessionStorage.getItem('currentUser');
const cacheTimestamp = sessionStorage.getItem('currentUserTimestamp');
const cacheAge = Date.now() - parseInt(cacheTimestamp || 0);
const cacheTTL = 5 * 60 * 1000; // 5 minutes

if (cachedUser && cacheAge < cacheTTL) {
  // Use cache
  window.currentUser = JSON.parse(cachedUser);
  return;
}

// Cache expired or missing; revalidate
const resp = await fetch('/api/auth/me');
if (resp.status === 401) {
  clearSessionCache();
  return;
}
const userData = await resp.json();
window.currentUser = userData;
sessionStorage.setItem('currentUser', JSON.stringify(userData));
sessionStorage.setItem('currentUserTimestamp', Date.now().toString());
```
**Impact:** Provides a reasonable stale window (5 min) while ensuring eventual consistency; permissioning changes take effect on next page load after 5 min.

**Option C: WebSocket-based cache invalidation (most complex, best for real-time)**
```javascript
// Pseudo-code: server broadcasts permission change to client
// Listen on websocket for 'permission_updated' event
socket.on('permission_updated', (data) => {
  if (data.user_id === window.currentUser.id) {
    clearSessionCache(); // Force revalidation on next API call
  }
});
```
**Impact:** Requires backend support to broadcast permission changes; immediate effect but adds complexity.

#### Decision after assessment:
For current expected use (internal users, limited adversarial risk, and acceptable page-refresh consistency), the existing cache-first behavior is accepted as an intentional trade-off and will remain unchanged for now.

Potential future trigger for change:
- Revisit **Option B (TTL-based cache)** if operational or compliance requirements change and permission revocation must take effect within a defined time window.

#### Priority:
**LOW** – The current behavior is acceptable for most deployments. Escalate to HIGH only if your deployment requires immediate permission revocation.

---

### 4) Low: Missing browser hardening headers in nginx configuration
**Severity:** Low  
**Status:** **Fixed (2026-03-19)**  
**CVSS Estimate:** 3.7 (CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:N/A:N)

#### What was observed:
Before remediation, the nginx configuration in [server/nginx.conf](server/nginx.conf#L1-L174) served static assets and proxied requests to the Flask backend without several important browser hardening headers:

**Missing headers:**
- `Content-Security-Policy` (CSP): Restricts resource loading and inline script execution
- `X-Frame-Options`: Prevents clickjacking by blocking frame embedding
- `X-Content-Type-Options`: Prevents MIME-type sniffing attacks
- `Strict-Transport-Security` (HSTS): Enforces HTTPS on future connections
- `Referrer-Policy`: Controls what referrer information is shared with linked sites

#### Actions taken:
- Implemented the recommended Option A baseline browser hardening headers in the HTTPS nginx server block in [server/nginx.conf](server/nginx.conf#L102-L106).
- Added `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, and `Referrer-Policy` with the `always` flag for consistent HTTPS response coverage.
- Repeated the same hardening headers in HTTPS location blocks that already define `add_header` directives to avoid nginx `add_header` inheritance gaps in [server/nginx.conf](server/nginx.conf#L134-L138), [server/nginx.conf](server/nginx.conf#L161-L165), and [server/nginx.conf](server/nginx.conf#L173-L177).

#### Primary code references:
- [server/nginx.conf](server/nginx.conf#L102): CSP baseline policy (`default-src`, `script-src`, `style-src`)
- [server/nginx.conf](server/nginx.conf#L103): `X-Frame-Options: SAMEORIGIN`
- [server/nginx.conf](server/nginx.conf#L104): `X-Content-Type-Options: nosniff`
- [server/nginx.conf](server/nginx.conf#L105): `Strict-Transport-Security`
- [server/nginx.conf](server/nginx.conf#L106): `Referrer-Policy`
- [server/nginx.conf](server/nginx.conf#L134): Header coverage maintained in `/api/` location responses
- [server/nginx.conf](server/nginx.conf#L161): Header coverage maintained in static-asset location responses
- [server/nginx.conf](server/nginx.conf#L173): Header coverage maintained in HTML location responses

#### Impact:
Pre-fix impact:
- **Clickjacking risk (Low):** An attacker can frame the application in a hidden iframe and trick users into clicking UI elements
- **MIME-type sniffing (Low):** Browsers may interpret uploaded files (PDFs, images) as scripts if Content-Type is incorrect
- **HTTPS downgrade via HSTS bypass (Low-Medium):** Without HSTS, a user connecting to `https://example.com` for the first time can be downgraded to HTTP if intercepted
- **XSS residual risk (Low):** CSP would prevent many inline script attacks, but the current frontend already applies HTML escaping, so this is defense-in-depth

#### Recommendations:
- ~~Add basic browser hardening headers (CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy).~~ **FIXED**: implemented in nginx HTTPS server and location blocks with `always` semantics.
- ~~Preserve compatibility with current inline script usage while introducing CSP.~~ **FIXED**: deployed baseline CSP includes `'unsafe-inline'` for current compatibility.
- **Future hardening option:** consider strict nonce-based CSP (`script-src 'nonce-...'`) after inline script refactoring.

#### Validation performed:
- Static configuration validation completed by reviewing [server/nginx.conf](server/nginx.conf#L102-L177) to confirm header coverage in HTTPS server scope and `add_header`-overriding location scopes.
- Runtime verification remains in the testing checklist (DevTools Network response-header check) for deployment validation.

#### Priority:
**LOW (Completed)** – Defense-in-depth gap closed with baseline browser hardening headers.

#### Deployment notes:
- HSTS with `max-age=31536000` (1 year) is permanent; test thoroughly before deploying. Browsers will enforce HTTPS for 1 year after the first HSTS response.
- CSP with `'unsafe-inline'` is permissive and reduces the CSP benefit; consider refactoring inline scripts in a future iteration if strict CSP is a compliance requirement.

---

## Automated SAST Findings

**Tool:** Snyk Code (Static Application Security Testing)  
**Scope:** `www/js/` directory  
**Date:** 2026-03-17  
**Issues Reported:** 21 medium-severity DOM-XSS issues

**SAST Summary:**
Snyk Code identified 21 potential DOM-XSS issues in the current `www/js` scan. The previous `notifications.js` finding has been remediated and no longer appears in the scanner output after the DOM-rendering and URL-hardening changes. Remaining issues are primarily in other files and still require manual validation because SAST data-flow in vanilla JavaScript can over-report mitigated paths.

**Files with flagged issues (updated):**
- backup-restore.js: 3 issues → 0 confirmed (all mitigated by escapeHtml)
- theme-builder.js: 3 issues → 0 confirmed (all mitigated by escapeHtml)
- boards.js: 3 issues → 0 confirmed (all mitigated by escapeHtml)
- notifications.js: 0 issues (previous href attribute escaping gap fixed)
- role-management.js: 6 issues → 0 confirmed (all mitigated by escapeHtml)
- user-management.js: 6 issues → 0 confirmed (all mitigated by escapeHtml)

**Recommendation:** Continue using Snyk Code for coverage, but maintain manual validation of reported issues before allocating development resources. False-positive filtering was performed by tracing data-flow from API response through `escapeHtml()` calls to DOM insertion.

---

## Frontend Architecture Overview

**Technology Stack:**
- **Framework:** None; vanilla JavaScript (no React, Vue, Angular)
- **HTTP Client:** fetch API with global wrapper/error handler
- **Real-time:** Socket.IO (WebSocket) for board updates
- **Session Storage:** HTTP cookies (server-side session) + sessionStorage (client-side cache)
- **Permission Enforcement:** Client-side `hasPermission()` check using `window.currentUser.permissions`

**Security-relevant design patterns:**
- HTML escaping via shared `escapeHtml()` utility function (applied inconsistently; XSS findings often reflect missing applications)
- Permission caching in sessionStorage with early-return optimization
- Fetch wrapper in utils.js handles 401/403 responses by clearing session cache
- Socket.IO handlers validate permissions server-side (verified in API security review)

---

## Session Management Model

**Cookie Configuration:**
```python
SESSION_COOKIE_HTTPONLY = True       # ✓ Prevents JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax'      # ✓ Limited CSRF scope
SESSION_COOKIE_SECURE = True         # ✓ Default enforces HTTPS-only cookie transport
```

**Client-side Caching:**
```javascript
// sessionStorage.getItem('currentUser') used for offline availability
// Cleared on 401/403 by fetch wrapper
// Trusted on page load with early-return optimization (stale window risk noted)
```

**Server-side Validation:**
```python
# Flask-Session validates cookie signature and checks:
# - User is active (User.is_active == True)
# - User is approved (User.is_approved == True) [added in recent fix]
# - Session has not expired
```

---

## Recommendations Summary

### Immediate (Next Sprint)
1. ~~**FIX:** Notification href XSS – Apply attribute escaping to `action_url` (Finding #1)~~ **FIXED (2026-03-17)**
  - Implemented via DOM-based rendering and URL hardening checks
  - Follow-up: retain regression tests and include in release verification
2. ~~**FIX:** Set `SESSION_COOKIE_SECURE=True` default in app.py (Finding #2)~~ **FIXED (2026-03-19)**
  - Implemented with secure-by-default app config plus startup warning on explicit insecure override
  - Risk reduced: accidental HTTP cookie transport from unset env defaults

### Near-term (Next Release)
3. ~~**ADD:** Uncomment HTTP→HTTPS redirect in nginx.conf (Finding #2 mitigation)~~ **FIXED (2026-03-19)**
  - Implemented as conditional redirect with reverse-proxy loop protection
4. ~~**REVIEW:** Session cache TTL trade-off decision (Finding #3)~~ **ASSESSED (2026-03-19): ACCEPT AS-IS FOR NOW**
  - Outcome: No adjustments for current expected use; revisit TTL-based cache only if revocation-latency requirements tighten.

### Medium-term (Next Quarter)
5. ~~**ADD:** Browser hardening headers to nginx (Finding #4)~~ **FIXED (2026-03-19)**
  - Implemented baseline CSP, X-Frame-Options, X-Content-Type-Options, HSTS, and Referrer-Policy in HTTPS responses
  - Added location-level header duplication where cache `add_header` directives would otherwise override inheritance

### Operational
6. **ROTATE:** `SECRET_KEY` after deploying Session_Cookie_Secure changes (invalidates all sessions; expected behavior)
7. ~~**UPDATE:** `.env` template to explicitly set `SESSION_COOKIE_SECURE=true` and `HSTS=true`~~ **N/A FOR CURRENT IMPLEMENTATION**: `SESSION_COOKIE_SECURE` is fixed and HSTS is enforced directly in nginx.
8. **DOCUMENT:** Deployment checklist for HTTPS enforcement before security hardening rollout

---

## Testing Checklist

- [ ] Notification XSS test: Attempt to render notification with `action_url='/x" onclick="alert(1)' data-x="'`; verify no onclick fires
- [ ] Session cookie secure: Deploy to HTTP-only environment; verify `Set-Cookie` response includes `Secure; HttpOnly; SameSite=Lax` flags
- [ ] Browser headers: Open "Network" tab in DevTools; verify responses include CSP, X-Frame-Options, HSTS headers
- [ ] Session cache: Modify user permissions via admin panel; verify UI reflects accepted behavior (changes take effect on next page refresh or on 401/403-driven cache clear)
- [ ] SAST regression: Re-run Snyk Code on next release; compare issue count and validate new findings with manual inspection

---

## References

- [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP Secure Coding Practices – Session Management](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/stable-en/02-authentication_and_session_management/04-session-management)
- [MDN: Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy)
- [MDN: Set-Cookie – Secure, HttpOnly, SameSite flags](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
