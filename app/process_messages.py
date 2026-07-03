"""
Run location matching on all existing messages in the DB.
Use this to populate message_locations without re-scraping Telegram.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.base import engine
from models.message import Message
from models.associations import MessageLocation
from models.location import Location
from app.processor.processing import load_gazetteer_to_db_if_empty, find_locations_in_message
from sqlalchemy.orm import Session
from sqlalchemy import select

with Session(engine) as session:
    session.query(MessageLocation).delete()
    session.query(Location).delete()
    session.commit()
    print("Cleared existing associations and locations.")

    load_gazetteer_to_db_if_empty(session)

    messages = session.execute(select(Message)).scalars().all()
    print(f"Processing {len(messages)} messages...")

    for i, message in enumerate(messages):
        find_locations_in_message(session, message)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(messages)}")

    count = session.execute(select(MessageLocation)).scalars().all()
    print(f"Done. Created {len(count)} associations.")
