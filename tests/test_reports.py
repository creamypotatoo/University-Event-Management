import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.models import Club, Event, EventExpense, Registration, Student, User, Venue
from app.reports.csv_export import safe_cell
from app.reports.queries import Filters, analytics_report, finance_report, personal_summary
from app.reports.validation import expense_input
from tests.helpers import TEST_HASH, login, token


def post(browser, path, **values):
    return browser.post(path, data={"csrf_token": token(browser, "/"), **values})


@pytest.fixture
def report_data(model_session, accounts):
    tag = uuid4().hex
    venue = Venue(venue_name=tag, location="Report fixture", capacity=10)
    past = datetime(2020, 1, 1, 4, tzinfo=timezone.utc)
    events = [Event(club_id=accounts["assigned"], venue=venue, title="Completed " + tag, description="Report fixture", start_time=past, end_time=past + timedelta(hours=1), capacity=4, status="completed"),
              Event(club_id=accounts["assigned"], venue=venue, title="Future " + tag, description="Report fixture", start_time=datetime(2045, 1, 1, 4, tzinfo=timezone.utc), end_time=datetime(2045, 1, 1, 5, tzinfo=timezone.utc), capacity=5, status="scheduled"),
              Event(club_id=accounts["other"], venue=venue, title="Secret " + tag, description="Report fixture", start_time=past + timedelta(days=1), end_time=past + timedelta(days=1, hours=1), capacity=10, status="completed")]
    model_session.add_all(events)
    model_session.flush()
    expenses = [EventExpense(event=events[0], description="Printing", amount=Decimal("10.10"), expense_date=date(2026, 1, 10)),
                EventExpense(event=events[0], description="Materials", amount=Decimal("20.20"), expense_date=date(2026, 2, 10)),
                EventExpense(event=events[2], description="Private other club expense", amount=Decimal("99.99"), expense_date=date(2026, 1, 10))]
    model_session.add_all(expenses)
    own = model_session.scalar(select(Student).where(Student.user_id == accounts["student"]["id"]))
    students = [own]
    for index in range(2):
        students.append(Student(user=User(full_name=f"Fixture {index}", email=f"{uuid4().hex}@example.edu", password_hash=TEST_HASH, role="student"), student_number=uuid4().hex, department="Science", batch="2026"))
    model_session.add_all(students)
    model_session.flush()
    model_session.add_all([Registration(event=events[0], student=students[0], status="attended"),
                           Registration(event=events[0], student=students[1], status="registered"),
                           Registration(event=events[0], student=students[2], status="cancelled"),
                           Registration(event=events[1], student=students[0], status="registered")])
    model_session.commit()
    return {"events": [e.event_id for e in events], "expenses": [e.expense_id for e in expenses], "titles": [e.title for e in events], "student": own.student_id}


def actor(session, accounts, role="club_admin"):
    return session.get(User, accounts[role]["id"])


def test_expense_create_edit_delete_confirmation(browser, model_session, accounts, report_data):
    login(browser, accounts["club_admin"]["email"])
    event_id = report_data["events"][0]
    base = f"/events/{event_id}/expenses"
    assert browser.get(base).status_code == 200
    assert browser.get(base + "/new").status_code == 200
    assert post(browser, base + "/new", description="New expense", amount="0.10", expense_date="2026-03-01", event_id=report_data["events"][2]).status_code == 302
    expense = model_session.scalar(select(EventExpense).where(EventExpense.description == "New expense"))
    identifier = expense.expense_id
    assert expense.event_id == event_id and expense.amount == Decimal("0.10")
    assert browser.get(base + f"/{identifier}/edit").status_code == 200
    assert post(browser, base + f"/{identifier}/edit", description="Updated", amount="0.20", expense_date="2026-03-02", event_id=report_data["events"][2]).status_code == 302
    assert model_session.get(EventExpense, identifier).amount == Decimal("0.20")
    assert browser.get(base + f"/{identifier}/delete").status_code == 200
    assert model_session.get(EventExpense, identifier) is not None
    assert post(browser, base + f"/{identifier}/delete").status_code == 400
    assert post(browser, base + f"/{identifier}/delete", confirm="delete").status_code == 302
    assert model_session.get(EventExpense, identifier) is None
    assert model_session.get(Event, event_id) is not None


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity", "1.001", "10000000000", "1e2", "1,000.00", "", "١٢"])
def test_invalid_money(browser, accounts, report_data, amount):
    login(browser, accounts["club_admin"]["email"])
    assert post(browser, f"/events/{report_data['events'][0]}/expenses/new", description="Test", amount=amount, expense_date="2026-01-01").status_code == 400


def test_financial_exact_aggregation_no_registration_fanout(model_session, accounts, report_data):
    data = finance_report(model_session, actor(model_session, accounts), Filters())
    assert data["total"] == Decimal("30.30")
    assert isinstance(data["total"], Decimal)
    assert len(data["events"]) == 2
    totals = {row["event_id"]: row["total_expenses"] for row in data["events"]}
    assert totals[report_data["events"][0]] == Decimal("30.30")
    assert totals[report_data["events"][1]] == Decimal("0.00")
    assert data["clubs"][0]["event_count"] == 2
    assert data["highest"][0]["event_id"] == report_data["events"][0]
    assert [row["total_expenses"] for row in data["monthly"]] == [Decimal("10.10"), Decimal("20.20")]
    all_data = finance_report(model_session, actor(model_session, accounts, "system_admin"), Filters())
    assert all_data["total"] == Decimal("130.29")


def test_finance_expense_date_filter_and_empty_club(model_session, accounts, report_data):
    admin = actor(model_session, accounts, "system_admin")
    empty = Club(club_name=uuid4().hex, description="Empty club")
    model_session.add(empty)
    model_session.flush()
    empty_id = empty.club_id
    filtered = finance_report(model_session, admin, Filters(from_date=date(2026, 1, 1), to_date=date(2026, 1, 31), club_id=accounts["assigned"]))
    assert filtered["total"] == Decimal("10.10")
    empty_data = finance_report(model_session, admin, Filters(club_id=empty_id))
    assert empty_data["total"] == Decimal("0.00") and empty_data["clubs"][0]["event_count"] == 0
    assert empty_data["clubs"][0]["total_expenses"] == Decimal("0.00")


def test_analytics_formulas_scope_and_personal_summary(model_session, accounts, report_data):
    data = analytics_report(model_session, actor(model_session, accounts), Filters())
    summary = data["summary"]
    assert summary["total_events"] == 2 and summary["upcoming_events"] == 1
    assert summary["total_registrations"] == 4 and summary["active_registrations"] == 2
    assert summary["attended"] == 1 and summary["cancelled_registrations"] == 1
    assert summary["attendance_rate"] == Decimal("50.0")
    rows = {row["event_id"]: row for row in data["events"]}
    assert rows[report_data["events"][0]]["occupancy_pct"] == Decimal("50.0")
    assert rows[report_data["events"][1]]["attendance_rate"] is None
    assert data["clubs"][0]["occupied"] == 3
    assert data["popular"][0]["total_registrations"] == 3
    personal = personal_summary(model_session, report_data["student"])
    assert personal["total"] == 2 and personal["attended"] == 1 and personal["upcoming"] == 1


def test_analytics_date_boundary_campus_months(model_session, accounts, report_data):
    event = model_session.get(Event, report_data["events"][0])
    event.start_time = datetime(2019, 12, 31, 20, tzinfo=timezone.utc)  # Jan 1 in Dhaka.
    event.end_time = event.start_time + timedelta(hours=1)
    model_session.flush()
    data = analytics_report(model_session, actor(model_session, accounts), Filters(from_date=date(2020, 1, 1), to_date=date(2020, 1, 1)))
    assert data["summary"]["total_events"] == 1
    assert int(data["monthly"][0]["year"]) == 2020 and int(data["monthly"][0]["month"]) == 1


@pytest.mark.parametrize("route", ["/reports/financial", "/reports/analytics", "/reports/financial.csv", "/reports/participation.csv"])
def test_reports_scope_html_csv_and_students_forbidden(browser, accounts, report_data, route):
    login(browser, accounts["club_admin"]["email"])
    response = browser.get(route)
    assert response.status_code == 200
    assert report_data["titles"][2].encode() not in response.data
    assert browser.get(route, query_string={"club_id": accounts["other"]}).status_code == 403
    assert browser.get(route, query_string={"event_id": report_data["events"][2]}).status_code == 403
    assert post(browser, "/auth/logout").status_code == 302
    login(browser, accounts["student"]["email"])
    assert browser.get(route).status_code == 403
    assert b"Financial reports" not in browser.get("/dashboard/student").data


def test_expense_scope_nonexistent_and_student_denial(browser, accounts, report_data):
    login(browser, accounts["club_admin"]["email"])
    own, other = report_data["events"][0], report_data["events"][2]
    assert browser.get(f"/events/{other}/expenses").status_code == 403
    assert post(browser, f"/events/{other}/expenses/new", description="Bad", amount="1", expense_date="2026-01-01").status_code == 403
    assert browser.get(f"/events/{own}/expenses/{report_data['expenses'][2]}/edit").status_code == 404
    assert post(browser, f"/events/{own}/expenses/{report_data['expenses'][2]}/delete", confirm="delete").status_code == 404
    assert browser.get("/events/2147483647/expenses").status_code == 404
    post(browser, "/auth/logout")
    login(browser, accounts["student"]["email"])
    assert browser.get(f"/events/{own}/expenses").status_code == 403
    assert post(browser, f"/events/{own}/expenses/{report_data['expenses'][0]}/edit", description="Bad", amount="1", expense_date="2026-01-01").status_code == 403


def test_csv_utf8_quote_injection_and_filters(browser, accounts, report_data, model_session):
    event = model_session.get(Event, report_data["events"][0])
    event.title = '=HYPERLINK("evil"), বাংলা'
    event.club.club_name = " +SUM(1,2)"
    model_session.commit()
    login(browser, accounts["club_admin"]["email"])
    params = {"event_id": report_data["events"][0], "from_date": "2026-01-01", "to_date": "2026-01-31"}
    response = browser.get("/reports/financial.csv", query_string=params)
    assert response.status_code == 200 and response.content_type == "text/csv; charset=utf-8"
    assert "attachment;" in response.headers["Content-Disposition"]
    rows = list(csv.DictReader(StringIO(response.data.decode("utf-8"))))
    assert len(rows) == 1 and rows[0]["total_expenses_bdt"] == "10.10"
    assert rows[0]["event_title"].startswith("'=") and rows[0]["club_name"].startswith("' +")
    html = browser.get("/reports/financial", query_string=params)
    assert b"10.10" in html.data and b"20.20" not in html.data


@pytest.mark.parametrize("params", [{"from_date": "bad"}, {"from_date": "2026-02-01", "to_date": "2026-01-01"}, {"club_id": "abc"}, {"to_date": "9999-12-31"}])
def test_invalid_report_filters(browser, accounts, params):
    login(browser, accounts["system_admin"]["email"])
    assert browser.get("/reports/financial", query_string=params).status_code == 400
    assert browser.get("/reports/participation.csv", query_string=params).status_code == 400


@pytest.mark.parametrize("path", ["/events/1/expenses/new", "/events/1/expenses/1/edit", "/events/1/expenses/1/delete"])
def test_expense_csrf(browser, path):
    assert browser.post(path, data={}).status_code == 400


def test_finance_database_failure_safe(browser, accounts):
    login(browser, accounts["system_admin"]["email"])
    with patch("app.reports.finance_report", side_effect=OperationalError("private", {}, Exception("private"))):
        response = browser.get("/reports/financial")
    assert response.status_code == 503 and b"private" not in response.data


def test_empty_analytics_and_finance(browser, model_session, accounts):
    manager = actor(model_session, accounts)
    data = analytics_report(model_session, manager, Filters())
    assert data["summary"]["total_events"] == 0 and data["summary"]["attendance_rate"] is None
    assert data["clubs"][0]["event_count"] == 0 and data["monthly"] == []
    assert finance_report(model_session, manager, Filters())["total"] == Decimal("0.00")
    login(browser, accounts["club_admin"]["email"])
    assert browser.get("/reports/analytics").status_code == 200
    assert browser.get("/reports/financial").status_code == 200


def test_system_expense_access_and_empty_assignment(browser, model_session, accounts, report_data):
    login(browser, accounts["system_admin"]["email"])
    assert browser.get(f"/events/{report_data['events'][2]}/expenses").status_code == 200
    assert browser.get("/reports/analytics").status_code == 200
    model_session.get(User, accounts["student"]["id"]).role = "club_admin"
    model_session.commit()
    post(browser, "/auth/logout")
    login(browser, accounts["student"]["email"])
    assert b"30.30" not in browser.get("/reports/financial").data
    assert browser.get("/reports/financial.csv", query_string={"event_id": report_data["events"][0]}).status_code == 403


@pytest.mark.parametrize("value", ["=1+1", " +SUM(1)", "-cmd", "@cmd", "\tcmd", "\r=cmd", "\ncmd", "＝cmd", "\ufeff=cmd"])
def test_csv_formula_neutralization(value):
    assert safe_cell(value).startswith("'")


def test_money_validation_exact_and_limits():
    assert expense_input({"description": "Valid", "amount": "9999999999.99", "expense_date": "2026-01-01"})[0]["amount"] == Decimal("9999999999.99")
    assert expense_input({"description": "Valid", "amount": "0.00", "expense_date": "2026-01-01"})[0]["amount"] == Decimal("0.00")
    assert expense_input({"description": "Valid", "amount": "9" * 5000, "expense_date": "invalid"})[2]
