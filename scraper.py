import re
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

def run():
    """
    Scrape upcoming boxing fights from The Ring Magazine schedule page.
    Returns a list of fight dictionaries with fighter names, dates, locations, and times.
    """
    fights_data = []

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
            print("Loading URL...")
            page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
            page.wait_for_timeout(5000)

            # Click Load More to get more fights
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

            # Get full page text and parse it line by line
            body = page.inner_text('body')
            lines = [l.strip() for l in body.split('\n') if l.strip()]

            print(f"DEBUG: Got {len(lines)} non-empty lines from page")

            # Patterns
            date_pattern = re.compile(r'(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}')
            time_pattern = re.compile(r'(\d{1,2}:\d{2}\s+(?:AM|PM))\s+(\S+)')  # e.g., "2:00 AM Europe/Brussels"
            gmt_pattern = re.compile(r'(\d{1,2}:\d{2})\s+GMT')  # e.g., "01:00 GMT"

            # Track current event context for undercards
            current_date = None
            current_location = None
            current_time = None
            current_broadcast = None

            i = 0
            while i < len(lines):
                line = lines[i]

                # Check for date line
                if date_pattern.match(line):
                    current_date = line
                    i += 1
                    continue

                # Check for time line
                time_match = time_pattern.match(line)
                if time_match:
                    current_time = time_match.group(1)
                    i += 1
                    continue

                # Check for GMT time (use as fallback)
                gmt_match = gmt_pattern.match(line)
                if gmt_match and not current_time:
                    current_time = gmt_match.group(1) + " GMT"
                    i += 1
                    continue

                # Check for broadcast info
                if line.startswith('LIVE ON '):
                    current_broadcast = line
                    i += 1
                    continue

                # Look for VS pattern
                if line == 'VS' and i > 0 and i < len(lines) - 1:
                    fighter1 = lines[i - 1]
                    fighter2 = lines[i + 1]

                    # Skip if fighters look like junk or titles
                    if (len(fighter1) < 3 or len(fighter2) < 3 or
                        'CHAMPION' in fighter1.upper() or 'CHAMPION' in fighter2.upper() or
                        fighter1.isdigit() or fighter2.isdigit()):
                        i += 1
                        continue

                    # Look ahead for fight-specific details
                    fight_location = None
                    fight_date = None
                    fight_time = None
                    fight_broadcast = None

                    # Scan next several lines for this fight's details
                    for j in range(i + 2, min(i + 12, len(lines))):
                        scan_line = lines[j]

                        # Stop if we hit another VS (next fight)
                        if scan_line == 'VS':
                            break

                        # Date
                        if date_pattern.match(scan_line):
                            fight_date = scan_line
                            continue

                        # Time
                        time_match = time_pattern.match(scan_line)
                        if time_match:
                            fight_time = time_match.group(1)
                            continue

                        # GMT time
                        gmt_match = gmt_pattern.match(scan_line)
                        if gmt_match:
                            if not fight_time:
                                fight_time = gmt_match.group(1) + " GMT"
                            continue

                        # Broadcast
                        if scan_line.startswith('LIVE ON '):
                            fight_broadcast = scan_line
                            continue

                        # Location (contains comma, not a number, not special keywords)
                        if (',' in scan_line and
                            not scan_line.startswith('|') and
                            not scan_line.isdigit() and
                            not date_pattern.match(scan_line) and
                            len(scan_line) > 5):
                            fight_location = scan_line

                    # Use fight-specific details or fall back to current context
                    final_date = fight_date or current_date
                    final_location = fight_location or current_location
                    final_time = fight_time or current_time
                    final_broadcast = fight_broadcast or current_broadcast

                    # Update context if we found new details (for undercards)
                    if fight_date:
                        current_date = fight_date
                    if fight_location:
                        current_location = fight_location
                    if fight_time:
                        current_time = fight_time
                    if fight_broadcast:
                        current_broadcast = fight_broadcast

                    # Create fight entry
                    fights_data.append({
                        'fighter1': fighter1,
                        'fighter2': fighter2,
                        'title': f"{fighter1} vs {fighter2}",
                        'date_raw': final_date or "TBD",
                        'location': final_location or "",
                        'time': final_time or "",
                        'broadcast': final_broadcast or ""
                    })

                    print(f"  Found: {fighter1} vs {fighter2} - {final_date}")

                i += 1

        except Exception as e:
            print(f"Browser Error: {e}")
            import traceback
            traceback.print_exc()

        browser.close()

    return fights_data


def create_calendar(fights):
    """
    Create an iCalendar file from the list of fights.
    """
    cal = Calendar()
    cal.add('prodid', '-//Boxing Schedule//github-action//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'Boxing Schedule')

    for fight in fights:
        try:
            # Skip garbage entries
            if len(fight['title']) < 5:
                continue

            event = Event()
            event.add('summary', f"🥊 {fight['title']}")

            # Parse the date
            dt = datetime.now()
            try:
                # Expected format: "Sun, Dec 07 2025"
                date_str = fight['date_raw']
                if date_str and date_str != "TBD":
                    # Remove the day name prefix
                    date_str = re.sub(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),\s*', '', date_str)
                    dt = datetime.strptime(date_str, "%b %d %Y")
            except Exception as e:
                print(f"  Date parse error for '{fight['date_raw']}': {e}")
                # Keep default (today) if parsing fails

            # Parse the time if available
            hour, minute = 20, 0  # Default to 8 PM
            try:
                if fight.get('time'):
                    time_str = fight['time']
                    # Handle "2:00 AM" or "01:00 GMT" formats
                    if 'AM' in time_str or 'PM' in time_str:
                        time_match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str)
                        if time_match:
                            hour = int(time_match.group(1))
                            minute = int(time_match.group(2))
                            if time_match.group(3) == 'PM' and hour != 12:
                                hour += 12
                            elif time_match.group(3) == 'AM' and hour == 12:
                                hour = 0
                    elif 'GMT' in time_str:
                        time_match = re.match(r'(\d{1,2}):(\d{2})', time_str)
                        if time_match:
                            hour = int(time_match.group(1))
                            minute = int(time_match.group(2))
            except:
                pass  # Keep default time

            dt = dt.replace(hour=hour, minute=minute, second=0)

            event.add('dtstart', dt)
            event.add('dtend', dt + timedelta(hours=4))

            # Build description
            description_parts = [f"Matchup: {fight['title']}"]
            if fight.get('location'):
                description_parts.append(f"Location: {fight['location']}")
            if fight.get('broadcast'):
                description_parts.append(f"Broadcast: {fight['broadcast']}")
            if fight.get('time'):
                description_parts.append(f"Time: {fight['time']}")

            event.add('description', '\n'.join(description_parts))

            # Add location if available
            if fight.get('location'):
                event.add('location', fight['location'])

            # Create unique UID using fighters and date
            uid_base = re.sub(r'[^a-zA-Z0-9]', '', fight['title'])
            uid = f"{uid_base}{dt.strftime('%Y%m%d')}@boxingbot"
            event.add('uid', uid)

            cal.add_component(event)

        except Exception as e:
            print(f"  Error creating event for {fight.get('title', 'unknown')}: {e}")
            continue

    return cal


if __name__ == "__main__":
    data = run()
    print(f"\n--- FOUND {len(data)} FIGHTS ---")

    if len(data) > 0:
        cal = create_calendar(data)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("SUCCESS: boxing_schedule.ics created")

        # Print summary
        print("\nFights in calendar:")
        for fight in data:
            print(f"  - {fight['title']} ({fight['date_raw']})")
    else:
        print("FAILURE: No fights found. The website structure may have changed.")
        sys.exit(1)
