# HTA Firmware Tracker

A web dashboard that tracks the latest firmware/software versions for HTA's
audio gear, so nobody has to manually check manufacturer sites.

## What it does

- Tracks 47 pieces of equipment across DiGiCo, Yamaha, Solid State Logic,
  Allen & Heath, Shure, d&b audiotechnik, and Dante/Audinate.
- **All 47 items are checked automatically** — most by scraping a static
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
  automatically 1 month after the change was first detected — no one needs
  to click anything to dismiss it. Installable as a PWA on a phone (Add to
  Home Screen) for a full-screen, app-like view.
- Items that are genuinely the same underlying platform tracked from one
  source — e.g. DiGiCo's six Quantum consoles — collapse into a single
  family row ("Quantum series", under DiGiCo's own section heading)
  instead of listing near-duplicate rows that always move together. See
  [Firmware families](#firmware-families) for how that grouping is
  decided and kept in sync with Slack notifications.

## Architecture at a glance

One flow, run in two places (a daily GitHub Actions job, and locally on
demand):

```
app/seed.py ──► SQLite (throwaway in CI) ◄── data/equipment.json
 (what we track)         │                    (last known state, in git)
                         ▼
           app/runner.py  ─►  checker module per manufacturer
           (diff + persist)    (check_all(items) -> {item.id: CheckResult})
                         │
                         ├─►  app/slack.py       (only genuinely new versions)
                         ▼
           data/equipment.json  ─►  scripts/build_static.py  ─►  public/index.html
           (committed back)          (shared app/dashboard_data.py)   (Vercel)
```

- **`seed.py` is the list of what's tracked**; each row names a
  `checker_key` (e.g. `digico:quantum`), whose prefix `registry.py` routes
  to a manufacturer module. A checker gets all of its items at once and
  returns one `CheckResult` per item - it fetches each *source* once, not
  once per model.
- **State lives in git, not a database server.** CI starts from nothing
  each run: it re-seeds a throwaway SQLite DB, overlays the last known
  versions/timestamps from `data/equipment.json` (matched on
  manufacturer + model), checks, and writes the result back. So history
  persists as commits, and "what changed" is a before/after diff of two
  JSON snapshots (`app/changes.py`) rather than anything stored.
- **The deployed site is static HTML.** `build_static.py` renders the same
  Jinja template and calls the same `build_dashboard_context()` as the
  live FastAPI app, so the two can't drift on grouping/sorting/stats.
  There's no server in production - and so nothing that writes: flags
  clear themselves after a month instead of needing an "acknowledge".
- **Failures degrade, they don't cascade.** A checker that raises marks
  only its own items "Check failed"; a Slack outage or missing webhook
  never blocks the daily commit; a release-date lookup failing doesn't
  fail the version check it rode along with.

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
~90MB headless browser used only by the Allen & Heath / Shure / d&b / Dante
checkers — see below.)

## How each manufacturer is checked

| Manufacturer | Method | Notes |
|---|---|---|
| DiGiCo | ✅ Scraped | `support.digico.biz`'s Zendesk help-center JSON API |
| Yamaha | ✅ Scraped | Each product's Downloads page on `usa.yamaha.com` (a `#firmware-table` with a genuine "Last Update" date per file, not just a version) |
| Solid State Logic | ✅ Scraped | `support.solidstatelogic.com`'s Zendesk API too; tracked via SOLSA (versions 1:1 with SSL Live console software) and the Network I/O firmware bundle |
| Allen & Heath | ✅ Scraped (headless) | Version: `www.allen-heath.com` returns HTTP 403 to plain requests (bot protection) — works fine in a real headless browser. Release date: a separate evergreen article on `support.allen-heath.com` (a Zendesk help centre, read via its public JSON API — even a real browser can't get past that subdomain's own Cloudflare challenge page), month/year only, no day |
| Dante/Audinate | ✅ Scraped (headless) | The version table is inside a click-to-expand accordion, so it's not in the page until JS runs. Dante Controller is published as separate Windows / macOS Apple Silicon / macOS Intel builds with their own versions, so all three are tracked (see below) |
| d&b audiotechnik | ✅ Scraped (headless) | Their Download Center is a JS-driven search box behind a cookie-consent overlay; D40/D90 share one firmware release, DN1 Switch has its own |
| Shure | ✅ Scraped (headless) | Firmware versions come from `shure.com`'s searchable software/firmware archive listing |

Every item is checked automatically. A piece of gear only gets added to the
list once a checker can read its version.

**Per-platform versions (Dante Controller).** Its row stays compact - one
status badge and the newest version, with a "3 platforms" note - and expands
(chevron on desktop, tap on phone) to list each platform's own version. Each
platform tracks its own previous version and change date, and the row's badge
is "Update available" whenever *any* platform changed within the 1-month
highlight window (the expanded list tags which one). Slack alerts name the
platform(s), e.g. "Dante Controller (Windows) → 4.18.1.3", and an update to
just one platform is caught even if it doesn't change the headline version.
Each platform also has its own real release date - Audinate publishes a
dedicated "Release Notes" page per platform build, linked right from the
same accordion the version comes from - so the expanded list shows each
platform's own date, and the row's own Release date column shows whichever
platform's date matches the headline version.

**Article-based sources (DiGiCo, SSL).** These manufacturers announce
firmware in a help-centre *article* rather than on a dedicated firmware page,
so a new release shows up as a new article/title/version and is handled like
any other update - same title/version-based detection as every other
checker. The DMI-Dante64@96 card is tracked as two rows (Zynq HC and the
older Summit HC), since they're separate hardware variants with their own
firmware lines - one shared row used to flip between whichever line
published most recently.

Every manufacturer publishes a real release date now. The "Detected on"
fallback (the day the tracker itself first caught a version change,
`last_changed_at`, not a manufacturer-published date) is still there for
whenever a future manufacturer's checker has nothing to put in
release_date - it's determined per manufacturer from the data (any item
with a real release date), not a hardcoded list, so nothing needs to
change here if that happens again.

### How the headless-browser checkers work

`app/checkers/browser_base.py` holds a small Playwright helper
(`browser_page()` launches a headless Chromium tab, `dismiss_cookie_banner()`
clicks past consent overlays). `allenheath.py`, `dante.py`, `dbaudio.py`, and
`shure.py` use it to load a page, interact with it if needed (click an accordion, type
into a search box), and pull the version out of the rendered text. They're
slower than the plain-HTTP checkers (each spins up a real browser) but run
fine as part of the once-a-day background check. To add another one, copy
the shape of `dante.py`, then register it in `app/checkers/registry.py` and
point the relevant `app/seed.py` rows at it with `"scrape"` + a `checker_key`.

## Firmware families

Some rows track the same underlying platform from one firmware source -
DiGiCo's six Quantum consoles, Allen & Heath's four dLive surfaces/
MixRacks, Yamaha's two Rio-D2 I/O racks, Yamaha's eight Rivage PM
components, d&b's three D-series amps - and always report the identical
version because they're assigned the same `CheckResult` from one
`check_all()` call. Those collapse into a single dashboard row (e.g.
"Quantum series", under DiGiCo's own section heading) instead of six
near-identical ones. On desktop/tablet every field - status, version,
release date, previous version, last checked, source - still shows
directly in that one row, since it's identical for every member; only the
individual model names (e.g. Quantum 112/225/326/338/5/7) sit behind the
chevron, as pill tags. On phone, where the whole row's detail is already a
tap away, the model pills join the rest of that existing reveal instead of
getting their own control. A family whose collective name already spells
out every member - d&b's amp group is named "D25/D40/D90", not a generic
"series" label, because unlike the others it has no shorter collective
name that wouldn't also fit some other d&b product - skips the
chevron/expand entirely on both desktop and phone, in `FAMILY_NO_EXPAND`
(`app/families.py`): there's nothing left for it to reveal.

This is deliberately **not** based on matching version-number strings -
two unrelated products could coincidentally share a version number (Shure's
AD610, SBC240, and ADXR are different product types and always stay as
separate rows even if that happens). The real signal is `checker_key`
(assigned per actual firmware source in `app/seed.py`): items sharing one
were checked together and are guaranteed to move together. `app/families.py`
holds the one `FAMILY_NAMES` mapping (checker_key → friendly collective
name) that both `app/dashboard_data.py` (row consolidation) and
`app/slack.py` (notification grouping, see
[Slack notifications](#slack-notifications)) import, so the two can never
disagree about what counts as "the same family." Those names are
deliberately brand-free ("Quantum series", not "DiGiCo Quantum series") -
on the dashboard the row already sits under its manufacturer's own section
heading, so repeating the brand on every row under it would be redundant.
Slack messages have no such heading, so `app/slack.py` prepends the
manufacturer back on when it builds the notification text (correcting
Yamaha's all-caps `YAMAHA` field to "Yamaha" through `MANUFACTURER_LABELS`
along the way) - a Slack message still reads "DiGiCo Quantum series" even
though the stored name is just "Quantum series".

A family whose members all share one dashboard category (Yamaha's two
Rio-D2 racks are both "I/O Racks") is filed under it normally, same as any
other row. One spanning several categories (Yamaha's Rivage PM components
live under Consoles, DSP Engines, and I/O Racks) isn't attributed to any
one of them arbitrarily - it instead gets its own dedicated subsection,
named in `FAMILY_CATEGORIES` (also in `app/families.py`), e.g. "Rivage PM
Series". That's only set for families where it's actually useful - one
that's the only thing tracked under its manufacturer (Allen & Heath's
dLive series) stays without a heading instead, since a heading identical
to the one row underneath it would just be noise. A manufacturer's
subsections don't have to sort alphabetically or by equipment type either:
Yamaha's "Rivage PM Series" is pinned ahead of "Consoles" in
`CATEGORY_ORDER` (`app/dashboard_data.py`) since it's their flagship line,
not because any general ordering rule would put it first.

DiGiCo's SD10 is a genuine singleton (no other SD-series console is
tracked), but it still renders as a family-style row - "SD series", with a
chevron expanding to a lone "SD10" pill - rather than falling back to a
plain, non-expandable row the way every other singleton does. That's
`FAMILY_FORCE` in `app/families.py`: a checker_key can opt into the family
treatment even with one current member, when (like DiGiCo SD) its
FAMILY_NAMES entry represents a whole product line rather than describing
one specific model. Its dashboard category is just "Consoles" though, same
as the Quantum family right above it - no dedicated subsection, since both
are genuinely the same equipment type.

A family's members are supposed to always report identically (same
`CheckResult`, one `check_all()` call), but that premise could still be
violated by something outside any single check run - a member added to
the family before its first real check, stale state from before it
joined, a future checker bug. So `_consolidate_families` doesn't just
trust the first member for the row's displayed status: it picks whichever
member's status is most urgent (error beats a pending update beats "ok"),
so a failing member can't be quietly absorbed into a row that otherwise
looks fine. A family with any failing member shows "Check failed" on its
row. The error line underneath is the message once when the whole family
failed together (the normal case - one shared fetch), and names specific
models only when just some failed or the messages differ. There's
deliberately no per-model marker in the expanded pills - with every
current checker assigning one shared result per `checker_key`, a single
member failing alone can't happen in practice, so the row-level status is
all that's needed.

The stats panel's two counts deliberately mean different things. "Tracked"
is a coverage number - every real, individually-tracked piece of
equipment, unaffected by how many rows that collapses into on screen, so
it doesn't shrink just because some of what it covers shares one firmware
source. "Updates" counts rows instead, not units - if Rivage PM's 8
components all pick up a new version at once, that's genuinely one thing
to go look at, so it shows "1 update available," not 8. Clicking the
Updates card filters straight to those rows, so the number it shows always
matches what you'd actually see land on screen. "Errors" still counts
units (unchanged) - see `build_dashboard_context` in
`app/dashboard_data.py` for exactly which list each one sums over.

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
- The site asks search engines not to index it: a `<meta name="robots"
  content="noindex, nofollow, noarchive">` tag in the template plus an
  `X-Robots-Tag` header for every file (`vercel.json`). That's a request
  well-behaved crawlers honor, not access control - anyone with the link
  can still open it, and it doesn't cover the public GitHub repo itself
  (GitHub has no setting to keep a public repo out of search). There's
  deliberately no `robots.txt` blocking crawling: a crawler has to be
  allowed to fetch the page to see the noindex instruction.
- `data/tracker.db` (SQLite) is still what the local interactive app uses
  day-to-day and is gitignored, same as always - it's not part of the
  deployment at all.

### Slack notifications

The daily workflow posts to Slack (`app/slack.py`) whenever it finds a
**genuinely new** firmware version - comparing each item's version before
and after that day's run, not just whatever's currently flagged. A version
that's still pending from a previous day, or one that just auto-cleared
after its 1-month window, doesn't trigger a repeat message; only an actual
change does.

Items are grouped by family before posting - e.g. all 6 DiGiCo Quantum
consoles updating together becomes one message ("New firmware available
for *DiGiCo Quantum series* → V23"), not six. Grouped by `checker_key`
(items that share one get checked together and always report the same new
version, by construction - a more reliable "these are really the same
family" signal than just matching version-number strings, which could
coincidentally collide between two unrelated manufacturers), using the
same `FAMILY_NAMES` mapping in `app/families.py` that the dashboard uses to
consolidate rows - see [Firmware families](#firmware-families) - so the two
never disagree about what counts as one family. A genuinely unrelated
update detected the same day (different `checker_key`) always gets its own
separate message, `@channel` and all - never bundled into someone else's.

**Check-failure alerts.** A separate message goes out when an item's check
*newly* fails (`find_new_errors` in `app/changes.py` compares each item's
status before and after the run): "⚠️ Firmware check failed for *Yamaha
Rivage PM series*: <error>". It fires once when the failure starts, not
every morning while it stays broken, and a brand-new item failing its very
first check counts too. Family members that share one fetch are one
message with the error stated once. Unlike version alerts it pings one
person, not `@channel` - the same `SLACK_ALERT_USER_ID` member ID the "daily
run failed" alert uses. This matters because a single broken scraper
doesn't fail the workflow (the runner records it and carries on), so the
workflow-level alert would never fire for it. Not covered: a failed Vercel
deploy, and a failure that is already present the first time this runs.

Reads the webhook URL from the `SLACK_WEBHOOK_URL` repository secret (GitHub
→ Settings → Secrets and variables → Actions), passed to the workflow step
as an env var - never hardcoded, and not logged anywhere (GitHub also masks
any exact occurrence of a registered secret's value in the Action's log
output automatically). Missing the secret, or the POST itself failing,
never breaks the daily commit - `notify_updates()` in `app/slack.py`
degrades to a no-op (logged, not raised) in either case.

**Testing Slack (new webhook, new recipient).** GitHub → Actions → "Daily
firmware check" → Run workflow → tick `slack_test`. That runs only
`scripts/slack_test.py` - no firmware checks, no commit - and posts one
clearly-labelled TEST message (no `@channel`) using the real
`SLACK_WEBHOOK_URL` and `SLACK_ALERT_USER_ID`, mentioning the alert
recipient so you can see exactly who real failure alerts will ping. The run
goes red if Slack rejects it, with Slack's reason in the log (e.g.
`no_service` = webhook revoked, `channel_not_found`). Locally:
`SLACK_WEBHOOK_URL=... SLACK_ALERT_USER_ID=U01ABCDE2F python3 scripts/slack_test.py`.
A webhook posts to the one channel picked when it was created, and member
IDs belong to a workspace - so moving to a different workspace means
replacing *both* secrets.

### Local automatic checking

If you run this locally instead of relying on the deployed site, the
background scheduler (`app/scheduler.py`, APScheduler) only runs **while the
app's process is alive** — if it's just open on your laptop, it only checks
while your laptop has it open. The deployed site doesn't have this
limitation, since GitHub Actions runs the check regardless of whether
anyone's computer is on.

When a version changes, the item gets an "Update available" badge and an
amber row highlight, in its normal position - it isn't moved to the top.
Both clear themselves automatically 1 month after the change was *first*
detected (`Equipment.last_changed_at`, see `app/runner.py`'s
`UPDATE_HIGHLIGHT_WINDOW`) - re-confirming the same pending version on later
daily checks doesn't restart that clock, only a genuinely new version change
does. No manual acknowledgment involved anywhere.

## Project layout

```
app/
  main.py            FastAPI routes + dashboard
  dashboard_data.py  Grouping/sorting/summary logic shared by the live app
                     and the static-site builder, incl. family row
                     consolidation (see Firmware families)
  families.py        FAMILY_NAMES: checker_key -> brand-free family name,
                     shared by dashboard_data.py and slack.py (the latter
                     prepends the manufacturer back on)
  models.py          Equipment / CheckLog tables (SQLAlchemy)
  runner.py          Runs checkers, diffs versions, writes history,
                     auto-expires update flags after UPDATE_HIGHLIGHT_WINDOW
  scheduler.py       Background interval job (local interactive use only)
  seed.py            The 47-item equipment list + which checker covers each
  export.py          Equipment <-> data/equipment.json round-trip, used by
                     the CI pipeline
  changes.py         Before/after diff of two JSON snapshots -> the genuine
                     version changes Slack is told about
  slack.py           Webhook notifications, one message per family
  checkers/
    digico.py, yamaha.py, ssl.py                       Plain-HTTP (HTML / Zendesk JSON API)
    allenheath.py, dante.py, dbaudio.py, shure.py      Headless-browser (Playwright)
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
