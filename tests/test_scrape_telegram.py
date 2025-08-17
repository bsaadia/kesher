from app.scraper.scrape_telegram import init_scraper, close_scraper, fetch_past_messages, fetch_messages_in_date_range, save_messages_to_db
import pytest
from datetime import datetime, timezone
from models.message import Message
from sqlalchemy import select

# test initialization and closure of the scraper
@pytest.mark.asyncio
async def test_init_and_close_scraper():
    client = await init_scraper()
    assert client is not None
    assert client.is_connected()
    await close_scraper(client)
    assert not client.is_connected()

# test fetching past messages from a channel
@pytest.mark.asyncio
async def test_fetch_past_messages(telegram_client):
    channel = '@idf_telegram'
    messages = await fetch_past_messages(telegram_client, channel, limit=5)
    assert len(messages) <= 5
    for message in messages:
        assert 'id' in message
        assert 'date' in message
        assert 'text' in message
        assert 'sender_id' in message
    await close_scraper(telegram_client)

# test fetching messages in a date range
@pytest.mark.asyncio
async def test_fetch_messages_in_date_range(telegram_client):
    channel = '@idf_telegram'
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 1, 2, tzinfo=timezone.utc)
    
    messages = await fetch_messages_in_date_range(telegram_client, channel, start_date, end_date)
    print(len(messages))
    assert len(messages) > 0
    for message in messages:
        assert 'id' in message
        assert 'date' in message
        assert 'text' in message
        assert 'sender_id' in message
    await close_scraper(telegram_client)

# test saving messages to the database
@pytest.mark.asyncio
async def test_save_messages_to_db(telegram_client, db_session):
    channel = '@idf_telegram'
    messages = await fetch_past_messages(telegram_client, channel, limit=5)
    save_messages_to_db(db_session, messages)
    
    assert len(messages) > 0
    db_messages = db_session.execute(select(Message)).scalars().all()
    assert len(db_messages) == len(messages)