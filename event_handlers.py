"""event_handlers.py – respond to Discord guild‑scheduled‑event webhooks
Minimal, no type‑hints.  Fixes the earlier syntax error and restores three
listeners (add, update, delete) with optional guild‑ID matching.
"""

import asyncio
import logging

from interactions.api.events import (
    GuildScheduledEventDelete,
    GuildScheduledEventUpdate,
    GuildScheduledEventUserAdd,
)

from bot_setup import bot
from calendar_builder import poll_new_events, rebuild_calendar
from config import DATA_DIR
from file_helpers import ensure_files, load_index, save_index
from server import run_http

log = logging.getLogger(__name__)

# ───────────────────────── helpers ─────────────────────────────────────────


def _to_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _dump_attrs(obj, label="evt"):
    attrs = {n: getattr(obj, n) for n in dir(obj) if not n.startswith("__")}
    log.warning("%s attrs → %s", label, attrs)


def _id_from_se(se):
    if not se:
        return None, None
    gid = _to_int(getattr(se, "guild_id", None)) or _to_int(
        getattr(getattr(se, "guild", None), "id", None)
    )
    eid = _to_int(getattr(se, "id", None))
    return gid, eid


def _extract_ids(evt):
    """Return (guild_id, event_id) no matter how the payload is shaped."""
    for attr in ("scheduled_event", "after", "before", "event"):
        gid, eid = _id_from_se(getattr(evt, attr, None))
        if eid:  # event_id is mandatory; guild_id may be None
            return gid, eid
    gid = _to_int(getattr(evt, "guild_id", None))
    eid = _to_int(getattr(evt, "scheduled_event_id", None) or getattr(evt, "id", None))
    return gid, eid


# ───────────────────────── listeners ───────────────────────────────────────


@bot.listen(GuildScheduledEventUserAdd)
async def on_interested(evt):
    uid = _to_int(evt.user_id)
    gid, eid = _extract_ids(evt)
    if uid is None or eid is None:
        log.warning("Interested payload missing ids – skipping")
        _dump_attrs(evt, "interested_evt")
        return

    ensure_files(uid)
    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == (gid or r["guild_id"]) for r in idx):
        idx.append({"guild_id": gid or 0, "id": eid})
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s to user %s and rebuilt calendar", eid, uid)


@bot.listen(GuildScheduledEventUpdate)
async def on_event_updated(evt):
    gid, eid = _extract_ids(evt)
    if eid is None:
        log.warning("Event update without event_id – skipping")
        _dump_attrs(evt, "update_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        if any(r["id"] == eid and (gid is None or r["guild_id"] == gid) for r in idx):
            await rebuild_calendar(uid, idx)
            log.info("Rebuilt calendar for %s after update to event %s", uid, eid)


@bot.listen(GuildScheduledEventDelete)
async def on_event_deleted(evt):
    gid, eid = _extract_ids(evt)
    if eid is None:
        log.warning("Event delete without event_id – skipping")
        _dump_attrs(evt, "delete_evt")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx = load_index(uid)
        new_idx = [
            r
            for r in idx
            if not (r["id"] == eid and (gid is None or r["guild_id"] == gid))
        ]
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
