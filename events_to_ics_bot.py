"""
events_to_ics_bot.py
────────────────────
A Discord bot that gives every user a personal iCalendar feed of Interested events.

Config via .env or environment:
  DISCORD_TOKEN   – bot token (required)
  BASE_URL        – public URL base (e.g. https://calendar.example.com) (required)
  HTTP_PORT       – port for feeds (default: 8080)
  DEV_GUILD_ID    – if set, register slash cmds only to this guild for testing

Required intents:
  GUILD_SCHEDULED_EVENTS, MESSAGE_CONTENT
"""

from __future__ import annotations
import os, re, json, asyncio, datetime as dt
from pathlib import Path

import pytz
import aiohttp.web
import interactions
from interactions.api.events import GuildScheduledEventUserAdd
from ics import Calendar, Event
from dotenv import load_dotenv

# ─── Config ──────────────────────────────────────────────────
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN") or ""
BASE_URL = os.getenv("BASE_URL") or ""
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
TZ = pytz.timezone(os.getenv("TIMEZONE", "UTC"))

DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")
GUILD_SCOPE = [int(DEV_GUILD_ID)] if DEV_GUILD_ID else None

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is required")
if not BASE_URL:
    raise RuntimeError("BASE_URL is required")

# where we store per-user .json indexes and .ics feeds
DATA_DIR = Path(os.getenv("DATA_DIR", "calendars"))
DATA_DIR.mkdir(exist_ok=True)

# ─── Bot & Intents ───────────────────────────────────────────
intents = (
    interactions.Intents.DEFAULT
    | interactions.Intents.GUILD_SCHEDULED_EVENTS
    | interactions.Intents.MESSAGE_CONTENT
)
bot = interactions.Client(token=TOKEN, intents=intents)

EVENT_RE = re.compile(r"https?://(?:www\.)?discord\.com/events/(\d+)/(\d+)")

# ─── HTTP Server ─────────────────────────────────────────────
app = aiohttp.web.Application()
app.add_routes([aiohttp.web.static("/cal", DATA_DIR, show_index=False)])


async def run_http():
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    print(f"🌐  Serving /cal on port {HTTP_PORT}")


# ─── Helpers ──────────────────────────────────────────────────
def feed_url(uid: int) -> str:
    return f"{BASE_URL}/cal/{uid}.ics"


def idx_path(uid: int) -> Path:
    return DATA_DIR / f"{uid}.json"


def ics_path(uid: int) -> Path:
    return DATA_DIR / f"{uid}.ics"


def load_index(uid: int) -> list[dict]:
    try:
        txt = idx_path(uid).read_text()
        return json.loads(txt) if txt.strip() else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_index(uid: int, idx: list[dict]) -> None:
    idx_path(uid).write_text(json.dumps(idx))


def ensure_files(uid: int) -> None:
    if not idx_path(uid).exists():
        save_index(uid, [])
    if not ics_path(uid).exists():
        ics_path(uid).write_bytes(Calendar().serialize().encode())


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


def rebuild_calendar(uid: int, idx: list[dict]) -> None:
    cal = Calendar()
    loop = asyncio.get_event_loop()
    for ent in idx:
        try:
            ev = loop.run_until_complete(
                bot.fetch_scheduled_event(ent["guild_id"], ent["id"])
            )
            if ev:
                cal.events.add(event_to_ics(ev))
        except Exception:
            continue
    ics_path(uid).write_bytes(cal.serialize().encode())


# ─── Bot Events ──────────────────────────────────────────────
http_started = False


@bot.listen()
async def on_ready():
    global http_started
    if not http_started:
        asyncio.create_task(run_http())
        http_started = True
    print("✅ Bot is online; HTTP server started.")


# dynamic slash_command decorator args
base_kwargs = dict(
    name="mycalendar", description="Get a personal calendar-feed link in DMs"
)
if GUILD_SCOPE:
    base_kwargs["scopes"] = GUILD_SCOPE


@interactions.slash_command(**base_kwargs)
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
        "Whenever you mark an event **Interested**, it appears here automatically."
    )
    print(f"🔗 Sent feed link to {uid}")


@bot.listen(GuildScheduledEventUserAdd)
async def on_interested(ev: GuildScheduledEventUserAdd):
    uid = ev.user_id
    ensure_files(uid)

    idx = load_index(uid)
    rec = {"guild_id": ev.guild_id, "id": ev.scheduled_event_id}
    if rec in idx:
        return

    idx.append(rec)
    save_index(uid, idx)
    rebuild_calendar(uid, idx)

    user = await bot.fetch_user(uid)
    try:
        se = await bot.fetch_scheduled_event(ev.guild_id, ev.scheduled_event_id)
        await user.send(
            f"Added **{se.name}** to your feed ✅\nFeed URL: {feed_url(uid)}"
        )
        print(f"➕ Added {se.id} for user {uid}")
    except interactions.Forbidden:
        print(f"⚠️ Cannot DM user {uid}")


# ─── Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Starting Events→ICS bot…")
    bot.start()
