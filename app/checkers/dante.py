"""Dante/Audinate checker.

Source: getdante.com's software-downloads page is an accordion - the version
table for each product ("Dante Controller v4.18.1.2 Package (Windows)") only
appears in the DOM after its section header is clicked, so a plain HTTP fetch
sees nothing. The clickable header is `a.toggle-software`.

The section lists one build per platform, each with its own version number
("v4.18.1.2 Package (Windows)", "v4.18.1.1 Package (Apple Silicon)", ...),
and they don't always move together - so every platform is returned, not
just Windows.
"""
import re

from app.checkers.base import CheckResult, newest_version
from app.checkers.browser_base import browser_page

DOWNLOADS_URL = "https://www.getdante.com/resources/software-downloads/"

VERSION_RE = re.compile(r"Dante Controller\s+v([\d.]+)\s+Package\s*\(([^)]+)\)", re.IGNORECASE)

# How the page labels each build -> how we show it (the page's "Apple
# Silicon" doesn't say it's a Mac build on its own). Anything unrecognised is
# shown exactly as the page writes it, so a new platform still appears.
PLATFORM_NAMES = {
    "windows": "Windows",
    "apple silicon": "macOS Apple Silicon",
    "macos intel": "macOS Intel",
}


def _fetch_dante_controller_versions():
    with browser_page() as page:
        page.goto(DOWNLOADS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.locator("a.toggle-software").filter(has_text="Dante Controller").first.click()
        page.wait_for_timeout(1500)
        text = page.inner_text("body")
    platforms = {}
    for version, label in VERSION_RE.findall(text):
        name = PLATFORM_NAMES.get(label.strip().lower(), label.strip())
        platforms.setdefault(name, version)
    if not platforms:
        raise ValueError("Version pattern not found after expanding Dante Controller section")
    return platforms


def check_all(equipment_items):
    try:
        platforms = _fetch_dante_controller_versions()
        result = CheckResult(
            newest_version(platforms.values()), True, source_url=DOWNLOADS_URL, platforms=platforms
        )
    except Exception as e:  # noqa: BLE001
        result = CheckResult(None, False, f"Fetch failed: {e}", source_url=DOWNLOADS_URL)

    return {item.id: result for item in equipment_items}
