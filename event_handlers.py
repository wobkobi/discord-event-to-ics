# event_handlers.py – respond to Discord guild-scheduled-event webhooks (discord.py)

import asyncio
import logging
import discord

from bot_setup import client, tree
from calendar_builder import poll_new_events, rebuild_calendar
from config import DATA_DIR, DEV_GUILD_ID
from file_helpers import ensure_files, load_index, save_index
from server import run_http

log = logging.getLogger(__name__)


def _to_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@client.event
async def on_guild_scheduled_event_user_add(guild, user, event):
    uid = _to_int(user.id)
    gid = _to_int(guild.id)
    eid = _to_int(event.id)
    if not all((uid, gid, eid)):
        log.warning("Interest payload missing ids – skipping")
        return
    ensure_files(uid)
    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == gid for r in idx):
        idx.append({"guild_id": gid, "id": eid})
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s to user %s and rebuilt calendar", eid, uid)


@client.event
async def on_guild_scheduled_event_update(before, after):
    gid = _to_int(after.guild_id or (getattr(after, "guild", None) and after.guild.id))
    eid = _to_int(after.id)
    if eid is None:
        log.warning("Update payload missing event ID – skipping")
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


@client.event
async def on_guild_scheduled_event_delete(event):
    gid = _to_int(event.guild_id or (getattr(event, "guild", None) and event.guild.id))
    eid = _to_int(event.id)
    if eid is None:
        log.warning("Delete payload missing event ID – skipping")
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


@client.event
async def on_ready():
    if DEV_GUILD_ID:
        dev_guild = discord.Object(id=DEV_GUILD_ID)
        tree.copy_global_to(guild=dev_guild)
        await tree.sync(guild=dev_guild)
        print(f"🔧 ⚙️  Synced commands to DEV_GUILD_ID={DEV_GUILD_ID}")
    else:
        await tree.sync()
        print("🔧 ⚙️  Synced commands globally (may take up to 1 hour to appear)")
    print("🔧 Registered slash commands:")
    for cmd in tree.get_commands():
        print(" •", cmd.name)
    log.info("Bot is online; launching HTTP server and polling tasks.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
