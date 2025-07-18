"""event_handlers.py – respond to Discord guild-scheduled-event webhooks

All IDs coming from `interactions.py` are `Snowflake_Type`, typed as
`Union[int, str]` and thus *not* accepted as `SupportsInt`.  We cast each ID to
`int` at the boundary using `_to_int()`, which accepts either form and keeps
static type‑checkers quiet.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, SupportsInt, Tuple, Union

from interactions import listen
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

# ---------------------------------------------------------------------------
# ────────────────  helpers  ────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _to_int(value: Union[SupportsInt, str, None]) -> int | None:  # noqa: D401
    """Convert a Snowflake (int‑like or numeric str) to `int`, else **None**.

    *Accepts* → `int`, any object implementing `__int__`, numeric `str`, or
    `None`.  Returns `None` if the input is `None` or cannot be sensibly cast.
    """

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_ids(evt: Any) -> Tuple[int | None, int | None]:
    """Return `(guild_id, event_id)` for *any* guild‑scheduled‑event payload."""

    # 1) look for a ScheduledEvent object in common attributes
    for attr in ("scheduled_event", "after", "before"):
        se = getattr(evt, attr, None)
        if se is not None:
            gid = _to_int(getattr(se, "guild_id", None))
            eid = _to_int(getattr(se, "id", None))
            if gid is not None and eid is not None:
                return gid, eid

    # 2) fall back to flat fields present on some payloads
    gid = _to_int(getattr(evt, "guild_id", None))
    eid = _to_int(getattr(evt, "scheduled_event_id", None) or getattr(evt, "id", None))
    return gid, eid


# ---------------------------------------------------------------------------
# 1) User clicks “Interested”
# ---------------------------------------------------------------------------


@listen(GuildScheduledEventUserAdd)
async def on_interested(evt: GuildScheduledEventUserAdd):  # noqa: D401
    """Add the event to the user’s index and rebuild their calendar."""

    uid = _to_int(evt.user_id)
    gid, eid = _extract_ids(evt)

    if uid is None or gid is None or eid is None:
        log.warning("Interested payload missing ids – skipping")
        return

    ensure_files(uid)

    rec: Dict[str, int] = {"guild_id": gid, "id": eid}

    idx = load_index(uid)
    if not any(r["id"] == eid and r["guild_id"] == gid for r in idx):
        idx.append(rec)
        save_index(uid, idx)
        await rebuild_calendar(uid, idx)
        log.info("Added event %s to user %s and rebuilt calendar", eid, uid)


# ---------------------------------------------------------------------------
# 2) Event UPDATED – propagate changes
# ---------------------------------------------------------------------------


@listen(GuildScheduledEventUpdate)
async def on_event_updated(evt: GuildScheduledEventUpdate):  # noqa: D401
    gid, eid = _extract_ids(evt)
    if gid is None or eid is None:
        log.warning("Event update without ids – skipping")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx: List[Dict[str, int]] = load_index(uid)
        if any(r["id"] == eid and r["guild_id"] == gid for r in idx):
            await rebuild_calendar(uid, idx)
            log.info("Rebuilt calendar for %s after update to event %s", uid, eid)


# ---------------------------------------------------------------------------
# 3) Event DELETED – remove from all calendars
# ---------------------------------------------------------------------------


@listen(GuildScheduledEventDelete)
async def on_event_deleted(evt: GuildScheduledEventDelete):  # noqa: D401
    gid, eid = _extract_ids(evt)
    if gid is None or eid is None:
        log.warning("Event delete without ids – skipping")
        return

    for idx_file in DATA_DIR.glob("*.json"):
        try:
            uid = int(idx_file.stem)
        except ValueError:
            continue

        ensure_files(uid)
        idx: List[Dict[str, int]] = load_index(uid)
        new_idx = [r for r in idx if not (r["id"] == eid and r["guild_id"] == gid)]
        if new_idx != idx:
            save_index(uid, new_idx)
            await rebuild_calendar(uid, new_idx)
            log.info(
                "Removed deleted event %s from user %s and rebuilt calendar", eid, uid
            )


# ---------------------------------------------------------------------------
# 4) Bot ready – start HTTP server & background poller
# ---------------------------------------------------------------------------


@bot.listen("ready")
async def on_ready(_: Any):  # noqa: D401
    """Kick off aiohttp server and calendar polling once the bot is online."""

    log.info("Bot is online; launching HTTP server and polling tasks.")
    asyncio.create_task(run_http())
    asyncio.create_task(poll_new_events())
