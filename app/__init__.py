"""University Event and Club Management application factory."""

from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, render_template
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import environment_config
from app.extensions import db, login_manager, migrate


def create_app(test_config=None):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(environment_config())
    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise ValueError("SECRET_KEY is required. See .env.example and README.md.")
    database_url = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not database_url:
        raise ValueError("DATABASE_URL is required. See .env.example and README.md.")
    if not app.testing and make_url(database_url).drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use postgresql+psycopg://.")

    db.init_app(app)
    from app import models  # Register metadata before Alembic inspects it.
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.main import main
    app.register_blueprint(main)

    from app.auth import auth
    from app.auth.cli import create_admin
    from app.dashboards import dashboards
    from app.security import csrf_token, protect_csrf, security_headers
    app.register_blueprint(auth)
    app.register_blueprint(dashboards)
    from app.management import management
    app.register_blueprint(management)
    from app.events import events
    app.register_blueprint(events)
    app.cli.add_command(create_admin)
    app.before_request(protect_csrf)
    app.after_request(security_headers)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", message=error.description), 400

    @app.errorhandler(409)
    def conflict(error):
        return render_template("errors/400.html", message=error.description), 409

    from app.seed import seed_dev
    app.cli.add_command(seed_dev)

    @app.cli.command("check-db")
    def check_db():
        """Verify a connection with a read-only SELECT; never create tables."""
        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            # Driver errors may include credentials or infrastructure details.
            raise click.ClickException(
                "Database connection failed. Check DATABASE_URL and PostgreSQL availability."
            ) from None
        click.echo("Database connection verified (SELECT 1).")

    return app
