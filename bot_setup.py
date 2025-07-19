# bot_setup.py – core bot client & command tree setup.

import logging
import discord
from discord import app_commands
from config import DISCORD_TOKEN, DEV_GUILD_ID

# Silence discord.py and aiohttp access logs for clarity
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# Intents
intents = discord.Intents.default()
intents.guilds = True
intents.guild_scheduled_events = True

# Instantiate the bot client
client = discord.Client(intents=intents)

# Create the slash-command tree that hooks into the client
tree = app_commands.CommandTree(client)

# Pull in event handlers and commands so they register at startup
import event_handlers
import bot_commands
