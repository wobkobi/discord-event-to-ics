import discord
from config import TOKEN

# ── create the bot ──
intents = discord.Intents.default()
intents.guilds = True
intents.scheduled_events = True
bot = discord.Bot(intents=intents)

# ── register commands & handlers ──
import bot_commands  # <— this registers /mycalendar
import event_handlers  # <— this registers your on_... listeners

# ── run it ──
if __name__ == "__main__":
    print("🚀 Starting Events → ICS Bot…")
    bot.run(TOKEN)
