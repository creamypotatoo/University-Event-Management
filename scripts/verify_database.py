"""Read-only schema/integrity audit and representative EXPLAIN plans.

Never prints credentials or user records; never runs ANALYZE or schema changes.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, select, func, text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db


def audit():
    app = create_app()
    with app.app_context(), db.engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '5s'"))
        inspector = inspect(connection)
        result = {"read_only": True, "revision": connection.scalar(text("SELECT version_num FROM alembic_version")), "tables": {}, "plans": {}}
        if not set(db.metadata.tables).issubset(inspector.get_table_names(schema="public")):
            raise RuntimeError("Core tables are missing; audit stopped without changes.")
        for table in db.metadata.sorted_tables:
            name = table.name
            columns = inspector.get_columns(name)
            assert {c["name"] for c in columns} == set(table.columns.keys()), f"Column mismatch: {name}"
            assert all(not c["nullable"] for c in columns), f"Unexpected nullable column: {name}"
            primary = inspector.get_pk_constraint(name)["constrained_columns"]
            assert primary == [c.name for c in table.primary_key], f"Primary key mismatch: {name}"
            foreign = inspector.get_foreign_keys(name)
            assert len(foreign) == len(table.foreign_key_constraints), f"Foreign key mismatch: {name}"
            expected_fk = {(tuple(c.parent.name for c in constraint.elements), constraint.referred_table.name, tuple(c.column.name for c in constraint.elements)) for constraint in table.foreign_key_constraints}
            actual_fk = {(tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"])) for fk in foreign}
            assert actual_fk == expected_fk, f"Foreign key target mismatch: {name}"
            assert all(fk["options"].get("ondelete") == "RESTRICT" for fk in foreign), f"Deletion policy mismatch: {name}"
            checks = inspector.get_check_constraints(name)
            expected_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
            assert expected_checks.issubset({c["name"] for c in checks}), f"Missing check: {name}"
            uniques = inspector.get_unique_constraints(name)
            expected_unique = {tuple(c.name for c in constraint.columns) for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
            assert expected_unique.issubset({tuple(u["column_names"]) for u in uniques}), f"Missing unique key: {name}"
            indexes = inspector.get_indexes(name)
            for expected in table.indexes:
                assert any(index["name"] == expected.name and index["unique"] == expected.unique for index in indexes), f"Missing index: {name}"
            paths = [tuple(primary)] + [tuple(u["column_names"]) for u in uniques] + [tuple(i["column_names"]) for i in indexes]
            for fk in foreign:
                key = tuple(fk["constrained_columns"])
                assert any(path[:len(key)] == key for path in paths), f"Foreign key has no leading index: {name}"
            result["tables"][name] = {"rows": connection.scalar(select(func.count()).select_from(table)), "primary_key": primary,
                                      "foreign_keys": len(foreign), "checks": len(checks), "unique_keys": len(uniques), "indexes": [i["name"] for i in indexes]}
        exclusion = connection.scalar(text("SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND t.relname='events' AND c.conname='ex_events_venue_time'"))
        assert exclusion and "EXCLUDE USING gist" in exclusion and "tstzrange" in exclusion and "cancelled" in exclusion
        assert connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='btree_gist')"))
        result["venue_exclusion"] = exclusion
        queries = {
            "seat_count": "SELECT count(*) FROM registrations WHERE event_id = 0 AND status IN ('registered', 'attended')",
            "upcoming": "SELECT event_id FROM events WHERE status='scheduled' AND start_time > CURRENT_TIMESTAMP ORDER BY start_time LIMIT 10",
            "expense_totals": "SELECT e.event_id, COALESCE(SUM(x.amount), 0.00) FROM events e LEFT JOIN event_expenses x ON x.event_id=e.event_id GROUP BY e.event_id",
        }
        for name, query in queries.items():
            result["plans"][name] = list(connection.execute(text("EXPLAIN (FORMAT TEXT) " + query)).scalars())
        result["plan_limit"] = "Plans reflect the current small development dataset; they are not load benchmarks or evidence to add indexes. No EXPLAIN ANALYZE was run."
        return result


if __name__ == "__main__":
    try:
        print(json.dumps(audit(), indent=2, default=str))
    except SQLAlchemyError:
        print("Database audit failed. Check local configuration; driver details suppressed.", file=sys.stderr)
        sys.exit(1)
