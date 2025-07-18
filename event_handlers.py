"""event_handlers.py – respond to Discord guild‑scheduled‑event webhooks

Minimal version with no static‑type hints.  We still cast Discord Snowflakes to
plain `int` for JSON and file helpers, but all typing imports and `# type:`
comments have been removed for brevity.
"""

import asyncio
import logging

from interactions.api.events import (
    GuildScheduledEventDelete,
    GuildScheduledEventUpdate,
    GuildScheduledEventUserAdd,
)

from bot_setup import bot  # the interactions.Client instance
from calendar_builder import poll_new_events, rebuild_calendar
from config import DATA_DIR
from file_helpers import ensure_files, load_index, save_index
from server import run_http

log = logging.getLogger(__name__)

# ───────────────────────────── helpers ──────────────────────────────────────


def _to_int(value):
    """Return int(value) when possible, else None."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_ids(evt):
    """Return (guild_id, event_id) for any scheduled‑event payload."""
    for attr in ("scheduled_event", "after", "before"):
        se = getattr(evt, attr, None)
        if se:
            gid = _to_int(getattr(se, "guild_id", None))
            eid = _to_int(getattr(se, "id", None))
            if gid and eid:
                return gid, eid

    gid = _to_int(getattr(evt, "guild_id", None))
    eid = _to_int(getattr(evt, "scheduled_event_id", None) or getattr(evt, "id", None))
    return gid, eid


# ───────────────────────── listeners ────────────────────────────────────────


@bot.listen(GuildScheduledEventUserAdd)
async def on_interested(evt):
    uid = _to_int(evt.user_id)
    gid, eid = _extract_ids(evt)

    if not all((uid, gid, eid)):
        log.warning("Interested payload missing ids – skipping")
        return

    ensure_files(uid)

    rec = {"guild_id": gid, "id": eid}

    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == gid for r in idx):
        idx.append(rec)
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s to user %s and rebuilt calendar", eid, uid)


@bot.listen(GuildScheduledEventUpdate)
async def on_event_updated(evt):
    gid, eid = _extract_ids(evt)
    if not all((gid, eid)):
        log.warning("Event update without ids – skipping")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        if any(r["id"] == eid and r["guild_id"] == gid for r in idx):
            await rebuild_calendar(uid, idx)
            log.info("Rebuilt calendar for %s after update to event %s", uid, eid)


@bot.listen(GuildScheduledEventDelete)
async def on_event_deleted(evt):
    gid, eid = _extract_ids(evt)
    if not all((gid, eid)):
        log.warning("Event delete without ids – skipping")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        new_idx = [r for r in idx if not (r["id"] == eid and r["guild_id"] == gid)]
        if new_idx != idx:
            save_index(uid, new_idx)
            await rebuild_calendar(uid, new_idx)
            log.info(
                "Removed deleted event %s from user %s and rebuilt calendar", eid, uid
            )


# ---------------------------------------------------------------------------
# ready – start HTTP + poller
# ---------------------------------------------------------------------------


@bot.listen("ready")
async def on_ready(_):
    log.info("Bot is online; launching HTTP server and polling tasks.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
