# Automated Boxing Event Calendar (The Ring Edition)

**An automated, self-updating iCal feed for upcoming boxing matches, scraped directly from The Ring Magazine.**

> **Why:** This project replaces the dormant "Sunday Puncher" calendar. It automatically scrapes schedule data from The Ring Magazine, converts it into a calendar format, and hosts it for free using GitHub, so you never miss a big fight.

-----

## How It Works

1.  **Scrapes:** A Python script uses **Playwright** to visit [The Ring Magazine's schedule page](https://ringmagazine.com/en/schedule/fights). It renders the full page, clicks "Load More" automatically to gather future fights, and extracts data using specific CSS selectors.
2.  **Converts:** The fight data (Date, Matchup, Location, Network) is parsed and converted into a standard `.ics` (iCalendar) file.
3.  **Automates:** **GitHub Actions** runs the script every day at 06:00 UTC automatically.
4.  **Hosts:** **GitHub Pages** serves the calendar file so you can subscribe to it in Apple Calendar, Google Calendar, or Outlook.

-----

## Setup Guide (Do It Yourself)

Follow these steps to create your own self-updating calendar.

### 1\. Create the Repository (Crucial Step)

1.  Create a new repository on GitHub (e.g., named `boxing-schedule`).
2.  **IMPORTANT:** You must set the repository visibility to **Public**.
      * *Why?* GitHub Pages (the hosting feature) only works for free on Public repositories. If it is Private, the calendar link will return a 404 error.

### 2\. Add the Files

Create these three files in your repository.

**File 1: `requirements.txt`** (Dependencies)

```text
playwright
icalendar
```

**File 2: `scraper.py`** (The Logic)
*Copy the Python script from the repo.*

**File 3: `.github/workflows/main.yml`** (The Automation)
*Copy the YAML configuration from the repo into the directory `.github/workflows/`.*

### 3\. Configure GitHub Pages

This is how the calendar gets a public URL.

1.  Go to your repository on GitHub.
2.  Click **Settings** (top right tab).
3.  In the left sidebar, click **Pages**.
4.  Under **Build and deployment** -\> **Source**, select **Deploy from a branch**.
5.  Under **Branch**, select `main` (or `master`) and keep the folder as `/ (root)`.
6.  Click **Save**.

### 4\. Trigger the First Run

1.  Go to the **Actions** tab.
2.  Click **Update Boxing Calendar** on the left.
3.  Click **Run workflow**.
4.  Wait for the green checkmark.

-----

## How to Subscribe

Once the Action finishes successfully, your calendar URL will be:

```text
https://<YOUR-GITHUB-USERNAME>.github.io/<REPO-NAME>/boxing_schedule.ics
```

**Example:** `https://mhmdmstf.github.io/boxing-schedule/boxing_schedule.ics`

### For Apple Calendar (iOS/Mac)

1.  Open Calendar -\> **File** -\> **New Calendar Subscription**.
2.  Paste your URL.
3.  **Crucial:** Set "Auto-refresh" to **Every Day**.

### For Google Calendar

1.  Open Google Calendar (Desktop).
2.  On the left, find "Other calendars" -\> **+** -\> **From URL**.
3.  Paste your URL and click **Add calendar**.

-----

## Maintenance & Troubleshooting

**If the calendar stops updating:**
This scraper relies on The Ring Magazine's website layout. If they redesign their site, the script might fail.

  * **Error:** "Timeout" or "No data found".
  * **Fix:** The CSS class names in `scraper.py` (specifically `.schedule-row`, `.date`, `.fight-title`) likely need to be updated to match the new website HTML.

-----

## License

This project is open source. Feel free to fork, modify, and improve\!