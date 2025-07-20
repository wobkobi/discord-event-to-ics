"""event_handlers.py – respond to Discord scheduled-event hooks (Pycord).

Includes:
• on_ready           – starts HTTP server, poller, and a one-shot sync.
• on_scheduled_event_create  – captures creator auto-subscribe.
• on_scheduled_event_user_add / _remove  – RSVP listeners.
• on_scheduled_event_update / _delete    – edit + delete handling.
"""

import asyncio
import logging
from pathlib import Path

import discord

from bot_setup import bot
from server import run_http
from calendar_builder import poll_new_events, rebuild_calendar
from config import DATA_DIR
from file_helpers import ensure_files, load_index, save_index

log = logging.getLogger(__name__)

# ───────────────────── helper utilities ──────────────────────


def _to_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _dump_attrs(obj, label="evt"):
    attrs = {n: getattr(obj, n, None) for n in dir(obj) if not n.startswith("__")}
    log.warning("%s attrs → %s", label, attrs)


def _id_from_se(se: discord.ScheduledEvent):
    if not se:
        return None, None
    gid = _to_int(getattr(se, "guild_id", None)) or _to_int(
        getattr(getattr(se, "guild", None), "id", None)
    )
    eid = _to_int(getattr(se, "id", None))
    return gid, eid


# ───────────────────────── listeners ─────────────────────────


@bot.event
async def on_scheduled_event_create(event: discord.ScheduledEvent):
    """Creator is auto-subscribed; add the event to their feed."""
    gid, eid = _id_from_se(event)
    creator = event.creator or (
        await bot.fetch_user(event.creator_id) if event.creator_id else None
    )
    uid = _to_int(getattr(creator, "id", None))
    if uid is None or eid is None:
        return

    ensure_files(uid)
    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == gid for r in idx):
        idx.append({"guild_id": gid, "id": eid})
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Event %s auto-added for creator %s", eid, uid)


@bot.event
async def on_scheduled_event_user_add(
    event: discord.ScheduledEvent, user: discord.User
):
    gid, eid = _id_from_se(event)
    uid = _to_int(user.id)
    if uid is None or eid is None:
        _dump_attrs(event, "add_evt")
        return

    ensure_files(uid)
    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == gid for r in idx):
        idx.append({"guild_id": gid, "id": eid})
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s for user %s", eid, uid)


@bot.event
async def on_scheduled_event_user_remove(
    event: discord.ScheduledEvent, user: discord.User
):
    gid, eid = _id_from_se(event)
    uid = _to_int(user.id)
    if uid is None or eid is None:
        _dump_attrs(event, "remove_evt")
        return

    ensure_files(uid)
    idx = load_index(uid)
    new_idx = [r for r in idx if not (r["id"] == eid and r["guild_id"] == gid)]
    if new_idx != idx:
        save_index(uid, new_idx)
        await rebuild_calendar(uid, new_idx)
        log.info("Removed event %s for user %s", eid, uid)


@bot.event
async def on_scheduled_event_update(
    before: discord.ScheduledEvent, after: discord.ScheduledEvent
):
    gid, eid = _id_from_se(after)
    if eid is None:
        _dump_attrs(after, "update_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue
        ensure_files(uid)
        idx = load_index(uid)
        if any(r["id"] == eid and r["guild_id"] == gid for r in idx):
            await rebuild_calendar(uid, idx)
            log.info("Rebuilt calendar for %s after update to event %s", uid, eid)


@bot.event
async def on_scheduled_event_delete(event: discord.ScheduledEvent):
    gid, eid = _id_from_se(event)
    if eid is None:
        _dump_attrs(event, "delete_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue
        ensure_files(uid)
        idx = load_index(uid)
        new_idx = [r for r in idx if not (r["id"] == eid and r["guild_id"] == gid)]
        if new_idx != idx:
            save_index(uid, new_idx)
            await rebuild_calendar(uid, new_idx)
            log.info("Removed deleted event %s for user %s", eid, uid)


# ───────────────────── one-shot back-fill task ─────────────────────


async def sync_existing_events():
    """Scan every guild and add any missing events for interested users."""
    for guild in bot.guilds:
        events = await guild.fetch_scheduled_events()
        for ev in events:
            try:
                async for user in ev.subscribers(limit=None):
                    gid, eid = guild.id, ev.id
                    uid = _to_int(user.id)
                    ensure_files(uid)
                    idx = load_index(uid)
                    if any(r["id"] == eid and r["guild_id"] == gid for r in idx):
                        continue
                    idx.append({"guild_id": gid, "id": eid})
                    save_index(uid, idx)
                    await rebuild_calendar(uid, idx)
                    log.info("Synced old event %s into %s", eid, uid)
            except discord.NotFound:
                log.info("Event %s vanished while syncing – skipping", ev.id)
                continue

        await asyncio.sleep(1)  # be gentle on the API


# ─────────────────── bot ready: kick off tasks ───────────────────


@bot.event
async def on_ready():
    log.info("Bot online; launching HTTP server & poller.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
    asyncio.create_task(sync_existing_events())
