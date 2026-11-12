# Final testing and QA report

Date: **2026-11-12**, Asia/Dhaka. Phase 7 branch: `feature/phase7-final-polish`, based on clean, updated main after verified Phase 6 merge PR #2 (`11191a6`). This report distinguishes automated evidence, read-only inspection, and pending human checks. It is not production/security certification.

## Executed checks and exact results

| Check | Result |
| --- | --- |
| `python -m pytest --postgres --postgres-concurrency -q` | **403 passed, 0 failed, 5 skipped**, 153.08 seconds |
| Final-QA focused suite on both databases | **13 passed, 0 failed** |
| pytest warnings | **0 reported** in final full run; no filters added to suppress warnings |
| `python -m compileall -q app tests scripts migrations` | Passed |
| `python -m pip check` | No broken requirements |
| `flask db current` | **0002_club_active (head)** |
| `flask db check` | **No new upgrade operations detected** |
| `python scripts/verify_database.py` | Read-only schema/constraint/index/EXPLAIN audit passed |
| `python scripts/verify_templates.py` | **33 templates compiled; 16 source POST forms include CSRF fields** |
| Schema and ER regeneration | Passed; same fields/relationships, improved legends and documentation links |
| `git diff --check` | Passed; Git's LF/CRLF notices are line-ending information, not pytest warnings |
| Coverage | **Not available**: coverage package is not installed; no percentage claimed or extra dependency installed |

The 403 passing tests comprise **191 PostgreSQL cases**, **180 SQLite cases**, and **32 database-independent checks**. All five skips are PostgreSQL-only venue exclusion cases when parametrized on SQLite; corresponding PostgreSQL cases pass. The six opt-in real concurrency tests ran successfully in the approved local development environment with established UUID fixtures and exact-ID cleanup. No automated unit/PostgreSQL test was omitted from the full command.

Browser tests, screenshots, JS runtime/syntax execution, screen-reader checks, and spreadsheet-client import tests were **not run**. No Node/browser/coverage tool was installed for this phase. CSS/JS/templates were inspected and HTTP rendering/form structure was tested; these do not establish visual or browser correctness. Use the [manual checklist](final-demo-guide.md#manual-browser-checklist-all-pending-human-verification) before presentation.

## Defects and polish completed

- Replaced generic 404/500 behavior and misleading shared 400 titles on conflict/failure with clear status-specific 400/403/404/409/500/503 pages. Unexpected 500 messages do not echo exception details.
- Fixed database-outage error recovery: Flask-Login's normal template context processor eagerly loads the user. Error pages now render through the autoescaping Jinja environment without that processor, avoiding a repeated failed database lookup while producing a safe 503. Failure tests verify this and rollback behavior.
- Mobile navigation uses a small local deferred script, aria-expanded/controls, Escape-key closing, current-page indication, and a no-JS visible-navigation fallback. No new frontend dependency.
- Improved table spacing/contrast, focus rings, wrapping, responsive scroll regions, reduced-motion behavior, form labels/error associations, and search clearing. Membership dates now use the same campus-time formatter as event pages; reports retain explicit BDT and date-filter semantics.
- Added convenience confirmation prompts for terminal event changes, club deactivation/reactivation, and student registration cancellation. The existing server-side expense deletion confirmation remains authoritative. JS prompts are progressive enhancement, not authorization or CSRF controls.
- Event detail buttons now reflect existing business rules: edits only for eligible future events, completion only after end, cancellation only where allowed. Server checks remain mandatory, including direct crafted requests.
- Removed obsolete homepage preview wording and linked final documentation. The homepage test still checks its actual content rather than dropping the assertion.
- Added one integrated three-role HTTP journey and focused error/security/accessibility regressions; existing tests and constraints were not weakened.

## Functional evidence

| Area | Automated evidence |
| --- | --- |
| Student identity/profile | Registration+User/Student atomicity, login/logout, profile whitelist, private directory denial |
| Clubs/membership | Search/filter/pagination, own joins/leaves/reactivation, unique lifetime row, assigned-club scope, preservation on deactivation |
| Venues/events | Positive capacities, venue limits, editable future events, terminal statuses, adjacent/cancelled booking semantics, overlap exclusion |
| Event registration | Own record only, duplicates/reactivation, deadline/full/closed checks, history, next-five dashboard list |
| Participants | Assigned-club lists, cross-object denial, attendance start/end handling, completed-only rates |
| Expenses | Decimal bounds/precision/nonfinite rejection, scoped CRUD, explicit confirmation, event relationships retained |
| Reports | Exact PostgreSQL totals, separate child preaggregation, zero rows, club/date/event scope, personal-only student summary |
| CSV/security | UTF-8/quotes/headers, formula neutralization, matching filters, CSRF, role injection, next redirects, XSS escaping, safe errors |
| End-to-end journey | Real test-client forms across three sessions through account/profile, memberships, venue/event setup, registration/cancel/reactivate, attendance/completion, expense create/edit/delete, reports/export, logout |

The journey uses a simulated test clock for attendance/completion, not fabricated timestamps or browser interaction. Student directory access remains system-admin-only. General user role/assignment management is unsupported and documented instead of silently added.

## PostgreSQL integrity and query-plan audit

The read-only audit found **nine core primary keys, ten required foreign keys with RESTRICT deletion, nineteen CHECK constraints, seven UNIQUE constraints plus the users.email unique index**, all mandatory columns, and index paths beginning with each foreign-key tuple. The event GiST exclusion and installed btree_gist were verified. Duplicate registration/membership pairs, negative expenses, invalid times/statuses, and reference violations are tested natively.

No schema, constraint, model, or migration changes were needed. The regenerated schema/ER documents agree with current metadata. Application capacity rules remain service-level: all app registration/cancel/reactivation/capacity writes use the documented Club→Venue(s)→Event→Registration lock order where relevant, refreshed ORM identities, and one commit/rollback boundary. Direct SQL writers can bypass service-only capacity/finite-money rules; trusted operators must follow the contract.

Representative `EXPLAIN (FORMAT TEXT)` statements were run for seat counting, upcoming events, and zero-preserving expense totals. Final plans included small-table Seq Scans, a Sort/Limit for upcoming events, and a Nested Loop Left Join/HashAggregate for expenses. Earlier planner choices differed as test cleanup/statistics changed. These are genuine inspected plans, **not timing/load benchmarks**. No EXPLAIN ANALYZE, index addition, manual ANALYZE, or planner-setting change was performed; the tiny/empty event tables provide no evidence for new indexes.

## Data preservation

Before and after testing, core counts were **one existing User and one existing Student; zero clubs, venues, assignments, memberships, events, registrations, and expenses**. New final-QA tests use outer transaction rollback/savepoints. The previously approved race tests briefly commit uniquely named fixture rows and remove only those captured IDs. No fixture records remained, and no existing development record was changed. Sequence counters may advance. No seed-dev, demo setup, persistent administrator creation, database reset, truncation, or schema/table drop ran.

## Remaining limitations and human sign-off

- Every browser item in the demo guide remains pending, including mobile layout, native confirmation dialogs, JS menu behavior, keyboard scrolling, contrast verification with real tools, screen readers, and spreadsheet import behavior. Claims are limited to inspected source and automated HTTP/DB results.
- Shared rate limiting, email/enrollment verification, password recovery, MFA, server-side session revocation, general role-provisioning UI, notifications, waitlists, full cancellation-cycle history, categories/revenue/budgets, and production hosting/security hardening remain outside scope.
- Flask signed cookies are not encrypted; stolen valid cookies cannot be centrally revoked without additional infrastructure. Production requires HTTPS, a suitable WSGI server, trusted-host configuration, and operational controls. The local debugger must not be public.
- Reports materialize grouped result sets before pagination/export; use DB pagination/streaming for large installations. PostgreSQL, not SQLite, is the exact financial/concurrency target.
- Optional synthetic organizer provisioning is documented for a trusted operator after approval. It was not executed. There are no committed default/demo passwords.
- Feature branch must be reviewed before merge; no automatic merge or additional development phase is authorized by this completion report.
