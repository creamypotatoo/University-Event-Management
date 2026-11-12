"""One-time read-only PostgreSQL comparison for the initial revision.

Unlike `flask db migrate`, this does not initialize an alembic_version table.
Never prints connection URLs or database exception details.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.autogenerate import produce_migrations, render_python_code
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db


def main():
    app = create_app()
    with app.app_context(), db.engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        tables = inspect(connection).get_table_names()
        print(f"Public tables before migration: {len(tables)}")
        if tables:
            raise RuntimeError("Initial migration generation requires an empty public schema; no changes made.")
        available = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'btree_gist')"))
        installed = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist')"))
        print(f"btree_gist available: {available}; installed: {installed}")
        if not available:
            raise RuntimeError("btree_gist is unavailable on this PostgreSQL server.")
        context = MigrationContext.configure(connection, opts={"target_metadata": db.metadata})
        changes = produce_migrations(context, db.metadata)
        config = Config("migrations/alembic.ini")
        config.set_main_option("script_location", "migrations")
        scripts = ScriptDirectory.from_config(config)
        if scripts.get_heads():
            raise RuntimeError("A revision already exists; refusing to create another initial migration.")
        scripts.generate_revision(
            "0001_initial", "initial normalized university schema",
            upgrades=render_python_code(changes.upgrade_ops, migration_context=context),
            downgrades=render_python_code(changes.downgrade_ops, migration_context=context),
            imports="from sqlalchemy.dialects import postgresql",
        )
        print("Revision generated using read-only PostgreSQL inspection. No database schema changes applied.")


if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError:
        print("Database inspection failed. Check local connection settings; driver details suppressed.", file=sys.stderr)
        sys.exit(1)
