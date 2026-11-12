"""Final integration journeys and failure/security regression checks."""

from datetime import datetime, timezone
from html.parser import HTMLParser
from unittest.mock import patch
from uuid import uuid4

import pytest
from flask import abort
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import Event, EventExpense, Registration, Venue
from tests.helpers import PASSWORD, login, token


def post(client, path, **data):
    return client.post(path, data={"csrf_token": token(client, "/auth/register" if path == "/auth/register" else "/"), **data})


class FormAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.duplicates = set()
        self.references = []
        self.posts = []
        self.current = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                self.duplicates.add(attrs["id"])
            self.ids.add(attrs["id"])
        if attrs.get("aria-invalid") == "true":
            assert attrs.get("aria-describedby"), "Invalid control has no associated error text"
        self.references.extend(attrs.get("aria-describedby", "").split())
        if tag == "form":
            self.current = [] if attrs.get("method", "get").lower() == "post" else None
            if self.current is not None:
                self.posts.append(self.current)
        if tag == "input" and self.current is not None and attrs.get("name") == "csrf_token":
            self.current.append(attrs.get("value"))

    def handle_endtag(self, tag):
        if tag == "form": self.current = None


def test_complete_three_role_http_journey(auth_app, accounts, model_session, monkeypatch):
    student, admin, organizer = (auth_app.test_client() for _ in range(3))
    tag = uuid4().hex
    email, title = f"{tag}@example.invalid", f"QA Workshop {tag}"
    assert post(student, "/auth/register", full_name="QA Student", email=email, student_number=f"QA-{tag}", department="Science", batch="2026", password=PASSWORD, confirm_password=PASSWORD).status_code == 302
    assert login(student, email).status_code == 302
    assert post(student, "/profile/edit", full_name="QA Student", department="Computer Science", batch="2026").status_code == 302
    assert post(student, f"/clubs/{accounts['assigned']}/join").status_code == 302
    assert student.get("/students").status_code == 403
    assert student.get("/clubs").status_code == 200
    assert login(admin, accounts["system_admin"]["email"]).status_code == 302
    assert admin.get("/students").status_code == 200
    venue_name = f"QA Hall {tag}"
    assert post(admin, "/venues/new", venue_name=venue_name, location="QA campus", capacity="1").status_code == 302
    venue_id = model_session.scalar(select(Venue.venue_id).where(Venue.venue_name == venue_name))
    assert login(organizer, accounts["club_admin"]["email"]).status_code == 302
    assert organizer.get(f"/clubs/{accounts['other']}/edit").status_code == 403
    values = {"title": title, "description": "End-to-end fixture", "venue_id": str(venue_id), "capacity": "1", "start_time": "2045-01-01T10:00", "end_time": "2045-01-01T11:00"}
    assert post(organizer, f"/clubs/{accounts['assigned']}/events/new", **values).status_code == 302
    event_id = model_session.scalar(select(Event.event_id).where(Event.title == title))
    assert post(organizer, f"/events/{event_id}/edit", **values).status_code == 302
    assert admin.get(f"/events/{event_id}/edit").status_code == 200
    assert title.encode() in student.get("/events", query_string={"q": title}).data
    for _ in range(2): assert post(student, f"/events/{event_id}/register").status_code == 302
    assert model_session.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == event_id)) == 1
    assert title.encode() in student.get("/dashboard/student").data
    assert post(student, f"/events/{event_id}/registration/cancel").status_code == 302
    assert post(student, f"/events/{event_id}/register").status_code == 302
    assert student.get(f"/events/{event_id}/participants").status_code == 403
    assert organizer.get(f"/events/{event_id}/participants").status_code == 200
    assert post(organizer, f"/events/{event_id}/expenses/new", description="QA materials", amount="10.10", expense_date="2026-11-12").status_code == 302
    expense_id = model_session.scalar(select(EventExpense.expense_id).where(EventExpense.event_id == event_id))
    assert post(organizer, f"/events/{event_id}/expenses/{expense_id}/edit", description="QA materials", amount="20.20", expense_date="2026-11-12").status_code == 302
    assert b"20.20" in organizer.get("/reports/financial.csv", query_string={"event_id": event_id}).data
    assert student.get("/reports/financial").status_code == 403
    # Simulate waiting for the real start/end deadline, without changing schema or event dates.
    clock = lambda: datetime(2045, 1, 1, 5, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.events.services.now_utc", clock)
    monkeypatch.setattr("app.reports.queries.now_utc", clock)
    registration_id = model_session.scalar(select(Registration.registration_id).where(Registration.event_id == event_id))
    assert post(organizer, f"/events/{event_id}/participants/{registration_id}/status", status="attended").status_code == 302
    assert post(organizer, f"/events/{event_id}/status", status="completed").status_code == 302
    assert b"Attended" in student.get("/registrations").data
    assert b"100.0%" in organizer.get("/reports/analytics", query_string={"event_id": event_id}).data
    assert admin.get("/reports/participation.csv").status_code == 200
    assert organizer.get(f"/events/{event_id}/expenses/{expense_id}/delete").status_code == 200
    assert post(organizer, f"/events/{event_id}/expenses/{expense_id}/delete", confirm="delete").status_code == 302
    assert post(student, "/auth/logout").status_code == 302
    assert student.get("/dashboard/student").status_code == 302


@pytest.mark.parametrize("code", [400, 403, 404, 409, 500])
def test_status_pages_escape_and_hide_internal_details(app, code):
    @app.get("/qa-error")
    def qa_error():
        abort(code, description="internal-detail-marker" if code == 500 else "<script>untrusted</script>")
    response = app.test_client().get("/qa-error")
    assert response.status_code == code
    assert b"<h1" in response.data and str(code).encode() in response.data
    assert b"<script>untrusted" not in response.data
    assert b"internal-detail-marker" not in response.data
    assert b"Return home" in response.data


def test_unexpected_500_is_generic_and_rolls_back(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    @app.get("/qa-crash")
    def crash():
        raise RuntimeError("internal-error-marker")
    with patch.object(db.session, "rollback") as rollback:
        response = app.test_client().get("/qa-crash")
    assert response.status_code == 500 and b"internal-error-marker" not in response.data
    rollback.assert_called_once()


def test_database_error_page_never_reloads_current_user(auth_app, browser, accounts):
    login(browser, accounts["student"]["email"])
    # Simulate a database outage during the next request's user loader.
    with patch.object(db.session, "get", side_effect=OperationalError("secret-marker", {}, Exception("secret-marker"))):
        response = browser.get("/dashboard/student")
    assert response.status_code == 503 and b"secret-marker" not in response.data
    assert b"temporarily unavailable" in response.data


def test_invalid_event_form_has_accessible_errors(auth_app, browser, accounts):
    login(browser, accounts["club_admin"]["email"])
    response = post(browser, f"/clubs/{accounts['assigned']}/events/new", title="", description="", venue_id="", capacity="-1", start_time="bad", end_time="bad")
    assert response.status_code == 400
    audit = FormAudit()
    audit.feed(response.get_data(as_text=True))
    assert not audit.duplicates
    assert set(audit.references).issubset(audit.ids)
    assert all(form and form[0] for form in audit.posts)
    assert b'aria-controls="primary-menu"' in response.data
    assert browser.get("/static/js/app.js").status_code == 200


def test_production_cookie_flags_without_real_secrets(monkeypatch):
    from app import create_app
    import secrets
    monkeypatch.setenv("APP_ENV", "production")
    application = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32), "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert application.config["SESSION_COOKIE_SECURE"] is True
    assert application.config["SESSION_COOKIE_HTTPONLY"] is True
    response = application.test_client().get("/auth/login")
    assert "Strict-Transport-Security" in response.headers
    assert any("Secure" in header and "HttpOnly" in header for header in response.headers.getlist("Set-Cookie"))
