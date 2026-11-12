"""Unbound extensions, initialized by the application factory."""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

db = SQLAlchemy(metadata=MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}))
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    # Reject malformed/tampered identifiers before integer conversion or querying.
    if not isinstance(user_id, str) or not user_id.isascii() or not user_id.isdigit() or len(user_id) > 10:
        return None
    identifier = int(user_id)
    if not 0 < identifier <= 2147483647:
        return None
    return db.session.get(User, identifier)
