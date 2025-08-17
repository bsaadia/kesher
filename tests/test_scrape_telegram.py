from app.scraper.scrape_telegram import init_scraper, close_scraper, fetch_past_messages
import pytest

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

