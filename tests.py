"""Tests for the boxing schedule scraper."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper import (
    Event,
    Fight,
    build_calendar,
    filter_recent,
    infer_timezone,
    parse_event,
    parse_events,
    parse_fight,
)

FIXTURE = Path(__file__).parent / "fixtures" / "events_api.json"


@pytest.fixture(scope="session")
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def events(payload: dict) -> list[Event]:
    return parse_events(payload)


# ---------------------------------------------------------------------------
# infer_timezone
# ---------------------------------------------------------------------------


class TestInferTimezone:
    def test_country_default(self) -> None:
        assert infer_timezone("JP", "Tokyo") == ZoneInfo("Asia/Tokyo")
        assert infer_timezone("GB", "London") == ZoneInfo("Europe/London")
        assert infer_timezone("UK", None) == ZoneInfo("Europe/London")
        assert infer_timezone("EG", "Giza") == ZoneInfo("Africa/Cairo")
        assert infer_timezone("KG", "Bishkek") == ZoneInfo("Asia/Bishkek")
        assert infer_timezone("ZA", "Johannesburg") == ZoneInfo("Africa/Johannesburg")

    def test_us_default(self) -> None:
        assert infer_timezone("US", None) == ZoneInfo("America/New_York")
        assert infer_timezone("US", "New York City") == ZoneInfo("America/New_York")

    def test_us_city_overrides(self) -> None:
        assert infer_timezone("US", "Las Vegas") == ZoneInfo("America/Los_Angeles")
        assert infer_timezone("US", "Chicago") == ZoneInfo("America/Chicago")
        assert infer_timezone("US", "Phoenix") == ZoneInfo("America/Phoenix")
        assert infer_timezone("US", "Denver") == ZoneInfo("America/Denver")

    def test_canada_city_override(self) -> None:
        assert infer_timezone("CA", "Vancouver") == ZoneInfo("America/Vancouver")
        # Montreal/Toronto stay on the default
        assert infer_timezone("CA", "Montreal") == ZoneInfo("America/Toronto")

    def test_russia_multi_zone(self) -> None:
        assert infer_timezone("RU", "Moscow") == ZoneInfo("Europe/Moscow")
        assert infer_timezone("RU", "Yekaterinburg") == ZoneInfo("Asia/Yekaterinburg")

    def test_fallback_logs_and_returns_ny(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            tz = infer_timezone("ZZ", "Nowhere")
        assert tz == ZoneInfo("America/New_York")
        assert any("Falling back" in r.message for r in caplog.records)

    def test_city_override_case_insensitive(self) -> None:
        assert infer_timezone("US", "LAS VEGAS") == ZoneInfo("America/Los_Angeles")
        assert infer_timezone("US", "las vegas") == ZoneInfo("America/Los_Angeles")

    def test_country_code_case_insensitive(self) -> None:
        assert infer_timezone("jp", None) == ZoneInfo("Asia/Tokyo")


# ---------------------------------------------------------------------------
# parse_fight / parse_event
# ---------------------------------------------------------------------------


class TestParseFight:
    def test_basic(self) -> None:
        raw = {
            "fighterA": {"name": "Naoya Inoue"},
            "fighterB": {"name": "Junto Nakatani"},
            "isMainEvent": True,
            "weightClass": "Junior featherweight",
            "noOfRounds": 12,
        }
        f = parse_fight(raw)
        assert f.fighter_a == "Naoya Inoue"
        assert f.fighter_b == "Junto Nakatani"
        assert f.is_main_event is True
        assert f.weight_class == "Junior featherweight"
        assert f.rounds == 12

    def test_undercard(self) -> None:
        raw = {
            "fighterA": {"name": "Foo"},
            "fighterB": {"name": "Bar"},
            "isMainEvent": False,
        }
        assert parse_fight(raw).is_main_event is False

    def test_strips_whitespace(self) -> None:
        raw = {
            "fighterA": {"name": "  Foo  "},
            "fighterB": {"name": "Bar\n"},
        }
        f = parse_fight(raw)
        assert f.fighter_a == "Foo"
        assert f.fighter_b == "Bar"


class TestParseEvent:
    def test_full_record(self) -> None:
        raw = {
            "id": "abc123",
            "eventStart": "2026-05-23T18:00:00.000Z",
            "eventEnd": "2026-05-23T22:00:00.000Z",
            "eventLocation": {
                "venueName": "Pyramids of Giza",
                "city": "Giza",
                "country": "EG",
            },
            "fights": [
                {"fighterA": {"name": "A"}, "fighterB": {"name": "B"},
                 "isMainEvent": True},
                {"fighterA": {"name": "C"}, "fighterB": {"name": "D"},
                 "isMainEvent": False},
            ],
            "isSoldOut": True,
        }
        ev = parse_event(raw)
        assert ev is not None
        assert ev.id == "abc123"
        assert ev.start_utc == datetime(2026, 5, 23, 18, 0, tzinfo=UTC)
        assert ev.end_utc == datetime(2026, 5, 23, 22, 0, tzinfo=UTC)
        assert ev.venue == "Pyramids of Giza"
        assert ev.country == "EG"
        assert len(ev.fights) == 2
        assert ev.main_event is not None and ev.main_event.fighter_a == "A"
        assert len(ev.undercards) == 1
        assert ev.is_sold_out is True

    def test_missing_start_returns_none(self) -> None:
        assert parse_event({"id": "x", "fights": []}) is None

    def test_no_named_fights_returns_none(self) -> None:
        raw = {
            "id": "x",
            "eventStart": "2026-05-23T18:00:00.000Z",
            "fights": [{"fighterA": {"name": ""}, "fighterB": {"name": ""}}],
        }
        assert parse_event(raw) is None

    def test_handles_missing_optional_fields(self) -> None:
        raw = {
            "id": "x",
            "eventStart": "2026-05-23T18:00:00.000Z",
            "fights": [{"fighterA": {"name": "A"}, "fighterB": {"name": "B"}}],
        }
        ev = parse_event(raw)
        assert ev is not None
        assert ev.venue is None
        assert ev.city is None
        assert ev.country is None
        assert ev.end_utc is None
        assert ev.is_sold_out is False

    def test_unparsable_start_returns_none(self) -> None:
        raw = {
            "id": "x",
            "eventStart": "not a date",
            "fights": [{"fighterA": {"name": "A"}, "fighterB": {"name": "B"}}],
        }
        assert parse_event(raw) is None

    def test_event_with_no_main_flag_takes_first_fight_as_main(self) -> None:
        raw = {
            "id": "x",
            "eventStart": "2026-05-23T18:00:00.000Z",
            "fights": [
                {"fighterA": {"name": "A"}, "fighterB": {"name": "B"},
                 "isMainEvent": False},
                {"fighterA": {"name": "C"}, "fighterB": {"name": "D"},
                 "isMainEvent": False},
            ],
        }
        ev = parse_event(raw)
        assert ev is not None
        assert ev.main_event is not None
        assert ev.main_event.fighter_a == "A"


# ---------------------------------------------------------------------------
# Fixture-driven integration tests
# ---------------------------------------------------------------------------


class TestFixture:
    def test_parses_fixture(self, events: list[Event]) -> None:
        assert len(events) > 0

    def test_every_event_has_a_main(self, events: list[Event]) -> None:
        for ev in events:
            assert ev.main_event is not None, f"event {ev.id} has no main"

    def test_every_event_has_aware_utc_start(self, events: list[Event]) -> None:
        for ev in events:
            assert ev.start_utc.tzinfo is not None
            assert ev.start_utc.utcoffset() == timedelta(0)

    def test_known_event_usyk_verhoeven(self, events: list[Event]) -> None:
        match = [
            ev for ev in events
            if ev.main_event is not None
            and "Usyk" in ev.main_event.fighter_a
            and "Verhoeven" in ev.main_event.fighter_b
        ]
        assert len(match) == 1
        ev = match[0]
        assert ev.country == "EG"
        assert ev.venue == "Pyramids of Giza"
        assert ev.timezone == ZoneInfo("Africa/Cairo")

    def test_known_event_inoue_tokyo_dome(self, events: list[Event]) -> None:
        match = [ev for ev in events if ev.venue == "Tokyo Dome"]
        assert len(match) == 1
        ev = match[0]
        assert ev.country == "JP"
        assert ev.timezone == ZoneInfo("Asia/Tokyo")
        # Tokyo Dome card has multiple undercards
        assert len(ev.undercards) >= 3

    def test_timezones_resolved_for_every_event(self, events: list[Event]) -> None:
        # Sanity: nothing should hit the fallback for known fixture
        for ev in events:
            assert ev.timezone is not None

    def test_local_start_round_trips(self, events: list[Event]) -> None:
        # Local start should equal UTC start when both are converted back
        for ev in events:
            assert ev.local_start.astimezone(UTC) == ev.start_utc


# ---------------------------------------------------------------------------
# filter_recent
# ---------------------------------------------------------------------------


def _make_event(start: datetime, eid: str = "x") -> Event:
    return Event(
        id=eid,
        start_utc=start,
        end_utc=None,
        venue=None,
        city=None,
        country="US",
        fights=(Fight(fighter_a="A", fighter_b="B", is_main_event=True),),
        is_sold_out=False,
    )


class TestFilterRecent:
    def test_keeps_future(self) -> None:
        now = datetime(2026, 5, 14, tzinfo=UTC)
        future = _make_event(now + timedelta(days=10))
        assert filter_recent([future], now_utc=now) == [future]

    def test_keeps_recent_past(self) -> None:
        now = datetime(2026, 5, 14, tzinfo=UTC)
        recent = _make_event(now - timedelta(days=3))
        assert filter_recent([recent], now_utc=now) == [recent]

    def test_drops_old_past(self) -> None:
        now = datetime(2026, 5, 14, tzinfo=UTC)
        old = _make_event(now - timedelta(days=30))
        assert filter_recent([old], now_utc=now) == []

    def test_cutoff_boundary_inclusive(self) -> None:
        now = datetime(2026, 5, 14, tzinfo=UTC)
        # exactly at cutoff -> kept
        edge = _make_event(now - timedelta(days=7))
        assert filter_recent([edge], now_utc=now) == [edge]


# ---------------------------------------------------------------------------
# Calendar rendering
# ---------------------------------------------------------------------------


class TestBuildCalendar:
    def test_basic_calendar(self, events: list[Event]) -> None:
        cal = build_calendar(events[:1])
        text = cal.to_ical().decode("utf-8")
        assert "BEGIN:VCALENDAR" in text
        assert "END:VCALENDAR" in text
        assert "BEGIN:VEVENT" in text
        assert "DTSTAMP:" in text
        assert "PRODID:" in text
        assert "VERSION:2.0" in text

    def test_event_uid_is_stable(self, events: list[Event]) -> None:
        ev = events[0]
        cal1 = build_calendar([ev])
        cal2 = build_calendar([ev])
        # UIDs match across calls
        uids1 = [c["UID"] for c in cal1.walk("VEVENT")]
        uids2 = [c["UID"] for c in cal2.walk("VEVENT")]
        assert uids1 == uids2
        assert str(uids1[0]).startswith("boxing-")

    def test_summary_has_emoji_and_main_event(self, events: list[Event]) -> None:
        ev = next(
            e for e in events
            if e.main_event is not None and "Usyk" in e.main_event.fighter_a
        )
        cal = build_calendar([ev])
        ical_event = next(iter(cal.walk("VEVENT")))
        summary = str(ical_event["SUMMARY"])
        assert "USYK" in summary.upper()
        assert "VERHOEVEN" in summary.upper()
        if ev.undercards:
            assert f"+{len(ev.undercards)} more" in summary

    def test_description_mentions_venue(self, events: list[Event]) -> None:
        ev = next(e for e in events if e.venue == "Tokyo Dome")
        cal = build_calendar([ev])
        ical_event = next(iter(cal.walk("VEVENT")))
        desc = str(ical_event["DESCRIPTION"])
        assert "Tokyo Dome" in desc
        assert "MAIN EVENT" in desc

    def test_dtstart_in_local_timezone(self, events: list[Event]) -> None:
        ev = next(e for e in events if e.venue == "Tokyo Dome")
        cal = build_calendar([ev])
        ical_event = next(iter(cal.walk("VEVENT")))
        dtstart = ical_event["DTSTART"].dt
        # Should be a timezone-aware datetime
        assert dtstart.tzinfo is not None
        # And should equal the UTC start
        assert dtstart.astimezone(UTC) == ev.start_utc

    def test_dtend_defaults_to_four_hours(self) -> None:
        start = datetime(2026, 5, 23, 18, 0, tzinfo=UTC)
        ev = Event(
            id="abc",
            start_utc=start,
            end_utc=None,
            venue="V",
            city="C",
            country="US",
            fights=(Fight("A", "B", is_main_event=True),),
            is_sold_out=False,
        )
        cal = build_calendar([ev])
        ical_event = next(iter(cal.walk("VEVENT")))
        dtstart = ical_event["DTSTART"].dt
        dtend = ical_event["DTEND"].dt
        assert dtend - dtstart == timedelta(hours=4)

    def test_rfc5545_required_fields(self, events: list[Event]) -> None:
        cal = build_calendar(events[:3])
        for component in cal.walk("VEVENT"):
            assert component["UID"]
            assert component["SUMMARY"]
            assert component["DTSTART"]
            assert component["DTEND"]
            assert component["DTSTAMP"]
