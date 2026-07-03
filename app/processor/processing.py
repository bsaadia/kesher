import re
import pandas as pd
import os
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from models.location import Location
from models.message import Message
from models.associations import MessageLocation


GAZETTEER_PATH = os.path.join("scrap", "geocoded_locations.csv")

# For ambiguous location names, exclude matches where the name is preceded
# by one of these strings (indicating a compound phrase, not the place itself).
COMPOUND_EXCLUSIONS = {
    'עזה': ['רצועת ', 'אוגדת ', 'חטיבת ', 'מחוז ', 'נפת ', 'עיריית '],
}

# Whole matched tokens to reject for specific names.
# Needed when a prefix letter (ב/כ/ל/מ/ש/ה/ו) combined with the name
# spells a common Hebrew word unrelated to the location.
WORD_EXCLUSIONS = {
    'צור': {'מצור'},   # מצור = siege, not "from Tyre"
}


def load_gazetteer_to_db_if_empty(db_session: Session):
    """
    Loads gazetteer data into the database if the Location table is empty.
    This is a synchronous, one-time setup function.
    Args:
        db_session: SQLAlchemy Session object
    Returns:
        None
    """
    # Check if the Location table is empty
    if db_session.scalar(select(func.count()).select_from(Location)) == 0:
        # Load gazetteer data from a predefined source
        gazetteer_data = pd.read_csv(GAZETTEER_PATH).to_dict(orient="records")

        for loc in gazetteer_data:
            if pd.isna(loc.get("lat")) or pd.isna(loc.get("lon")):
                continue

            location = Location(
                name_he=loc["name_he"],
                name_en=loc["name_en"],
                name_ar=loc.get("name_ar") or None,
                front=loc.get("front") or None,
                lat=loc["lat"],
                lon=loc["lon"]
            )
            db_session.add(location)

        db_session.commit()


def find_locations_in_message(db_session: Session, message: Message):
    """
    Finds locations from the gazetteer within the text of a single message
    using whole word matching, and creates associations in the database.
    Args:
        db_session: SQLAlchemy Session object.
        message: The Message object to process.
    """
    result = db_session.execute(select(Location))
    locations = result.scalars().all()

    found_locations = set()  # Use a set to avoid duplicate location matches
    for loc in locations:
        # Search for Hebrew name
        if loc.name_he:
            name_pattern = re.escape(loc.name_he).replace("'", "'?")
            exclusions = COMPOUND_EXCLUSIONS.get(loc.name_he, [])
            lookbehinds = ''.join(f'(?<!{p})' for p in exclusions)
            pattern_he = lookbehinds + r"\b(?:[בכלמשהו])?" + name_pattern + r"\b"
            word_excl = WORD_EXCLUSIONS.get(loc.name_he, set())
            for m in re.finditer(pattern_he, message.text):
                if m.group() not in word_excl:
                    found_locations.add(loc)
                    break

    if not found_locations:
        return

    for loc in found_locations:
        association = MessageLocation(message_id=message.id, location_id=loc.id)
        db_session.add(association)

    db_session.commit()


def process_messages_for_locations(db_session: Session, messages):
    """
    Runs location extraction over a collection of messages, creating message-location
    associations for each. Used by both the full seed and the incremental update so the
    two paths share identical processing logic.

    Args:
        db_session: SQLAlchemy Session object.
        messages: Iterable of Message objects to process.
    """
    for message in messages:
        find_locations_in_message(db_session, message)


# Initialize any resources needed by the processing system
def initialize_processing():
    """
    Initializes the processing system by setting up necessary resources.
    Returns:
        None
    """
    # In the future, this could prepare resources needed for async processing
    pass