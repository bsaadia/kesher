# scripts/load_gazetteer.py

import csv
import os
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

# Import from your app
from models.db import get_session, init_db
from models.location import Location

GAZETTEER_PATH = os.path.join("data", "gaza_gazetteer.csv")


def load_gazetteer_to_db(db_session: Optional[Session], csv_path: str) -> None:
    """
    Load locations from a CSV file into the Location table.

    If db_session is None, a session is created via get_session() and closed here.
    If a Session is provided (e.g. from tests), it is used and left open for the caller.
    Uses SQLAlchemy 2.0 style queries (select + .scalars()).
    """
    created_session = False
    session = db_session
    if session is None:
        session = get_session()
        created_session = True

    if not os.path.exists(csv_path):
        print(f"⚠️ CSV file not found: {csv_path}")
        if created_session:
            session.close()
        return

    locations = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                name = (row.get("name") or row.get("Name") or row.get("hebrew_name") or "").strip()
                if not name:
                    continue

                # modern SQLAlchemy: check existence with select + scalars().first()
                stmt = select(Location).where(Location.name == name)
                exists = session.execute(stmt).scalars().first()
                if exists:
                    continue

                try:
                    latitude = float(row.get("latitude") or 0)
                except (ValueError, TypeError):
                    latitude = 0.0
                try:
                    longitude = float(row.get("longitude") or 0)
                except (ValueError, TypeError):
                    longitude = 0.0

                location = Location(
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    region=row.get("region"),
                    country=row.get("country"),
                )
                locations.append(location)

        if locations:
            session.add_all(locations)
            session.commit()
            print(f"✅ Loaded {len(locations)} new locations.")
        else:
            print("⚠️ No new locations to add.")
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        print(f"❌ Failed to load gazetteer: {exc}")
        raise
    finally:
        if created_session:
            session.close()


def main():
    """Entry point for the script."""
    print("Initializing database...")
    init_db()  # creates tables if not existing
    db_session = get_session()

    print(f"Loading gazetteer from {GAZETTEER_PATH} ...")
    load_gazetteer_to_db(db_session, GAZETTEER_PATH)

    db_session.close()
    print("Done.")


if __name__ == "__main__":
    main()
