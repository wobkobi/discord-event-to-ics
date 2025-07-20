"""bot_commands.py – slash-commands for the Events → ICS bot (Pycord edition)"""

import logging
import discord
from discord.errors import Forbidden

from bot_setup import bot 
from calendar_builder import rebuild_calendar
from file_helpers import ensure_files, feed_url, load_index

log = logging.getLogger(__name__)


@bot.slash_command(
    name="mycalendar",
    description="Get your personal calendar feed",
)
async def mycalendar(ctx: discord.ApplicationContext):
    """Send the caller their webcal URL via DM (and rebuild the feed first)."""
    uid = int(ctx.author.id)
    log.info("/mycalendar invoked by user %s", uid)

    ensure_files(uid)
    idx = load_index(uid)
    if idx:
        await rebuild_calendar(uid, idx)

    url = feed_url(uid)
    await ctx.respond("✅ A DM with your calendar link has been sent.", ephemeral=True)

    try:
        user = await bot.fetch_user(uid)
        if user:
            await user.send(
                f"Your calendar feed:\n• {url}\n\n"
                "Subscribe in your calendar app using this URL."
            )
            log.info("Sent calendar link to user %s", uid)
    except Forbidden:
        log.warning("Cannot DM user %s", uid)
