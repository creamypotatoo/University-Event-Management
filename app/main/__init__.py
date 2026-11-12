"""Public pages and application health."""

from flask import Blueprint, jsonify, render_template

main = Blueprint("main", __name__)


@main.get("/")
def index():
    return render_template("main/index.html")


@main.get("/health")
def health():
    """Liveness only: this endpoint does not query PostgreSQL."""
    return jsonify(status="ok", database="not_checked")
