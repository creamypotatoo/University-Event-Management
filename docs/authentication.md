# Authentication and authorization design

Phase 3 extends the working Phase 2 schema without migrations or constraint changes. User inherits Flask-Login UserMixin and returns user_id as a string; the loader validates integer range and loads the current database record. Password methods use Werkzeug scrypt generation/checking. No password, role, or permission list is stored in the signed browser session. Role and assignment changes are checked from database state on subsequent requests.

## Public registration and login

Registration accepts only the five named identity/profile fields and password/confirmation. Server code fixes the role to student and constructs the User/Student relationship before one commit. Database unique constraints arbitrate concurrent email or student-number collisions; the error path rolls back the whole transaction and returns a generic registration message. Required values and lengths match the actual model columns. No pending user can remain after a conflicting student identifier. Institution-specific student-number patterns and enrollment verification are unspecified: this release verifies format and uniqueness, not university enrollment or email ownership.

The login page normalizes email and uses the same failure message/status for an unknown user or wrong password. Unknown/malformed identities still execute a dummy scrypt comparison, reducing obvious timing differences; this is not a guarantee of constant response time. Failed login never sets an authenticated session. Invalid database hashes fail closed. Input size and password length are bounded. Password fields are not copied into template values; Jinja escapes other supplied text.

Login clears the anonymous session, establishes a fresh Flask-Login session, and enables an eight-hour expiry. No remember-me option is accepted; login and logout explicitly expire any legacy remember-me cookie. Logout is POST-only, CSRF protected, calls logout_user, and clears the session. The conservative next validator accepts only root-relative URLs without schemes, authorities, percent escapes, backslashes, whitespace, or control characters. Permitted targets still run normal authorization.

## CSRF and sessions

Every POST/PUT/PATCH/DELETE is checked in a global before-request hook, including login and registration. Each browser session gets a 32-byte cryptographic random token in a hidden field. The server verifies equality using compare_digest and checks the stored issue time against a one-hour lifetime. Missing, forged, non-ASCII, cross-session, expired, and pre-login tokens are rejected. After token expiry, reload the form. The signed HttpOnly session cookie protects token integrity; SameSite=Lax is additional protection rather than a replacement for token checks. AJAX state changes are not implemented; future JS must submit the same form token or extend the protection deliberately.

Flask's session cookie is signed, not encrypted. Application code stores only Flask-Login session metadata, the CSRF nonce/timestamp, session permanence, and transient flash messages. Passwords and database connection settings never enter it. A stolen previously valid cookie cannot be centrally revoked by clearing one browser's cookie; full server-side revocation, password-change session invalidation, and multi-device logout require additional infrastructure/schema work and are not implemented. Strong session protection checks the request/browser identifier. Secure cookies are enabled in APP_ENV=production; local HTTP uses development settings.

## Authorization extension points

`roles_required(*roles)` requires authentication then an exact role match; it returns 403 for an authenticated wrong role. Anonymous requests use Flask-Login's login redirect. `can_manage_club(user, club_id)` permits system_admin globally and club_admin only with a matching ClubAdmin record. `club_admin_required` wraps routes with a named club_id parameter. Student membership alone never confers administration. The club-scoped read-only dashboard uses this decorator and verifies the club exists after permission checks.

Phase 4 management routes reuse these checks, derive the owning club from the object being changed, and ignore arbitrary submitted club/owner IDs. See the [management route reference](phase4-management.md). Administrator role/assignment editing pages remain absent. The initial administrator CLI requires interactive hidden password entry, validation, and an atomic commit; it does not run on startup. Seed users retain unusable randomly generated passwords until a separately designed provisioning flow exists.

## Verification and operational limits

Authentication HTTP tests run on both SQLite and PostgreSQL through the same views, with real CSRF enabled and actual Werkzeug hashing. The request session is bound to a savepoint-aware SQLAlchemy session inside an outer test transaction. Application commits/rollbacks affect savepoints; final fixture cleanup rolls back every test record. No existing tables or schemas are recreated on PostgreSQL. Sequence counters may advance. CLI tests create only rolled-back administrators, never a persistent default account.

Tests cover registration success/validation/atomic conflicts, hashing, role injection, login errors and sessions, logout method/CSRF, role matrix, club ownership and revocation, missing users/profiles, redirect attacks, expired/forged/cross-session tokens, escaped profile output, CLI bootstrap safeguards, headers, and database error handling. Phase 2 model/constraint tests remain part of the suite.

This local course application has no email verification, password reset/change, MFA, shared login throttling, or server-side session revocation. Before internet deployment, add persistent abuse controls and an account recovery policy, use a production WSGI server and HTTPS, and configure trusted hosts. The development server/debugger is for local use. Bootstrap remains CDN-hosted. No browser screenshot or manual visual verification is implied by HTTP tests.

Patterns follow the official [Flask security guidance](https://flask.palletsprojects.com/en/stable/web-security/) and [Flask-Login documentation](https://flask-login.readthedocs.io/en/latest/).

## Final QA recovery note

Phase 7 adds status-specific error pages and a database-safe renderer that bypasses Flask-Login's eager template context processor during failures. A user-loader/database outage returns a generic 503 rather than attempting the same failed lookup while rendering an error. Regression tests cover that path, 500 detail suppression, rollback, and production cookie flags. No authentication schema or privilege rules changed. See [final testing report](final-testing-report.md) for automated evidence and explicit remaining browser/security limitations.
