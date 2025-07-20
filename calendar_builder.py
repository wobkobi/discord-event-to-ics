"""calendar_builder.py – builds per-user iCalendar feeds from Discord events

All static type-hints have been removed for simplicity. Behaviour is identical
(FIFO: fetch event → convert → write .ics). Compatible with Outlook, Apple, and
Google Calendar.
"""

import asyncio
import datetime as dt
import logging
import re
from urllib.parse import quote_plus

import discord
from ics import Calendar, Event, Geo
from ics.grammar.parse import ContentLine

from main import bot
from config import DATA_DIR, POLL_INTERVAL, TIMEZONE
from file_helpers import ics_path, load_index, save_index, ensure_files

log = logging.getLogger(__name__)

_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")

# ───────────────────────── helpers ──────────────────────────


def _add_prop(component, name, value):
    """Attach an extra ContentLine; ics-py will serialize it verbatim."""
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
            # Pycord: use get_channel instead of cache.get_channel
            chan = bot.get_channel(int(ch_id))
            chan_name = getattr(chan, "name", f"id {ch_id}") if chan else f"id {ch_id}"
            e.location = f"Discord channel: {chan_name}"
            e.url = f"https://discord.com/events/{guild_id}/{ev_id}"


def _apply_recurrence(e, recurrence):
    if recurrence:
        for rule in recurrence:
            _add_prop(e, "RRULE", rule)


# ─────────────────────── event → VEVENT ──────────────────────


def event_to_ics(ev, guild_id):
    e = Event()
    e.uid = f"{ev.id}@discord-{guild_id}"

    last_edit = (
        getattr(ev, "updated_at", None)
        or getattr(ev, "last_updated_at", None)
        or getattr(ev, "edited_timestamp", None)
    )
    if last_edit:
        _add_prop(e, "SEQUENCE", str(int(last_edit.timestamp())))

    e.name = ev.name
    e.begin = ev.start_time.astimezone(TIMEZONE)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(
        TIMEZONE
    )
    e.description = (ev.description or "").strip()

    _apply_recurrence(e, getattr(ev, "recurrence", None))
    _apply_location(e, getattr(ev, "entity_metadata", None), guild_id, ev.id)
    return e


# ────────────────────── user-calendar rebuild ──────────────────────


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
        try:
            # Pycord: fetch event via Guild object
            guild = bot.get_guild(gid) or await bot.fetch_guild(gid)
            ev = await guild.fetch_scheduled_event(eid)
            if ev:
                cal.events.add(event_to_ics(ev, gid))
                updated.append(rec)
        except discord.NotFound:
            # Event or guild not found – drop it from index
            continue
        except Exception as exc:
            log.exception("Fetching event %s failed: %s", eid, exc)
            updated.append(rec)

    if updated != idx:
        save_index(user_id, updated)

    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("Saved .ics for %s (%d events)", user_id, len(cal.events))


# ───────────────────────── cron-style poller ─────────────────────────


async def poll_new_events():
    """On boot: rebuild every calendar, then repeat every POLL_INTERVAL minutes."""
    while True:
        for json_idx in DATA_DIR.glob("*.json"):
            try:
                uid = int(json_idx.stem)
            except ValueError:
                continue

            ensure_files(uid)
            index = load_index(uid)
            await rebuild_calendar(uid, index)

        await asyncio.sleep(POLL_INTERVAL * 60)
