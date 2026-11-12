from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Club, ClubAdmin, ClubMembership, Event, EventExpense, Registration, Student, User, Venue
from app.seed import seed_data


@pytest.fixture
def graph(model_session):
    session = model_session
    tag = uuid4().hex
    user = User(full_name="Test Student", email=f"{tag}@example.edu", password_hash="test-only-hash")
    student = Student(user=user, student_number=tag, department="Computer Science", batch="2026")
    club = Club(club_name=f"Computing {tag}", description="Test club")
    venue = Venue(venue_name=f"Hall {tag}", location="Main Building", capacity=100)
    start = datetime(2035, 1, 1, 4, tzinfo=timezone.utc)
    event = Event(club=club, venue=venue, title="Workshop", description="Test event",
                  start_time=start, end_time=start + timedelta(hours=2), capacity=50)
    session.add_all([student, event])
    session.flush()
    return student, club, venue, event


def rejected(session, record):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(record)
            session.flush()


def test_relationships_many_to_many_and_expenses(model_session, graph):
    student, club, venue, event = graph
    second = Event(club=club, venue=venue, title="Second", description="Another event", capacity=20,
                   start_time=event.end_time, end_time=event.end_time + timedelta(hours=1))
    other_club = Club(club_name=f"Debate {uuid4().hex}", description="Debate")
    other_student = Student(user=User(full_name="Other", email=f"{uuid4().hex}@example.edu", password_hash="test-hash"),
                            student_number=uuid4().hex, department="Business", batch="2026")
    model_session.add_all([
        Registration(student=student, event=event), Registration(student=student, event=second),
        Registration(student=other_student, event=event),
        ClubMembership(student=student, club=club), ClubMembership(student=student, club=other_club),
        ClubAdmin(club=club, user=student.user),
        EventExpense(event=event, description="Materials", amount=Decimal("12.50"), expense_date=date(2035, 1, 1)),
    ])
    model_session.flush()
    assert len(student.registrations) == 2
    assert len(event.registrations) == 2
    assert len(student.memberships) == 2
    assert len(club.events) == 2
    assert len(venue.events) == 2
    assert event.expenses[0].amount == Decimal("12.50")
    assert student.user.student is student
    assert club.admin_assignments[0].user is student.user


@pytest.mark.parametrize("kind", ["registration", "membership"])
def test_duplicate_pairs_including_cancelled(model_session, graph, kind):
    student, club, venue, event = graph
    if kind == "registration":
        existing = Registration(student_id=student.student_id, event_id=event.event_id, status="cancelled")
        duplicate = Registration(student_id=student.student_id, event_id=event.event_id)
        active = "registered"
    else:
        existing = ClubMembership(student_id=student.student_id, club_id=club.club_id, status="cancelled")
        duplicate = ClubMembership(student_id=student.student_id, club_id=club.club_id)
        active = "active"
    model_session.add(existing)
    model_session.flush()
    rejected(model_session, duplicate)
    existing.status = active
    model_session.flush()
    assert existing.status == active


@pytest.mark.parametrize("case", ["venue_capacity", "event_capacity", "event_time", "negative_expense",
                                   "role", "event_status", "membership_status", "registration_status",
                                   "email_case", "blank_name", "null_title", "foreign_key", "duplicate_admin",
                                   "duplicate_user_student", "duplicate_student_number", "duplicate_email"])
def test_constraints(model_session, graph, case):
    student, club, venue, event = graph
    tag = uuid4().hex
    if case == "venue_capacity":
        record = Venue(venue_name=tag, location="Campus", capacity=0)
    elif case in {"event_capacity", "event_time", "event_status", "null_title"}:
        values = dict(club_id=club.club_id, venue_id=venue.venue_id, title=tag, description="Test",
                      start_time=event.end_time, end_time=event.end_time + timedelta(hours=1), capacity=10)
        if case == "event_capacity": values["capacity"] = 0
        if case == "event_time": values["end_time"] = values["start_time"]
        if case == "event_status": values["status"] = "unknown"
        if case == "null_title": values["title"] = None
        record = Event(**values)
    elif case == "negative_expense":
        record = EventExpense(event_id=event.event_id, description="Invalid", amount=Decimal("-0.01"), expense_date=date.today())
    elif case in {"role", "email_case", "blank_name", "duplicate_email"}:
        record = User(full_name="  " if case == "blank_name" else "Test",
                      email=student.user.email if case == "duplicate_email" else (f"UPPER{tag}@example.edu" if case == "email_case" else f"{tag}@example.edu"),
                      password_hash="test-hash", role="unknown" if case == "role" else "student")
    elif case == "membership_status":
        record = ClubMembership(club_id=club.club_id, student_id=student.student_id, status="unknown")
    elif case == "registration_status":
        record = Registration(event_id=event.event_id, student_id=student.student_id, status="unknown")
    elif case == "foreign_key":
        record = Registration(event_id=-1, student_id=student.student_id)
    elif case == "duplicate_admin":
        model_session.add(ClubAdmin(club_id=club.club_id, user_id=student.user_id))
        model_session.flush()
        record = ClubAdmin(club_id=club.club_id, user_id=student.user_id)
    else:
        user = User(full_name="Another", email=f"{tag}@example.edu", password_hash="test-hash")
        model_session.add(user)
        model_session.flush()
        record = Student(user_id=student.user_id if case == "duplicate_user_student" else user.user_id,
                         student_number=student.student_number if case == "duplicate_student_number" else tag,
                         department="Science", batch="2026")
    rejected(model_session, record)


def test_join_grouping_and_aggregation(model_session, graph):
    student, club, venue, event = graph
    model_session.add(Registration(student=student, event=event))
    model_session.flush()
    statement = (select(Club.club_name, func.count(Registration.registration_id))
                 .join(Event, Event.club_id == Club.club_id)
                 .join(Registration, Registration.event_id == Event.event_id)
                 .where(Club.club_id == club.club_id).group_by(Club.club_id, Club.club_name))
    assert model_session.execute(statement).one() == (club.club_name, 1)


def test_seed_is_idempotent_preserves_cancellations(model_session):
    seed_data(model_session)
    model_session.flush()
    models = [User, Student, Club, ClubAdmin, ClubMembership, Venue, Event, Registration, EventExpense]
    counts = [model_session.scalar(select(func.count()).select_from(model)) for model in models]
    registration = model_session.scalar(select(Registration).join(Event).where(Event.title == "Introduction to Competitive Programming"))
    registration.status = "cancelled"
    seed_data(model_session)
    model_session.flush()
    assert [model_session.scalar(select(func.count()).select_from(model)) for model in models] == counts
    assert registration.status == "cancelled"


@pytest.mark.parametrize("case", ["overlap", "adjacent", "cancelled", "other_venue", "reactivate"])
def test_postgresql_venue_exclusion(model_session, graph, case):
    if model_session.bind.dialect.name != "postgresql":
        pytest.skip("Venue exclusion is PostgreSQL-only")
    student, club, venue, event = graph
    other = Event(club_id=club.club_id, venue_id=venue.venue_id, title="Booking", description="Booking", capacity=20,
                  start_time=event.start_time + timedelta(minutes=30), end_time=event.end_time + timedelta(minutes=30))
    if case == "adjacent": other.start_time = event.end_time
    if case in {"cancelled", "reactivate"}: other.status = "cancelled"
    if case == "other_venue":
        other.venue = Venue(venue_name=uuid4().hex, location="Another building", capacity=30)
    if case == "overlap":
        rejected(model_session, other)
    else:
        model_session.add(other)
        model_session.flush()
        if case == "reactivate":
            with pytest.raises(IntegrityError):
                with model_session.begin_nested():
                    other.status = "scheduled"
                    model_session.flush()
