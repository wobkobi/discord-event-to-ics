# file_helpers.py

import json
import logging
from pathlib import Path
from typing import List, Dict

from ics import Calendar

from config import BASE_URL, DATA_DIR

log = logging.getLogger(__name__)


def feed_url(uid: int) -> str:

    # turn https://calendar.example.com into webcal://calendar.example.com
    from urllib.parse import urlparse

    parsed = urlparse(BASE_URL)
    host = parsed.netloc
    return f"webcal://{host}/cal/{uid}.ics"


def idx_path(uid: int) -> Path:
    """
    Path to the JSON index for a given user ID.
    """
    return DATA_DIR / f"{uid}.json"


def ics_path(uid: int) -> Path:
    """
    Path to the .ics file for a given user ID.
    """
    return DATA_DIR / f"{uid}.ics"


def load_index(uid: int) -> List[Dict[str, int]]:
    """
    Load a user's event index from disk.
    Returns an empty list on any error or if the file is empty.
    """
    try:
        raw = idx_path(uid).read_text()
        index = json.loads(raw) if raw.strip() else []
        log.info(f"Loaded index for user {uid}, {len(index)} entries")
        return index
    except Exception:
        log.exception(f"Failed loading index for user {uid}")
        return []


def save_index(uid: int, idx: List[Dict[str, int]]) -> None:
    """
    Save a user's event index to disk.
    """
    try:
        idx_path(uid).write_text(json.dumps(idx))
        log.info(f"Saved index for user {uid}, {len(idx)} entries")
    except Exception:
        log.exception(f"Failed saving index for user {uid}")


def ensure_files(uid: int) -> None:
    """
    Ensure that both the JSON index and ICS file exist for this user.
    If missing, create an empty index and an empty calendar.
    """
    try:
        idx_file = idx_path(uid)
        if not idx_file.exists():
            log.info(f"Creating new index file for user {uid}")
            save_index(uid, [])
        ics_file = ics_path(uid)
        if not ics_file.exists():
            log.info(f"Creating new ICS feed file for user {uid}")
            ics_file.write_bytes(Calendar().serialize().encode())
    except Exception:
        log.exception(f"Failed ensuring files for user {uid}")
