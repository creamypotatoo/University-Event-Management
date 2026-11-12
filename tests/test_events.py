from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.events import services
from app.events.validation import event_input
from app.models import Club, Event, Registration, Student, User, Venue
from tests.helpers import TEST_HASH, login, token


def post(browser, path, **values):
    return browser.post(path, data={"csrf_token": token(browser, "/"), **values})


@pytest.fixture
def event_data(model_session, accounts):
    venue = Venue(venue_name=f"Event Hall {uuid4().hex}", location="Campus", capacity=30)
    start = datetime(2045, 1, 1, 4, tzinfo=timezone.utc)
    event = Event(club_id=accounts["assigned"], venue=venue, title=f"Workshop {uuid4().hex}", description="Learn together",
                  start_time=start, end_time=start + timedelta(hours=2), capacity=2, status="scheduled")
    model_session.add(event)
    model_session.commit()
    student = model_session.scalar(select(Student).where(Student.user_id == accounts["student"]["id"]))
    return {"id": event.event_id, "venue_id": venue.venue_id, "title": event.title, "student_id": student.student_id,
            "values": {"title": "Edited workshop", "description": "Updated", "venue_id": str(venue.venue_id),
                       "start_time": "2045-01-01T10:00", "end_time": "2045-01-01T12:00", "capacity": "2"}}


def test_public_events_search_details_filters(browser, event_data):
    response = browser.get("/events", query_string={"q": event_data["title"], "venue_id": event_data["venue_id"]})
    assert response.status_code == 200 and event_data["title"].encode() in response.data
    assert b"No events match" in browser.get("/events?status=completed").data
    response = browser.get(f"/events/{event_data['id']}")
    assert response.status_code == 200 and b"Available seats" in response.data and b"Asia/Dhaka" in response.data
    assert b"Test student" not in response.data
    assert browser.get("/events?venue_id=bad").status_code == 400
    assert browser.get("/events?from_date=invalid").status_code == 400


def test_manager_create_edit_ownership_and_timezone(browser, accounts, event_data, model_session):
    login(browser, accounts["club_admin"]["email"])
    assert browser.get("/events/manage").status_code == 200
    assert browser.get(f"/clubs/{accounts['assigned']}/events/new").status_code == 200
    assert browser.get(f"/events/{event_data['id']}/edit").status_code == 200
    response = post(browser, f"/events/{event_data['id']}/edit", **event_data["values"], club_id=accounts["other"], status="completed")
    assert response.status_code == 302
    event = model_session.get(Event, event_data["id"])
    assert event.club_id == accounts["assigned"] and event.status == "scheduled"
    assert services.utc(event.start_time).hour == 4  # 10:00 Asia/Dhaka is 04:00 UTC.
    values = {**event_data["values"], "title": "Adjacent workshop", "start_time": "2045-01-01T12:00", "end_time": "2045-01-01T13:00"}
    assert post(browser, f"/clubs/{accounts['assigned']}/events/new", **values).status_code == 302


@pytest.mark.parametrize("role", ["student", "club_admin"])
def test_event_cross_club_permissions(browser, accounts, event_data, role):
    login(browser, accounts[role]["email"])
    other = accounts["other"] if role == "club_admin" else accounts["assigned"]
    assert post(browser, f"/clubs/{other}/events/new", **event_data["values"]).status_code == 403
    if role == "student":
        assert post(browser, f"/events/{event_data['id']}/edit", **event_data["values"]).status_code == 403
        assert post(browser, f"/events/{event_data['id']}/status", status="cancelled").status_code == 403


def test_unassigned_event_edit_cancel_and_participant_access(browser, accounts, event_data, model_session):
    event = model_session.get(Event, event_data["id"])
    event.club_id = accounts["other"]
    model_session.commit()
    login(browser, accounts["club_admin"]["email"])
    for path in ("edit", "participants"):
        assert browser.get(f"/events/{event_data['id']}/{path}").status_code == 403
    assert post(browser, f"/events/{event_data['id']}/status", status="cancelled").status_code == 403
    response = browser.get("/events/manage")
    assert event_data["title"].encode() not in response.data


def test_system_can_manage_other_club_event(browser, accounts, event_data):
    login(browser, accounts["system_admin"]["email"])
    assert browser.get(f"/events/{event_data['id']}/edit").status_code == 200
    assert browser.get(f"/events/{event_data['id']}/participants").status_code == 200


@pytest.mark.parametrize("change,code", [({"title": ""}, 400), ({"start_time": "invalid"}, 400), ({"end_time": "2045-01-01T09:00"}, 400),
                                      ({"capacity": "0"}, 400), ({"capacity": "31"}, 400), ({"capacity": "2.5"}, 400),
                                      ({"venue_id": ""}, 400), ({"start_time": "2000-01-01T10:00"}, 400)])
def test_event_validation(browser, accounts, event_data, change, code):
    login(browser, accounts["club_admin"]["email"])
    assert post(browser, f"/events/{event_data['id']}/edit", **{**event_data["values"], **change}).status_code == code


def test_overlap_adjacent_cancelled_event_and_history_preserved(browser, accounts, event_data, model_session):
    registration = Registration(event_id=event_data["id"], student_id=event_data["student_id"])
    model_session.add(registration)
    model_session.commit()
    registration_id = registration.registration_id
    login(browser, accounts["club_admin"]["email"])
    create = f"/clubs/{accounts['assigned']}/events/new"
    assert post(browser, create, **event_data["values"]).status_code == 409
    assert post(browser, f"/events/{event_data['id']}/status", status="cancelled").status_code == 302
    assert model_session.get(Registration, registration_id).status == "registered"
    assert post(browser, create, **event_data["values"]).status_code == 302
    assert post(browser, f"/events/{event_data['id']}/status", status="completed").status_code == 409
    assert post(browser, f"/events/{event_data['id']}/edit", **event_data["values"]).status_code == 409


def test_register_duplicate_cancel_reactivate_and_dashboard(browser, accounts, event_data, model_session):
    login(browser, accounts["student"]["email"])
    base = f"/events/{event_data['id']}"
    assert post(browser, base + "/register", student_id="2147483647").status_code == 302
    registration = model_session.scalar(select(Registration).where(Registration.event_id == event_data["id"]))
    identifier, registered_at = registration.registration_id, registration.registered_at
    assert registration.student_id == event_data["student_id"]
    assert post(browser, base + "/register").status_code == 302
    assert event_data["title"].encode() in browser.get("/dashboard/student").data
    assert event_data["title"].encode() in browser.get("/registrations").data
    assert post(browser, base + "/registration/cancel").status_code == 302
    assert model_session.get(Registration, identifier).status == "cancelled"
    assert post(browser, base + "/register").status_code == 302
    registration = model_session.get(Registration, identifier)
    assert registration.status == "registered" and registration.registered_at == registered_at
    assert model_session.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == event_data["id"])) == 1


@pytest.mark.parametrize("reason", ["cancelled", "completed", "started", "inactive", "full"])
def test_ineligible_registration(browser, accounts, event_data, model_session, reason):
    event = model_session.get(Event, event_data["id"])
    if reason in {"cancelled", "completed"}: event.status = reason
    if reason == "started":
        event.start_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    if reason == "inactive": event.club.is_active = False
    if reason == "full":
        event.capacity = 1
        user = User(full_name="Other", email=f"{uuid4().hex}@example.edu", password_hash=TEST_HASH, role="student")
        student = Student(user=user, student_number=uuid4().hex, department="Science", batch="2026")
        model_session.add(Registration(event=event, student=student, status="attended"))
    model_session.commit()
    login(browser, accounts["student"]["email"])
    assert post(browser, f"/events/{event_data['id']}/register").status_code == 409


def test_capacity_reduction_cannot_displace_registration(browser, accounts, event_data, model_session):
    # Existing attended and registered rows both occupy capacity.
    user = User(full_name="Other", email=f"{uuid4().hex}@example.edu", password_hash=TEST_HASH, role="student")
    student = Student(user=user, student_number=uuid4().hex, department="Science", batch="2026")
    model_session.add_all([Registration(event_id=event_data["id"], student_id=event_data["student_id"], status="registered"),
                           Registration(event_id=event_data["id"], student=student, status="attended")])
    model_session.commit()
    login(browser, accounts["club_admin"]["email"])
    assert post(browser, f"/events/{event_data['id']}/edit", **{**event_data["values"], "capacity": "1"}).status_code == 409
    assert model_session.get(Event, event_data["id"]).capacity == 2


def test_participant_history_privacy_and_attendance(browser, accounts, event_data, model_session):
    registration = Registration(event_id=event_data["id"], student_id=event_data["student_id"])
    model_session.add(registration)
    model_session.commit()
    identifier = registration.registration_id
    login(browser, accounts["student"]["email"])
    assert browser.get(f"/events/{event_data['id']}/participants").status_code == 403
    assert b"Test student" not in browser.get(f"/events/{event_data['id']}").data
    post(browser, "/auth/logout")
    login(browser, accounts["club_admin"]["email"])
    assert browser.get("/registrations").status_code == 403
    path = f"/events/{event_data['id']}/participants/{identifier}/status"
    assert post(browser, path, status="attended").status_code == 409
    event = model_session.get(Event, event_data["id"])
    event.start_time, event.end_time = datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2020, 1, 2, tzinfo=timezone.utc)
    model_session.commit()
    assert post(browser, path, status="attended").status_code == 302
    assert model_session.get(Registration, identifier).status == "attended"
    assert post(browser, f"/events/{event_data['id']}/status", status="completed").status_code == 302
    assert post(browser, f"/events/{event_data['id']}/status", status="cancelled").status_code == 409


def test_complete_before_end_rejected_and_registration_cancel_closed(browser, accounts, event_data, model_session):
    login(browser, accounts["club_admin"]["email"])
    assert post(browser, f"/events/{event_data['id']}/status", status="completed").status_code == 409
    post(browser, "/auth/logout")
    login(browser, accounts["student"]["email"])
    post(browser, f"/events/{event_data['id']}/register")
    event = model_session.get(Event, event_data["id"])
    event.start_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    model_session.commit()
    assert post(browser, f"/events/{event_data['id']}/registration/cancel").status_code == 409


@pytest.mark.parametrize("path", ["/events/1/register", "/events/1/registration/cancel", "/events/1/status", "/events/1/edit", "/clubs/1/events/new", "/events/1/participants/1/status"])
def test_event_csrf(browser, path):
    assert browser.post(path).status_code == 400


def test_event_transaction_failure_is_safe(browser, accounts, event_data):
    login(browser, accounts["student"]["email"])
    csrf = token(browser, "/")
    with patch("app.events.services.register_student", side_effect=OperationalError("sensitive", {}, Exception("sensitive"))):
        response = browser.post(f"/events/{event_data['id']}/register", data={"csrf_token": csrf})
    assert response.status_code == 503 and b"sensitive" not in response.data


def test_event_date_validation_without_database():
    values, display, errors = event_input({"title": "Test", "description": "Details", "venue_id": "1", "capacity": "1", "start_time": "2045-01-01T10:00", "end_time": "2045-01-01T11:00"})
    assert not errors and values["start_time"].hour == 4
    assert event_input({"capacity": "9" * 5000})[2]
