from telethon import TelegramClient
from datetime import datetime, timezone
from typing import List, Dict
from models.db import MessageStorage
from models.message import Message
from sqlalchemy import select
from sqlalchemy.orm import Session
import asyncio
from bidi.algorithm import get_display
from app.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
import csv

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
    
    async for message in client.iter_messages(channel, limit=limit):
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
    
    async for message in client.iter_messages(channel, offset_date=end_date):
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

def save_messages_to_db(db_session: Session, messages: List[Dict[str, str]]) -> List[Message]:
    """
    Saves scraped messages to the database, skipping any whose (telegram_id, channel)
    already exists. Inserts survivors in a single batch and returns the newly created
    Message objects so callers can process only the new rows.

    Args:
        db_session: SQLAlchemy Session object.
        messages: List of scraped message dicts with 'id', 'date', 'text', 'sender_id'.

    Returns:
        List[Message]: The Message objects that were inserted (empty if all were dupes).
    """
    if not messages:
        print("No messages to save.")
        return []

    # Load the (telegram_id, channel) pairs already stored for the incoming channels,
    # so we can dedup in one query instead of per-row lookups.
    channels = {str(m['sender_id']) for m in messages}
    existing = set(
        db_session.execute(
            select(Message.telegram_id, Message.channel).where(Message.channel.in_(channels))
        ).all()
    )

    new_messages: List[Message] = []
    seen = set()  # guard against duplicates within this batch too
    for message in messages:
        telegram_id = message['id']
        channel = str(message['sender_id'])
        key = (telegram_id, channel)
        if key in existing or key in seen:
            continue
        seen.add(key)
        new_messages.append(Message(
            telegram_id=telegram_id,
            timestamp=message['date'],
            text=message['text'] or '',
            channel=channel,
        ))

    if new_messages:
        MessageStorage(db_session).batch_add_messages(new_messages)
    print(f"Saved {len(new_messages)} new messages to database "
          f"({len(messages) - len(new_messages)} skipped as duplicates).")
    return new_messages
    
def export_messages_to_csv(messages: List[Dict[str, str]], filename: str) -> None:
    with open(filename, mode='w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'date', 'text', 'sender_id']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for message in messages:
            writer.writerow(message)
    print(f"Exported {len(messages)} messages to {filename}.")

def export_messages_to_txt(messages: List[Dict[str, str]], filename: str) -> None:
    with open(filename, mode='w', encoding='utf-8') as textfile:
        for message in messages:
            textfile.write(f"ID: {message['id']}\n")
            textfile.write(f"Date: {message['date']}\n")
            textfile.write(f"Text: {message['text']}\n")
            textfile.write("\n")
    print(f"Exported {len(messages)} messages to {filename}.")

async def get_messages_since(client: TelegramClient, channel: str, last_id: int) -> List[Dict[str, str]]:
    """
    Fetches messages from a Telegram channel that are strictly newer than a given
    message ID, using Telethon's ``min_id`` cursor. This is the incremental fetch used
    to catch the database up to the present without re-pulling the whole history.

    Args:
        client: An instance of the Telegram client.
        channel: The identifier (username, ID, or entity) of the Telegram channel to fetch messages from.
        last_id (int): The highest message ID already stored; only messages with a larger id are returned.

    Returns:
        list: A list of dictionaries, each containing the 'id', 'date', 'text', and 'sender_id' of a message,
        ordered oldest-first.
    """
    messages = []

    async for message in client.iter_messages(channel, min_id=last_id, reverse=True):
        messages.append({
            'id': message.id,
            'date': message.date,
            'text': message.text,
            'sender_id': message.sender_id
        })
    return messages
