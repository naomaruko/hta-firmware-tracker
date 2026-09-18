# To-Do — HTA Firmware Tracker

Things worth doing next, in roughly the order they matter.

Already done:
- Verifying the Shure accessories via SUU, and adding headless-browser
  checkers for Solid State Logic, Allen & Heath, d&b, and Dante — all 43
  tracked items are fully automatic now (Waves was dropped from tracking;
  d&b's DN1 Switch got its own automated checker).
- Deployed as a static site (see README's "Deployment" section): a daily
  GitHub Actions workflow runs the checkers and commits the results, Vercel
  serves the published `public/` output, and it's installable as a PWA on a
  phone (Add to Home Screen, full-screen app-like view).
- Removed the manual "Log"/"Acknowledge" buttons entirely - update flags
  (amber row highlight + badge) now clear themselves automatically 2 weeks
  after first being detected, with no one needing to click anything.

## 1. Slack integration

The plan: when a scraper detects a version change, post it to a channel
instead of relying on someone opening the dashboard. The checking logic is
already separate from the web routes, so this is additive, not a rewrite -
the daily GitHub Actions run would be the natural place to add a
"post to Slack if anything changed" step after `scripts/ci_check.py`.

## Later, only if it becomes worth it

**A real domain instead of the default Vercel one.** Once more people are
using it regularly, worth pointing a friendlier name (e.g.
`firmware.hta.com`) at the Vercel deployment instead of the generated
`*.vercel.app` address.

**A different highlight window than 2 weeks.** Currently a hardcoded
constant (`UPDATE_HIGHLIGHT_WINDOW` in `app/runner.py`) - trivial to change
if 2 weeks turns out to be too short/long in practice.
