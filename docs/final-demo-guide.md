# Final demonstration guide

This is a local university DBMS project, not a production deployment. The application implements student accounts/profiles, club membership, club/venue administration, events and transaction-safe registration, attendance, expenses, scoped financial/participation reports, and CSV. No new demo-data command was needed. **No persistent demo records have been inserted by the agent.**

## Launch on Windows (PowerShell)

1. Open Windows **Services** and confirm your installed PostgreSQL service is running (its exact name depends on the installation). Alternatively open pgAdmin and connect to the local server. Starting a stopped Windows service may require an administrator; do that yourself if required. Do not reset or recreate the existing university_events database.
2. Open VS Code at D:\dbms_project. For an existing checkout/virtual environment, skip installation. For a fresh approved setup, use the README commands to create .venv and install requirements. Copy .env.example only if .env does not already exist. Set your own secret and PostgreSQL URL; never show that file during the presentation.
3. Verify, without schema/data changes:

```powershell
Set-Location D:\dbms_project
.\.venv\Scripts\python.exe -m flask --app app:create_app check-db
.\.venv\Scripts\python.exe -m flask --app app:create_app db current
.\.venv\Scripts\python.exe scripts/verify_database.py
```

Expected migration head is 0002_club_active. If missing, stop and obtain approval before applying existing migrations. Do not run db init, downgrade, create_all, reset/drop, or seed-dev against the real database.

4. Run the local development server, then open http://127.0.0.1:5000:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app run --debug
```

Use APP_ENV=development for local HTTP. The debugger is only for your own local development; do not expose it publicly. /health reports app liveness and database=not_checked; check-db verifies the connection separately. Bootstrap CSS needs internet; local CSS/JS still load from Flask. Stop with Ctrl+C.

## Identify the three roles safely

Use separate browser profiles/private windows for student, organizer, and system administrator so sessions do not overwrite each other. Never project passwords, .env, hashes, cookies, or tokens. No default demo password is supplied: choose private 12–128-character passphrases and keep them outside Git.

- **Student:** use the registration page to create a newly labeled synthetic student, such as full name DEMO Student One, a unique DEMO-* student number, and an address in example.invalid. Register a second synthetic student if demonstrating the last-seat rule. Keep a note of your own chosen private credentials, not in the repository.
- **System administrator:** identify an existing authorized account. If none exists, obtain approval to create one persistently, then run `python -m flask --app app:create_app create-admin` using the virtual environment. Password entry is hidden and confirmed. The command refuses to promote an existing user or create a second bootstrap administrator. It does not reveal an existing account's password.
- **Club administrator:** use an existing assigned organizer if available. Public registration cannot assign this role, and there is no general role/assignment CRUD UI. For a newly created synthetic demo organizer only, a trusted local operator can explicitly provision the role/assignment as below after approval. Do not change any real account or reuse existing real data for the demo.

### Optional manual provisioning of a newly created synthetic organizer

This is a documented operator workflow, not an automatic seed command and not an action the agent has executed. **Approval is required before performing persistent demo setup.** First register DEMO Organizer using a fresh @example.invalid address and private password through the normal form, and have the system administrator create a new club named DEMO Programming Club (choose a unique suffix if needed). Then launch the trusted Flask shell:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app shell
```

Enter the following, supplying only your newly created synthetic identifiers. It will not create/change an unrelated real account. Repeating it does not duplicate the assignment:

```python
from app.extensions import db
from app.models import User, Club, ClubAdmin
email = input("New synthetic organizer email: ").strip().lower()
club_name = input("New synthetic club name: ").strip()
organizer = db.session.scalar(db.select(User).where(User.email == email))
club = db.session.scalar(db.select(Club).where(Club.club_name == club_name))
assert organizer and organizer.full_name.startswith("DEMO ") and organizer.email.endswith("@example.invalid")
assert organizer.role in {"student", "club_admin"} and club and club.club_name.startswith("DEMO ")
assignment = db.session.scalar(db.select(ClubAdmin).where(ClubAdmin.club_id == club.club_id, ClubAdmin.user_id == organizer.user_id))
organizer.role = "club_admin"
if assignment is None:
    db.session.add(ClubAdmin(club_id=club.club_id, user_id=organizer.user_id))

db.session.commit()
```

If an assertion fails, use db.session.rollback() and stop; never remove assertions to target real records. This preserves the synthetic account's Student profile; role and explicit assignment control authorization. No password is printed or changed. General provisioning remains an operator responsibility, not a hidden application feature.

## Suggested 10–15 minute presentation

Every row you create below must be clearly synthetic and intentionally approved. This guide describes expected behavior; it is not a claim that browser checks or demo setup have already been performed.

1. **Overview:** show homepage, Events/Clubs/Venues directories, ER diagram, and nine normalized tables. Explain public versus private routes and no default privileged registration.
2. **Student:** log in, update permitted profile fields, show email/student number/role remain read-only. Join, leave, and rejoin the synthetic club; show one membership row retained. /students must be 403 for students (it is a private system-administrator directory, not a public student listing).
3. **System administrator:** create DEMO Hall with capacity 1 and the synthetic club if not already prepared. Search student records, then show venue and club administration. Never deactivate a real club for presentation.
4. **Assigned organizer:** edit the synthetic club; demonstrate an unassigned synthetic club edit/roster returns 403. Create DEMO Last Seat Workshop in DEMO Hall, capacity 1. Choose start at least five minutes ahead and end two minutes after start. Times are Asia/Dhaka; creation requires a future start. Explain why capacity 2 is rejected by a capacity-1 venue.
5. **Scheduling:** attempt another event in the same venue overlapping the workshop; expect a friendly 409. Explain adjacent [start,end) slots are allowed. Show the PostgreSQL exclusion definition with the read-only audit command. Do not try to bypass constraints with real SQL writes.
6. **Registration:** student one registers twice; explain repeated eligible requests keep one row and one seat. Student two receives full/409. Student one cancels; student two can take the seat. Student one's reactivation is rejected while full. Have student two cancel, then student one reactivate. This retains the original registration ID/timestamp. Show personal dashboard/history and denial of the participant list to students.
7. **Expenses while waiting:** organizer enters synthetic expenses 10.10 and 20.20 BDT; the expected total for those two entries is 30.30. Edit an entry, inspect the explicit delete-confirmation page, and cancel deletion first to demonstrate safety. If you subsequently confirm deletion, remove only your synthetic expense. Negative, NaN, excess precision, and invalid dates are rejected.
8. **Attendance:** after the real start time, organizer marks student one attended. After the real end, mark the event completed. The app intentionally rejects early attendance/completion and disallows edits after start. Do not backdate event rows in PostgreSQL to speed up the demo; prepare the timing or explain the automated simulated-clock test instead.
9. **Reports:** organizer shows only assigned-club totals; system administrator shows university-wide totals. Financial date filters use expense_date; analytics filters use event start date in Asia/Dhaka. Explain registered vs attended vs cancelled, occupancy, and completed-only attendance rate. An upcoming event displays N/A attendance percentage.
10. **CSV:** download both filtered exports. Inspect UTF-8 headers, quoting, exact monetary text, and matching filter scope. Use the automated injection regression test rather than opening an untrusted formula payload in a spreadsheet. Exports are aggregate event data, not student identity lists.
11. **Cancellation/history:** on a separate newly created synthetic future event, cancel it and show its record/registrations retained and registration closed. Cancelled/completed events cannot be reopened. Deactivating the synthetic club preserves history and blocks new memberships/registration.
12. **Integrity finale:** show the read-only schema audit, migration head, final test report, and six real concurrency tests. The human last-seat demo is sequential; the PostgreSQL multi-connection tests demonstrate actual competing transactions and observed locks. Log out and verify private pages redirect to login.

## What is deliberately unsupported

No general user/role/club-admin assignment UI, account recovery, MFA, email/enrollment verification, revenue, budgets, categories, profit, ticketing, notifications, waitlists, recurring events, or full cancellation-cycle audit log. Student directory access is system-admin-only. Direct SQL does not inherit Flask authorization and can bypass service capacity rules; use trusted operators and transactional services. This is not a production-security certification.

## Manual browser checklist (all pending human verification)

Mark each item only after actually performing it, record browser/version/date and observations. Automated Flask HTTP tests are separate and are not evidence of visual/browser execution.

| Check | What to verify | Browser status |
| --- | --- | --- |
| Homepage | Branding, no preview wording, public navigation | Pending |
| Registration/login | Labels, password masking, generic failures, keyboard flow | Pending |
| Student dashboard/profile | Only own information; editing whitelist | Pending |
| Club admin dashboard | Only assigned clubs, working report/event links | Pending |
| System dashboard | All-club stats, private student search, venues | Pending |
| Event forms | Invalid-field associations; Dhaka times; venue conflicts | Pending |
| Registration | Last seat, duplicates, cancellation/reactivation | Pending |
| History | Event status distinct from registration status | Pending |
| Attendance | Start/end boundaries and completed rate | Pending |
| Expenses | Validation, edit, confirmation, cancel/delete behavior | Pending |
| Financial reports | Exact totals, zero rows, scope/date filters | Pending |
| Analytics | Occupancy, N/A upcoming rate, monthly campus dates | Pending |
| CSV | Download headers, UTF-8, filter parity, spreadsheet text import | Pending |
| Error pages | 400/403/404/409; safe unavailable/500 behavior | Pending |
| Logout/access | POST-only logout; expired/missing CSRF handling | Pending |
| Desktop/tablet/mobile | 1440px, 768px, 375px; menu, wrapping, horizontal tables | Pending |
| Keyboard/accessibility | Skip link, Tab focus, Menu/Escape, scrollable tables, labels | Pending |
| Confirmations | Decline/accept status and cancellation prompts; expense confirmation | Pending |
| JS disabled | Navigation remains visible; forms work; server expense confirmation retained | Pending |

Client-side convenience prompts need JavaScript; server authorization, CSRF, and expense deletion confirmation do not depend on it. Browser automation, screenshots, JS execution, and assistive-technology testing were not performed by the agent.
