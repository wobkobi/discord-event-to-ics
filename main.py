# main.py – launches the bot
# imports everything once so commands and listeners are registered, then runs

import logging

from config import TOKEN
from bot_setup import bot  # shared bot instance

# import side‑effect modules that add commands, listeners, and tasks
import calendar_builder
import bot_commands
import event_handlers

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print("🚀 starting events → ics bot…")
    bot.run(TOKEN)
