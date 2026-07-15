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
from app.processor.hebrew_text import (
    normalize_hebrew_punctuation,
    BOUNDARY_START,
    BOUNDARY_END,
    CANONICAL_GERESH,
)


GAZETTEER_PATH = os.path.join("scrap", "gazetteer", "geocoded_locations_new.csv")
ACTIVITY_TAGS_PATH = os.path.join("scrap", "gazetteer", "activity_tags.csv")
EXCLUSIONS_PATH = os.path.join("scrap", "gazetteer", "match_exclusions.csv")

# Data-driven table of known false-match patterns for ambiguous gazetteer
# names, keyed by name_he. Generated and maintained via
# scripts/sweep_gazetteer_matches.py rather than hand-added as each collision
# is separately discovered in production. Exclusion types:
#   bare_word:        reject if the whole matched token equals this value
#                      (e.g. "מחמד" fusing the מ prefix onto "חמד").
#   compound_before:   reject if this word immediately precedes the match
#                      (separated by a space or hyphen), e.g. "מטען חבלה".
#   compound_after:    reject if this word immediately follows the match
#                      (separated by a space), e.g. "ירון פינקלמן".
#   require_geresh:    a geresh in this name is normally optional (messages
#                      often drop it, e.g. "רדואן" for "רדואן׳"), but for a
#                      handful of names dropping it spells a different real
#                      word (ח'דר -> חדר, "room"); those names opt out of the
#                      optional-geresh matching entirely.
_exclusions_cache = None


def _load_exclusions():
    global _exclusions_cache
    if _exclusions_cache is None:
        word_excl = {}
        compound_before = {}
        compound_after = {}
        require_geresh = set()
        rows = pd.read_csv(EXCLUSIONS_PATH).to_dict(orient="records")
        for row in rows:
            name_he = row["name_he"]
            kind = row["exclusion_type"]
            value = row["value"]
            if kind == "bare_word":
                word_excl.setdefault(name_he, set()).add(value)
            elif kind == "compound_before":
                compound_before.setdefault(name_he, []).append(value)
            elif kind == "compound_after":
                compound_after.setdefault(name_he, []).append(value)
            elif kind == "require_geresh":
                require_geresh.add(name_he)
        _exclusions_cache = (word_excl, compound_before, compound_after, require_geresh)
    return _exclusions_cache


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


def iter_location_matches(loc: Location, normalized_text: str, exclusions=None):
    """
    Yields each non-excluded regex match of a single location's Hebrew name
    within already-normalized message text (see normalize_hebrew_punctuation).

    Factored out of find_locations_in_message so that
    scripts/sweep_gazetteer_matches.py can audit exactly what the production
    matcher would tag, without duplicating (and risking drifting from) the
    matching logic itself.

    Args:
        loc: The Location row to match.
        normalized_text: Message text already passed through
            normalize_hebrew_punctuation.
        exclusions: Optional (word_excl_map, compound_before_map,
            compound_after_map, require_geresh_set) tuple as returned by
            _load_exclusions(). Loaded fresh if not provided.
    """
    if not loc.name_he:
        return

    word_excl_map, compound_before_map, compound_after_map, require_geresh_set = (
        exclusions or _load_exclusions()
    )

    name_pattern = re.escape(normalize_hebrew_punctuation(loc.name_he))
    if loc.name_he not in require_geresh_set:
        # A geresh is routinely dropped in casual writing (e.g. "רדואן" for
        # "רדואן׳"); only names proven to collide on the geresh-dropped
        # spelling (require_geresh) keep it mandatory -- see the note above
        # _load_exclusions.
        name_pattern = name_pattern.replace(re.escape(CANONICAL_GERESH), re.escape(CANONICAL_GERESH) + "?")
    compound_before = compound_before_map.get(loc.name_he, [])
    lookbehinds = ''.join(f'(?<!{re.escape(p)}[ \\-])' for p in compound_before)
    pattern_he = lookbehinds + BOUNDARY_START + r"(?:[בכלמשהו])?" + name_pattern + BOUNDARY_END

    word_excl = word_excl_map.get(loc.name_he, set())
    compound_after = compound_after_map.get(loc.name_he, [])
    after_pattern = None
    if compound_after:
        after_pattern = re.compile(
            r'[ \-]+(?:' + '|'.join(re.escape(w) for w in compound_after) + r')\b'
        )

    for m in re.finditer(pattern_he, normalized_text):
        if m.group() in word_excl:
            continue
        if after_pattern and after_pattern.match(normalized_text, m.end()):
            continue
        yield m


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

    exclusions = _load_exclusions()

    # Normalized once per message: canonicalizes geresh/gershayim variants so
    # a gazetteer name and the message text only need to agree on meaning,
    # not on which visually-similar apostrophe/quote character was typed.
    text = normalize_hebrew_punctuation(message.text)

    found_locations = set()  # Use a set to avoid duplicate location matches
    for loc in locations:
        for _ in iter_location_matches(loc, text, exclusions=exclusions):
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