# Automated Boxing Event Calendar (The Ring Edition) (RIP Sunday Puncher)

**An automated, self-updating iCal feed for upcoming boxing matches, scraped directly from The Ring Magazine.**

> **Origin Story:** This project was created to replace the now-dormant "Sunday Puncher" calendar. It automatically scrapes schedule data, converts it into a calendar format, and hosts it for free using GitHub, so you never miss a big fight.

-----

## 🚀 How It Works

1.  **Scrapes:** A Python script uses **Playwright** to visit [The Ring Magazine's schedule page](https://ringmagazine.com/en/schedule/fights), rendering the JavaScript and clicking "Load More" to gather future fights.
2.  **Converts:** The data is parsed and converted into a standard `.ics` (iCalendar) file.
3.  **Automates:** **GitHub Actions** runs the script every day at 06:00 UTC automatically.
4.  **Hosts:** **GitHub Pages** serves the calendar file so you can subscribe to it in Apple Calendar, Google Calendar, or Outlook.

-----

## 🛠️ Setup Guide (Do It Yourself)

Follow these steps to create your own self-updating calendar.

### 1\. Create the Repository

1.  Create a new public repository on GitHub (e.g., named `boxing-calendar`).
2.  Clone it to your computer or use the "Add File" button on GitHub to create the files below.

### 2\. Add the Files

You need to create three specific files in your repository.

**File 1: `requirements.txt`** (Dependencies)

```text
playwright
icalendar
python-dateutil
```

**File 2: `scraper.py`** (The logic)
*Copy the Python script provided in the previous solution into this file.*

**File 3: `.github/workflows/main.yml`** (The automation)
*Copy the YAML configuration provided in the previous solution into this directory.*
*Note: Ensure you create the folder structure `.github` -\> `workflows` first.*

### 3\. Configure GitHub Pages

This is how the calendar gets a public URL.

1.  Go to your repository on GitHub.
2.  Click **Settings** (top right tab).
3.  In the left sidebar, click **Pages**.
4.  Under **Build and deployment** -\> **Source**, select **Deploy from a branch**.
5.  Under **Branch**, select `main` (or `master`) and keep the folder as `/ (root)`.
6.  Click **Save**.

### 4\. Trigger the First Run

1.  Go to the **Actions** tab in your repository.
2.  Click **Update Boxing Calendar** on the left.
3.  Click the **Run workflow** button on the right.
4.  Wait about 2-3 minutes for it to finish. Green checkmarks mean success\!

-----

## How to Subscribe

Once the Action finishes successfully, your calendar URL will be:

```text
https://<YOUR-GITHUB-USERNAME>.github.io/<REPO-NAME>/boxing_schedule.ics
```

### For Apple Calendar (iOS/Mac)

1.  Open Calendar.
2.  Go to **File** \> **New Calendar Subscription**.
3.  Paste your URL.
4.  **Important:** Set "Auto-refresh" to **Every Day**.

### For Google Calendar

1.  Open Google Calendar on a desktop.
2.  On the left, find "Other calendars" and click the **+** button.
3.  Select **From URL**.
4.  Paste your URL and click **Add calendar**.

-----

## Maintenance & Troubleshooting

**If the calendar stops updating:**
Web scrapers are fragile by nature. If The Ring Magazine changes their website layout (CSS classes or HTML structure), the scraper might fail.

1.  Check the **Actions** tab in GitHub to see error logs.
2.  If the script fails to find elements, you may need to update the CSS selectors in `scraper.py` to match the new website design.

-----

## License

This project is open source. Feel free to fork, modify, and improve\!