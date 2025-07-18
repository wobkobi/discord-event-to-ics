"""config.py – project settings without static-type hints."""

import datetime as dt
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load values from .env (if present)
load_dotenv()

# ───────────────────────── logging ─────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Quiet noisy libraries
logging.getLogger("interactions").setLevel(logging.CRITICAL)


class _Ignore404(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return not (msg.startswith("GET::https") and "404" in msg)


logging.getLogger("interactions").addFilter(_Ignore404())

# ───────────────────────── env config ──────────────────────────────────────

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("⚠️  DISCORD_TOKEN env var is required")

BASE_URL = os.getenv("BASE_URL", "http://localhost").rstrip("/")
HTTP_PORT = int(os.getenv("HTTP_PORT", "9000"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))  # minutes

TIMEZONE = dt.datetime.now().astimezone().tzinfo  # system TZ

DATA_DIR = Path(os.getenv("DATA_DIR", "calendars"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
