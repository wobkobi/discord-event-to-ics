"""
events_to_ics_bot.py
────────────────────
• /mycalendar   → DM you a personal calendar-feed URL
• “Interested”  → auto-append that event to your .ics feed
• HTTP server  → serves /cal/<user_id>.ics so calendar apps auto-refresh

Env vars:
  DISCORD_TOKEN your bot token
  BASE_URL      e.g. https://your.domain      (default http://localhost:8080)
  HTTP_PORT     port to serve on (default 8080)

Intents: GUILD_SCHEDULED_EVENTS + MESSAGE_CONTENT
Invite perms integer: 41488 (VIEW_CHANNEL, READ_MESSAGE_HISTORY,
                          SEND_MESSAGES, ATTACH_FILES)
"""

from __future__ import annotations

import os
import re
import json
import asyncio
import datetime as dt
import sys
from pathlib import Path
from io import BytesIO

import aiohttp
import aiohttp.web
import interactions  # pip install interactions.py
from interactions.api.events import GuildScheduledEventUserAdd
from ics import Calendar, Event  # pip install ics
import pytz  # pip install pytz
from dotenv import load_dotenv

# ─────────── config ───────────
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
HTTP_PORT = int(os.getenv("HTTP_PORT", 8080))
TZ = pytz.timezone("Pacific/Auckland")

if not TOKEN:
    print("DISCORD_TOKEN missing", file=sys.stderr)
    sys.exit(1)

CAL_DIR = Path("calendars")
CAL_DIR.mkdir(exist_ok=True)

intents = (
    interactions.Intents.DEFAULT
    | interactions.Intents.GUILD_SCHEDULED_EVENTS
    | interactions.Intents.MESSAGE_CONTENT
)
bot = interactions.Client(token=TOKEN, intents=intents)

EVENT_URL_RE = re.compile(r"https?://(?:www\.)?discord\.com/events/(\d+)/(\d+)")

# ─────────── HTTP server ───────────
app = aiohttp.web.Application()
app.add_routes([aiohttp.web.static("/cal", CAL_DIR, show_index=False)])


async def run_http():
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    print(f"🌐  Calendar HTTP server on port {HTTP_PORT}")


# ─────────── helpers ───────────
def load_index(user_id: int) -> list[dict]:
    f = CAL_DIR / f"{user_id}.json"
    try:
        text = f.read_text()
        if not text.strip():
            return []
        return json.loads(text)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_index(user_id: int, idx: list[dict]):
    (CAL_DIR / f"{user_id}.json").write_text(json.dumps(idx))


def ensure_user_feed(user_id: int):
    idx_file = CAL_DIR / f"{user_id}.json"
    ics_file = CAL_DIR / f"{user_id}.ics"
    if not idx_file.exists():
        idx_file.write_text("[]")
    if not ics_file.exists():
        ics_file.write_bytes(Calendar().serialize().encode())


def feed_url(user_id: int) -> str:
    return f"{BASE_URL}/cal/{user_id}.ics"


def model_to_ics(ev) -> Event:
    e = Event()
    e.name = ev.name
    e.description = (ev.description or "")[:2000]
    e.url = f"https://discord.com/events/{ev.guild_id}/{ev.id}"
    e.begin = ev.start_time.astimezone(TZ)
    e.end = (ev.end_time or (ev.start_time + dt.timedelta(hours=1))).astimezone(TZ)
    if ev.entity_metadata and ev.entity_metadata.location:
        e.location = ev.entity_metadata.location
    elif ev.channel_id:
        e.location = f"Discord channel {ev.channel_id}"
    return e


def regenerate_calendar(user_id: int, idx: list[dict]):
    cal = Calendar()
    for item in idx:
        try:
            ev = asyncio.run_coroutine_threadsafe(
                bot.fetch_scheduled_event(item["guild_id"], item["id"]),
                asyncio.get_event_loop(),
            ).result()
            if ev:
                cal.events.add(model_to_ics(ev))
        except Exception:
            continue
    (CAL_DIR / f"{user_id}.ics").write_bytes(cal.serialize().encode())


# ─────────── event hooks ───────────
http_started = False


@bot.listen()
async def on_ready():
    global http_started
    if not http_started:
        asyncio.create_task(run_http())
        http_started = True
    print("✅  Bot connected.")


@interactions.slash_command(
    name="mycalendar",
    description="DM me my personal calendar-feed link",
)
async def mycalendar(ctx: interactions.SlashContext):
    ensure_user_feed(ctx.author.id)
    idx = load_index(ctx.author.id)
    if idx:
        regenerate_calendar(ctx.author.id, idx)
    url = feed_url(ctx.author.id)
    webcal = url.replace("https://", "webcal://").replace("http://", "webcal://")
    await ctx.send("I’ve sent your feed link in DMs!", ephemeral=True)
    await ctx.author.send(
        f"Your personal calendar feed:\n\n"
        f"webcal:// link:\n`{webcal}`\n\n"
        f"https:// link:\n`{url}`\n\n"
        "Events you mark **Interested** will appear automatically."
    )
    print(f"🔗  Sent feed URL to user {ctx.author.id}")


@bot.listen(GuildScheduledEventUserAdd)
async def on_interested(event: GuildScheduledEventUserAdd):
    user_id = event.user_id
    ensure_user_feed(user_id)

    idx = load_index(user_id)
    if any(item["id"] == event.scheduled_event_id for item in idx):
        return
    idx.append({"guild_id": event.guild_id, "id": event.scheduled_event_id})
    save_index(user_id, idx)
    regenerate_calendar(user_id, idx)

    user = await bot.fetch_user(user_id)
    try:
        ev = await bot.fetch_scheduled_event(event.guild_id, event.scheduled_event_id)
        await user.send(
            f"Added **{ev.name}** to your calendar feed ✅\n"
            f"Feed URL: {feed_url(user_id)}"
        )
        print(f"➕  {ev.name} added for user {user_id}")
    except interactions.Forbidden:
        print(f"⚠️  Could not DM user {user_id}")


# ─────────── run ───────────
if __name__ == "__main__":
    print("🚀  Starting Events→ICS bot …")
    bot.start()
