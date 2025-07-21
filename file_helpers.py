# file_helpers.py – reads and writes user and guild data

import json
from pathlib import Path

from config import BASE_URL

# where we store everything
DATA_DIR = Path("calendars")
GUILD_DIR = DATA_DIR / "guilds"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GUILD_DIR.mkdir(parents=True, exist_ok=True)

# helpers for paths


def ics_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.ics"


def index_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


# user index helpers


def ensure_files(user_id: int) -> None:
    # create an empty index if it doesn’t exist yet
    p = index_path(user_id)
    if not p.exists():
        p.write_text("[]")


def load_index(user_id: int) -> list[dict]:
    # get the list of events the user is subscribed to
    return json.loads(index_path(user_id).read_text())


def save_index(user_id: int, idx: list[dict]) -> None:
    # write the updated event list back to disk
    index_path(user_id).write_text(json.dumps(idx))


# guild alert helpers


def _gcfg(gid: int) -> Path:
    return GUILD_DIR / f"{gid}.json"


def load_guild_alerts(guild_id: int) -> tuple[int, int | None]:
    # return (first_alert, second_alert) in minutes
    p = _gcfg(guild_id)
    if p.exists():
        data = json.loads(p.read_text())
        a1 = int(data.get("alert1", 60))
        a2_raw = data.get("alert2")
        a2 = int(a2_raw) if a2_raw is not None else None
        return a1, a2
    return 60, None


def save_guild_alerts(guild_id: int, alert1: int, alert2: int | None) -> None:
    # store the default alerts for this guild
    json.dump({"alert1": alert1, "alert2": alert2}, _gcfg(guild_id).open("w"))


# build the public webcal url for a user


def feed_url(user_id: int) -> str:
    return f"webcal://{BASE_URL}/cal/{user_id}.ics"
