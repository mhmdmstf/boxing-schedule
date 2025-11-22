import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event
import sys

def run():
    fights_data = []
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Loading The Ring schedule...")
        # We use a generous timeout because the site can be slow
        page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
        
        # Wait for the specific fight rows to load
        try:
            page.wait_for_selector('.schedule-row, .fight-row', timeout=20000)
        except:
            print("Warning: Page took too long or selector changed.")

        # CLICK LOAD MORE: Attempt to load 3 months of fights
        print("Checking for 'Load More' buttons...")
        for _ in range(4): 
            try:
                # The Ring specific load more button usually looks like this
                load_more = page.locator('a.load-more, button.load-more, span:has-text("Load More")')
                if load_more.count() > 0 and load_more.first.is_visible():
                    load_more.first.click()
                    page.wait_for_timeout(2500) # Wait for data to fill
                else:
                    break
            except:
                break

        # PRECISION SCRAPING
        # We pull the data directly from The Ring's specific CSS classes
        print("Extracting fight data...")
        fights_data = page.evaluate("""() => {
            const fights = [];
            # The Ring uses rows for schedule items
            const rows = document.querySelectorAll('.schedule-row, .fight-row, tr');
            
            rows.forEach(row => {
                // 1. Get Date
                let dateEl = row.querySelector('.date, .fight-date, td:nth-child(1)');
                let dateText = dateEl ? dateEl.innerText.trim() : '';
                
                // 2. Get Fighters (Matchup)
                let fightEl = row.querySelector('.fighters, .fight-title, .event, td:nth-child(2)');
                let fightText = fightEl ? fightEl.innerText.trim() : '';

                // 3. Get Location
                let locEl = row.querySelector('.location, .venue, td:nth-child(3)');
                let locText = locEl ? locEl.innerText.trim() : '';

                // 4. Get Network/Broadcaster
                let netEl = row.querySelector('.network, .broadcaster, td:nth-child(4)');
                let netText = '';
                if (netEl) {
                    // Sometimes network is an image logo, check alt text
                    const img = netEl.querySelector('img');
                    if (img) {
                        netText = img.getAttribute('alt') || 'Check Listings';
                    } else {
                        netText = netEl.innerText.trim();
                    }
                }

                if (fightText && dateText) {
                    fights.push({
                        date_raw: dateText,
                        title: fightText,
                        location: locText,
                        network: netText
                    });
                }
            });
            return fights;
        }""")

        browser.close()
    
    return fights_data

def parse_ring_date(date_str):
    """
    The Ring usually formats dates like 'Saturday, November 22'
    We need to add the current year (or next year if the month is early)
    """
    try:
        # Remove day names like "Saturday," to just get "November 22"
        clean_date = re.sub(r'^[A-Za-z]+,\s*', '', date_str).strip()
        
        # Helper to try parsing with a year
        def try_parse(d_str, year):
            full_str = f"{d_str} {year}"
            return datetime.strptime(full_str, "%B %d %Y")

        current_year = datetime.now().year
        
        # Try parsing with current year
        try:
            dt = try_parse(clean_date, current_year)
            # If the date is more than 2 months in the past, it's probably for next year
            if dt < datetime.now() - timedelta(days=60):
                dt = try_parse(clean_date, current_year + 1)
        except:
            # Fallback: sometimes they might include the year, try parsing as is
            dt = datetime.now() 

        # Set specific time to 8:00 PM (20:00) as a default for boxing
        return dt.replace(hour=20, minute=0, second=0)
    except:
        return datetime.now()

def create_calendar(fights):
    cal = Calendar()
    cal.add('prodid', '-//Boxing Schedule//ringscraper//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'The Ring Boxing Schedule')
    cal.add('refresh-interval;value=DURATION:PT12H')

    for fight in fights:
        event = Event()
        
        # Clean up title
        summary = fight['title'].replace('\n', ' vs ')
        event.add('summary', f"🥊 {summary}")
        
        # Parse Date
        start_dt = parse_ring_date(fight['date_raw'])
        event.add('dtstart', start_dt)
        event.add('dtend', start_dt + timedelta(hours=4)) # Fight usually lasts ~4 hours
        
        # Location
        event.add('location', fight['location'])
        
        # Description
        desc = f"Network: {fight['network'] or 'TBA'}\n\n"
        desc += f"Matchup: {summary}\n"
        desc += f"Venue: {fight['location']}\n"
        desc += "Source: The Ring Magazine"
        event.add('description', desc)
        
        # Unique ID
        uid = f"{summary[:10].strip()}-{start_dt.strftime('%Y%m%d')}@boxing-cal"
        uid = re.sub(r'[^a-zA-Z0-9\-]', '', uid)
        event.add('uid', uid)

        cal.add_component(event)

    return cal

if __name__ == "__main__":
    print("Starting scraper...")
    data = run()
    print(f"Scraped {len(data)} fights.")
    
    if data:
        cal = create_calendar(data)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("Success! 'boxing_schedule.ics' created.")
    else:
        print("No data found. The site structure might have changed.")