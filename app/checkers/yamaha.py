"""Yamaha checker.

Source: each product's "Downloads" page (e.g.
usa.yamaha.com/products/proaudio/mixers/dm7/downloads.html) has a
`#firmware-table` listing every firmware/software file for sale, with a
genuine manufacturer-published "Last Update" date per row - unlike the old
approach (the standalone /support/updates/<slug>_firm.html release page),
which only gave a version, not a date. A page can have more than one such
table (Yamaha reuses a "related downloads" block across product families -
DM7's page, for instance, also lists the R-series I/O racks it's compatible
with), so every table on a page is searched.

Not every product we track has its own downloads page. DSP-R10/RX/RX-EX/
RPio622/RPio222 share the console's own firmware (see below). Rio1608-D2
and Rio3224-D2 do have one, just not under a URL containing their own
model name - Yamaha groups them under the family name "R Series (AD/DA):
2nd-generation" instead (r_series_adda_2), which is easy to miss searching
by product name alone. HY144-D-SRC genuinely has no page of its own though
(checked every "interfaces" family downloads page against Yamaha's
sitemap.xml, one by one) - its firmware only ever appears as a "compatible
downloads" row on the RIVAGE PM page, which is where that key is pointed
below instead.

Per Yamaha's official RIVAGE PM/DM7/CL/QL/R/Tio compatibility chart
(download.yamaha.com/files/tcm:39-1161321): DSP-R10, DSP-RX, DSP-RX-EX,
RPio622, and RPio222 genuinely share ONE firmware version with the console
itself, so those stay bundled under the rivage_pm slug. Rio3224-D2 and
Rio1608-D2 are on their own separate firmware track entirely from the
console (shown as a distinct column in that chart) - but HTA has confirmed
the two of them ship one identical release between each other (same
version, same changelog, every time), so they're bundled together under
their own rio_d2 slug rather than each getting a separate key.
"""
import re
from urllib.parse import urljoin

from app.checkers.base import CheckResult, http_get, iso_to_readable_date

# Downloads pages that carry a firmware-table for at least one checker_key
# below - fetched once each, not once per checker_key that reads from them.
PAGES = {
    "rivage_pm": "https://usa.yamaha.com/products/proaudio/mixers/rivage_pm/downloads.html",
    "dm7": "https://usa.yamaha.com/products/proaudio/mixers/dm7/downloads.html",
    "swp1": "https://usa.yamaha.com/products/proaudio/network_switches/swp1/downloads.html",
    "r_series_adda_2": "https://usa.yamaha.com/products/proaudio/interfaces/r_series_adda_2/downloads.html",
}

# checker_key -> (which page in PAGES to read, regex matching that row's
# exact link text). Anchored at the start and requiring "Firmware" right
# after the model name so e.g. "HY144-D-SRC Firmware" can't accidentally
# match the "HY144-D Firmware" row (a different, untracked product one
# prefix short of it), and "Rio1608-D2 Firmware" can't match "Rio1608-D3".
# rio_d2 matches whichever of the two model names' rows comes first on the
# page - Rio1608-D2 and Rio3224-D2 ship one identical release (confirmed by
# HTA), so either row carries the version that applies to both.
ROWS = {
    "yamaha:rivage_pm": ("rivage_pm", re.compile(r"^RIVAGE PM Firmware\b")),
    "yamaha:dm7": ("dm7", re.compile(r"^DM7 Firmware\b")),
    "yamaha:swp1": ("swp1", re.compile(r"^SWP1 Firmware\b")),
    "yamaha:hy144dsrc": ("rivage_pm", re.compile(r"^HY144-D-SRC Firmware\b")),
    "yamaha:rio_d2": ("r_series_adda_2", re.compile(r"^Rio(?:1608|3224)-D2 Firmware\b")),
}

VERSION_RE = re.compile(r"V([\d]+(?:\.[\d]+)*)", re.IGNORECASE)


def _fetch_rows(url):
    """Every (name, date, absolute_href) row from every #firmware-table on
    a downloads page."""
    from bs4 import BeautifulSoup

    r = http_get(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    rows = []
    for table in soup.find_all("table", id="firmware-table"):
        for tr in table.find_all("tr")[1:]:  # skip the header row
            a = tr.find("a")
            tds = tr.find_all("td")
            if not a or not tds:
                continue
            name = a.get_text(strip=True)
            date = tds[-1].get_text(strip=True)
            href = urljoin(url, a.get("href", ""))
            rows.append((name, date, href))
    return rows


def check_all(equipment_items):
    needed_keys = {item.checker_key for item in equipment_items}
    needed_pages = {ROWS[k][0] for k in needed_keys if k in ROWS}

    page_rows = {}
    page_errors = {}
    for page_key in needed_pages:
        try:
            page_rows[page_key] = _fetch_rows(PAGES[page_key])
        except Exception as e:  # noqa: BLE001
            page_errors[page_key] = f"Fetch failed: {e}"

    resolved = {}
    for key in needed_keys:
        if key not in ROWS:
            continue
        page_key, pattern = ROWS[key]
        if page_key in page_errors:
            resolved[key] = CheckResult(None, False, page_errors[page_key])
            continue
        rows = page_rows.get(page_key, [])
        match = next(((n, d, h) for n, d, h in rows if pattern.search(n)), None)
        if not match:
            resolved[key] = CheckResult(
                None, False, f"No row matching {pattern.pattern!r} on {PAGES[page_key]}"
            )
            continue
        name, date, href = match
        vm = VERSION_RE.search(name)
        if not vm:
            resolved[key] = CheckResult(None, False, f"Could not find version in row text: {name!r}")
            continue
        resolved[key] = CheckResult(
            vm.group(0), True, source_url=href, release_date=iso_to_readable_date(date)
        )

    results = {}
    for item in equipment_items:
        results[item.id] = resolved.get(
            item.checker_key, CheckResult(None, False, "Unknown Yamaha checker key")
        )
    return results
