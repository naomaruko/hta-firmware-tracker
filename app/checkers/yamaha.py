"""Yamaha checker.

Source: each product's "Resources" page (e.g.
usa.yamaha.com/business/audio/products/mixers/dm7/resources.html) lists every
firmware/software file for the product, with a genuine manufacturer-published
"Last Update" date per entry - unlike the old standalone
/support/updates/<slug>_firm.html release pages, which only gave a version.
A page can list files for more than one product (Yamaha reuses a "related
downloads" block across product families - DM7's page, for instance, also
lists the R-series I/O racks it's compatible with), so every entry on a page
is searched.

How the list is read changed on 2026-11-10, when Yamaha moved these pages from
/products/proaudio/.../downloads.html to /business/audio/.../resources.html
(the old URLs redirect). The old page had the list as a server-rendered
`#firmware-table`; the new one ships empty tables and a script fills them from
Yamaha's search service (yamaha.search.zetacx.net/api/search/assets) - so the
checker saw a perfectly good page (HTTP 200) with no firmware on it, and every
Yamaha item failed with "No row matching ...". That service refuses plain HTTP
requests (403) but answers the page's own request, so the checker opens the
page in the headless browser, copies the firmware search request the page
itself makes (so the product list and settings are whatever Yamaha currently
uses, not hard-coded IDs), and replays it asking for up to 200 entries rather
than the page's 6. Each entry has a name ("RIVAGE PM Firmware V7.20"), a link
to its release page and an ISO last-update date.

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
version, same changelog, every time), so they share their own rio_d2 slug
rather than each getting a separate key. But Yamaha still lists them as two
separate rows, so each is read from its own row (PER_MODEL_KEYS below) -
if one ever gets a version the other doesn't, they report separately
instead of one silently standing in for both.
"""
import json
import re
from urllib.parse import urljoin

from app.checkers.base import CheckResult, iso_to_readable_date
from app.checkers.browser_base import browser_page, describe_browser_page

# Resource pages that list firmware for at least one checker_key below -
# fetched once each, not once per checker_key that reads from them.
PAGES = {
    "rivage_pm": "https://usa.yamaha.com/business/audio/products/mixers/rivage-pm/resources.html",
    "dm7": "https://usa.yamaha.com/business/audio/products/mixers/dm7/resources.html",
    "swp1": "https://usa.yamaha.com/business/audio/products/network-devices/swp1/resources.html",
    "r_series_adda_2": "https://usa.yamaha.com/business/audio/products/interfaces/r-series-adda-2/resources.html",
}

SITE = "https://usa.yamaha.com"
SEARCH_API = "https://yamaha.search.zetacx.net/api/search/assets"
PAGE_SIZE = 200  # the API's maximum ("must be 200 or less")

# checker_key -> (which page in PAGES to read, regex matching that row's
# exact link text). Anchored at the start and requiring "Firmware" right
# after the model name so e.g. "HY144-D-SRC Firmware" can't accidentally
# match the "HY144-D Firmware" row (a different, untracked product one
# prefix short of it), and "Rio1608-D2 Firmware" can't match "Rio1608-D3".
# rio_d2's pattern here only decides which page to read; each of its models
# is matched to its own row by name (see PER_MODEL_KEYS).
ROWS = {
    "yamaha:rivage_pm": ("rivage_pm", re.compile(r"^RIVAGE PM Firmware\b")),
    "yamaha:dm7": ("dm7", re.compile(r"^DM7 Firmware\b")),
    "yamaha:swp1": ("swp1", re.compile(r"^SWP1 Firmware\b")),
    "yamaha:hy144dsrc": ("rivage_pm", re.compile(r"^HY144-D-SRC Firmware\b")),
    "yamaha:rio_d2": ("r_series_adda_2", re.compile(r"^Rio(?:1608|3224)-D2 Firmware\b")),
}

# Keys whose members each have their own row on the page, matched by model
# name instead of sharing one result.
PER_MODEL_KEYS = {"yamaha:rio_d2"}

VERSION_RE = re.compile(r"V([\d]+(?:\.[\d]+)*)", re.IGNORECASE)


_FETCH_JS = """async (fields) => {
  const fd = new FormData();
  for (const [k, v] of fields) fd.append(k, v);
  const r = await fetch(%s, {method: 'POST', body: fd});
  return {status: r.status, text: await r.text()};
}""" % json.dumps(SEARCH_API)


def _form_fields(post_data):
    """[(name, value)] from the multipart body of the page's search request."""
    return [
        (m.group(1), m.group(2))
        for m in re.finditer(r'name="([^"]+)"\r?\n\r?\n(.*?)\r?\n------', (post_data or "") + "\n------", re.S)
    ]


def _is_firmware_search(request):
    return (
        "zetacx.net/api/search/assets" in request.url
        and request.method == "POST"
        and "downloadType" in (request.post_data or "")
    )


def _fetch_rows(page, url):
    """(rows, description) for one resources page: every (name, date,
    absolute_href) entry Yamaha lists for it - date being the ISO last-update
    timestamp - plus a one-line description of the page itself for failure
    messages. See the module docstring for how."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    resp = None
    try:
        with page.expect_request(_is_firmware_search, timeout=25_000) as captured:
            resp = page.goto(url, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        raise ValueError(
            "The page never made its firmware search request - has Yamaha changed the page again? "
            f"({describe_browser_page(page, resp.status if resp else None)})"
        ) from None
    status = resp.status if resp else None
    base_fields = _form_fields(captured.value.post_data)
    if not base_fields:
        raise ValueError(f"Couldn't read the page's firmware search request ({describe_browser_page(page, status)})")

    rows, offset = [], 0
    while True:
        fields = [(k, str(PAGE_SIZE) if k == "limit" else str(offset) if k == "offset" else v) for k, v in base_fields]
        out = page.evaluate(_FETCH_JS, fields)
        if out["status"] != 200:
            raise ValueError(f"Yamaha's search service answered HTTP {out['status']}: {out['text'][:150]!r}")
        data = json.loads(out["text"])
        assets = data.get("assetsList", [])
        rows += [
            (a.get("assetName", ""), a.get("lastUpdateDate", ""), urljoin(SITE, a.get("assetUrl", "")))
            for a in assets
        ]
        offset += len(assets)
        if not assets or offset >= int(data.get("numberOfSearches") or 0) or offset >= 5 * PAGE_SIZE:
            break
    return rows, describe_browser_page(page, status, f"{len(rows)} downloads listed")


def check_all(equipment_items):
    needed_keys = {item.checker_key for item in equipment_items}
    needed_pages = {ROWS[k][0] for k in needed_keys if k in ROWS}

    page_rows = {}
    page_info = {}
    page_errors = {}
    if needed_pages:
        try:
            with browser_page() as page:
                for page_key in sorted(needed_pages):
                    try:
                        page_rows[page_key], page_info[page_key] = _fetch_rows(page, PAGES[page_key])
                    except Exception as e:  # noqa: BLE001
                        page_errors[page_key] = f"Fetch failed: {str(e).splitlines()[0] if str(e) else e.__class__.__name__}"
        except Exception as e:  # noqa: BLE001
            for page_key in needed_pages - set(page_rows) - set(page_errors):
                page_errors[page_key] = f"Browser session failed: {str(e).splitlines()[0] if str(e) else e.__class__.__name__}"

    def resolve(page_key, pattern):
        if page_key in page_errors:
            return CheckResult(None, False, page_errors[page_key])
        rows = page_rows.get(page_key, [])
        match = next(((n, d, h) for n, d, h in rows if pattern.search(n)), None)
        if not match:
            return CheckResult(
                None, False, f"No row matching {pattern.pattern!r} on {PAGES[page_key]} ({page_info[page_key]})"
            )
        name, date, href = match
        vm = VERSION_RE.search(name)
        if not vm:
            return CheckResult(None, False, f"Could not find version in row text: {name!r}")
        return CheckResult(vm.group(0), True, source_url=href, release_date=iso_to_readable_date(date))

    resolved = {}
    for key in needed_keys:
        if key in ROWS and key not in PER_MODEL_KEYS:
            page_key, pattern = ROWS[key]
            resolved[key] = resolve(page_key, pattern)

    results = {}
    for item in equipment_items:
        if item.checker_key in PER_MODEL_KEYS:
            page_key = ROWS[item.checker_key][0]
            pattern = re.compile(rf"^{re.escape(item.model)} Firmware\b")
            results[item.id] = resolve(page_key, pattern)
        else:
            results[item.id] = resolved.get(
                item.checker_key, CheckResult(None, False, "Unknown Yamaha checker key")
            )
    return results
