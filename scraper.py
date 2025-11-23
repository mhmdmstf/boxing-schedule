import re
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event


def scrape_main_page_fights(page):
    """
    Scrape fights from the main page, preserving casing to identify main events.
    Returns list of fights with is_main_event flag and context info.
    """
    fights = []

    body = page.inner_text('body')
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    # Patterns
    date_pattern = re.compile(r'(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}')
    time_pattern = re.compile(r'(\d{1,2}:\d{2}\s+(?:AM|PM))\s+(\S+)')
    gmt_pattern = re.compile(r'(\d{1,2}:\d{2})\s+GMT')

    # Track current context
    current_date = None
    current_location = None
    current_time = None
    current_broadcast = None

    i = 0
    while i < len(lines):
        line = lines[i]

        # Update context
        if date_pattern.match(line):
            current_date = line
            i += 1
            continue

        time_match = time_pattern.match(line)
        if time_match:
            current_time = time_match.group(1)
            i += 1
            continue

        gmt_match = gmt_pattern.match(line)
        if gmt_match and not current_time:
            current_time = gmt_match.group(1) + " GMT"
            i += 1
            continue

        if line.startswith('LIVE ON ') or line.startswith('LIVE AND '):
            current_broadcast = line
            i += 1
            continue

        # Look for VS pattern
        if line == 'VS' and i > 0 and i < len(lines) - 1:
            fighter1 = lines[i - 1]
            fighter2 = lines[i + 1]

            # Skip invalid entries
            if (len(fighter1) < 3 or len(fighter2) < 3 or
                'CHAMPION' in fighter1.upper() or 'CHAMPION' in fighter2.upper() or
                fighter1.isdigit() or fighter2.isdigit()):
                i += 1
                continue

            # Check if this is a main event (ALL CAPS)
            is_main_event = fighter1.isupper() and fighter2.isupper()

            # Look ahead for fight-specific details
            fight_location = None
            fight_date = None
            fight_time = None
            fight_broadcast = None

            for j in range(i + 2, min(i + 12, len(lines))):
                scan_line = lines[j]
                if scan_line == 'VS':
                    break
                if date_pattern.match(scan_line):
                    fight_date = scan_line
                time_match = time_pattern.match(scan_line)
                if time_match:
                    fight_time = time_match.group(1)
                gmt_match = gmt_pattern.match(scan_line)
                if gmt_match and not fight_time:
                    fight_time = gmt_match.group(1) + " GMT"
                if scan_line.startswith('LIVE ON ') or scan_line.startswith('LIVE AND '):
                    fight_broadcast = scan_line
                if (',' in scan_line and not scan_line.startswith('|') and
                    not scan_line.isdigit() and not date_pattern.match(scan_line) and
                    len(scan_line) > 5):
                    fight_location = scan_line

            # Use fight-specific or context
            final_date = fight_date or current_date
            final_location = fight_location or current_location
            final_time = fight_time or current_time
            final_broadcast = fight_broadcast or current_broadcast

            # Update context for undercards
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


def scrape_fight_detail(page, url):
    """
    Scrape details from an individual fight page.
    """
    try:
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2000)

        body = page.inner_text('body')
        lines = [l.strip() for l in body.split('\n') if l.strip()]

        fighter1 = None
        fighter2 = None
        fight_date = None
        location = None
        time_str = None
        broadcast = None

        short_date_pattern = re.compile(r'(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{4})')
        long_date_pattern = re.compile(r'(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})')
        time_pattern = re.compile(r'(\d{1,2}:\d{2}\s*(?:AM|PM))', re.IGNORECASE)
        gmt_pattern = re.compile(r'(\d{1,2}:\d{2})\s*GMT', re.IGNORECASE)

        for i, line in enumerate(lines):
            if line.upper() == 'VS' and i > 0 and i < len(lines) - 1:
                potential_f1 = lines[i - 1]
                potential_f2 = lines[i + 1]
                if (len(potential_f1) >= 3 and len(potential_f2) >= 3 and
                    'CHAMPION' not in potential_f1.upper() and
                    'CHAMPION' not in potential_f2.upper() and
                    not potential_f1.isdigit() and not potential_f2.isdigit()):
                    fighter1 = potential_f1
                    fighter2 = potential_f2

            long_match = long_date_pattern.search(line)
            if long_match and not fight_date:
                month_map = {'January': 'Jan', 'February': 'Feb', 'March': 'Mar', 'April': 'Apr',
                             'May': 'May', 'June': 'Jun', 'July': 'Jul', 'August': 'Aug',
                             'September': 'Sep', 'October': 'Oct', 'November': 'Nov', 'December': 'Dec'}
                day_map = {'Sunday': 'Sun', 'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
                           'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat'}
                day_name = day_map.get(long_match.group(1), long_match.group(1)[:3])
                month = month_map.get(long_match.group(2), long_match.group(2)[:3])
                fight_date = f"{day_name}, {month} {long_match.group(3)} {long_match.group(4)}"

            short_match = short_date_pattern.search(line)
            if short_match and not fight_date:
                fight_date = short_match.group(0)

            if 'GMT' in line.upper() and not time_str:
                gmt_match = gmt_pattern.search(line)
                if gmt_match:
                    time_str = gmt_match.group(1) + " GMT"

            time_match = time_pattern.search(line)
            if time_match and not time_str:
                time_str = time_match.group(1)

            if (',' in line and len(line) > 10 and len(line) < 100 and
                not short_date_pattern.search(line) and not long_date_pattern.search(line) and
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
                'is_main_event': False  # Individual pages don't preserve casing
            }

    except Exception as e:
        print(f"  Error scraping {url}: {e}")

    return None


def normalize_key(date, location):
    """Create a normalized key for grouping fights into cards."""
    # Normalize location - extract city/venue name
    loc_key = location.lower().strip() if location else ""
    # Remove common suffixes for matching
    loc_key = re.sub(r'\s*,\s*(us|uk|gb|au|jp|pr|mx|de|dk)$', '', loc_key, flags=re.IGNORECASE)
    return (date or "TBD", loc_key)


def normalize_fighter_name(name):
    """Normalize a fighter name for comparison."""
    # Lowercase, remove extra spaces, remove common suffixes/prefixes
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    return name


def fighters_match(fight1, fight2):
    """Check if two fights are the same based on fighter names."""
    f1_a = normalize_fighter_name(fight1['fighter1'])
    f1_b = normalize_fighter_name(fight1['fighter2'])
    f2_a = normalize_fighter_name(fight2['fighter1'])
    f2_b = normalize_fighter_name(fight2['fighter2'])

    # Check if fighters match (in either order)
    # Also check if one name contains the other (e.g., "Erika Cruz" vs "Cruz")
    def names_match(n1, n2):
        if n1 == n2:
            return True
        # Check if one contains the other (for partial names like "Cruz" vs "Erika Cruz")
        if n1 in n2 or n2 in n1:
            return True
        # Check last name match
        parts1 = n1.split()
        parts2 = n2.split()
        if parts1 and parts2 and parts1[-1] == parts2[-1]:
            return True
        return False

    # Check both orderings
    match1 = names_match(f1_a, f2_a) and names_match(f1_b, f2_b)
    match2 = names_match(f1_a, f2_b) and names_match(f1_b, f2_a)

    return match1 or match2


def run():
    """
    Scrape upcoming boxing fights and group them into cards.
    Returns a list of card dictionaries with main event and undercards.
    """
    all_fights = []
    seen_slugs = set()
    main_page_fights = {}  # Track fights from main page by normalized title

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
            page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
            page.wait_for_timeout(5000)

            # Click Load More
            for i in range(5):
                try:
                    btn = page.locator('text=Load More')
                    if btn.count() > 0 and btn.first.is_visible():
                        print(f"Clicking Load More ({i+1})...")
                        btn.first.click()
                        page.wait_for_timeout(2000)
                    else:
                        break
                except:
                    pass

            # First pass: get fights from main page (has casing info)
            print("\nScraping main page for featured events...")
            main_fights = scrape_main_page_fights(page)
            for fight in main_fights:
                title_key = fight['title'].upper()
                main_page_fights[title_key] = fight
                all_fights.append(fight)
                print(f"  {'[MAIN]' if fight['is_main_event'] else '[card]'} {fight['title']} - {fight['date_raw']}")

            # Get all fight URLs from page
            html = page.content()
            fight_urls = re.findall(r'/en/schedule/fights/([a-z0-9-]+)', html)
            unique_slugs = sorted(set(fight_urls))

            print(f"\nFound {len(unique_slugs)} fight URLs, scraping details...")

            # Second pass: visit each fight page for details
            for slug in unique_slugs:
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                url = f"https://ringmagazine.com/en/schedule/fights/{slug}"
                print(f"  Scraping: {slug}...")

                fight = scrape_fight_detail(page, url)
                if fight:
                    # Check if we already have this fight (with fuzzy matching)
                    found_match = False
                    for existing in all_fights:
                        if fighters_match(fight, existing):
                            # Update existing with any missing details
                            if not existing['location'] and fight['location']:
                                existing['location'] = fight['location']
                            if not existing['time'] and fight['time']:
                                existing['time'] = fight['time']
                            if not existing['broadcast'] and fight['broadcast']:
                                existing['broadcast'] = fight['broadcast']
                            found_match = True
                            break

                    if not found_match:
                        # New fight not in list
                        all_fights.append(fight)
                    print(f"    Found: {fight['title']} - {fight['date_raw']}")

        except Exception as e:
            print(f"Browser Error: {e}")
            import traceback
            traceback.print_exc()

        browser.close()

    # Group fights into cards by date + location
    print("\nGrouping fights into cards...")
    cards = {}

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

        # Update card details if this fight has better info
        if not card['location'] and fight['location']:
            card['location'] = fight['location']
        if not card['time'] and fight['time']:
            card['time'] = fight['time']
        if not card['broadcast'] and fight['broadcast']:
            card['broadcast'] = fight['broadcast']

        if fight['is_main_event']:
            card['main_event'] = fight
        else:
            # Don't add as undercard if it matches the main event
            if card['main_event'] and fighters_match(fight, card['main_event']):
                continue
            # Don't add if already in undercards
            is_duplicate = False
            for uc in card['undercards']:
                if fighters_match(fight, uc):
                    is_duplicate = True
                    break
            if not is_duplicate:
                card['undercards'].append(fight)

    # Build final card list
    final_cards = []
    for key, card in cards.items():
        # If no main event identified, use the first fight or pick one
        if not card['main_event'] and card['undercards']:
            # Promote first undercard to main event
            card['main_event'] = card['undercards'].pop(0)

        if card['main_event']:
            # Final cleanup: remove any undercards that match the main event
            card['undercards'] = [
                uc for uc in card['undercards']
                if not fighters_match(uc, card['main_event'])
            ]
            final_cards.append(card)

    print(f"Created {len(final_cards)} cards from {len(all_fights)} fights")
    return final_cards


def create_calendar(cards):
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

            # Build title: MAIN EVENT: undercard1, undercard2
            main_title = main['title'].upper()
            if undercards:
                undercard_titles = [f['title'] for f in undercards]
                title = f"{main_title}: {', '.join(undercard_titles)}"
            else:
                title = main_title

            event = Event()
            event.add('summary', f"🥊 {title}")

            # Parse the date
            dt = datetime.now()
            try:
                date_str = card['date_raw']
                if date_str and date_str != "TBD":
                    date_str = re.sub(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s*', '', date_str)
                    dt = datetime.strptime(date_str, "%b %d %Y")
            except Exception as e:
                print(f"  Date parse error for '{card['date_raw']}': {e}")

            # Parse the time
            hour, minute = 20, 0  # Default to 8 PM
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

            dt = dt.replace(hour=hour, minute=minute, second=0)

            event.add('dtstart', dt)
            event.add('dtend', dt + timedelta(hours=4))

            # Build description
            description_parts = [f"Main Event: {main['title'].upper()}"]
            if undercards:
                description_parts.append("")
                description_parts.append("Undercard:")
                for uc in undercards:
                    description_parts.append(f"  • {uc['title']}")
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

            # Create unique UID
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

        # Print summary
        print("\nCards in calendar:")
        for card in cards:
            main = card['main_event']
            uc_count = len(card['undercards'])
            print(f"  - {main['title'].upper()} ({card['date_raw']}) + {uc_count} undercard(s)")
    else:
        print("FAILURE: No cards found. The website structure may have changed.")
        sys.exit(1)
