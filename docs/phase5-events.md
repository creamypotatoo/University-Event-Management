# Phase 5: events and registration

The existing Event, Registration, Club, and Venue models and all constraints are reused. There is no new migration: head remains `0002_club_active`. PostgreSQL's `btree_gist` exclusion constraint remains intact. No event deletion, expense management, or Phase 6 reporting is introduced.

## Routes and permissions

| Route | Methods | Access |
| --- | --- | --- |
| `/events` | GET | Public search/filter/paginated directory |
| `/events/<event_id>` | GET | Public details, seat counts, own registration only |
| `/events/manage` | GET | Club administrators: assigned clubs only; system administrators: all events |
| `/clubs/<club_id>/events` | GET | Assigned club administrator or system administrator |
| `/clubs/<club_id>/events/new` | GET, POST | Assigned club administrator or system administrator |
| `/events/<event_id>/edit` | GET, POST | Owning club's administrator or system administrator |
| `/events/<event_id>/status` | POST | Same management scope; cancelled/completed transitions |
| `/events/<event_id>/register` | POST | Student: own profile only |
| `/events/<event_id>/registration/cancel` | POST | Student: own registration only |
| `/registrations` | GET | Student: own searchable registration/participation history |
| `/events/<event_id>/participants` | GET | Owning club's administrator or system administrator |
| `/events/<event_id>/participants/<registration_id>/status` | POST | Same management scope; record/undo attendance after start |

Every POST requires the existing global CSRF token. Anonymous private-route requests redirect to login; authenticated unauthorized requests receive 403. Unknown authorized records receive 404, malformed inputs 400, business conflicts/full/closed events 409, and unavailable database services 503. Driver errors and connection details are never rendered. Event ownership cannot be transferred through submitted fields; the owning club is derived from the stored event. Participant IDs must belong to the event in the URL. Public pages never include other students' identities. Managers see participant name, student number, department, and status, not account emails/password hashes.

Directory filters: `q` (literal case-insensitive title/description search), `status` (all/scheduled/completed/cancelled), `when` (upcoming/past/all), `club_id`, `venue_id`, and inclusive campus-local `from_date`/`to_date`. Default is upcoming events with all statuses. Pagination uses ten rows per page and preserves whitelisted filters. History and participant lists provide status/search filters and pagination. The student dashboard shows the next five scheduled future registered events, with a link to complete history. Manager dashboards link to event creation and participant lists.

## Scheduling and status rules

- Input without an explicit offset is interpreted in **Asia/Dhaka**, converted to UTC, and persisted in existing timezone-aware columns. All event page dates display in Asia/Dhaka. SQLite's naive retrieved values are treated as UTC for portable tests.
- New events are always scheduled, with a future start, end strictly after start, nonblank title (maximum 200), description (maximum 5000, multiline supported), valid venue, and positive integer capacity no greater than venue capacity. Club must be active. Extra status/owner fields are ignored.
- Only upcoming scheduled events may be edited. Changing time/venue retains the event ID and all registration history. Managers must consider communicating schedule changes; automated notifications are not implemented.
- Scheduled events may be cancelled; scheduled events may be completed only after their end. Cancelled and completed events are final. Repeated transition to the same terminal status is idempotent. There is no hard deletion or reopening of events.
- Cancellation retains registrations and their statuses. History displays event status separately so a registered row for a cancelled event is not mistaken for a live event. Cancelled events do not reserve their venue; completed events retain historical bookings.
- Half-open venue ranges `[start, end)` allow adjacent bookings. App pre-checks give a friendly conflict; PostgreSQL's exclusion constraint is authoritative, including independent writers that bypass the service.

## Registration eligibility and history

No separate deadline column exists. **Registration/reactivation and normal student cancellation close exactly at event start**; checks use the clock after acquiring the event lock, not when a request entered a queue. Registration requires a future scheduled event and an active club. Club membership is not a prerequisite: all students may attend university events. Students cannot create registrations for others via submitted IDs.

Statuses `registered` and `attended` occupy seats; `cancelled` does not. First registration inserts one row. Repeating an eligible registration is idempotent even when otherwise full. Reactivating a cancelled row requires eligibility and a free seat and preserves registration_id and original registered_at. The existing UNIQUE(event_id, student_id) remains unchanged.

Cancelling one's absent/already cancelled registration is idempotent and creates no row. Attended or completed participation cannot be cancelled. Students may cancel a non-attended registration for a cancelled event even after its start; cancellation of a live event closes at start. No cancellation or event cancellation deletes participation records.

Managers can mark registered participants attended, or undo attendance to registered, only after event start and only for non-cancelled events and registrations. Both statuses occupy a seat. Managers cannot use this endpoint to enroll or reactivate cancelled students. Students retain control of their cancellation. This phase records latest status/original timestamps, not an audit log of every cycle.

## Transaction and lock strategy

Services accept a SQLAlchemy session and never commit internally. Routes call one service and commit once, rolling back all changes on any validation/SQL failure. Unique/exclusion conflicts become safe 409 messages; deadlock, serialization, or lock-timeout failures prompt retry without partial writes. Capacity checks require **PostgreSQL READ COMMITTED**, the default for this app; each statement sees commits that happened while waiting. A stronger isolation deployment must retry serialization failures and review this assumption.

Lock order is Club (FOR SHARE), Venue(s) in ascending ID for event scheduling, Event (FOR UPDATE), then Registration. Registration/cancellation/attendance need only Club -> Event -> Registration; they never wait for a Venue. The shared Club lock prevents deactivation during eligibility checks. All service operations reacquire and refresh ORM state (`populate_existing`) after waiting so a cached event cannot supply stale capacity/status/times.

Competing registrations lock the same Event. The winner counts occupied statuses and inserts/reactivates while retaining the lock through commit; the next request counts again after it gets the lock. Cancellation takes the same lock, freeing a seat atomically. Edits lock the Event before recounting and reject capacity below occupied rows. No unlocked count-then-insert path exists in the application.

Event scheduling locks target/source Venue rows before the Event. Venue capacity edits already lock the Venue and check all non-cancelled events. This serializes event capacity/booking changes against venue reductions. Concurrent bookings for the same venue are serialized by that venue lock and checked with a fresh overlap query. The PostgreSQL exclusion constraint remains a final guard. Locking is deliberately conservative for a course project; one venue's event edits can queue behind each other. Cancellations/completion don't need a Venue lock because they cannot add a booking or increase venue requirements.

These cross-row limits are service-level rules, not new database triggers. Future writers, imports, and APIs must use the same services/locking contract. Direct SQL can violate capacity even though unique/check/exclusion constraints still apply. SQLite exercises business rules but cannot prove PostgreSQL locking/exclusion behavior.

References: [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html), [SQLAlchemy identity map refresh](https://docs.sqlalchemy.org/en/20/orm/session_api.html).

## Test commands and data safety

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest --postgres -q
```

These use existing rollback/savepoint isolation for request and model tests. To verify real races, separate connections need mutually visible committed fixtures. After explicit approval:

```powershell
.\.venv\Scripts\python.exe -m pytest --postgres --postgres-concurrency -q
```

Six concurrency cases use UUID-named test-only clubs/venues/events/students, commit competing transactions, and delete only captured fixture IDs in reverse foreign-key order afterward. Cleanup verifies fixture club identity before proceeding. No pre-existing records, schemas, or databases are dropped/reset. This is test setup, not seed-dev; seed-dev is never run. If a process is forcibly killed during these tests, unique `phase5-race-*` fixtures may remain; inspect and obtain approval for targeted cleanup rather than resetting the database. Sequence counters advance. Run tests locally without other writers or parallel pytest workers.

Real races cover last-seat competition, duplicate requests by one student, both orderings of cancellation versus registration (observing the blocked PostgreSQL lock), concurrent service bookings, and concurrent raw inserts rejected by native exclusion. HTTP tests cover validation, time conversion, scoped permissions, duplicate/reactivation behavior, capacity reduction, deadlines/statuses, history/privacy, attendance, CSRF, and safe transaction errors. Adjacent and cancelled-booking behavior is also covered. Browser visual QA is not claimed by the Flask test client.

## Verification (2026-11-12)

Full run with approved concurrency fixtures: **320 passed, 0 failed, 5 skipped**. Of these, **158 are PostgreSQL cases**, including all six multi-connection races. Only PostgreSQL-specific exclusions on SQLite were skipped. Standard rollback-only run: 314 passed, 11 skipped. Native constraint checks, compilation, dependency checks, and Alembic schema comparison passed. Head remains `0002_club_active`. After both race runs, existing record counts matched the baseline (one User, one Student, all other domain tables empty). No fixture records remained, no seed command ran, and no migration was needed. Git branch: `feature/phase5-events-registration`; review is required before merge.
