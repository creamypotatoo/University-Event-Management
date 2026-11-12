# Student, club, membership, and venue management

Final Phase 7 QA preserves the management rules and adds search clearing, campus-local membership dates, accessible navigation/tables/forms, and convenience club status prompts. Server CSRF/role/lifecycle checks remain authoritative; JS prompts are optional enhancement. See [final demo](final-demo-guide.md) and [final testing report](final-testing-report.md). Results recorded below refer to the original Phase 4 completion.

Phase 4 builds on existing Flask blueprints, CSRF protection, role checks, and normalized tables. No event registration or expense workflows are added.

## Routes and permissions

Every POST requires the global CSRF token. Anonymous access to private routes redirects to login; authenticated users without permission receive 403. Unknown authorized resources receive 404. Invalid form input returns 400, and joining/reactivating an inactive club returns 409. Duplicate names produce a form error and transaction rollback, using existing database unique constraints.

| Route | Methods | Permission / behavior |
| --- | --- | --- |
| `/profile` | GET | Student: own private profile |
| `/profile/edit` | GET, POST | Student: own name, department, batch only |
| `/students` | GET | System administrator: search and exact department filter |
| `/students/<student_id>` | GET | System administrator or profile owner |
| `/clubs` | GET | Public directory; q search and active/inactive/all filter |
| `/clubs/<club_id>` | GET | Public details; no member identities |
| `/clubs/new` | GET, POST | System administrator only |
| `/clubs/<club_id>/edit` | GET, POST | System administrator or assigned club administrator |
| `/clubs/<club_id>/status` | POST | System administrator; status=active/inactive |
| `/clubs/<club_id>/join` | POST | Student joins/reactivates own membership |
| `/clubs/<club_id>/leave` | POST | Student cancels own membership |
| `/memberships` | GET | Student: own memberships, q/status filters |
| `/clubs/<club_id>/members` | GET | System administrator or assigned club administrator; q/status filters |
| `/clubs/<club_id>/members/<membership_id>/status` | POST | Same scope; active/cancelled only; membership must belong to URL club |
| `/venues` | GET | Public directory; name/location search |
| `/venues/new` | GET, POST | System administrator only |
| `/venues/<venue_id>/edit` | GET, POST | System administrator only |

Lists use ten records per page, stable ordering with ID tie-breakers, preserved search/filter links, and empty states. Page numbers must be integers from 1 to 100000. Search is case-insensitive literal substring matching with SQL wildcard characters escaped. Student department filtering is exact. Page links whitelist filter keys instead of passing arbitrary query parameters to url_for. Pagination uses [Flask-SQLAlchemy paginate](https://flask-sqlalchemy.palletsprojects.com/en/stable/pagination/).

## Private profile fields

Students may update full name (1–150 printable characters), department (1–100), and batch (1–30). Email, student number, role, password hash, and owner IDs are immutable through profile forms. Extra submitted fields are ignored. System administrators can browse/view records but cannot modify another student's profile in this phase. Club administrators see only names, student numbers, departments, batches, and statuses in their club rosters; rosters omit account emails and private-profile links.

## Club lifecycle and necessary migration

The original Club model had no lifecycle field. Encoding deactivation in its name/description or deleting rows would lose meaning or relationships. Reviewed revision `0002_club_active` adds exactly one column:

```sql
ALTER TABLE clubs ADD COLUMN is_active BOOLEAN DEFAULT true NOT NULL;
```

Existing and new clubs default to active. Existing CHECK, foreign-key, unique, and index constraints remain unchanged. Alembic updates its version row normally. No records are deleted and no seed command is run. Downgrade would remove lifecycle state and is not part of this workflow. See PostgreSQL's [ADD COLUMN behavior](https://www.postgresql.org/docs/current/sql-altertable.html).

The SQL compiled offline. Applying it requires explicit approval; schema reference and ER diagram include the new field. PostgreSQL club queries require the approved upgrade before the application can use them.

Deactivation retains club details, admin assignments, membership statuses, events, registrations, and expenses. Club pages and inactive-directory filtering remain available. Students cannot join/rejoin inactive clubs, and administrators cannot reactivate their memberships. Students may still leave, and administrators may cancel memberships. Only system administrators reactivate clubs. Assigned club administrators may edit inactive clubs' name/description but cannot change the active flag.

## Membership transitions and transactions

The existing unique `(club_id, student_id)` constraint remains authoritative. First join creates one active row; repeated join is idempotent. Leaving changes status to cancelled. Rejoining updates the same row, preserving membership_id and original joined_at. Leaving without joining creates no row. No deletion or full cancellation history is introduced.

Administrators cancel/reactivate existing rows only; enrolling another student is not added. They cannot set unknown statuses, move memberships, or operate on another club's membership ID. Students always act as their logged-in profile, ignoring supplied student/owner IDs.

Membership writes and club status writes lock the owning Club with SELECT FOR UPDATE until commit on PostgreSQL. This serializes first joins and deactivation/reactivation races. Membership updates additionally lock the association row. SQLite does not provide these PostgreSQL row-lock guarantees. The single-transaction integration suite does not claim multi-connection stress coverage.

## Venue preservation

Venue names (1–150) and locations (1–255) must be printable and nonblank. Capacity must be an integer from 1 through 2147483647. Names retain case-sensitive uniqueness. Rows are edited in place; no deletion or event reassignment occurs. Capacity cannot be reduced below a non-cancelled existing event's capacity, including completed events. Edits lock the Venue row. Phase 5 event creation/rescheduling must use compatible venue locking and capacity checks; neither is introduced here.

## Verification and assumptions

Shared HTTP fixtures use real authentication and CSRF. New tests cover profile ownership/field whitelists, privacy, search/pagination, cross-club authorization, deactivation preservation, membership idempotency/reactivation, invalid statuses, venue validation, event relationships, and new-form CSRF. SQLite uses in-memory tables. PostgreSQL tests use outer-transaction rollback/savepoints without schema resets or committed test records; sequence counters may advance.

Account role changes, club administrator assignment/provisioning, password recovery, and institutional identity verification remain outside these flows. Browser visual verification is not implied by HTTP tests.

## Completion record (2026-11-11)

The user approved applying revision `0002_club_active` and running PostgreSQL tests. Upgrade succeeded; the database is at head and Alembic reports no new upgrade operations. Full suite: **251 passed, 0 failed, 5 skipped**, including **121 PostgreSQL cases**. All skips are PostgreSQL-only venue exclusion checks on SQLite. Before/after record counts matched: one existing User, one existing Student, and zero rows in the remaining domain tables. Test data was rolled back; no seed command was run. Existing constraints were preserved and only the approved lifecycle column was added.
