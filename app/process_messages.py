"""
Run location and activity matching on all existing messages in the DB.
Use this to populate message_locations / message_activities without re-scraping Telegram.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.base import engine, Base
from models.message import Message
from models.associations import MessageLocation, MessageActivity
from models.location import Location
from models.activity import Activity
from app.processor.processing import (
    load_gazetteer_to_db_if_empty,
    load_activities_to_db_if_empty,
    process_message,
)
from sqlalchemy.orm import Session
from sqlalchemy import select

# Ensure any newly-added tables (e.g. activities / message_activities) exist.
Base.metadata.create_all(engine)

with Session(engine) as session:
    session.query(MessageActivity).delete()
    session.query(MessageLocation).delete()
    session.query(Activity).delete()
    session.query(Location).delete()
    session.commit()
    print("Cleared existing associations, locations, and activities.")

    load_gazetteer_to_db_if_empty(session)
    load_activities_to_db_if_empty(session)

    messages = session.execute(select(Message)).scalars().all()
    print(f"Processing {len(messages)} messages...")

    for i, message in enumerate(messages):
        process_message(session, message)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(messages)}")

    loc_count = session.execute(select(MessageLocation)).scalars().all()
    act_count = session.execute(select(MessageActivity)).scalars().all()
    print(f"Done. Created {len(loc_count)} location and {len(act_count)} activity associations.")
