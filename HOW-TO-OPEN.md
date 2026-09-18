# How to Open the HTA Firmware Tracker

## Every time you want to check it

1. Open **Finder** and go to the `hta-firmware-tracker` project folder.
2. Double-click **`start.command`** (not `start.sh` — macOS doesn't offer
   Terminal in "Open With" for `.sh` files, but `.command` files open
   straight into Terminal). First time only: macOS will likely block it with
   a "cannot be opened" security warning — **right-click `start.command` →
   Open**, then click **Open** again in the dialog that appears. After that
   one-time step, double-clicking works normally.
3. A Terminal window opens and starts the app. Your browser should open
   automatically to the dashboard. If it doesn't, go to:
   **http://127.0.0.1:8811**

## When you're done

Go back to that Terminal window and press **Control + C** to stop the app.
Closing the Terminal window also stops it.

## Running it from Terminal directly (alternative)

If you'd rather type it than double-click:

```bash
cd "hta-firmware-tracker"
./start.sh
```

(`start.sh` and `start.command` are identical — `start.command` just exists
because Finder can double-click it.)

## Good to know

- The app only runs **while that Terminal window is open** on your Mac. If you
  close it, the dashboard stops working (for you and for anyone else you've
  shared the address with).
- Right now it's only reachable from **your own computer** — coworkers can't
  see it yet. Getting it onto a machine that's always on (and reachable on the
  network) is the first item on the [to-do list](TODO.pdf); once that's done,
  nobody needs to "start" anything — it's just always there at a fixed
  address.
- If the page looks stale, click **"Check All Now"** in the top-left of the
  dashboard to force a fresh check of everything.
