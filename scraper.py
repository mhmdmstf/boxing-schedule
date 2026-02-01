import re
import sys
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from icalendar import Calendar, Event
from playwright.sync_api import sync_playwright


# Type definitions
class Fight(TypedDict):
    fighter1: str
    fighter2: str
    title: str
    date_raw: str
    location: str
    time: str
    broadcast: str
    is_main_event: bool


class Card(TypedDict):
    main_event: Fight | None
    undercards: list[Fight]
    date_raw: str
    location: str
    time: str
    broadcast: str


# Timeout constants (milliseconds)
PAGE_LOAD_TIMEOUT_MS = 60000
DETAIL_PAGE_TIMEOUT_MS = 30000
INITIAL_LOAD_WAIT_MS = 5000
POST_CLICK_WAIT_MS = 2000

# Scraping constants
LOAD_MORE_CLICKS = 5
LOOKAHEAD_LINES = 12
MIN_FIGHTER_NAME_LENGTH = 3

# Compiled regex patterns
DATE_PATTERN = re.compile(
    r'(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+'
    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}'
)
LONG_DATE_PATTERN = re.compile(
    r'(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+'
    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
    r'(\d{1,2}),?\s+(\d{4})'
)
TIME_PATTERN = re.compile(r'(\d{1,2}:\d{2}\s+(?:AM|PM))\s+(\S+)')
TIME_ONLY_PATTERN = re.compile(r'(\d{1,2}:\d{2}\s*(?:AM|PM))', re.IGNORECASE)
GMT_PATTERN = re.compile(r'(\d{1,2}:\d{2})\s*GMT', re.IGNORECASE)

# Date conversion maps
LONG_TO_SHORT_MONTH = {
    'January': 'Jan', 'February': 'Feb', 'March': 'Mar', 'April': 'Apr',
    'May': 'May', 'June': 'Jun', 'July': 'Jul', 'August': 'Aug',
    'September': 'Sep', 'October': 'Oct', 'November': 'Nov', 'December': 'Dec'
}
LONG_TO_SHORT_DAY = {
    'Sunday': 'Sun', 'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
    'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat'
}


def scrape_main_page_fights(page) -> list[Fight]:
    """
    Scrape fights from the main page, preserving casing to identify main events.
    Returns list of fights with is_main_event flag and context info.
    """
    fights: list[Fight] = []

    body = page.inner_text('body')
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    current_date = None
    current_location = None
    current_time = None
    current_broadcast = None

    i = 0
    while i < len(lines):
        line = lines[i]

        if DATE_PATTERN.match(line):
            current_date = line
            i += 1
            continue

        time_match = TIME_PATTERN.match(line)
        if time_match:
            current_time = time_match.group(1)
            i += 1
            continue

        gmt_match = GMT_PATTERN.match(line)
        if gmt_match and not current_time:
            current_time = gmt_match.group(1) + " GMT"
            i += 1
            continue

        if line.startswith('LIVE ON ') or line.startswith('LIVE AND '):
            current_broadcast = line
            i += 1
            continue

        if line == 'VS' and i > 0 and i < len(lines) - 1:
            fighter1 = lines[i - 1]
            fighter2 = lines[i + 1]

            if (len(fighter1) < MIN_FIGHTER_NAME_LENGTH or
                len(fighter2) < MIN_FIGHTER_NAME_LENGTH or
                'CHAMPION' in fighter1.upper() or 'CHAMPION' in fighter2.upper() or
                fighter1.isdigit() or fighter2.isdigit()):
                i += 1
                continue

            is_main_event = fighter1.isupper() and fighter2.isupper()

            fight_location = None
            fight_date = None
            fight_time = None
            fight_broadcast = None

            for j in range(i + 2, min(i + LOOKAHEAD_LINES, len(lines))):
                scan_line = lines[j]
                if scan_line == 'VS':
                    break
                if DATE_PATTERN.match(scan_line):
                    fight_date = scan_line
                time_match = TIME_PATTERN.match(scan_line)
                if time_match:
                    fight_time = time_match.group(1)
                gmt_match = GMT_PATTERN.match(scan_line)
                if gmt_match and not fight_time:
                    fight_time = gmt_match.group(1) + " GMT"
                if scan_line.startswith('LIVE ON ') or scan_line.startswith('LIVE AND '):
                    fight_broadcast = scan_line
                if (',' in scan_line and not scan_line.startswith('|') and
                    not scan_line.isdigit() and not DATE_PATTERN.match(scan_line) and
                    len(scan_line) > 5):
                    fight_location = scan_line

            final_date = fight_date or current_date
            final_location = fight_location or current_location
            final_time = fight_time or current_time
            final_broadcast = fight_broadcast or current_broadcast

            if fight_date:
                current_date = fight_date
            if fight_location:
                current_location = fight_location
            if fight_time:
                current_time = fight_time
            if fight_broadcast:
                current_broadcast = fight_broadcast

            fights.append({
                'fighter1': fighter1,
                'fighter2': fighter2,
                'title': f"{fighter1} vs {fighter2}",
                'date_raw': final_date or "TBD",
                'location': final_location or "",
                'time': final_time or "",
                'broadcast': final_broadcast or "",
                'is_main_event': is_main_event
            })

        i += 1

    return fights


def scrape_fight_detail(page, url: str) -> Fight | None:
    """Scrape details from an individual fight page."""
    try:
        page.goto(url, timeout=DETAIL_PAGE_TIMEOUT_MS)
        page.wait_for_timeout(POST_CLICK_WAIT_MS)

        body = page.inner_text('body')
        lines = [l.strip() for l in body.split('\n') if l.strip()]

        fighter1 = None
        fighter2 = None
        fight_date = None
        location = None
        time_str = None
        broadcast = None

        for i, line in enumerate(lines):
            if line.upper() == 'VS' and i > 0 and i < len(lines) - 1:
                potential_f1 = lines[i - 1]
                potential_f2 = lines[i + 1]
                if (len(potential_f1) >= MIN_FIGHTER_NAME_LENGTH and
                    len(potential_f2) >= MIN_FIGHTER_NAME_LENGTH and
                    'CHAMPION' not in potential_f1.upper() and
                    'CHAMPION' not in potential_f2.upper() and
                    not potential_f1.isdigit() and not potential_f2.isdigit()):
                    fighter1 = potential_f1
                    fighter2 = potential_f2

            long_match = LONG_DATE_PATTERN.search(line)
            if long_match and not fight_date:
                day_name = LONG_TO_SHORT_DAY.get(long_match.group(1), long_match.group(1)[:3])
                month = LONG_TO_SHORT_MONTH.get(long_match.group(2), long_match.group(2)[:3])
                fight_date = f"{day_name}, {month} {long_match.group(3)} {long_match.group(4)}"

            short_match = DATE_PATTERN.search(line)
            if short_match and not fight_date:
                fight_date = short_match.group(0)

            if 'GMT' in line.upper() and not time_str:
                gmt_match = GMT_PATTERN.search(line)
                if gmt_match:
                    time_str = gmt_match.group(1) + " GMT"

            time_match = TIME_ONLY_PATTERN.search(line)
            if time_match and not time_str:
                time_str = time_match.group(1)

            if (',' in line and len(line) > 10 and len(line) < 100 and
                not DATE_PATTERN.search(line) and not LONG_DATE_PATTERN.search(line) and
                not line.startswith('|') and any(c.isalpha() for c in line)):
                if any(x in line.upper() for x in [', US', ', UK', ', GB', ', AU', ', JP', ', PR', ', MX', ', DE',
                       'ARENA', 'CENTER', 'CENTRE', 'STADIUM', 'HALL', 'THEATER', 'THEATRE', 'CASINO', 'GARDEN', 'LIVE']):
                    if not location:
                        location = line

            if line.upper().startswith('LIVE ON ') or line.upper().startswith('LIVE AND '):
                broadcast = line

        if fighter1 and fighter2:
            return {
                'fighter1': fighter1,
                'fighter2': fighter2,
                'title': f"{fighter1} vs {fighter2}",
                'date_raw': fight_date or "TBD",
                'location': location or "",
                'time': time_str or "",
                'broadcast': broadcast or "",
                'is_main_event': False
            }

    except Exception as e:
        print(f"  Error scraping {url}: {e}")

    return None


def normalize_key(date: str | None, location: str | None) -> tuple[str, str]:
    """Create a normalized key for grouping fights into cards."""
    loc_key = location.lower().strip() if location else ""
    loc_key = re.sub(r'\s*,\s*(us|uk|gb|au|jp|pr|mx|de|dk)$', '', loc_key, flags=re.IGNORECASE)
    return (date or "TBD", loc_key)


def normalize_fighter_name(name: str) -> str:
    """Normalize a fighter name for comparison."""
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    return name


def fighters_match(fight1: Fight, fight2: Fight) -> bool:
    """Check if two fights are the same based on fighter names."""
    f1_a = normalize_fighter_name(fight1['fighter1'])
    f1_b = normalize_fighter_name(fight1['fighter2'])
    f2_a = normalize_fighter_name(fight2['fighter1'])
    f2_b = normalize_fighter_name(fight2['fighter2'])

    def names_match(n1: str, n2: str) -> bool:
        if n1 == n2:
            return True
        if n1 in n2 or n2 in n1:
            return True
        parts1 = n1.split()
        parts2 = n2.split()
        if parts1 and parts2 and parts1[-1] == parts2[-1]:
            return True
        return False

    match1 = names_match(f1_a, f2_a) and names_match(f1_b, f2_b)
    match2 = names_match(f1_a, f2_b) and names_match(f1_b, f2_a)

    return match1 or match2


def run() -> list[Card]:
    """
    Scrape upcoming boxing fights and group them into cards.
    Returns a list of card dictionaries with main event and undercards.
    """
    all_fights: list[Fight] = []
    seen_slugs: set[str] = set()
    main_page_fights: dict[str, Fight] = {}

    with sync_playwright() as p:
        print("--- LAUNCHING BROWSER ---")
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
        )
        page = browser.new_page()

        try:
            print("Loading main schedule page...")
            page.goto("https://ringmagazine.com/en/schedule/fights", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(INITIAL_LOAD_WAIT_MS)

            for i in range(LOAD_MORE_CLICKS):
                try:
                    btn = page.locator('text=Load More')
                    if btn.count() > 0 and btn.first.is_visible():
                        print(f"Clicking Load More ({i+1})...")
                        btn.first.click()
                        page.wait_for_timeout(POST_CLICK_WAIT_MS)
                    else:
                        break
                except:
                    pass

            print("\nScraping main page for featured events...")
            main_fights = scrape_main_page_fights(page)
            for fight in main_fights:
                title_key = fight['title'].upper()
                main_page_fights[title_key] = fight
                all_fights.append(fight)
                print(f"  {'[MAIN]' if fight['is_main_event'] else '[card]'} {fight['title']} - {fight['date_raw']}")

            html = page.content()
            fight_urls = re.findall(r'/en/schedule/fights/([a-z0-9-]+)', html)
            unique_slugs = sorted(set(fight_urls))

            print(f"\nFound {len(unique_slugs)} fight URLs, scraping details...")

            for slug in unique_slugs:
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                url = f"https://ringmagazine.com/en/schedule/fights/{slug}"
                print(f"  Scraping: {slug}...")

                fight = scrape_fight_detail(page, url)
                if fight:
                    found_match = False
                    for existing in all_fights:
                        if fighters_match(fight, existing):
                            if not existing['location'] and fight['location']:
                                existing['location'] = fight['location']
                            if not existing['time'] and fight['time']:
                                existing['time'] = fight['time']
                            if not existing['broadcast'] and fight['broadcast']:
                                existing['broadcast'] = fight['broadcast']
                            found_match = True
                            break

                    if not found_match:
                        all_fights.append(fight)
                    print(f"    Found: {fight['title']} - {fight['date_raw']}")

        except Exception as e:
            print(f"Browser Error: {e}")
            import traceback
            traceback.print_exc()

        browser.close()

    print("\nGrouping fights into cards...")
    cards: dict[tuple[str, str], Card] = {}

    for fight in all_fights:
        key = normalize_key(fight['date_raw'], fight['location'])
        if key not in cards:
            cards[key] = {
                'main_event': None,
                'undercards': [],
                'date_raw': fight['date_raw'],
                'location': fight['location'],
                'time': fight['time'],
                'broadcast': fight['broadcast']
            }

        card = cards[key]

        if not card['location'] and fight['location']:
            card['location'] = fight['location']
        if not card['time'] and fight['time']:
            card['time'] = fight['time']
        if not card['broadcast'] and fight['broadcast']:
            card['broadcast'] = fight['broadcast']

        if fight['is_main_event']:
            card['main_event'] = fight
        else:
            if card['main_event'] and fighters_match(fight, card['main_event']):
                continue
            is_duplicate = False
            for uc in card['undercards']:
                if fighters_match(fight, uc):
                    is_duplicate = True
                    break
            if not is_duplicate:
                card['undercards'].append(fight)

    final_cards: list[Card] = []
    for key, card in cards.items():
        if not card['main_event'] and card['undercards']:
            card['main_event'] = card['undercards'].pop()

        if card['main_event']:
            card['undercards'] = [
                uc for uc in card['undercards']
                if not fighters_match(uc, card['main_event'])
            ]
            final_cards.append(card)

    print(f"Created {len(final_cards)} cards from {len(all_fights)} fights")
    return final_cards


def create_calendar(cards: list[Card]) -> Calendar:
    """
    Create an iCalendar file from the list of cards.
    Each card becomes one event with main event and undercards.
    """
    cal = Calendar()
    cal.add('prodid', '-//Boxing Schedule//github-action//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'Boxing Schedule')

    for card in cards:
        try:
            main = card['main_event']
            undercards = card['undercards']

            main_title = main['title'].upper()
            if undercards:
                undercard_titles = [f['title'] for f in undercards]
                title = f"{main_title}: {', '.join(undercard_titles)}"
            else:
                title = main_title

            event = Event()
            event.add('summary', f"\U0001F94A {title}")

            dt = datetime.now()
            try:
                date_str = card['date_raw']
                if date_str and date_str != "TBD":
                    date_str = re.sub(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s*', '', date_str)
                    dt = datetime.strptime(date_str, "%b %d %Y")
            except Exception as e:
                print(f"  Date parse error for '{card['date_raw']}': {e}")

            hour, minute = 20, 0
            try:
                if card.get('time'):
                    time_str = card['time']
                    if 'AM' in time_str.upper() or 'PM' in time_str.upper():
                        time_match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str, re.IGNORECASE)
                        if time_match:
                            hour = int(time_match.group(1))
                            minute = int(time_match.group(2))
                            if time_match.group(3).upper() == 'PM' and hour != 12:
                                hour += 12
                            elif time_match.group(3).upper() == 'AM' and hour == 12:
                                hour = 0
                    elif 'GMT' in time_str.upper():
                        time_match = re.match(r'(\d{1,2}):(\d{2})', time_str)
                        if time_match:
                            hour = int(time_match.group(1))
                            minute = int(time_match.group(2))
            except:
                pass

            dt = dt.replace(hour=hour, minute=minute, second=0, tzinfo=timezone.utc)

            event.add('dtstart', dt)
            event.add('dtend', dt + timedelta(hours=4))

            description_parts = [f"Main Event: {main['title'].upper()}"]
            if undercards:
                description_parts.append("")
                description_parts.append("Undercard:")
                for uc in undercards:
                    description_parts.append(f"  \u2022 {uc['title']}")
            description_parts.append("")
            if card.get('location'):
                description_parts.append(f"Location: {card['location']}")
            if card.get('broadcast'):
                description_parts.append(f"Broadcast: {card['broadcast']}")
            if card.get('time'):
                description_parts.append(f"Time: {card['time']}")

            event.add('description', '\n'.join(description_parts))

            if card.get('location'):
                event.add('location', card['location'])

            uid_base = re.sub(r'[^a-zA-Z0-9]', '', main['title'])
            uid = f"{uid_base}{dt.strftime('%Y%m%d')}@boxingbot"
            event.add('uid', uid)

            cal.add_component(event)

        except Exception as e:
            print(f"  Error creating event: {e}")
            continue

    return cal


if __name__ == "__main__":
    cards = run()
    print(f"\n--- FOUND {len(cards)} CARDS ---")

    if len(cards) > 0:
        cal = create_calendar(cards)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("SUCCESS: boxing_schedule.ics created")

        print("\nCards in calendar:")
        for card in cards:
            main = card['main_event']
            uc_count = len(card['undercards'])
            print(f"  - {main['title'].upper()} ({card['date_raw']}) + {uc_count} undercard(s)")
    else:
        print("FAILURE: No cards found. The website structure may have changed.")
        sys.exit(1)
