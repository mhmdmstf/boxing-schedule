"""Unit tests for boxing schedule scraper."""

from datetime import datetime, timedelta

import pytest

from scraper import (
    Card,
    Fight,
    _is_location_line,
    _names_match,
    build_cards,
    create_calendar,
    fighters_match,
    filter_past_events,
    infer_timezone,
    normalize_name,
    parse_date,
    parse_time,
)


# ---------------------------------------------------------------------------
# Name Matching
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("  Erika  Cruz  ") == "erika cruz"

    def test_suffix_jr(self):
        assert normalize_name("Floyd Mayweather Jr.") == "floyd mayweather"

    def test_suffix_iii(self):
        assert normalize_name("Sugar Ray Leonard III") == "sugar ray leonard"

    def test_case(self):
        assert normalize_name("CANELO ALVAREZ") == "canelo alvarez"


class TestNamesMatch:
    def test_exact(self):
        assert _names_match("erika cruz", "erika cruz")

    def test_last_name_only(self):
        assert _names_match("cruz", "erika cruz")

    def test_different_first_names(self):
        assert not _names_match("isaac cruz", "erika cruz")

    def test_similar_first_names(self):
        # "eri" prefix matches — handles "E. Cruz" vs "Erika Cruz"
        assert _names_match("eri cruz", "erika cruz")

    def test_completely_different(self):
        assert not _names_match("canelo alvarez", "floyd mayweather")

    def test_empty(self):
        assert not _names_match("", "erika cruz")


class TestFightersMatch:
    def test_exact_match(self):
        f1 = Fight("Erika Cruz", "Amanda Serrano")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert fighters_match(f1, f2)

    def test_case_insensitive(self):
        f1 = Fight("ERIKA CRUZ", "AMANDA SERRANO")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert fighters_match(f1, f2)

    def test_partial_name_same_bout(self):
        f1 = Fight("Cruz", "Serrano")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert fighters_match(f1, f2)

    def test_different_fighters_same_last_name(self):
        """Isaac Cruz and Erika Cruz are different fighters."""
        f1 = Fight("Isaac Cruz", "Lamont Roach")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert not fighters_match(f1, f2)

    def test_reversed_order(self):
        f1 = Fight("Cruz", "Serrano")
        f2 = Fight("Amanda Serrano", "Erika Cruz")
        assert fighters_match(f1, f2)

    def test_no_false_positive_common_name(self):
        """Two different fights shouldn't match just because one fighter shares a last name."""
        f1 = Fight("Andy Cruz", "Someone Else")
        f2 = Fight("Isaac Cruz", "Lamont Roach")
        assert not fighters_match(f1, f2)


# ---------------------------------------------------------------------------
# Date Parsing
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_short_format(self):
        dt = parse_date("Dec 7 2025")
        assert dt is not None
        assert dt.month == 12 and dt.day == 7 and dt.year == 2025

    def test_with_day_prefix(self):
        dt = parse_date("Sat, Dec 7 2025")
        assert dt is not None
        assert dt.month == 12 and dt.day == 7

    def test_long_format(self):
        dt = parse_date("Saturday, December 7, 2025")
        assert dt is not None
        assert dt.month == 12 and dt.day == 7

    def test_long_no_comma(self):
        dt = parse_date("December 7 2025")
        assert dt is not None
        assert dt.month == 12

    def test_tbd(self):
        assert parse_date("TBD") is None

    def test_empty(self):
        assert parse_date("") is None

    def test_garbage(self):
        assert parse_date("not a date at all") is None


# ---------------------------------------------------------------------------
# Time Parsing
# ---------------------------------------------------------------------------


class TestParseTime:
    def test_pm(self):
        assert parse_time("8:00 PM") == (20, 0)

    def test_am(self):
        assert parse_time("2:00 AM") == (2, 0)

    def test_noon(self):
        assert parse_time("12:00 PM") == (12, 0)

    def test_midnight(self):
        assert parse_time("12:00 AM") == (0, 0)

    def test_gmt(self):
        assert parse_time("18:00 GMT") == (18, 0)

    def test_empty(self):
        assert parse_time("") == (20, 0)

    def test_garbage(self):
        assert parse_time("not a time") == (20, 0)


# ---------------------------------------------------------------------------
# Timezone Inference
# ---------------------------------------------------------------------------


class TestInferTimezone:
    def test_gmt_time(self):
        assert infer_timezone("6:00 GMT", "") == "Europe/London"

    def test_uk_location(self):
        assert infer_timezone("6:00 PM", "O2 Arena, London, GB") == "Europe/London"

    def test_au_location(self):
        assert infer_timezone("", "ICC Sydney Theatre, Sydney, AU") == "Australia/Sydney"

    def test_japan(self):
        assert infer_timezone("", "Toyota Arena, Tokyo, JP") == "Asia/Tokyo"

    def test_us_west_coast(self):
        assert infer_timezone("", "MGM Grand, Las Vegas, US") == "America/Los_Angeles"

    def test_us_central(self):
        assert infer_timezone("", "Frost Bank Center, San Antonio, US") == "America/Chicago"

    def test_us_default(self):
        assert infer_timezone("8:00 PM", "Barclays Center, New York, US") == "America/New_York"

    def test_saudi(self):
        assert infer_timezone("", "Kingdom Arena, Riyadh, SA") == "Asia/Riyadh"

    def test_puerto_rico(self):
        assert infer_timezone("", "Coliseo, San Juan, PR") == "America/Puerto_Rico"

    def test_canada(self):
        assert infer_timezone("", "Lac Leamy Casino, Gatineau, CA") == "America/Toronto"


# ---------------------------------------------------------------------------
# Location Detection
# ---------------------------------------------------------------------------


class TestIsLocationLine:
    def test_valid_venue(self):
        assert _is_location_line("Frost Bank Center, San Antonio, US")

    def test_article_headline(self):
        """Article headlines with commas should be rejected."""
        assert not _is_location_line(
            "Shabaz Masoud-Peter McGrail Tops Matchroom's Monte-Carlo Show, Dec. 6"
        )

    def test_too_short(self):
        assert not _is_location_line("Hi, US")

    def test_no_comma(self):
        assert not _is_location_line("Madison Square Garden New York")

    def test_date_line(self):
        assert not _is_location_line("Sat, Dec 7 2025")

    def test_results_article(self):
        assert not _is_location_line("Fight Results, Highlights and Analysis")


# ---------------------------------------------------------------------------
# Past Event Filtering
# ---------------------------------------------------------------------------


class TestFilterPastEvents:
    def test_removes_old_events(self):
        old = Card(date=datetime.now() - timedelta(days=30), date_raw="old")
        old.fights = [Fight("A", "B")]
        future = Card(date=datetime.now() + timedelta(days=30), date_raw="future")
        future.fights = [Fight("C", "D")]
        result = filter_past_events([old, future])
        assert len(result) == 1
        assert result[0].date_raw == "future"

    def test_keeps_recent(self):
        recent = Card(date=datetime.now() - timedelta(days=3), date_raw="recent")
        recent.fights = [Fight("A", "B")]
        result = filter_past_events([recent])
        assert len(result) == 1

    def test_keeps_tbd(self):
        tbd = Card(date=None, date_raw="TBD")
        tbd.fights = [Fight("A", "B")]
        result = filter_past_events([tbd])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Card Building
# ---------------------------------------------------------------------------


class TestBuildCards:
    def test_groups_by_date_location(self):
        fights = [
            {"fighter1": "A", "fighter2": "B", "date_raw": "Dec 7 2025",
             "location": "Arena, City, US", "time": "", "broadcast": "",
             "is_main_event": True, "source": "main_page"},
            {"fighter1": "C", "fighter2": "D", "date_raw": "Dec 7 2025",
             "location": "Arena, City, US", "time": "", "broadcast": "",
             "is_main_event": False, "source": "main_page"},
        ]
        cards = build_cards(fights)
        assert len(cards) == 1
        assert len(cards[0].fights) == 2

    def test_separates_different_dates(self):
        fights = [
            {"fighter1": "A", "fighter2": "B", "date_raw": "Dec 7 2025",
             "location": "Arena, City, US", "time": "", "broadcast": "",
             "is_main_event": True, "source": "main_page"},
            {"fighter1": "C", "fighter2": "D", "date_raw": "Dec 14 2025",
             "location": "Arena, City, US", "time": "", "broadcast": "",
             "is_main_event": True, "source": "main_page"},
        ]
        cards = build_cards(fights)
        assert len(cards) == 2

    def test_deduplicates_within_card(self):
        fights = [
            {"fighter1": "ERIKA CRUZ", "fighter2": "AMANDA SERRANO",
             "date_raw": "Dec 7 2025", "location": "Arena, City, US",
             "time": "", "broadcast": "", "is_main_event": True, "source": "main_page"},
            {"fighter1": "Erika Cruz", "fighter2": "Amanda Serrano",
             "date_raw": "Dec 7 2025", "location": "Arena, City, US",
             "time": "", "broadcast": "", "is_main_event": False, "source": "detail_page"},
        ]
        cards = build_cards(fights)
        assert len(cards) == 1
        assert len(cards[0].fights) == 1


# ---------------------------------------------------------------------------
# Calendar Generation
# ---------------------------------------------------------------------------


class TestCreateCalendar:
    def test_creates_valid_ics(self):
        card = Card(
            date=datetime(2025, 12, 7),
            date_raw="Dec 7 2025",
            location="Test Arena, Test, US",
            time_raw="8:00 PM",
            broadcast="LIVE ON TEST",
        )
        card.fights = [
            Fight("Fighter A", "Fighter B", is_main_event=True),
            Fight("Fighter C", "Fighter D"),
        ]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "BEGIN:VCALENDAR" in ics
        assert "FIGHTER A VS FIGHTER B" in ics
        assert "(+1 more)" in ics

    def test_skips_no_date(self):
        card = Card(date=None, date_raw="TBD", location="Somewhere")
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "VEVENT" not in ics

    def test_includes_location(self):
        card = Card(
            date=datetime(2025, 12, 7),
            date_raw="Dec 7 2025",
            location="Madison Square Garden, New York, US",
        )
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "Madison Square Garden" in ics

    def test_has_timezone(self):
        card = Card(
            date=datetime(2025, 12, 7),
            date_raw="Dec 7 2025",
            location="O2 Arena, London, GB",
            timezone="Europe/London",
        )
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "TZID" in ics or "VTIMEZONE" in ics or "Europe/London" in ics


# ---------------------------------------------------------------------------
# Card Model
# ---------------------------------------------------------------------------


class TestCard:
    def test_main_event_property(self):
        card = Card()
        card.fights = [
            Fight("A", "B", is_main_event=False),
            Fight("C", "D", is_main_event=True),
        ]
        assert card.main_event.fighter1 == "C"

    def test_main_event_fallback(self):
        card = Card()
        card.fights = [Fight("A", "B"), Fight("C", "D")]
        assert card.main_event.fighter1 == "A"

    def test_undercards(self):
        card = Card()
        card.fights = [
            Fight("Main1", "Main2", is_main_event=True),
            Fight("UC1", "UC2"),
            Fight("UC3", "UC4"),
        ]
        assert len(card.undercards) == 2

    def test_add_fight_dedup(self):
        card = Card()
        card.add_fight(Fight("ERIKA CRUZ", "AMANDA SERRANO"))
        added = card.add_fight(Fight("Erika Cruz", "Amanda Serrano"))
        assert not added
        assert len(card.fights) == 1
