"""Dante/Audinate checker.

Source: getdante.com's software-downloads page is an accordion - the version
table for each product ("Dante Controller v4.18.1.2 Package (Windows)") only
appears in the DOM after its section header is clicked, so a plain HTTP fetch
sees nothing. The clickable header is `a.toggle-software`.
"""
import re

from app.checkers.base import CheckResult
from app.checkers.browser_base import browser_page

DOWNLOADS_URL = "https://www.getdante.com/resources/software-downloads/"

VERSION_RE = re.compile(r"Dante Controller\s+v([\d.]+)\s+Package\s*\(Windows\)", re.IGNORECASE)


def _fetch_dante_controller_version():
    with browser_page() as page:
        page.goto(DOWNLOADS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.locator("a.toggle-software").filter(has_text="Dante Controller").first.click()
        page.wait_for_timeout(1500)
        text = page.inner_text("body")
    m = VERSION_RE.search(text)
    if not m:
        raise ValueError("Version pattern not found after expanding Dante Controller section")
    return m.group(1)


def check_all(equipment_items):
    try:
        version = _fetch_dante_controller_version()
        result = CheckResult(version, True, source_url=DOWNLOADS_URL)
    except Exception as e:  # noqa: BLE001
        result = CheckResult(None, False, f"Fetch failed: {e}", source_url=DOWNLOADS_URL)

    return {item.id: result for item in equipment_items}
