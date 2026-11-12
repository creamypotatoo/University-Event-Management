"""Opt-in real PostgreSQL races. Committed UUID fixtures have exact-ID cleanup."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event as Signal
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import create_app
from app.events import services
from app.extensions import db
from app.models import Club, Event, Registration, Student, User, Venue

pytestmark = pytest.mark.postgresql


@pytest.fixture
def race_data(request):
    if not request.config.getoption("--postgres-concurrency"):
        pytest.skip("Requires explicit approval and --postgres-concurrency for committed test fixtures")
    app = create_app()
    if app.config["APP_ENV"] != "development":
        pytest.fail("Concurrency fixtures require a development database", pytrace=False)
    with app.app_context():
        engine = db.engine
    prefix = "phase5-race-" + uuid4().hex
    with Session(engine) as session, session.begin():
        club = Club(club_name=prefix, description="Temporary concurrency fixture")
        venue = Venue(venue_name=prefix, location="Temporary test venue", capacity=10)
        students = []
        for index in range(3):
            student = Student(user=User(full_name="Concurrency Fixture", email=f"{prefix}-{index}@example.invalid",
                                        password_hash="unusable-concurrency-fixture", role="student"),
                              student_number=f"R-{uuid4().hex}", department="Test", batch="Test")
            students.append(student)
        start = datetime(2050, 7, 1, 4, tzinfo=timezone.utc)
        event = Event(club=club, venue=venue, title=prefix, description="Temporary test event",
                      start_time=start, end_time=start + timedelta(hours=1), capacity=1, status="scheduled")
        session.add_all([event, *students])
        session.flush()
        data = {"engine": engine, "club": club.club_id, "venue": venue.venue_id, "event": event.event_id,
                "students": [s.student_id for s in students], "users": [s.user_id for s in students], "prefix": prefix}
    try:
        yield data
    finally:
        # No resets, TRUNCATE, schema drops, or broad deletes. Never touch pre-existing rows.
        with Session(engine) as session, session.begin():
            assert session.scalar(select(Club.club_name).where(Club.club_id == data["club"])) == prefix
            event_ids = select(Event.event_id).where(Event.club_id == data["club"])
            session.execute(delete(Registration).where(Registration.event_id.in_(event_ids)))
            session.execute(delete(Event).where(Event.club_id == data["club"]))
            session.execute(delete(Student).where(Student.student_id.in_(data["students"])))
            session.execute(delete(User).where(User.user_id.in_(data["users"])))
            session.execute(delete(Club).where(Club.club_id == data["club"]))
            session.execute(delete(Venue).where(Venue.venue_id == data["venue"]))
        engine.dispose()


def bounded(session):
    session.execute(text("SET LOCAL lock_timeout = '8s'"))
    session.execute(text("SET LOCAL statement_timeout = '12s'"))


@pytest.mark.parametrize("same_student", [False, True])
def test_competing_registrations_never_oversell(race_data, same_student):
    barrier = Barrier(2)

    def compete(index):
        with Session(race_data["engine"]) as session:
            try:
                with session.begin():
                    bounded(session)
                    # Deliberately preload an ORM identity before the competing commit.
                    session.get(Event, race_data["event"])
                    barrier.wait(timeout=5)
                    services.register_student(session, race_data["event"], race_data["students"][0 if same_student else index])
                return "registered"
            except services.RuleViolation:
                return "full"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, (0, 1)))
    assert results.count("registered") == (2 if same_student else 1)
    with Session(race_data["engine"]) as session:
        assert services.seats_used(session, race_data["event"]) == 1
        assert len(session.scalars(select(Registration).where(Registration.event_id == race_data["event"])).all()) == 1


@pytest.mark.parametrize("cancel_first", [True, False])
def test_concurrent_cancellation_and_registration_block_on_event(race_data, cancel_first):
    with Session(race_data["engine"]) as session, session.begin():
        services.register_student(session, race_data["event"], race_data["students"][0])
    staged, follower_ready, release = Signal(), Signal(), Signal()
    follower_pid = []

    def action(session, cancel):
        try:
            if cancel:
                services.cancel_registration(session, race_data["event"], race_data["students"][0])
                return "cancelled"
            services.register_student(session, race_data["event"], race_data["students"][1])
            return "registered"
        except services.RuleViolation:
            return "full"

    def leader():
        with Session(race_data["engine"]) as session, session.begin():
            bounded(session)
            services.event_and_club(session, race_data["event"])
            outcome = action(session, cancel_first)
            staged.set()
            assert release.wait(timeout=10)
            return outcome

    def follower():
        assert staged.wait(timeout=5)
        with Session(race_data["engine"]) as session, session.begin():
            bounded(session)
            follower_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
            follower_ready.set()
            return action(session, not cancel_first)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(leader), pool.submit(follower)
        try:
            assert follower_ready.wait(timeout=5)
            deadline, blocked = monotonic() + 5, False
            with race_data["engine"].connect() as connection:
                while monotonic() < deadline:
                    blocked = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)"), {"pid": follower_pid[0]})
                    if blocked:
                        break
                    sleep(0.02)
            assert blocked, "Competing operation did not wait for the Event row lock"
        finally:
            release.set()
        results = [first.result(timeout=15), second.result(timeout=15)]
    assert results == (["cancelled", "registered"] if cancel_first else ["full", "cancelled"])
    with Session(race_data["engine"]) as session:
        assert services.seats_used(session, race_data["event"]) == (1 if cancel_first else 0)


@pytest.mark.parametrize("use_service", [True, False])
def test_concurrent_venue_bookings_and_native_exclusion(race_data, use_service):
    barrier = Barrier(2)
    values = {"title": "Concurrent booking", "description": "Temporary test event", "venue_id": race_data["venue"],
              "start_time": datetime(2050, 7, 2, 4, tzinfo=timezone.utc), "end_time": datetime(2050, 7, 2, 5, tzinfo=timezone.utc), "capacity": 2}

    def book(index):
        with Session(race_data["engine"]) as session:
            try:
                with session.begin():
                    bounded(session)
                    barrier.wait(timeout=5)
                    if use_service:
                        services.save_event(session, SimpleNamespace(role="system_admin"), values, club_id=race_data["club"])
                    else:
                        session.add(Event(club_id=race_data["club"], status="scheduled", **values))
                        session.flush()
                return "booked"
            except services.RuleViolation:
                return "conflict"
            except IntegrityError as error:
                assert error.orig.sqlstate == "23P01"
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(book, (0, 1)))
    assert sorted(results) == ["booked", "conflict"]
