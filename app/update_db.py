import sys
import os
from datetime import datetime, timezone
import asyncio

# Add the project root to the python path so we can import app and models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.scraper.scrape_telegram import (
    save_messages_to_db,
    fetch_messages_in_date_range,
    get_messages_since,
    init_scraper,
    close_scraper,
)
from app.processor.processing import (
    load_gazetteer_to_db_if_empty,
    load_activities_to_db_if_empty,
    process_messages,
)
from models.base import engine
from models.message import Message
from sqlalchemy.orm import Session
from sqlalchemy import func, select

CHANNEL = "@idf_telegram"
SEED_START_DATE = datetime(2023, 10, 7, tzinfo=timezone.utc)


async def update_database_to_current():
    """
    Brings the database up to the present by appending only messages newer than what is
    already stored — no wiping, no full re-scrape.

    - Ensures the gazetteer exists (never deletes).
    - Watermarks off MAX(telegram_id) and fetches only strictly-newer messages.
    - Dedups + inserts the new messages, then geolocates just those new rows.

    Schema is managed by Alembic (`alembic upgrade head`), not this script.
    """
    with Session(engine) as session:
        load_gazetteer_to_db_if_empty(session)
        load_activities_to_db_if_empty(session)

        # Highest Telegram message id we already have. NULL/None => empty DB.
        last_id = session.scalar(select(func.max(Message.telegram_id)))

    client = await init_scraper()

    if last_id is None:
        print("Database is empty; performing initial fetch from Oct 7, 2023.")
        end_date = datetime.now(timezone.utc)
        scraped_messages = await fetch_messages_in_date_range(
            client, CHANNEL, SEED_START_DATE, end_date
        )
    else:
        print(f"Fetching messages newer than telegram_id {last_id} from '{CHANNEL}'...")
        scraped_messages = await get_messages_since(client, CHANNEL, last_id)

    await close_scraper(client)

    print(f"Fetched {len(scraped_messages)} candidate messages.")

    with Session(engine) as session:
        new_messages = save_messages_to_db(session, scraped_messages)

        if new_messages:
            print(f"Processing {len(new_messages)} new messages for locations and activities...")
            process_messages(session, new_messages)

        latest = session.scalar(select(func.max(Message.timestamp)))
        total = session.scalar(select(func.count()).select_from(Message))
        print(f"Update complete. Added {len(new_messages)} messages. "
              f"DB now holds {total} messages up to {latest}.")


if __name__ == "__main__":
    asyncio.run(update_database_to_current())
