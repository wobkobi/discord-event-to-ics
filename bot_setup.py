# bot_setup.py
import discord
from config import TOKEN

intents = discord.Intents.default()
intents.guilds           = True
intents.scheduled_events = True

bot = discord.Bot(intents=intents)   # single source of truth, importable anywhere
