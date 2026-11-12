# University Event and Club Management System

Database foundation for a university DBMS course project. Uses Python Flask, PostgreSQL, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Werkzeug, server-rendered HTML, CSS, and Bootstrap 5.

## Final presentation handoff

Phases 1–7 are implemented. Final full suite: **403 passed, 0 failed, 5 skipped**. No Phase 7 migration or new dependency was needed; head remains `0002_club_active`. Browser/manual sign-off remains pending and is not implied by HTTP tests.

- [Final demo guide and manual checklist](docs/final-demo-guide.md): Windows launch, three-role setup, timed presentation steps, and explicitly pending browser checks.
- [Viva preparation](docs/viva-preparation.md): ER/normalization explanation, 40 questions and concise answers, 14 actual-schema SQL examples, locking and financial query reasoning.
- [Final testing report](docs/final-testing-report.md): exact results/warnings/coverage availability, security audit, data preservation, query plans, known limitations.
- [Schema reference](docs/schema.md) and [ER diagram](docs/er-diagram.md): generated from actual models, with unique-pair/cardinality explanations.

Phase 7 improves navigation/focus/tables/forms, safe status-specific error recovery, date display, and confirmation prompts while preserving Phase 1–6 functionality. It does not add general account/role management. Student records remain private to their owner/system administrator; the student directory is not public.

Final verification commands (from the configured local development environment):

```powershell
.\.venv\Scripts\python.exe -m pytest --postgres --postgres-concurrency -q
.\.venv\Scripts\python.exe scripts/verify_database.py
.\.venv\Scripts\python.exe scripts/verify_templates.py
.\.venv\Scripts\python.exe -m compileall -q app tests scripts migrations
.\.venv\Scripts\python.exe -m pip check
```

The full suite reuses previously approved concurrency fixtures with exact-ID cleanup. The database audit is read-only and prints schema/counts/plans, not user records or credentials. Template checks do not execute JavaScript or replace the pending browser checklist. Coverage tooling is unavailable and no coverage percentage is claimed.

## Scope

Implemented: application factory, configuration, health check, nine normalized models, migrations, optional seed, authentication/CSRF, role and club authorization, role dashboards, initial administrator CLI, student profiles, club directory/editing/deactivation, memberships and club rosters, venue management, and tests.

Phases 5–6 add event management, transactional registration, attendance/history, expense CRUD, exact financial summaries, participation analytics, role-based summary cards, and safe CSV export. Club administrator provisioning screens remain outside scope. No database tables are created at startup; migrations require approval.

## Windows setup (PowerShell)

Prerequisites: Python 3.12 or newer and a running local PostgreSQL server. Install PostgreSQL separately if needed. Using pgAdmin, create a dedicated local login role and an empty database named `university_events`, owned by that role. Choose your own credentials; this project supplies none. Do not use a production database.

Run from the VS Code PowerShell terminal:

```powershell
Set-Location D:\dbms_project
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
notepad .env
```

If `.venv` already exists, skip its creation. If `.env` already exists, edit it rather than copying over it. Paste the generated random value after `SECRET_KEY=`. Replace `YOUR_USER` and `YOUR_PASSWORD` in `DATABASE_URL` with your local PostgreSQL credentials; URL-encode reserved characters in the credentials (for example, `@` becomes `%40`). Keep the `postgresql+psycopg://` prefix. Set the host, port, and database name to match your installation.

`.env` is ignored by Git. Never commit it or share its contents. Existing process environment variables take precedence over `.env`. The factory loads `.env` relative to the project root. Allowed `APP_ENV` values are `development`, `production`, and `testing`. Production enables secure cookies and requires HTTPS. Debug mode is enabled only by the explicit development command below.

Virtual environment activation and PowerShell execution-policy changes are unnecessary; these commands call its Python directly.

Verify database connectivity explicitly:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app check-db
```

Success prints `Database connection verified (SELECT 1).` This read-only command creates no schema and modifies no data. Failure returns a nonzero exit code without printing driver details. Check PostgreSQL service status, the role/database, port, and credentials. Application startup and `/health` alone do not verify PostgreSQL connectivity.

Start the local development server:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app run --debug
```

Open <http://127.0.0.1:5000/>. Stop the server with Ctrl+C. The Flask development server is for local development only.

In another terminal, check liveness:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

JSON response: `{"database":"not_checked","status":"ok"}`. HTTP 200 means the app is responding, independently of database availability.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pip check
```

Default tests provide their own ephemeral secret and in-memory SQLite configuration, so no `.env`, PostgreSQL server, or real credentials are needed. They verify HTTP responses, static assets, configuration, extensions, portable model constraints, relationships, seed idempotency, and offline PostgreSQL migration compilation. PostgreSQL tests are skipped unless explicitly enabled as described below. SQLite does not enforce the PostgreSQL venue exclusion constraint.

## Structure

```text
app/
  __init__.py                 Application factory and check-db command
  config.py                   Environment configuration
  extensions.py               SQLAlchemy, Migrate, and LoginManager
  models.py                   Nine normalized domain models
  seed.py                     Optional additive development seed
  security.py                 Global CSRF protection and security headers
  auth/                       Login, registration, validation, permissions, admin CLI
  dashboards.py               Read-only role and club dashboards
  management/                 Phase 4 routes, validation, and membership rules
  events/                     Event routes, validation, and transactional registration services
  reports/                    Expense CRUD, scoped aggregate queries, money validation, CSV safety
  errors.py                   Status-specific failure recovery without user/database template lookup
  static/js/app.js            Lightweight progressive navigation and confirmation prompts
  main/__init__.py            Public routes and health endpoint
  templates/base.html         Shared Bootstrap layout
  templates/main/index.html   Homepage
  static/css/style.css        Responsive campus styling
tests/
  conftest.py                 Isolated application and client fixtures
  test_foundation.py          Foundation tests
  test_models.py              Portable and PostgreSQL model tests
  test_migration.py           Offline migration and seed opt-in tests
  test_auth.py                Authentication/authorization tests on both databases
  test_management.py          Phase 4 business rules and HTTP tests on both databases
  test_events.py              Phase 5 HTTP and business-rule tests
  test_event_concurrency.py   Opt-in PostgreSQL multi-connection races with exact-ID cleanup
  test_reports.py             Phase 6 expense, aggregate, permissions, dashboard, and CSV tests
  test_final_qa.py            Three-role HTTP journey and final error/security/accessibility regressions
migrations/                   Alembic environment and reviewed initial revision
scripts/                      Read-only initial generation and schema doc tools
docs/                         ER diagram, schema reference, design decisions
.env.example                 Configuration template without credentials
pytest.ini                   Test discovery configuration
requirements.txt             Compatible dependency ranges
```

Flask-Migrate includes initial revision `0001_initial` and the necessary Phase 4 revision `0002_club_active`. Authentication itself required no schema changes.

## Phase 4: management features

See the [route and permission reference](docs/phase4-management.md) for the full route list, lifecycle rules, and migration review.

- **My profile:** students view their private profile and edit name, department, and batch. Email, student number, and role remain read-only.
- **Clubs:** search by name/description and filter active/inactive clubs. Open club details to join, leave, or rejoin. **My memberships** includes search, status filtering, and pagination.
- **Club administrator dashboard:** open assigned clubs to edit details and manage member statuses. Other clubs and rosters cannot be managed.
- **System administrator dashboard:** create/edit clubs, deactivate/reactivate clubs, manage venues, and browse/search student records. Deactivation preserves all relationships, blocks joining/reactivation, and permits cancellation.
- **Venues:** public name/location search. Only system administrators create/edit venues. Positive integer capacity is required; reductions below an existing non-cancelled event's capacity are rejected.

Forms use global CSRF protection and role/scoped authorization. Lists show ten records per page. Search is literal and case-insensitive; student department filtering is exact. No deletion, event registration, expense management, or account role editing flow is added.

**Migration approved and applied locally:** `0002_club_active` adds only `clubs.is_active BOOLEAN NOT NULL DEFAULT true`, making existing clubs active and preserving all prior constraints. For another local database, review and obtain approval before applying it:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
.\.venv\Scripts\python.exe -m flask --app app:create_app db current
.\.venv\Scripts\python.exe -m flask --app app:create_app db check
.\.venv\Scripts\python.exe -m pytest --postgres -q
```

Expected head after application: `0002_club_active`. Until that upgrade is applied, PostgreSQL club queries lack the new column. Preview just the new migration without applying it:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade 0001_initial:0002_club_active --sql
```

## Phase 5: event management and registration

See the [event routes, business rules, locking strategy, and test safety](docs/phase5-events.md). **No migration is needed**; current head remains `0002_club_active`.

- Use **Events** to search/filter by title/description, status, upcoming/past dates, club, or venue. Event details show organizing club, venue, campus-local dates/times, capacity, available seats, and your own registration status.
- Students register/reactivate or cancel from event details, view **My events** for personal status/history, and see their next five registered events on the student dashboard. Registration and normal cancellation close at start time; club membership is not required.
- Assigned club administrators create events from a club dashboard or **Manage events**, edit upcoming scheduled events, cancel events, complete them after their end, and manage their participants. System administrators have the same capabilities for all clubs. Students cannot manage events or view others' participant lists.
- Enter form times in **Asia/Dhaka**. New events require active clubs, valid non-overlapping venue slots, and capacity no greater than venue capacity. Cancelled/completed events cannot reopen. Event and registration history is preserved.
- Registrations use the existing unique student/event row. Repeated joins are idempotent; reactivation updates the cancelled row. `registered` and `attended` occupy seats. PostgreSQL Event row locks serialize registration, cancellation, and capacity reductions; venue row locks coordinate booking/capacity edits. The existing exclusion constraint is preserved.
- Managers record/undo attendance after event start. This does not enroll additional students or reactivate cancelled records. Every write form uses CSRF protection and owning-club authorization.

Standard PostgreSQL tests roll back their writes:

```powershell
.\.venv\Scripts\python.exe -m pytest --postgres -q
```

Multi-connection concurrency tests require explicit approval because their unique fixtures briefly commit and cleanup removes only those fixture IDs. With approval, run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest --postgres --postgres-concurrency -q
```

Never run these against production or alongside other writers. No seed-dev run, reset, drop, or migration is part of Phase 5. Full details, limitations, and all routes are documented in `docs/phase5-events.md`.

## Phase 6: expenses, financial reports, and analytics

See [Phase 6 routes, permissions, metric formulas, query design, and CSV safety](docs/phase6-reports.md). No migration is required; head remains `0002_club_active`.

- From an event's detail page, authorized managers open **Event expenses** to search/filter costs and add/edit records. Delete links open a confirmation page; only a confirmed CSRF-protected POST removes the selected expense. Students cannot access private financial information.
- **Financial reports** shows exact BDT expense totals by event and club, monthly expense trends, and highest-spending events. Events/clubs with no expenses show zero. The existing schema has no categories/revenue/budgets, so these are not invented.
- **Analytics** shows event counts/statuses, registration/attendance counts, occupancy, club participation, popular events, and monthly event starts. Completed-event attendance rates use attended / (registered + attended); upcoming-event rates show N/A.
- Manager dashboards show authorized summary cards and links to complete reports; club administrators see assigned clubs only. Student dashboards show only their own upcoming registrations, attended count, past non-cancelled participation, and history link.
- Both report pages support date range, club, and event filters. Financial dates refer to expense_date; analytics dates refer to event start in Asia/Dhaka. CSV downloads apply the same permissions/filters and include all filtered rows rather than only the current HTML page. Text cells are neutralized against spreadsheet formula injection and properly quoted as UTF-8.
- Expense input uses Decimal/NUMERIC: nonnegative amounts up to 9999999999.99 with at most two fractional digits. Invalid/nonfinite numbers and excess precision are rejected. All existing constraints and relationships remain intact.

Run the focused PostgreSQL checks and complete regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reports.py --postgres -q
.\.venv\Scripts\python.exe -m pytest --postgres --postgres-concurrency -q
```

New report/expense tests roll back all writes, including fixture deletions. The full suite reuses the six previously approved temporary committed concurrency fixtures with exact-ID cleanup. No development records are changed by setup, and seed-dev is not run.

## Phase 3: accounts and access

Start the local server using the Windows command above after configuring `.env` and applying the approved initial migration. No additional dependencies are needed for Phase 3.

- Register a student at <http://127.0.0.1:5000/auth/register>. Full name, email, student number, department, batch, password, and confirmation are required. A successful registration commits User and Student together and redirects to login.
- Log in at <http://127.0.0.1:5000/auth/login>. All roles use the same page. `/dashboard` sends you to your role's landing page.
- Student dashboard: `/dashboard/student`. Club administrator dashboard: `/dashboard/club-admin`. System administrator dashboard: `/dashboard/system-admin`.
- `/clubs/<club_id>/dashboard` permits only the explicitly assigned club administrator or a system administrator. This is a read-only overview, not a CRUD interface.
- Use the navigation's **Log out** button. Logout requires POST and a valid CSRF token; GET never logs a user out.

Create the **initial** system administrator yourself with this interactive command:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app create-admin
```

Enter your chosen full name and email, followed by a password twice. Password entry is hidden. There is no password command-line argument, generated default password, or default admin account. The command refuses to promote an existing user or create an account when a system administrator already exists. PostgreSQL bootstrap attempts are serialized with a transaction advisory lock. The command is implemented and tested with rolled-back fixtures; it has not been run to create a persistent local administrator. Run interactively rather than piping secrets from shell commands or storing them in scripts.

Public registration always creates role `student`, regardless of submitted role, ID, or password-hash fields. It cannot create ClubAdmin assignments. Existing club administrator accounts require both role `club_admin` and explicit ClubAdmin records to access a club. Role/assignment provisioning UI belongs to Phase 4 and is intentionally absent. System administrator accounts have university-wide authorization; existing read-only views are the extent of Phase 3 functionality.

Input policies: email is trimmed/lowercase and unique; password is a printable passphrase of 12–128 characters, hashed with Werkzeug scrypt; student number is a unique, case-sensitive identifier of 3–40 ASCII letters/numbers/hyphens/underscores/slashes beginning with a letter/number. Full name, department, and batch must be nonblank and fit existing model limits. Registration reports a generic conflict for email/student-number collisions. Login uses the same invalid-credentials message and HTTP 401 for unknown emails and incorrect passwords. Passwords are never repopulated in forms, stored in sessions, or logged by application code.

Anonymous dashboard requests redirect to login (302); authenticated users with the wrong role or club assignment receive 403. Invalid/expired CSRF forms receive 400. Login `next` permits only unambiguous root-relative URLs; external, scheme-relative, encoded, backslash, and control-character targets are rejected. Authorization is still checked after any permitted redirect.

All unsafe HTTP methods are protected by a session-bound, 256-bit random CSRF token with a one-hour lifetime and constant-time comparison. No state-changing route is CSRF-exempt. Login and logout clear the prior session and invalidate its CSRF token. Login uses an eight-hour signed session with HttpOnly and SameSite=Lax cookies, no remember-me cookie, and Flask-Login strong session protection. Production configuration sets Secure cookies and requires HTTPS. Authenticated responses and forms use `Cache-Control: no-store`; security headers restrict framing and form targets. Read the [authentication design notes](docs/authentication.md) for limits and extension points.

## Phase 2 schema and migrations

Read the [schema reference](docs/schema.md), [Mermaid ER diagram](docs/er-diagram.md), and [design and migration review](docs/database-design.md). Models cover User, Student, Club, ClubMembership, ClubAdmin, Venue, Event, Registration, and EventExpense.

Duplicate memberships and registrations are prevented across all statuses. Cancel/reactivate the existing row rather than insert another row for the same pair. Timestamps preserve the original join/registration instant. Full cancellation-cycle auditing is outside this schema.

The initial revision was generated by read-only PostgreSQL inspection. `btree_gist` is required for race-safe venue overlap exclusion. The upgrade installs this trusted extension if absent, so the configured database role needs CREATE privilege on the database. No superuser or OS elevation is inherently required. If permissions are insufficient, ask the database owner to provision the extension; do not bypass permission checks.

Preview SQL without applying anything:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade --sql
```

**Only after explicit approval to apply migrations to the local database**, run:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
.\.venv\Scripts\python.exe -m flask --app app:create_app db current
.\.venv\Scripts\python.exe -m flask --app app:create_app db check
```

Expected latest revision after the approved Phase 4 upgrade: `0002_club_active (head)`. The initial upgrade adds nine domain tables plus `alembic_version`; it does not seed data. Do not run `db init` again, reset the database, or execute downgrade commands. The one-time `scripts/generate_initial_migration.py` intentionally refuses existing tables/revisions and is not a routine migration command.

After the migration is approved and applied, enable PostgreSQL integration tests explicitly:

```powershell
.\.venv\Scripts\python.exe -m pytest --postgres -q
```

These tests use the configured local development database. All test data is rolled back in outer transactions; PostgreSQL sequence counters may still advance. They create no schemas and never drop/reset tables. This command also runs the SQLite and foundation tests; use `-m postgresql --postgres` for PostgreSQL cases only. Keep `APP_ENV=development` and avoid concurrent manual changes or seeding. Database exceptions are not printed by the connection setup. Run against a local development database only.

## Optional development seed (separate approval required)

After reviewing the seed and obtaining approval to insert demonstration records:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app seed-dev --confirm
```

This command runs only in development, uses one transaction, and inserts missing demo users/students, three clubs, three venues, three events, memberships, registrations, one club administrator, and expenses. It preserves existing matching records, including cancellations, on repeated runs. It uses reserved `demo.*@example.edu` addresses and `DEMO-2026-*` identifiers. Event dates are generated 30 days ahead on first insertion. Password hashes use random, discarded secrets; no usable demo login passwords are supplied. No system administrator is seeded. There is no seed at startup or during upgrade. The real database seed command has not been run.

Regenerate schema documentation after model changes:

```powershell
.\.venv\Scripts\python.exe scripts/generate_schema_docs.py
```

## Assumptions and unresolved items

- Phase 6 stops before Phase 7 polishing and additional account/role provisioning features.
- PostgreSQL settings are supplied locally. Phase 4 requires approval to add club lifecycle state with revision `0002_club_active`.
- Bootstrap 5.3.3 CSS is loaded from jsDelivr, requiring internet for Bootstrap styling. Custom CSS remains local. No JavaScript interactions are needed yet.
- Dependencies use bounded compatible ranges rather than a fully locked environment. Record exact installed versions for final delivery.
- The application factory follows the [Flask factory pattern](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) and initializes configuration before [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/config/).

This is the final development phase. Review the feature branch and complete manual browser sign-off before presentation/merge; no additional phase is started automatically.

## Phase 1 verification record (2026-11-11)

- Python 3.12.9; dependencies installed in the project-local `.venv` with user approval.
- `python -m pytest -q`: **10 passed**.
- `python -m compileall -q app tests`: passed.
- `python -m pip check`: no broken requirements found.
- Homepage, static CSS, and health endpoint verified through the Flask test client; no browser visual verification performed.
- PostgreSQL connectivity not verified: no `.env` or local database credentials were supplied. No schema or database data was modified.

## Phase 2 verification record (2026-11-11, before migration approval)

- PostgreSQL connected successfully during an explicitly read-only schema inspection: zero public tables; `btree_gist` available but not installed. No credentials printed.
- Default pytest run: **33 passed, 31 skipped**. This includes 21 SQLite model/seed cases and 12 foundation/offline-migration/CLI checks. Of the skipped cases, 26 require PostgreSQL opt-in and five are PostgreSQL-only overlap cases omitted on SQLite.
- Offline PostgreSQL upgrade SQL compiled successfully: extension, nine domain tables, Alembic version table, and venue exclusion included; no DROP TABLE in upgrade.
- Compilation passed for app, tests, migrations, and scripts. Dependency check: no broken requirements.
- PostgreSQL integration tests have not run because applying the reviewed migration requires user approval. The real database seed command has not been run.

## Phase 2 final verification (2026-11-11, after approval)

- User explicitly approved applying `0001_initial` and running rollback-isolated PostgreSQL tests.
- Upgrade applied successfully to local `university_events`, including `btree_gist`. Current revision: **0001_initial (head)**.
- `flask db check`: **No new upgrade operations detected**. Constraint-specific tests independently verified native PostgreSQL checks and exclusions; Alembic autogeneration does not detect every possible constraint change.
- `pytest --postgres -q`: **59 passed, 5 skipped**, comprising **26 PostgreSQL integration cases**, **21 SQLite model/seed cases**, and **12 foundation/offline-migration/CLI checks**. All skips are SQLite executions of PostgreSQL-only venue overlap tests.
- The PostgreSQL tests verified duplicate-pair handling, reactivation, foreign keys, unique constraints, capacity/time/amount/status checks, joins/aggregation, seed idempotency within rolled-back test transactions, and overlap/adjacent/cancelled/other-venue/reactivation booking behavior.
- A final read-only row count confirmed **zero rows in all nine domain tables** after test rollback. The real development seed command remains unrun. Sequence counters may have advanced during tests.
- Phase 2 is complete. Phase 3 has not started. Cross-row capacity enforcement and registration transaction/concurrency services remain Phase 5 work, as documented in the design notes.

## Phase 3 verification record (2026-11-11)

- `python -m pytest --postgres -q`: **187 passed, 0 failed, 5 skipped**. This comprises **90 PostgreSQL integration cases**, **85 SQLite model/authentication cases**, and **12 foundation/offline-migration/CLI checks**. The five skips are venue exclusion cases on SQLite; those cases pass on PostgreSQL.
- All 64 authentication cases ran against both SQLite and PostgreSQL, with real CSRF validation and Werkzeug hashing. Coverage includes atomic registration, validation/uniqueness, password hashing, generic login failures, session/logout behavior, CSRF attacks, role/club access, assignment revocation, privilege injection, safe redirects, escaped output, CLI bootstrap/confirmation, legacy remember-cookie removal, and safe database errors.
- `flask db check`: no new upgrade operations detected. `flask db current`: **0001_initial (head)**. No schema constraints, migration revisions, or database schema were changed in Phase 3.
- Python compilation passed; dependency check reported no broken requirements. No dependencies were added or installed.
- Read-only counts before and after PostgreSQL tests confirmed **zero rows in all nine domain tables**. All test writes, including test administrators, were rolled back. Sequences may have advanced.
- No persistent initial administrator was created; run the interactive `create-admin` command when ready. The development seed command remains unrun.
- Pages and navigation were exercised through the Flask HTTP test client; browser visual verification was not performed. Operational limitations and assumptions are recorded in `docs/authentication.md`.
- Phase 3 is complete. Phase 4 CRUD has not started and requires approval.

## Phase 4 verification record (2026-11-11)

- SQLite/default suite before migration: **130 passed, 0 failed, 126 skipped**. PostgreSQL cases were gated pending migration approval. Targeted checks also passed after adding own-membership filters.
- The user explicitly approved migration `0002_club_active` and PostgreSQL integration tests. Upgrade applied successfully; `db current` reports **0002_club_active (head)** and `db check` reports **No new upgrade operations detected**.
- Full suite: `python -m pytest --postgres -q` → **251 passed, 0 failed, 5 skipped**, comprising **121 PostgreSQL cases**, **116 SQLite cases**, and **14 database-independent foundation/validation/offline-migration/CLI checks**. All five skips are PostgreSQL-only venue exclusion cases on SQLite, which pass on PostgreSQL.
- All prior Phase 1–3 tests continue to pass. New cases cover profile field restrictions/privacy, directories and search, club creation/edit scope, deactivation/reactivation, membership cancellation/reactivation/idempotency, roster scope and invalid transitions, venue validation/relationships/capacity reductions, pagination, and new-form CSRF.
- Python compilation passed; dependency check found no broken requirements. No dependency installation was needed.
- Before and after PostgreSQL testing: **one existing User and one existing Student**, with all other domain table counts zero. Test writes rolled back; existing records were preserved. Sequence counters may have advanced. No schema reset, database drop, seed-dev run, or persistent test administrator creation occurred.
- The schema reference and ER diagram include is_active. Route permissions, editable-field assumptions, membership lifecycle, and the migration review are in `docs/phase4-management.md`. HTTP rendering/flows were tested; browser visual verification and multi-connection stress tests were not performed.
- Restart the local Flask server if it was running without automatic reload. Phase 4 is complete; Phase 5 has not started and requires approval.

## Phase 5 verification record (2026-11-12)

- Began with a clean worktree on main at `5bd71c4`, confirmed origin `creamypotatoo/University-Event-Management`, and created `feature/phase5-events-registration` before implementation. Only Phase 5-related changes are included.
- `python -m pytest --postgres --postgres-concurrency -q`: **320 passed, 0 failed, 5 skipped**, comprising **158 PostgreSQL cases** (including six actual multi-connection races), **147 SQLite cases**, and **15 independent foundation/validation/offline-migration/CLI checks**. Skips are native venue exclusion cases on SQLite; PostgreSQL counterparts passed.
- The rollback-only PostgreSQL run also passed: **314 passed, 0 failed, 11 skipped** (six concurrency cases opt-in plus five SQLite exclusions). The six concurrency tests passed independently before the combined suite.
- The user explicitly approved temporary committed concurrency fixtures and exact-ID cleanup. Verified races: last-seat competition, same-student duplicate competition, both cancellation/registration orderings with an observed waiting Event lock, concurrent service bookings, and native PostgreSQL exclusion on competing raw inserts.
- `db current`: **0002_club_active (head)**. `db check`: **No new upgrade operations detected**. No model columns, constraints, migration revisions, or real seed data were changed. Python compilation and pip dependency checks passed; no dependencies were installed.
- Before/after tests: one existing User, one existing Student, all other domain tables empty. Rollback fixtures left no test records; committed race fixtures were removed by captured IDs. Existing data was preserved; sequence counters may have advanced. No database/schema reset/drop and no seed-dev run occurred.
- New routes, eligibility/deadline/status rules, privacy, lock ordering, and SQLite limitations are documented in `docs/phase5-events.md`. HTTP rendering and flow tests passed; browser visual QA was not performed.
- Phase 5 is complete. Expense management/reporting and Phase 6 have not started. Feature branch requires review before any merge into main.

## Phase 6 verification record (2026-11-12)

- Verified Phase 5 merged into main by PR #1 (`79cb0dd`), confirmed a clean worktree, ran the requested fast-forward-only pull, and created `feature/phase6-reports-expenses` from updated main.
- Focused expense/report suite on SQLite and PostgreSQL: **70 passed, 0 failed**.
- Full suite: `python -m pytest --postgres --postgres-concurrency -q` → **390 passed, 0 failed, 5 skipped**. This comprises **188 PostgreSQL cases**, **177 SQLite cases**, and **25 database-independent checks**. All five skips are native venue exclusion cases on SQLite; PostgreSQL counterparts pass. All Phase 1–5 regressions and the six previously approved concurrency cases passed.
- Verified expense CRUD/confirmation, Decimal validation, exact sums without registration join fanout, zero events/clubs, role/club scope, student privacy, dashboard metrics, campus-local date boundaries, filtered CSV quoting/Unicode/formula safety, CSRF, and safe database errors.
- `db current`: **0002_club_active (head)**. `db check`: **No new upgrade operations detected**. No migration, model change, schema reset/drop, dependency install, or seed-dev run was needed. Python compilation and pip dependency checks passed.
- Before/after testing: one existing User and one existing Student; every other domain table empty. New report/expense tests rolled back, and previously approved race fixtures cleaned up only their own IDs. Existing development records were preserved; sequence counters may have advanced.
- Routes, permissions, formulas, query strategy, date meanings, unsupported schema fields, CSV safety, and report-size limitations are documented in `docs/phase6-reports.md`. HTTP rendering was tested; browser visual QA was not performed.
- Phase 6 is complete and requires feature-branch review before merge. Phase 7 has not started.

## Phase 7 final verification (2026-11-12)

- Verified Phase 6 merged into main through PR #2, updated main with fast-forward-only pull, and created `feature/phase7-final-polish` from clean main.
- Full suite: **403 passed, 0 failed, 5 skipped**, including **191 PostgreSQL cases**, **180 passing SQLite cases**, and **32 independent checks**. The five skips are PostgreSQL-specific venue exclusions on SQLite; corresponding PostgreSQL tests and all six approved concurrency tests passed. No pytest warnings were reported.
- Focused final-QA suite: **13 passed**, including a complete three-role HTTP journey, error status/escaping/rollback behavior, logged-in database-outage recovery, event-form error associations, and production cookie flags.
- Schema/index/constraint audit passed in a read-only transaction; representative EXPLAIN plans were reviewed on the small current dataset. No index or schema change was justified. Head remains `0002_club_active`; `db check` found no new upgrade operations.
- **33 Jinja templates compiled**, and all **16 source POST forms** contained CSRF fields. Python compilation and dependency checks passed. No new dependency was installed; coverage and JS/browser runtime tooling were unavailable.
- Existing data preserved: one User, one Student, all other core tables empty before/after. No persistent demo setup, seed-dev, database reset/drop, or migration ran. Tests rolled back their rows or cleaned up previously approved synthetic race IDs; sequence counters may have advanced.
- Created demo/manual-QA guide, 40-question viva preparation with 14 SQL examples, and final testing report. Schema and ER documentation were regenerated consistently; feature docs include final QA notes.
- Manual browser, responsive rendering, JavaScript dialogs/menu execution, assistive technologies, and spreadsheet import remain pending human sign-off. This is not production-security certification. Final feature branch must be reviewed before merge; no further development phase is started.
