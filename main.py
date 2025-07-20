"""bot_setup.py – defines the Pycord Bot *and* runs it when executed directly."""

import discord
from config import TOKEN

# ────────────────────── intents & construction ──────────────────────

intents = discord.Intents.default()
intents.guilds = True
intents.scheduled_events = True

bot = discord.Bot(intents=intents)  # exported for other modules

# ─────────────────────────── entry-point ────────────────────────────

if __name__ == "__main__":
    print("🚀 Starting Events → ICS Bot…")
    bot.run(TOKEN)  # blocking call
