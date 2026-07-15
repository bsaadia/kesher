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

def test_compound_after_exclusion_bare_name_collision(db_session, message_factory, location_factory):
    # Location name "ירון" (Yaroun, Lebanon) bare-matches the first name of
    # Maj. Gen. Yaron Finkelman with no prefix involved at all -- the
    # WORD_EXCLUSIONS-style bare_word mechanism can't catch this since the
    # matched surface form ("ירון") is legitimately the place name too; only
    # the following word disambiguates it.
    location_factory(name_he="ירון")
    msg = message_factory(text="מפקד פיקוד הדרום, אלוף ירון פינקלמן, ערך סיור בגבול.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_compound_after_exclusion_still_matches_genuine_mention(db_session, message_factory, location_factory):
    # Genuine "Yaroun" village mentions (no "פינקלמן" following) must still match.
    loc = location_factory(name_he="ירון")
    msg = message_factory(text="כוחות צה\"ל פעלו הלילה בכפר ירון שבדרום לבנון.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()
    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_geresh_is_required_not_optional(db_session, message_factory, location_factory):
    # Location name "ח'דר" (Khadar, with geresh) must not match the ordinary
    # word "חדר" ("room") just because the geresh was dropped -- the old
    # `.replace("'", "'?")` hack made the geresh optional, which is exactly
    # what let this collision through.
    location_factory(name_he="ח'דר")
    msg = message_factory(text="עד למפגש המפתיע בחדר 303 בבה\"ד 1.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_geresh_variant_spellings_still_match(db_session, message_factory, location_factory):
    # Genuine mentions must still match regardless of which visually-similar
    # apostrophe/geresh character was typed (straight apostrophe, Hebrew
    # geresh, or curly quote all mean the same thing here).
    loc = location_factory(name_he="ח'דר")  # gazetteer CSV spells it with a straight apostrophe
    for geresh_char in ["'", "׳", "’"]:
        msg = message_factory(text=f"המחבל ח{geresh_char}דר אלשהאביה פיקד על מרחב הר דב.")
        find_locations_in_message(db_session, msg)
        result = db_session.execute(
            select(MessageLocation).where(MessageLocation.message_id == msg.id)
        ).scalars().all()
        assert len(result) == 1, f"expected a match for geresh variant {geresh_char!r}"
        assert result[0].location_id == loc.id

def test_gershayim_does_not_fracture_acronym(db_session, message_factory, location_factory):
    # Location name "חמא" (Hama, Syria) must not match inside חמא"ס ("Hamas")
    # -- gershayim is not a \w character in Python's regex engine, so a plain
    # \b treats it as a word boundary and lets "חמא" match as if it were a
    # standalone bounded token.
    location_factory(name_he="חמא")
    msg = message_factory(text="הלחימה נגד ארגון הטרור חמא\"ס ברצועת עזה נמשכת.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_gershayim_genuine_standalone_mention_still_matches(db_session, message_factory, location_factory):
    # A genuine standalone mention of the city (not embedded in an acronym)
    # must still match.
    loc = location_factory(name_he="חמא")
    msg = message_factory(text="מטוסי קרב תקפו מטרות בסביבות העיר חמא שבסוריה.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()
    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_single_letter_word_plus_quote_still_matches(db_session, message_factory, location_factory):
    # "ה'עבסנים'" is the single-letter word "ה" (the) directly touching an
    # opening scare-quote, not a multi-letter acronym fragment -- unlike
    # חמא"ס, this must still match. A naive "mark = word boundary" fix (mark
    # has a word character on only one side => not a boundary) would
    # incorrectly treat ה+quote the same as an internal acronym marker and
    # reject the match entirely.
    loc = location_factory(name_he="עבסנים")
    msg = message_factory(text="סיירת גבעתי נגד ה'עבסנים'. רגעי הקרב שטרם סופר.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()
    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_compound_exclusion_extended_habla_triggers(db_session, message_factory, location_factory):
    # The original COMPOUND_EXCLUSIONS list for "חבלה" missed several common
    # preceding words found in a full sweep of the message table; these must
    # now be excluded too.
    location_factory(name_he="חבלה")
    for text in [
        "נשקים, מחסניות ומטעני נפץ וחבלה שהוטמנו בשטח.",
        "כוחות החבלה של מג\"ב איו\"ש פעלו במקום.",
        "עצרו 25 מחבלים ואיתרו מעבדות חבלה ואמל\"ח.",
        "המנהרה הושמדה באמצעות חבלה מבוקרת.",
    ]:
        msg = message_factory(text=text)
        find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_compound_before_and_after_exclusions_for_tzur(db_session, message_factory, location_factory):
    # "צור" (Tyre, Lebanon) bare-matches several unrelated same-spelling
    # places and an idiom; each needs its own compound exclusion.
    location_factory(name_he="צור")
    for text in [
        "בקבוקי תבערה לעבר היישוב כרמי צור שבחטיבת עציון.",   # Karmei Tzur
        "קפצו לפני זמן קצר לסלעית וצור יצחק.",                    # Tzur Yitzhak
        "תת-אלוף (במיל') רמי צור חכם התראיין הבוקר.",             # a person's name
        "מתבקש לצור קשר עם מוקד זה בהקדם.",                       # idiom "make contact"
    ]:
        msg = message_factory(text=text)
        find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

def test_compound_exclusions_still_match_genuine_tzur_mention(db_session, message_factory, location_factory):
    loc = location_factory(name_he="צור")
    msg = message_factory(text="צה\"ל תקף אתמול מטרות בפרברי העיר צור שבדרום לבנון.")

    find_locations_in_message(db_session, msg)

    result = db_session.execute(
        select(MessageLocation).where(MessageLocation.message_id == msg.id)
    ).scalars().all()
    assert len(result) == 1
    assert result[0].location_id == loc.id

def test_bare_word_exclusion_common_verb_and_noun(db_session, message_factory, location_factory):
    # "דוחה" (Doha) and "סעדה" (Sa'dah) are both, in their bare/prefixed form,
    # ordinary Hebrew words -- a verb and a noun respectively.
    location_factory(name_he="דוחה")
    location_factory(name_he="סעדה")
    for text in [
        "צה\"ל דוחה על הסף את הטענה שהועלתה בתקשורת.",
        "כ-140,000 מנות הסעדה מחולקות מידי יום ברצועת עזה.",
    ]:
        msg = message_factory(text=text)
        find_locations_in_message(db_session, msg)

    result = db_session.execute(select(MessageLocation)).scalars().all()
    assert len(result) == 0

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