"""bot_commands.py – slash-commands for the Events → ICS bot (fast DM version)"""

import asyncio
import logging
import discord
from discord.errors import Forbidden

from bot_setup import bot
from calendar_builder import rebuild_calendar
from file_helpers import ensure_files, feed_url, load_index

log = logging.getLogger(__name__)


async def _rebuild_in_background(uid: int):
    """Background task so /mycalendar returns fast."""
    idx = load_index(uid)
    if idx:
        await rebuild_calendar(uid, idx)
    log.info("Background rebuild for %s finished", uid)


@bot.slash_command(
    name="mycalendar",
    description="Get your personal calendar feed",
)
async def mycalendar(ctx: discord.ApplicationContext):
    """DM the caller their webcal URL; rebuild runs in the background."""
    uid = int(ctx.author.id)
    log.info("/mycalendar invoked by user %s", uid)

    # 1️⃣ Defer right away (ephemeral)
    await ctx.defer(ephemeral=True)

    # 2️⃣ Quick ops needed to craft the URL
    ensure_files(uid)
    url = feed_url(uid)

    # 3️⃣ DM the user immediately
    try:
        user = await bot.fetch_user(uid)
        if user:
            await user.send(
                f"Your calendar feed:\n• {url}\n\n"
                "Subscribe in your calendar app using this URL."
            )
            log.info("Sent calendar link to user %s", uid)
    except Forbidden:
        log.warning("Cannot DM user %s (DMs disabled)", uid)

    # 4️⃣ Acknowledge the slash command
    await ctx.followup.send(
        "✅ Check your DMs for the calendar link! "
        "I’ll finish updating the feed in the background.",
        ephemeral=True,
    )

    # 5️⃣ Kick off rebuild without blocking interaction
    asyncio.create_task(_rebuild_in_background(uid))
