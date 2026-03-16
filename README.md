# Boxing Schedule Calendar

[![Update Boxing Calendar](https://github.com/mhmdmstf/boxing-schedule/actions/workflows/main.yml/badge.svg)](https://github.com/mhmdmstf/boxing-schedule/actions/workflows/main.yml)

A self-updating iCal feed for upcoming boxing matches, scraped daily from [The Ring Magazine](https://ringmagazine.com/en/schedule/fights).

## Subscribe

Paste this URL into your calendar app:

```
https://raw.githubusercontent.com/mhmdmstf/boxing-schedule/refs/heads/main/boxing_schedule.ics
```

**Apple Calendar:** File > New Calendar Subscription > paste URL > Auto-refresh: Every Day

**Google Calendar:** Other calendars (+) > From URL > paste URL

**Outlook:** Add calendar > Subscribe from web > paste URL

## What You Get

Each calendar event is a full **fight card**, not individual bouts:

```
🥊 JAKE PAUL VS ANTHONY JOSHUA (+4 more)
```

The event description lists the full card — main event in caps, undercard fights below, plus venue, broadcast, and start time. Events include timezone info based on the venue location.

Past events are automatically removed after one week.

## How It Works

1. A Python script scrapes The Ring Magazine schedule using Playwright
2. Fights are grouped into cards by date and venue
3. Main events are detected from the source page formatting
4. An `.ics` calendar file is generated with timezone-aware times
5. GitHub Actions runs this daily at 06:00 UTC and commits any changes

## Self-Host

1. Fork this repo (must be **public** for free GitHub Pages)
2. Go to Settings > Pages > Deploy from `main` branch
3. Go to Actions > "Update Boxing Calendar" > Run workflow

Your feed will be at:
```
https://raw.githubusercontent.com/<YOU>/<REPO>/refs/heads/main/boxing_schedule.ics
```

## License

Open source. Fork and modify as needed.
