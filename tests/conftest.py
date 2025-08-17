import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models.message import Base
from telethon import TelegramClient
import os
import asyncio
from app.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

@pytest.fixture
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
