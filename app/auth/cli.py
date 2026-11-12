"""Interactive bootstrap for the first system administrator; no password flags."""

import click
from flask.cli import with_appcontext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.validation import normalize_email, valid_email, valid_password, valid_text
from app.extensions import db
from app.models import User


@click.command("create-admin")
@with_appcontext
def create_admin():
    """Create the initial system administrator using private interactive prompts."""
    name = click.prompt("Full name").strip()
    email = normalize_email(click.prompt("Email"))
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    if not valid_text(name, 150) or not valid_email(email) or not valid_password(password):
        raise click.ClickException("Invalid account details. Name: 1–150 characters; valid email; password: 12–128 printable characters.")
    try:
        with db.session.begin():
            if db.engine.dialect.name == "postgresql":
                # Serialize bootstrap commands so simultaneous attempts cannot create two initial admins.
                db.session.execute(text("SELECT pg_advisory_xact_lock(42819031)"))
            if db.session.scalar(db.select(User.user_id).where(User.role == "system_admin").limit(1)) is not None:
                raise click.ClickException("A system administrator already exists. No account was created or changed.")
            if db.session.scalar(db.select(User.user_id).where(User.email == email)) is not None:
                raise click.ClickException("That email cannot be used. No account was created or changed.")
            user = User(full_name=name, email=email, role="system_admin")
            user.set_password(password)
            db.session.add(user)
    except SQLAlchemyError:
        raise click.ClickException("Administrator creation failed; transaction rolled back. Check database availability and schema.") from None
    click.echo("Initial system administrator created. No credentials are displayed.")
