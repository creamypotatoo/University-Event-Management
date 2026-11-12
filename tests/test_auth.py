"""Real HTTP authentication tests on SQLite and rollback-isolated PostgreSQL."""

import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from werkzeug.security import check_password_hash

from app.auth import safe_next
from app.extensions import db, load_user
from app.models import Club, ClubAdmin, Student, User

from tests.helpers import PASSWORD, TEST_HASH, login, token


def registration(**extra):
    tag = uuid4().hex
    return {"full_name": "New Student", "email": f"{tag}@example.edu", "student_number": f"N-{tag}",
            "department": "Computer Science", "batch": "2026", "password": PASSWORD,
            "confirm_password": PASSWORD, **extra}


def submit_registration(client, data):
    return client.post("/auth/register", data={"csrf_token": token(client, "/auth/register"), **data})


def test_student_registration_hashing_normalization_and_login(browser, model_session):
    data = registration()
    data["email"] = data["email"].upper()
    response = submit_registration(browser, data)
    assert response.status_code == 302
    user = model_session.scalar(select(User).where(User.email == data["email"].lower()))
    assert user is not None and user.role == "student"
    assert user.password_hash != PASSWORD and user.password_hash.startswith("scrypt:")
    assert check_password_hash(user.password_hash, PASSWORD)
    assert user.student.student_number == data["student_number"]
    assert login(browser, data["email"]).status_code == 302
    assert browser.get("/dashboard/student").status_code == 200


@pytest.mark.parametrize("conflict", ["email", "student_number"])
def test_registration_uniqueness_atomic_rollback(browser, model_session, accounts, conflict):
    before = model_session.scalar(select(func.count()).select_from(User))
    data = registration()
    student = model_session.get(User, accounts["student"]["id"]).student
    data[conflict] = accounts["student"]["email"].upper() if conflict == "email" else student.student_number
    response = submit_registration(browser, data)
    assert response.status_code == 400
    assert b"Unable to register with these details" in response.data
    assert PASSWORD.encode() not in response.data
    assert model_session.scalar(select(func.count()).select_from(User)) == before
    if conflict == "student_number":
        assert model_session.scalar(select(User).where(User.email == data["email"])) is None


@pytest.mark.parametrize("field,value", [("email", "invalid"), ("password", "short"), ("confirm_password", "different"),
                                          ("student_number", "bad identifier!"), ("student_number", "x"),
                                          ("department", ""), ("batch", " " ), ("full_name", "x" * 151),
                                          ("password", "x" * 129), ("email", "a" * 255 + "@example.edu")])
def test_invalid_registration(browser, model_session, field, value):
    before = model_session.scalar(select(func.count()).select_from(User))
    response = submit_registration(browser, registration(**{field: value}))
    assert response.status_code == 400
    assert PASSWORD.encode() not in response.data
    assert model_session.scalar(select(func.count()).select_from(User)) == before


def test_public_registration_cannot_escalate_role(browser, model_session):
    data = registration(role="system_admin", user_id="1", club_id="1", password_hash="attacker-controlled")
    assert submit_registration(browser, data).status_code == 302
    user = model_session.scalar(select(User).where(User.email == data["email"]))
    assert user.role == "student" and user.password_hash != "attacker-controlled"
    login(browser, data["email"])
    assert browser.get("/dashboard/system-admin").status_code == 403
    assert browser.get("/dashboard/club-admin").status_code == 403


@pytest.mark.parametrize("role,path", [("student", "/dashboard/student"), ("club_admin", "/dashboard/club-admin"),
                                      ("system_admin", "/dashboard/system-admin")])
def test_login_dashboard_logout_and_navigation(browser, accounts, role, path):
    with browser.session_transaction() as state:
        state["pre_login_marker"] = "discard-me"
    response = login(browser, accounts[role]["email"])
    assert response.status_code == 302
    page = browser.get("/dashboard", follow_redirects=True)
    assert page.status_code == 200 and page.request.path == path
    assert b"Log out" in page.data and b"Join as a student" not in page.data
    with browser.session_transaction() as state:
        assert state["_user_id"] == str(accounts[role]["id"])
        assert state.permanent and "pre_login_marker" not in state
    assert browser.get("/auth/logout").status_code == 405
    assert browser.post("/auth/logout", data={"csrf_token": token(browser, path)}).status_code == 302
    assert browser.get(path).status_code == 302
    with browser.session_transaction() as state:
        assert "_user_id" not in state


@pytest.mark.parametrize("role,target", [("student", "/dashboard/system-admin"), ("student", "/dashboard/club-admin"),
                                        ("club_admin", "/dashboard/student"), ("club_admin", "/dashboard/system-admin"),
                                        ("system_admin", "/dashboard/student")])
def test_wrong_roles_forbidden(browser, accounts, role, target):
    login(browser, accounts[role]["email"])
    response = browser.get(target)
    assert response.status_code == 403 and b"Access denied" in response.data


def test_club_scope_and_role_changes_enforced(browser, accounts, model_session):
    login(browser, accounts["club_admin"]["email"])
    assert browser.get(f"/clubs/{accounts['assigned']}/dashboard").status_code == 200
    assert browser.get(f"/clubs/{accounts['other']}/dashboard").status_code == 403
    page = browser.get("/dashboard/club-admin")
    assert f"/clubs/{accounts['assigned']}/dashboard".encode() in page.data
    assert f"/clubs/{accounts['other']}/dashboard".encode() not in page.data
    # DB role changes take effect on the next request; the role is never trusted from a cookie.
    user = model_session.get(User, accounts["club_admin"]["id"])
    user.role = "student"
    model_session.commit()
    assert browser.get(f"/clubs/{accounts['assigned']}/dashboard").status_code == 403


@pytest.mark.parametrize("role,status", [("student", 403), ("system_admin", 200)])
def test_club_scope_system_override_and_student_rejection(browser, accounts, role, status):
    login(browser, accounts[role]["email"])
    assert browser.get(f"/clubs/{accounts['other']}/dashboard").status_code == status


@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/student", "/dashboard/club-admin", "/dashboard/system-admin", "/clubs/1/dashboard"])
def test_anonymous_redirect_to_login(browser, path):
    response = browser.get(path)
    assert response.status_code == 302 and "/auth/login?next=" in response.location


def test_generic_login_failure(browser, accounts):
    responses = [login(browser, accounts["student"]["email"], password="wrong-password"),
                 login(browser, f"{uuid4().hex}@example.edu", password="wrong-password")]
    assert all(response.status_code == 401 for response in responses)
    assert all(b"Invalid email or password." in response.data for response in responses)
    assert responses[0].data == responses[1].data
    with browser.session_transaction() as state:
        assert "_user_id" not in state


@pytest.mark.parametrize("path", ["/auth/login", "/auth/register", "/auth/logout"])
@pytest.mark.parametrize("bad_token", [None, "forged", "f" * 64, "é" * 64])
def test_missing_invalid_csrf(browser, path, bad_token):
    token(browser)
    response = browser.post(path, data={} if bad_token is None else {"csrf_token": bad_token})
    assert response.status_code == 400 and b"could not be verified" in response.data


def test_expired_cross_session_and_rotated_csrf(browser, auth_app, accounts):
    old = token(browser)
    another = auth_app.test_client()
    assert another.post("/auth/login", data={"csrf_token": old}).status_code == 400
    with browser.session_transaction() as state:
        state["_csrf_time"] = time.time() - 3601
    assert browser.post("/auth/login", data={"csrf_token": old}).status_code == 400
    login(browser, accounts["student"]["email"])
    assert browser.post("/auth/logout", data={"csrf_token": old}).status_code == 400
    assert token(browser, "/dashboard/student") != old


@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/", "/\\evil.example", "/%2fevil.example", "/%252fevil.example", "javascript:alert(1)", "/\t/evil.example"])
def test_open_redirects_rejected(browser, accounts, target):
    assert safe_next(target) is None
    response = login(browser, accounts["student"]["email"], next=target)
    assert response.status_code == 302 and response.location == "/dashboard"


def test_local_next_allowed_and_authorized(browser, accounts):
    response = login(browser, accounts["student"]["email"], next="/dashboard/system-admin")
    assert response.location == "/dashboard/system-admin"
    assert browser.get(response.location).status_code == 403


def test_loader_missing_and_malformed_users(auth_app):
    with auth_app.app_context():
        for identifier in ["-1", "bogus", "999999999999999999", "0", "2147483648", "١", "2147483647"]:
            assert load_user(identifier) is None


def test_initial_admin_cli_private_input(auth_app, model_session):
    email = f"{uuid4().hex}@example.edu"
    result = auth_app.test_cli_runner().invoke(args=["create-admin"], input=f"Initial Admin\n{email}\n{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0
    assert PASSWORD not in result.output
    user = model_session.scalar(select(User).where(User.email == email))
    assert user.role == "system_admin" and user.check_password(PASSWORD)
    model_session.commit()  # End assertion query's transaction before the next CLI invocation.
    second = auth_app.test_cli_runner().invoke(args=["create-admin"], input=f"Another Admin\n{uuid4().hex}@example.edu\n{PASSWORD}\n{PASSWORD}\n")
    assert second.exit_code != 0 and "already exists" in second.output


def test_admin_cli_rejects_weak_password_and_existing_email(auth_app, model_session):
    email = f"{uuid4().hex}@example.edu"
    model_session.add(User(full_name="Student", email=email, password_hash=TEST_HASH, role="student"))
    model_session.commit()
    for password in ("short", PASSWORD):
        result = auth_app.test_cli_runner().invoke(args=["create-admin"], input=f"Admin\n{email}\n{password}\n{password}\n")
        assert result.exit_code != 0 and password not in result.output
    assert model_session.scalar(select(User).where(User.email == email)).role == "student"


def test_security_headers_and_cookie(browser, accounts):
    response = login(browser, accounts["student"]["email"])
    cookie = next(header for header in response.headers.getlist("Set-Cookie") if header.startswith("session="))
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_club_assignment_revocation(browser, accounts, model_session):
    login(browser, accounts["club_admin"]["email"])
    assignment = model_session.scalar(select(ClubAdmin).where(ClubAdmin.club_id == accounts["assigned"]))
    assignment.user_id = accounts["system_admin"]["id"]
    model_session.commit()
    assert browser.get(f"/clubs/{accounts['assigned']}/dashboard").status_code == 403


def test_missing_user_cookie_is_anonymous(browser):
    with browser.session_transaction() as state:
        state["_user_id"] = "2147483647"
    assert browser.get("/dashboard").status_code == 302


def test_student_without_profile_forbidden(browser, model_session):
    email = f"{uuid4().hex}@example.edu"
    model_session.add(User(full_name="Incomplete", email=email, password_hash=TEST_HASH, role="student"))
    model_session.commit()
    login(browser, email)
    assert browser.get("/dashboard/student").status_code == 403


def test_escaped_profile_and_authenticated_register(browser, model_session):
    data = registration(full_name="<script>alert('name')</script>")
    submit_registration(browser, data)
    login(browser, data["email"])
    response = browser.get("/dashboard/student")
    assert b"<script>" not in response.data and b"&lt;script&gt;" in response.data
    assert browser.get("/auth/register").status_code == 302


def test_cookie_and_login_role_injection_rejected(browser, accounts):
    login(browser, accounts["student"]["email"], role="system_admin", user_id=accounts["system_admin"]["id"])
    with browser.session_transaction() as state:
        state["role"] = "system_admin"
    assert browser.get("/dashboard/system-admin").status_code == 403


def test_admin_cli_password_confirmation(auth_app, model_session):
    email = f"{uuid4().hex}@example.edu"
    result = auth_app.test_cli_runner().invoke(args=["create-admin"], input=f"Admin\n{email}\n{PASSWORD}\nnot-matching\n")
    assert result.exit_code != 0
    assert PASSWORD not in result.output and "not-matching" not in result.output
    assert model_session.scalar(select(User).where(User.email == email)) is None


def test_logout_clears_legacy_remember_cookie(browser, auth_app, accounts):
    from flask_login.utils import encode_cookie
    login(browser, accounts["student"]["email"])
    browser.set_cookie("remember_token", encode_cookie(str(accounts["student"]["id"]), key=auth_app.secret_key))
    response = browser.post("/auth/logout", data={"csrf_token": token(browser, "/dashboard/student")})
    assert any("remember_token=;" in header for header in response.headers.getlist("Set-Cookie"))
    assert browser.get("/dashboard/student").status_code == 302


def test_login_rollback_on_database_failure(browser):
    from sqlalchemy.exc import OperationalError
    csrf = token(browser)
    with patch.object(db.session, "scalar", side_effect=OperationalError("private", {}, Exception("private"))):
        response = browser.post("/auth/login", data={"csrf_token": csrf, "email": "test@example.edu", "password": PASSWORD})
    assert response.status_code == 503 and b"private" not in response.data
