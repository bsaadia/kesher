import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models.message import Base, Message
from models.location import Location
from datetime import datetime
from telethon import TelegramClient
import os
import asyncio
from app.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

@pytest.fixture(scope="function")
def db_session():
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session
    
    session.close()

@pytest_asyncio.fixture(scope="function")
async def telegram_client(request):
    session_name = "session"
    
    # Initialize the client. It will find the existing session file
    client = TelegramClient(session_name, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    try:
        # This will automatically reconnect using the session file
        await client.start(phone=TELEGRAM_PHONE)
        yield client  # Provide the connected client to the test
    finally:
        if client.is_connected():
            await client.disconnect()

@pytest.fixture
def message_factory(db_session):
    def _create(**kwargs):
        defaults = {"text": "test message", "timestamp": datetime.utcnow(), "channel": "test"}
        defaults.update(kwargs)
        msg = Message(**defaults)
        db_session.add(msg)
        db_session.commit()
        db_session.refresh(msg)
        return msg
    return _create

@pytest.fixture
def location_factory(db_session):
    def _create(**kwargs):
        defaults = {"name_he": "מיקום בדיקה", "name_en": "Test Location", "lat": 1.0, "lon": 1.0}
        defaults.update(kwargs)
        loc = Location(**defaults)
        db_session.add(loc)
        db_session.commit()
        db_session.refresh(loc)
        return loc
    return _create
