# Boxing Schedule Calendar

[![Update Boxing Calendar](https://github.com/mhmdmstf/boxing-schedule/actions/workflows/main.yml/badge.svg)](https://github.com/mhmdmstf/boxing-schedule/actions/workflows/main.yml)

Auto-updating iCal feed for upcoming boxing matches, scraped from The Ring Magazine.

## Subscribe

```
https://raw.githubusercontent.com/mhmdmstf/boxing-schedule/refs/heads/main/boxing_schedule.ics
```

**Apple Calendar:** File > New Calendar Subscription > paste URL > set Auto-refresh to "Every Day"

**Google Calendar:** Other calendars > + > From URL > paste URL

**Outlook:** Add calendar > Subscribe from web > paste URL

## How It Works

1. Python script uses Playwright to load [The Ring Magazine schedule](https://ringmagazine.com/en/schedule/fights)
2. Clicks "Load More" to expand the full schedule
3. Scrapes fighter names, dates, locations, times, and broadcast info
4. Groups fights into cards by date and venue
5. Creates one calendar event per card
6. GitHub Actions runs daily at 06:00 UTC

## Event Format

Each event represents a fight card:

```
MAIN EVENT: undercard1, undercard2
```

- **MAIN EVENT** (ALL CAPS): Headline fight
- **undercards** (title case): Supporting fights

## Run Your Own

1. Fork this repo (must be public for free GitHub Pages)
2. Enable GitHub Pages: Settings > Pages > Deploy from branch > main / root
3. Actions tab > Run workflow

Your calendar: `https://raw.githubusercontent.com/<USER>/<REPO>/refs/heads/main/boxing_schedule.ics`

## Troubleshooting

- **No fights found:** Website structure may have changed
- **Timeout errors:** Try increasing timeout values in script
- **Missing dates:** Source may not have dates listed yet
- **Duplicates:** Fighter names may differ across pages

## License

MIT License. Fork and modify freely.
