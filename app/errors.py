"""Consistent error pages that never depend on loading the current database user."""

from flask import current_app, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

TITLES = {400: "Check your request", 403: "Access denied", 404: "Page not found", 409: "This action conflicts with the current state", 500: "Something went wrong", 503: "Service temporarily unavailable"}


def error_response(code, message):
    # Flask-Login's normal template context processor eagerly reloads the user.
    # Error recovery must avoid that processor when the database is unavailable.
    template = current_app.jinja_env.get_template("errors/status.html")
    return template.render(code=code, title=TITLES.get(code, "Request could not be completed"), message=message, url_for=url_for), code


def rollback_safely():
    try:
        db.session.rollback()
    except SQLAlchemyError:
        # A disconnected connection can also fail rollback; teardown closes it.
        pass


def register_errors(app):
    @app.errorhandler(400)
    def bad_request(error):
        return error_response(400, error.description)

    @app.errorhandler(403)
    def forbidden(error):
        return error_response(403, "Your account role or club assignment does not permit this action.")

    @app.errorhandler(404)
    def missing(error):
        return error_response(404, "The page or record could not be found. Check the address or return to the directory.")

    @app.errorhandler(409)
    def conflict(error):
        return error_response(409, error.description)

    @app.errorhandler(500)
    def internal_error(error):
        rollback_safely()
        return error_response(500, "Your request could not be completed. Please try again later or contact the project administrator.")

    @app.errorhandler(503)
    def unavailable(error):
        rollback_safely()
        return error_response(503, "The service is temporarily unavailable. No partial changes were saved. Please try again later.")

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        rollback_safely()
        return error_response(503, "The database is temporarily unavailable. No partial changes were saved. Please try again later.")
