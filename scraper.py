"""Boxing Schedule scraper.

Pipeline:
    fetch_events()         -> dict          (raw API response)
    parse_events()         -> list[Event]   (typed, timezone-aware)
    filter_recent()        -> list[Event]   (drop events older than cutoff)
    build_calendar()       -> Calendar      (iCal object, RFC 5545)
    write_ics()            -> bytes         (serialise + persist)

Data source: ringmagazine.com's public schedule API.  No browser, no HTML
parsing -- the API returns the same structured records that power the website.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar  # type: ignore[import-untyped]
from icalendar import Event as IcalEvent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EVENTS_API = (
    "https://www.ringmagazine.com/api/cached/v1/content/search/events/upcoming"
    "?limit=50&language=en"
)
HTTP_TIMEOUT_SECONDS = 30
USER_AGENT = (
    "Mozilla/5.0 (compatible; boxing-schedule/3.0; "
    "+https://github.com/mhmdmstf/boxing-schedule)"
)
EVENT_DURATION = timedelta(hours=4)
PAST_EVENT_CUTOFF = timedelta(days=7)
OUTPUT_FILE = Path("boxing_schedule.ics")
CALENDAR_NAME = "Boxing Schedule"
CALENDAR_PRODID = "-//Boxing Schedule//github-action//"

log = logging.getLogger("boxing")

# ---------------------------------------------------------------------------
# Timezone inference
# ---------------------------------------------------------------------------
#
# Strategy: ISO-3166 country code provides a default timezone; selected cities
# in multi-zone countries (US, CA, AU, RU) override that default.  Keep the
# overrides curated, not exhaustive -- the country default is correct for the
# common case.

_COUNTRY_DEFAULT_TZ: dict[str, str] = {
    "AR": "America/Argentina/Buenos_Aires",
    "AU": "Australia/Sydney",
    "BR": "America/Sao_Paulo",
    "CA": "America/Toronto",
    "CN": "Asia/Shanghai",
    "CO": "America/Bogota",
    "CR": "America/Costa_Rica",
    "DE": "Europe/Berlin",
    "DK": "Europe/Copenhagen",
    "DO": "America/Santo_Domingo",
    "EG": "Africa/Cairo",
    "ES": "Europe/Madrid",
    "FR": "Europe/Paris",
    "GB": "Europe/London",
    "GH": "Africa/Accra",
    "IE": "Europe/Dublin",
    "IT": "Europe/Rome",
    "JP": "Asia/Tokyo",
    "KG": "Asia/Bishkek",
    "KR": "Asia/Seoul",
    "MX": "America/Mexico_City",
    "NI": "America/Managua",
    "NZ": "Pacific/Auckland",
    "PA": "America/Panama",
    "PH": "Asia/Manila",
    "PL": "Europe/Warsaw",
    "PR": "America/Puerto_Rico",
    "RU": "Europe/Moscow",
    "SA": "Asia/Riyadh",
    "TH": "Asia/Bangkok",
    "UA": "Europe/Kyiv",
    "AE": "Asia/Dubai",
    "UK": "Europe/London",  # informal alias for GB
    "US": "America/New_York",
    "ZA": "Africa/Johannesburg",
}

# City -> timezone for places that aren't covered by their country default.
# Compared case-insensitively against ApiLocation.city.
_CITY_OVERRIDE_TZ: dict[str, str] = {
    # United States (default America/New_York)
    "los angeles": "America/Los_Angeles",
    "las vegas": "America/Los_Angeles",
    "san diego": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "san jose": "America/Los_Angeles",
    "phoenix": "America/Phoenix",
    "glendale": "America/Phoenix",
    "tucson": "America/Phoenix",
    "denver": "America/Denver",
    "albuquerque": "America/Denver",
    "salt lake city": "America/Denver",
    "chicago": "America/Chicago",
    "dallas": "America/Chicago",
    "houston": "America/Chicago",
    "san antonio": "America/Chicago",
    "new orleans": "America/Chicago",
    "memphis": "America/Chicago",
    "nashville": "America/Chicago",
    "el paso": "America/Denver",
    "tx": "America/Chicago",
    "texas": "America/Chicago",
    # Canada (default America/Toronto)
    "vancouver": "America/Vancouver",
    "calgary": "America/Edmonton",
    "edmonton": "America/Edmonton",
    "winnipeg": "America/Winnipeg",
    # Russia (default Europe/Moscow)
    "yekaterinburg": "Asia/Yekaterinburg",
    "novosibirsk": "Asia/Novosibirsk",
    "vladivostok": "Asia/Vladivostok",
    # Australia (default Australia/Sydney)
    "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide",
    "brisbane": "Australia/Brisbane",
}


def infer_timezone(country: str | None, city: str | None) -> ZoneInfo:
    """Return the best-guess timezone for an event venue.

    Falls back to America/New_York if neither country nor city resolves.
    The fallback only kicks in for events we genuinely can't place; logging
    surfaces such cases so the override list can grow.
    """
    if city:
        tz_name = _CITY_OVERRIDE_TZ.get(city.lower())
        if tz_name:
            return _zoneinfo(tz_name)
    if country:
        tz_name = _COUNTRY_DEFAULT_TZ.get(country.upper())
        if tz_name:
            return _zoneinfo(tz_name)
    log.warning("Falling back to America/New_York for country=%r city=%r",
                country, city)
    return ZoneInfo("America/New_York")


def _zoneinfo(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        log.warning("Unknown timezone %r, using UTC", name)
        return ZoneInfo("UTC")


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fight:
    fighter_a: str
    fighter_b: str
    is_main_event: bool
    weight_class: str | None = None
    rounds: int | None = None

    @property
    def title(self) -> str:
        return f"{self.fighter_a} vs {self.fighter_b}"


@dataclass(frozen=True)
class Event:
    """A single boxing card."""

    id: str
    start_utc: datetime
    end_utc: datetime | None
    venue: str | None
    city: str | None
    country: str | None  # ISO-3166-1 alpha-2
    fights: tuple[Fight, ...]
    is_sold_out: bool

    @property
    def main_event(self) -> Fight | None:
        for fight in self.fights:
            if fight.is_main_event:
                return fight
        return self.fights[0] if self.fights else None

    @property
    def undercards(self) -> tuple[Fight, ...]:
        main = self.main_event
        return tuple(f for f in self.fights if f is not main)

    @property
    def timezone(self) -> ZoneInfo:
        return infer_timezone(self.country, self.city)

    @property
    def local_start(self) -> datetime:
        return self.start_utc.astimezone(self.timezone)

    @property
    def location_str(self) -> str:
        parts = [p for p in (self.venue, self.city, self.country) if p]
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Parsing -- pure functions over the API JSON shape
# ---------------------------------------------------------------------------


def _parse_iso_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        UTC
    )


def parse_fight(raw: dict) -> Fight:
    return Fight(
        fighter_a=(raw.get("fighterA") or {}).get("name", "").strip(),
        fighter_b=(raw.get("fighterB") or {}).get("name", "").strip(),
        is_main_event=bool(raw.get("isMainEvent")),
        weight_class=(raw.get("weightClass") or None),
        rounds=raw.get("noOfRounds"),
    )


def parse_event(raw: dict) -> Event | None:
    """Build an Event from one API record.  Returns None if essential fields
    are missing -- start time and at least one named fight."""
    start_raw = raw.get("eventStart")
    if not start_raw:
        log.debug("Skipping event %s: no eventStart", raw.get("id"))
        return None
    try:
        start_utc = _parse_iso_utc(start_raw)
    except ValueError:
        log.warning("Skipping event %s: unparsable eventStart %r",
                    raw.get("id"), start_raw)
        return None

    end_raw = raw.get("eventEnd")
    end_utc: datetime | None = None
    if end_raw:
        try:
            end_utc = _parse_iso_utc(end_raw)
        except ValueError:
            log.debug("Event %s has unparsable eventEnd %r", raw.get("id"),
                      end_raw)

    fights = tuple(
        f for f in (parse_fight(rf) for rf in raw.get("fights") or [])
        if f.fighter_a and f.fighter_b
    )
    if not fights:
        log.debug("Skipping event %s: no named fights", raw.get("id"))
        return None

    location = raw.get("eventLocation") or {}
    return Event(
        id=str(raw.get("id") or ""),
        start_utc=start_utc,
        end_utc=end_utc,
        venue=(location.get("venueName") or None),
        city=(location.get("city") or None),
        country=(location.get("country") or None),
        fights=fights,
        is_sold_out=bool(raw.get("isSoldOut")),
    )


def parse_events(payload: dict) -> list[Event]:
    """Parse the full API payload into a list of Events (lazy-failure-tolerant)."""
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise ValueError(f"Unexpected payload shape: data is {type(data).__name__}")
    parsed = [event for event in (parse_event(r) for r in data) if event]
    log.info("Parsed %d events from %d API records", len(parsed), len(data))
    return parsed


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def fetch_events(url: str = EVENTS_API) -> dict:
    """Hit the schedule API and return the parsed JSON body."""
    log.info("Fetching %s", url)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e
    # API returns UTF-8 with a BOM in some responses; tolerate it.
    payload: dict = json.loads(body.decode("utf-8-sig"))
    return payload


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def filter_recent(
    events: list[Event],
    now_utc: datetime | None = None,
    past_cutoff: timedelta = PAST_EVENT_CUTOFF,
) -> list[Event]:
    """Drop events that ended more than `past_cutoff` ago."""
    now = now_utc or datetime.now(UTC)
    cutoff = now - past_cutoff
    kept: list[Event] = []
    dropped = 0
    for ev in events:
        if ev.start_utc >= cutoff:
            kept.append(ev)
        else:
            dropped += 1
    if dropped:
        log.info("Filtered %d past events (older than %s)", dropped, cutoff.date())
    return kept


# ---------------------------------------------------------------------------
# Calendar rendering
# ---------------------------------------------------------------------------


def _format_summary(event: Event) -> str:
    main = event.main_event
    assert main is not None  # parse_event already rejected empty cards
    summary = f"\U0001f94a {main.title.upper()}"
    n_uc = len(event.undercards)
    if n_uc:
        summary += f" (+{n_uc} more)"
    return summary


def _format_description(event: Event) -> str:
    main = event.main_event
    assert main is not None
    lines = [f"MAIN EVENT: {main.title.upper()}"]
    if main.weight_class:
        lines.append(f"  {main.weight_class}"
                     + (f", {main.rounds} rounds" if main.rounds else ""))
    if event.undercards:
        lines.append("")
        lines.append("Undercard:")
        for uc in event.undercards:
            line = f"  - {uc.title}"
            if uc.weight_class:
                line += f"  ({uc.weight_class})"
            lines.append(line)
    lines.append("")
    if event.venue:
        lines.append(f"Venue: {event.location_str}")
    local = event.local_start
    lines.append(f"Local start: {local:%a %d %b %Y, %H:%M %Z}")
    if event.is_sold_out:
        lines.append("Status: SOLD OUT")
    return "\n".join(lines)


def build_calendar(events: list[Event], now_utc: datetime | None = None) -> Calendar:
    cal = Calendar()
    cal.add("prodid", CALENDAR_PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CALENDAR_NAME)

    stamp = now_utc or datetime.now(UTC)

    for event in events:
        ical = IcalEvent()
        ical.add("uid", f"boxing-{event.id}@ringmagazine.com")
        ical.add("summary", _format_summary(event))
        ical.add("description", _format_description(event))
        ical.add("dtstamp", stamp)
        ical.add("sequence", 0)
        ical.add("status", "CONFIRMED")
        dtstart = event.local_start
        dtend = (event.end_utc.astimezone(event.timezone)
                 if event.end_utc else dtstart + EVENT_DURATION)
        ical.add("dtstart", dtstart)
        ical.add("dtend", dtend)
        if event.venue:
            ical.add("location", event.location_str)
        cal.add_component(ical)

    return cal


def write_ics(calendar: Calendar, path: Path = OUTPUT_FILE) -> int:
    body = calendar.to_ical()
    path.write_bytes(body)
    return len(body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    payload = fetch_events()
    events = parse_events(payload)
    events = filter_recent(events)
    events.sort(key=lambda e: e.start_utc)

    if not events:
        log.error("No upcoming events to write. Aborting.")
        return 1

    calendar = build_calendar(events)
    n_bytes = write_ics(calendar)
    log.info("Wrote %s (%d events, %d bytes)", OUTPUT_FILE, len(events), n_bytes)

    for ev in events:
        main_fight = ev.main_event
        title = main_fight.title.upper() if main_fight else "?"
        log.info("  %s  %s  @  %s  (+%d UC)",
                 ev.local_start.strftime("%Y-%m-%d %H:%M %Z"),
                 title, ev.venue or "?", len(ev.undercards))
    return 0


if __name__ == "__main__":
    sys.exit(main())
