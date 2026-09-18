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

**Interactive Log/Acknowledge on the live site.** Right now those only work
when running the app locally (see README) - the published site is read-only
by design, to keep it a free static deploy with no hosted backend/database.
If that tradeoff stops being worth it, revisit adding a small backend with
persistent storage.
