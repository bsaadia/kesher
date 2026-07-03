import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models.message import Base, Message
from models.location import Location
from models.associations import MessageLocation
from datetime import datetime
from telethon import TelegramClient
import os
import asyncio
from unittest.mock import patch
from app import create_app
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
    counter = {"n": 0}

    def _create(**kwargs):
        counter["n"] += 1
        defaults = {
            "telegram_id": counter["n"],
            "text": "test message",
            "timestamp": datetime.utcnow(),
            "channel": "test",
        }
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

@pytest.fixture
def association_factory(db_session):
    def _create(message, location):
        assoc = MessageLocation(message_id=message.id, location_id=location.id)
        db_session.add(assoc)
        db_session.commit()
        return assoc
    return _create

@pytest.fixture
def client(db_session):
    """
    Create a Flask test client.
    We patch 'app.Session' so that the Flask app uses the test database session
    instead of creating a new one connected to the production DB.
    """
    with patch('app.Session', return_value=db_session):
        app = create_app()
        app.config['TESTING'] = True
        
        with app.test_client() as client:
            yield client
