# HTA Firmware Tracker

A web dashboard that tracks the latest firmware/software versions for HTA's
audio gear, so nobody has to manually check manufacturer sites.

## What it does

- Tracks 43 pieces of equipment across DiGiCo, Yamaha, Solid State Logic,
  Allen & Heath, Shure, d&b audiotechnik, and Dante/Audinate.
- **All 43 items are checked automatically** — most by scraping a static
  page, several manufacturers via a real headless browser where the site
  needs JavaScript or blocks plain requests (see
  [How each manufacturer is checked](#how-each-manufacturer-is-checked)).
- Re-checks everything once a day (via a scheduled GitHub Actions workflow -
  see [Deployment](#deployment) - or via a background job if you run it
  locally) and highlights anything whose version changed since the last
  check.
- A stats panel at the top (Tracked / Updates / Errors / Last checked, the
  last shown as a relative time like "2h ago"), with a search box and
  Up to date / Update available / Check failed filters. Clicking the
  Updates card jumps straight to the flagged rows.
- Dashboard grouped by manufacturer, with status badges (Up to date / Update
  available / Check failed). A row with a new version gets a
  soft amber highlight in place (it isn't reordered) that clears itself
  automatically 2 weeks after the change was first detected — no one needs
  to click anything to dismiss it. Installable as a PWA on a phone (Add to
  Home Screen) for a full-screen, app-like view.

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

## How each manufacturer is checked

| Manufacturer | Method | Notes |
|---|---|---|
| DiGiCo | ✅ Scraped | `support.digico.biz`'s Zendesk help-center JSON API |
| Yamaha | ✅ Scraped | Static per-product firmware pages on `usa.yamaha.com` |
| Solid State Logic | ✅ Scraped | `support.solidstatelogic.com`'s Zendesk API too; tracked via SOLSA (versions 1:1 with SSL Live console software) and the Network I/O firmware bundle |
| Allen & Heath | ✅ Scraped (headless) | Site returns HTTP 403 to plain requests (bot protection) — works fine in a real headless browser |
| Dante/Audinate | ✅ Scraped (headless) | The version table is inside a click-to-expand accordion, so it's not in the page until JS runs. Dante Controller is published as separate Windows / macOS Apple Silicon / macOS Intel builds with their own versions, so all three are tracked (see below) |
| d&b audiotechnik | ✅ Scraped (headless) | Their Download Center is a JS-driven search box behind a cookie-consent overlay; D40/D90 share one firmware release, DN1 Switch has its own |
| Shure | ✅ Scraped (headless) | Firmware versions come from `shure.com`'s searchable software/firmware archive listing |

Every item is checked automatically. A piece of gear only gets added to the
list once a checker can read its version.

**Per-platform versions (Dante Controller).** Its row stays compact - one
status badge and the newest version, with a "3 platforms" note - and expands
(chevron on desktop, tap on phone) to list each platform's own version. Each
platform tracks its own previous version and change date, and the row's badge
is "Update available" whenever *any* platform changed within the 2-week
highlight window (the expanded list tags which one). Slack alerts name the
platform(s), e.g. "Dante Controller (Windows) → 4.18.1.3", and an update to
just one platform is caught even if it doesn't change the headline version.

**Article-based sources (DiGiCo, SSL) and "Needs verification".** These
manufacturers announce firmware in a help-centre *article* rather than on a
dedicated firmware page, so a new release normally shows up as a new
article/title/version and is handled like any other update. But an article
can also be edited in place. For these rows the checker keeps a fingerprint of
the matched article's content (text plus link and image URLs, so a swapped
download file counts). If the fingerprint changes while the title/version
stay the same, the row is marked **Needs verification** (purple badge, a note
with a link to the article, and a filter chip that only appears when something
is flagged) instead of "Update available" - it might be a real firmware change
or just a typo fix, and there's no way to tell automatically. A flag clears
itself after the same 2-week window as update flags, or is replaced by a normal
"Update available" if the version then really changes. The first fingerprint
stored for a row is only a baseline and never flags. Slack posts a separate,
non-@channel message for each newly flagged article that @-mentions the person
in the `SLACK_ALERT_USER_ID` repo secret; it is never announced like a
confirmed update. The DMI-Dante64@96 card is tracked as two rows (Zynq HC and
the older Summit HC), since they have separate firmware lines.

Yamaha, Allen & Heath, and Dante/Audinate don't publish a release date at
all - their checkers have nothing to put there. For those manufacturers
only, that column is labeled "Detected on" instead of "Release date" and
shows the day the tracker itself first caught a version change
(`last_changed_at`), not a manufacturer-published date. It stays blank for
anything that hasn't had a detected change - existing entries aren't
backfilled, and it's determined per manufacturer from the data (any item
with a real release date), not a hardcoded list.

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
- The dashboard has no interactive controls that write anything (no manual
  "Log" or "Acknowledge" buttons) — it's a pure status *display*, matching
  what a backend-less static site can actually support. Update flags clear
  themselves automatically instead (see below).
- `data/tracker.db` (SQLite) is still what the local interactive app uses
  day-to-day and is gitignored, same as always - it's not part of the
  deployment at all.

### Slack notifications

The daily workflow posts to Slack (`app/slack.py`) whenever it finds a
**genuinely new** firmware version - comparing each item's version before
and after that day's run, not just whatever's currently flagged. A version
that's still pending from a previous day, or one that just auto-cleared
after its 2-week window, doesn't trigger a repeat message; only an actual
change does.

Items are grouped by family before posting - e.g. all 5 DiGiCo Quantum
consoles updating together becomes one message ("New firmware available
for *DiGiCo Quantum series* → V23"), not five. Grouped by `checker_key`
(items that share one get checked together and always report the same new
version, by construction - a more reliable "these are really the same
family" signal than just matching version-number strings, which could
coincidentally collide between two unrelated manufacturers), with a
hand-curated `FAMILY_NAMES` mapping in `app/slack.py` for the friendly
name shown. A genuinely unrelated update detected the same day (different
`checker_key`) always gets its own separate message, `@channel` and all -
never bundled into someone else's.

Reads the webhook URL from the `SLACK_WEBHOOK_URL` repository secret (GitHub
→ Settings → Secrets and variables → Actions), passed to the workflow step
as an env var - never hardcoded, and not logged anywhere (GitHub also masks
any exact occurrence of a registered secret's value in the Action's log
output automatically). Missing the secret, or the POST itself failing,
never breaks the daily commit - `notify_updates()` in `app/slack.py`
degrades to a no-op (logged, not raised) in either case.

### Local automatic checking

If you run this locally instead of relying on the deployed site, the
background scheduler (`app/scheduler.py`, APScheduler) only runs **while the
app's process is alive** — if it's just open on your laptop, it only checks
while your laptop has it open. The deployed site doesn't have this
limitation, since GitHub Actions runs the check regardless of whether
anyone's computer is on.

When a version changes, the item gets an "Update available" badge and an
amber row highlight, in its normal position - it isn't moved to the top.
Both clear themselves automatically 2 weeks after the change was *first*
detected (`Equipment.last_changed_at`, see `app/runner.py`'s
`UPDATE_HIGHLIGHT_WINDOW`) - re-confirming the same pending version on later
daily checks doesn't restart that clock, only a genuinely new version change
does. No manual acknowledgment involved anywhere.

## Project layout

```
app/
  main.py            FastAPI routes + dashboard
  dashboard_data.py  Grouping/sorting/summary logic shared by the live app
                     and the static-site builder
  models.py          Equipment / CheckLog tables (SQLAlchemy)
  runner.py          Runs checkers, diffs versions, writes history,
                     auto-expires update flags after UPDATE_HIGHLIGHT_WINDOW
  scheduler.py       Background interval job (local interactive use only)
  seed.py            The 43-item equipment list + which checker covers each
  export.py          Equipment <-> data/equipment.json round-trip, used by
                     the CI pipeline
  checkers/
    digico.py, yamaha.py, shure.py, ssl.py             Static-page scrapers
    allenheath.py, dante.py, dbaudio.py                Headless-browser scrapers
    browser_base.py    Shared Playwright helper
    registry.py         Routes a checker_key to its module
  templates/, static/  Dashboard UI
scripts/
  ci_check.py        Entry point for the daily GitHub Actions run
  build_static.py    Renders the dashboard to public/ for Vercel
data/tracker.db      SQLite database (created on first run, local dev only)
data/equipment.json  Git-committed source of truth for the deployed site
```

## Adding equipment

Add a row to the `EQUIPMENT` list in `app/seed.py` (manufacturer, model,
category, checker_key, source URL, optional notes), then
restart the app (or run `python3 -m app.seed`) — `seed()` fully syncs the
database to match the list: new rows are added, changed rows are updated,
and rows removed from the list are deleted.
