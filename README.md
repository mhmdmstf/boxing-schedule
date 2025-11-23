# Boxing Schedule Calendar

An automated, self-updating iCal feed for upcoming boxing matches, scraped from The Ring Magazine.

---

## Quick Subscribe

You can subscribe to the calendar directly without setting anything up:

```
https://raw.githubusercontent.com/mhmdmstf/boxing-schedule/refs/heads/main/boxing_schedule.ics
```

**Apple Calendar (iOS/Mac):** File > New Calendar Subscription > paste the URL > set Auto-refresh to "Every Day"

**Google Calendar:** Other calendars > + > From URL > paste the URL

**Outlook:** Add calendar > Subscribe from web > paste the URL

If you want your own copy or want to modify it, see the setup guide below.

---

## How It Works

1. A Python script uses Playwright to load [The Ring Magazine schedule page](https://ringmagazine.com/en/schedule/fights)
2. It clicks "Load More" to expand the full schedule
3. Extracts all fight URLs from the page and visits each fight's detail page
4. Scrapes fighter names, dates, locations, times, and broadcast info from each page
5. Groups fights into **cards** by date and venue
6. Creates one calendar event per card with the full fight lineup
7. GitHub Actions runs this daily at 06:00 UTC
8. GitHub Pages hosts the file at a public URL

---

## Calendar Event Format

Each calendar event represents a full **fight card** (not individual fights). The format is:

```
🥊 MAIN EVENT: undercard1, undercard2, undercard3
```

**Convention:**
- **MAIN EVENT** (ALL CAPS): The headline fight of the card
- **undercards** (title case): Supporting fights on the same card, separated by commas

**Example:**
```
🥊 ISAAC CRUZ VS LAMONT ROACH: Gabriel Flores vs Joe Cordina, Skye Nicolson vs Yuliahn Luna
```

This means Isaac Cruz vs Lamont Roach is the main event, with Flores-Cordina and Nicolson-Luna as undercard fights.

**Event Description** includes:
- Main event name
- Full undercard list with bullet points
- Venue location
- Broadcast network (e.g., "LIVE ON PRIME VIDEO PPV")
- Start time

---

## Setup Your Own Version

### 1. Create Repository

1. Fork this repo or create a new public repository
2. The repository must be **Public** for GitHub Pages to work for free

### 2. Add Files

Copy these files to your repository:
- `requirements.txt` - Python dependencies
- `scraper.py` - The scraper script
- `.github/workflows/main.yml` - GitHub Actions workflow

### 3. Configure GitHub Pages

1. Go to repository Settings > Pages
2. Under Source, select "Deploy from a branch"
3. Select the `main` branch and `/ (root)` folder
4. Save

### 4. Run It

1. Go to the Actions tab
2. Select "Update Boxing Calendar"
3. Click "Run workflow"

Your calendar will be available at:
```
https://raw.githubusercontent.com/<YOUR-USERNAME>/<REPO-NAME>/refs/heads/main/boxing_schedule.ics
```

---

## Troubleshooting

This scraper depends on The Ring Magazine website structure. If they redesign their site, the scraper may break.

Common issues:
- **No fights found:** The page structure may have changed. Check if fight detail pages still exist at `/en/schedule/fights/<slug>`.
- **Timeout errors:** The page may be slow to load. Try increasing the timeout values in the script.
- **Missing dates:** Some fights may not have dates listed yet on the source page.
- **Duplicate fights:** The scraper uses fuzzy name matching to deduplicate. If you see duplicates, the fighter names may be formatted differently on different pages.
- **Wrong grouping:** Fights are grouped by date and venue. If fights appear on separate cards when they should be together, check if the venue names match exactly.

---

## License

Open source. Fork and modify as needed.
