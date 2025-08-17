import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Get Telegram API credentials
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")