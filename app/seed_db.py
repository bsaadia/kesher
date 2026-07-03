import sys
import os
from datetime import datetime, timezone
import asyncio

# Add the project root to the python path so we can import app and models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.scraper.scrape_telegram import save_messages_to_db, fetch_messages_in_date_range, init_scraper, close_scraper
from app.processor.processing import load_gazetteer_to_db_if_empty, process_messages_for_locations
from models.base import engine, Base
from models.message import Message
from models.location import Location
from models.associations import MessageLocation
from sqlalchemy.orm import Session
from sqlalchemy import select

async def seed():
    """
    Resets the database and seeds it with fresh messages from Telegram.
    - Deletes all existing messages and location associations.
    - Ensures the gazetteer of locations is loaded.
    - Fetches messages from October 7th, 2023 onwards.
    - Populates the message-location associations table.
    """
    print("Rebuilding database schema (dropping and recreating all tables)...")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Database reset complete.")
    
    with Session(engine) as session:
        print("Loading gazetteer to DB if empty...")
        load_gazetteer_to_db_if_empty(session)

    client = await init_scraper()
    
    channel = "@idf_telegram"
    start_date = datetime(2023, 10, 7, tzinfo=timezone.utc)
    end_date = datetime.now(timezone.utc)
    
    print(f"Fetching messages from channel '{channel}' between {start_date} and {end_date}...")
    
    scraped_messages = await fetch_messages_in_date_range(client, channel, start_date, end_date)
            
    print(f"Found {len(scraped_messages)} messages since Oct 7, 2023.")
    
    if scraped_messages:
        with Session(engine) as session:
            save_messages_to_db(session, scraped_messages)
    else:
        print("No messages found to seed.")
        
    await close_scraper(client)

    # Process messages to find locations
    print("Processing messages to find locations...")
    with Session(engine) as session:
        # Get all messages from the DB
        result = session.execute(select(Message))
        messages_from_db = result.scalars().all()

        print(f"Found {len(messages_from_db)} messages in the database to process.")

        process_messages_for_locations(session, messages_from_db)

        print("Finished processing messages.")

if __name__ == "__main__":
    asyncio.run(seed())