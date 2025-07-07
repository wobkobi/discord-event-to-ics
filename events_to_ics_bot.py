"""
events_to_ics_bot.py
────────────────────
A Discord bot that gives every user a personal iCalendar feed of events
they mark “Interested” on.

Configuration via environment (e.g. a .env file):
  • DISCORD_TOKEN   – your bot token (required)
  • BASE_URL        – public base URL, e.g. https://calendar.example.com (required)
  • HTTP_PORT       – port to serve feeds on (optional; defaults to 8080)

Required Intents:
  • GUILD_SCHEDULED_EVENTS
  • MESSAGE_CONTENT
"""

from __future__ import annotations

import os
import re
import json
import asyncio
import datetime as dt
from pathlib import Path

import pytz
import aiohttp.web
import interactions
from interactions.api.events import GuildScheduledEventUserAdd
from ics import Calendar, Event
from dotenv import load_dotenv

# ─────────────── Configuration ───────────────
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("HTTP_PORT", "8080"))
TZ = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

if not TOKEN:
    raise RuntimeError("Environment variable DISCORD_TOKEN is required")
if not BASE_URL:
    raise RuntimeError("Environment variable BASE_URL is required")

DATA_DIR = Path(os.getenv("DATA_DIR", "calendars"))
DATA_DIR.mkdir(exist_ok=True)

intents = (
    interactions.Intents.DEFAULT
    | interactions.Intents.GUILD_SCHEDULED_EVENTS
    | interactions.Intents.MESSAGE_CONTENT
)
bot = interactions.Client(token=TOKEN, intents=intents)

EVENT_RE = re.compile(r"https?://(?:www\.)?discord\.com/events/(\d+)/(\d+)")

# ─────────────── HTTP Server ───────────────
app = aiohttp.web.Application()
app.add_routes([aiohttp.web.static("/cal", DATA_DIR, show_index=False)])


async def run_http():
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐  Serving calendar feeds on port {PORT}")


# ─────────────── Helpers ───────────────
def feed_url(user_id: int) -> str:
    return f"{BASE_URL}/cal/{user_id}.ics"


def idx_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


def ics_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.ics"


def load_index(user_id: int) -> list[dict]:
    try:
        text = idx_path(user_id).read_text()
        return json.loads(text) if text.strip() else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_index(user_id: int, index: list[dict]) -> None:
    idx_path(user_id).write_text(json.dumps(index))


def ensure_files(user_id: int) -> None:
    if not idx_path(user_id).exists():
        save_index(user_id, [])
    if not ics_path(user_id).exists():
        # start with an empty calendar
        ics_path(user_id).write_bytes(Calendar().serialize().encode())


def event_to_ics(ev) -> Event:
    e = Event()
    e.name = ev.name
    e.description = (ev.description or "")[:2000]
    e.url = f"https://discord.com/events/{ev.guild_id}/{ev.id}"
    e.begin = ev.start_time.astimezone(TZ)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(TZ)
    meta = getattr(ev, "entity_metadata", None)
    if meta and getattr(meta, "location", None):
        e.location = meta.location
    elif ev.channel_id:
        e.location = f"Discord channel {ev.channel_id}"
    return e


def rebuild_calendar(user_id: int, index: list[dict]) -> None:
    cal = Calendar()
    loop = asyncio.get_event_loop()
    for entry in index:
        try:
            ev = loop.run_until_complete(
                bot.fetch_scheduled_event(entry["guild_id"], entry["id"])
            )
            if ev:
                cal.events.add(event_to_ics(ev))
        except Exception:
            continue
    ics_path(user_id).write_bytes(cal.serialize().encode())


# ─────────────── Bot Events ───────────────
http_started = False


@bot.listen()
async def on_ready():
    global http_started
    if not http_started:
        asyncio.create_task(run_http())
        http_started = True
    print("✅ Bot is online and HTTP server started.")


@interactions.slash_command(
    name="mycalendar", description="Get a personal calendar-feed link in DMs"
)
async def mycalendar(ctx: interactions.SlashContext):
    uid = ctx.author.id
    ensure_files(uid)
    idx = load_index(uid)
    if idx:
        rebuild_calendar(uid, idx)

    url = feed_url(uid)
    webcal = url.replace("https://", "webcal://").replace("http://", "webcal://")

    await ctx.send("I’ve sent your personal calendar link via DM.", ephemeral=True)
    await ctx.author.send(
        "Here’s your personal calendar feed:\n\n"
        f"webcal:// link:\n`{webcal}`\n\n"
        f"HTTPS link:\n`{url}`\n\n"
        "Whenever you mark a server event as Interested, it will automatically\n"
        "appear in this feed."
    )
    print(f"🔗 Sent feed link to user {uid}")


@bot.listen(GuildScheduledEventUserAdd)
async def on_interested(event: GuildScheduledEventUserAdd):
    uid = event.user_id
    ensure_files(uid)

    idx = load_index(uid)
    record = {"guild_id": event.guild_id, "id": event.scheduled_event_id}
    if record in idx:
        return

    idx.append(record)
    save_index(uid, idx)
    rebuild_calendar(uid, idx)

    user = await bot.fetch_user(uid)
    try:
        ev = await bot.fetch_scheduled_event(event.guild_id, event.scheduled_event_id)
        await user.send(
            f"Added **{ev.name}** to your calendar feed ✅\n"
            f"Feed URL: {feed_url(uid)}"
        )
        print(f"➕ Added event {ev.id} for user {uid}")
    except interactions.Forbidden:
        print(f"⚠️ Could not DM user {uid}")


# ─────────────── Run ───────────────
if __name__ == "__main__":
    print("🚀 Starting Events→ICS Bot…")
    bot.start()
