import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

def run():
    fights_data = []
    
    with sync_playwright() as p:
        # 1. STEALTH BROWSER SETUP
        print("Launching Stealth Browser...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
            ]
        )
        page = browser.new_page()
        
        # Hook up browser console logs to our terminal (Crucial for debugging)
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))

        print("Loading The Ring schedule...")
        try:
            page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
            page.wait_for_timeout(5000) 
        except Exception as e:
            print(f"Page load warning: {e}")

        # 2. CLICK LOAD MORE
        print("Expanding schedule...")
        for i in range(3): 
            try:
                load_more = page.locator('button:has-text("Load More"), a:has-text("Load More"), .load-more')
                if load_more.count() > 0 and load_more.first.is_visible():
                    load_more.first.click()
                    page.wait_for_timeout(2000)
                else:
                    break
            except:
                break

        # 3. EXTRACT DATA (Running inside the browser)
        print("Extracting fight data...")
        fights_data = page.evaluate("""() => {
            const fights = [];
            
            // Strategy A: Look for the specific "schedule-row" class (The Ring's standard)
            let rows = Array.from(document.querySelectorAll('.schedule-row, .fight-row, tr.fight'));
            
            console.log('Found ' + rows.length + ' rows using Strategy A (Class Name)');

            // Strategy B: If A failed, find ANY element containing " vs "
            if (rows.length === 0) {
                console.log('Switching to Strategy B (Text Search)...');
                const allDivs = document.querySelectorAll('div, article');
                rows = Array.from(allDivs).filter(el => 
                    el.innerText.includes(' vs ') && 
                    el.innerText.length < 200 && 
                    el.children.length < 5
                );
            }

            rows.forEach(row => {
                const text = row.innerText;
                
                // PARSE DATE
                // Look for a date-like structure (e.g., "Nov 22" or class="date")
                let dateText = '';
                const dateEl = row.querySelector('[class*="date"], time');
                if (dateEl) {
                    dateText = dateEl.innerText;
                } else {
                    // Regex hunt for date
                    const dateMatch = text.match(/([A-Z][a-z]{2,8}\\s\\d{1,2})/);
                    if (dateMatch) dateText = dateMatch[0];
                }

                // PARSE TITLE (Fighters)
                let titleText = '';
                const titleEl = row.querySelector('[class*="fighter"], [class*="matchup"], h2, h3');
                if (titleEl) {
                    titleText = titleEl.innerText;
                } else {
                    // Fallback: grab the line with "vs"
                    const lines = text.split('\\n');
                    titleText = lines.find(l => l.includes('vs')) || '';
                }

                // PARSE NETWORK
                let netText = 'TBA';
                const netEl = row.querySelector('[class*="network"], [class*="broadcaster"]');
                if (netEl) {
                    const img = netEl.querySelector('img');
                    netText = img ? (img.alt || 'TV') : netEl.innerText;
                }

                if (titleText && titleText.includes('vs')) {
                    fights.push({
                        date_raw: dateText.trim(),
                        title: titleText.trim(),
                        network: netText.trim(),
                        location: "Check Details"
                    });
                }
            });
            
            return fights;
        }""")

        browser.close()
    
    return fights_data

def parse_date(date_str):
    """Robust date parser handling multiple formats"""
    try:
        # Remove day names (Saturday, Mon, etc)
        clean = re.sub(r'(?i)(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*', '', date_str).strip()
        clean = re.sub(r'\s+', ' ', clean) # Remove extra spaces
        
        now = datetime.now()
        current_year = now.year
        
        # Try formats like "November 22" or "Nov 22"
        for fmt in ["%B %d", "%b %d", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(clean, fmt)
                # If format didn't have year, add it
                if dt.year == 1900:
                    dt = dt.replace(year=current_year)
                    # If date is way in the past, assume next year
                    if dt < now - timedelta(days=60):
                        dt = dt.replace(year=current_year + 1)
                return dt.replace(hour=20, minute=0)
            except:
                continue
                
        return now # Fail safe
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
            summary = fight['title'].replace('\n', ' ').replace('  ', ' ')
            event.add('summary', f"🥊 {summary}")
            
            start = parse_date(fight['date_raw'])
            event.add('dtstart', start)
            event.add('dtend', start + timedelta(hours=4))
            event.add('location', fight['location'])
            
            desc = f"Network: {fight['network']}\n"
            desc += f"Date Info: {fight['date_raw']}\n"
            desc += "Source: The Ring Magazine"
            event.add('description', desc)
            
            uid = re.sub(r'[^a-zA-Z0-9]', '', summary[:15] + str(start.strftime('%Y%m%d')))
            event.add('uid', uid + "@boxingcal")
            
            cal.add_component(event)
        except Exception as e:
            print(f"Skipping event: {e}")
            pass
    return cal

if __name__ == "__main__":
    print("--- STARTING SCRAPER ---")
    data = run()
    print(f"--- SCRAPED {len(data)} FIGHTS ---")
    
    if len(data) > 0:
        cal = create_ics(data)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("SUCCESS: 'boxing_schedule.ics' created.")
    else:
        print("FAILURE: No fights found. Check BROWSER LOGS above.")