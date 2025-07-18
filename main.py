"""Entry point for the Events → ICS bot (no type‑hints)."""

import logging

from event_handlers import bot

# Log only warnings and errors from third‑party libs
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    print("🚀 Starting Events → ICS Bot…")
    bot.start()
