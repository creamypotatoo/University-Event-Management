# Entity relationship diagram

```mermaid
erDiagram
    clubs {
        integer club_id PK
        varchar club_name UK
        text description
        boolean is_active
        datetime created_at
    }
    users {
        integer user_id PK
        varchar full_name
        varchar email UK
        varchar password_hash
        varchar role
    }
    venues {
        integer venue_id PK
        varchar venue_name UK
        varchar location
        integer capacity
    }
    club_admins {
        integer club_admin_id PK
        integer club_id FK
        integer user_id FK
    }
    clubs ||--o{ club_admins : club_id
    users ||--o{ club_admins : user_id
    events {
        integer event_id PK
        integer club_id FK
        integer venue_id FK
        varchar title
        text description
        datetime start_time
        datetime end_time
        integer capacity
        varchar status
    }
    clubs ||--o{ events : club_id
    venues ||--o{ events : venue_id
    students {
        integer student_id PK
        integer user_id FK,UK
        varchar student_number UK
        varchar department
        varchar batch
    }
    users ||--o| students : user_id
    club_memberships {
        integer membership_id PK
        integer club_id FK
        integer student_id FK
        datetime joined_at
        varchar status
    }
    clubs ||--o{ club_memberships : club_id
    students ||--o{ club_memberships : student_id
    event_expenses {
        integer expense_id PK
        integer event_id FK
        varchar description
        numeric amount
        date expense_date
    }
    events ||--o{ event_expenses : event_id
    registrations {
        integer registration_id PK
        integer event_id FK
        integer student_id FK
        datetime registered_at
        varchar status
    }
    events ||--o{ registrations : event_id
    students ||--o{ registrations : student_id
```

PK = primary key; FK = required foreign key; UK = single-column unique key. Parents may have zero child rows.

Registration and ClubMembership are associative entities, not direct many-to-many shortcuts. Composite unique pairs are `(event_id, student_id)`, `(club_id, student_id)`, and `(club_id, user_id)` for ClubAdmin. They apply across all statuses, including cancelled rows. Student.user_id is unique, giving User an optional one-to-one Student profile.

All fields and constraint details are in [schema.md](schema.md). Service-level capacity and authorization rules are explained in [database-design.md](database-design.md) and [viva-preparation.md](viva-preparation.md).
