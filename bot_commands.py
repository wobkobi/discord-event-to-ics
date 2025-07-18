"""bot_commands.py – slash commands for the Events → ICS Bot

Handles:
• `/mycalendar`  → rebuilds and DMs your webcal link
• `/setalerts`  → configure minutes-before alerts
• `/setdefaultlength` → set default duration for events w/o end-time
"""

import logging

from interactions.client.errors import Forbidden

from bot_setup import bot
from calendar_builder import rebuild_calendar
from file_helpers import (
    ensure_files,
    load_index,
    feed_url,
    load_settings,
    save_settings,
)

log = logging.getLogger(__name__)

# ───────────────────────── slash commands ──────────────────────────────────


@bot.slash_command(name="mycalendar", description="Get your personal calendar feed")
async def mycalendar(ctx):
    uid = int(ctx.author.id)
    log.info("/mycalendar invoked by user %s", uid)

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
            log.info("Sent calendar link to user %s", uid)
    except Forbidden:
        log.warning("Cannot DM user %s", uid)


@bot.slash_command(
    name="setalerts", description="Configure alert times (minutes before). E.g. 0,15"
)
async def setalerts(ctx, times: str):
    uid = int(ctx.author.id)
    parts = [p.strip() for p in times.split(",") if p.strip().isdigit()]
    alerts = sorted({int(p) for p in parts})
    settings = load_settings(uid)
    settings["alerts"] = alerts
    save_settings(uid, settings)
    await ctx.send(f"✅ Alerts set to: {alerts} minutes before", ephemeral=True)


@bot.slash_command(
    name="setdefaultlength",
    description="Set default event length in minutes for events without end-time",
)
async def setdefaultlength(ctx, minutes: int):
    uid = int(ctx.author.id)
    settings = load_settings(uid)
    settings["default_length"] = minutes
    save_settings(uid, settings)
    await ctx.send(f"✅ Default event length set to {minutes} minutes", ephemeral=True)
