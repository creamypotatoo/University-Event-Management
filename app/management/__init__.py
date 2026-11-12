"""Phase 4 student, club, membership, and venue routes."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.auth.authorization import can_manage_club, club_admin_required, roles_required
from app.extensions import db
from app.management.services import student_membership, transition_membership
from app.management.validation import CLUB_FIELDS, PROFILE_FIELDS, VENUE_FIELDS, text_fields, venue_input
from app.models import Club, ClubMembership, Event, Student, User, Venue

management = Blueprint("management", __name__)


def save_changes():
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return "Those details conflict with an existing record. Names must be unique."
    except SQLAlchemyError:
        db.session.rollback()
        abort(503, description="Changes could not be saved. Please try again later.")
    return None


def get_record(model, identifier, lock=False):
    statement = db.select(model).where(model.__mapper__.primary_key[0] == identifier)
    if lock:
        statement = statement.with_for_update()
    record = db.session.scalar(statement)
    if record is None:
        abort(404)
    return record


def my_student():
    student = current_user.student
    if student is None:
        abort(403)
    return student


def query_text(name="q", maximum=150):
    value = request.args.get(name, "").strip()
    if len(value) > maximum or any(not c.isprintable() for c in value):
        abort(400, description="Search values are too long or contain invalid characters.")
    return value


def page(statement):
    number = request.args.get("page", "1")
    if not number.isascii() or not number.isdigit() or len(number) > 6 or not 1 <= int(number) <= 100000:
        abort(400, description="Choose a valid page number.")
    return db.paginate(statement, page=int(number), per_page=10, max_per_page=10, error_out=False)


@management.app_template_global()
def page_url(number):
    arguments = {name: request.args[name] for name in ("q", "status", "department") if name in request.args}
    arguments.update(request.view_args or {})
    arguments["page"] = number
    return url_for(request.endpoint, **arguments)


@management.get("/profile")
@roles_required("student")
def profile():
    return render_template("management/profile.html", student=my_student())


@management.route("/profile/edit", methods=["GET", "POST"])
@roles_required("student")
def profile_edit():
    student = my_student()
    values = {"full_name": current_user.full_name, "department": student.department, "batch": student.batch}
    errors = {}
    if request.method == "POST":
        values, errors = text_fields(request.form, PROFILE_FIELDS)
        if not errors:
            current_user.full_name = values["full_name"]
            student.department, student.batch = values["department"], values["batch"]
            error = save_changes()
            if not error:
                flash("Your profile has been updated.", "success")
                return redirect(url_for("management.profile"))
            errors["form"] = error
    return render_template("management/edit.html", heading="Edit your student profile", fields=PROFILE_FIELDS,
                           values=values, errors=errors, back=url_for("management.profile")), (400 if errors else 200)


@management.get("/students")
@roles_required("system_admin")
def students():
    q, department = query_text(), query_text("department", 100)
    statement = db.select(Student).join(User).options(joinedload(Student.user))
    if q:
        statement = statement.where(or_(User.full_name.icontains(q, autoescape=True), User.email.icontains(q, autoescape=True), Student.student_number.icontains(q, autoescape=True)))
    if department:
        statement = statement.where(Student.department == department)
    return render_template("management/students.html", pagination=page(statement.order_by(User.full_name, Student.student_id)), q=q, department=department)


@management.get("/students/<int:student_id>")
@roles_required("student", "system_admin")
def student_detail(student_id):
    if current_user.role == "student" and my_student().student_id != student_id:
        abort(403)
    return render_template("management/profile.html", student=get_record(Student, student_id))


@management.get("/clubs")
def clubs():
    q, status = query_text(), request.args.get("status", "active")
    if status not in {"active", "inactive", "all"}:
        abort(400, description="Choose a valid club status.")
    statement = db.select(Club)
    if q:
        statement = statement.where(or_(Club.club_name.icontains(q, autoescape=True), Club.description.icontains(q, autoescape=True)))
    if status != "all":
        statement = statement.where(Club.is_active == (status == "active"))
    return render_template("management/clubs.html", pagination=page(statement.order_by(Club.club_name, Club.club_id)), q=q, status=status)


@management.get("/clubs/<int:club_id>")
def club_detail(club_id):
    club = get_record(Club, club_id)
    membership = None
    if current_user.is_authenticated and current_user.role == "student" and current_user.student:
        membership = db.session.scalar(db.select(ClubMembership).where(ClubMembership.club_id == club_id, ClubMembership.student_id == current_user.student.student_id))
    return render_template("management/club_detail.html", club=club, membership=membership,
                           may_manage=can_manage_club(current_user, club_id))


@management.route("/clubs/new", methods=["GET", "POST"])
@roles_required("system_admin")
def club_create():
    return club_form()


@management.route("/clubs/<int:club_id>/edit", methods=["GET", "POST"])
@club_admin_required
def club_edit(club_id):
    return club_form(get_record(Club, club_id, lock=request.method == "POST"))


def club_form(club=None):
    values = {name: getattr(club, name, "") for name, label, maximum in CLUB_FIELDS}
    errors = {}
    if request.method == "POST":
        values, errors = text_fields(request.form, CLUB_FIELDS)
        if not errors:
            record = club or Club()
            record.club_name, record.description = values["club_name"], values["description"]
            db.session.add(record)
            error = save_changes()
            if not error:
                flash("Club saved.", "success")
                return redirect(url_for("management.club_detail", club_id=record.club_id))
            errors["form"] = error
    return render_template("management/edit.html", heading="Edit club" if club else "Create club", fields=CLUB_FIELDS,
                           values=values, errors=errors, back=url_for("management.clubs")), (400 if errors else 200)


@management.post("/clubs/<int:club_id>/status")
@roles_required("system_admin")
def club_status(club_id):
    target = request.form.get("status")
    if target not in {"active", "inactive"}:
        abort(400, description="Choose active or inactive club status.")
    club = get_record(Club, club_id, lock=True)
    club.is_active = target == "active"
    if save_changes():
        abort(409, description="The club status could not be saved.")
    flash("Club status updated. Existing records have been preserved.", "success")
    return redirect(url_for("management.club_detail", club_id=club_id))


@management.post("/clubs/<int:club_id>/join")
@roles_required("student")
def join_club(club_id):
    return change_my_membership(club_id, "active")


@management.post("/clubs/<int:club_id>/leave")
@roles_required("student")
def leave_club(club_id):
    return change_my_membership(club_id, "cancelled")


def change_my_membership(club_id, target):
    club = get_record(Club, club_id, lock=True)
    student_membership(club, my_student(), target)
    if save_changes():
        abort(409, description="Your membership could not be saved. Please reload and try again.")
    flash("You have joined the club." if target == "active" else "Your membership is cancelled.", "success")
    return redirect(url_for("management.club_detail", club_id=club_id))


@management.get("/memberships")
@roles_required("student")
def memberships():
    q, status = query_text(), request.args.get("status", "all")
    if status not in {"active", "cancelled", "all"}:
        abort(400, description="Choose a valid membership status.")
    statement = db.select(ClubMembership).join(Club).where(ClubMembership.student_id == my_student().student_id).options(joinedload(ClubMembership.club))
    if q:
        statement = statement.where(Club.club_name.icontains(q, autoescape=True))
    if status != "all":
        statement = statement.where(ClubMembership.status == status)
    return render_template("management/memberships.html", pagination=page(statement.order_by(ClubMembership.joined_at.desc(), ClubMembership.membership_id)), q=q, status=status)


@management.get("/clubs/<int:club_id>/members")
@club_admin_required
def club_members(club_id):
    club = get_record(Club, club_id)
    q, status = query_text(), request.args.get("status", "active")
    if status not in {"active", "cancelled", "all"}:
        abort(400, description="Choose a valid membership status.")
    statement = db.select(ClubMembership).join(Student).join(User).where(ClubMembership.club_id == club_id).options(joinedload(ClubMembership.student).joinedload(Student.user))
    if q:
        statement = statement.where(or_(User.full_name.icontains(q, autoescape=True), Student.student_number.icontains(q, autoescape=True)))
    if status != "all":
        statement = statement.where(ClubMembership.status == status)
    return render_template("management/members.html", club=club, pagination=page(statement.order_by(User.full_name, ClubMembership.membership_id)), q=q, status=status)


@management.post("/clubs/<int:club_id>/members/<int:membership_id>/status")
@club_admin_required
def member_status(club_id, membership_id):
    club = get_record(Club, club_id, lock=True)
    membership = db.session.scalar(db.select(ClubMembership).where(ClubMembership.club_id == club_id, ClubMembership.membership_id == membership_id).with_for_update())
    if membership is None:
        abort(404)
    transition_membership(membership, club, request.form.get("status"))
    if save_changes():
        abort(409, description="The membership could not be saved.")
    flash("Membership updated.", "success")
    return redirect(url_for("management.club_members", club_id=club_id, status="all"))


@management.get("/venues")
def venues():
    q = query_text()
    statement = db.select(Venue)
    if q:
        statement = statement.where(or_(Venue.venue_name.icontains(q, autoescape=True), Venue.location.icontains(q, autoescape=True)))
    return render_template("management/venues.html", pagination=page(statement.order_by(Venue.venue_name, Venue.venue_id)), q=q)


@management.route("/venues/new", methods=["GET", "POST"])
@roles_required("system_admin")
def venue_create():
    return venue_form()


@management.route("/venues/<int:venue_id>/edit", methods=["GET", "POST"])
@roles_required("system_admin")
def venue_edit(venue_id):
    return venue_form(get_record(Venue, venue_id, lock=request.method == "POST"))


def venue_form(venue=None):
    values = {name: getattr(venue, name, "") for name, label, maximum in VENUE_FIELDS}
    errors = {}
    if request.method == "POST":
        values, errors = venue_input(request.form)
        if not errors and venue is not None:
            too_large = db.session.scalar(db.select(Event.event_id).where(Event.venue_id == venue.venue_id, Event.status != "cancelled", Event.capacity > int(values["capacity"])).limit(1))
            if too_large is not None:
                errors["capacity"] = "Capacity cannot be below the capacity of an existing non-cancelled event."
        if not errors:
            record = venue or Venue()
            record.venue_name, record.location, record.capacity = values["venue_name"], values["location"], int(values["capacity"])
            db.session.add(record)
            error = save_changes()
            if not error:
                flash("Venue saved. Existing event relationships have been preserved.", "success")
                return redirect(url_for("management.venues"))
            errors["form"] = error
    return render_template("management/edit.html", heading="Edit venue" if venue else "Create venue", fields=VENUE_FIELDS,
                           values=values, errors=errors, back=url_for("management.venues")), (400 if errors else 200)
