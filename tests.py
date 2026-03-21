"""Unit tests for boxing schedule scraper."""

from datetime import datetime, timedelta

import pytest

from scraper import (
    Card,
    Fight,
    RawFight,
    _is_location_line,
    _is_valid_fighter,
    _names_match,
    _normalize_location_key,
    build_cards,
    create_calendar,
    fighters_match,
    filter_past_events,
    infer_timezone,
    normalize_name,
    parse_date,
    parse_fight_detail_text,
    parse_main_page_text,
    parse_time,
)

# ---------------------------------------------------------------------------
# Name Matching
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_basic(self) -> None:
        assert normalize_name("  Erika  Cruz  ") == "erika cruz"

    def test_suffix_jr(self) -> None:
        assert normalize_name("Floyd Mayweather Jr.") == "floyd mayweather"

    def test_suffix_iii(self) -> None:
        assert normalize_name("Sugar Ray Leonard III") == "sugar ray leonard"

    def test_case(self) -> None:
        assert normalize_name("CANELO ALVAREZ") == "canelo alvarez"


class TestNamesMatch:
    def test_exact(self) -> None:
        assert _names_match("erika cruz", "erika cruz")

    def test_last_name_only(self) -> None:
        assert _names_match("cruz", "erika cruz")

    def test_different_first_names(self) -> None:
        assert not _names_match("isaac cruz", "erika cruz")

    def test_similar_first_names(self) -> None:
        # "eri" prefix matches — handles "E. Cruz" vs "Erika Cruz"
        assert _names_match("eri cruz", "erika cruz")

    def test_completely_different(self) -> None:
        assert not _names_match("canelo alvarez", "floyd mayweather")

    def test_empty(self) -> None:
        assert not _names_match("", "erika cruz")

    def test_hyphenated_last_name(self) -> None:
        assert _names_match("oscar de la hoya", "oscar de la hoya")

    def test_hyphenated_different_first(self) -> None:
        assert not _names_match("juan de la hoya", "oscar de la hoya")


class TestFightersMatch:
    def test_exact_match(self) -> None:
        f1 = Fight("Erika Cruz", "Amanda Serrano")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert fighters_match(f1, f2)

    def test_case_insensitive(self) -> None:
        f1 = Fight("ERIKA CRUZ", "AMANDA SERRANO")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert fighters_match(f1, f2)

    def test_partial_name_same_bout(self) -> None:
        f1 = Fight("Cruz", "Serrano")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert fighters_match(f1, f2)

    def test_different_fighters_same_last_name(self) -> None:
        """Isaac Cruz and Erika Cruz are different fighters."""
        f1 = Fight("Isaac Cruz", "Lamont Roach")
        f2 = Fight("Erika Cruz", "Amanda Serrano")
        assert not fighters_match(f1, f2)

    def test_reversed_order(self) -> None:
        f1 = Fight("Cruz", "Serrano")
        f2 = Fight("Amanda Serrano", "Erika Cruz")
        assert fighters_match(f1, f2)

    def test_no_false_positive_common_name(self) -> None:
        """Two different fights shouldn't match just because one fighter shares a last name."""
        f1 = Fight("Andy Cruz", "Someone Else")
        f2 = Fight("Isaac Cruz", "Lamont Roach")
        assert not fighters_match(f1, f2)


# ---------------------------------------------------------------------------
# Date Parsing
# ---------------------------------------------------------------------------


class TestParseDate:
    @pytest.mark.parametrize(
        "input_str, expected_month, expected_day, expected_year",
        [
            ("Dec 7 2025", 12, 7, 2025),
            ("Sat, Dec 7 2025", 12, 7, 2025),
            ("Saturday, December 7, 2025", 12, 7, 2025),
            ("December 7 2025", 12, 7, 2025),
            ("7 December 2025", 12, 7, 2025),
            ("7 Dec 2025", 12, 7, 2025),
        ],
    )
    def test_valid_dates(
        self, input_str: str, expected_month: int, expected_day: int, expected_year: int
    ) -> None:
        dt = parse_date(input_str)
        assert dt is not None
        assert (dt.month, dt.day, dt.year) == (expected_month, expected_day, expected_year)

    @pytest.mark.parametrize("input_str", ["TBD", "", "not a date at all"])
    def test_invalid_dates(self, input_str: str) -> None:
        assert parse_date(input_str) is None


# ---------------------------------------------------------------------------
# Time Parsing
# ---------------------------------------------------------------------------


class TestParseTime:
    @pytest.mark.parametrize(
        "input_str, expected",
        [
            ("8:00 PM", (20, 0)),
            ("2:00 AM", (2, 0)),
            ("12:00 PM", (12, 0)),
            ("12:00 AM", (0, 0)),
            ("18:00 GMT", (18, 0)),
            ("", (20, 0)),
            ("not a time", (20, 0)),
            ("9:30 PM", (21, 30)),
            ("6:00 AM", (6, 0)),
        ],
    )
    def test_parse_time(self, input_str: str, expected: tuple[int, int]) -> None:
        assert parse_time(input_str) == expected


# ---------------------------------------------------------------------------
# Timezone Inference
# ---------------------------------------------------------------------------


class TestInferTimezone:
    @pytest.mark.parametrize(
        "time_str, location, expected_tz",
        [
            ("6:00 GMT", "", "Europe/London"),
            ("6:00 PM", "O2 Arena, London, GB", "Europe/London"),
            ("", "ICC Sydney Theatre, Sydney, AU", "Australia/Sydney"),
            ("", "Toyota Arena, Tokyo, JP", "Asia/Tokyo"),
            ("", "MGM Grand, Las Vegas, US", "America/Los_Angeles"),
            ("", "Frost Bank Center, San Antonio, US", "America/Chicago"),
            ("8:00 PM", "Barclays Center, New York, US", "America/New_York"),
            ("", "Kingdom Arena, Riyadh, SA", "Asia/Riyadh"),
            ("", "Coliseo, San Juan, PR", "America/Puerto_Rico"),
            ("", "Lac Leamy Casino, Gatineau, CA", "America/Toronto"),
            # New expanded timezone tests
            ("", "Wells Fargo Center, Philadelphia, US", "America/New_York"),
            ("", "Boardwalk Hall, Atlantic City, US", "America/New_York"),
            ("", "Pepsi Center, Denver, US", "America/Denver"),
            ("", "Arena CDMX, Mexico City, MX", "America/Mexico_City"),
            ("", "Palais des Sports, Paris, FR", "Europe/Paris"),
            ("", "Foro Sol, Madrid, ES", "Europe/Madrid"),
            ("", "Impact Arena, Bangkok, TH", "Asia/Bangkok"),
            ("", "Estadio Luna Park, Buenos Aires, AR", "America/Argentina/Buenos_Aires"),
        ],
    )
    def test_infer_timezone(
        self, time_str: str, location: str, expected_tz: str
    ) -> None:
        assert infer_timezone(time_str, location) == expected_tz


# ---------------------------------------------------------------------------
# Location Detection
# ---------------------------------------------------------------------------


class TestIsLocationLine:
    def test_valid_venue(self) -> None:
        assert _is_location_line("Frost Bank Center, San Antonio, US")

    def test_article_headline(self) -> None:
        """Article headlines with commas should be rejected."""
        assert not _is_location_line(
            "Shabaz Masoud-Peter McGrail Tops Matchroom's Monte-Carlo Show, Dec. 6"
        )

    def test_too_short(self) -> None:
        assert not _is_location_line("Hi, US")

    def test_no_comma(self) -> None:
        assert not _is_location_line("Madison Square Garden New York")

    def test_date_line(self) -> None:
        assert not _is_location_line("Sat, Dec 7 2025")

    def test_results_article(self) -> None:
        assert not _is_location_line("Fight Results, Highlights and Analysis")

    def test_venue_keyword_resort(self) -> None:
        assert _is_location_line("Wynn Resort, Las Vegas, US")

    def test_venue_keyword_field(self) -> None:
        assert _is_location_line("SoFi Stadium Field, Inglewood, US")


# ---------------------------------------------------------------------------
# Fighter Validation
# ---------------------------------------------------------------------------


class TestIsValidFighter:
    def test_valid_name(self) -> None:
        assert _is_valid_fighter("Canelo Alvarez")

    def test_too_short(self) -> None:
        assert not _is_valid_fighter("AB")

    def test_champion_tag(self) -> None:
        assert not _is_valid_fighter("WBA CHAMPION")

    def test_schedule_text(self) -> None:
        assert not _is_valid_fighter("BOXING SCHEDULE 2025")

    def test_live_prefix(self) -> None:
        assert not _is_valid_fighter("LIVE ON DAZN")

    def test_url(self) -> None:
        assert not _is_valid_fighter("https://ringmagazine.com/fight")

    def test_too_long(self) -> None:
        assert not _is_valid_fighter("A" * 61)

    def test_digit_only(self) -> None:
        assert not _is_valid_fighter("12345")


# ---------------------------------------------------------------------------
# Location Key Normalization
# ---------------------------------------------------------------------------


class TestNormalizeLocationKey:
    def test_basic(self) -> None:
        assert _normalize_location_key("Arena, City, US") == "arena, city"

    def test_double_suffix(self) -> None:
        """Should strip state + country suffix."""
        result = _normalize_location_key("T-Mobile Arena, Las Vegas, NV, US")
        assert result == "t-mobile arena, las vegas"

    def test_no_suffix(self) -> None:
        result = _normalize_location_key("Madison Square Garden, New York")
        assert result == "madison square garden, new york"

    def test_whitespace_normalization(self) -> None:
        result = _normalize_location_key("  Some   Arena,  City,  US  ")
        assert "  " not in result


# ---------------------------------------------------------------------------
# Past Event Filtering
# ---------------------------------------------------------------------------


class TestFilterPastEvents:
    def test_removes_old_events(self) -> None:
        old = Card(date=datetime.now() - timedelta(days=30), date_raw="old")
        old.fights = [Fight("A", "B")]
        future = Card(date=datetime.now() + timedelta(days=30), date_raw="future")
        future.fights = [Fight("C", "D")]
        result = filter_past_events([old, future])
        assert len(result) == 1
        assert result[0].date_raw == "future"

    def test_keeps_recent(self) -> None:
        recent = Card(date=datetime.now() - timedelta(days=3), date_raw="recent")
        recent.fights = [Fight("A", "B")]
        result = filter_past_events([recent])
        assert len(result) == 1

    def test_keeps_tbd(self) -> None:
        tbd = Card(date=None, date_raw="TBD")
        tbd.fights = [Fight("A", "B")]
        result = filter_past_events([tbd])
        assert len(result) == 1

    def test_exact_boundary(self) -> None:
        """Event exactly at cutoff should be kept."""
        boundary = Card(date=datetime.now() - timedelta(days=7), date_raw="boundary")
        boundary.fights = [Fight("A", "B")]
        result = filter_past_events([boundary])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Card Building
# ---------------------------------------------------------------------------


class TestBuildCards:
    def test_groups_by_date_location(self) -> None:
        fights = [
            RawFight("A", "B", date_raw="Dec 7 2025", location="Arena, City, US",
                     is_main_event=True, source="main_page"),
            RawFight("C", "D", date_raw="Dec 7 2025", location="Arena, City, US",
                     source="main_page"),
        ]
        cards = build_cards(fights)
        assert len(cards) == 1
        assert len(cards[0].fights) == 2

    def test_separates_different_dates(self) -> None:
        fights = [
            RawFight("A", "B", date_raw="Dec 7 2025", location="Arena, City, US",
                     is_main_event=True, source="main_page"),
            RawFight("C", "D", date_raw="Dec 14 2025", location="Arena, City, US",
                     is_main_event=True, source="main_page"),
        ]
        cards = build_cards(fights)
        assert len(cards) == 2

    def test_deduplicates_within_card(self) -> None:
        fights = [
            RawFight("ERIKA CRUZ", "AMANDA SERRANO", date_raw="Dec 7 2025",
                     location="Arena, City, US", is_main_event=True, source="main_page"),
            RawFight("Erika Cruz", "Amanda Serrano", date_raw="Dec 7 2025",
                     location="Arena, City, US", source="detail_page"),
        ]
        cards = build_cards(fights)
        assert len(cards) == 1
        assert len(cards[0].fights) == 1

    def test_tbd_dates_grouped_separately(self) -> None:
        fights = [
            RawFight("A", "B", date_raw="TBD", location="Arena, City, US",
                     is_main_event=True, source="main_page"),
            RawFight("C", "D", date_raw="Dec 7 2025", location="Arena, City, US",
                     is_main_event=True, source="main_page"),
        ]
        cards = build_cards(fights)
        assert len(cards) == 2


# ---------------------------------------------------------------------------
# Calendar Generation
# ---------------------------------------------------------------------------


class TestCreateCalendar:
    def test_creates_valid_ics(self) -> None:
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

    def test_skips_no_date(self) -> None:
        card = Card(date=None, date_raw="TBD", location="Somewhere")
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "VEVENT" not in ics

    def test_includes_location(self) -> None:
        card = Card(
            date=datetime(2025, 12, 7),
            date_raw="Dec 7 2025",
            location="Madison Square Garden, New York, US",
        )
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "Madison Square Garden" in ics

    def test_has_timezone(self) -> None:
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

    def test_has_dtstamp(self) -> None:
        card = Card(date=datetime(2025, 12, 7), date_raw="Dec 7 2025")
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "DTSTAMP" in ics

    def test_has_status(self) -> None:
        card = Card(date=datetime(2025, 12, 7), date_raw="Dec 7 2025")
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "CONFIRMED" in ics

    def test_has_calscale(self) -> None:
        card = Card(date=datetime(2025, 12, 7), date_raw="Dec 7 2025")
        card.fights = [Fight("A", "B", is_main_event=True)]
        cal = create_calendar([card])
        ics = cal.to_ical().decode()
        assert "CALSCALE:GREGORIAN" in ics

    def test_uid_uniqueness(self) -> None:
        """Different fights on the same date should have different UIDs."""
        card1 = Card(date=datetime(2025, 12, 7), date_raw="Dec 7 2025")
        card1.fights = [Fight("Fighter A", "Fighter B", is_main_event=True)]
        card2 = Card(date=datetime(2025, 12, 7), date_raw="Dec 7 2025")
        card2.fights = [Fight("Fighter C", "Fighter D", is_main_event=True)]
        cal = create_calendar([card1, card2])
        ics = cal.to_ical().decode()
        uids = [line for line in ics.split("\n") if line.startswith("UID:")]
        assert len(uids) == 2
        assert uids[0] != uids[1]


# ---------------------------------------------------------------------------
# Card Model
# ---------------------------------------------------------------------------


class TestCard:
    def test_main_event_property(self) -> None:
        card = Card()
        card.fights = [
            Fight("A", "B", is_main_event=False),
            Fight("C", "D", is_main_event=True),
        ]
        assert card.main_event is not None
        assert card.main_event.fighter1 == "C"

    def test_main_event_fallback(self) -> None:
        card = Card()
        card.fights = [Fight("A", "B"), Fight("C", "D")]
        assert card.main_event is not None
        assert card.main_event.fighter1 == "A"

    def test_undercards(self) -> None:
        card = Card()
        card.fights = [
            Fight("Main1", "Main2", is_main_event=True),
            Fight("UC1", "UC2"),
            Fight("UC3", "UC4"),
        ]
        assert len(card.undercards) == 2

    def test_add_fight_dedup(self) -> None:
        card = Card()
        card.add_fight(Fight("ERIKA CRUZ", "AMANDA SERRANO"))
        added = card.add_fight(Fight("Erika Cruz", "Amanda Serrano"))
        assert not added
        assert len(card.fights) == 1


# ---------------------------------------------------------------------------
# RawFight Model
# ---------------------------------------------------------------------------


class TestRawFight:
    def test_as_fight(self) -> None:
        raw = RawFight("Canelo", "Benavidez", is_main_event=True, source="main_page")
        fight = raw.as_fight()
        assert fight.fighter1 == "Canelo"
        assert fight.fighter2 == "Benavidez"
        assert fight.is_main_event is True
        assert fight.source == "main_page"

    def test_default_values(self) -> None:
        raw = RawFight("A", "B")
        assert raw.date_raw == "TBD"
        assert raw.location == ""
        assert raw.time == ""
        assert raw.broadcast == ""
        assert raw.is_main_event is False
        assert raw.source == ""


# ---------------------------------------------------------------------------
# Main Page Text Parsing (integration tests)
# ---------------------------------------------------------------------------


class TestParseMainPageText:
    def test_basic_main_event(self) -> None:
        lines = [
            "Sat, Mar 15 2025",
            "8:00 PM EST",
            "LIVE ON DAZN",
            "CANELO ALVAREZ",
            "VS",
            "DAVID BENAVIDEZ",
            "T-Mobile Arena, Las Vegas, US",
        ]
        fights = parse_main_page_text(lines)
        assert len(fights) == 1
        assert fights[0].fighter1 == "CANELO ALVAREZ"
        assert fights[0].fighter2 == "DAVID BENAVIDEZ"
        assert fights[0].is_main_event is True
        assert fights[0].location == "T-Mobile Arena, Las Vegas, US"
        assert fights[0].source == "main_page"

    def test_main_event_with_undercard(self) -> None:
        lines = [
            "Sat, Mar 15 2025",
            "8:00 PM EST",
            "CANELO ALVAREZ",
            "VS",
            "DAVID BENAVIDEZ",
            "T-Mobile Arena, Las Vegas, US",
            "John Riel Casimero",
            "VS",
            "Naoya Inoue",
        ]
        fights = parse_main_page_text(lines)
        assert len(fights) == 2
        assert fights[0].is_main_event is True  # ALL CAPS = main event
        assert not fights[1].is_main_event  # Mixed case = undercard

    def test_context_inheritance(self) -> None:
        """Undercard fights inherit date/location from the main event context."""
        lines = [
            "Sat, Mar 15 2025",
            "8:00 PM EST",
            "CANELO ALVAREZ",
            "VS",
            "DAVID BENAVIDEZ",
            "T-Mobile Arena, Las Vegas, US",
            "John Riel Casimero",
            "VS",
            "Naoya Inoue",
        ]
        fights = parse_main_page_text(lines)
        assert fights[1].date_raw == "Sat, Mar 15 2025"
        assert fights[1].location == "T-Mobile Arena, Las Vegas, US"

    def test_multiple_cards(self) -> None:
        """Different dates produce separate fight entries with correct context."""
        lines = [
            "Sat, Mar 15 2025",
            "FIGHTER ONE",
            "VS",
            "FIGHTER TWO",
            "Sat, Mar 22 2025",
            "FIGHTER THREE",
            "VS",
            "FIGHTER FOUR",
        ]
        fights = parse_main_page_text(lines)
        assert len(fights) == 2
        # Both fights get dates assigned — second date comes from context update
        assert fights[0].date_raw is not None
        assert fights[1].date_raw == "Sat, Mar 22 2025"

    def test_broadcast_detection(self) -> None:
        lines = [
            "Sat, Mar 15 2025",
            "LIVE ON DAZN",
            "FIGHTER A",
            "VS",
            "FIGHTER B",
        ]
        fights = parse_main_page_text(lines)
        assert fights[0].broadcast == "LIVE ON DAZN"

    def test_gmt_time(self) -> None:
        lines = [
            "Sat, Mar 15 2025",
            "18:00 GMT",
            "FIGHTER A",
            "VS",
            "FIGHTER B",
        ]
        fights = parse_main_page_text(lines)
        assert fights[0].time == "18:00 GMT"

    def test_no_fights_found(self) -> None:
        lines = ["Just some random text", "No fights here", "Nothing to see"]
        fights = parse_main_page_text(lines)
        assert len(fights) == 0

    def test_invalid_fighter_rejected(self) -> None:
        """Lines that look like fighter names but aren't should be rejected."""
        lines = [
            "Sat, Mar 15 2025",
            "LIVE ON DAZN",
            "VS",
            "FIGHTER B",
        ]
        fights = parse_main_page_text(lines)
        assert len(fights) == 0

    def test_lookahead_location(self) -> None:
        """Location found via lookahead should be used."""
        lines = [
            "Sat, Mar 15 2025",
            "FIGHTER A",
            "VS",
            "FIGHTER B",
            "MGM Grand Arena, Las Vegas, US",
        ]
        fights = parse_main_page_text(lines)
        assert fights[0].location == "MGM Grand Arena, Las Vegas, US"


# ---------------------------------------------------------------------------
# Detail Page Text Parsing (integration tests)
# ---------------------------------------------------------------------------


class TestParseFightDetailText:
    def test_basic_detail(self) -> None:
        lines = [
            "Canelo Alvarez",
            "VS",
            "David Benavidez",
            "Saturday, March 15, 2025",
            "T-Mobile Arena, Las Vegas, US",
            "8:00 PM",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert result.fighter1 == "Canelo Alvarez"
        assert result.fighter2 == "David Benavidez"
        assert result.is_main_event is True
        assert result.source == "detail_page"

    def test_long_date_format(self) -> None:
        lines = [
            "Fighter A",
            "VS",
            "Fighter B",
            "Saturday, March 15, 2025",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert "Mar" in result.date_raw
        assert "15" in result.date_raw
        assert "2025" in result.date_raw

    def test_short_date_format(self) -> None:
        lines = [
            "Fighter A",
            "VS",
            "Fighter B",
            "Sat, Mar 15 2025",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert "Mar" in result.date_raw

    def test_gmt_time(self) -> None:
        lines = [
            "Fighter A",
            "VS",
            "Fighter B",
            "18:00 GMT",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert result.time == "18:00 GMT"

    def test_location_detection(self) -> None:
        lines = [
            "Fighter A",
            "VS",
            "Fighter B",
            "Madison Square Garden, New York, US",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert "Madison Square Garden" in result.location

    def test_broadcast_detection(self) -> None:
        lines = [
            "Fighter A",
            "VS",
            "Fighter B",
            "LIVE ON ESPN+",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert result.broadcast == "LIVE ON ESPN+"

    def test_no_valid_fighters(self) -> None:
        lines = ["Some random text", "No fights here", "Just articles"]
        result = parse_fight_detail_text(lines)
        assert result is None

    def test_first_vs_is_main_event(self) -> None:
        """Only the first VS on a detail page is captured as the main event."""
        lines = [
            "Main Fighter A",
            "VS",
            "Main Fighter B",
            "Undercard X",
            "VS",
            "Undercard Y",
        ]
        result = parse_fight_detail_text(lines)
        assert result is not None
        assert result.fighter1 == "Main Fighter A"
        assert result.fighter2 == "Main Fighter B"
