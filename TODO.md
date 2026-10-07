# To-Do — HTA Firmware Tracker

Things worth doing next, in roughly the order they matter.

## Next up

**Move the repo to a company GitHub organization.** It lives under a
personal account (`naomaruko`), so the daily check, the Slack alerts, and
the site's updates all depend on that one account. Once a company org
exists:

1. Repo Settings -> General -> Danger Zone -> Transfer ownership. Keep the
   name `hta-firmware-tracker`, and avoid ~6 AM Pacific (the daily run).
2. Re-enter the two secrets under Settings -> Secrets and variables ->
   Actions: `SLACK_WEBHOOK_URL` and `SLACK_ALERT_USER_ID`. It isn't confirmed
   that repo secrets survive a transfer, so don't assume they did.
3. Check the Actions tab: workflows enabled and allowed by the org, workflow
   permissions allow writing, and no branch protection on `main` that
   blocks the bot's daily commit (a blocked push shows up as a "daily run
   failed" Slack alert).
4. Vercel: install the Vercel GitHub app on the org (an org owner approves
   it), confirm the project's Git connection in its settings, then run the
   workflow and confirm the site updates. Keep the repo **public** - Vercel's
   free Hobby plan can't deploy private org repos, and a private repo
   probably blocks the bot's commits too (unconfirmed); either needs Pro.
5. Point the local copy at it: `git remote set-url origin <new url>`.
6. Re-run the manual `slack_test` workflow to confirm alerts still land.

If not already done: add a colleague as a collaborator on the Slack app
(api.slack.com/apps -> the app -> Collaborators), so it isn't tied to one
person.

**Watch the first real update alert.** The `@channel` on firmware-update
alerts hasn't been seen working in the company channel yet - the test
message deliberately avoids it so it doesn't ping everyone. Check that the
first real one actually notifies the channel.

## Already done
- Verifying the Shure accessories via SUU, and adding headless-browser
  checkers for Solid State Logic, Allen & Heath, d&b, and Dante — all 47
  tracked items are fully automatic now (Waves was dropped from tracking;
  d&b's DN1 Switch got its own automated checker).
- Deployed as a static site (see README's "Deployment" section): a daily
  GitHub Actions workflow runs the checkers and commits the results, Vercel
  serves the published `public/` output, and it's installable as a PWA on a
  phone (Add to Home Screen, full-screen app-like view).
- Removed the manual "Log"/"Acknowledge" buttons entirely - update flags
  (amber row highlight + badge) now clear themselves automatically 1 month
  after first being detected, with no one needing to click anything.
- Slack integration: the daily GitHub Actions run posts an `@channel`
  message with a dashboard link whenever it finds a genuinely new firmware
  version - not on every run, and not a repeat ping for a version that's
  still pending or just auto-cleared (see README's "Deployment" section).
- Slack now points at the company workspace, with a separate alert (pinging
  one person, not `@channel`) when an item's check newly fails, and a manual
  `slack_test` workflow run to confirm a webhook/recipient works.
- Equipment that always moves together (e.g. DiGiCo's Quantum consoles) is
  grouped into one dashboard row and one Slack message (see README's
  "Firmware families").

## Later, only if it becomes worth it

**A real domain instead of the default Vercel one.** Once more people are
using it regularly, worth pointing a friendlier name (e.g.
`firmware.hta.com`) at the Vercel deployment instead of the generated
`*.vercel.app` address.

**A different highlight window than 1 month.** Currently a hardcoded
constant (`UPDATE_HIGHLIGHT_WINDOW` in `app/runner.py`) - trivial to change
if a month turns out to be too short/long in practice.
