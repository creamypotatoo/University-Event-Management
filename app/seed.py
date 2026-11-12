"""Opt-in, additive development data. Never invoked at application startup."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import secrets

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Club, ClubAdmin, ClubMembership, Event, EventExpense, Registration, Student, User, Venue


def seed_data(session):
    """Insert missing demo records without overwriting existing rows or committing."""
    def get_or_add(model, lookup, **values):
        record = session.scalar(db.select(model).filter_by(**lookup))
        if record is None:
            record = model(**lookup, **values)
            session.add(record)
            session.flush()
        return record

    clubs = [get_or_add(Club, {"club_name": name}, description=description) for name, description in [
        ("Programming Club", "Peer learning, programming contests, and software workshops."),
        ("Debating Society", "Student debates and public speaking practice."),
        ("Photography Club", "Campus photography walks and exhibitions."),
    ]]
    venues = [get_or_add(Venue, {"venue_name": name}, location=location, capacity=capacity)
              for name, location, capacity in [
                  ("Computer Lab A", "Science Building, Floor 2", 60),
                  ("Central Auditorium", "Main Building, Ground Floor", 300),
                  ("Student Activity Hall", "Student Center, Floor 1", 100),
              ]]
    students = []
    for number, name, department in [(1, "Ayesha Rahman", "Computer Science"),
                                     (2, "Tanvir Hasan", "Electrical Engineering"),
                                     (3, "Nusrat Jahan", "Business Administration")]:
        user = get_or_add(User, {"email": f"demo.student{number}@example.edu"},
                          full_name=name, role="student",
                          password_hash=generate_password_hash(secrets.token_urlsafe(32)))
        student = get_or_add(Student, {"student_number": f"DEMO-2026-{number:03}"},
                             user_id=user.user_id, department=department, batch="2026")
        if student.user_id != user.user_id:
            raise ValueError("Demo student identifier belongs to a different user.")
        students.append(student)
    admin = get_or_add(User, {"email": "demo.organizer@example.edu"},
                       full_name="Farhan Ahmed", role="club_admin",
                       password_hash=generate_password_hash(secrets.token_urlsafe(32)))
    get_or_add(ClubAdmin, {"club_id": clubs[0].club_id, "user_id": admin.user_id})
    # Re-runs find each existing event by club/title; dates are set only on first insertion.
    first_day = (datetime.now(timezone.utc) + timedelta(days=30)).replace(hour=4, minute=0, second=0, microsecond=0)
    for index, title in enumerate(["Introduction to Competitive Programming", "Interdepartmental Debate", "Campus Photography Walk"]):
        event = get_or_add(Event, {"club_id": clubs[index].club_id, "title": title},
                           venue_id=venues[index].venue_id,
                           description="Development demonstration event.",
                           start_time=first_day + timedelta(days=index),
                           end_time=first_day + timedelta(days=index, hours=2),
                           capacity=min(40, venues[index].capacity), status="scheduled")
        for student in students:
            get_or_add(ClubMembership, {"club_id": clubs[index].club_id, "student_id": student.student_id})
            get_or_add(Registration, {"event_id": event.event_id, "student_id": student.student_id})
        get_or_add(EventExpense, {"event_id": event.event_id, "description": "Demo printing and materials"},
                   amount=Decimal("1500.00"), expense_date=date.today())


@click.command("seed-dev")
@click.option("--confirm", is_flag=True, help="Explicitly opt in to inserting development data.")
@with_appcontext
def seed_dev(confirm):
    """Add idempotent demo data to an already migrated development database."""
    if current_app.config["APP_ENV"] != "development":
        raise click.ClickException("Seeding is allowed only with APP_ENV=development.")
    if not confirm:
        raise click.ClickException("Review the README, then pass --confirm to insert demo data.")
    try:
        with db.session.begin():
            seed_data(db.session)
    except (SQLAlchemyError, ValueError):
        raise click.ClickException("Seed failed; transaction rolled back. Check schema and demo identifier conflicts.") from None
    click.echo("Development seed complete. Existing records were preserved. No usable demo passwords are supplied.")
