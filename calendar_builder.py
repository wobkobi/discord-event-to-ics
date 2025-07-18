# calendar_builder.py – RFC 5545-compliant location & recurrence handling (no ics.geo dependency)
import asyncio
import logging
import datetime as dt
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ics import Calendar, Event

from file_helpers import ics_path, load_index, save_index
from config import TIMEZONE, DATA_DIR, POLL_INTERVAL
from bot_setup import bot

log = logging.getLogger(__name__)

# Regex for simple “<lat>,<lon>” detection → RFC 5545 GEO param
_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")


def _apply_location(e: Event, meta: Any, guild_id: int, ev_id: int) -> None:
    """Add LOCATION / GEO / URL fields according to RFC 5545, without ics.geo."""
    if meta is None:
        return

    loc = getattr(meta, "location", None)
    loc_url = getattr(meta, "location_url", None)

    if loc:
        e.location = loc
        # GEO parameter if the location is explicit lat,long
        m = _LAT_LON.match(loc)
        if m:
            e.extra.append(("GEO", f"{m.group(1)};{m.group(2)}"))
        else:
            # Convenience clickable link
            e.url = f"https://www.google.com/maps/search/{quote_plus(loc)}"

    elif loc_url:
        e.location = loc_url
        e.url = loc_url

    else:
        ch_id = getattr(meta, "channel_id", None)
        if ch_id:
            try:
                channel = bot.cache.get_channel(int(ch_id))
                chan_name = channel.name if channel else f"id {ch_id}"
                e.location = f"Discord channel: {chan_name}"
            except Exception:
                e.location = f"Discord channel id {ch_id}"
            e.url = f"https://discord.com/events/{guild_id}/{ev_id}"


def _apply_recurrence(e: Event, recurrence: Optional[List[str]]) -> None:
    """Attach RRULE lines via extra properties (ics-py has no .rrule attribute)."""
    if not recurrence:
        return
    for rule in recurrence:
        e.extra.append(("RRULE", rule))


def event_to_ics(ev: Any, guild_id: int) -> Event:
    e = Event()
    e.name = ev.name
    e.begin = ev.start_time.astimezone(TIMEZONE)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(
        TIMEZONE
    )
    e.description = (ev.description or "").strip()

    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    return e


async def rebuild_calendar(uid: int, idx: List[Dict[str, int]]) -> None:
    cal = Calendar()
    updated_idx: List[Dict[str, int]] = []

    for rec in idx:
        gid = rec["guild_id"]
        eid = rec["id"]
        try:
            ev = await bot.fetch_scheduled_event(gid, eid)
            if ev:
                cal.events.add(event_to_ics(ev, gid))
                updated_idx.append(rec)
        except Exception as e:
            if getattr(e, "status", None) == 404:
                log.info(f"Event {eid} removed – pruning for user {uid}")
            else:
                log.exception(f"Error fetching {eid}: {e}")
                updated_idx.append(rec)

    if updated_idx != idx:
        save_index(uid, updated_idx)

    ics_path(uid).write_bytes(cal.serialize().encode())
    log.info(f"Saved calendar for {uid}: {len(cal.events)} events")


async def poll_new_events() -> None:
    await asyncio.sleep(5)
    while True:
        for p in DATA_DIR.glob("*.json"):
            try:
                uid = int(p.stem)
            except ValueError:
                continue
            idx = load_index(uid)
            if idx:
                await rebuild_calendar(uid, idx)
        await asyncio.sleep(POLL_INTERVAL * 60)
