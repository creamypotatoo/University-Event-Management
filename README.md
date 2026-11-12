# University Event and Club Management System

Database foundation for a university DBMS course project. Uses Python Flask, PostgreSQL, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Werkzeug, server-rendered HTML, CSS, and Bootstrap 5.

## Scope

Implemented: application factory, configuration, health check, nine normalized models, migrations, optional seed, authentication/CSRF, role and club authorization, role dashboards, initial administrator CLI, student profiles, club directory/editing/deactivation, memberships and club rosters, venue management, and tests.

Not yet implemented: club administrator provisioning screens, event registration/capacity services, expense management, or reports. These belong to later approved phases. No database tables are created at startup; migrations require approval.

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

- Phase 4 stops before event registration, expenses, and administrator role/assignment provisioning.
- PostgreSQL settings are supplied locally. Phase 4 requires approval to add club lifecycle state with revision `0002_club_active`.
- Bootstrap 5.3.3 CSS is loaded from jsDelivr, requiring internet for Bootstrap styling. Custom CSS remains local. No JavaScript interactions are needed yet.
- Dependencies use bounded compatible ranges rather than a fully locked environment. Record exact installed versions for final delivery.
- The application factory follows the [Flask factory pattern](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) and initializes configuration before [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/config/).

Phase 5 requires explicit approval.

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
