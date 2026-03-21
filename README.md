# Boxing Schedule Calendar

[![Update Boxing Calendar](https://github.com/mhmdmstf/boxing-schedule/actions/workflows/main.yml/badge.svg)](https://github.com/mhmdmstf/boxing-schedule/actions/workflows/main.yml)

A self-updating iCal feed for upcoming boxing matches, scraped daily from [The Ring Magazine](https://ringmagazine.com/en/schedule/fights).

## Subscribe

Paste this URL into your calendar app:

```
https://raw.githubusercontent.com/mhmdmstf/boxing-schedule/refs/heads/main/boxing_schedule.ics
```

- **Apple Calendar:** File > New Calendar Subscription > paste URL > Auto-refresh: Every Day
- **Google Calendar:** Other calendars (+) > From URL > paste URL
- **Outlook:** Add calendar > Subscribe from web > paste URL

## What You Get

Each calendar event is a full fight card:

```
🥊 CANELO ALVAREZ VS DAVID BENAVIDEZ (+4 more)
```

The description lists the full card with venue, broadcast, and start time. Events are timezone-aware based on venue location. Past events drop off after one week.

## How It Works

A Python script scrapes The Ring Magazine schedule via Playwright, groups fights into cards by date and venue, detects main events from page formatting, and generates a timezone-aware `.ics` file. GitHub Actions runs this daily at 06:00 UTC.

## Self-Host

1. Fork this repo
2. Go to Actions > "Update Boxing Calendar" > Run workflow
3. Subscribe to `https://raw.githubusercontent.com/<YOU>/<REPO>/refs/heads/main/boxing_schedule.ics`

## License

Open source. Fork and modify as needed.
