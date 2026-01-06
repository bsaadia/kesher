import re
import pandas as pd
import os
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from models.location import Location
from models.message import Message
from models.associations import MessageLocation


GAZETTEER_PATH = os.path.join("scrap", "gaza_gazetteer.csv")


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
            pattern_he = r"\b(?:[בכלמשהו])?" + re.escape(loc.name_he) + r"\b"
            if re.search(pattern_he, message.text):  # No IGNORECASE for Hebrew typically
                found_locations.add(loc)

    if not found_locations:
        return

    for loc in found_locations:
        association = MessageLocation(message_id=message.id, location_id=loc.id)
        db_session.add(association)

    db_session.commit()


# Initialize any resources needed by the processing system
def initialize_processing():
    """
    Initializes the processing system by setting up necessary resources.
    Returns:
        None
    """
    # In the future, this could prepare resources needed for async processing
    pass