import time
import random
from sqlalchemy import select, delete, func
from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from models.associations import MessageLocation
from models.message import Message
from models.location import Location
from app.processor.processing import find_locations_in_message


# Test loading gazetteer data into the database
def test_load_gazetteer_to_db_if_empty(db_session):
    from app.processor.processing import load_gazetteer_to_db_if_empty
    from models.location import Location

    # Ensure the Location table is empty
    db_session.execute(delete(Location))
    db_session.commit()

    # Load gazetteer data
    load_gazetteer_to_db_if_empty(db_session)

    # Verify that locations were added
    location_count = db_session.scalar(select(func.count()).select_from(Location))
    assert location_count > 0

def test_find_single_location_in_message(db_session, message_factory, location_factory):
    # Create a location and a message that contains the location's Hebrew name
    loc = location_factory(name_he="עזה")
    msg = message_factory(text="התקפה באזור עזה.")

    # Run the function to find locations
    find_locations_in_message(db_session, msg)

    # Verify that the association was created
    result = db_session.execute(
        select(MessageLocation).where(
            MessageLocation.message_id == msg.id,
            MessageLocation.location_id == loc.id
        )
    ).scalar_one_or_none()

    assert result is not None

def test_no_location_in_message(db_session, message_factory, location_factory):
    # Create a location and a message that does NOT contain the location's name
    location_factory(name_he="עזה")
    msg = message_factory(text="אין כאן שמות של מקומות.")

    # Run the function
    find_locations_in_message(db_session, msg)

    # Verify that no association was created
    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_multiple_mentions_of_same_location(db_session, message_factory, location_factory):
    # Create a location and a message that mentions it multiple times
    loc = location_factory(name_he="רפיח")
    msg = message_factory(text="קרבות ברפיח, פינוי אוכלוסיה מרפיח.")

    # Run the function
    find_locations_in_message(db_session, msg)

    # Verify that only ONE association was created
    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()

    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_location_name_as_substring(db_session, message_factory, location_factory):
    # Location name is "בית" but the message contains "ביתו" which should not match.
    location_factory(name_he="בית")
    msg = message_factory(text="ביקרנו בביתו של החייל.") # "בביתו" contains "בית"

    # Run the function
    find_locations_in_message(db_session, msg)

    # Verify no association was created because it's not a whole word match
    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_multiple_locations_in_one_message(db_session, message_factory, location_factory):
    # Create multiple locations
    loc1 = location_factory(name_he="שדרות")
    loc2 = location_factory(name_he="נתיבות")
    msg = message_factory(text=".ירי לעבר שדרות ונתיבות")

    # Run the function
    find_locations_in_message(db_session, msg)

    # Verify that both associations were created
    results = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()

    assert len(results) == 2
    found_loc_ids = {res.location_id for res in results}
    assert {loc1.id, loc2.id} == found_loc_ids

def test_prefix_fusion_word_exclusion(db_session, message_factory, location_factory):
    # Location name is "חמד" (Hamad) but "מחמד" (the name Mohammed) should not
    # match, since the ambiguous prefix letter מ fuses onto the name.
    location_factory(name_he="חמד")
    msg = message_factory(text="צה\"ל חיסל את מחמד קטמאש, בכיר בארגון הטרור חמאס.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_prefix_fusion_still_matches_genuine_mention(db_session, message_factory, location_factory):
    # Genuine "Hamad" neighborhood mentions must still match.
    loc = location_factory(name_he="חמד")
    msg = message_factory(text="כוחות אוגדה 98 ממשיכים במבצע בשכונת \"חמד\" במערב חאן יונס.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()
    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_compound_exclusion_common_noun(db_session, message_factory, location_factory):
    # Location name is "חבלה" (Habla) but "מטען חבלה" (explosive charge) is a
    # common noun phrase unrelated to the village.
    location_factory(name_he="חבלה")
    msg = message_factory(text="הלוחמים איתרו מספר מטעני חבלה בשטח.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_compound_exclusion_still_matches_genuine_mention(db_session, message_factory, location_factory):
    # Genuine "Habla" village mentions must still match.
    loc = location_factory(name_he="חבלה")
    msg = message_factory(text="כוחות צה\"ל פעלו הלילה בכפר חבלה שבחטיבת אפרים.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()
    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_performance_of_find_locations_in_message(db_session, message_factory, location_factory):
    """
    Measures and prints the performance of processing a batch of messages.
    This is not a strict benchmark but gives a good indication of speed.
    """
    NUM_LOCATIONS = 500
    NUM_MESSAGES = 100

    # 1. Create locations
    locations = [location_factory(name_he=f"מיקום_{i}") for i in range(NUM_LOCATIONS)]

    # 2. Create messages
    messages = []
    for i in range(NUM_MESSAGES):
        text = f"הודעת בדיקה מספר {i}. "
        # ~50% of messages will contain a location
        if random.random() > 0.5:
            loc = random.choice(locations)
            text += f"האזעקה נשמעה ב{loc.name_he}."
        messages.append(message_factory(text=text))
    
    # 3. Time the processing
    start_time = time.time()

    for msg in messages:
        find_locations_in_message(db_session, msg)

    end_time = time.time()

    # 4. Print results
    duration = end_time - start_time
    messages_per_second = NUM_MESSAGES / duration if duration > 0 else float('inf')

    print(f"\n--- Performance Test ---")
    print(f"Processed {NUM_MESSAGES} messages against {NUM_LOCATIONS} locations.")
    print(f"Total time: {duration:.4f} seconds.")
    print(f"Messages per second: {messages_per_second:.2f}.")
    print(f"----------------------")

    # Basic assertion to ensure it's not catastrophically slow
    assert duration < 30