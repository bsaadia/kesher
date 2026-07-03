from datetime import datetime, timezone

from sqlalchemy import select, func

from app.scraper.scrape_telegram import save_messages_to_db
from models.message import Message


def _scraped(msg_id, sender_id="test", text="hello"):
    return {
        "id": msg_id,
        "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "text": text,
        "sender_id": sender_id,
    }


def test_save_messages_persists_telegram_id(db_session):
    saved = save_messages_to_db(db_session, [_scraped(100), _scraped(101)])

    assert len(saved) == 2
    assert {m.telegram_id for m in saved} == {100, 101}
    assert db_session.scalar(select(func.count()).select_from(Message)) == 2


def test_save_messages_skips_existing_and_intra_batch_duplicates(db_session):
    # Pre-existing message with telegram_id 100 on channel "test".
    save_messages_to_db(db_session, [_scraped(100)])

    # Batch re-includes 100 (already stored) and 101 twice (dup within batch).
    saved = save_messages_to_db(
        db_session, [_scraped(100), _scraped(101), _scraped(101)]
    )

    assert [m.telegram_id for m in saved] == [101]
    total = db_session.scalar(select(func.count()).select_from(Message))
    assert total == 2  # only 100 and 101 exist, no duplicates


def test_same_telegram_id_different_channel_is_not_a_duplicate(db_session):
    save_messages_to_db(db_session, [_scraped(100, sender_id="chan_a")])
    saved = save_messages_to_db(db_session, [_scraped(100, sender_id="chan_b")])

    assert len(saved) == 1
    assert db_session.scalar(select(func.count()).select_from(Message)) == 2
