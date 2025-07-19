# main.py – entry point for the Events  to  ICS Bot (discord.py)

import logging
from config import DISCORD_TOKEN
from bot_setup import client

# Only show warnings and errors from third-party libraries
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    print("🚀 Starting Events  to  ICS Bot…")
    client.run(DISCORD_TOKEN)
