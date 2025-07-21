# event_handlers.py – listens for Discord Scheduled Events and updates user feeds
# starts the HTTP server and polling loop once the bot is ready

import asyncio
import logging

import discord

from bot_setup import bot
from server import run_http
from calendar_builder import poll_new_events, rebuild_calendar
from config import DATA_DIR
from file_helpers import ensure_files, load_index, save_index

log = logging.getLogger(__name__)

# convert anything to int or return None


def _to_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# pull guild_id and event_id out of a ScheduledEvent object


def _ids(se: discord.ScheduledEvent):
    if not se:
        return None, None
    guild_id = _to_int(getattr(se, "guild_id", None)) or _to_int(
        getattr(getattr(se, "guild", None), "id", None)
    )
    event_id = _to_int(getattr(se, "id", None))
    return guild_id, event_id


# creator is auto‑subscribed, so add the event to their feed


@bot.event
async def on_scheduled_event_create(event: discord.ScheduledEvent):
    g_id, e_id = _ids(event)
    creator = event.creator or (
        await bot.fetch_user(event.creator_id) if event.creator_id else None
    )
    u_id = _to_int(getattr(creator, "id", None))
    if u_id is None or e_id is None:
        return

    ensure_files(u_id)
    idx = load_index(u_id)
    if not any(r["id"] == e_id and r["guild_id"] == g_id for r in idx):
        idx.append({"guild_id": g_id, "id": e_id})
        save_index(u_id, idx)
        await rebuild_calendar(u_id, idx)
        log.info("auto‑added %s for creator %s", e_id, u_id)


# user clicked Interested / Going


@bot.event
async def on_scheduled_event_user_add(
    event: discord.ScheduledEvent, user: discord.User
):
    g_id, e_id = _ids(event)
    u_id = _to_int(user.id)
    if u_id is None or e_id is None:
        return

    ensure_files(u_id)
    idx = load_index(u_id)
    if not any(r["id"] == e_id and r["guild_id"] == g_id for r in idx):
        idx.append({"guild_id": g_id, "id": e_id})
        save_index(u_id, idx)
        await rebuild_calendar(u_id, idx)
        log.info("added %s for %s", e_id, u_id)


# user un‑RSVP’d


@bot.event
async def on_scheduled_event_user_remove(
    event: discord.ScheduledEvent, user: discord.User
):
    g_id, e_id = _ids(event)
    u_id = _to_int(user.id)
    if u_id is None or e_id is None:
        return

    ensure_files(u_id)
    idx = load_index(u_id)
    new_idx = [r for r in idx if not (r["id"] == e_id and r["guild_id"] == g_id)]
    if new_idx != idx:
        save_index(u_id, new_idx)
        await rebuild_calendar(u_id, new_idx)
        log.info("removed %s for %s", e_id, u_id)


# event details changed


@bot.event
async def on_scheduled_event_update(
    before: discord.ScheduledEvent, after: discord.ScheduledEvent
):
    g_id, e_id = _ids(after)
    if e_id is None:
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            u_id = int(idx_file.stem)
        except ValueError:
            continue
        ensure_files(u_id)
        idx = load_index(u_id)
        if any(r["id"] == e_id and r["guild_id"] == g_id for r in idx):
            await rebuild_calendar(u_id, idx)
            log.info("calendar for %s rebuilt after update to %s", u_id, e_id)


# event was deleted or cancelled


@bot.event
async def on_scheduled_event_delete(event: discord.ScheduledEvent):
    g_id, e_id = _ids(event)
    if e_id is None:
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            u_id = int(idx_file.stem)
        except ValueError:
            continue
        ensure_files(u_id)
        idx = load_index(u_id)
        new_idx = [r for r in idx if not (r["id"] == e_id and r["guild_id"] == g_id)]
        if new_idx != idx:
            save_index(u_id, new_idx)
            await rebuild_calendar(u_id, new_idx)
            log.info("deleted %s removed from %s", e_id, u_id)


# scan all guilds once at startup and back‑fill missing events


async def _sync_existing_events():
    for guild in bot.guilds:
        events = await guild.fetch_scheduled_events()
        for ev in events:
            g_id, e_id = guild.id, ev.id
            async for usr in ev.subscribers(limit=None):
                u_id = _to_int(usr.id)
                if u_id is None:
                    continue
                ensure_files(u_id)
                idx = load_index(u_id)
                if any(r["id"] == e_id and r["guild_id"] == g_id for r in idx):
                    continue
                idx.append({"guild_id": g_id, "id": e_id})
                save_index(u_id, idx)
                await rebuild_calendar(u_id, idx)
                log.info("back‑filled %s into %s", e_id, u_id)
        await asyncio.sleep(1)


# when the bot is ready, start web server, polling loop, and back‑fill task


@bot.event
async def on_ready():
    log.info("bot is online – starting background tasks")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
    asyncio.create_task(_sync_existing_events())
