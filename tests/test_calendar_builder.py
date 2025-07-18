# tests/test_calendar_builder.py – ensure import paths work on local runner
"""Pytest unit-tests for calendar feed helpers.
Run with: pytest -q
"""
import sys
from pathlib import Path

# Add project root to sys.path so `import calendar_builder` succeeds when the
# tests are run from the project directory without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import datetime as dt
from types import SimpleNamespace

import pytest

from calendar_builder import event_to_ics
from file_helpers import feed_url, ensure_files, idx_path, ics_path
from config import DATA_DIR, BASE_URL, TIMEZONE

"""Pytest unit-tests for calendar feed helpers.
Run with:  pytest -q
"""
import datetime as dt
from types import SimpleNamespace
from pathlib import Path

import pytest

from calendar_builder import event_to_ics
from file_helpers import feed_url, ensure_files, idx_path, ics_path
from config import DATA_DIR, BASE_URL, TIMEZONE


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------
class FakeMeta(SimpleNamespace):
    """Mimic discord.EntityMetadata with arbitrary attributes."""


class FakeEvent(SimpleNamespace):
    """Mimic a discord.ScheduledEvent object with minimal fields."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.start_time = kwargs.get(
            "start_time",
            dt.datetime.now(tz=TIMEZONE).replace(minute=0, second=0, microsecond=0),
        )
        self.end_time = kwargs.get("end_time", self.start_time + dt.timedelta(hours=1))
        self.description = kwargs.get("description", "")
        self.recurrence = kwargs.get("recurrence", None)
        self.entity_metadata = kwargs.get("entity_metadata", None)
        self.id = kwargs.get("id", 1)
        self.guild_id = kwargs.get("guild_id", 1)


# ---------------------------------------------------------------------------
# feed_url
# ---------------------------------------------------------------------------


def test_feed_url_scheme():
    url = feed_url(123456)
    assert url.startswith("webcal://")
    assert str(123456) in url
    assert BASE_URL.split("//", 1)[-1] in url


# ---------------------------------------------------------------------------
# ensure_files
# ---------------------------------------------------------------------------


def test_ensure_files(tmp_path, monkeypatch):
    monkeypatch.setattr("config.DATA_DIR", tmp_path, raising=False)
    uid = 42
    ensure_files(uid)
    assert idx_path(uid).exists()
    assert ics_path(uid).exists()


# ---------------------------------------------------------------------------
# event_to_ics: location handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "loc,expect_geo",
    [
        ("40.6892,-74.0445", True),  # coordinates
        ("221B Baker St, London", False),  # address
    ],
)
def test_event_to_ics_location(loc, expect_geo):
    meta = FakeMeta(location=loc)
    ev = FakeEvent(name="Loc test", entity_metadata=meta)
    ics_event = event_to_ics(ev, guild_id=1)
    assert ics_event.location == loc
    geo_props = [val for key, val in ics_event.extra if key == "GEO"]
    if expect_geo:
        assert geo_props, "Expected GEO parameter"  # should not be empty
    else:
        assert not geo_props, "Unexpected GEO parameter present"


# ---------------------------------------------------------------------------
# event_to_ics: recurrence handling
# ---------------------------------------------------------------------------


def test_event_to_ics_rrule():
    rule = "FREQ=WEEKLY;BYDAY=MO,WE,FR"
    ev = FakeEvent(name="Repeat", recurrence=[rule])
    ics_event = event_to_ics(ev, guild_id=1)
    rrule_props = [v for k, v in ics_event.extra if k == "RRULE"]
    assert rule in rrule_props
