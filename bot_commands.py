# bot_commands.py – slash commands for the calendar bot
# /mycalendar  – DMs you your personal webcal link (feed rebuilds in the background)
# /setalerts <min1> [min2] – sets default popup reminders

import asyncio
import logging
import discord
from discord.errors import Forbidden

from bot_setup import bot
from calendar_builder import rebuild_calendar
from file_helpers import (
    ensure_files,
    feed_url,
    load_index,
    save_guild_alerts,
)

log = logging.getLogger(__name__)


# helper: rebuild a user’s feed without blocking the slash response
async def _rebuild_async(uid: int):
    idx = load_index(uid)
    if idx:
        await rebuild_calendar(uid, idx)
    log.info("calendar rebuild finished for %s", uid)


# /mycalendar – send the link and kick off a rebuild
@bot.slash_command(name="mycalendar", description="DM me my personal calendar link")
async def mycalendar(ctx: discord.ApplicationContext):
    uid = int(ctx.author.id)
    log.info("/mycalendar by %s", uid)

    # keeps the interaction alive
    await ctx.defer(ephemeral=True)

    ensure_files(uid)
    url = feed_url(uid)

    # DM the link
    try:
        user = await bot.fetch_user(uid)
        await user.send(
            "Hey there! 🎉\n"
            "Here’s your calendar feed link:\n"
            f"`{url}`\n\n"
            "Copy & paste that into your calendar app."
        )
        dm_ok = True
    except (Forbidden, AttributeError):
        dm_ok = False
        log.warning("DM failed for %s", uid)

    msg = (
        "✅ Check your DMs for the link!"
        if dm_ok
        else "⚠️ I couldn’t DM you. Are your DMs closed?"
    )
    await ctx.followup.send(msg, ephemeral=True)

    # rebuild feed in the background
    asyncio.create_task(_rebuild_async(uid))


# /setalerts – configure server‑wide default reminders
@bot.slash_command(
    name="setalerts",
    description="Set default popup reminders (minutes before event)",
    default_member_permissions=discord.Permissions(manage_guild=True),
)
async def setalerts(
    ctx: discord.ApplicationContext,
    alert1: int,  # required first alert in minutes
    alert2: int | None = None,  # optional second alert in minutes
):
    if alert1 <= 0 or (alert2 is not None and alert2 <= 0):
        await ctx.respond("Times must be positive minutes.", ephemeral=True)
        return

    alerts = sorted([alert1] + ([alert2] if alert2 is not None else []))
    alert1 = alerts[0]
    alert2 = alerts[1] if len(alerts) > 1 else None

    save_guild_alerts(ctx.guild_id, alert1, alert2)

    txt = (
        f"Default reminders set to {alert1} min"
        + (f" and {alert2} min" if alert2 else "")
        + " before every event."
    )
    await ctx.respond(txt, ephemeral=True)

    log.info("Guild %s updated alerts to %s", ctx.guild_id, alerts)
