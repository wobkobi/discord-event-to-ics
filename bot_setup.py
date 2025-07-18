"""bot_setup.py – create and export the Discord client (no type‑hints)."""

import logging

from interactions import Client, Intents
from config import TOKEN

# Silence overly‑verbose logs from dependencies
logging.getLogger("interactions").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# We need basic guild data + scheduled‑event gateway events
intents = Intents.GUILDS | Intents.GUILD_SCHEDULED_EVENTS

# The bot instance used throughout the project
bot = Client(
    token=TOKEN,
    intents=intents,
    sync_interactions=True,
)
