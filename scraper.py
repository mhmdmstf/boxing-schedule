import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

def run():
    fights_data = []
    
    with sync_playwright() as p:
        # STEALTH MODE: Arguments to hide that we are a bot
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
            ]
        )
        page = browser.new_page()
        
        print("Loading The Ring schedule...")
        try:
            page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
            page.wait_for_timeout(5000) # Wait 5 seconds for initial load
        except Exception as e:
            print(f"Error loading page: {e}")

        # DEBUG: Check what the bot actually sees
        page_title = page.title()
        print(f"DEBUG: Page Title is '{page_title}'")
        
        if "Cloudflare" in page_title or "Just a moment" in page_title:
            print("BLOCKED: The site blocked the scraper.")
            browser.close()
            return []

        # CLICK LOAD MORE
        print("Checking for 'Load More' buttons...")
        for _ in range(3): 
            try:
                # Try multiple button styles
                load_more = page.locator('button:has-text("Load More"), a:has-text("Load More"), span:has-text("Load More")')
                if load_more.count() > 0 and load_more.first.is_visible():
                    print("Clicking 'Load More'...")
                    load_more.first.click()
                    page.wait_for_timeout(3000)
                else:
                    break
            except:
                break

        # SCRAPING
        print("Extracting fight data...")
        fights_data = page.evaluate("""() => {
            const fights = [];
            // Grab ALL table rows or card-like divs
            const rows = document.querySelectorAll('tr, .schedule-row, .fight-row, div[class*="row"]');
            
            rows.forEach(row => {
                const text = row.innerText;
                // Basic validation: A fight row usually has a date and 'vs' or fighter names
                if (text.length < 10) return;

                // 1. Try to find date
                // Look for element with class 'date' or first cell
                let dateEl = row.querySelector('[class*="date"], td:first-child');
                let dateText = dateEl ? dateEl.innerText.trim() : '';

                // 2. Try to find fighters
                // Look for element with 'vs' or class 'fighters'
                let fightEl = row.querySelector('[class*="fight"], [class*="event"], td:nth-child(2)');
                let fightText = fightEl ? fightEl.innerText.trim() : '';
                
                // Fallback: if we can't find specific elements, try to parse the raw text
                if (!fightText && text.includes('vs')) {
                     fightText = text.split('\\n')[0]; // Take the first line
                }

                // 3. Network/Location (Optional)
                let locEl = row.querySelector('[class*="venue"], [class*="loc"], td:nth-child(3)');
                let netEl = row.querySelector('[class*="net"], [class*="broad"], td:nth-child(4)');
                
                // Network logo check
                let netText = '';
                if (netEl) {
                    const img = netEl.querySelector('img');
                    netText = img ? img.alt : netEl.innerText;
                }

                if (fightText && dateText) {
                    fights.push({
                        date_raw: dateText,
                        title: fightText,
                        location: locEl ? locEl.innerText.trim() : '',
                        network: netText.trim()
                    });
                }
            });
            return fights;
        }""")

        browser.close()
    
    return fights_data

def parse_date(date_str):
    # Simple parser for "Saturday, November 22" format
    try:
        # Clean up
        clean = re.sub(r'^[A-Za-z]+,\s*', '', date_str).strip()
        now = datetime.now()
        try:
            dt = datetime.strptime(f"{clean} {now.year}", "%B %d %Y")
            if dt < now - timedelta(days=60):
                dt = dt.replace(year=now.year + 1)
        except:
            dt = now
        return dt.replace(hour=20, minute=0) # Default 8 PM
    except:
        return datetime.now()

def create_ics(fights):
    cal = Calendar()
    cal.add('prodid', '-//Boxing Schedule//ringscraper//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'The Ring Boxing Schedule')

    for fight in fights:
        try:
            event = Event()
            summary = fight['title'].replace('\n', ' vs ')
            event.add('summary', f"🥊 {summary}")
            
            start = parse_date(fight['date_raw'])
            event.add('dtstart', start)
            event.add('dtend', start + timedelta(hours=4))
            event.add('location', fight['location'])
            event.add('description', f"Network: {fight['network']}\n\n{summary}")
            
            uid = re.sub(r'[^a-zA-Z0-9]', '', summary[:15] + str(start.year))
            event.add('uid', uid + "@boxingcal")
            
            cal.add_component(event)
        except:
            pass
    return cal

if __name__ == "__main__":
    data = run()
    print(f"Scraped {len(data)} fights.")
    
    if len(data) > 0:
        cal = create_ics(data)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("File created successfully.")
    else:
        # If we get here, check the DEBUG log above to see if we were blocked
        print("No fights found. Please check the 'DEBUG: Page Title' log above.")