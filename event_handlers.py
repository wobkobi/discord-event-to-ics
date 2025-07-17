import asyncio
import logging
from typing import Any

from interactions.client.errors import Forbidden

from bot_setup import bot
from file_helpers import ensure_files, load_index, save_index, feed_url
from calendar_builder import rebuild_calendar, poll_new_events
from server import run_http

log = logging.getLogger(__name__)


@bot.listen()
async def on_ready() -> None:
    """Start HTTP server and polling when the bot is ready."""
    try:
        log.info("Bot is online; launching HTTP server and polling tasks.")
        asyncio.create_task(run_http())
        asyncio.create_task(poll_new_events())
    except Exception:
        log.exception("Error during on_ready setup")


@bot.listen("guild_scheduled_event_user_add")
async def on_interested(ev: Any) -> None:
    """Handle when a user marks an event as Interested."""
    uid = int(ev.user_id)
    event_id = int(ev.scheduled_event_id)
    rec = {"guild_id": ev.guild_id, "id": event_id}
    try:
        log.info(f"User {uid} marked event {event_id} as Interested")
        ensure_files(uid)
        idx = load_index(uid)
        if rec not in idx:
            idx.append(rec)
            save_index(uid, idx)
            await rebuild_calendar(uid, idx)
            user = await bot.fetch_user(uid)
            if user:
                await user.send(f"Added event to your feed: {feed_url(uid)}")
                log.info(f"Sent DM to user {uid} for event {event_id}")
    except Forbidden:
        log.warning(f"Cannot DM user {uid}")
    except Exception:
        log.exception(f"Error handling interested event for user {uid}")
