"""Transactional event and seat allocation rules. Caller commits or rolls back.

Lock order: Club (shared) -> Venue(s, ascending ID) -> Event -> Registration.
Registration needs only Club -> Event -> Registration. Never commit inside here.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import Club, ClubAdmin, Event, Registration, Venue

OCCUPIED = ("registered", "attended")


class RuleViolation(Exception):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


def now_utc():
    return datetime.now(timezone.utc)


def utc(value):
    # SQLite loses timezone information; all application writes are normalized UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def locked(session, model, identifier, shared=False):
    record = session.get(model, identifier, populate_existing=True, with_for_update={"read": shared})
    if record is None:
        raise RuleViolation("The requested record does not exist.", 404)
    return record


def require_manager(session, actor, club_id):
    if actor.role == "system_admin":
        return
    if actor.role != "club_admin" or session.scalar(select(ClubAdmin.club_admin_id).where(
        ClubAdmin.club_id == club_id, ClubAdmin.user_id == actor.user_id
    )) is None:
        raise RuleViolation("You cannot manage events for this club.", 403)


def seats_used(session, event_id):
    return session.scalar(select(func.count(Registration.registration_id)).where(
        Registration.event_id == event_id, Registration.status.in_(OCCUPIED)
    ))


def event_and_club(session, event_id):
    preview = session.get(Event, event_id)
    if preview is None:
        raise RuleViolation("Event not found.", 404)
    # Event ownership cannot be changed by any Phase 5 operation.
    club = locked(session, Club, preview.club_id, shared=True)
    event = locked(session, Event, event_id)
    return event, club


def register_student(session, event_id, student_id, *, now=None):
    event, club = event_and_club(session, event_id)
    now = now or now_utc()  # Evaluate the deadline after acquiring the Event lock.
    if event.status != "scheduled" or utc(event.start_time) <= now or not club.is_active:
        raise RuleViolation("Registration is closed. The event must be upcoming, scheduled, and organized by an active club.")
    registration = session.scalar(select(Registration).where(
        Registration.event_id == event_id, Registration.student_id == student_id
    ).with_for_update().execution_options(populate_existing=True))
    if registration is not None and registration.status in OCCUPIED:
        return registration
    if seats_used(session, event_id) >= event.capacity:
        raise RuleViolation("This event is full. Please check again if a seat becomes available.")
    if registration is None:
        registration = Registration(event_id=event_id, student_id=student_id, status="registered")
        session.add(registration)
    else:
        registration.status = "registered"
    session.flush()
    return registration


def cancel_registration(session, event_id, student_id, *, now=None):
    event, club = event_and_club(session, event_id)
    registration = session.scalar(select(Registration).where(
        Registration.event_id == event_id, Registration.student_id == student_id
    ).with_for_update().execution_options(populate_existing=True))
    if registration is None or registration.status == "cancelled":
        return registration
    if registration.status == "attended" or event.status == "completed":
        raise RuleViolation("Completed participation cannot be cancelled.")
    if event.status != "cancelled" and utc(event.start_time) <= (now or now_utc()):
        raise RuleViolation("Cancellation closes when the event starts.")
    registration.status = "cancelled"
    session.flush()
    return registration


def save_event(session, actor, values, *, event_id=None, club_id=None, now=None):
    previous = session.get(Event, event_id) if event_id is not None else None
    if event_id is not None and previous is None:
        raise RuleViolation("Event not found.", 404)
    owner = previous.club_id if previous is not None else club_id
    require_manager(session, actor, owner)
    club = locked(session, Club, owner, shared=True)
    if not club.is_active:
        raise RuleViolation("An inactive club cannot create or edit scheduled events.")
    # Lock both old and new venue in a deterministic order before the Event.
    venue_ids = {values["venue_id"]}
    if previous is not None:
        venue_ids.add(previous.venue_id)
    venues = {identifier: locked(session, Venue, identifier) for identifier in sorted(venue_ids)}
    event = locked(session, Event, event_id) if previous is not None else None
    now = now or now_utc()
    if event is not None and (event.status != "scheduled" or utc(event.start_time) <= now):
        raise RuleViolation("Only upcoming scheduled events can be edited.")
    if utc(values["start_time"]) <= now or utc(values["end_time"]) <= utc(values["start_time"]):
        raise RuleViolation("Choose a future start and an end later than the start.", 400)
    if not 1 <= values["capacity"] <= venues[values["venue_id"]].capacity:
        raise RuleViolation("Event capacity must be positive and cannot exceed venue capacity.", 400)
    if event is not None and values["capacity"] < seats_used(session, event.event_id):
        raise RuleViolation("Capacity cannot be reduced below the occupied seat count.")
    overlap = select(Event.event_id).where(
        Event.venue_id == values["venue_id"], Event.status != "cancelled",
        Event.start_time < values["end_time"], Event.end_time > values["start_time"]
    )
    if event is not None:
        overlap = overlap.where(Event.event_id != event.event_id)
    if session.scalar(overlap.limit(1)) is not None:
        raise RuleViolation("This venue is already booked for part of that time. Choose another venue or time.")
    if event is None:
        event = Event(club_id=owner, status="scheduled")
        session.add(event)
    for name in ("title", "description", "venue_id", "start_time", "end_time", "capacity"):
        setattr(event, name, values[name])
    session.flush()  # PostgreSQL exclusion constraint remains the final booking guard.
    return event


def change_event_status(session, actor, event_id, target, *, now=None):
    event, club = event_and_club(session, event_id)
    require_manager(session, actor, event.club_id)
    if target not in {"cancelled", "completed"}:
        raise RuleViolation("Choose cancelled or completed status.", 400)
    if event.status == target:
        return event
    if event.status != "scheduled":
        raise RuleViolation("Cancelled and completed events are final and cannot change status.")
    if target == "completed" and utc(event.end_time) > (now or now_utc()):
        raise RuleViolation("An event can be completed only after it ends.")
    event.status = target
    session.flush()
    return event


def mark_participant(session, actor, event_id, registration_id, target, *, now=None):
    event, club = event_and_club(session, event_id)
    require_manager(session, actor, event.club_id)
    registration = session.scalar(select(Registration).where(
        Registration.event_id == event_id, Registration.registration_id == registration_id
    ).with_for_update().execution_options(populate_existing=True))
    if registration is None:
        raise RuleViolation("Registration not found for this event.", 404)
    if target not in {"registered", "attended"}:
        raise RuleViolation("Choose registered or attended status. Students manage their own cancellation.", 400)
    if registration.status == "cancelled" or event.status == "cancelled":
        raise RuleViolation("Cancelled registrations or events cannot be marked for attendance.")
    if utc(event.start_time) > (now or now_utc()):
        raise RuleViolation("Attendance can be recorded only after the event starts.")
    registration.status = target  # Both statuses occupy a seat; no new seat is allocated.
    session.flush()
    return registration
