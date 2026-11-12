"""Reusable, database-backed role and club scope checks."""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from app.extensions import db
from app.models import ClubAdmin


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def protected(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return protected
    return decorator


def can_manage_club(user, club_id):
    if not user.is_authenticated:
        return False
    if user.role == "system_admin":
        return True
    if user.role != "club_admin":
        return False
    return db.session.scalar(db.select(ClubAdmin.club_admin_id).where(
        ClubAdmin.user_id == user.user_id, ClubAdmin.club_id == club_id
    )) is not None


def club_admin_required(view):
    """Use on routes with a named club_id; system administrators are allowed."""
    @wraps(view)
    @login_required
    def protected(*args, **kwargs):
        if not can_manage_club(current_user, kwargs.get("club_id")):
            abort(403)
        return view(*args, **kwargs)
    return protected
