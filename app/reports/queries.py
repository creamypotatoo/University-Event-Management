"""Scoped aggregates. Aggregate child tables separately to prevent join fanout."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, extract, false, func, select

from app.events.services import now_utc
from app.events.validation import CAMPUS_TIMEZONE
from app.models import Club, ClubAdmin, Event, EventExpense, Registration

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Filters:
    from_date: date | None = None
    to_date: date | None = None
    club_id: int | None = None
    event_id: int | None = None


def club_scope(actor):
    statement = select(Club)
    if actor.role not in {"system_admin", "club_admin"}:
        statement = statement.where(false())
    elif actor.role == "club_admin":
        statement = statement.where(Club.club_id.in_(select(ClubAdmin.club_id).where(ClubAdmin.user_id == actor.user_id)))
    return statement


def event_scope(actor, filters):
    statement = select(Event).where(Event.club_id.in_(club_scope(actor).with_only_columns(Club.club_id)))
    if filters.club_id is not None:
        statement = statement.where(Event.club_id == filters.club_id)
    if filters.event_id is not None:
        statement = statement.where(Event.event_id == filters.event_id)
    return statement


def expense_conditions(filters):
    conditions = []
    if filters.from_date:
        conditions.append(EventExpense.expense_date >= filters.from_date)
    if filters.to_date:
        conditions.append(EventExpense.expense_date <= filters.to_date)
    return conditions


def dated_events(statement, filters):
    if filters.from_date:
        statement = statement.where(Event.start_time >= datetime.combine(filters.from_date, time.min, CAMPUS_TIMEZONE).astimezone(timezone.utc))
    if filters.to_date:
        # Half-open next-day boundary includes fractional seconds at the end date.
        statement = statement.where(Event.start_time < datetime.combine(filters.to_date + timedelta(days=1), time.min, CAMPUS_TIMEZONE).astimezone(timezone.utc))
    return statement


def percentage(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def finance_report(session, actor, filters):
    scope = event_scope(actor, filters).subquery()
    expenses = select(EventExpense.event_id, func.sum(EventExpense.amount).label("total"), func.count().label("entries")).where(
        *expense_conditions(filters)
    ).group_by(EventExpense.event_id).subquery()
    rollup = select(scope.c.event_id, scope.c.club_id, scope.c.title, Club.club_name,
                    func.coalesce(expenses.c.total, ZERO).label("total_expenses"),
                    func.coalesce(expenses.c.entries, 0).label("expense_count")).join(
        Club, Club.club_id == scope.c.club_id
    ).outerjoin(expenses, expenses.c.event_id == scope.c.event_id).subquery()
    events = [dict(row) for row in session.execute(select(rollup).order_by(rollup.c.title, rollup.c.event_id)).mappings()]
    clubs = club_scope(actor).subquery()
    statement = select(clubs.c.club_id, clubs.c.club_name, func.count(rollup.c.event_id).label("event_count"),
                       func.coalesce(func.sum(rollup.c.total_expenses), ZERO).label("total_expenses")).outerjoin(
        rollup, rollup.c.club_id == clubs.c.club_id
    )
    if filters.club_id:
        statement = statement.where(clubs.c.club_id == filters.club_id)
    if filters.event_id:
        statement = statement.where(clubs.c.club_id.in_(select(scope.c.club_id)))
    club_rows = [dict(row) for row in session.execute(statement.group_by(clubs.c.club_id, clubs.c.club_name).order_by(clubs.c.club_name)).mappings()]
    monthly = select(extract("year", EventExpense.expense_date).label("year"), extract("month", EventExpense.expense_date).label("month"),
                     func.sum(EventExpense.amount).label("total_expenses")).where(
        EventExpense.event_id.in_(select(scope.c.event_id)), *expense_conditions(filters)
    ).group_by(extract("year", EventExpense.expense_date), extract("month", EventExpense.expense_date)).order_by("year", "month")
    total = session.scalar(select(func.coalesce(func.sum(rollup.c.total_expenses), ZERO)))
    return {"events": events, "clubs": club_rows, "monthly": [dict(row) for row in session.execute(monthly).mappings()],
            "total": total, "highest": sorted(events, key=lambda r: (-r["total_expenses"], r["event_id"]))[:5]}


def analytics_report(session, actor, filters):
    scope = dated_events(event_scope(actor, filters), filters).subquery()
    registrations = select(Registration.event_id, func.count().label("total_registrations"),
        func.sum(case((Registration.status == "registered", 1), else_=0)).label("active_registrations"),
        func.sum(case((Registration.status == "attended", 1), else_=0)).label("attended"),
        func.sum(case((Registration.status == "cancelled", 1), else_=0)).label("cancelled_registrations")
    ).group_by(Registration.event_id).subquery()
    rollup = select(scope.c.event_id, scope.c.club_id, scope.c.title, scope.c.status, scope.c.start_time, scope.c.capacity, Club.club_name,
                    *[func.coalesce(registrations.c[name], 0).label(name) for name in ("total_registrations", "active_registrations", "attended", "cancelled_registrations")]
    ).join(Club, Club.club_id == scope.c.club_id).outerjoin(registrations, registrations.c.event_id == scope.c.event_id).subquery()
    rows = [dict(row) for row in session.execute(select(rollup).order_by(rollup.c.start_time, rollup.c.event_id)).mappings()]
    for row in rows:
        row["occupied"] = row["active_registrations"] + row["attended"]
        row["occupancy_pct"] = percentage(row["occupied"], row["capacity"])
        row["attendance_rate"] = percentage(row["attended"], row["occupied"]) if row["status"] == "completed" else None
    now = now_utc()
    summary = dict(session.execute(select(
        func.count().label("total_events"),
        func.coalesce(func.sum(case(((rollup.c.status == "scheduled") & (rollup.c.start_time > now), 1), else_=0)), 0).label("upcoming_events"),
        *[func.coalesce(func.sum(case((rollup.c.status == status, 1), else_=0)), 0).label(status + "_events") for status in ("completed", "cancelled")],
        *[func.coalesce(func.sum(rollup.c[name]), 0).label(name) for name in ("total_registrations", "active_registrations", "attended", "cancelled_registrations")],
        func.coalesce(func.sum(case((rollup.c.status == "completed", rollup.c.attended), else_=0)), 0).label("completed_attended"),
        func.coalesce(func.sum(case((rollup.c.status == "completed", rollup.c.active_registrations + rollup.c.attended), else_=0)), 0).label("completed_occupied")
    )).mappings().one())
    summary["attendance_rate"] = percentage(summary["completed_attended"], summary["completed_occupied"])
    clubs = club_scope(actor).subquery()
    club_query = select(clubs.c.club_id, clubs.c.club_name, func.count(rollup.c.event_id).label("event_count"),
        func.coalesce(func.sum(rollup.c.total_registrations), 0).label("total_registrations"),
        func.coalesce(func.sum(rollup.c.active_registrations + rollup.c.attended), 0).label("occupied"),
        func.coalesce(func.sum(rollup.c.attended), 0).label("attended")
    ).outerjoin(rollup, rollup.c.club_id == clubs.c.club_id)
    if filters.club_id: club_query = club_query.where(clubs.c.club_id == filters.club_id)
    if filters.event_id: club_query = club_query.where(clubs.c.club_id.in_(select(scope.c.club_id)))
    local_time = func.timezone("Asia/Dhaka", rollup.c.start_time) if session.get_bind().dialect.name == "postgresql" else func.datetime(rollup.c.start_time, "+6 hours")
    year, month = extract("year", local_time), extract("month", local_time)
    monthly = session.execute(select(year.label("year"), month.label("month"), func.count().label("event_count")).group_by(year, month).order_by(year, month)).mappings().all()
    return {"events": rows, "summary": summary, "clubs": [dict(row) for row in session.execute(club_query.group_by(clubs.c.club_id, clubs.c.club_name).order_by(clubs.c.club_name)).mappings()],
            "monthly": [dict(row) for row in monthly], "popular": sorted(rows, key=lambda r: (-r["total_registrations"], r["event_id"]))[:5]}


def personal_summary(session, student_id):
    now = now_utc()
    return dict(session.execute(select(func.count().label("total"),
        func.coalesce(func.sum(case(((Event.status == "scheduled") & (Event.start_time > now) & (Registration.status == "registered"), 1), else_=0)), 0).label("upcoming"),
        func.coalesce(func.sum(case((Registration.status == "registered", 1), else_=0)), 0).label("registered"),
        func.coalesce(func.sum(case((Registration.status == "attended", 1), else_=0)), 0).label("attended"),
        func.coalesce(func.sum(case((Registration.status == "cancelled", 1), else_=0)), 0).label("cancelled"),
        func.coalesce(func.sum(case(((Event.start_time <= now) & (Event.status != "cancelled") & Registration.status.in_(("registered", "attended")), 1), else_=0)), 0).label("past")
    ).select_from(Registration).join(Event).where(Registration.student_id == student_id)).mappings().one())
