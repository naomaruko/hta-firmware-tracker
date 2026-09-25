"""DiGiCo checker.

Source: DiGiCo's support site runs on Zendesk, which exposes a public JSON
API for its help-center articles. Software-release articles are titled things
like "Quantum Console Software V2126" or, more recently, "V22 Quantum Console
Software" (DiGiCo switched from build-number to marketing-style version
names, so we can't just pick the numerically highest version). Instead we
sort articles by creation date (newest first) and take the first title that
matches each product family.
"""
import re

from app.checkers.base import CheckResult, content_fingerprint, http_get, iso_to_readable_date

ARTICLES_URL = (
    "https://support.digico.biz/api/v2/help_center/en-gb/categories/"
    "26478756671377/articles.json"
)

VERSION_RE = re.compile(r"\bV(\d+(?:\.\d+)*)\b", re.IGNORECASE)

# (checker_key, list of regexes to match against article title, in priority order)
PATTERNS = {
    "digico:quantum": [r"Quantum Console Software"],
    "digico:sd": [r"\bSD Console Software\b"],
    "digico:orangebox": [r"Orange Box Controller"],
    # The DMI-Dante64@96 card exists in two hardware variants with separate
    # firmware lines (Zynq HC 4.2.x, older Summit HC 4.0.x), so they're
    # tracked as two rows - one shared pattern would flip back and forth
    # between whichever line was published most recently.
    "digico:dmidante_zynq": [r"DMI[- ]?Dante.*Zynq.*firmware"],
    "digico:dmidante_summit": [r"DMI[- ]?Dante.*Summit.*firmware"],
}

# Keys whose titles don't carry a "V22"-style version - "...Firmware 4.2.8",
# "...firmware to v4.2.11". Everything else uses VERSION_RE above.
DMI_VERSION_RE = re.compile(r"(?:\bv|firmware\s+)(\d+(?:\.\d+)+)", re.IGNORECASE)
TITLE_VERSION_PATTERNS = {
    "digico:dmidante_zynq": DMI_VERSION_RE,
    "digico:dmidante_summit": DMI_VERSION_RE,
}


def _fetch_articles():
    articles = []
    url = ARTICLES_URL
    params = {"sort_by": "created_at", "sort_order": "desc", "per_page": 100}
    # Zendesk paginates; two pages (200 articles) is more than enough history.
    for _ in range(2):
        r = http_get(url, params=params)
        r.raise_for_status()
        data = r.json()
        articles.extend(data.get("articles", []))
        url = data.get("next_page")
        params = None  # next_page already encodes params
        if not url:
            break
    return articles


def check_all(equipment_items):
    """equipment_items: list of Equipment rows with checker_key starting 'digico:'"""
    try:
        articles = _fetch_articles()
    except Exception as e:  # noqa: BLE001
        return {item.id: CheckResult(None, False, f"Fetch failed: {e}") for item in equipment_items}

    # Resolve the newest matching article per checker_key once.
    resolved = {}
    for key, patterns in PATTERNS.items():
        match = None
        for a in articles:
            title = a.get("title", "")
            if any(re.search(p, title, re.IGNORECASE) for p in patterns):
                if key in TITLE_VERSION_PATTERNS:
                    m = TITLE_VERSION_PATTERNS[key].search(title)
                    version = m.group(1) if m else title
                else:
                    m = VERSION_RE.search(title)
                    version = m.group(0) if m else title
                # New article per release here, so created_at is the release date
                # (unlike SSL's evergreen article, which needs updated_at instead).
                match = CheckResult(
                    version,
                    True,
                    source_url=a.get("html_url"),
                    release_date=iso_to_readable_date(a.get("created_at")),
                    content_hash=content_fingerprint(a.get("body")),
                )
                break
        resolved[key] = match

    results = {}
    for item in equipment_items:
        match = resolved.get(item.checker_key)
        if match:
            results[item.id] = match
        else:
            results[item.id] = CheckResult(
                None, False, "No matching software article found on support.digico.biz"
            )
    return results
