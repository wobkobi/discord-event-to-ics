# main.py
"""
Entry point for the Events → ICS Bot.
Runs the Discord bot.
"""
import logging
from event_handlers import bot

# Configure logging to only show warnings and errors
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    # Essential startup message
    print("🚀 Starting Events → ICS Bot...")
    bot.start()
