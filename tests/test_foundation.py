from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db


def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Find your people." in response.data
    assert b"Campus life, connected." in response.data
    assert b"bootstrap@5.3.3" in response.data


def test_health_does_not_connect_to_database(app, client):
    with app.app_context():
        with patch.object(db.engine, "connect", side_effect=AssertionError("Unexpected connection")):
            response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "not_checked"}


def test_extensions_and_migration_cli(app):
    assert "sqlalchemy" in app.extensions
    assert "migrate" in app.extensions
    assert app.login_manager is not None
    assert app.test_cli_runner().invoke(args=["db", "--help"]).exit_code == 0


def test_static_stylesheet(client):
    assert client.get("/static/css/style.css").status_code == 200


def test_unknown_route(client):
    assert client.get("/missing").status_code == 404


@pytest.mark.parametrize("key", ["SECRET_KEY", "SQLALCHEMY_DATABASE_URI"])
def test_missing_required_configuration(key):
    config = {"TESTING": True, "SECRET_KEY": "temporary-test-only", "SQLALCHEMY_DATABASE_URI": "sqlite://"}
    config[key] = None
    with pytest.raises(ValueError, match="required"):
        create_app(config)


def test_production_requires_postgresql():
    with pytest.raises(ValueError, match="postgresql"):
        create_app({"SECRET_KEY": "temporary-test-only", "SQLALCHEMY_DATABASE_URI": "sqlite://"})


def test_database_check_success(app):
    result = app.test_cli_runner().invoke(args=["check-db"])
    assert result.exit_code == 0
    assert "verified" in result.output


def test_database_check_failure_hides_driver_details(app):
    with app.app_context():
        with patch.object(db.engine, "connect", side_effect=OperationalError("sensitive", {}, Exception("secret"))):
            result = app.test_cli_runner().invoke(args=["check-db"])
    assert result.exit_code != 0
    assert "Database connection failed" in result.output
    assert "secret" not in result.output
