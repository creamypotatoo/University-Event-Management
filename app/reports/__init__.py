"""Private expense management and scoped reports, with matching HTML/CSV filters."""

from datetime import date, datetime
from decimal import Decimal
from math import ceil
from types import SimpleNamespace

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.auth.authorization import can_manage_club, roles_required
from app.events.validation import CAMPUS_TIMEZONE
from app.extensions import db
from app.management import get_record, page, query_text
from app.models import Club, Event, EventExpense
from app.reports.csv_export import csv_response
from app.reports.queries import Filters, analytics_report, club_scope, event_scope, expense_conditions, finance_report
from app.reports.validation import expense_input

reports = Blueprint("reports", __name__)


@reports.errorhandler(SQLAlchemyError)
def database_error(error):
    db.session.rollback()
    return render_template("errors/400.html", message="Financial/report services are temporarily unavailable. No partial changes were saved."), 503


@reports.app_template_filter("money")
def money(value):
    return f"{value if value is not None else Decimal('0.00'):,.2f}"


def manager_event(event_id):
    event = get_record(Event, event_id)
    if not can_manage_club(current_user, event.club_id):
        abort(403)
    return event


def report_filters():
    values = {}
    for name in ("from_date", "to_date"):
        raw = request.args.get(name, "")
        if not raw:
            values[name] = None
        else:
            try:
                parsed = date.fromisoformat(raw)
                if parsed.isoformat() != raw or parsed.year == 9999:
                    raise ValueError
                values[name] = parsed
            except ValueError:
                abort(400, description="Choose valid ISO dates (YYYY-MM-DD, before year 9999).")
    if values["from_date"] and values["to_date"] and values["from_date"] > values["to_date"]:
        abort(400, description="The end date cannot precede the start date.")
    for name in ("club_id", "event_id"):
        raw = request.args.get(name, "")
        if raw and (not raw.isascii() or not raw.isdigit() or len(raw) > 10 or not 1 <= int(raw) <= 2147483647):
            abort(400, description="Choose a valid club and event.")
        values[name] = int(raw) if raw else None
    if values["club_id"]:
        allowed = db.session.scalar(club_scope(current_user).where(Club.club_id == values["club_id"]))
        if allowed is None:
            abort(404 if current_user.role == "system_admin" else 403)
    if values["event_id"]:
        event = manager_event(values["event_id"])
        if values["club_id"] and values["club_id"] != event.club_id:
            abort(400, description="The selected event does not belong to the selected club.")
    return Filters(**values)


def choices():
    return {"clubs": db.session.scalars(club_scope(current_user).order_by(Club.club_name)).all(),
            "events": db.session.scalars(event_scope(current_user, Filters()).order_by(Event.title, Event.event_id)).all()}


def paginate_rows(rows):
    raw = request.args.get("page", "1")
    if not raw.isascii() or not raw.isdigit() or len(raw) > 6 or not 1 <= int(raw) <= 100000:
        abort(400, description="Choose a valid page number.")
    number, pages = int(raw), ceil(len(rows) / 10)
    return SimpleNamespace(items=rows[(number - 1) * 10:number * 10], page=number, pages=pages, total=len(rows),
                           has_prev=number > 1, has_next=number < pages, prev_num=number - 1, next_num=number + 1)


@reports.get("/events/<int:event_id>/expenses")
@roles_required("club_admin", "system_admin")
def expenses(event_id):
    event = manager_event(event_id)
    filters = report_filters()
    if filters.event_id and filters.event_id != event_id or filters.club_id and filters.club_id != event.club_id:
        abort(400, description="Expense filters must match this event.")
    q = query_text()
    statement = db.select(EventExpense).where(EventExpense.event_id == event_id, *expense_conditions(filters))
    if q:
        statement = statement.where(EventExpense.description.icontains(q, autoescape=True))
    totals = statement.subquery()
    total = db.session.scalar(db.select(func.coalesce(func.sum(totals.c.amount), Decimal("0.00"))))
    return render_template("reports/expenses.html", event=event, pagination=page(statement.order_by(EventExpense.expense_date.desc(), EventExpense.expense_id)), total=total, q=q)


@reports.route("/events/<int:event_id>/expenses/new", methods=["GET", "POST"])
@roles_required("club_admin", "system_admin")
def expense_create(event_id):
    return expense_form(manager_event(event_id))


def scoped_expense(event_id, expense_id, lock=False):
    statement = db.select(EventExpense).where(EventExpense.event_id == event_id, EventExpense.expense_id == expense_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    expense = db.session.scalar(statement)
    if expense is None:
        abort(404)
    return expense


@reports.route("/events/<int:event_id>/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
@roles_required("club_admin", "system_admin")
def expense_edit(event_id, expense_id):
    event = manager_event(event_id)
    return expense_form(event, scoped_expense(event_id, expense_id, request.method == "POST"))


def expense_form(event, expense=None):
    values = {"description": expense.description, "amount": format(expense.amount, ".2f"), "expense_date": expense.expense_date.isoformat()} if expense else {"expense_date": datetime.now(CAMPUS_TIMEZONE).date().isoformat()}
    errors = {}
    if request.method == "POST":
        parsed, values, errors = expense_input(request.form)
        if not errors:
            record = expense or EventExpense(event_id=event.event_id)
            for name in ("description", "amount", "expense_date"):
                setattr(record, name, parsed[name])
            db.session.add(record)
            db.session.commit()
            flash("Expense saved.", "success")
            return redirect(url_for("reports.expenses", event_id=event.event_id))
    return render_template("reports/expense_form.html", event=event, expense=expense, values=values, errors=errors), (400 if errors else 200)


@reports.route("/events/<int:event_id>/expenses/<int:expense_id>/delete", methods=["GET", "POST"])
@roles_required("club_admin", "system_admin")
def expense_delete(event_id, expense_id):
    event = manager_event(event_id)
    expense = scoped_expense(event_id, expense_id, request.method == "POST")
    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400, description="Confirm deletion using the confirmation form.")
        db.session.delete(expense)
        db.session.commit()
        flash("Expense deleted. The event and its other records were preserved.", "success")
        return redirect(url_for("reports.expenses", event_id=event_id))
    return render_template("reports/expense_delete.html", event=event, expense=expense)


@reports.get("/reports/financial")
@roles_required("club_admin", "system_admin")
def financial():
    data = finance_report(db.session, current_user, report_filters())
    return render_template("reports/financial.html", data=data, pagination=paginate_rows(data["events"]), **choices())


@reports.get("/reports/analytics")
@roles_required("club_admin", "system_admin")
def analytics():
    data = analytics_report(db.session, current_user, report_filters())
    return render_template("reports/analytics.html", data=data, pagination=paginate_rows(data["events"]), **choices())


@reports.get("/reports/financial.csv")
@roles_required("club_admin", "system_admin")
def financial_csv():
    data = finance_report(db.session, current_user, report_filters())
    return csv_response("event-expenses.csv", ["event_id", "event_title", "club_id", "club_name", "expense_count", "total_expenses_bdt"],
                        ((r["event_id"], r["title"], r["club_id"], r["club_name"], r["expense_count"], r["total_expenses"]) for r in data["events"]))


@reports.get("/reports/participation.csv")
@roles_required("club_admin", "system_admin")
def participation_csv():
    data = analytics_report(db.session, current_user, report_filters())
    columns = ["event_id", "title", "club_id", "club_name", "status", "capacity", "total_registrations", "active_registrations", "attended", "cancelled_registrations", "occupied", "occupancy_pct", "attendance_rate"]
    return csv_response("event-participation.csv", columns, ([r[name] for name in columns] for r in data["events"]))
