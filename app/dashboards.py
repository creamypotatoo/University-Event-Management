"""Role landing pages linking to authorized management workflows."""

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.auth.authorization import club_admin_required, roles_required
from app.extensions import db
from app.models import Club, ClubAdmin, Event, Registration

dashboards = Blueprint("dashboards", __name__)


@dashboards.get("/dashboard")
@login_required
def index():
    endpoints = {"student": "dashboards.student", "club_admin": "dashboards.club_admin", "system_admin": "dashboards.system_admin"}
    endpoint = endpoints.get(current_user.role)
    if endpoint is None:
        abort(403)
    return redirect(url_for(endpoint))


@dashboards.get("/dashboard/student")
@roles_required("student")
def student():
    if current_user.student is None:
        abort(403)
    from app.events.services import now_utc
    from sqlalchemy.orm import joinedload
    registrations = db.session.scalars(db.select(Registration).join(Event).where(
        Registration.student_id == current_user.student.student_id, Registration.status == "registered",
        Event.status == "scheduled", Event.start_time > now_utc()
    ).options(joinedload(Registration.event)).order_by(Event.start_time, Event.event_id).limit(5)).all()
    from app.reports.queries import personal_summary
    return render_template("dashboards/student.html", upcoming_registrations=registrations, personal=personal_summary(db.session, current_user.student.student_id))


@dashboards.get("/dashboard/club-admin")
@roles_required("club_admin")
def club_admin():
    clubs = db.session.scalars(db.select(Club).join(ClubAdmin).where(ClubAdmin.user_id == current_user.user_id).order_by(Club.club_name)).all()
    return render_template("dashboards/club_admin.html", clubs=clubs, **report_summary())


@dashboards.get("/dashboard/system-admin")
@roles_required("system_admin")
def system_admin():
    return render_template("dashboards/system_admin.html", **report_summary())


def report_summary():
    from app.reports.queries import Filters, analytics_report, finance_report
    return {"analytics": analytics_report(db.session, current_user, Filters()),
            "finance": finance_report(db.session, current_user, Filters())}


@dashboards.get("/clubs/<int:club_id>/dashboard")
@club_admin_required
def club_scope(club_id):
    club = db.session.get(Club, club_id)
    if club is None:
        abort(404)
    return render_template("dashboards/club_scope.html", club=club)
