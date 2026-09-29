"""Dante/Audinate checker.

Source: getdante.com's software-downloads page is an accordion - the version
table for each product ("Dante Controller v4.18.1.2 Package (Windows)") only
appears in the DOM after its section header is clicked, so a plain HTTP fetch
sees nothing. The clickable header is `a.toggle-software`.

The section lists one build per platform, each with its own version number
("v4.18.1.2 Package (Windows)", "v4.18.1.1 Package (Apple Silicon)", ...),
and they don't always move together - so every platform is returned, not
just Windows.

Each platform's entry also links to its own "Release Notes" page (e.g.
getdante.com/releases/dante-controller/windows/dante-controller-v4-18-1-2-
package-windows/), which states a real release date ("Release Date: 15th of
July 2026") - that page loads fine with a plain fetch (unlike the accordion
itself), so once the accordion gives us those three URLs, the dates come
from three ordinary GETs rather than more browser automation. A date-fetch
failure for one platform doesn't affect the others or fail the version
check as a whole - version tracking is the part that actually matters.
"""
import datetime as dt
import re

from app.checkers.base import CheckResult, http_get, newest_version
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

# "Release Date: 15th of July 2026" - ordinal suffix and "of" are dropped
# rather than relied on (in case a future date lands on a day whose suffix
# we get wrong), just the day/month/year numbers matter.
RELEASE_DATE_RE = re.compile(r"Release Date:\s*(\d{1,2})\w*\s*(?:of\s+)?([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)


def _parse_release_date(text):
    m = RELEASE_DATE_RE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    try:
        return dt.datetime.strptime(f"{day} {month} {year}", "%d %B %Y").strftime("%b %-d, %Y")
    except ValueError:
        return None


def _fetch_dante_controller_platforms():
    """{platform name: version}, {platform name: its Release Notes URL}."""
    with browser_page() as page:
        page.goto(DOWNLOADS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.locator("a.toggle-software").filter(has_text="Dante Controller").first.click()
        page.wait_for_timeout(1500)
        rows_locator = page.locator("li#dante-controller ul.platforms > li")
        rows = []
        for i in range(rows_locator.count()):
            li = rows_locator.nth(i)
            title = li.locator("h3").inner_text()
            notes_link = li.locator("a", has_text="Release Notes")
            href = notes_link.get_attribute("href") if notes_link.count() else None
            rows.append((title, href))

    platforms = {}
    release_notes_urls = {}
    for title, href in rows:
        m = VERSION_RE.search(title)
        if not m:
            continue
        version, label = m.groups()
        name = PLATFORM_NAMES.get(label.strip().lower(), label.strip())
        platforms.setdefault(name, version)
        if href:
            release_notes_urls.setdefault(name, href)

    if not platforms:
        raise ValueError("Version pattern not found after expanding Dante Controller section")
    return platforms, release_notes_urls


def _fetch_platform_release_dates(release_notes_urls):
    dates = {}
    for name, url in release_notes_urls.items():
        try:
            r = http_get(url)
            r.raise_for_status()
        except Exception:  # noqa: BLE001
            continue
        date = _parse_release_date(r.text)
        if date:
            dates[name] = date
    return dates


def check_all(equipment_items):
    try:
        platforms, release_notes_urls = _fetch_dante_controller_platforms()
    except Exception as e:  # noqa: BLE001
        result = CheckResult(None, False, f"Fetch failed: {e}", source_url=DOWNLOADS_URL)
        return {item.id: result for item in equipment_items}

    # Best-effort on top of an already-successful version check, same
    # reasoning as every other checker's release_date: never lets a broken
    # release-notes page turn a working version check into a failed one.
    platform_release_dates = _fetch_platform_release_dates(release_notes_urls)

    newest = newest_version(platforms.values())
    # The headline release_date (shown in the main table/card before the row
    # is expanded) is whichever platform's version *is* that newest version -
    # same idea as current_version already being the newest platform version.
    top_release_date = next(
        (platform_release_dates.get(name) for name, version in platforms.items() if version == newest),
        None,
    )

    result = CheckResult(
        newest,
        True,
        source_url=DOWNLOADS_URL,
        release_date=top_release_date,
        platforms=platforms,
        platform_release_dates=platform_release_dates,
    )
    return {item.id: result for item in equipment_items}
