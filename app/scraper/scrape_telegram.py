from telethon import TelegramClient
from datetime import datetime, timezone
from typing import List, Dict
from models.db import MessageStorage
from sqlalchemy.orm import Session

import asyncio
from bidi.algorithm import get_display
from app.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
# from models.db import MessageStorage
# from models.message import Message

async def init_scraper()-> TelegramClient:
    """
    Initializes and starts a TelegramClient session asynchronously.

    Returns:
        TelegramClient: An instance of the TelegramClient after successful authentication and startup.
    """
    client = TelegramClient('session', TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start(phone=TELEGRAM_PHONE)
    return client

async def close_scraper(client: TelegramClient)-> None:
    """
    Asynchronously closes the Telegram client connection if it is currently connected.

    Args:
        client: An instance of the Telegram client to be disconnected.

    Returns:
        None
    """
    if client.is_connected():
        await client.disconnect()

async def fetch_past_messages(client: TelegramClient, channel: str, limit: int=10) -> List[Dict[str, str]]:
    """
    Asynchronously fetches a specified number of past messages from a Telegram channel.
    Args:
        client: An instance of the Telegram client.
        channel: The identifier (username, ID, or entity) of the Telegram channel to fetch messages from.
        limit (int, optional): The maximum number of messages to retrieve. Defaults to 10.
    Returns:
        list: A list of dictionaries, each containing the 'id', 'date', 'text', and 'sender_id' of a message.
    Raises:
        Any exceptions raised by the Telegram client or during message retrieval.
    """
    messages = []
    
    async with client.takeout() as takeout:
        async for message in takeout.iter_messages(channel, limit=limit):
            messages.append({
                'id': message.id,
                'date': message.date,
                'text': message.text,
                'sender_id': message.sender_id
            })
    return messages

async def fetch_messages_in_date_range(client: TelegramClient, channel: str, start_date: datetime, end_date: datetime) -> List[Dict[str, str]]:
    """
    Asynchronously fetches messages from a Telegram channel within a specified date range.

    Args:
        client: An instance of the Telegram client.
        channel: The identifier (username, ID, or entity) of the Telegram channel to fetch messages from.
        start_date (datetime): The start date of the range.
        end_date (datetime): The end date of the range.

    Returns:
        list: A list of dictionaries, each containing the 'id', 'date', 'text', and 'sender_id' of a message.

    Raises:
        Any exceptions raised by the Telegram client or during message retrieval.
    """
    messages = []
    
    async with client.takeout() as takeout:
        async for message in takeout.iter_messages(channel, offset_date=end_date):
            if message.date < start_date:
                break
            if start_date <= message.date <= end_date:
                messages.append({
                    'id': message.id,
                    'date': message.date,
                    'text': message.text,
                    'sender_id': message.sender_id
                })
    return messages

def save_messages_to_db(db_session: Session, messages: List[Dict[str, str]]) -> None:
    storage = MessageStorage(db_session)
    for message in messages:
        timestamp = message['date']
        text = get_display(message['text']) if message['text'] else ''
        channel = message['sender_id']
        storage.add_message(timestamp=timestamp, text=text, channel=channel)
    print("Saved messages to database.")