# bot_commands.py – friendly slash commands for the Events  to  ICS Bot (discord.py)

import logging
import discord
from discord import app_commands

from bot_setup import client, tree
from file_helpers import (
    ensure_files,
    load_index,
    feed_url,
    load_settings,
    save_settings,
)
from calendar_builder import rebuild_calendar

log = logging.getLogger(__name__)


@tree.command(name="mycalendar", description="📅 Send you your personal calendar feed")
async def mycalendar(interaction: discord.Interaction):
    """Handle /mycalendar: rebuild feed and DM the webcal link."""
    uid = interaction.user.id
    log.info("User %s asked for their calendar", uid)

    # Make sure we have a place to store their index & feed
    ensure_files(uid)

    # Rebuild if they already have events tracked
    idx = load_index(uid)
    if idx:
        await interaction.response.send_message(
            "Hold on, I'm updating your calendar… ⏳", ephemeral=True
        )
        await rebuild_calendar(uid, idx)
    else:
        # First-time user or no events
        await interaction.response.send_message(
            "Looks like you haven't marked any events yet—your feed is empty.",
            ephemeral=True,
        )

    # Send the feed link via DM
    url = feed_url(uid)
    try:
        user = await client.fetch_user(uid)
        if user:
            await user.send(
                f"Hey there! 🎉\n"
                f"Here’s your calendar feed link:\n{url}\n\n"
                "Copy-paste that into your favorite calendar app (Apple, Outlook, Google)."
            )
            log.info("Sent calendar link to user %s", uid)
    except discord.Forbidden:
        log.warning("Could not DM user %s—they might have DMs disabled.", uid)


@tree.command(
    name="setalerts",
    description="⏰ Configure your reminder times (minutes before each event).",
)
@app_commands.describe(times="e.g. 0,15 for an alert at start and 15 minutes prior")
async def setalerts(interaction: discord.Interaction, times: str):
    """Handle /setalerts: parse and save user’s preferred alert offsets."""
    uid = interaction.user.id
    parts = [p.strip() for p in times.split(",")]
    alerts = []
    for part in parts:
        if part.isdigit():
            alerts.append(int(part))
        else:
            # ignore any non-numeric bits
            log.warning("Ignoring invalid alert time: %r from user %s", part, uid)
    alerts = sorted(set(alerts))

    # Save settings
    settings = load_settings(uid)
    settings["alerts"] = alerts
    save_settings(uid, settings)

    # Confirmation
    if alerts:
        desc = ", ".join(f"{a}m" for a in alerts)
        await interaction.response.send_message(
            f"✅ Got it! I'll remind you at {desc} before each event.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "⚠️ No valid alert times provided. Please give me minutes, like `0,15`.",
            ephemeral=True,
        )


@tree.command(
    name="setdefaultlength",
    description="⏳ Choose your default event duration (minutes) if no end time set.",
)
async def setdefaultlength(interaction: discord.Interaction, minutes: int):
    """Handle /setdefaultlength: save user’s preferred default event length."""
    uid = interaction.user.id

    # Persist their choice
    settings = load_settings(uid)
    settings["default_length"] = minutes
    save_settings(uid, settings)

    # Let them know
    await interaction.response.send_message(
        f"✅ Sweet! Events without an end time will now last {minutes} minutes by default.",
        ephemeral=True,
    )
