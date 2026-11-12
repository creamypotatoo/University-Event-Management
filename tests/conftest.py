import secrets

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from sqlalchemy.orm import scoped_session
from uuid import uuid4
from app.models import Club, ClubAdmin, Student, User
from tests.helpers import TEST_HASH


def pytest_addoption(parser):
    parser.addoption("--postgres", action="store_true", default=False,
                     help="Run rollback-isolated tests against the configured migrated local PostgreSQL database.")


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgresql)])
def model_session(request):
    """No committed test rows, schema resets, deletes, or database drops."""
    if request.param == "postgresql":
        if not request.config.getoption("--postgres"):
            pytest.skip("PostgreSQL tests require migration approval/application and --postgres")
        application = create_app()
        if application.config["APP_ENV"] != "development":
            pytest.fail("PostgreSQL integration tests require APP_ENV=development", pytrace=False)
        with application.app_context():
            engine = db.engine
    else:
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        db.metadata.create_all(engine)
    try:
        connection = engine.connect()
    except SQLAlchemyError:
        pytest.fail("Test database connection failed; driver details suppressed.", pytrace=False)
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        if request.param == "postgresql":
            if not set(db.metadata.tables).issubset(inspect(connection).get_table_names()):
                pytest.fail("PostgreSQL schema is not migrated. Obtain approval before applying migration.", pytrace=False)
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        if request.param == "sqlite":
            engine.dispose()


@pytest.fixture
def app():
    return create_app({
        "TESTING": True,
        "SECRET_KEY": secrets.token_hex(32),
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_app(model_session, monkeypatch):
    application = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                              "SQLALCHEMY_DATABASE_URI": model_session.bind.engine.url,
                              "APP_ENV": "development"})
    sessions = scoped_session(lambda: model_session)
    monkeypatch.setattr(db, "session", sessions)
    yield application
    sessions.remove()


@pytest.fixture
def browser(auth_app):
    return auth_app.test_client()


@pytest.fixture
def accounts(auth_app, model_session):
    tag = uuid4().hex
    result = {}
    for role in ("student", "club_admin", "system_admin"):
        user = User(full_name=f"Test {role}", email=f"{tag}.{role}@example.edu", password_hash=TEST_HASH, role=role)
        model_session.add(user)
        model_session.flush()
        result[role] = {"id": user.user_id, "email": user.email}
        if role == "student":
            model_session.add(Student(user_id=user.user_id, student_number=f"S-{tag}", department="Science", batch="2026"))
    assigned = Club(club_name=f"Assigned {tag}", description="Assigned club")
    other = Club(club_name=f"Other {tag}", description="Unassigned club")
    model_session.add_all([assigned, other])
    model_session.flush()
    model_session.add(ClubAdmin(user_id=result["club_admin"]["id"], club_id=assigned.club_id))
    result["assigned"] = assigned.club_id
    result["other"] = other.club_id
    model_session.commit()
    return result
