# file_helpers.py – path helpers and JSON/ICS persistence (no type-hints).

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from ics import Calendar

from config import BASE_URL, DATA_DIR

log = logging.getLogger(__name__)


def feed_url(uid):
    """Return the public webcal:// URL for a user's .ics feed."""
    host = urlparse(BASE_URL).netloc
    return f"webcal://{host}/cal/{uid}.ics"


def idx_path(uid):
    """Path to the JSON index for a given user ID."""
    return DATA_DIR / f"{uid}.json"


def ics_path(uid):
    """Path to the .ics file for a given user ID."""
    return DATA_DIR / f"{uid}.ics"


def load_index(uid):
    """Load a user's event index from disk; return [] on error."""
    try:
        raw = idx_path(uid).read_text()
        data = json.loads(raw) if raw.strip() else []
        log.info("Loaded index for user %s, %d entries", uid, len(data))
        return data
    except Exception:
        log.exception("Failed loading index for user %s", uid)
        return []


def save_index(uid, idx):
    """Save a user's event index to disk."""
    try:
        idx_path(uid).write_text(json.dumps(idx))
        log.info("Saved index for user %s, %d entries", uid, len(idx))
    except Exception:
        log.exception("Failed saving index for user %s", uid)


def ensure_files(uid):
    """Ensure both the JSON index and the .ics file exist."""
    try:
        if not idx_path(uid).exists():
            log.info("Creating new index file for user %s", uid)
            save_index(uid, [])

        if not ics_path(uid).exists():
            log.info("Creating new ICS feed file for user %s", uid)
            ics_path(uid).write_bytes(Calendar().serialize().encode())
    except Exception:
        log.exception("Failed ensuring files for user %s", uid)


#                           user settings I/O


def settings_path(uid):
    """Path to the user settings JSON."""
    return DATA_DIR / f"{uid}.settings.json"


def load_settings(uid):
    """Load alert & default-length settings; return defaults on error."""
    p = settings_path(uid)
    if not p.exists():
        return {"alerts": [0], "default_length": 60}
    try:
        return json.loads(p.read_text())
    except Exception:
        log.exception("Failed loading settings for user %s", uid)
        return {"alerts": [0], "default_length": 60}


def save_settings(uid, settings):
    """Save alert & default-length settings."""
    try:
        settings_path(uid).write_text(json.dumps(settings))
        log.info("Saved settings for user %s  to  %s", uid, settings)
    except Exception:
        log.exception("Failed saving settings for user %s", uid)
