import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Get Telegram API credentials
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")
# Telethon StringSession, so the scraper doesn't depend on a session file
# surviving on disk between runs (Render's filesystem is ephemeral).
TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "")

# Flask session/cookie signing key.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")