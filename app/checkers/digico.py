"""DiGiCo checker.

Source: DiGiCo's support site runs on Zendesk, which exposes a public JSON
API for its help-center articles. Software-release articles are titled things
like "Quantum Console Software V2126" or, more recently, "V22 Quantum Console
Software" (DiGiCo switched from build-number to marketing-style version
names, so we can't just pick the numerically highest version). Instead we
sort articles by creation date (newest first) and take the first title that
matches each product family.

Console software (Quantum, SD) is the exception to "the title is the version":
DiGiCo keeps one article per major release (e.g. "V22 Quantum Console
Software") and edits it in place as point releases ship - v2242 in June, then
v2242.4 in October for only the Q1/Q2 consoles - without touching the title
or creation date. The real versions are in the download buttons in the
article body, one per model, with the version in the file name and the
upload month in its path:

    <span class="download-link"
          data-link=".../uploads/2026/10/Quantum1_V2242-4x_Update_Package.zip">Quantum 112</span>

So for those two keys each tracked model is matched to its own button and
gets its own version and release month. Models in one family can therefore
differ, which the dashboard and Slack alerts are built to show (a family is
one row only while every member agrees).
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

from app.checkers.base import CheckResult, http_get, iso_to_readable_date

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

# Keys whose versions are read per model from the article's download buttons
# rather than from its title (see the module docstring).
PER_MODEL_KEYS = {"digico:quantum", "digico:sd"}

# ".../uploads/2026/10/Quantum1_V2242-4x_Update_Package.zip" -> year, month,
# "2242", "4". The trailing letter (x/z) is a build flavour, not part of the
# version DiGiCo quotes (v2242.4).
PACKAGE_RE = re.compile(r"/uploads/(\d{4})/(\d{2})/[^/]*?_V(\d+)(?:-(\d+))?[a-z]*_[^/]*\.zip", re.IGNORECASE)


def _download_links(article):
    """[(label, url)] for every download button in an article body."""
    soup = BeautifulSoup(article.get("body") or "", "lxml")
    links = []
    for el in soup.find_all(True):
        url = el.get("data-link") or (el.get("href") if el.name == "a" else None)
        if url and url.lower().split("?")[0].endswith(".zip"):
            links.append((el.get_text(" ", strip=True), url))
    return links


def _norm(name):
    """Comparable form of a model name: lower-case, single spaces, and
    DiGiCo's "Dual Screen" folded into "DS", so the article's "Quantum 225
    Dual Screen" button matches our "Quantum 225DS" (and "Quantum 225 DS")."""
    name = re.sub(r"\s+", " ", name).strip().lower()
    name = re.sub(r"\s*dual screen$", "ds", name)
    return re.sub(r"\s+ds$", "ds", name)


def _label_models(label):
    """Model names a download button covers (normalised): "Quantum 326 &
    338" is both "Quantum 326" and "Quantum 338"; "Quantum 225 Dual Screen"
    is only the DS model, so it never matches the plain "Quantum 225"."""
    parts = [p.strip() for p in label.split("&") if p.strip()]
    m = re.match(r"^(\D*)\d", parts[0]) if parts else None
    prefix = m.group(1) if m else ""
    return {_norm(p if i == 0 or not p[:1].isdigit() else prefix + p) for i, p in enumerate(parts)}


def _per_model_result(article, links, model):
    """The CheckResult for one tracked model, from its own download button."""
    if article is None:
        return CheckResult(None, False, "No matching software article found on support.digico.biz")
    title = article.get("title", "")
    if not links:
        return CheckResult(
            None, False,
            f"No download links found in {title!r} - has the article layout changed?",
            source_url=article.get("html_url"),
        )
    wanted = _norm(model)
    url = next((u for label, u in links if wanted in _label_models(label)), None)
    if url is None:
        return CheckResult(None, False, f"{model} isn't listed in {title!r}'s download links", source_url=article.get("html_url"))
    m = PACKAGE_RE.search(url)
    if not m:
        return CheckResult(None, False, f"Couldn't read a version from the download link {url.rsplit('/', 1)[-1]!r}", source_url=article.get("html_url"))
    year, month, major, minor = m.groups()
    version = f"V{major}" + (f".{minor}" if minor else "")
    release = dt.date(int(year), int(month), 1).strftime("%b %Y")
    return CheckResult(version, True, source_url=article.get("html_url"), release_date=release)


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
    articles_by_key = {}  # per-model keys: (article, its download links)
    for key, patterns in PATTERNS.items():
        match = None
        found = None
        for a in articles:
            title = a.get("title", "")
            if any(re.search(p, title, re.IGNORECASE) for p in patterns):
                found = a
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
                )
                break
        resolved[key] = match
        if key in PER_MODEL_KEYS:
            articles_by_key[key] = (found, _download_links(found) if found else [])

    results = {}
    for item in equipment_items:
        if item.checker_key in PER_MODEL_KEYS:
            article, links = articles_by_key.get(item.checker_key, (None, []))
            results[item.id] = _per_model_result(article, links, item.model)
            continue
        match = resolved.get(item.checker_key)
        if match:
            results[item.id] = match
        else:
            results[item.id] = CheckResult(
                None, False, "No matching software article found on support.digico.biz"
            )
    return results
