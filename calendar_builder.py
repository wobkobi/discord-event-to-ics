# calendar_builder.py – RFC 5545‑compliant builder with UID, SEQUENCE and Apple/Google headers
import asyncio
import datetime as dt
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ics import Calendar, Event

from bot_setup import bot
from config import DATA_DIR, POLL_INTERVAL, TIMEZONE
from file_helpers import ics_path, load_index, save_index

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------
_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")

# ---------------------------------------------------------------------------
# Location & recurrence helpers
# ---------------------------------------------------------------------------


def _apply_location(e: Event, meta: Any, guild_id: int, ev_id: int) -> None:
    """Attach LOCATION / GEO / URL fields."""
    if not meta:
        return

    loc = getattr(meta, "location", None)
    loc_url = getattr(meta, "location_url", None)

    if loc:
        e.location = loc
        if m := _LAT_LON.match(loc):
            e.extra.append(("GEO", f"{m.group(1)};{m.group(2)}"))
        else:
            e.url = f"https://www.google.com/maps/search/{quote_plus(loc)}"
    elif loc_url:
        e.location = loc_url
        e.url = loc_url
    else:
        ch_id = getattr(meta, "channel_id", None)
        if ch_id:
            channel = bot.cache.get_channel(int(ch_id)) if ch_id else None
            chan_name = getattr(channel, "name", f"id {ch_id}")
            e.location = f"Discord channel: {chan_name}"
            e.url = f"https://discord.com/events/{guild_id}/{ev_id}"


def _apply_recurrence(e: Event, recurrence: Optional[List[str]]) -> None:
    if recurrence:
        for rule in recurrence:
            e.extra.append(("RRULE", rule))


# ---------------------------------------------------------------------------
# Core converter
# ---------------------------------------------------------------------------


def event_to_ics(ev: Any, guild_id: int) -> Event:
    """Convert a Discord ScheduledEvent into an RFC 5545 Event."""
    e = Event()

    # Stable UID so clients recognise updates
    e.uid = f"{ev.id}@discord-{guild_id}"

    # SEQUENCE via extra property (ics library lacks direct attribute)
    seq_src = (
        getattr(ev, "updated_at", None)
        or getattr(ev, "last_updated_at", None)
        or getattr(ev, "edited_timestamp", None)
    )
    if seq_src:
        e.extra.append(("SEQUENCE", str(int(seq_src.timestamp()))))

    # Core fields
    e.name = ev.name
    e.begin = ev.start_time.astimezone(TIMEZONE)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(
        TIMEZONE
    )
    e.description = (ev.description or "").strip()

    # Extras
    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    return e


# ---------------------------------------------------------------------------
# Calendar rebuild & polling
# ---------------------------------------------------------------------------


async def rebuild_calendar(user_id: int, idx: List[Dict[str, int]]) -> None:
    """Rebuild the .ics feed for a user."""
    cal = Calendar()
    # Apple / Google friendly calendar‑level headers
    cal.extra.extend(
        [
            ("PRODID", "-//Discord Events → ICS Bot//EN"),
            ("VERSION", "2.0"),
            ("CALSCALE", "GREGORIAN"),
            ("X-WR-TIMEZONE", str(TIMEZONE)),
        ]
    )

    updated_idx: List[Dict[str, int]] = []

    for rec in idx:
        gid, eid = rec["guild_id"], rec["id"]
        try:
            ev = await bot.fetch_scheduled_event(gid, eid)
            if ev:
                cal.events.add(event_to_ics(ev, gid))
                updated_idx.append(rec)
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                log.info(f"Event {eid} missing – removed from {user_id}")
            else:
                log.exception(f"Error fetching event {eid}: {exc}")
                updated_idx.append(rec)  # keep until next run

    if updated_idx != idx:
        save_index(user_id, updated_idx)

    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("Saved .ics for %s (%d events)", user_id, len(cal.events))


async def poll_new_events() -> None:
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
