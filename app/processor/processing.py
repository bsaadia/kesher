import re
import pandas as pd
import os
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from models.location import Location
from models.activity import Activity
from models.message import Message
from models.associations import MessageLocation, MessageActivity


GAZETTEER_PATH = os.path.join("scrap", "gazetteer", "geocoded_locations_new.csv")
ACTIVITY_TAGS_PATH = os.path.join("scrap", "gazetteer", "activity_tags.csv")

# For ambiguous location names, exclude matches where the name is preceded
# by one of these words (indicating a compound phrase, not the place itself).
# Separator between the word and the name may be a space or a hyphen (e.g.
# "עוטף-עזה"), so the trailing separator is added by the pattern builder
# rather than being baked into the strings here.
COMPOUND_EXCLUSIONS = {
    'עזה': ['רצועת', 'אוגדת', 'חטיבת', 'מחוז', 'נפת', 'עיריית', 'עוטף'],
    'חבלה': ['מטען', 'מטעני', 'חומר', 'חומרי', 'אמצעי', 'פעולת', 'פעולות', 'מעבדת', 'ציוד', 'לבנות', 'פתילי'],
    'רמון': ['מצפה', 'נמל התעופה', 'שדה התעופה', 'בסיס', 'בסיס חיל האוויר'],
}

# Whole matched tokens to reject for specific names.
# Needed when a prefix letter (ב/כ/ל/מ/ש/ה/ו) combined with the name
# spells a common Hebrew word unrelated to the location.
WORD_EXCLUSIONS = {
    'צור': {'מצור'},    # מצור = siege, not "from Tyre"
    'חמד': {'מחמד'},    # מחמד = the name Mohammed, not "Hamad"
    'ירון': {'מירון', 'לירון'},  # מירון = Meron; לירון = the first name "Liron"
    'רמיה': {'כרמיה'},  # כרמיה = Karmia (an unrelated kibbutz)
    'קטנה': {'הקטנה'},  # הקטנה = "the small one" (e.g. "עזה הקטנה"), not the village
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


def load_activities_to_db_if_empty(db_session: Session):
    """
    Loads the distinct activity categories from the activity tags CSV into the
    database if the Activity table is empty. Only categories with at least one
    "active" term are loaded; "deferred"/ambiguous terms are ignored.
    Args:
        db_session: SQLAlchemy Session object
    Returns:
        None
    """
    if db_session.scalar(select(func.count()).select_from(Activity)) == 0:
        tags = pd.read_csv(ACTIVITY_TAGS_PATH)
        active = tags[tags["status"] == "active"]
        for category in active["category"].unique():
            db_session.add(Activity(category=category))
        db_session.commit()


# Cache of (category, compiled_pattern) tuples for the active activity terms,
# built once from the tags CSV on first use. Each pattern matches the Hebrew
# term as a whole word, allowing an optional single-letter prefix (ב/כ/ל/מ/ש/ה/ו),
# mirroring the location matching in find_locations_in_message.
_activity_terms = None


def _load_activity_terms():
    global _activity_terms
    if _activity_terms is None:
        tags = pd.read_csv(ACTIVITY_TAGS_PATH)
        active = tags[tags["status"] == "active"]
        terms = []
        for row in active.itertuples(index=False):
            pattern = re.compile(r"\b(?:[בכלמשהו])?" + re.escape(row.term_he) + r"\b")
            terms.append((row.category, pattern))
        _activity_terms = terms
    return _activity_terms


def find_activities_in_message(db_session: Session, message: Message):
    """
    Finds activity terms within the text of a single message and creates
    message-activity associations for each distinct category matched.

    A message may match several categories (e.g. an air strike that also caused
    casualties); each category is associated at most once, the same way multiple
    locations are handled in find_locations_in_message.
    Args:
        db_session: SQLAlchemy Session object.
        message: The Message object to process.
    """
    result = db_session.execute(select(Activity))
    activity_by_category = {a.category: a for a in result.scalars().all()}

    found_categories = set()
    for category, pattern in _load_activity_terms():
        if category in found_categories:
            continue
        if pattern.search(message.text):
            found_categories.add(category)

    for category in found_categories:
        activity = activity_by_category.get(category)
        if activity is None:
            continue
        association = MessageActivity(message_id=message.id, activity_id=activity.id)
        db_session.add(association)

    if found_categories:
        db_session.commit()


def find_locations_in_message(db_session: Session, message: Message, locations=None):
    """
    Finds locations from the gazetteer within the text of a single message
    using whole word matching, and creates associations in the database.
    Args:
        db_session: SQLAlchemy Session object.
        message: The Message object to process.
        locations: Optional pre-fetched list of Location rows, so a caller
            processing many messages in one run can query the table once
            instead of once per message. Queried fresh if not provided.
    """
    if locations is None:
        result = db_session.execute(select(Location))
        locations = result.scalars().all()

    found_locations = set()  # Use a set to avoid duplicate location matches
    for loc in locations:
        # Search for Hebrew name
        if loc.name_he:
            name_pattern = re.escape(loc.name_he).replace("'", "'?")
            exclusions = COMPOUND_EXCLUSIONS.get(loc.name_he, [])
            lookbehinds = ''.join(f'(?<!{re.escape(p)}[ \\-])' for p in exclusions)
            pattern_he = lookbehinds + r"\b(?:[בכלמשהו])?" + name_pattern + r"\b"
            word_excl = WORD_EXCLUSIONS.get(loc.name_he, set())
            for m in re.finditer(pattern_he, message.text):
                if m.group() not in word_excl:
                    found_locations.add(loc)
                    break

    if not found_locations:
        return found_locations

    for loc in found_locations:
        association = MessageLocation(message_id=message.id, location_id=loc.id)
        db_session.add(association)

    db_session.commit()
    return found_locations


def process_message(db_session: Session, message: Message, locations=None):
    """
    Fully processes a single message: extracts locations, and — only when the
    message mentions at least one location — extracts activity categories.

    Args:
        db_session: SQLAlchemy Session object.
        message: The Message object to process.
        locations: Optional pre-fetched list of Location rows; see
            find_locations_in_message.
    """
    found_locations = find_locations_in_message(db_session, message, locations=locations)
    if found_locations:
        find_activities_in_message(db_session, message)


def process_messages(db_session: Session, messages):
    """
    Runs location and activity extraction over a collection of messages, creating
    the corresponding associations for each. Used by both the full seed and the
    incremental update so the two paths share identical processing logic.

    Locations are queried once for the whole batch rather than once per message,
    since re-querying the (effectively static) gazetteer table per message is
    pure overhead that gets expensive over a real network connection.

    Args:
        db_session: SQLAlchemy Session object.
        messages: Iterable of Message objects to process.
    """
    locations = db_session.execute(select(Location)).scalars().all()
    for message in messages:
        process_message(db_session, message, locations=locations)


# Initialize any resources needed by the processing system
def initialize_processing():
    """
    Initializes the processing system by setting up necessary resources.
    Returns:
        None
    """
    # In the future, this could prepare resources needed for async processing
    pass