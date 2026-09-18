# To-Do — HTA Firmware Tracker

Things worth doing next, in roughly the order they matter.

Already done: verifying the Shure accessories via SUU, and adding
headless-browser checkers for Solid State Logic, Allen & Heath, d&b, and
Dante — 43 of 47 tracked items are fully automatic now.

## 1. Get it running somewhere that's always on

Right now it only checks automatically while the app's process is alive. Pick
one:

- A spare Mac or a NAS you already have
- A cheap always-on VPS
- Ask IT if there's a house server this can live on

Once it's running continuously, everyone on the network can open the same
dashboard from their own computer and see live data — no install needed on
their end. Automatic daily checks also only really work once this is set up.

## 2. Slack integration

The plan: when a scraper detects a version change, post it to a channel
instead of relying on someone opening the dashboard. The checking logic is
already separate from the web routes, so this is additive, not a rewrite.

## Still manual, no source found (4 items)

Nobody's fault to fix in code — these genuinely don't have a version page or
API to scrape:

- **Waves**: SuperRack (installs through Waves Central, no standalone version
  page), WSG-HY128, Waves Plugins (release notes are per-plugin, not one
  overall version)
- **d&b**: DN1 Switch (no firmware entry exists for it in d&b's Download
  Center at all)

If any of these change (a new product page shows up, etc.), let me know and
I'll take another pass.

## Later, only if it becomes worth it

**A real domain instead of a raw address.** Once this is deployed
somewhere always-on, people will reach it by typing something like
`http://192.168.1.50:8000`. Fine for a small team; only worth swapping for a
friendlier name (e.g. `firmware.hta.internal`) once more people are using it
regularly.
