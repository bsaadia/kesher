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

# Basemap for the Plotly maps. MAP_STYLE_URL is a style.json URL template with
# a {key} slot; the key is substituted in from MAP_API_KEY. With no key set we
# fall back to Plotly's built-in "carto-positron" so local dev still works.
MAP_API_KEY = os.getenv("MAP_API_KEY", "")
MAP_STYLE_URL = os.getenv(
    "MAP_STYLE_URL",
    "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json?api_key={key}",
)


def map_style():
    """Value for Plotly's ``mapbox_style``: a keyed style URL, or the built-in fallback."""
    if MAP_API_KEY:
        return MAP_STYLE_URL.format(key=MAP_API_KEY)
    return "carto-positron"
