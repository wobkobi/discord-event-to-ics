import logging
from config import TOKEN
from bot_setup import bot  # ← import here, not from event handlers

# register everything (these files will import bot_setup, not main)
import bot_commands
import event_handlers

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    print("🚀 Starting Events → ICS Bot…")
    bot.run(TOKEN)
