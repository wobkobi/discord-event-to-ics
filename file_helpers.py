"""file_helpers.py – path helpers and JSON/ICS persistence (no type-hints)."""

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from ics import Calendar

from config import BASE_URL, DATA_DIR

log = logging.getLogger(__name__)

# URL + path helpers 


def feed_url(uid):
    """Return the public *webcal://* URL for a user's .ics feed."""
    host = urlparse(BASE_URL).netloc
    return f"webcal://{host}/cal/{uid}.ics"


def idx_path(uid):
    return DATA_DIR / f"{uid}.json"


def ics_path(uid):
    return DATA_DIR / f"{uid}.ics"


# JSON index I/O


def load_index(uid):
    """Read the user's JSON index. Return an empty list on any problem."""
    try:
        raw = idx_path(uid).read_text()
        data = json.loads(raw) if raw.strip() else []
        log.info("Loaded index for user %s, %d entries", uid, len(data))
        return data
    except Exception:
        log.exception("Failed loading index for user %s", uid)
        return []


def save_index(uid, idx):
    try:
        idx_path(uid).write_text(json.dumps(idx))
        log.info("Saved index for user %s, %d entries", uid, len(idx))
    except Exception:
        log.exception("Failed saving index for user %s", uid)


# file existence guard


def ensure_files(uid):
    """Guarantee both JSON and ICS files exist for this user."""
    try:
        if not idx_path(uid).exists():
            log.info("Creating new index file for user %s", uid)
            save_index(uid, [])

        if not ics_path(uid).exists():
            log.info("Creating new ICS feed file for user %s", uid)
            ics_path(uid).write_bytes(Calendar().serialize().encode())
    except Exception:
        log.exception("Failed ensuring files for user %s", uid)
