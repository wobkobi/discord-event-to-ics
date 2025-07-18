# bot_setup.py
"""
Initializes and exports the Discord bot instance with required intents.
"""
import logging
from interactions import Intents, Client

from config import TOKEN

# Configure logging for the bot
logging.getLogger("interactions").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# Request both GUILDS and Scheduled Events intents
intents = Intents.GUILDS | Intents.GUILD_SCHEDULED_EVENTS

# Instantiate the bot client
bot = Client(
    token=TOKEN,
    intents=intents,
    sync_interactions=True,  # push commands at startup
)
