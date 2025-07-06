import os
from io import StringIO
import datetime as dt

from dotenv import load_dotenv
import interactions
from ics import Calendar, Event
import pytz

load_dotenv()  # reads .env if present
TOKEN = os.getenv("DISCORD_TOKEN")  # ← no secret in code!

intents = interactions.Intents.DEFAULT | interactions.Intents.GUILD_SCHEDULED_EVENTS
bot = interactions.Client(token=TOKEN, intents=intents)


@interactions.slash_command(
    name="calendar",
    description="Export every upcoming Discord event as an .ics file",
)
async def calendar(ctx: interactions.SlashContext):
    """Slash command handler: /calendar"""
    await ctx.defer()  # small events can take >3 s

    guild = await ctx.get_guild()  # the server you ran it in
    events = (
        await guild.fetch_scheduled_events()
    )  # REST call, not cache    :contentReference[oaicite:1]{index=1}

    cal = Calendar()
    cal.events.clear()

    tz = pytz.timezone("Pacific/Auckland")

    for ev in events:
        if ev.status.name != "SCHEDULED":  # skip completed/cancelled
            continue

        e = Event()
        e.name = ev.name
        e.begin = ev.start_time.astimezone(tz)
        e.end = (
            ev.end_time.astimezone(tz)
            if ev.end_time
            else e.begin + dt.timedelta(hours=1)  # Discord lets end_time be None
        )
        if ev.location:  # “External” events
            e.location = ev.location
        elif ev.channel_id:  # Stage/voice/… channel
            channel = guild.get_channel(ev.channel_id)
            e.location = f"Discord • #{channel.name}"
        e.description = (ev.description or "")[
            :2000
        ]  # ics has no 2k limit but mail clients do
        e.url = f"https://discord.com/events/{guild.id}/{ev.id}"
        cal.events.add(e)

    # Serialise calendar to RAM, then attach
    fp = StringIO(cal.serialize())  # gives you valid text/*+calendar
    await ctx.send(files=[interactions.File(fp, "discord-events.ics")])


bot.start()
