"""Renders the dashboard to static HTML for Vercel (or any static host).

Reads data/equipment.json (written by scripts/ci_check.py, or by exporting
the live dev DB - see the README) and renders the exact same dashboard.html
template the live FastAPI app uses, via build_dashboard_context so the two
can never disagree on grouping/sorting/summary logic. Output goes to
public/ - the directory name Vercel auto-detects as static site root with no
config needed.

The template itself doesn't reference FastAPI's `request` object anywhere
(checked - it only ever uses hardcoded /static/... paths, never url_for), so
this renders it with a plain jinja2.Environment rather than needing to fake
one up.
"""
import datetime as dt
import shutil
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jinja2  # noqa: E402

from app.dashboard_data import build_dashboard_context  # noqa: E402
from app.export import load_json  # noqa: E402
from app.timeutil import to_pacific  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "equipment.json"
TEMPLATES_DIR = ROOT / "app" / "templates"
STATIC_SRC = ROOT / "app" / "static"
OUT_DIR = ROOT / "public"


def _parse_dt(value):
    return dt.datetime.fromisoformat(value) if value else None


def _record_to_item(record: dict):
    """dashboard.html accesses fields as item.foo and calls
    item.last_checked_at.isoformat() directly, so the JSON's ISO strings get
    parsed back into real datetime objects rather than staying plain dicts."""
    item = types.SimpleNamespace(**record)
    item.last_checked_at = _parse_dt(record.get("last_checked_at"))
    item.last_changed_at = _parse_dt(record.get("last_changed_at"))
    return item


def main():
    records = load_json(JSON_PATH)
    if not records:
        raise SystemExit(f"{JSON_PATH} is empty or missing - run scripts/ci_check.py first")

    items = [_record_to_item(r) for r in records]
    context = build_dashboard_context(items)

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)))
    env.filters["pacific"] = to_pacific
    # Cache-busting query param on every static asset URL, same purpose as
    # main.py's BUILD_VERSION - a fresh value per deploy so Vercel's CDN/the
    # browser can't keep serving a stale style.css or app.js after a push.
    env.globals["v"] = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    template = env.get_template("dashboard.html")

    html = template.render(
        now=dt.datetime.utcnow(),
        interactive=False,
        **context,
    )

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    (OUT_DIR / "index.html").write_text(html)
    shutil.copytree(STATIC_SRC, OUT_DIR / "static")

    # Also served at the site root (not just /static/sw.js) - a service
    # worker's default max scope is the directory it's served from, so this
    # is what lets app.js register it with scope "/" and actually control
    # the dashboard page itself, not just static assets. Mirrors the /sw.js
    # FastAPI route in app/main.py used for local dev.
    shutil.copy(STATIC_SRC / "sw.js", OUT_DIR / "sw.js")

    # Also served at the site root - browsers request /favicon.ico directly
    # regardless of the <link> tags in <head>. Mirrors the /favicon.ico
    # FastAPI route in app/main.py used for local dev.
    shutil.copy(STATIC_SRC / "icons" / "favicon.ico", OUT_DIR / "favicon.ico")

    # Bump the service worker's cache name so each deploy gets a clean cache
    # instead of a phone potentially holding onto a previous deploy's assets
    # indefinitely (see app/static/sw.js).
    for sw_path in (OUT_DIR / "sw.js", OUT_DIR / "static" / "sw.js"):
        sw_path.write_text(
            sw_path.read_text().replace('"hta-firmware-v1"', f'"hta-firmware-{env.globals["v"]}"')
        )

    print(f"Built {OUT_DIR / 'index.html'} from {len(items)} items")


if __name__ == "__main__":
    main()
