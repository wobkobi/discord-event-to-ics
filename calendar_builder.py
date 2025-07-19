# calendar_builder.py – build and update per-user iCalendar feeds,
# with support for location, default durations, and personalized alerts.

import asyncio
import datetime as dt
import logging
import re
from urllib.parse import quote_plus

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
    """
    Attach a raw ContentLine to a component so ics.py writes it exactly.
    Useful for RRULE, VALARM, SEQUENCE, and custom headers.
    """
    component.extra.append(ContentLine(name=name, params={}, value=value))


def _apply_location(event_obj, metadata, guild_id, event_id):
    """
    Read the Discord entity_metadata and set:
      - event_obj.location (string)
      - event_obj.url (link to map or Discord channel)
      - event_obj.geo (if given as coords)
    """
    if not metadata:
        return

    loc = getattr(metadata, "location", None)
    loc_url = getattr(metadata, "location_url", None)

    if loc:
        event_obj.location = loc
        # If it's lat/lon, set Geo; else build a Google search URL
        if m := _LAT_LON.match(loc):
            event_obj.geo = Geo(latitude=float(m.group(1)), longitude=float(m.group(2)))
        else:
            event_obj.url = f"https://www.google.com/maps/search/{quote_plus(loc)}"

    elif loc_url:
        event_obj.location = loc_url
        event_obj.url = loc_url

    else:
        ch_id = getattr(metadata, "channel_id", None)
        if ch_id is not None:
            chan = client.get_channel(int(ch_id))
            # Use getattr to safely retrieve .name if present
            chan_name = getattr(chan, "name", f"id {ch_id}") if chan else f"id {ch_id}"
            event_obj.location = f"Discord channel: {chan_name}"
            event_obj.url = f"https://discord.com/channels/{guild_id}/{ch_id}"


def _apply_recurrence(event_obj, recurrence_rules):
    """
    Add each RRULE from Discord to the VEVENT.
    """
    if recurrence_rules:
        for rule in recurrence_rules:
            _add_prop(event_obj, "RRULE", rule)


def event_to_ics(ev, guild_id, user_id):
    """
    Convert a Discord ScheduledEvent into an ics.Event,
    applying:
      - SEQUENCE for edits
      - start/end times with default-length fallback
      - description, name
      - recurrence rules
      - location metadata
      - personalized VALARM blocks
    """
    e = Event()
    e.uid = f"{ev.id}@discord-{guild_id}"

    # 1) SEQUENCE – bump when edited
    last_edit = getattr(ev, "updated_at", None) or getattr(ev, "edited_timestamp", None)
    if last_edit:
        seq = str(int(last_edit.timestamp()))
        _add_prop(e, "SEQUENCE", seq)

    # 2) Times – apply timezone and default length if needed
    start = ev.start_time.astimezone(TIMEZONE)
    end = ev.end_time.astimezone(TIMEZONE) if ev.end_time else None

    settings = load_settings(user_id)
    if end is None:
        # no explicit end → use default_length (in minutes)
        length = settings.get("default_length", 60)
        end = start + dt.timedelta(minutes=length)

    e.begin = start
    e.end = end

    # 3) Core details
    e.name = ev.name
    e.description = (ev.description or "").strip()

    # 4) Recurrence & location
    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    # 5) VALARM blocks for reminders
    for mins in sorted(set(settings.get("alerts", [0]))):
        _add_prop(e, "BEGIN", "VALARM")
        _add_prop(e, "ACTION", "DISPLAY")
        _add_prop(e, "DESCRIPTION", e.name)
        trigger = f"-PT{mins}M" if mins else "-PT0M"
        _add_prop(e, "TRIGGER", trigger)
        _add_prop(e, "END", "VALARM")

    return e


async def rebuild_calendar(user_id, idx):
    """
    Regenerate a user's .ics file based on their index of (guild_id, event_id):
      1) Fetch each ScheduledEvent (with retries on rate-limit)
      2) Convert to VEVENT via event_to_ics
      3) Write the full Calendar out to disk
      4) Trim entries for events that 404
    """
    cal = Calendar()
    # Custom headers before any events
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

        # Try up to 3 times if we hit a rate-limit / bucket-lock
        for attempt in range(1, 4):
            try:
                guild = client.get_guild(gid) or await client.fetch_guild(gid)
                ev = await guild.fetch_scheduled_event(eid)
                break
            except Exception as exc:
                text = str(exc).lower()
                if "ratelimit" in text or "locked" in text:
                    log.warning(
                        "Rate-limit on event %s (try %d) – retrying...", eid, attempt
                    )
                    await asyncio.sleep(attempt)
                    continue
                log.exception("Error fetching event %s: %s", eid, exc)
                break

        if ev:
            cal.events.add(event_to_ics(ev, gid, user_id))
            updated.append(rec)
        else:
            log.error("Skipping event %s after failed fetches", eid)

    # If some events were removed (404), save the trimmed index
    if updated != idx:
        save_index(user_id, updated)

    # Write out the .ics file
    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("Saved .ics for user %s (%d events)", user_id, len(cal.events))


async def poll_new_events():
    """
    On startup and every POLL_INTERVAL minutes:
    • Load each user's index
    • Rebuild their calendar
    """
    while True:
        for index_file in DATA_DIR.glob("*.json"):
            try:
                uid = int(index_file.stem)
            except ValueError:
                continue
            ensure_files(uid)
            idx = load_index(uid)
            await rebuild_calendar(uid, idx)
        await asyncio.sleep(POLL_INTERVAL * 60)
