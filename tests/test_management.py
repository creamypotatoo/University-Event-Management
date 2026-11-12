from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.management.validation import venue_input, text_fields, PROFILE_FIELDS
from app.models import Club, ClubMembership, Event, Student, User, Venue
from tests.helpers import TEST_HASH, login, token


def post(browser, path, **values):
    return browser.post(path, data={"csrf_token": token(browser, "/"), **values})


@pytest.fixture
def second_student(model_session):
    tag = uuid4().hex
    user = User(full_name="Private Other Student", email=f"{tag}@example.edu", password_hash=TEST_HASH, role="student")
    student = Student(user=user, student_number=tag, department="Business", batch="2025")
    model_session.add(student)
    model_session.commit()
    return {"student_id": student.student_id, "email": user.email}


def test_student_profile_whitelist(browser, accounts, model_session):
    login(browser, accounts["student"]["email"])
    assert browser.get("/profile").status_code == 200
    original = model_session.get(User, accounts["student"]["id"]).student.student_number
    response = post(browser, "/profile/edit", full_name="Updated Student", department="Physics", batch="2027",
                    email="attacker@example.edu", role="system_admin", student_number="REPLACED", user_id=accounts["system_admin"]["id"])
    assert response.status_code == 302
    user = model_session.get(User, accounts["student"]["id"])
    assert (user.full_name, user.student.department, user.student.batch) == ("Updated Student", "Physics", "2027")
    assert user.role == "student" and user.email == accounts["student"]["email"]
    assert user.student.student_number == original


def test_private_students_only_owner_or_system(browser, accounts, second_student):
    login(browser, accounts["student"]["email"])
    assert browser.get(f"/students/{second_student['student_id']}").status_code == 403
    assert browser.get("/students").status_code == 403
    assert second_student["email"].encode() not in browser.get("/profile").data


def test_system_student_search_and_filters(browser, accounts, second_student):
    login(browser, accounts["system_admin"]["email"])
    response = browser.get("/students", query_string={"q": second_student["email"], "department": "Business"})
    assert response.status_code == 200 and second_student["email"].encode() in response.data
    response = browser.get("/students", query_string={"q": second_student["email"], "department": "Physics"})
    assert b"No students match" in response.data
    assert browser.get(f"/students/{second_student['student_id']}").status_code == 200


def test_invalid_profile_is_atomic(browser, accounts, model_session):
    login(browser, accounts["student"]["email"])
    assert post(browser, "/profile/edit", full_name="Changed", department="", batch="2026").status_code == 400
    assert model_session.get(User, accounts["student"]["id"]).full_name == "Test student"


def test_public_directories_and_search(browser, accounts, model_session):
    assert browser.get("/clubs").status_code == 200
    assert browser.get("/venues").status_code == 200
    assert browser.get(f"/clubs/{accounts['assigned']}").status_code == 200
    name = model_session.get(Club, accounts["assigned"]).club_name
    response = browser.get("/clubs", query_string={"q": name})
    assert b"Assigned" in response.data and b"Other " not in response.data


def test_system_club_create_edit_duplicate(browser, accounts, model_session):
    login(browser, accounts["system_admin"]["email"])
    name = f"New Club {uuid4().hex}"
    response = post(browser, "/clubs/new", club_name=name, description="First line\nSecond line", is_active="false")
    assert response.status_code == 302
    club = model_session.scalar(select(Club).where(Club.club_name == name))
    identifier = club.club_id
    assert club.is_active is True
    assert post(browser, "/clubs/new", club_name=name, description="Duplicate").status_code == 400
    assert post(browser, f"/clubs/{identifier}/edit", club_name=name, description="Edited description").status_code == 302
    assert model_session.get(Club, identifier).description == "Edited description"


@pytest.mark.parametrize("role", ["student", "club_admin"])
def test_only_system_creates_deactivates_and_modifies_venues(browser, accounts, role):
    login(browser, accounts[role]["email"])
    assert browser.get("/clubs/new").status_code == 403
    assert post(browser, "/clubs/new", club_name="Forbidden", description="Forbidden").status_code == 403
    assert post(browser, f"/clubs/{accounts['assigned']}/status", status="inactive").status_code == 403
    assert browser.get("/venues/new").status_code == 403
    assert post(browser, "/venues/new", venue_name="Forbidden", location="Campus", capacity="100").status_code == 403
    assert post(browser, "/venues/1/edit", venue_name="Forbidden", location="Campus", capacity="100").status_code == 403


def test_club_admin_edit_scope_and_cannot_change_activation(browser, accounts, model_session):
    login(browser, accounts["club_admin"]["email"])
    assert browser.get(f"/clubs/{accounts['other']}/edit").status_code == 403
    assert post(browser, f"/clubs/{accounts['other']}/edit", club_name="Forged", description="Forbidden").status_code == 403
    response = post(browser, f"/clubs/{accounts['assigned']}/edit", club_name="Edited Assigned", description="New description", is_active="false", club_id=accounts["other"])
    assert response.status_code == 302
    club = model_session.get(Club, accounts["assigned"])
    assert club.club_name == "Edited Assigned" and club.is_active is True


def test_membership_reactivation_no_duplicates_or_other_student_updates(browser, accounts, second_student, model_session):
    login(browser, accounts["student"]["email"])
    path = f"/clubs/{accounts['assigned']}"
    assert post(browser, path + "/join", student_id=second_student["student_id"]).status_code == 302
    membership = model_session.scalar(select(ClubMembership).where(ClubMembership.club_id == accounts["assigned"]))
    identifier, joined_at = membership.membership_id, membership.joined_at
    assert membership.student.user_id == accounts["student"]["id"]
    assert post(browser, path + "/join").status_code == 302
    assert post(browser, path + "/leave").status_code == 302
    assert model_session.get(ClubMembership, identifier).status == "cancelled"
    assert post(browser, path + "/join").status_code == 302
    membership = model_session.get(ClubMembership, identifier)
    assert membership.status == "active" and membership.joined_at == joined_at
    assert model_session.scalar(select(func.count()).select_from(ClubMembership).where(ClubMembership.club_id == accounts["assigned"])) == 1
    assert browser.get("/memberships").status_code == 200


def test_leave_without_join_does_not_insert(browser, accounts, model_session):
    login(browser, accounts["student"]["email"])
    assert post(browser, f"/clubs/{accounts['assigned']}/leave").status_code == 302
    assert model_session.scalar(select(func.count()).select_from(ClubMembership)) == 0


def add_membership(model_session, accounts, club_key="assigned", status="active"):
    student = model_session.scalar(select(Student).where(Student.user_id == accounts["student"]["id"]))
    record = ClubMembership(club_id=accounts[club_key], student_id=student.student_id, status=status)
    model_session.add(record)
    model_session.commit()
    return record.membership_id


def test_admin_member_status_transitions_and_scope(browser, accounts, model_session):
    own_id = add_membership(model_session, accounts)
    other_id = add_membership(model_session, accounts, "other")
    login(browser, accounts["club_admin"]["email"])
    own = f"/clubs/{accounts['assigned']}/members"
    assert browser.get(own).status_code == 200
    assert browser.get(f"/clubs/{accounts['other']}/members").status_code == 403
    assert post(browser, own + f"/{other_id}/status", status="cancelled").status_code == 404
    assert post(browser, own + f"/{own_id}/status", status="attended").status_code == 400
    assert post(browser, own + f"/{own_id}/status", status="cancelled").status_code == 302
    assert model_session.get(ClubMembership, own_id).status == "cancelled"
    assert post(browser, own + f"/{own_id}/status", status="active").status_code == 302
    assert model_session.get(ClubMembership, own_id).status == "active"


def test_student_cannot_read_roster_or_manage_member(browser, accounts, model_session):
    identifier = add_membership(model_session, accounts)
    login(browser, accounts["student"]["email"])
    base = f"/clubs/{accounts['assigned']}/members"
    assert browser.get(base).status_code == 403
    assert post(browser, base + f"/{identifier}/status", status="cancelled").status_code == 403


def test_deactivation_preserves_membership_event_and_blocks_join(browser, accounts, model_session):
    membership_id = add_membership(model_session, accounts)
    venue = Venue(venue_name=uuid4().hex, location="Campus", capacity=100)
    start = datetime(2040, 1, 1, tzinfo=timezone.utc)
    event = Event(club_id=accounts["assigned"], venue=venue, title="Preserved event", description="Test", start_time=start, end_time=start + timedelta(hours=1), capacity=50)
    model_session.add(event)
    model_session.commit()
    event_id = event.event_id
    login(browser, accounts["system_admin"]["email"])
    assert post(browser, f"/clubs/{accounts['assigned']}/status", status="inactive").status_code == 302
    assert model_session.get(ClubMembership, membership_id).status == "active"
    assert model_session.get(Event, event_id).club_id == accounts["assigned"]
    assert browser.get("/clubs", query_string={"status": "inactive", "q": "Assigned"}).status_code == 200
    # Switch accounts without bypassing the real logout form.
    assert post(browser, "/auth/logout").status_code == 302
    login(browser, accounts["student"]["email"])
    assert post(browser, f"/clubs/{accounts['assigned']}/join").status_code == 409
    assert post(browser, f"/clubs/{accounts['assigned']}/leave").status_code == 302
    assert post(browser, f"/clubs/{accounts['assigned']}/join").status_code == 409
    assert model_session.get(ClubMembership, membership_id).status == "cancelled"
    post(browser, "/auth/logout")
    login(browser, accounts["system_admin"]["email"])
    assert post(browser, f"/clubs/{accounts['assigned']}/status", status="active").status_code == 302
    assert model_session.get(Club, accounts["assigned"]).is_active is True


def test_inactive_club_blocks_admin_reactivation(browser, accounts, model_session):
    identifier = add_membership(model_session, accounts, status="cancelled")
    club = model_session.get(Club, accounts["assigned"])
    club.is_active = False
    model_session.commit()
    login(browser, accounts["club_admin"]["email"])
    assert post(browser, f"/clubs/{accounts['assigned']}/members/{identifier}/status", status="active").status_code == 409


def test_system_venue_create_edit_uniqueness(browser, accounts, model_session):
    login(browser, accounts["system_admin"]["email"])
    name = uuid4().hex
    assert post(browser, "/venues/new", venue_name=name, location="Main campus", capacity="100").status_code == 302
    venue = model_session.scalar(select(Venue).where(Venue.venue_name == name))
    identifier = venue.venue_id
    assert post(browser, "/venues/new", venue_name=name, location="Duplicate", capacity="10").status_code == 400
    assert post(browser, f"/venues/{identifier}/edit", venue_name=name, location="North campus", capacity="120").status_code == 302
    assert model_session.get(Venue, identifier).location == "North campus"


@pytest.mark.parametrize("capacity", ["0", "-1", "1.5", "abc", "2147483648", "١٢"])
def test_bad_venue_capacity(browser, accounts, capacity):
    login(browser, accounts["system_admin"]["email"])
    assert post(browser, "/venues/new", venue_name="Test venue", location="Campus", capacity=capacity).status_code == 400


def test_venue_capacity_edit_preserves_event(browser, accounts, model_session):
    venue = Venue(venue_name=uuid4().hex, location="Campus", capacity=100)
    start = datetime(2040, 1, 1, tzinfo=timezone.utc)
    event = Event(club_id=accounts["assigned"], venue=venue, title="Existing", description="Test", start_time=start, end_time=start + timedelta(hours=1), capacity=60)
    model_session.add(event)
    model_session.commit()
    venue_id, event_id, name = venue.venue_id, event.event_id, venue.venue_name
    login(browser, accounts["system_admin"]["email"])
    assert post(browser, f"/venues/{venue_id}/edit", venue_name=name, location="Campus", capacity="50").status_code == 400
    assert model_session.get(Venue, venue_id).capacity == 100
    assert post(browser, f"/venues/{venue_id}/edit", venue_name=name, location="New campus", capacity="70").status_code == 302
    assert model_session.get(Event, event_id).venue_id == venue_id


def test_pagination_filters_literal_search_and_invalid_pages(browser, accounts, model_session):
    prefix = uuid4().hex
    for number in range(12):
        model_session.add(Club(club_name=f"{prefix}-{number:02}", description="Pagination"))
    model_session.commit()
    first = browser.get("/clubs", query_string={"q": prefix})
    assert b"Page 1 of 2" in first.data and b"Next" in first.data
    second = browser.get("/clubs", query_string={"q": prefix, "page": 2})
    assert f"{prefix}-10".encode() in second.data and f"{prefix}-00".encode() not in second.data
    assert b"No clubs match" in browser.get("/clubs", query_string={"q": "%"}).data
    assert browser.get("/clubs?page=0").status_code == 400
    assert browser.get("/clubs?status=bad").status_code == 400


@pytest.mark.parametrize("path", ["/profile/edit", "/clubs/new", "/clubs/1/status", "/clubs/1/join", "/clubs/1/leave", "/clubs/1/members/1/status", "/venues/new"])
def test_all_new_writes_require_csrf(browser, path):
    assert browser.post(path, data={}).status_code == 400


def test_validation_rules_without_database():
    assert "capacity" in venue_input({"venue_name": "Hall", "location": "Campus", "capacity": "-1"})[1]
    assert "department" in text_fields({"full_name": "Test", "department": "", "batch": "2026"}, PROFILE_FIELDS)[1]
    assert "capacity" in venue_input({"venue_name": "Hall", "location": "Campus", "capacity": "9" * 5000})[1]
