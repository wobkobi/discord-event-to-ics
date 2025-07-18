# calendar_builder.py (RFC 5545‑compliant location & recurrence handling)
import asyncio
import logging
import datetime as dt
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ics import Calendar, Event, Geo

from file_helpers import ics_path, load_index, save_index
from config import TIMEZONE, DATA_DIR, POLL_INTERVAL
from bot_setup import bot

log = logging.getLogger(__name__)

# Regex for simple “<lat>,<lon>” detection
_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")


def _apply_location(e: Event, meta: Any, guild_id: int, ev_id: int) -> None:
    """Add LOCATION / GEO / URL fields according to RFC 5545."""
    if meta is None:
        return

    # Physical address or free‑text location
    loc = getattr(meta, "location", None)
    loc_url = getattr(meta, "location_url", None)

    if loc:
        e.location = loc  # Always include LOCATION text

        # Detect latitude, longitude pair → GEO property
        m = _LAT_LON.match(loc)
        if m:
            lat, lon = map(float, m.groups())
            e.geo = Geo(latitude=lat, longitude=lon)
        else:
            # Provide a Maps URL for convenience
            e.url = f"https://www.google.com/maps/search/{quote_plus(loc)}"

    elif loc_url:
        # Online meeting or external link
        e.location = loc_url  # LOCATION text per RFC
        e.url = loc_url  # URL parameter (same value)

    else:
        # Discord voice/stage/text channel fallback
        ch_id = (
            getattr(meta, "channel_id", None)
            or getattr(meta, "channel", None)
            or getattr(meta, "location", None)
        )
        if ch_id:
            try:
                channel = bot.cache.get_channel(int(ch_id))
                chan_name = channel.name if channel else f"id {ch_id}"
                e.location = f"Discord channel: {chan_name}"
            except Exception:
                e.location = f"Discord channel id {ch_id}"
            e.url = f"https://discord.com/events/{guild_id}/{ev_id}"


def _apply_recurrence(e: Event, recurrence: Optional[List[str]]) -> None:
    """Copy Discord recurrence strings to RFC 5545 RRULE lines."""
    if not recurrence:
        return

    # The ics library does not have a direct 'rrule' attribute; add RRULE(s) as extra properties.
    e.extra.append(("RRULE", recurrence[0]))
    for extra_rule in recurrence[1:]:
        # Store additional rules in extra properties list
        e.extra.append(("RRULE", extra_rule))


def event_to_ics(ev: Any, guild_id: int) -> Event:
    """Convert a Discord ScheduledEvent into an RFC 5545‑compliant ICS Event."""
    e = Event()

    # Title & timing
    e.name = ev.name
    e.begin = ev.start_time.astimezone(TIMEZONE)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(
        TIMEZONE
    )
    e.description = (ev.description or "").strip()

    # Recurrence (RRULE)
    _apply_recurrence(e, getattr(ev, "recurrence", None))

    # Location / GEO / URL
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    return e


async def rebuild_calendar(uid: int, idx: List[Dict[str, int]]) -> None:
    """Re‑fetch events and write a new ICS file for the user asynchronously."""
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
            if getattr(e, "status", None) == 404:
                log.info(f"Event {event_id} vanished; dropping from user {uid}")
            else:
                log.exception(f"Error fetching {event_id}: {e}")
                updated_idx.append(rec)

    if updated_idx != idx:
        save_index(uid, updated_idx)

    ics_path(uid).write_bytes(cal.serialize().encode())
    log.info(f"Saved calendar for {uid} with {len(cal.events)} events")


async def poll_new_events() -> None:
    """Background task: refresh all feeds every POLL_INTERVAL minutes."""
    await asyncio.sleep(5)
    while True:
        for json_idx in DATA_DIR.glob("*.json"):
            try:
                uid = int(json_idx.stem)
            except ValueError:
                continue
            idx = load_index(uid)
            if idx:
                await rebuild_calendar(uid, idx)
        await asyncio.sleep(POLL_INTERVAL * 60)
