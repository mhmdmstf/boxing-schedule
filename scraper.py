"""
Boxing Schedule Scraper v2
Scrapes Ring Magazine for upcoming boxing fights, groups them into cards,
and generates a subscribable iCalendar (.ics) file.
"""

import logging
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCHEDULE_URL = "https://ringmagazine.com/en/schedule/fights"
LOAD_MORE_CLICKS = 5
PAGE_LOAD_TIMEOUT = 60_000
DETAIL_PAGE_TIMEOUT = 30_000
DETAIL_PAGE_WAIT = 2_000
DEFAULT_HOUR = 20
DEFAULT_MINUTE = 0
EVENT_DURATION_HOURS = 4
PAST_EVENT_CUTOFF_DAYS = 7
OUTPUT_FILE = "boxing_schedule.ics"

log = logging.getLogger("boxing")

# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------


@dataclass
class Fight:
    fighter1: str
    fighter2: str
    is_main_event: bool = False
    source: str = ""

    @property
    def title(self) -> str:
        return f"{self.fighter1} vs {self.fighter2}"


@dataclass
class Card:
    date: Optional[datetime] = None
    date_raw: str = "TBD"
    location: str = ""
    time_raw: str = ""
    timezone: str = "America/New_York"
    broadcast: str = ""
    fights: list[Fight] = field(default_factory=list)

    @property
    def main_event(self) -> Optional[Fight]:
        for f in self.fights:
            if f.is_main_event:
                return f
        return self.fights[0] if self.fights else None

    @property
    def undercards(self) -> list[Fight]:
        main = self.main_event
        return [f for f in self.fights if f is not main]

    def add_fight(self, fight: Fight) -> bool:
        """Add fight if not a duplicate. Returns True if added."""
        for existing in self.fights:
            if fighters_match(existing, fight):
                return False
        self.fights.append(fight)
        return True


# ---------------------------------------------------------------------------
# Name Matching
# ---------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    """Normalize a fighter name for comparison."""
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\s+(jr\.?|sr\.?|iii|ii|iv)$", "", name)
    return name


def _names_match(n1: str, n2: str) -> bool:
    """Check if two normalized fighter names refer to the same person."""
    if n1 == n2:
        return True
    parts1 = n1.split()
    parts2 = n2.split()
    if not parts1 or not parts2:
        return False
    # Last names must match exactly
    if parts1[-1] != parts2[-1]:
        return False
    # If both have first names, they must match
    if len(parts1) > 1 and len(parts2) > 1:
        return parts1[0] == parts2[0] or parts1[0][:3] == parts2[0][:3]
    # One is a single name (just last name) — accept the last name match
    return True


def fighters_match(fight1: Fight, fight2: Fight) -> bool:
    """Check if two fights are the same matchup (either order)."""
    a1 = normalize_name(fight1.fighter1)
    a2 = normalize_name(fight1.fighter2)
    b1 = normalize_name(fight2.fighter1)
    b2 = normalize_name(fight2.fighter2)
    forward = _names_match(a1, b1) and _names_match(a2, b2)
    crossed = _names_match(a1, b2) and _names_match(a2, b1)
    return forward or crossed


# ---------------------------------------------------------------------------
# Date / Time / Timezone Parsing
# ---------------------------------------------------------------------------

DATE_FORMATS = [
    "%b %d %Y",
    "%B %d %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string into a datetime. Returns None on failure."""
    if not date_str or date_str == "TBD":
        return None
    cleaned = re.sub(
        r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)(day|nesday|urday)?,?\s*", "", date_str
    )
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned.strip(), fmt)
        except ValueError:
            continue
    log.warning("Could not parse date: '%s'", date_str)
    return None


def parse_time(time_str: str) -> tuple[int, int]:
    """Extract hour and minute from a time string. Returns (20, 0) default."""
    if not time_str:
        return DEFAULT_HOUR, DEFAULT_MINUTE
    # AM/PM format
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_str, re.IGNORECASE)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if m.group(3).upper() == "PM" and hour != 12:
            hour += 12
        elif m.group(3).upper() == "AM" and hour == 12:
            hour = 0
        return hour, minute
    # GMT / 24h format
    m = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    return DEFAULT_HOUR, DEFAULT_MINUTE


# Country suffix -> timezone (checked at end of location string)
_COUNTRY_TZ: list[tuple[str, str]] = [
    (", GB", "Europe/London"),
    (", UK", "Europe/London"),
    (", AU", "Australia/Sydney"),
    (", JP", "Asia/Tokyo"),
    (", DE", "Europe/Berlin"),
    (", DK", "Europe/Copenhagen"),
    (", MX", "America/Mexico_City"),
    (", PR", "America/Puerto_Rico"),
    (", SA", "Asia/Riyadh"),
    (", AE", "Asia/Dubai"),
    (", GH", "Africa/Accra"),
    (", CA", "America/Toronto"),
    (", IE", "Europe/Dublin"),
    (", FR", "Europe/Paris"),
    (", PH", "Asia/Manila"),
    (", NZ", "Pacific/Auckland"),
    (", KR", "Asia/Seoul"),
]

# City/region keywords -> timezone (checked anywhere in location)
_CITY_TZ: list[tuple[list[str], str]] = [
    (["LONDON", "MANCHESTER", "BIRMINGHAM", "LEEDS", "NOTTINGHAM",
      "DERBY", "SHEFFIELD", "LIVERPOOL"], "Europe/London"),
    (["SYDNEY", "MELBOURNE", "BRISBANE", "GOLD COAST", "PERTH",
      "ADELAIDE"], "Australia/Sydney"),
    (["TOKYO", "OSAKA", "NAGOYA", "SAITAMA"], "Asia/Tokyo"),
    (["OBERHAUSEN", "BERLIN", "HAMBURG"], "Europe/Berlin"),
    (["KOLDING", "COPENHAGEN"], "Europe/Copenhagen"),
    (["RIYADH", "JEDDAH", "SAUDI"], "Asia/Riyadh"),
    (["DUBAI", "ABU DHABI"], "Asia/Dubai"),
    (["ACCRA", "GHANA"], "Africa/Accra"),
    (["MONTREAL", "TORONTO", "VANCOUVER", "GATINEAU", "OTTAWA",
      "CALGARY"], "America/Toronto"),
    (["PUERTO RICO", "SAN JUAN"], "America/Puerto_Rico"),
    # US West Coast
    (["LAS VEGAS", "NEVADA", "LOS ANGELES", "CALIFORNIA", "PHOENIX",
      "GLENDALE", "STOCKTON", "ANAHEIM", "INGLEWOOD"], "America/Los_Angeles"),
    # US Central
    (["CHICAGO", "ILLINOIS", "SAN ANTONIO", "HOUSTON", "DALLAS",
      "TEXAS"], "America/Chicago"),
]


def infer_timezone(time_str: str, location: str) -> str:
    """Guess timezone from time string and location."""
    if "GMT" in time_str.upper():
        return "Europe/London"
    loc_upper = location.upper().strip()
    # Check city keywords first (more specific than country suffix)
    for keywords, tz in _CITY_TZ:
        if any(kw in loc_upper for kw in keywords):
            return tz
    # Then check country suffix at end of string
    for suffix, tz in _COUNTRY_TZ:
        if loc_upper.endswith(suffix.upper()):
            return tz
    return "America/New_York"


# ---------------------------------------------------------------------------
# Scraping — Main Page
# ---------------------------------------------------------------------------

# Regex patterns
_DATE_PAT = re.compile(
    r"(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}"
)
_TIME_PAT = re.compile(r"(\d{1,2}:\d{2}\s+(?:AM|PM))\s+(\S+)")
_GMT_PAT = re.compile(r"(\d{1,2}:\d{2})\s+GMT")

# Words that disqualify a line from being a venue/location
_LOCATION_NEGATIVE = re.compile(
    r"(tops|signs|announces?|preview|odds|results|highlights|confirmed|"
    r"undercard|breaking|report|watch|recap|analysis|exclusive|interview|"
    r"article|news|update|sources?|weighs?\s+in)",
    re.IGNORECASE,
)

# Known country suffixes for location detection
_COUNTRY_SUFFIXES = (
    ", US", ", UK", ", GB", ", AU", ", JP", ", PR", ", MX", ", DE",
    ", DK", ", CA", ", SA", ", AE", ", GH", ", IE", ", FR", ", ES",
    ", IT", ", PH", ", NZ", ", ZA", ", KR", ", CN", ", TH",
)

_VENUE_KEYWORDS = (
    "ARENA", "CENTER", "CENTRE", "STADIUM", "HALL", "THEATER", "THEATRE",
    "CASINO", "GARDEN", "COLISEUM", "COLISEO", "DOME", "PAVILION",
    "AUDITORIUM", "CONVENTION", "EXPO",
)


def _is_location_line(line: str) -> bool:
    """Check if a line looks like a venue/location."""
    if "," not in line or len(line) < 8 or len(line) > 120:
        return False
    if line.startswith("|") or line[0].isdigit():
        return False
    if _DATE_PAT.search(line):
        return False
    if _LOCATION_NEGATIVE.search(line):
        return False
    upper = line.upper()
    return (
        any(upper.endswith(s) for s in _COUNTRY_SUFFIXES)
        or any(kw in upper for kw in _VENUE_KEYWORDS)
    )


def _is_valid_fighter(name: str) -> bool:
    """Check if a string looks like a fighter name."""
    return (
        len(name) >= 3
        and "CHAMPION" not in name.upper()
        and not name.isdigit()
        and not name.startswith("LIVE ")
        and not _DATE_PAT.match(name)
    )


def scrape_main_page(page) -> list[dict]:
    """Scrape fights from the main schedule page."""
    fights = []
    body = page.inner_text("body")
    lines = [line.strip() for line in body.split("\n") if line.strip()]

    current_date = None
    current_location = None
    current_time = None
    current_broadcast = None

    i = 0
    while i < len(lines):
        line = lines[i]

        # Update context
        if _DATE_PAT.match(line):
            current_date = line
            i += 1
            continue

        time_match = _TIME_PAT.match(line)
        if time_match:
            current_time = time_match.group(1)
            i += 1
            continue

        gmt_match = _GMT_PAT.match(line)
        if gmt_match and not current_time:
            current_time = gmt_match.group(1) + " GMT"
            i += 1
            continue

        if line.startswith("LIVE ON ") or line.startswith("LIVE AND "):
            current_broadcast = line
            i += 1
            continue

        # Detect fights via VS pattern
        if line == "VS" and 0 < i < len(lines) - 1:
            fighter1 = lines[i - 1]
            fighter2 = lines[i + 1]

            if _is_valid_fighter(fighter1) and _is_valid_fighter(fighter2):
                is_main_event = fighter1.isupper() and fighter2.isupper()

                # Look ahead for fight-specific details
                fight_location = None
                fight_date = None
                fight_time = None
                fight_broadcast = None

                for j in range(i + 2, min(i + 12, len(lines))):
                    scan = lines[j]
                    if scan == "VS":
                        break
                    if _DATE_PAT.match(scan):
                        fight_date = scan
                    tm = _TIME_PAT.match(scan)
                    if tm:
                        fight_time = tm.group(1)
                    gm = _GMT_PAT.match(scan)
                    if gm and not fight_time:
                        fight_time = gm.group(1) + " GMT"
                    if scan.startswith("LIVE ON ") or scan.startswith("LIVE AND "):
                        fight_broadcast = scan
                    if _is_location_line(scan) and not fight_location:
                        fight_location = scan

                final_date = fight_date or current_date
                final_location = fight_location or current_location
                final_time = fight_time or current_time
                final_broadcast = fight_broadcast or current_broadcast

                # Update context for subsequent undercards
                current_date = fight_date or current_date
                current_location = fight_location or current_location
                current_time = fight_time or current_time
                current_broadcast = fight_broadcast or current_broadcast

                fights.append({
                    "fighter1": fighter1,
                    "fighter2": fighter2,
                    "date_raw": final_date or "TBD",
                    "location": final_location or "",
                    "time": final_time or "",
                    "broadcast": final_broadcast or "",
                    "is_main_event": is_main_event,
                    "source": "main_page",
                })

        i += 1

    return fights


# ---------------------------------------------------------------------------
# Scraping — Detail Pages
# ---------------------------------------------------------------------------

_LONG_DATE_PAT = re.compile(
    r"(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+"
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})"
)
_SHORT_DATE_PAT = re.compile(
    r"(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{4})"
)
_TIME_SEARCH_PAT = re.compile(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", re.IGNORECASE)
_GMT_SEARCH_PAT = re.compile(r"(\d{1,2}:\d{2})\s*GMT", re.IGNORECASE)

_MONTH_ABBREV = {
    "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
    "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
    "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec",
}
_DAY_ABBREV = {
    "Sunday": "Sun", "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed",
    "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat",
}


def scrape_fight_detail(page, url: str) -> Optional[dict]:
    """Scrape details from an individual fight page."""
    try:
        page.goto(url, timeout=DETAIL_PAGE_TIMEOUT)
        page.wait_for_timeout(DETAIL_PAGE_WAIT)

        body = page.inner_text("body")
        lines = [line.strip() for line in body.split("\n") if line.strip()]

        fighter1 = None
        fighter2 = None
        fight_date = None
        location = None
        time_str = None
        broadcast = None
        is_first_vs = True

        for i, line in enumerate(lines):
            # Fighter names via VS pattern
            if line.upper() == "VS" and 0 < i < len(lines) - 1:
                f1 = lines[i - 1]
                f2 = lines[i + 1]
                if _is_valid_fighter(f1) and _is_valid_fighter(f2):
                    if is_first_vs:
                        # First VS on a detail page = main event
                        fighter1 = f1
                        fighter2 = f2
                        is_first_vs = False

            # Date parsing
            long_m = _LONG_DATE_PAT.search(line)
            if long_m and not fight_date:
                day_a = _DAY_ABBREV.get(long_m.group(1), long_m.group(1)[:3])
                mon_a = _MONTH_ABBREV.get(long_m.group(2), long_m.group(2)[:3])
                fight_date = f"{day_a}, {mon_a} {long_m.group(3)} {long_m.group(4)}"

            short_m = _SHORT_DATE_PAT.search(line)
            if short_m and not fight_date:
                fight_date = short_m.group(0)

            # Time parsing
            if "GMT" in line.upper() and not time_str:
                gmt_m = _GMT_SEARCH_PAT.search(line)
                if gmt_m:
                    time_str = gmt_m.group(1) + " GMT"

            time_m = _TIME_SEARCH_PAT.search(line)
            if time_m and not time_str:
                time_str = time_m.group(1)

            # Location
            if _is_location_line(line) and not location:
                location = line

            # Broadcast
            if line.upper().startswith("LIVE ON ") or line.upper().startswith("LIVE AND "):
                broadcast = line

        if fighter1 and fighter2:
            return {
                "fighter1": fighter1,
                "fighter2": fighter2,
                "date_raw": fight_date or "TBD",
                "location": location or "",
                "time": time_str or "",
                "broadcast": broadcast or "",
                "is_main_event": True,  # First VS on detail page = main event
                "source": "detail_page",
            }

    except Exception as e:
        log.warning("Error scraping %s: %s", url, e)

    return None


# ---------------------------------------------------------------------------
# Scraping — Orchestrator
# ---------------------------------------------------------------------------


def scrape_all_fights() -> list[dict]:
    """Launch browser, scrape main page + detail pages, return all fights."""
    all_fights: list[dict] = []
    seen_slugs: set[str] = set()

    with sync_playwright() as p:
        log.info("Launching browser")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
            ],
        )
        page = browser.new_page()

        try:
            log.info("Loading schedule page")
            page.goto(SCHEDULE_URL, timeout=PAGE_LOAD_TIMEOUT)
            page.wait_for_timeout(5000)

            # Expand full schedule
            for i in range(LOAD_MORE_CLICKS):
                try:
                    btn = page.locator("text=Load More")
                    if btn.count() > 0 and btn.first.is_visible():
                        log.info("Clicking Load More (%d/%d)", i + 1, LOAD_MORE_CLICKS)
                        btn.first.click()
                        page.wait_for_timeout(2000)
                    else:
                        break
                except Exception as e:
                    log.debug("Load More click %d failed: %s", i + 1, e)
                    break

            # Pass 1: Main page (preserves casing for main event detection)
            log.info("Scraping main page")
            main_fights = scrape_main_page(page)
            for fight in main_fights:
                all_fights.append(fight)
                tag = "[MAIN]" if fight["is_main_event"] else "[card]"
                log.info("  %s %s vs %s — %s",
                         tag, fight["fighter1"], fight["fighter2"], fight["date_raw"])

            # Collect detail page URLs
            html = page.content()
            slugs = sorted(set(re.findall(r"/en/schedule/fights/([a-z0-9-]+)", html)))
            log.info("Found %d fight detail URLs", len(slugs))

            # Pass 2: Detail pages (fills in missing info)
            for slug in slugs:
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                url = f"https://ringmagazine.com/en/schedule/fights/{slug}"
                log.info("  Scraping: %s", slug)

                detail = scrape_fight_detail(page, url)
                if not detail:
                    continue

                # Merge with existing or add new
                detail_fight = Fight(detail["fighter1"], detail["fighter2"])
                merged = False
                for existing in all_fights:
                    existing_fight = Fight(existing["fighter1"], existing["fighter2"])
                    if fighters_match(detail_fight, existing_fight):
                        # Fill missing fields from detail page
                        for key in ("location", "time", "broadcast"):
                            if not existing[key] and detail[key]:
                                existing[key] = detail[key]
                        if existing["date_raw"] == "TBD" and detail["date_raw"] != "TBD":
                            existing["date_raw"] = detail["date_raw"]
                        if detail["is_main_event"]:
                            existing["is_main_event"] = True
                        merged = True
                        break

                if not merged:
                    all_fights.append(detail)
                    log.info("    New fight: %s vs %s — %s",
                             detail["fighter1"], detail["fighter2"], detail["date_raw"])

        except Exception as e:
            log.error("Browser error: %s", e)
            traceback.print_exc()
        finally:
            browser.close()

    return all_fights


# ---------------------------------------------------------------------------
# Card Assembly
# ---------------------------------------------------------------------------


def _normalize_location_key(location: str) -> str:
    """Normalize location for grouping (strip country suffix, lowercase)."""
    loc = location.lower().strip()
    loc = re.sub(r"\s*,\s*[a-z]{2}$", "", loc)
    return loc


def build_cards(raw_fights: list[dict]) -> list[Card]:
    """Group raw fight dicts into Cards by date + location."""
    cards_by_key: dict[tuple, Card] = {}

    for raw in raw_fights:
        date = parse_date(raw["date_raw"])
        date_key = date.strftime("%Y-%m-%d") if date else "TBD"
        loc_key = _normalize_location_key(raw.get("location", ""))
        key = (date_key, loc_key)

        if key not in cards_by_key:
            cards_by_key[key] = Card(
                date=date,
                date_raw=raw["date_raw"],
                location=raw.get("location", ""),
                time_raw=raw.get("time", ""),
                broadcast=raw.get("broadcast", ""),
            )

        card = cards_by_key[key]
        fight = Fight(
            fighter1=raw["fighter1"],
            fighter2=raw["fighter2"],
            is_main_event=raw.get("is_main_event", False),
            source=raw.get("source", ""),
        )
        card.add_fight(fight)

        # Fill missing card metadata
        if not card.location and raw.get("location"):
            card.location = raw["location"]
        if not card.time_raw and raw.get("time"):
            card.time_raw = raw["time"]
        if not card.broadcast and raw.get("broadcast"):
            card.broadcast = raw["broadcast"]

    # Infer timezone for each card
    for card in cards_by_key.values():
        card.timezone = infer_timezone(card.time_raw, card.location)

    return list(cards_by_key.values())


def filter_past_events(cards: list[Card], cutoff_days: int = PAST_EVENT_CUTOFF_DAYS) -> list[Card]:
    """Remove events that ended more than cutoff_days ago."""
    cutoff = datetime.now() - timedelta(days=cutoff_days)
    result = []
    for card in cards:
        if card.date is None or card.date >= cutoff:
            result.append(card)
        else:
            main = card.main_event
            name = main.title if main else "unknown"
            log.info("Filtering past event: %s (%s)", name, card.date_raw)
    return result


# ---------------------------------------------------------------------------
# Calendar Generation
# ---------------------------------------------------------------------------


def create_calendar(cards: list[Card]) -> Calendar:
    """Create an iCalendar from the list of cards."""
    cal = Calendar()
    cal.add("prodid", "-//Boxing Schedule//github-action//")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Boxing Schedule")
    cal.add("method", "PUBLISH")

    for card in cards:
        main = card.main_event
        if not main:
            continue

        if not card.date:
            log.warning("Skipping event with no date: %s", main.title)
            continue

        undercards = card.undercards

        # Summary: MAIN EVENT (+N more)
        summary = f"\U0001f94a {main.title.upper()}"
        if undercards:
            summary += f" (+{len(undercards)} more)"

        event = Event()
        event.add("summary", summary)

        # Date/time with timezone
        hour, minute = parse_time(card.time_raw)
        try:
            tz = ZoneInfo(card.timezone)
        except Exception:
            tz = ZoneInfo("America/New_York")
        dt = card.date.replace(hour=hour, minute=minute, second=0, tzinfo=tz)
        event.add("dtstart", dt)
        event.add("dtend", dt + timedelta(hours=EVENT_DURATION_HOURS))

        # Description
        desc_lines = [f"MAIN EVENT: {main.title.upper()}", ""]
        if undercards:
            desc_lines.append("Undercard:")
            for uc in undercards:
                desc_lines.append(f"  - {uc.title}")
            desc_lines.append("")
        if card.location:
            desc_lines.append(f"Location: {card.location}")
        if card.broadcast:
            desc_lines.append(f"Broadcast: {card.broadcast}")
        if card.time_raw:
            desc_lines.append(f"Time: {card.time_raw}")
        event.add("description", "\n".join(desc_lines))

        if card.location:
            event.add("location", card.location)

        # Stable UID
        names = re.sub(r"[^a-zA-Z0-9]", "", main.title)
        date_str = card.date.strftime("%Y%m%d")
        event.add("uid", f"{names}-{date_str}@boxingschedule")

        cal.add_component(event)

    return cal


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    raw_fights = scrape_all_fights()

    if not raw_fights:
        log.error("No fights found. The website structure may have changed.")
        sys.exit(1)

    cards = build_cards(raw_fights)
    cards = filter_past_events(cards)

    # Sort by date (TBD at end)
    cards.sort(key=lambda c: c.date or datetime.max)

    log.info("Built %d cards from %d fights", len(cards), len(raw_fights))

    cal = create_calendar(cards)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())
    log.info("Written %s", OUTPUT_FILE)

    # Summary
    for card in cards:
        main = card.main_event
        if main:
            uc = len(card.undercards)
            log.info("  %s (%s) +%d undercard(s)", main.title.upper(), card.date_raw, uc)


if __name__ == "__main__":
    main()
