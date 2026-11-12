import secrets

from app import create_app


def test_initial_migration_offline_sql():
    # Offline SQL compilation uses PostgreSQL without connecting or applying DDL.
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://localhost/offline_only"})
    result = app.test_cli_runner().invoke(args=["db", "upgrade", "--sql"])
    assert result.exit_code == 0, "Offline migration compilation failed"
    sql = result.output
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in sql
    assert "EXCLUDE USING gist" in sql
    assert "tstzrange(start_time, end_time, '[)')" in sql
    assert "uq_registrations_event_student" in sql
    assert "DROP TABLE" not in sql
    assert sql.count("CREATE TABLE") == 10  # Nine domain tables plus Alembic version.


def test_seed_requires_opt_in(app):
    result = app.test_cli_runner().invoke(args=["seed-dev"])
    assert result.exit_code != 0
    assert "--confirm" in result.output


def test_club_deactivation_migration_is_additive_offline():
    app = create_app({"TESTING": True, "SECRET_KEY": secrets.token_hex(32),
                      "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://localhost/offline_only"})
    result = app.test_cli_runner().invoke(args=["db", "upgrade", "0001_initial:0002_club_active", "--sql"])
    assert result.exit_code == 0
    assert "ALTER TABLE clubs ADD COLUMN is_active BOOLEAN DEFAULT true NOT NULL" in result.output
    assert "DROP" not in result.output and "DELETE" not in result.output
