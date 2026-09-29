"""Allen & Heath checker.

Version source: allen-heath.com's dLive resources page blocks plain HTTP
requests (403, likely bot protection) but loads fine in a real browser. The
"Firmware Downloads" section shows the current version as plain text, e.g.
"dLive Firmware V2.12" - covers the whole dLive family (S-Class surfaces,
C-Class surfaces, and DM-Class MixRacks alike), so one fetch covers both
S5000 and DM64 MixRack.

Release date source: a different site entirely - support.allen-heath.com,
Allen & Heath's help centre. That one's behind an actual Cloudflare
challenge page ("Performing security verification"), which blocks even a
real headless browser, so the HTML page itself is a dead end. It's Zendesk
underneath though (same platform DiGiCo and SSL run on), and Zendesk's
public JSON API isn't behind that challenge - so this reads the API
directly rather than the page. One evergreen article ("dLive Firmware
Release Notes") covers the whole version history, edited in place for each
release rather than DiGiCo's one-article-per-release - its body reads
"Current Version Release Notes / Version 2.12 - Maintenance Release.
January 2026 / [...] / Previous Version Release Notes / Version 2.11 -
... July 2025 / ...", so taking the *first* "Version X.YY - ... Month
YYYY" match is what gets the current one, not a stale older entry. Only a
month and year is ever stated, never a day.
"""
import re

from app.checkers.base import CheckResult, abbreviate_month, http_get
from app.checkers.browser_base import browser_page

DLIVE_URL = "https://www.allen-heath.com/hardware/dlive-series/all-models/resources/"
VERSION_RE = re.compile(r"dLive Firmware\s+V([\d.]+)", re.IGNORECASE)

# The release-notes article lives in this one help-centre section - listing
# the section (rather than hardcoding the article's own id) means a future
# article replacing this one (rather than continuing to edit it in place)
# still gets picked up automatically, same reasoning as DiGiCo/SSL.
RELEASE_NOTES_SECTION_URL = (
    "https://support.allen-heath.com/api/v2/help_center/en-gb/sections/"
    "42052149659153/articles.json"
)
RELEASE_DATE_RE = re.compile(r"Version\s+[\d.]+\s*-[^.]*\.\s*([A-Za-z]+ \d{4})")


def _fetch_dlive_version():
    with browser_page() as page:
        page.goto(DLIVE_URL, wait_until="networkidle")
        text = page.inner_text("body")
    m = VERSION_RE.search(text)
    if not m:
        raise ValueError("Version pattern not found on page")
    return f"V{m.group(1)}"


def _fetch_dlive_release_date():
    from bs4 import BeautifulSoup

    r = http_get(RELEASE_NOTES_SECTION_URL, params={"sort_by": "created_at", "sort_order": "desc", "per_page": 1})
    r.raise_for_status()
    articles = r.json().get("articles", [])
    if not articles:
        raise ValueError("No articles found in dLive release-notes section")
    article = articles[0]
    text = BeautifulSoup(article["body"], "lxml").get_text(" ", strip=True)
    m = RELEASE_DATE_RE.search(text)
    if not m:
        raise ValueError(f"Release-date pattern not found in article {article['id']}")
    return abbreviate_month(m.group(1)), article["html_url"]


def check_all(equipment_items):
    try:
        version = _fetch_dlive_version()
    except Exception as e:  # noqa: BLE001
        result = CheckResult(None, False, f"Fetch failed: {e}", source_url=DLIVE_URL)
        return {item.id: result for item in equipment_items}

    # The release date is a nice-to-have on top of a working version check,
    # not a requirement - a change to Allen & Heath's help centre shouldn't
    # turn a perfectly good version check into a failed one.
    release_date = None
    try:
        release_date, _ = _fetch_dlive_release_date()
    except Exception:  # noqa: BLE001
        pass

    result = CheckResult(version, True, source_url=DLIVE_URL, release_date=release_date)
    return {item.id: result for item in equipment_items}
