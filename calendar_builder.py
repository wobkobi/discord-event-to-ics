# calendar_builder.py – Clean, RFC 5545‑compliant builder
"""Builds per‑user iCalendar feeds from Discord Scheduled Events.
Compatible with Outlook, Apple Calendar, and Google Calendar.
"""

import asyncio
import datetime as dt
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ics import Calendar, Event, Geo
from ics.grammar.parse import ContentLine  # correct import path for ContentLine

from bot_setup import bot
from config import DATA_DIR, POLL_INTERVAL, TIMEZONE
from file_helpers import ics_path, load_index, save_index

log = logging.getLogger(__name__)

# Matches simple "lat,lon" strings – e.g. "40.6892,-74.0445"
_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _add_prop(component: Any, name: str, value: str) -> None:
    """Attach an extra ContentLine so ics‑py can clone/serialize safely."""
    component.extra.append(ContentLine(name=name, params={}, value=value))


# ---------------------------------------------------------------------------
# Location & recurrence handlers
# ---------------------------------------------------------------------------


def _apply_location(e: Event, meta: Any, guild_id: int, ev_id: int) -> None:
    """Populate LOCATION / GEO / URL according to RFC 5545."""
    if not meta:
        return

    loc: Optional[str] = getattr(meta, "location", None)
    loc_url: Optional[str] = getattr(meta, "location_url", None)

    if loc:
        e.location = loc
        if m := _LAT_LON.match(loc):
            e.geo = Geo(latitude=float(m.group(1)), longitude=float(m.group(2)))
        else:
            e.url = f"https://www.google.com/maps/search/{quote_plus(loc)}"
    elif loc_url:
        e.location = loc_url
        e.url = loc_url
    else:
        ch_id = getattr(meta, "channel_id", None)
        if ch_id:
            chan = bot.cache.get_channel(int(ch_id))
            chan_name = getattr(chan, "name", f"id {ch_id}") if chan else f"id {ch_id}"
            e.location = f"Discord channel: {chan_name}"
            e.url = f"https://discord.com/events/{guild_id}/{ev_id}"


def _apply_recurrence(e: Event, recurrence: Optional[List[str]]) -> None:
    if not recurrence:
        return
    for rule in recurrence:
        _add_prop(e, "RRULE", rule)


# ---------------------------------------------------------------------------
# Event converter
# ---------------------------------------------------------------------------


def event_to_ics(ev: Any, guild_id: int) -> Event:
    """Convert a single Discord ScheduledEvent → ics.Event."""
    e = Event()

    # Stable UID so clients detect updates
    e.uid = f"{ev.id}@discord-{guild_id}"

    # Use last edit timestamp (if any) as SEQUENCE so changes propagate
    last_edit = (
        getattr(ev, "updated_at", None)
        or getattr(ev, "last_updated_at", None)
        or getattr(ev, "edited_timestamp", None)
    )
    if last_edit:
        _add_prop(e, "SEQUENCE", str(int(last_edit.timestamp())))

    # Core fields
    e.name = ev.name
    e.begin = ev.start_time.astimezone(TIMEZONE)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(
        TIMEZONE
    )
    e.description = (ev.description or "").strip()

    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    return e


# ---------------------------------------------------------------------------
# Calendar rebuild per user
# ---------------------------------------------------------------------------


async def rebuild_calendar(user_id: int, idx: List[Dict[str, int]]) -> None:
    """Regenerate a user's ICS feed from their event index."""
    cal = Calendar()
    for name, value in [
        ("PRODID", "-//Discord Events → ICS Bot//EN"),
        ("VERSION", "2.0"),
        ("CALSCALE", "GREGORIAN"),
        ("X-WR-TIMEZONE", str(TIMEZONE)),
    ]:
        _add_prop(cal, name, value)

    updated_idx: List[Dict[str, int]] = []

    for rec in idx:
        gid, eid = rec["guild_id"], rec["id"]
        try:
            ev = await bot.fetch_scheduled_event(gid, eid)
            if ev:
                cal.events.add(event_to_ics(ev, gid))
                updated_idx.append(rec)
        except Exception as exc:
            if getattr(exc, "status", None) != 404:
                log.exception("Fetching event %s failed: %s", eid, exc)
                updated_idx.append(rec)

    if updated_idx != idx:
        save_index(user_id, updated_idx)

    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("Saved .ics for %s (%d events)", user_id, len(cal.events))


# ---------------------------------------------------------------------------
# Poller
# ---------------------------------------------------------------------------


async def poll_new_events() -> None:
    """Background task: refresh every POLL_INTERVAL minutes."""
    await asyncio.sleep(5)
    while True:
        for json_idx in DATA_DIR.glob("*.json"):
            try:
                uid = int(json_idx.stem)
            except ValueError:
                continue
            index = load_index(uid)
            if index:
                await rebuild_calendar(uid, index)
        await asyncio.sleep(POLL_INTERVAL * 60)
