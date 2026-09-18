"""d&b audiotechnik checker.

Source: dbaudio.com's Download Center is a search-driven file archive
(software, firmware, manuals, datasheets all mixed together). Results render
client-side after typing into the search box and hitting Enter, and a cookie
consent overlay blocks clicks until dismissed - so this needs a real browser,
not a plain fetch. D40 and D90 amplifiers share one combined firmware release
("D90/D40/D25/40D/25D Firmware Release notes"). DN1 Switch has its own
separate release ("DN1 Firmware Release notes").
"""
import datetime as dt
import re

from app.checkers.base import CheckResult
from app.checkers.browser_base import browser_page, dismiss_cookie_banner

DOWNLOADS_URL = "https://www.dbaudio.com/global/en/service-and-support/downloads/"

# checker_key -> (search term, regex to pull the version + posted date out of
# the result row - rows look like "<title> <version>\nFirmware\nPDF\n119
# KB\nEnglish \n27.05.2026", so the date is a bounded reluctant match after
# the version rather than a fixed distance, in case the category/filetype/
# size fields ever shift.)
QUERIES = {
    "db:d40d90": (
        "D40 Firmware Release notes",
        re.compile(
            r"D90/D40/D25/40D/25D Firmware Release notes\s+([\d.]+).{0,80}?(\d{2}\.\d{2}\.\d{4})",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    "db:dn1": (
        "DN1 Firmware Release notes",
        re.compile(
            r"DN1 Firmware Release notes\s+([\d.]+).{0,80}?(\d{2}\.\d{2}\.\d{4})",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
}


def _fmt_ddmmyyyy(date_str):
    """d&b dates are DD.MM.YYYY -> "March 20, 2026", or the raw string if
    that assumption turns out wrong for some row."""
    try:
        return dt.datetime.strptime(date_str, "%d.%m.%Y").strftime("%B %-d, %Y")
    except ValueError:
        return date_str


def _search(page, term, pattern):
    page.fill("input[name='searchTerm']", term)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)
    text = page.inner_text("body")
    m = pattern.search(text)
    if not m:
        raise ValueError(f"No result matching pattern for search {term!r}")
    return m.group(1), _fmt_ddmmyyyy(m.group(2))


def check_all(equipment_items):
    needed_keys = {item.checker_key for item in equipment_items}
    resolved = {}

    try:
        with browser_page() as page:
            page.goto(DOWNLOADS_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            dismiss_cookie_banner(page)
            page.wait_for_timeout(300)

            for key in needed_keys:
                query = QUERIES.get(key)
                if not query:
                    resolved[key] = CheckResult(None, False, "Unknown d&b checker key")
                    continue
                term, pattern = query
                try:
                    version, release_date = _search(page, term, pattern)
                    resolved[key] = CheckResult(version, True, source_url=page.url, release_date=release_date)
                except Exception as e:  # noqa: BLE001
                    resolved[key] = CheckResult(None, False, f"Fetch failed: {e}", source_url=DOWNLOADS_URL)
    except Exception as e:  # noqa: BLE001
        for key in needed_keys:
            resolved[key] = CheckResult(None, False, f"Browser session failed: {e}")

    results = {}
    for item in equipment_items:
        results[item.id] = resolved.get(item.checker_key, CheckResult(None, False, "Unknown d&b checker key"))
    return results
