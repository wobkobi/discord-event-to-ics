"""event_handlers.py – respond to Discord guild-scheduled-event webhooks
Minimal, no type-hints. Three listeners (add, update, delete) plus on_ready.
"""

import asyncio
import logging
from pathlib import Path

import discord

from main import bot
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


def _id_from_se(se):
    """Return (guild_id, event_id) for a ScheduledEvent object (or None, None)."""
    if not se:
        return None, None
    gid = _to_int(getattr(se, "guild_id", None)) or _to_int(
        getattr(getattr(se, "guild", None), "id", None)
    )
    eid = _to_int(getattr(se, "id", None))
    return gid, eid


def _extract_ids(payload):
    """Return (guild_id, event_id) no matter how the payload is shaped."""
    for attr in ("scheduled_event", "after", "before", "event"):
        gid, eid = _id_from_se(getattr(payload, attr, None))
        if eid:  # event_id is mandatory; guild_id may be None
            return gid, eid
    gid = _to_int(getattr(payload, "guild_id", None))
    eid = _to_int(
        getattr(payload, "scheduled_event_id", None) or getattr(payload, "id", None)
    )
    return gid, eid


# ───────────────────────── listeners ─────────────────────────


@bot.event
async def on_scheduled_event_user_add(
    event: discord.ScheduledEvent, user: discord.User
):
    """User showed interest / RSVP’d."""
    gid, eid = _id_from_se(event)
    uid = _to_int(user.id)

    if uid is None or eid is None:
        log.warning("Interested payload missing ids – skipping")
        _dump_attrs(event, "interested_evt")
        return

    ensure_files(uid)
    idx = load_index(uid)

    if not any(r["id"] == eid and r["guild_id"] == (gid or r["guild_id"]) for r in idx):
        idx.append({"guild_id": gid or 0, "id": eid})
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s for user %s and rebuilt calendar", eid, uid)


@bot.event
async def on_scheduled_event_update(
    before: discord.ScheduledEvent, after: discord.ScheduledEvent
):
    """An event was edited (time, description, etc.)."""
    gid, eid = _extract_ids(after)
    if eid is None:
        log.warning("Event update without event_id – skipping")
        _dump_attrs(after, "update_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        if any(r["id"] == eid and (gid is None or r["guild_id"] == gid) for r in idx):
            await rebuild_calendar(uid, idx)
            log.info("Rebuilt calendar for %s after update to event %s", uid, eid)


@bot.event
async def on_scheduled_event_delete(
    event: discord.ScheduledEvent,
):
    """Event deleted or cancelled."""
    gid, eid = _id_from_se(event)
    if eid is None:
        log.warning("Event delete without event_id – skipping")
        _dump_attrs(event, "delete_evt")
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
            if not (r["id"] == eid and (gid is None or r["guild_id"] == gid))
        ]
        if new_idx != idx:
            save_index(uid, new_idx)
            await rebuild_calendar(uid, new_idx)
            log.info(
                "Removed deleted event %s from user %s and rebuilt calendar", eid, uid
            )


# ─────────────────── bot ready: kick off tasks ───────────────────


@bot.event
async def on_ready():
    log.info("Bot is online; launching HTTP server and polling tasks.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
