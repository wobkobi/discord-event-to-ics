import asyncio
import logging
import datetime as dt
from typing import Any, Dict, List

from ics import Calendar, Event

from file_helpers import ics_path, load_index, save_index
from config import TIMEZONE, DATA_DIR, POLL_INTERVAL
from bot_setup import bot

log = logging.getLogger(__name__)


def event_to_ics(ev: Any, guild_id: int) -> Event:
    """Convert a Discord ScheduledEvent into an ics Event."""
    e = Event()
    e.name = ev.name
    start = ev.start_time.astimezone(TIMEZONE)
    end_dt = ev.end_time or (ev.start_time + dt.timedelta(hours=1))
    e.begin = start
    e.end = end_dt.astimezone(TIMEZONE)
    e.description = (ev.description or "")[:2000]
    meta = getattr(ev, "entity_metadata", None)
    if meta and getattr(meta, "location", None):
        e.location = meta.location  # type: ignore
    elif getattr(ev, "channel_id", None):
        e.location = f"Discord channel {ev.channel_id}"
    e.url = f"https://discord.com/events/{guild_id}/{ev.id}"
    return e


async def rebuild_calendar(uid: int, idx: List[Dict[str, int]]) -> None:
    """Re-fetch events and write a new ICS file for the user asynchronously.
    Remove any events that return 404 Not Found."""
    log.info(f"Rebuilding calendar for user {uid}")
    cal = Calendar()
    updated_idx: List[Dict[str, int]] = []
    for rec in idx:
        guild_id = rec["guild_id"]
        event_id = rec["id"]
        try:
            ev = await bot.fetch_scheduled_event(guild_id, event_id)
            if ev:
                cal.events.add(event_to_ics(ev, guild_id))
                updated_idx.append(rec)
        except Exception as e:
            status = getattr(e, "status", None)
            if status == 404:
                log.info(
                    f"Event {event_id} not found in guild {guild_id}, removing from index for user {uid}"
                )
            else:
                log.exception(f"Error fetching event {rec} for user {uid}")
                updated_idx.append(rec)
    if updated_idx != idx:
        save_index(uid, updated_idx)
    path = ics_path(uid)
    path.write_bytes(cal.serialize().encode())
    log.info(f"Calendar rebuilt and saved for user {uid}")


async def poll_new_events() -> None:
    """Background task: refresh all user feeds every POLL_INTERVAL minutes."""
    log.info(f"Starting background polling every {POLL_INTERVAL} minutes")
    await asyncio.sleep(5)
    while True:
        log.info("Polling calendars for updates...")
        for file in DATA_DIR.glob("*.json"):
            try:
                uid = int(file.stem)
            except ValueError:
                continue
            idx = load_index(uid)
            if idx:
                await rebuild_calendar(uid, idx)
        await asyncio.sleep(POLL_INTERVAL * 60)
