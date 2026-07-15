import sys
import os
import traceback
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
from models.base import DATABASE_URL, build_engine
from models.message import Message
from sqlalchemy.orm import Session
from sqlalchemy import func, select

CHANNEL = "@idf_telegram"
SEED_START_DATE = datetime(2023, 10, 7, tzinfo=timezone.utc)


def _target_engines():
    """
    Databases to bring up to date in this run. DATABASE_URL is always
    included -- it's production when run via the hourly cron
    (scripts/run_hourly_update.sh sources .env.production) or local when run
    by hand against .env. LOCAL_DATABASE_URL is an optional second target: if
    set, the local dev DB is kept in lockstep with production in the same
    run, so it never drifts out of sync between manual gazetteer/matcher
    fixes (which is what required a manual local<->prod reconciliation
    before this).

    Returns an ordered dict-like list of (name, engine, required) tuples;
    "required" targets propagate failures, optional ones only warn -- local
    Postgres being asleep/offline shouldn't break the hourly prod update.
    """
    targets = [("DATABASE_URL", build_engine(DATABASE_URL), True)]
    local_url = os.getenv("LOCAL_DATABASE_URL")
    if local_url:
        targets.append(("LOCAL_DATABASE_URL", build_engine(local_url), False))
    return targets


async def update_database_to_current():
    """
    Brings every configured target database (see _target_engines) up to the
    present by appending only messages newer than what's already stored — no
    wiping, no full re-scrape. Telegram is fetched exactly once and the same
    batch is written to each target; save_messages_to_db dedups per-target,
    so a target that's already caught up simply skips what it has.

    - Ensures the gazetteer exists in each target (never deletes).
    - Watermarks off the OLDEST MAX(telegram_id) across all targets, so a
      target that's fallen behind gets caught back up in the same pass.
    - Dedups + inserts the new messages per target, then geolocates just
      those new rows.

    Schema is managed by Alembic (`alembic upgrade head`), not this script.
    """
    targets = _target_engines()

    last_ids = []
    for name, target_engine, required in targets:
        with Session(target_engine) as session:
            load_gazetteer_to_db_if_empty(session)
            load_activities_to_db_if_empty(session)
            last_ids.append(session.scalar(select(func.max(Message.telegram_id))))

    # Highest Telegram message id we already have, taken across ALL targets
    # so none of them get skipped ahead. None (empty DB) forces a full fetch.
    last_id = None if any(x is None for x in last_ids) else min(last_ids)

    client = await init_scraper()

    if last_id is None:
        print("At least one target DB is empty; performing initial fetch from Oct 7, 2023.")
        end_date = datetime.now(timezone.utc)
        scraped_messages = await fetch_messages_in_date_range(
            client, CHANNEL, SEED_START_DATE, end_date
        )
    else:
        print(f"Fetching messages newer than telegram_id {last_id} from '{CHANNEL}'...")
        scraped_messages = await get_messages_since(client, CHANNEL, last_id)

    await close_scraper(client)

    print(f"Fetched {len(scraped_messages)} candidate messages.")

    for name, target_engine, required in targets:
        try:
            with Session(target_engine) as session:
                new_messages = save_messages_to_db(session, scraped_messages)

                if new_messages:
                    print(f"[{name}] Processing {len(new_messages)} new messages for locations and activities...")
                    process_messages(session, new_messages)

                latest = session.scalar(select(func.max(Message.timestamp)))
                total = session.scalar(select(func.count()).select_from(Message))
                print(f"[{name}] Update complete. Added {len(new_messages)} messages. "
                      f"DB now holds {total} messages up to {latest}.")
        except Exception:
            if required:
                raise
            print(f"[{name}] WARNING: optional target failed, continuing without it.")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(update_database_to_current())
