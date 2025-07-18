# event_handlers.py – handle Discord event updates in real‑time
import logging
from typing import Any, Dict, List

from file_helpers import ensure_files, load_index, save_index
from calendar_builder import rebuild_calendar
from config import DATA_DIR
from bot_setup import bot

log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# 1)  User clicks “Interested” – already handled elsewhere, but we keep it here
# ────────────────────────────────────────────────────────────────────────────
@bot.listen("guild_scheduled_event_user_add")
async def on_interested(payload: Any) -> None:
    """When a member marks Interested, add the event to their index and rebuild."""
    uid = payload.user_id
    ensure_files(uid)
    rec: Dict[str, int] = {
        "guild_id": payload.guild_id,
        "id": payload.scheduled_event_id,
    }

    idx = load_index(uid)
    if not any(r["id"] == rec["id"] and r["guild_id"] == rec["guild_id"] for r in idx):
        idx.append(rec)
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info(f"Added event {rec['id']} to user {uid} and rebuilt calendar")


# ────────────────────────────────────────────────────────────────────────────
# 2)  Event gets UPDATED – propagate changes instantly
# ────────────────────────────────────────────────────────────────────────────
@bot.listen("guild_scheduled_event_update")
async def on_event_updated(ev: Any) -> None:
    # ev is a ScheduledEvent object.  Grab its guild ID safely
    gid = getattr(
        getattr(ev, "guild", None), "id", None
    )  # fallback if .guild_id missing
    if gid is None:
        gid = getattr(ev, "guild_id", None)

    eid = ev.id
    if gid is None:
        log.warning("event update without guild id – skipping")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx: List[Dict[str, int]] = load_index(uid)
        if any(r["id"] == eid and r["guild_id"] == gid for r in idx):
            await rebuild_calendar(uid, idx)
            log.info(f"Rebuilt calendar for {uid} after update to event {eid}")


# ────────────────────────────────────────────────────────────────────────────
# 3)  Event gets DELETED – remove and rebuild
# ────────────────────────────────────────────────────────────────────────────
@bot.listen("guild_scheduled_event_delete")
async def on_event_deleted(ev: Any) -> None:
    gid = ev.guild_id
    eid = ev.id

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx: List[Dict[str, int]] = load_index(uid)
        new_idx = [
            rec for rec in idx if not (rec["id"] == eid and rec["guild_id"] == gid)
        ]
        if new_idx != idx:
            save_index(uid, new_idx)
            await rebuild_calendar(uid, new_idx)
            log.info(
                f"Removed deleted event {eid} from user {uid} and rebuilt calendar"
            )


# ────────────────────────────────────────────────────────────────────────────
# 4)  Bot ready – start HTTP server & polling
# ────────────────────────────────────────────────────────────────────────────
from server import run_http  # late import to avoid circulars
from calendar_builder import poll_new_events
import asyncio


@bot.listen("ready")
async def on_ready(_: Any) -> None:
    """Kick off aiohttp server and calendar polling."""
    log.info("Bot is online; launching HTTP server and polling tasks.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
