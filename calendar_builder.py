"""calendar_builder.py – builds per-user iCalendar feeds with alerts and default length support"""

import asyncio
import datetime as dt
import logging
import re
from urllib.parse import quote_plus

from ics import Calendar, Event, Geo
from ics.grammar.parse import ContentLine

from bot_setup import bot
from config import DATA_DIR, POLL_INTERVAL, TIMEZONE
from file_helpers import ics_path, load_index, save_index, ensure_files, load_settings

log = logging.getLogger(__name__)

_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")

# ───────────────────────────── helpers ─────────────────────────────────────


def _add_prop(component, name, value):
    component.extra.append(ContentLine(name=name, params={}, value=value))


def _apply_location(e, meta, guild_id, ev_id):
    if not meta:
        return
    loc = getattr(meta, "location", None)
    loc_url = getattr(meta, "location_url", None)
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
            name = getattr(chan, "name", f"id {ch_id}") if chan else f"id {ch_id}"
            e.location = f"Discord channel: {name}"
            e.url = f"https://discord.com/channels/{guild_id}/{ch_id}"


def _apply_recurrence(e, recurrence):
    if recurrence:
        for rule in recurrence:
            _add_prop(e, "RRULE", rule)


# ───────────────────────── event to VEVENT ─────────────────────────────────


def event_to_ics(ev, guild_id, user_id):
    """Convert a ScheduledEvent into an ICS Event, with alerts & default length."""
    e = Event()
    e.uid = f"{ev.id}@discord-{guild_id}"
    # Sequence for edits
    last = getattr(ev, "updated_at", None) or getattr(ev, "edited_timestamp", None)
    if last:
        _add_prop(e, "SEQUENCE", str(int(last.timestamp())))
    # Time handling
    start = ev.start_time.astimezone(TIMEZONE)
    end = ev.end_time.astimezone(TIMEZONE) if ev.end_time else None
    settings = load_settings(user_id)
    # Default length
    if end is None:
        length = settings.get("default_length", 60)
        end = start + dt.timedelta(minutes=length)
    e.begin = start
    e.end = end
    # Core props
    e.name = ev.name
    e.description = (ev.description or "").strip()
    # Recurrence + location
    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)
    # Alarms
    alerts = settings.get("alerts", [0])
    for mins in sorted(set(alerts)):
        _add_prop(e, "BEGIN", "VALARM")
        _add_prop(e, "ACTION", "DISPLAY")
        _add_prop(e, "DESCRIPTION", e.name)
        trig = f"-PT{mins}M" if mins else "-PT0M"
        _add_prop(e, "TRIGGER", trig)
        _add_prop(e, "END", "VALARM")
    return e


# ───────────────────────── rebuild calendar ─────────────────────────────────


async def rebuild_calendar(user_id, idx):
    cal = Calendar()
    for k, v in [
        ("PRODID", "-//Discord Events → ICS Bot//EN"),
        ("VERSION", "2.0"),
        ("CALSCALE", "GREGORIAN"),
        ("X-WR-TIMEZONE", str(TIMEZONE)),
    ]:
        _add_prop(cal, k, v)
    updated = []
    for rec in idx:
        gid, eid = rec["guild_id"], rec["id"]
        ev = None
        for attempt in range(1, 4):
            try:
                ev = await bot.fetch_scheduled_event(gid, eid)
                break
            except RuntimeError as exc:
                if "locked" in str(exc).lower():
                    wait = attempt
                    log.warning(
                        "Rate-limit on %s (try %d) – sleeping %ds", eid, attempt, wait
                    )
                    await asyncio.sleep(wait)
                    continue
                break
        if ev:
            cal.events.add(event_to_ics(ev, gid, user_id))
            updated.append(rec)
        else:
            log.error("Failed fetching %s after retries", eid)
    if updated != idx:
        save_index(user_id, updated)
    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("Saved .ics for %s (%d events)", user_id, len(cal.events))


# ─────────────────────── cron-style poller ────────────────────────────────


async def poll_new_events():
    while True:
        for file in DATA_DIR.glob("*.json"):
            try:
                uid = int(file.stem)
            except ValueError:
                continue
            ensure_files(uid)
            idx = load_index(uid)
            await rebuild_calendar(uid, idx)
        await asyncio.sleep(POLL_INTERVAL * 60)
