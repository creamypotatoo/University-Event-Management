"""Phase 5 event pages and authorized registration/attendance actions."""

from datetime import date, datetime, time, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.auth.authorization import can_manage_club, club_admin_required, roles_required
from app.events import services
from app.events.validation import CAMPUS_TIMEZONE, event_input
from app.extensions import db
from app.management import get_record, my_student, page, query_text
from app.models import Club, ClubAdmin, Event, Registration, Student, User, Venue

events = Blueprint("events", __name__)


@events.errorhandler(services.RuleViolation)
def rule_failure(error):
    db.session.rollback()
    return render_template("errors/400.html", message=str(error)), error.code


@events.errorhandler(SQLAlchemyError)
def database_failure(error):
    db.session.rollback()
    code = getattr(getattr(error, "orig", None), "sqlstate", None)
    if isinstance(error, IntegrityError):
        message = ("The venue booking conflicts with another event. Choose a different time or venue."
                   if code == "23P01" else "This change conflicts with an existing record. Reload and try again.")
        status = 409
    elif code in {"40001", "40P01", "55P03"}:
        message, status = "Another request changed this record. Please reload and try again.", 409
    else:
        message, status = "Event services are temporarily unavailable. Please try again later.", 503
    return render_template("errors/400.html", message=message), status


@events.app_template_filter("campus_time")
def campus_time(value, pattern="%d %b %Y, %I:%M %p"):
    return services.utc(value).astimezone(CAMPUS_TIMEZONE).strftime(pattern)


def identifier_filter(name):
    raw = request.args.get(name, "")
    if not raw:
        return None
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or not 1 <= int(raw) <= 2147483647:
        abort(400, description="Choose a valid club or venue.")
    return int(raw)


def filtered_events(statement):
    q, status, when = query_text(), request.args.get("status", "all"), request.args.get("when", "upcoming")
    if status not in {"all", "scheduled", "completed", "cancelled"} or when not in {"all", "upcoming", "past"}:
        abort(400, description="Choose valid event status and date filters.")
    if q:
        statement = statement.where(or_(Event.title.icontains(q, autoescape=True), Event.description.icontains(q, autoescape=True)))
    if status != "all":
        statement = statement.where(Event.status == status)
    if when != "all":
        statement = statement.where(Event.start_time > services.now_utc() if when == "upcoming" else Event.start_time <= services.now_utc())
    for name in ("club_id", "venue_id"):
        value = identifier_filter(name)
        if value is not None:
            statement = statement.where(getattr(Event, name) == value)
    for name, operator in (("from_date", "from"), ("to_date", "to")):
        raw = request.args.get(name, "")
        if raw:
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                abort(400, description="Choose a valid event date filter.")
            boundary = datetime.combine(parsed, time.min if operator == "from" else time.max, CAMPUS_TIMEZONE)
            statement = statement.where(Event.start_time >= boundary if operator == "from" else Event.start_time <= boundary)
    return statement.order_by(Event.start_time, Event.event_id)


def directory(statement, heading="Campus events", manage=False):
    pagination = page(filtered_events(statement.options(joinedload(Event.club), joinedload(Event.venue))))
    ids = [event.event_id for event in pagination.items]
    counts = dict(db.session.execute(db.select(Registration.event_id, func.count()).where(
        Registration.event_id.in_(ids), Registration.status.in_(services.OCCUPIED)
    ).group_by(Registration.event_id)).all()) if ids else {}
    return render_template("events/directory.html", pagination=pagination, counts=counts, heading=heading, manage=manage,
                           managed_club_ids=db.session.scalars(db.select(ClubAdmin.club_id).where(ClubAdmin.user_id == current_user.user_id)).all() if manage and current_user.role == "club_admin" else [],
                           clubs=db.session.scalars(db.select(Club).order_by(Club.club_name)).all(),
                           venues=db.session.scalars(db.select(Venue).order_by(Venue.venue_name)).all())


@events.get("/events")
def index():
    return directory(db.select(Event))


@events.get("/events/manage")
@roles_required("club_admin", "system_admin")
def manage():
    statement = db.select(Event)
    if current_user.role == "club_admin":
        statement = statement.join(ClubAdmin, ClubAdmin.club_id == Event.club_id).where(ClubAdmin.user_id == current_user.user_id)
    return directory(statement, "Manage your events", manage=True)


@events.get("/clubs/<int:club_id>/events")
@club_admin_required
def club_events(club_id):
    club = get_record(Club, club_id)
    return directory(db.select(Event).where(Event.club_id == club_id), f"{club.club_name} events", manage=True)


@events.get("/events/<int:event_id>")
def detail(event_id):
    event = get_record(Event, event_id)
    registration = None
    if current_user.is_authenticated and current_user.role == "student" and current_user.student:
        registration = db.session.scalar(db.select(Registration).where(Registration.event_id == event_id, Registration.student_id == current_user.student.student_id))
    open_registration = event.status == "scheduled" and services.utc(event.start_time) > services.now_utc() and event.club.is_active
    return render_template("events/detail.html", event=event, registration=registration, occupied=services.seats_used(db.session, event_id),
                           open_registration=open_registration, may_manage=can_manage_club(current_user, event.club_id))


@events.route("/clubs/<int:club_id>/events/new", methods=["GET", "POST"])
@club_admin_required
def create(club_id):
    club = get_record(Club, club_id)
    return event_form(club)


@events.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@roles_required("club_admin", "system_admin")
def edit(event_id):
    event = get_record(Event, event_id)
    services.require_manager(db.session, current_user, event.club_id)
    return event_form(event.club, event)


def event_form(club, event=None):
    values = {}
    if event is not None:
        values = {name: getattr(event, name) for name in ("title", "description", "capacity", "venue_id")}
        values.update({name: campus_time(getattr(event, name), "%Y-%m-%dT%H:%M") for name in ("start_time", "end_time")})
    errors = {}
    if request.method == "POST":
        parsed, values, errors = event_input(request.form)
        if not errors:
            saved = services.save_event(db.session, current_user, parsed, event_id=event.event_id if event else None, club_id=club.club_id)
            db.session.commit()
            flash("Event saved.", "success")
            return redirect(url_for("events.detail", event_id=saved.event_id))
    return render_template("events/form.html", club=club, event=event, values=values, errors=errors,
                           venues=db.session.scalars(db.select(Venue).order_by(Venue.venue_name)).all()), (400 if errors else 200)


@events.post("/events/<int:event_id>/status")
@roles_required("club_admin", "system_admin")
def status(event_id):
    services.change_event_status(db.session, current_user, event_id, request.form.get("status"))
    db.session.commit()
    flash("Event status updated. Registration history has been preserved.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events.post("/events/<int:event_id>/register")
@roles_required("student")
def register(event_id):
    services.register_student(db.session, event_id, my_student().student_id)
    db.session.commit()
    flash("Your registration is confirmed.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events.post("/events/<int:event_id>/registration/cancel")
@roles_required("student")
def cancel(event_id):
    services.cancel_registration(db.session, event_id, my_student().student_id)
    db.session.commit()
    flash("Your registration is cancelled.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events.get("/registrations")
@roles_required("student")
def history():
    q, status = query_text(), request.args.get("status", "all")
    if status not in {"all", "registered", "cancelled", "attended"}:
        abort(400, description="Choose a valid registration status.")
    statement = db.select(Registration).join(Event).where(Registration.student_id == my_student().student_id).options(
        joinedload(Registration.event).joinedload(Event.club), joinedload(Registration.event).joinedload(Event.venue))
    if q:
        statement = statement.where(Event.title.icontains(q, autoescape=True))
    if status != "all":
        statement = statement.where(Registration.status == status)
    return render_template("events/history.html", pagination=page(statement.order_by(Event.start_time.desc(), Registration.registration_id)), q=q, status=status)


@events.get("/events/<int:event_id>/participants")
@roles_required("club_admin", "system_admin")
def participants(event_id):
    event = get_record(Event, event_id)
    services.require_manager(db.session, current_user, event.club_id)
    q, status = query_text(), request.args.get("status", "all")
    if status not in {"all", "registered", "cancelled", "attended"}:
        abort(400, description="Choose a valid registration status.")
    statement = db.select(Registration).join(Student).join(User).where(Registration.event_id == event_id).options(joinedload(Registration.student).joinedload(Student.user))
    if q:
        statement = statement.where(or_(User.full_name.icontains(q, autoescape=True), Student.student_number.icontains(q, autoescape=True)))
    if status != "all":
        statement = statement.where(Registration.status == status)
    return render_template("events/participants.html", event=event, pagination=page(statement.order_by(User.full_name, Registration.registration_id)),
                           q=q, status=status, attendance_open=services.utc(event.start_time) <= services.now_utc() and event.status != "cancelled")


@events.post("/events/<int:event_id>/participants/<int:registration_id>/status")
@roles_required("club_admin", "system_admin")
def participant_status(event_id, registration_id):
    services.mark_participant(db.session, current_user, event_id, registration_id, request.form.get("status"))
    db.session.commit()
    flash("Attendance updated.", "success")
    return redirect(url_for("events.participants", event_id=event_id))
