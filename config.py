# config.py – project settings without static-type hints.

import os
import logging
import datetime as dt
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present
load_dotenv()

#                         Logging configuration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Quiet noisy libraries
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

#                           Environment variables

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not DISCORD_TOKEN:
    raise RuntimeError("⚠️ DISCORD_TOKEN environment variable is required")

# For fast guild-scoped command registration in development; leave empty or "0" for global only
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", "0"))

# Base URL for calendar feeds (used by slash commands and homepage)
BASE_URL = os.getenv("BASE_URL", "http://localhost").rstrip("/")

# HTTP server port for aiohttp
HTTP_PORT = int(os.getenv("HTTP_PORT", "9000"))

# Poll interval for refreshing calendars (in minutes)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

# Timezone for event times (auto-detected from system clock)
TIMEZONE = dt.datetime.now().astimezone().tzinfo

# Directory to store per-user JSON indices and .ics files
DATA_DIR = Path(os.getenv("DATA_DIR", "calendars"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
