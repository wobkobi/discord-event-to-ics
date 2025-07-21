# calendar_builder.py – builds each user’s .ics feed
# keeps past events and adds up to two default pop‑up reminders per guild

import asyncio
import datetime as dt
import logging
import re
from urllib.parse import quote_plus

import discord
from ics import Calendar, Event, Geo
from ics.alarm import DisplayAlarm
from ics.grammar.parse import ContentLine

from bot_setup import bot
from config import DATA_DIR, POLL_INTERVAL, TIMEZONE
from file_helpers import (
    ics_path,
    load_index,
    save_index,
    ensure_files,
    load_guild_alerts,
)

log = logging.getLogger(__name__)

# matches latitude,longitude strings like "-37.8, 175.0"
_LAT_LON = re.compile(r"^\s*(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$")

# add a custom line to an ics component


def _add(component, name: str, value: str):
    component.extra.append(ContentLine(name=name, params={}, value=value))


# fill Event.location and url from the event metadata


def _apply_location(evt: Event, meta, guild_id: int, event_id: int):
    if not meta:
        return

    loc = getattr(meta, "location", None)
    loc_url = getattr(meta, "location_url", None)

    if loc:
        evt.location = loc
        if m := _LAT_LON.match(loc):
            evt.geo = Geo(float(m[1]), float(m[2]))
        else:
            evt.url = f"https://www.google.com/maps/search/{quote_plus(loc)}"
    elif loc_url:
        evt.location = loc_url
        evt.url = loc_url
    else:
        ch_id = getattr(meta, "channel_id", None)
        if ch_id:
            chan = bot.get_channel(int(ch_id))
            name = getattr(chan, "name", f"channel {ch_id}")
            evt.location = f"Discord channel: {name}"
            evt.url = f"https://discord.com/events/{guild_id}/{event_id}"


# copy RRULE strings into the VEVENT


def _apply_recurrence(evt: Event, rules):
    for rule in rules or []:
        _add(evt, "RRULE", rule)


# convert a Discord scheduled event into a VEVENT


def event_to_ics(ev: discord.ScheduledEvent, guild_id: int) -> Event:
    evt = Event()
    evt.uid = f"{ev.id}@discord-{guild_id}"

    last_edit = (
        getattr(ev, "updated_at", None)
        or getattr(ev, "last_updated_at", None)
        or getattr(ev, "edited_timestamp", None)
    )
    if last_edit:
        _add(evt, "SEQUENCE", str(int(last_edit.timestamp())))

    evt.name = ev.name
    evt.begin = ev.start_time.astimezone(TIMEZONE)
    evt.end = (ev.end_time or ev.start_time + dt.timedelta(hours=1)).astimezone(
        TIMEZONE
    )
    evt.description = (ev.description or "").strip()

    _apply_recurrence(evt, getattr(ev, "recurrence", None))
    _apply_location(evt, getattr(ev, "entity_metadata", None), guild_id, ev.id)

    alert1, alert2 = load_guild_alerts(guild_id)
    if alert1 is not None:
        evt.alarms.append(
            DisplayAlarm(
                trigger=dt.timedelta(minutes=-alert1),
                display_text=f"Reminder: {ev.name} in {alert1} min",
            )
        )
    if alert2 is not None:
        evt.alarms.append(
            DisplayAlarm(
                trigger=dt.timedelta(minutes=-alert2),
                display_text=f"Reminder: {ev.name} in {alert2} min",
            )
        )

    return evt


# rebuild one user’s calendar file


async def rebuild_calendar(user_id: int, idx: list[dict]):
    # create a fresh Calendar and copy static headers
    cal = Calendar()
    for k, v in [
        ("PRODID", "-//Discord Events → ICS Bot//EN"),
        ("VERSION", "2.0"),
        ("CALSCALE", "GREGORIAN"),
        ("X-WR-TIMEZONE", str(TIMEZONE)),
    ]:
        _add(cal, k, v)

    new_idx: list[dict] = []

    for rec in idx:
        gid = rec.get("guild_id")
        eid = rec.get("id")
        if gid is None or eid is None:
            continue

        try:
            guild = bot.get_guild(gid) or await bot.fetch_guild(gid)
            ev = await guild.fetch_scheduled_event(eid)
            if ev is None:
                raise discord.NotFound(response=None, message="event gone")
            cal.events.add(event_to_ics(ev, gid))
            new_idx.append(rec)
        except discord.NotFound:
            log.info("event %s no longer exists", eid)
            continue
        except Exception as exc:
            log.exception("error fetching %s: %s", eid, exc)
            new_idx.append(rec)

    if new_idx != idx:
        save_index(user_id, new_idx)

    ics_path(user_id).write_bytes(cal.serialize().encode())
    log.info("wrote .ics for %s (%d events)", user_id, len(cal.events))


# loop that rebuilds everyone’s feed on a timer


async def poll_new_events():
    while True:
        for jf in DATA_DIR.glob("*.json"):
            try:
                uid = int(jf.stem)
            except ValueError:
                continue
            ensure_files(uid)
            await rebuild_calendar(uid, load_index(uid))
        await asyncio.sleep(POLL_INTERVAL * 60)
