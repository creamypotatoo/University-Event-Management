# Viva preparation

Use [schema.md](schema.md) and the [Mermaid ER diagram](er-diagram.md) beside this guide. Examples use the actual nine core tables and existing fields. No sample query output is asserted. SQL examples are for a trusted local operator, not a public endpoint; Flask authorization must still scope application queries.

## Design and ER explanation

User stores identity, normalized unique email, password_hash, and the coarse role. Student has a required unique user_id and unique student_number, giving User zero or one Student profile. Administrators need not have a student profile. Club and Venue have many Events; every Event has exactly one of each. Event has many EventExpense and Registration rows. Student–Event and Student–Club many-to-many relationships use explicit Registration and ClubMembership entities because they carry timestamps/status. ClubAdmin maps authorized users to their assigned clubs independently of student memberships.

Each table has an integer surrogate primary key. Important candidate keys include users.email, students.user_id, students.student_number, clubs.club_name, venues.venue_name, and the three composite association pairs. Registration(event_id, student_id), ClubMembership(club_id, student_id), and ClubAdmin(club_id, user_id) are unique across the lifetime of a row, not just active rows. Cancel/reactivate the existing row rather than insert another one. All core columns are NOT NULL; foreign keys use ON DELETE RESTRICT. Club.is_active supports preservation rather than deletion. Expenses alone have an authorized confirmation-based deletion workflow.

Representative functional dependencies:

- user_id → full_name, email, password_hash, role; email is also a candidate determinant.
- student_id → user_id, student_number, department, batch; user_id and student_number are alternate keys.
- event_id → club_id, venue_id, title, description, start_time, end_time, capacity, status.
- (event_id, student_id) → registration_id, registered_at, status.
- (club_id, student_id) → membership_id, joined_at, status.
- expense_id → event_id, description, amount, expense_date.

1NF uses single values per column and separate association rows rather than comma-separated event/member lists. 2NF avoids attributes depending on only part of an association's candidate key: event title belongs to Event, not Registration. 3NF keeps transitive facts outside another entity's row: venue location/capacity are in Venue, club name in Club, and student details in Student/User. Counts/totals are derived rather than duplicated as stored columns. This reasoning assumes the stated business dependencies; department/batch are free-text attributes, not separate administered entities.

## Forty realistic questions and concise answers

1. **Why PostgreSQL?** It provides exact NUMERIC, transactions, row locks, foreign/unique/check constraints, range types, and GiST exclusions needed for this project.
2. **Why not use SQLite as the deployed database?** SQLite is convenient for isolated portable tests but does not prove PostgreSQL row-lock/exclusion behavior or exact production NUMERIC aggregation.
3. **What is a primary key?** A unique, non-null row identifier; for example events.event_id.
4. **What is a foreign key?** A reference to an existing parent key, such as events.club_id → clubs.club_id.
5. **What are candidate keys?** Minimal sets that uniquely identify a row. students.student_number and students.user_id are alternate candidates to student_id.
6. **Why surrogate IDs as well as natural unique keys?** Stable short references keep foreign keys independent of mutable names/emails while unique constraints preserve business identity.
7. **What is a composite key here?** The unique event_id/student_id pair identifies one lifetime registration, although registration_id is the surrogate PK.
8. **What does User–Student cardinality mean?** A Student has one User; a User can have no Student profile or exactly one because user_id is unique in Student.
9. **Why an associative entity?** Registration stores student/event membership plus registered_at/status; a hidden join table would not expose those lifecycle attributes cleanly.
10. **Explain 1NF using this project.** Each club membership is one row, rather than a list of club IDs in Student.
11. **Explain 2NF.** A registration does not store event title or student department, which depend on only one side of its composite candidate key.
12. **Explain 3NF.** Event references Venue rather than duplicating venue location; event_id → venue_id → venue location is resolved by separate tables.
13. **How does referential integrity preserve history?** RESTRICT foreign keys and mandatory references prevent deleting parents while child records exist; club/event lifecycle actions change status instead.
14. **How are duplicate memberships/registrations prevented?** Named database unique constraints cover the entire pair, including cancelled records; services reactivate the old row.
15. **Why are application validations still needed with CHECKs?** They give useful errors and enforce cross-row/deadline/finite-money rules that a row CHECK cannot express. The DB remains a final guard for its declared constraints.
16. **Which checks are present?** Positive venue/event capacity, event end > start, nonnegative expense amount, allowed roles/statuses, normalized email, and selected nonblank fields.
17. **How are overlapping venue bookings prevented?** A PostgreSQL exclusion constraint rejects the same venue with overlapping tstzrange intervals for non-cancelled events.
18. **Why btree_gist?** It supplies GiST equality support for the integer venue_id so equality and range overlap can be combined in one exclusion.
19. **Can adjacent events share a venue?** Yes: [start,end) includes the start and excludes the end, so one event can start exactly when another ends.
20. **How do cancelled and completed events affect venue booking?** Cancelled events are excluded from the reservation constraint; completed events retain historical bookings.
21. **Which indexes matter?** PK/unique indexes support identity/duplicate checks; FK-leading indexes aid joins; event date/status indexes support browsing; the GiST index enforces venue exclusion.
22. **Why not add indexes until every plan uses them?** A sequential scan can be optimal for tiny tables. EXPLAIN estimates are not proof of poor performance; indexes also cost space and writes.
23. **What does OUTER JOIN achieve in reports?** Events/clubs without expenses remain visible with COALESCE-generated zero totals.
24. **Why can a report join produce a wrong total?** Joining two expenses to three registrations creates six rows. Separate preaggregation produces one row per event before joining.
25. **What do GROUP BY, SUM, COUNT, and COALESCE do?** Group related rows, add exact amounts, count records, and replace missing aggregate values with zero.
26. **How is monetary precision preserved?** Python Decimal validation and PostgreSQL NUMERIC(12,2); float conversion and unrequested rounding of extra precision are avoided.
27. **What is ACID here?** Atomic User/Student creation and service writes; consistency from constraints/rules; isolation through PostgreSQL transactions/locks; durability from committed PostgreSQL storage.
28. **Which isolation assumption is used?** PostgreSQL READ COMMITTED. Statements after acquiring a contested lock see newly committed rows; stronger isolation needs serialization retry analysis.
29. **What is the last-seat race?** Two requests can both see one free seat if count and insert are unlocked; both then insert. Locking the Event serializes count/check/write until commit.
30. **How do cancellations and capacity edits coordinate?** They lock the same Event. Cancellation frees a seat atomically; an edit recounts occupied rows before lowering capacity.
31. **Why refresh ORM state after waiting?** A previously loaded identity-map object may contain stale capacity/status/time. populate_existing refreshes the locked row before decisions.
32. **What is the lock order?** Club shared lock, then venue IDs in ascending order for scheduling, then Event, then Registration. Registration never needs a Venue lock, reducing cycles.
33. **What if a deadlock or serialization conflict still happens?** PostgreSQL aborts a transaction; the app rolls back and returns a safe retry conflict instead of partially saving or overselling.
34. **Can direct SQL bypass capacity rules?** Yes. Capacity is a service-level cross-row invariant, not a new trigger. Trusted writers must use the locking contract; unique/check/exclusion constraints still apply to direct SQL.
35. **What does the Flask factory do?** Reads environment configuration, validates required settings, binds extensions, and registers blueprints/error handling without opening schema tables or seeding on startup.
36. **How do ORM and migrations differ?** SQLAlchemy models describe/query data; Alembic/Flask-Migrate version explicit schema changes. Model edits do not automatically alter the real database.
37. **Authentication versus authorization?** Login proves which user is signed in; role plus ClubAdmin assignment determines what objects they may manage. Hiding buttons alone is insufficient.
38. **How are passwords/sessions/CSRF protected?** Werkzeug scrypt hashes, Flask-Login loading current DB roles, signed HttpOnly/SameSite cookies, session clearing at login/logout, and per-session expiring CSRF tokens for all unsafe methods.
39. **How are SQL injection, XSS, and CSV formulas addressed?** Bound SQLAlchemy parameters; Jinja HTML autoescaping; csv.writer quoting plus formula-prefix neutralization. These are different output contexts and need different protections.
40. **What remains outside scope?** General role provisioning UI, email/enrollment verification, password recovery, MFA, shared rate limits, server-side cookie revocation, categories/revenue/budgets, waitlists/notifications, full cancellation audit history, and production/security certification.

## Meaningful SQL examples

These examples match the schema and are illustrative, not claimed query output. Named parameters such as :student_id are SQLAlchemy bind parameters; use `connection.execute(text(sql), parameters)` or replace them deliberately with synthetic IDs in a trusted pgAdmin session. Do not concatenate web input into SQL. Identity queries are private and require application authorization; direct database credentials do not enforce Flask roles.

### 1. Private student/user join

```sql
SELECT s.student_id, s.student_number, u.full_name, s.department, s.batch
FROM students s JOIN users u ON u.user_id = s.user_id
WHERE s.student_id = :student_id;
```

### 2. A student's event history

```sql
SELECT e.title, e.start_time, e.status AS event_status,
       r.status AS registration_status, r.registered_at
FROM registrations r JOIN events e ON e.event_id = r.event_id
WHERE r.student_id = :student_id
ORDER BY e.start_time DESC;
```

### 3. Active club memberships

```sql
SELECT c.club_name, c.is_active, m.joined_at
FROM club_memberships m JOIN clubs c ON c.club_id = m.club_id
WHERE m.student_id = :student_id AND m.status = 'active';
```

### 4. Club administration scope requires both role and assignment

```sql
SELECT c.club_id, c.club_name
FROM club_admins a JOIN clubs c ON c.club_id = a.club_id
JOIN users u ON u.user_id = a.user_id
WHERE a.user_id = :user_id AND u.role = 'club_admin';
```

### 5. Upcoming event/venue join

```sql
SELECT e.event_id, e.title, c.club_name, v.venue_name, v.location
FROM events e JOIN clubs c ON c.club_id = e.club_id
JOIN venues v ON v.venue_id = e.venue_id
WHERE e.status = 'scheduled' AND e.start_time > CURRENT_TIMESTAMP
ORDER BY e.start_time, e.event_id;
```

### 6. Expense totals including zero-expense events

```sql
SELECT e.event_id, e.title, COALESCE(SUM(x.amount), 0.00) AS expense_bdt
FROM events e LEFT JOIN event_expenses x ON x.event_id = e.event_id
GROUP BY e.event_id, e.title;
```

### 7. Club total/count without expense fanout

```sql
WITH costs AS (
    SELECT event_id, SUM(amount) AS amount
    FROM event_expenses GROUP BY event_id
)
SELECT c.club_id, c.club_name, COUNT(e.event_id) AS event_count,
       COALESCE(SUM(costs.amount), 0.00) AS expense_bdt
FROM clubs c LEFT JOIN events e ON e.club_id = c.club_id
LEFT JOIN costs ON costs.event_id = e.event_id
GROUP BY c.club_id, c.club_name;
```

### 8. Monthly expenditure with date filtering

```sql
SELECT EXTRACT(YEAR FROM expense_date) AS year,
       EXTRACT(MONTH FROM expense_date) AS month, SUM(amount) AS expense_bdt
FROM event_expenses
WHERE expense_date BETWEEN :from_date AND :to_date
GROUP BY EXTRACT(YEAR FROM expense_date), EXTRACT(MONTH FROM expense_date)
ORDER BY year, month;
```

### 9. Occupancy counts every seat-occupying status

```sql
SELECT e.event_id, e.capacity,
       COUNT(r.registration_id) AS occupied,
       ROUND(100.0 * COUNT(r.registration_id) / e.capacity, 1) AS occupancy_pct
FROM events e LEFT JOIN registrations r
  ON r.event_id = e.event_id AND r.status IN ('registered', 'attended')
GROUP BY e.event_id, e.capacity;
```

### 10. Attendance percentage only for completed events

```sql
SELECT e.event_id,
       ROUND(100.0 * COUNT(r.registration_id) FILTER (WHERE r.status = 'attended')
         / NULLIF(COUNT(r.registration_id)
             FILTER (WHERE r.status IN ('registered','attended')), 0), 1) AS attendance_rate
FROM events e LEFT JOIN registrations r ON r.event_id = e.event_id
WHERE e.status = 'completed'
GROUP BY e.event_id;
```

### 11. Check candidate venue overlaps (not sufficient alone for concurrent writes)

```sql
SELECT event_id, title
FROM events
WHERE venue_id = :venue_id AND status <> 'cancelled'
  AND tstzrange(start_time, end_time, '[)') &&
      tstzrange(CAST(:start_time AS timestamptz), CAST(:end_time AS timestamptz), '[)');
```

### 12. Monthly event starts in campus time

```sql
SELECT date_trunc('month', start_time AT TIME ZONE 'Asia/Dhaka') AS campus_month,
       COUNT(*) AS events
FROM events
GROUP BY date_trunc('month', start_time AT TIME ZONE 'Asia/Dhaka')
ORDER BY campus_month;
```

### 13. Observe constraint definitions without data changes

```sql
SELECT t.relname AS table_name, c.conname, pg_get_constraintdef(c.oid)
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
ORDER BY t.relname, c.conname;
```

### 14. Demonstrate a row lock without persisting a registration

```sql
BEGIN;
SELECT event_id, capacity, status FROM events
WHERE event_id = :event_id FOR UPDATE;
SELECT COUNT(*) AS occupied FROM registrations
WHERE event_id = :event_id AND status IN ('registered', 'attended');
ROLLBACK;
```

This last example locks a row and releases it; it is not the complete service algorithm and cannot run inside a READ ONLY transaction. In the application, Club locking/eligibility refresh precede Event locking, then uniqueness/capacity checks, insert/reactivation, and one commit. Run against an approved synthetic event only, never hold locks during a live presentation longer than necessary.

## Explain the important implementation details

**Concurrency:** Register/cancel/reactivate/attendance/capacity edits share the Event lock; counted statuses are registered and attended. The next transaction sees the winner's committed rows. PostgreSQL tests cover two competitors, same-student duplicates, both cancellation orderings with observed blocked locks, concurrent booking services, and raw booking inserts rejected by exclusion. SQLite does not validate this concurrency property.

**Venue exclusion:** venue_id equality and overlapping timezone-aware ranges must not both hold for two non-cancelled events. btree_gist enables the integer part. Application overlap checks improve feedback but do not replace the DB exclusion. Target/source venue locks also coordinate capacity/booking edits.

**Financial aggregation:** expense children and registration children are grouped separately. Joining raw child tables is a common multiplicative error. Financial dates refer to expense_date; analytics dates refer to campus-local event start. Decimal rounding to one decimal is used for derived percentages; money accepts no extra fractional precision. Overall completed attendance is weighted using total attended/total eligible, not a mean of per-event rates.

**Architecture:** The browser submits named form fields and CSRF; blueprints validate and authorize, query/services manipulate SQLAlchemy objects, the database enforces declared constraints, and Jinja renders escaped HTML/feedback. Read-only reports have scoped queries and matching CSV filters. Application factories bind uninitialized extensions after environment config. Alembic head is 0002_club_active. The final error renderer intentionally avoids Flask-Login's eager template-user context during database outages.

**Common mistakes to discuss:** relying on hidden buttons instead of permission checks; trusting submitted owner IDs/roles; counting cancelled seats; unlocked count-then-insert; using stale ORM identities after locks; treating local dates as UTC; assuming a normal SELECT overlap pre-check is race-safe; summing after joining two child collections; dividing by zero/claiming upcoming attendance; using float for currency; confusing CSV quoting with formula neutralization; storing secrets in Git; or claiming manual browser checks/production certification from HTTP tests.
