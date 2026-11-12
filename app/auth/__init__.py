"""Authentication and public student registration."""

import secrets
from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth.validation import normalize_email, registration_input, valid_email
from app.extensions import db
from app.models import Student, User

auth = Blueprint("auth", __name__, url_prefix="/auth")
_DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32), method="scrypt")
LOGIN_ERROR = "Invalid email or password."
REGISTER_ERROR = "Unable to register with these details. Check your information or log in."


def safe_next(target):
    # Accept only root-relative URLs. Reject encoded/ambiguous browser interpretations.
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    if any(c in target for c in ("\\", "%")) or any(ord(c) < 33 or ord(c) == 127 for c in target):
        return None
    try:
        parsed = urlsplit(target)
    except ValueError:
        return None
    return target if not parsed.scheme and not parsed.netloc else None


@auth.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboards.index"))
    data, errors = ({}, {})
    if request.method == "POST":
        data, errors = registration_input(request.form)
        if not errors:
            user = User(full_name=data["full_name"], email=data["email"], role="student")
            user.set_password(request.form["password"])
            try:
                # One commit: a conflicting student identifier cannot leave an orphan user.
                db.session.add(Student(user=user, student_number=data["student_number"],
                                       department=data["department"], batch=data["batch"]))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["form"] = REGISTER_ERROR
            except SQLAlchemyError:
                db.session.rollback()
                abort(503, description="Account services are temporarily unavailable. Please try again later.")
            else:
                session.clear()
                flash("Your student account is ready. Please log in.", "success")
                return redirect(url_for("auth.login"))
        return render_template("auth/register.html", values=data, errors=errors), 400
    return render_template("auth/register.html", values=data, errors=errors)


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboards.index"))
    error = None
    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        user = None
        if valid_email(email) and 1 <= len(password) <= 128:
            try:
                user = db.session.scalar(db.select(User).where(User.email == email))
            except SQLAlchemyError:
                db.session.rollback()
                abort(503, description="Account services are temporarily unavailable. Please try again later.")
        # Perform a real password hash comparison even for unknown/malformed identities.
        valid = user.check_password(password) if user is not None else check_password_hash(_DUMMY_HASH, password[:128])
        if user is not None and valid:
            destination = safe_next(request.form.get("next"))
            session.clear()
            login_user(user, remember=False, fresh=True)
            session.permanent = True
            session["_remember"] = "clear"  # Expire any legacy persistent-login cookie.
            return redirect(destination or url_for("dashboards.index"))
        error = LOGIN_ERROR
    destination = safe_next(request.values.get("next")) or ""
    return render_template("auth/login.html", error=error, next_url=destination), (401 if error else 200)


@auth.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    session["_remember"] = "clear"
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
