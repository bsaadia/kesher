"""
Full resync: replace everything in the production database with the current
contents of the local database (messages, gazetteer, activities, and their
associations).

Unlike migrate_sqlite_to_postgres.py (a one-time, empty-target migration),
this is meant to be re-run: it wipes the target tables first, so it can be
used any time the local DB (freshly scraped + reprocessed) should become the
new source of truth for production.

Uses a single bulk COPY per table (not row-by-row inserts) since round trips
to a remote host are the dominant cost -- a few COPY calls instead of tens of
thousands of individual statements.

Requires LOCAL_DATABASE_URL and DATABASE_URL (the production URL) to both be
set in the environment when this is run; it does not read .env/.env.production
itself; e.g.:

    LOCAL_DATABASE_URL=$(grep -oP '(?<=^DATABASE_URL=).*' .env) \\
    DATABASE_URL=$(grep -oP '(?<=^DATABASE_URL=).*' .env.production) \\
    python scripts/sync_local_to_production.py --yes
"""
import argparse
import csv
import io
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, select, text

from models.message import Message
from models.location import Location
from models.activity import Activity
from models.associations import MessageLocation, MessageActivity

# Parents before children (for load); reversed for clearing.
TABLES_IN_ORDER = [
    Message.__table__,
    Location.__table__,
    Activity.__table__,
    MessageLocation.__table__,
    MessageActivity.__table__,
]

# CSV can't natively distinguish NULL from an empty string (both render as an
# unquoted empty field under Python's csv module, whatever the quoting mode).
# Instead of relying on quoting heuristics, mark real Nones with this sentinel
# and tell Postgres COPY to treat exactly that literal as NULL -- any other
# unquoted-empty field is then unambiguously an empty string, and any quoted
# field is never NULL regardless of content.
NULL_SENTINEL = "\x01__SQLCOPY_NULL_7f3a9c__\x01"


def _normalize(url: str) -> str:
    return url.replace("postgres://", "postgresql://", 1) if url.startswith("postgres://") else url


def sync(local_url: str, prod_url: str):
    if "render.com" not in prod_url:
        raise SystemExit(
            "Refusing to run: DATABASE_URL (target) doesn't look like the "
            "production Render host. Pass the production URL explicitly."
        )
    if "render.com" in local_url:
        raise SystemExit(
            "Refusing to run: LOCAL_DATABASE_URL (source) looks like the "
            "production Render host, expected the local DB as the source."
        )

    source_engine = create_engine(_normalize(local_url), connect_args={"connect_timeout": 10})
    target_engine = create_engine(_normalize(prod_url), connect_args={"connect_timeout": 10})

    with source_engine.connect() as src_conn, target_engine.begin() as tgt_conn:
        raw = tgt_conn.connection
        cur = raw.cursor()

        # Clear children before parents.
        for table in reversed(TABLES_IN_ORDER):
            cur.execute(f"DELETE FROM {table.name}")
        print("Cleared production tables.")

        # Load parents before children.
        for table in TABLES_IN_ORDER:
            cols = [c.name for c in table.columns]
            rows = src_conn.execute(select(table)).fetchall()
            if not rows:
                print(f"{table.name}: no rows to copy")
                continue

            # messages.text is NOT NULL in the target schema; a handful of
            # legacy local rows predate that constraint and have NULL text
            # (e.g. image-only posts). Treat those as empty string, not NULL.
            text_idx = cols.index("text") if "text" in cols else None
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(cols)
            for row in rows:
                row = list(row)
                if text_idx is not None and row[text_idx] is None:
                    row[text_idx] = ""
                row = [NULL_SENTINEL if v is None else v for v in row]
                writer.writerow(row)
            buf.seek(0)

            col_list = ", ".join(cols)
            cur.copy_expert(
                f"COPY {table.name} ({col_list}) FROM STDIN WITH CSV HEADER NULL '{NULL_SENTINEL}'",
                buf,
            )
            print(f"{table.name}: copied {len(rows)} rows")

        # Rows were inserted with explicit ids; advance each identity sequence
        # past the max id so future ORM inserts don't collide.
        for table in TABLES_IN_ORDER:
            if "id" not in table.c:
                continue
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table.name}), 1))"
            )

    print("Sync complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Required to actually run (safety gate).")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Pass --yes to confirm you want to overwrite production with local data.")

    local_url = os.environ.get("LOCAL_DATABASE_URL")
    prod_url = os.environ.get("DATABASE_URL")
    if not local_url or not prod_url:
        raise SystemExit("Both LOCAL_DATABASE_URL and DATABASE_URL must be set.")

    sync(local_url, prod_url)
