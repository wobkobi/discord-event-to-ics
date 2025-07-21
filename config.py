# config.py – central settings for the bot
# loads values from .env, makes sure data dirs exist, and sets up logging

import datetime as dt
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# read .env file if present
load_dotenv()

# discord bot token
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN env var is required")

# base url for webcal links
BASE_URL = os.getenv("BASE_URL", "http://localhost").rstrip("/")

# small web server that serves .ics files
HTTP_PORT = int(os.getenv("HTTP_PORT", "9000"))

# how often to rebuild every user’s feed (minutes)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

# use the system timezone for all calendar output
TIMEZONE = dt.datetime.now().astimezone().tzinfo

# folder where .ics files and indexes live
DATA_DIR = Path(os.getenv("DATA_DIR", "calendars"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# basic logging config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# filter out noisy 404 lines from Pycord http logs
class _Ignore404(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not ("GET https" in record.getMessage() and "404" in record.getMessage())


logging.getLogger("discord.http").addFilter(_Ignore404())
