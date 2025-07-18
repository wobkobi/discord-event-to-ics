import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import datetime

# Load environment variables from .env
load_dotenv()

# Configure root logger for essential info and above
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Suppress verbose logs from underlying libraries and filter HTTP 404s
logging.getLogger("interactions").setLevel(logging.CRITICAL)


class Ignore404Filter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # Drop only HTTP GET 404 logs from interactions
        return not (msg.startswith("GET::https") and "404" in msg)


logging.getLogger("interactions").addFilter(Ignore404Filter())

# Discord bot token (required)
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("⚠️ DISCORD_TOKEN environment variable is required")

# Base URL for serving calendar feeds, e.g., https://calendar.example.com
BASE_URL = os.getenv("BASE_URL", "http://localhost").rstrip("/")

# HTTP port for the aiohttp server
HTTP_PORT = int(os.getenv("HTTP_PORT", "9000"))

# Timezone for event times: detect from system clock
TIMEZONE = datetime.datetime.now().astimezone().tzinfo

# Poll interval in minutes for refreshing feeds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

# Directory to store per-user JSON indices and .ics files
data_dir = os.getenv("DATA_DIR", "calendars")
DATA_DIR = Path(data_dir)
DATA_DIR.mkdir(parents=True, exist_ok=True)
