"""bot_commands.py – fast /mycalendar for the Events → ICS bot (Pycord)"""

import asyncio
import logging
import discord
from discord.errors import Forbidden

from bot_setup import bot
from calendar_builder import rebuild_calendar
from file_helpers import ensure_files, feed_url, load_index

log = logging.getLogger(__name__)

# ───────────────────── helper coroutine ──────────────────────


async def _build_and_dm(uid: int):
    """Rebuild the user’s feed off-thread and DM them when done."""
    ensure_files(uid)
    idx = load_index(uid)
    if idx:
        await rebuild_calendar(uid, idx)

    url = feed_url(uid)

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


# ───────────────────── slash-command ────────────────────────


@bot.slash_command(
    name="mycalendar",
    description="Get your personal calendar feed",
)
async def mycalendar(ctx: discord.ApplicationContext):
    """Respond instantly; rebuild & DM run in the background."""
    uid = int(ctx.author.id)
    log.info("/mycalendar invoked by user %s", uid)

    # respond immediately (< 1 s)
    await ctx.respond(
        "🛠 Building your calendar… I’ll DM you the link shortly.",
        ephemeral=True,
    )

    # kick off background task; no need to await
    asyncio.create_task(_build_and_dm(uid))
