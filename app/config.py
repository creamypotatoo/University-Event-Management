"""Read environment settings each time an application is created."""

import os
from datetime import timedelta


def environment_config():
    environment = os.getenv("APP_ENV", "development")
    if environment not in {"development", "production", "testing"}:
        raise ValueError("APP_ENV must be development, production, or testing.")
    return {
        "APP_ENV": environment,
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL"),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": environment == "production",
        "REMEMBER_COOKIE_HTTPONLY": True,
        "REMEMBER_COOKIE_SECURE": environment == "production",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=8),
        "SESSION_REFRESH_EACH_REQUEST": False,
        "MAX_CONTENT_LENGTH": 64 * 1024,
        "CSRF_MAX_AGE": 3600,
    }
