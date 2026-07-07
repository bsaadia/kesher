"""
One-time data migration: copy rows from the legacy db.sqlite3 file into the
Postgres database pointed to by DATABASE_URL.

Assumes the target schema already exists (`alembic upgrade head`).
Safe to run against local dev Postgres or, later, Render's production
Postgres (via its external connection string) -- it refuses to run if any
target table already has rows, so it can't silently duplicate data.
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, select, text

from models.base import DATABASE_URL
from models.message import Message
from models.location import Location
from models.activity import Activity
from models.associations import MessageLocation, MessageActivity

SQLITE_URL = "sqlite:///db.sqlite3"

# Parents before children, so foreign keys always resolve.
TABLES_IN_ORDER = [
    Activity.__table__,
    Location.__table__,
    Message.__table__,
    MessageLocation.__table__,
    MessageActivity.__table__,
]


def migrate():
    if DATABASE_URL.startswith("sqlite"):
        raise SystemExit(
            "DATABASE_URL is still pointing at SQLite. Set it to a Postgres "
            "URL (local docker-compose DB or Render's connection string) "
            "before running this migration."
        )

    source_engine = create_engine(SQLITE_URL)
    target_engine = create_engine(DATABASE_URL)

    with source_engine.connect() as src_conn, target_engine.begin() as tgt_conn:
        for table in TABLES_IN_ORDER:
            if tgt_conn.execute(select(table).limit(1)).first() is not None:
                raise SystemExit(
                    f"Target table '{table.name}' already has data; aborting "
                    "to avoid duplicating rows."
                )

        for table in TABLES_IN_ORDER:
            rows = [dict(row._mapping) for row in src_conn.execute(select(table))]
            if not rows:
                print(f"{table.name}: no rows to copy")
                continue
            tgt_conn.execute(table.insert(), rows)
            print(f"{table.name}: copied {len(rows)} rows")

        # Rows were inserted with explicit ids, so each table's identity
        # sequence needs to be advanced past the max id we just inserted.
        for table in TABLES_IN_ORDER:
            if "id" not in table.c:
                continue
            tgt_conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table.name}), 1))"
            ))

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
