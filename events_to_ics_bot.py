#!/usr/bin/env python3
"""
events_to_ics_bot.py

A Discord bot that gives every user a personal iCalendar feed of Interested events,
with robust error handling, detailed logging, and a simple homepage.
"""

from __future__ import annotations
import os
import json
import asyncio
import datetime as dt
import traceback
import logging
from pathlib import Path
from typing import Any, cast

import pytz
import aiohttp.web
import interactions
from interactions.client.errors import Forbidden
from ics import Calendar, Event
from dotenv import load_dotenv

# ─── Configuration ────────────────────────────────────────────
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
HTTP_PORT = int(os.getenv("HTTP_PORT","")) 
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")
GUILD_SCOPE: list[int] | None = [int(DEV_GUILD_ID)] if DEV_GUILD_ID else None

if not TOKEN:
    raise RuntimeError("⚠️ DISCORD_TOKEN is required")
if not BASE_URL:
    raise RuntimeError("⚠️ BASE_URL is required")

# Directory where we store per-user indexes and .ics files
DATA_DIR = Path(os.getenv("DATA_DIR", "calendars"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─── Logging Setup ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("events_to_ics")

# ─── Bot Setup ───────────────────────────────────────────────
intents = (
    interactions.Intents.DEFAULT
    | interactions.Intents.GUILD_SCHEDULED_EVENTS
    | interactions.Intents.MESSAGE_CONTENT
)
bot = interactions.Client(token=TOKEN, intents=intents)

# ─── HTTP Server ─────────────────────────────────────────────
app = aiohttp.web.Application()


@aiohttp.web.middleware
async def request_logger(request, handler):
    log.info(f"HTTP {request.method} {request.path_qs} from {request.remote}")
    try:
        return await handler(request)
    except Exception:
        log.exception("Error handling HTTP request")
        return aiohttp.web.Response(text="Internal server error", status=500)


app.middlewares.append(request_logger)


async def handle_home(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """
    Serve a simple homepage explaining how to use the bot.
    """
    html = f"""
    <html>
      <head><title>Discord Events → ICS Bot</title></head>
      <body style="font-family: sans-serif; padding: 2rem;">
        <h1>Discord Events → ICS Bot</h1>
        <p>In Discord, run <code>/mycalendar</code> to receive your personal feed link.</p>
        <p>Feeds are served at: <code>{BASE_URL}/cal/&lt;YOUR_USER_ID&gt;.ics</code></p>
      </body>
    </html>
    """
    return aiohttp.web.Response(text=html, content_type="text/html")


# Mount static ICS feeds under /cal
app.add_routes(
    [
        aiohttp.web.get("/", handle_home),
        aiohttp.web.static("/cal", DATA_DIR, show_index=False),
    ]
)


async def run_http() -> None:
    """
    Start the aiohttp server on 0.0.0.0:HTTP_PORT.
    """
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    log.info(f"HTTP server running on port {HTTP_PORT}")


# ─── File & Calendar Helpers ─────────────────────────────────
def feed_url(uid: int) -> str:
    """Return the public HTTPS URL of a user's .ics feed."""
    return f"{BASE_URL}/cal/{uid}.ics"


def idx_path(uid: int) -> Path:
    """Return the Path to the user's JSON index."""
    return DATA_DIR / f"{uid}.json"


def ics_path(uid: int) -> Path:
    """Return the Path to the user's ICS file."""
    return DATA_DIR / f"{uid}.ics"


def load_index(uid: int) -> list[dict]:
    """
    Load a user's index (list of {"guild_id":…, "id":…}) from disk.
    On any error, returns an empty list.
    """
    try:
        raw = idx_path(uid).read_text()
        return json.loads(raw) if raw.strip() else []
    except Exception:
        log.exception(f"Failed to load index for user {uid}")
        return []


def save_index(uid: int, idx: list[dict]) -> None:
    """Save a user's index list back to disk."""
    try:
        idx_path(uid).write_text(json.dumps(idx))
    except Exception:
        log.exception(f"Failed to save index for user {uid}")


def ensure_files(uid: int) -> None:
    """
    Guarantee both the JSON index and ICS file exist for this user.
    Creates empty ones if missing.
    """
    try:
        if not idx_path(uid).exists():
            save_index(uid, [])
        if not ics_path(uid).exists():
            ics_path(uid).write_bytes(Calendar().serialize().encode())
    except Exception:
        log.exception(f"Failed to ensure files for user {uid}")


def event_to_ics(ev: Any) -> Event:
    """
    Convert a Discord ScheduledEvent object into an ics.Event.
    """
    e = Event()
    e.name = ev.name
    e.description = (ev.description or "")[:2000]
    e.url = f"https://discord.com/events/{ev.guild_id}/{ev.id}"
    e.begin = ev.start_time.astimezone(TIMEZONE)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(
        TIMEZONE
    )
    meta = getattr(ev, "entity_metadata", None)
    if meta and getattr(meta, "location", None):
        e.location = meta.location
    elif ev.channel_id:
        e.location = f"Discord channel {ev.channel_id}"
    return e


def rebuild_calendar(uid: int, idx: list[dict]) -> None:
    """
    Re-fetch every event in the user's index and write out a new ICS file.
    """
    try:
        cal = Calendar()
        loop = asyncio.get_event_loop()
        for rec in idx:
            try:
                guild_id = int(rec["guild_id"])
                ev_id = int(rec["id"])
                ev = loop.run_until_complete(bot.fetch_scheduled_event(guild_id, ev_id))
                if ev:
                    cal.events.add(event_to_ics(ev))
            except Exception:
                log.exception(f"Skipping failed event fetch {rec}")
                continue
        ics_path(uid).write_bytes(cal.serialize().encode())
    except Exception:
        log.exception(f"Failed to rebuild calendar for user {uid}")


# ─── Bot Event Handlers ──────────────────────────────────────
http_started = False


@bot.listen()
async def on_ready():
    """When the bot is ready, start the HTTP server (once)."""
    global http_started
    if not http_started:
        asyncio.create_task(run_http())
        http_started = True
    log.info("Bot is online; HTTP server started.")


# Build slash‐command kwargs with correct types
cmd_kwargs: dict[str, Any] = {
    "name": "mycalendar",
    "description": "Get your personal calendar-feed link",
}
if GUILD_SCOPE:
    cmd_kwargs["scopes"] = GUILD_SCOPE


@interactions.slash_command(**cmd_kwargs)
async def mycalendar(ctx: interactions.SlashContext):
    """
    /mycalendar
    Ensures user files exist, rebuilds their feed if needed, and DMs them the link.
    """
    uid = int(ctx.author.id)
    try:
        ensure_files(uid)
        idx = load_index(uid)
        if idx:
            rebuild_calendar(uid, idx)

        url = feed_url(uid)
        webcal = url.replace("https://", "webcal://").replace("http://", "webcal://")

        await ctx.send("✅ I've DM’d you your calendar link.", ephemeral=True)
        author = cast(interactions.User, ctx.author)
        await author.send(
            f"Here’s your personal calendar feed:\n\n"
            f"• webcal://{webcal}\n"
            f"• {url}\n\n"
            "Whenever you mark an event **Interested**, it appears here automatically."
        )
        log.info(f"Sent feed link to user {uid}")
    except Exception:
        log.exception(f"Error in /mycalendar for user {uid}")
        await ctx.send(
            "⚠️ Could not generate your calendar link. Please try again later.",
            ephemeral=True,
        )


@bot.listen("guild_scheduled_event_user_add")
async def on_interested(ev: Any):
    """
    Fires when a user marks a scheduled event as Interested.
    Adds it to their index, rebuilds their calendar, and notifies them by DM.
    """
    uid = int(ev.user_id)
    rec = {"guild_id": int(ev.guild_id), "id": int(ev.scheduled_event_id)}
    try:
        ensure_files(uid)
        idx = load_index(uid)
        if rec in idx:
            return  # already added

        idx.append(rec)
        save_index(uid, idx)
        rebuild_calendar(uid, idx)

        user = cast(interactions.User, await bot.fetch_user(uid))
        se = await bot.fetch_scheduled_event(
            int(ev.guild_id), int(ev.scheduled_event_id)
        )
        name = getattr(se, "name", "an event")
        await user.send(f"✅ Added **{name}** to your feed: {feed_url(uid)}")
        log.info(f"➕ Added event {ev.scheduled_event_id} for user {uid}")
    except Forbidden:
        log.warning(f"Cannot DM user {uid} (DMs may be closed)")
    except Exception:
        log.exception(f"Error handling interest for user {uid}")


# ─── Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    log.info("🚀 Starting Events → ICS bot…")
    bot.start()
