# bot_setup.py – creates and exports the shared Pycord bot

import discord
from config import TOKEN

# pick the gateway intents we actually use
intents = discord.Intents.default()
# lets us see guild info
intents.guilds = True
# gives us event create/update/delete hooks
intents.scheduled_events = True

# one bot object for the whole project
bot = discord.Bot(intents=intents)

# run this file directly to start the bot fast for testing
if __name__ == "__main__":
    bot.run(TOKEN)
