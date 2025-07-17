import logging
import interactions
from interactions import SlashContext, Intents
from interactions.client.errors import Forbidden

from file_helpers import ensure_files, load_index
from calendar_builder import rebuild_calendar
from file_helpers import feed_url
from config import TOKEN

log = logging.getLogger(__name__)

# Request both GUILDS and Scheduled Events intents to avoid warnings
intents = Intents.GUILDS | Intents.GUILD_SCHEDULED_EVENTS
bot = interactions.Client(token=TOKEN, intents=intents)


@interactions.slash_command(
    name="mycalendar", description="Get your personal calendar feed"
)
async def mycalendar(ctx: SlashContext) -> None:
    """Handle /mycalendar command by generating and sending the user's feed link."""
    uid = int(ctx.author.id)  # type: ignore
    log.info(f"/mycalendar invoked by user {uid}")
    ensure_files(uid)
    idx = load_index(uid)
    if idx:
        await rebuild_calendar(uid, idx)
    url = feed_url(uid)
    await ctx.send("✅ A DM with your calendar link has been sent.", ephemeral=True)
    try:
        user = await bot.fetch_user(uid)
        if user:
            await user.send(
                f"Your calendar feed:\n• {url}\n\n"
                "Subscribe in your calendar app using this URL."
            )
            log.info(f"Sent calendar link to user {uid}")
    except Forbidden:
        log.warning(f"Cannot DM user {uid}")
