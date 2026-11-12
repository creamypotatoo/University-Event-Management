"""Session-bound CSRF tokens for every unsafe HTTP method."""

import secrets
import time

from flask import abort, current_app, request, session


def csrf_token():
    now = time.time()
    if not session.get("_csrf_token") or now - session.get("_csrf_time", 0) > current_app.config["CSRF_MAX_AGE"]:
        session["_csrf_token"] = secrets.token_hex(32)
        session["_csrf_time"] = now
    return session["_csrf_token"]


def protect_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    token = request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    age = time.time() - session.get("_csrf_time", 0)
    if (not expected or len(token) != 64 or not token.isascii()
            or age < 0 or age > current_app.config["CSRF_MAX_AGE"]
            or not secrets.compare_digest(token, expected)):
        abort(400, description="Your form expired or could not be verified. Reload the page and try again.")


def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if current_app.config["APP_ENV"] == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; form-action 'self'; base-uri 'self'; frame-ancestors 'none'"
    )
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    return response
