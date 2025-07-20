"""event_handlers.py – respond to Discord scheduled-event hooks (Pycord)"""

import asyncio
import logging
from pathlib import Path

import discord

from bot_setup import bot 
from calendar_builder import poll_new_events, rebuild_calendar
from config import DATA_DIR
from file_helpers import ensure_files, load_index, save_index
from server import run_http

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
async def on_scheduled_event_user_add(
    event: discord.ScheduledEvent, user: discord.User
):
    log.info("🔥 Got on_scheduled_event_user_add: %s / %s", event.id, user.id)
    """User marked themselves interested."""
    gid, eid = _id_from_se(event)
    uid = _to_int(user.id)
    if uid is None or eid is None:
        log.warning("User-add missing IDs – skipping")
        _dump_attrs(event, "add_evt")
        return

    ensure_files(uid)
    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == (gid or r["guild_id"]) for r in idx):
        idx.append({"guild_id": gid or 0, "id": eid})
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s for user %s", eid, uid)


@bot.event
async def on_scheduled_event_user_remove(
    event: discord.ScheduledEvent, user: discord.User
):
    """User removed their interest."""
    gid, eid = _id_from_se(event)
    uid = _to_int(user.id)
    if uid is None or eid is None:
        log.warning("User-remove missing IDs – skipping")
        _dump_attrs(event, "remove_evt")
        return

    ensure_files(uid)
    idx = load_index(uid)
    new_idx = [
        r
        for r in idx
        if not (r["id"] == eid and r["guild_id"] == (gid or r["guild_id"]))
    ]
    if new_idx != idx:
        save_index(uid, new_idx)
        await rebuild_calendar(uid, new_idx)
        log.info("Removed event %s for user %s", eid, uid)


@bot.event
async def on_scheduled_event_update(
    before: discord.ScheduledEvent, after: discord.ScheduledEvent
):
    """An event was edited."""
    gid, eid = _id_from_se(after)
    if eid is None:
        log.warning("Update missing event ID – skipping")
        _dump_attrs(after, "update_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        if any(r["id"] == eid and (r["guild_id"] == gid or gid is None) for r in idx):
            await rebuild_calendar(uid, idx)
            log.info("Rebuilt calendar for %s after update to event %s", uid, eid)


@bot.event
async def on_scheduled_event_delete(scheduled_event: discord.ScheduledEvent):
    """An event was deleted or cancelled."""
    gid, eid = _id_from_se(scheduled_event)
    if eid is None:
        log.warning("Delete missing event ID – skipping")
        _dump_attrs(scheduled_event, "delete_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        new_idx = [
            r
            for r in idx
            if not (r["id"] == eid and (r["guild_id"] == gid or gid is None))
        ]
        if new_idx != idx:
            save_index(uid, new_idx)
            await rebuild_calendar(uid, new_idx)
            log.info("Removed deleted event %s for user %s", eid, uid)


# ─────────────────── bot ready: kick off server + poller ───────────────────


@bot.event
async def on_ready():
    log.info("Bot online; launching HTTP server & poller.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
