"""Shure checker.

Source: shure.com used to have a static per-product firmware archive page at
/en-US/support/downloads/software-firmware-archive/<slug>, server-rendered
and fetchable with a plain GET. As of Aug 2026, Shure restructured that
section: most of those per-product detail pages now either 500 or render
blank (the version table never populates - the "Shure Page" fallback title
in both cases, so it looks the same as a genuinely missing page). The
underlying data didn't go away though - it moved to a single searchable/
filterable archive listing at .../software-firmware-archive, which is
JS-rendered (results load client-side), so this now needs a real browser
like the d&b/Allen & Heath checkers rather than a plain fetch.

The listing accepts a `?q=<search term>` URL param that pre-filters results
on load, but the search is fuzzy (searching "AD610" can surface AD600 rows
first, "SBC240" surfaces SBC441/SBC840 rows, etc.) - so each checker key
carries both a search term AND a distinctive prefix of that product's exact
"Release Title" text, and we scan the page for the first version number
following that specific title, not just the first row back.
"""
import re

from app.checkers.base import CheckResult
from app.checkers.browser_base import browser_page, dismiss_cookie_banner

LISTING_URL = "https://www.shure.com/en-US/support/downloads/software-firmware-archive"

# checker_key -> (search term, distinctive prefix of the exact "Release
# Title" text on the archive listing - used to pick the right row out of the
# fuzzy search results, not just the first one back).
PRODUCTS = {
    "shure:ad_transmitters": (
        "AD1 AD2 ADX1 ADX2 transmitters",
        "Axient Digital Transmitters - AD1, AD2, ADX1",
    ),
    "shure:ad4q": ("AD4Q", "AD4Q - Axient Digital Four-Channel Receiver"),
    "shure:ad600": ("AD600", "AD600 - Axient Digital Spectrum Manager"),
    "shure:ad610": ("AD610", "AD610 - Axient Digital Diversity ShowLink"),
    "shure:ad8c": ("AD8C", "AD8C - Axient Digital PSM 8-Port Antenna Combiner"),
    "shure:adxr": ("ADXR", "ADXR - Axient Digital PSM Wireless Bodypack Receiver"),
    # Shure publishes ADTD/ADTQ firmware as its own release (currently the
    # same version as ADXR, but a separate listing) - tracked on its own so
    # the row's source link is the ADTQ search, not ADXR's.
    "shure:adtq": ("ADTQ", "ADTD and ADTQ - Axient Digital PSM Wireless Transmitters"),
    "shure:sbc441": ("SBC441", "SBC441 - Axient Digital PSM 4-Bay Docking Charger"),
    "shure:sbc240": ("SBC240", "SBC220/240 - 2-Bay Chargers"),
    "shure:sbrc": ("SBRC", "SBRC - Shure Battery Rack Charger"),
}


def _pattern_for(title_prefix):
    # Bounded, DOTALL gap between the title and its version/date, same
    # approach as the d&b checker - the row's other fields (type badge,
    # associated-products list, download-button text) sit in between in the
    # rendered text and vary in length, so this can't be a fixed offset.
    return re.compile(
        re.escape(title_prefix) + r".{0,40}?\s+([\d.]+)\s*See Release Notes\s*([A-Za-z]+ \d{1,2},?\s*\d{4})",
        re.DOTALL,
    )


def _fetch_one(page, term, title_prefix):
    url = f"{LISTING_URL}?q={term.replace(' ', '+')}&size=n_10_n&sort-field=versionreleasedate&sort-direction=desc"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1800)
    text = page.inner_text("main")
    m = _pattern_for(title_prefix).search(text)
    if not m:
        raise ValueError(f"No row matching {title_prefix!r} in search results for {term!r}")
    return m.group(1), m.group(2), url


def check_all(equipment_items):
    needed_keys = {item.checker_key for item in equipment_items}
    resolved = {}

    try:
        with browser_page() as page:
            page.goto(LISTING_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            dismiss_cookie_banner(page)
            page.wait_for_timeout(300)

            for key in needed_keys:
                product = PRODUCTS.get(key)
                if not product:
                    resolved[key] = CheckResult(None, False, "Unknown Shure checker key")
                    continue
                term, title_prefix = product
                try:
                    version, date, url = _fetch_one(page, term, title_prefix)
                    resolved[key] = CheckResult(version, True, source_url=url, release_date=date)
                except Exception as e:  # noqa: BLE001
                    resolved[key] = CheckResult(None, False, f"Fetch failed: {e}", source_url=LISTING_URL)
    except Exception as e:  # noqa: BLE001
        for key in needed_keys:
            resolved[key] = CheckResult(None, False, f"Browser session failed: {e}")

    results = {}
    for item in equipment_items:
        results[item.id] = resolved.get(item.checker_key, CheckResult(None, False, "Unknown Shure checker key"))
    return results
