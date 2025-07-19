# calendar_builder.py – build and update per-user iCalendar feeds,
# with support for location, default durations, and resilient handling when
# the bot temporarily loses access to a guild.

import asyncio
import datetime as dt
import logging
import re
from urllib.parse import quote_plus

import discord
from ics import Calendar, Event, Geo
from ics.grammar.parse import ContentLine

from bot_setup import client
from config import DATA_DIR, POLL_INTERVAL, TIMEZONE
from file_helpers import (
    ics_path,
    load_index,
    save_index,
    ensure_files,
    load_settings,
)

log = logging.getLogger(__name__)

# Matches "lat,lon" coordinates (e.g. "40.7128,-74.0060")
_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")


def _add_prop(component, name, value):
    """Attach a raw ContentLine so ics.py writes it exactly."""
    component.extra.append(ContentLine(name=name, params={}, value=value))


def _apply_location(event_obj, metadata, guild_id, event_id):
    """
    Read Discord entity_metadata and set:
      - event_obj.location  (string)
      - event_obj.url       (map link / channel link)
      - event_obj.geo       (if given as coords)
    """
    if not metadata:
        return

    loc = getattr(metadata, "location", None)
    loc_url = getattr(metadata, "location_url", None)

    if loc:
        event_obj.location = loc
        if m := _LAT_LON.match(loc):
            event_obj.geo = Geo(latitude=float(m.group(1)), longitude=float(m.group(2)))
        else:
            # Bias WhatsApp free-text to a map search
            query = quote_plus(loc)
            event_obj.url = f"https://www.google.com/maps/search/{query}?region=NZ"
    elif loc_url:
        event_obj.location = loc_url
        event_obj.url = loc_url
    else:
        ch_id = getattr(metadata, "channel_id", None)
        if ch_id is not None:
            chan = client.get_channel(int(ch_id))
            # Safely grab .name if present
            chan_name = getattr(chan, "name", f"id {ch_id}") if chan else f"id {ch_id}"
            event_obj.location = f"Discord channel: {chan_name}"
            event_obj.url = f"https://discord.com/channels/{guild_id}/{ch_id}"


def _apply_recurrence(event_obj, recurrence_rules):
    """Add each RRULE from Discord to the VEVENT."""
    if recurrence_rules:
        for rule in recurrence_rules:
            _add_prop(event_obj, "RRULE", rule)


def event_to_ics(ev, guild_id, user_id):
    """
    Convert a Discord ScheduledEvent into an ics.Event:
      • SEQUENCE for edits
      • start/end with default-length fallback
      • description, summary
      • recurrence
      • location metadata
      • personalized VALARM blocks
    """
    e = Event()
    e.uid = f"{ev.id}@discord-{guild_id}"

    # 1) SEQUENCE (bump when edited)
    last_edit = getattr(ev, "updated_at", None) or getattr(ev, "edited_timestamp", None)
    if last_edit:
        _add_prop(e, "SEQUENCE", str(int(last_edit.timestamp())))

    # 2) Start & end times
    start = ev.start_time.astimezone(TIMEZONE)
    end = ev.end_time.astimezone(TIMEZONE) if ev.end_time else None

    settings = load_settings(user_id)
    if end is None:
        # no explicit end → use default_length (minutes)
        length = settings.get("default_length", 60)
        end = start + dt.timedelta(minutes=length)

    e.begin = start
    e.end = end
    e.name = ev.name
    e.description = (ev.description or "").strip()

    # 3) Optional extras
    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    # 4) VALARM reminders
    for mins in sorted(set(settings.get("alerts", [0]))):
        _add_prop(e, "BEGIN", "VALARM")
        _add_prop(e, "ACTION", "DISPLAY")
        _add_prop(e, "DESCRIPTION", e.name)
        trig = f"-PT{mins}M" if mins else "-PT0M"
        _add_prop(e, "TRIGGER", trig)
        _add_prop(e, "END", "VALARM")

    return e


async def rebuild_calendar(user_id, idx):
    """
    Regenerate a user's .ics feed:
      • Fetch each event (with retries on rate-limit)
      • Keep only 404-removed events out of the index
      • Preserve records for 403 or transient errors (so a re-join can recover)
    """
    cal = Calendar()
    # Calendar-level headers
    for name, value in [
        ("PRODID", "-//Discord Events → ICS Bot//EN"),
        ("VERSION", "2.0"),
        ("CALSCALE", "GREGORIAN"),
        ("X-WR-TIMEZONE", str(TIMEZONE)),
    ]:
        _add_prop(cal, name, value)

    updated = []
    for rec in idx:
        gid, eid = rec["guild_id"], rec["id"]
        ev = None
        removed = False

        # up to 3 retries for rate-limit / lock errors
        for attempt in range(1, 4):
            try:
                guild = client.get_guild(gid) or await client.fetch_guild(gid)
                ev = await guild.fetch_scheduled_event(eid)
                break

            except discord.NotFound:
                log.info("Event %s not found (404) – dropping from index", eid)
                removed = True
                break

            except discord.Forbidden:
                log.warning(
                    "Missing access to event %s in guild %s (403) – will retry after re-join",
                    eid,
                    gid,
                )
                break

            except Exception as exc:
                log.exception(
                    "Transient error fetching event %s: %s – will retry later", eid, exc
                )
                break

        if ev:
            cal.events.add(event_to_ics(ev, gid, user_id))
            updated.append(rec)
        elif not removed:
            # Either Forbidden or another exception – preserve the record
            updated.append(rec)

    # Write back only the 404-removed events
    if updated != idx:
        save_index(user_id, updated)

    # Serialize to disk
    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("Saved .ics for %s (%d events)", user_id, len(cal.events))


async def poll_new_events():
    """
    On startup and every POLL_INTERVAL minutes:
      • Scan each user's index
      • Rebuild their calendar
    """
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
