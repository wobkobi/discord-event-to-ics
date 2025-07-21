"""bot_commands.py – slash-commands for the Events → ICS bot

All static-type hints have been stripped for simplicity. The command logic is
unchanged: `/mycalendar` DMs the caller their personal webcal link, rebuilding
their feed on-demand.
"""

import logging

import interactions
from interactions import Intents
from interactions.client.errors import Forbidden

from calendar_builder import rebuild_calendar
from config import TOKEN
from file_helpers import ensure_files, feed_url, load_index

log = logging.getLogger(__name__)

# bot setup

intents = Intents.GUILDS | Intents.GUILD_SCHEDULED_EVENTS
bot = interactions.Client(token=TOKEN, intents=intents)

# slash-commands


@interactions.slash_command(
    name="mycalendar", description="Get your personal calendar feed"
)
async def mycalendar(ctx):
    """Send the caller their webcal URL via DM (and rebuild the feed first)."""

    uid = int(ctx.author.id)
    log.info("/mycalendar invoked by user %s", uid)

    ensure_files(uid)
    idx = load_index(uid)
    if idx:
        await rebuild_calendar(uid, idx)

    url = feed_url(uid)

    # Let the slash response vanish for other users
    await ctx.send("✅ A DM with your calendar link has been sent.", ephemeral=True)

    try:
        user = await bot.fetch_user(uid)
        if user:
            await user.send(
                "Your calendar feed:\n• {url}\n\n"
                "Subscribe in your calendar app using this URL.".format(url=url)
            )
            log.info("Sent calendar link to user %s", uid)
    except Forbidden:
        log.warning("Cannot DM user %s", uid)
