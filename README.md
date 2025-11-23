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
3. Parses the page text line-by-line, looking for "VS" patterns to identify fights
4. Extracts fighter names, dates, locations, times, and broadcast info
5. Converts everything into a standard .ics calendar file
6. GitHub Actions runs this daily at 06:00 UTC
7. GitHub Pages hosts the file at a public URL

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
- **No fights found:** The page structure may have changed. Check if the "VS" text pattern still exists on the page.
- **Timeout errors:** The page may be slow to load. Try increasing the timeout values in the script.
- **Missing dates:** Some fights may not have dates listed yet on the source page.

---

## License

Open source. Fork and modify as needed.
