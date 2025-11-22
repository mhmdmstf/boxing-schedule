import re
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event

def run():
    fights_data = []
    
    with sync_playwright() as p:
        print("--- LAUNCHING BROWSER ---")
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            ]
        )
        page = browser.new_page()
        
        try:
            print("Loading URL...")
            page.goto("https://ringmagazine.com/en/schedule/fights", timeout=60000)
            page.wait_for_timeout(5000)
            
            # DEBUG: Print what the bot sees
            page_text = page.inner_text('body')
            print(f"DEBUG: Page loaded. First 300 chars:\n{page_text[:300]}...\n")
            
            if "vs" not in page_text.lower() and "fighter" not in page_text.lower():
                print("CRITICAL: The page seems to lack fight data (no 'vs' or 'fighter' found in text).")
            
            # Click Load More a few times
            for i in range(3):
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

            print("Starting Brute Force Search...")
            fights_data = page.evaluate("""() => {
                const fights = [];
                const seen = new Set();
                
                // Grab EVERYTHING that could be a container
                const candidates = document.querySelectorAll('tr, li, div, p, article, span');
                
                candidates.forEach(el => {
                    const text = el.innerText;
                    // Filter for text that looks like a matchup
                    if (text.includes(' vs ') && text.length < 150 && text.length > 10) {
                        
                        // Avoid duplicates (e.g. text found in child AND parent)
                        if (seen.has(text)) return;
                        seen.add(text);

                        // Basic Parsing Strategy
                        let dateVal = "Check Details";
                        let titleVal = text.split('\\n')[0].trim(); // Assume first line is title
                        
                        // Try to find a date in the parent element or nearby
                        // This regex looks for "Nov 22" or "2025-11-22" styles
                        const dateMatch = text.match(/([A-Z][a-z]{2,8}\\s\\d{1,2})|(\\d{4}-\\d{2}-\\d{2})/);
                        if (dateMatch) {
                            dateVal = dateMatch[0];
                        } else {
                            // Look at previous sibling for date? (Common in lists)
                            if (el.previousElementSibling) {
                                const prevText = el.previousElementSibling.innerText;
                                const prevDate = prevText.match(/([A-Z][a-z]{2,8}\\s\\d{1,2})/);
                                if (prevDate) dateVal = prevDate[0];
                            }
                        }

                        fights.push({
                            title: titleVal,
                            date_raw: dateVal,
                            full_text: text
                        });
                    }
                });
                return fights;
            }""")
            
        except Exception as e:
            print(f"Browser Error: {e}")
        
        browser.close()
    
    return fights_data

def create_calendar(fights):
    cal = Calendar()
    cal.add('prodid', '-//Boxing Schedule//github-action//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'Boxing Schedule')

    for fight in fights:
        try:
            # Skip garbage entries
            if len(fight['title']) < 5: continue

            event = Event()
            event.add('summary', f"🥊 {fight['title']}")
            
            # Simple Date Parser
            dt = datetime.now()
            try:
                clean_date = re.sub(r'(?i)(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*', '', fight['date_raw']).strip()
                dt = datetime.strptime(f"{clean_date} {dt.year}", "%B %d %Y")
                # Fix year rollover
                if dt < datetime.now() - timedelta(days=60):
                    dt = dt.replace(year=dt.year + 1)
            except:
                pass # Keep default today+time if parse fails
            
            # Set to 8 PM
            dt = dt.replace(hour=20, minute=0, second=0)
            
            event.add('dtstart', dt)
            event.add('dtend', dt + timedelta(hours=4))
            event.add('description', f"Matchup: {fight['title']}\nFull Info: {fight['full_text']}")
            
            # Create UID
            uid = re.sub(r'[^a-zA-Z0-9]', '', fight['title']) + str(dt.year)
            event.add('uid', uid + "@boxingbot")
            
            cal.add_component(event)
        except:
            continue
            
    return cal

if __name__ == "__main__":
    data = run()
    print(f"--- FOUND {len(data)} POTENTIAL FIGHTS ---")
    
    if len(data) > 0:
        cal = create_calendar(data)
        with open('boxing_schedule.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("SUCCESS: .ics file created")
    else:
        print("FAILURE: Still 0 fights. Check the DEBUG logs above.")
        sys.exit(1) # Force failure so we see red X in GitHub