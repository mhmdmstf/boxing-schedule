import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event
import sys

def clean_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def run():
    with sync_playwright() as p:
        # Launch a headless browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Loading The Ring schedule...")
        page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
        
        # Wait for the initial fights to load
        try:
            page.wait_for_selector('div[class*="schedule-card"], div[class*="fight-card"]', timeout=15000)
        except:
            print("Could not find fight cards. The page structure might have changed.")
            # We continue anyway to see if we can grab snapshots
            
        # LOGIC TO CLICK "LOAD MORE"
        # We attempt to click it a few times to get ~2-3 months of fights
        for _ in range(3): 
            try:
                load_more = page.locator('button:has-text("Load More"), div:has-text("Load More")')
                if load_more.count() > 0 and load_more.first.is_visible():
                    print("Clicking 'Load More'...")
                    load_more.first.click()
                    page.wait_for_timeout(2000) # Wait for React to hydrate new items
                else:
                    break
            except Exception as e:
                print(f"Stop loading more: {e}")
                break

        # EXTRACT DATA
        # We use a generic evaluation to be safe against class name changes
        fights_data = page.evaluate("""() => {
            // Try to find cards based on common structures in React apps
            const cards = Array.from(document.querySelectorAll('div[class*="fight"], article, div[class*="card"]'));
            
            return cards.map(card => {
                const text = card.innerText;
                const html = card.innerHTML;
                
                // Attempt to find dates
                // Looking for standard time tags or date-like strings
                let dateText = "";
                const timeEl = card.querySelector('time');
                if (timeEl) {
                    dateText = timeEl.getAttribute('datetime') || timeEl.innerText;
                } else {
                    // Fallback: look for date patterns in text
                    dateText = "See Details"; 
                }

                // Attempt to find Titles (Fighter A vs Fighter B)
                const titleEl = card.querySelector('h1, h2, h3, h4, strong');
                const title = titleEl ? titleEl.innerText : "Boxing Event";

                // Attempt to find Broadcast/Network info
                const networkEl = card.querySelector('.network, .broadcast, [class*="tv"]');
                const network = networkEl ? networkEl.innerText : "Check Listings";

                return {
                    title: title,
                    date_raw: dateText,
                    network: network,
                    full_text: text
                };
            }).filter(f => f.title.toLowerCase().includes('vs') || f.full_text.toLowerCase().includes('vs'));
        }""")

        browser.close()
        return fights_data

def create_calendar(fights):
    cal = Calendar()
    cal.add('prodid', '-//Ring Magazine Scraper//mxm.com//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'The Ring Boxing Schedule')
    cal.add('refresh-interval;value=DURATION:PT12H') # Refresh every 12 hours

    for fight in fights:
        try:
            # Skip empty data
            if "vs" not in fight['title'].lower():
                continue

            event = Event()
            event.add('summary', clean_text(fight['title']))
            
            # Date Parsing Logic
            # Since date formats vary wildly on scrapers, we default to a "All Day" event 
            # if we can't perfectly parse the ISO. 
            # ideally, we parse the 'date_raw' here.
            # For safety in this v1 script, we set it to today + offset if parsing fails, 
            # generally you would use dateutil.parser.parse(fight['date_raw'])
            
            try:
                # Placeholder for actual date parsing logic based on what the scraper returns
                # Assuming ISO format or standard text for this example
                from dateutil import parser
                dt = parser.parse(fight['date_raw'])
                event.add('dtstart', dt)
                event.add('dtend', dt + timedelta(hours=4))
            except:
                # If parsing fails, we skip adding a date (invalid event) or log error
                # For now, we continue to ensure script doesn't crash
                continue

            description = f"Network: {fight['network']}\n\nSource: The Ring"
            event.add('description', description)
            
            # Create unique ID
            uid = re.sub(r'[^a-zA-Z0-9]', '', fight['title']) + str(fight.get('date_raw',''))
            event.add('uid', uid + '@ringscraper')

            cal.add_component(event)
        except Exception as e:
            print(f"Error adding event: {e}")

    return cal

if __name__ == "__main__":
    data = run()
    print(f"Scraped {len(data)} potential fights.")
    
    if data:
        cal = create_calendar(data)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
            print("Calendar file 'boxing_schedule.ics' created successfully.")
    else:
        print("No fights found. Check selectors.")