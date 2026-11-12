# Phase 6: expense management, financial reporting, and analytics

Final Phase 7 QA retains these monetary/query/CSV rules, improves expense-field error associations, and renders safe 503 recovery pages without reloading the database user. Server-side expense deletion confirmation is unchanged. See [final testing report](final-testing-report.md) and [demo guide](final-demo-guide.md). Historical verification at the end of this document refers to Phase 6 completion.

Phase 5 was verified merged into main via PR #1 (`79cb0dd`), then main was updated with `git pull --ff-only origin main`. Work uses `feature/phase6-reports-expenses`. No Phase 7 functionality is added.

## Schema and data safety

The existing EventExpense fields are reused unchanged: expense_id, event_id, description (255 characters), amount NUMERIC(12,2), and expense_date. Existing foreign keys, nonnegative amount check, and indexes remain intact. **No migration is needed**; database head remains `0002_club_active`. The schema has no categories, revenue, tickets, budgets, sponsorships, or profit. The UI adapts to that schema rather than treating descriptions as invented categories or adding columns.

No existing development records are altered during setup/testing, and seed-dev is not run. Expense CRUD changes real data only when an authorized user submits its form. Deletion has a dedicated confirmation page and requires both CSRF and confirm=delete on POST. GET never deletes. Deletion removes one scoped expense, preserving event/registration/club relationships. Existing tests use rollback/savepoint isolation; the previously approved Phase 5 concurrency fixtures remain opt-in and clean up only their own captured IDs.

## Routes and permissions

| Route | Methods | Behavior |
| --- | --- | --- |
| `/events/<event_id>/expenses` | GET | Paginated description/date-filtered expense list and filtered total |
| `/events/<event_id>/expenses/new` | GET, POST | Create one expense |
| `/events/<event_id>/expenses/<expense_id>/edit` | GET, POST | Edit description, amount, date only |
| `/events/<event_id>/expenses/<expense_id>/delete` | GET, POST | GET confirmation, POST confirmed deletion |
| `/reports/financial` | GET | Event/club financial totals, monthly expenditure, highest spend |
| `/reports/analytics` | GET | Event counts, registration/attendance metrics, club participation, monthly events |
| `/reports/financial.csv` | GET | Financial event rows with identical authorization/filters |
| `/reports/participation.csv` | GET | Event-level participation rows with identical authorization/filters |

System administrators can manage/report all clubs. Club administrators require both role club_admin and a matching ClubAdmin assignment; all queries, summary cards, filter choices, and CSV exports use that scope. A forged club/event filter does not widen scope: an unassigned club/event yields 403. A system administrator's unknown ID yields 404; a club/event mismatch yields 400. Expense IDs must belong to the authorized URL event; unrelated IDs yield 404 even if otherwise valid. Form-supplied owner/event IDs are ignored.

Students cannot access any financial route, report, export, or expense form. Their existing dashboard gains only their own summary, upcoming events, and history link; no financial queries or amounts run for student summaries. Public event details show an expense link only to managers, without financial amounts. Managers' participant exports contain event-level counts, not student identities or account information.

Anonymous private requests redirect to login. Authenticated wrong roles receive 403. All unsafe forms use existing global CSRF, including create/edit/delete. Invalid forms/filters return 400; unknown records 404. Database failures roll back and return a generic 503 without driver/connection information. Edit/delete lock the expense row; these flows do not change event capacity or scheduling.

## Exact monetary input

Amounts use Decimal and PostgreSQL NUMERIC, with no float conversion. Accepted syntax is ASCII digits with an optional decimal point and one/two fractional digits, in [0.00, 9999999999.99]. Zero is allowed by the existing CHECK. Negative signs, scientific notation, commas, empty input, overprecision, NaN, Infinity, and overflow are rejected before database writes. Valid values are quantized to two decimal places. Descriptions are nonblank, maximum 255; expense dates use canonical YYYY-MM-DD. Future/backdated expenses are permitted because the schema/business brief specifies no restriction. Currency is assumed BDT, consistently with the existing seed/design notes; no exchange rates or mixed-currency arithmetic is introduced.

PostgreSQL SUM(numeric) is exact. Financial queries return Decimal and use COALESCE(…, 0.00). SQLAlchemy adapts portable SQLite numeric results to Decimal for unit tests, but SQLite's NUMERIC storage is not equivalent to PostgreSQL's exact arithmetic; production financial correctness is verified on PostgreSQL.

## Filters and time boundaries

Reports accept from_date, to_date, club_id, event_id. Dates are canonical YYYY-MM-DD, inclusive, ordered start <= end, and before year 9999 so next-day boundaries are representable. Managers may filter only assigned clubs; system administrators may filter any club. Date filters never add clubs/events to the permission scope.

- **Financial:** range applies to expense_date, not event start. A January expense for a December event is included in January finances. All authorized selected events remain listed with zero expenses if none match; event counts on this page count all selected events independently of expense dates. Expenses for cancelled/completed events still count because cancellation does not erase incurred costs. Highest spending and monthly expenditure use the same filtered expense totals.
- **Analytics:** range applies to event start in Asia/Dhaka, converted to UTC half-open boundaries [local start midnight, midnight after end]. Monthly event grouping uses the campus-local year/month, including events near UTC month boundaries. Registration metrics describe records belonging to those selected events, not registrations created during the range.
- Expense lists additionally accept q (literal case-insensitive description search); their total matches both date and search filters. Reports deliberately do not use this expense-description search as an implicit event filter.

HTML event report tables and expense lists show ten rows per page. CSV exports include all filtered event rows, ignoring HTML pagination. Club/month/top-five tables summarize the whole filtered scope. Month tables show months with records, without inventing activity in gaps. Scoped choices and URLs preserve only known filters. For this local course app, grouped event results are materialized before HTML pagination and CSV output; large deployments should add database pagination/streaming without changing the aggregate/filter contract. Simple tables are used instead of additional chart dependencies.

## Financial query design

EventExpense is first grouped by event_id with SUM(amount) and COUNT. This one-row-per-event result is OUTER JOINed to the scoped Event relation and Club, with COALESCE for missing totals/counts. Club totals SUM those event rollups and GROUP BY club ID/name, preserving zero-event clubs. Monthly expenditure groups scoped expense rows by extracted year/month of expense_date. Overall total SUMs the rollup. Highest-spend ranking sorts the same Decimal event totals, ties by event ID, and shows five.

Registrations are not joined directly into financial expense rows. Three registrations and two expenses must not turn a 30.30 expense total into 90.90. Participation similarly preaggregates Registration by event before joining to Event/Club. All aggregates demonstrate JOIN/OUTER JOIN, SUM, COUNT, GROUP BY, COALESCE, date predicates, and date extraction. Clubs with no events and events with no child rows show zero where applicable. No report query mutates data.

## Metric definitions

| Metric | Formula |
| --- | --- |
| Total events | Count of authorized events selected by analytics filters |
| Upcoming events | Scheduled selected events whose start is strictly later than now |
| Completed/cancelled events | Counts by stored Event.status |
| Total registrations | All selected registration rows, including cancelled |
| Active/registered-status registrations | Registration.status = registered; excludes attended and cancelled |
| Attended | Registration.status = attended |
| Cancelled registrations | Registration.status = cancelled |
| Occupied / non-cancelled participation | registered + attended; a participation-row count, not distinct students |
| Event occupancy | 100 × occupied / capacity, rounded to one decimal with Decimal ROUND_HALF_UP |
| Completed-event attendance rate | 100 × attended / (registered + attended), only for completed events; denominator zero means N/A |
| Overall completed attendance | Same formula using summed numerators/denominators across completed events, not an unweighted mean |
| Popular events | Descending total registration rows including cancellations; ties by event ID; top five |
| Club activity/participation | Event count and registration/occupied/attended sums, grouped by club |
| Student personal summary | Only that Student's total, registered, attended, cancelled, upcoming registered, and past non-cancelled participation rows |

Upcoming/in-progress/cancelled event attendance percentages are N/A. Registration status and event status stay separate: cancelling an event preserves registered history. Thus registered-status and occupancy figures on a cancelled event describe retained records, not a live seat offer. Personal past participation means a non-cancelled registration for a non-cancelled event that has started; it includes underway events, not only completed events.

## CSV safety and format

Downloads use text/csv; charset=utf-8, fixed attachment filenames, CRLF line endings, a stable header row, and Python csv.writer with QUOTE_ALL. Values remain UTF-8; embedded commas/quotes/newlines are quoted correctly. Text cells with formula prefixes (=, +, -, @ and full-width counterparts), including prefixes hidden by leading whitespace/BOM, receive a leading apostrophe. Leading tabs/CR/LF are neutralized too. Decimal/int values are emitted as numeric text without introducing float arithmetic; unavailable rates are empty, not false zeros. Filenames are constants, never user input. Authenticated reports/downloads use Cache-Control: no-store and the existing security headers.

Financial headers: event_id, event_title, club_id, club_name, expense_count, total_expenses_bdt. Participation headers: event_id, title, club_id, club_name, status, capacity, total_registrations, active_registrations, attended, cancelled_registrations, occupied, occupancy_pct, attendance_rate. Exports contain aggregate event data rather than private individual student lists. Formula protection is intended for direct import; users should preserve text treatment when re-saving CSV in spreadsheet software.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reports.py --postgres -q
.\.venv\Scripts\python.exe -m pytest --postgres --postgres-concurrency -q
.\.venv\Scripts\python.exe -m flask --app app:create_app db current
.\.venv\Scripts\python.exe -m flask --app app:create_app db check
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pip check
```

The full command includes the previously approved six temporary committed Phase 5 race fixtures with exact-ID cleanup. New expense/report tests use rollback isolation only; even deletion tests remove newly created fixtures inside outer rollback transactions, never existing development data. Cases cover CRUD, confirmation/CSRF, amount bounds and invalid numbers, aggregation without join fanout, zero results, scope/privacy, formulas, campus date boundaries, CSV quoting/Unicode/formula injection, matching filters, empty assignments, and safe failures. No browser visual QA is implied by HTTP tests.

References: [PostgreSQL aggregate behavior](https://www.postgresql.org/docs/current/functions-aggregate.html), [OWASP CSV injection](https://owasp.org/www-community/attacks/CSV_Injection).

## Verification (2026-11-12)

Focused suite: **70 passed, 0 failed** across SQLite/PostgreSQL. Full suite with previously approved concurrency fixtures: **390 passed, 0 failed, 5 skipped**, including **188 PostgreSQL cases**; remaining cases are 177 SQLite and 25 independent checks. Skips are PostgreSQL venue exclusion checks on SQLite. Compilation, dependency checks, and Alembic comparison passed; head is unchanged at `0002_club_active`. Before/after record counts match: one User, one Student, no other domain records. New report/expense tests never committed their changes; temporary race fixtures were cleaned up by exact IDs. No existing development records were modified or deleted. Feature branch: `feature/phase6-reports-expenses`. Phase 7 has not started; review is required before merging.
