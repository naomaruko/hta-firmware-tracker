# HTA Firmware Tracker

A web dashboard that tracks the latest firmware/software versions for HTA's
audio gear, so nobody has to manually check manufacturer sites.

## What it does

- Tracks 43 pieces of equipment across DiGiCo, Yamaha, Solid State Logic,
  Allen & Heath, Shure, d&b audiotechnik, and Dante/Audinate.
- **All 43 items are checked automatically** — most by scraping a static
  page, several manufacturers via a real headless browser where the site
  needs JavaScript or blocks plain requests (see
  [What's automatic vs. manual](#whats-automatic-vs-manual)).
- Re-checks everything once a day (via a scheduled GitHub Actions workflow -
  see [Deployment](#deployment) - or via a background job if you run it
  locally) and highlights anything whose version changed since the last
  check.
- Dashboard grouped by manufacturer, with status badges (Up to date / Update
  available / Manual check / Check failed), a "Log" button for manually-
  checked items, and an "Acknowledge" button to clear an update flag once
  you've dealt with it. Installable as a PWA on a phone (Add to Home Screen)
  for a full-screen, app-like view.

## Quick start

```bash
cd "hta-firmware-tracker"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — the database (SQLite, at `data/tracker.db`) is
created and seeded automatically on first run, and a check kicks off ~5
seconds after startup. (The `playwright install chromium` step downloads a
~90MB headless browser used only by the Allen & Heath / SSL / d&b / Dante
checkers — see below.)

## What's automatic vs. manual

| Manufacturer | Method | Notes |
|---|---|---|
| DiGiCo | ✅ Scraped | `support.digico.biz`'s Zendesk help-center JSON API |
| Yamaha | ✅ Scraped | Static per-product firmware pages on `usa.yamaha.com` |
| Solid State Logic | ✅ Scraped | `support.solidstatelogic.com`'s Zendesk API too; tracked via SOLSA (versions 1:1 with SSL Live console software) and the Network I/O firmware bundle |
| Allen & Heath | ✅ Scraped (headless) | Site returns HTTP 403 to plain requests (bot protection) — works fine in a real headless browser |
| Dante/Audinate | ✅ Scraped (headless) | The version table is inside a click-to-expand accordion, so it's not in the page until JS runs |
| d&b audiotechnik | ✅ Scraped (headless) | Their Download Center is a JS-driven search box behind a cookie-consent overlay; D40/D90 share one firmware release, DN1 Switch has its own |
| Shure | ✅ Scraped (headless) | Firmware versions come from `shure.com`'s searchable software/firmware archive listing |

Every manufacturer is fully automated right now. If a new piece of gear gets
added that has no scrapable version page, it'll show up here as "Manual
check" with a direct link to where to look by hand instead.

### How the headless-browser checkers work

`app/checkers/browser_base.py` holds a small Playwright helper
(`browser_page()` launches a headless Chromium tab, `dismiss_cookie_banner()`
clicks past consent overlays). `allenheath.py`, `dante.py`, and `dbaudio.py`
use it to load a page, interact with it if needed (click an accordion, type
into a search box), and pull the version out of the rendered text. They're
slower than the plain-HTTP checkers (each spins up a real browser) but run
fine as part of the once-a-day background check. To add another one, copy
the shape of `dante.py`, then register it in `app/checkers/registry.py` and
point the relevant `app/seed.py` rows at it with `"scrape"` + a `checker_key`.

## Deployment

The published site (on Vercel) is a **static build**, not the live FastAPI
app — there's no server running continuously anywhere. Instead:

- **`.github/workflows/daily-check.yml`** runs once a day (GitHub Actions
  cron, plus a manual "Run workflow" button). It rebuilds a throwaway
  database from `data/equipment.json`, runs every checker for real, writes
  the results back to `data/equipment.json`, renders the dashboard to
  `public/index.html` (`scripts/build_static.py`), and commits both back to
  the repo — a fresh "Last checked" timestamp lands every single day, even
  when no version actually changed, so there's always a commit to show the
  check ran.
- **Vercel** serves the `public/` directory as-is (see `vercel.json`) — no
  build step, no server, just static files. Importing this repo into Vercel
  needs no extra configuration.
- Because the deployed site has no backend, **"Log" and "Acknowledge" are
  read-only there** — the published dashboard is a live status *display*.
  Those two buttons still work exactly as before when someone runs the app
  locally (`start.command`); commit and push the resulting
  `data/equipment.json` (and re-run `scripts/build_static.py`) to reflect a
  manual change on the live site before the next scheduled run picks it up.
- `data/tracker.db` (SQLite) is still what the local interactive app uses
  day-to-day and is gitignored, same as always - it's not part of the
  deployment at all.

### Local automatic checking

If you run this locally instead of relying on the deployed site, the
background scheduler (`app/scheduler.py`, APScheduler) only runs **while the
app's process is alive** — if it's just open on your laptop, it only checks
while your laptop has it open. The deployed site doesn't have this
limitation, since GitHub Actions runs the check regardless of whether
anyone's computer is on.

When a version changes, the item flips to an "Update available" badge and
stays that way (even across further checks) until someone clicks
"Acknowledge" — so a change can't get silently missed between visits.

## Project layout

```
app/
  main.py           FastAPI routes + dashboard
  models.py         Equipment / CheckLog tables (SQLAlchemy)
  runner.py         Runs checkers, diffs versions, writes history
  scheduler.py       Background interval job
  seed.py            The 47-item equipment list + which checker covers each
  checkers/
    digico.py, yamaha.py, waves.py, shure.py, ssl.py   Static-page scrapers
    allenheath.py, dante.py, dbaudio.py                Headless-browser scrapers
    browser_base.py    Shared Playwright helper
    registry.py         Routes a checker_key to its module
  templates/, static/  Dashboard UI
data/tracker.db      SQLite database (created on first run)
```

## Adding equipment

Add a row to the `EQUIPMENT` list in `app/seed.py` (manufacturer, model,
`"scrape"` or `"manual"`, checker_key, source URL, optional notes), then
restart the app (or run `python3 -m app.seed`) — `seed()` fully syncs the
database to match the list: new rows are added, changed rows are updated,
and rows removed from the list are deleted.
