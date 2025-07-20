"""main.py – launches the Events → ICS bot"""

import logging
from config import TOKEN
from bot_setup import bot  # ← import bot here

# ── register commands & listeners (these also import bot_setup, *not* main) ──
import calendar_builder  # defines rebuild_calendar / poll_new_events
import bot_commands
import event_handlers

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print("🚀 Starting Events → ICS Bot…")
    bot.run(TOKEN)
