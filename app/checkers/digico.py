"""DiGiCo checker.

Source: DiGiCo's support site runs on Zendesk, which exposes a public JSON
API for its help-center articles. Software-release articles are titled things
like "Quantum Console Software V2126" or, more recently, "V22 Quantum Console
Software" (DiGiCo switched from build-number to marketing-style version
names, so we can't just pick the numerically highest version). Instead we
sort articles by creation date (newest first) and take the first title that
matches each product family.

Console software (Quantum, SD) is the exception to "the title is the version",
in two ways:

1. DiGiCo keeps one article per major release and edits it in place as point
   releases ship - v2242 in June, then v2242.4 in October for only the Q1/Q2
   consoles - without touching the title or creation date. The real versions
   are in the per-model download links in the article body, with the version
   in the file name and the upload month in its path
   (.../uploads/2026/10/Quantum1_V2242-4x_Update_Package.zip). Each tracked
   model is matched to its own link and gets its own version and release
   month, so models in one family can differ (the dashboard and Slack alerts
   are built to show that).

2. DiGiCo reorganises these articles without notice. The title has been
   "Quantum Console Software V2126", then "V22 Quantum Console Software", then
   "Version 22 Quantum Software"; the download links were <span data-link>
   buttons, then <option value> entries in a dropdown (with "Quantum 326 &
   338" becoming "Quantum 326 / 338"). A checker that picks the article by
   title silently falls back to an *older* article the day a rename stops
   matching - on 2026-11-06 that recorded V1619 and V2126 as new "updates".
   So the article is chosen by what's in it, not what it's called: the newest
   one whose body has console update packages (Update_Package.zip) for the
   family. And because a layout change could still leave the newest article
   unreadable, a tripwire fails the check loudly - rather than reading an
   older article - if a newer article's title looks like this family's console
   software but it has no links we can read.
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
# Quantum and SD console software aren't here: their article is chosen by its
# contents, not its title (see PER_MODEL_PACKAGES below and the module
# docstring).
PATTERNS = {
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

# Keys whose versions are read per model from console-software download
# links, not from an article title: checker_key -> the file-name prefix of that
# family's update packages ("Quantum1_V2242-4x_Update_Package.zip",
# "SD10_V2242z_Update_Package.zip"). Offline installers and session converters
# have different names, so they never count.
PER_MODEL_PACKAGES = {
    "digico:quantum": re.compile(r"^Quantum\d", re.IGNORECASE),
    "digico:sd": re.compile(r"^SD\d", re.IGNORECASE),
}
PER_MODEL_KEYS = set(PER_MODEL_PACKAGES)

# Tripwire: titles that look like a family's console-software article, used
# only to notice when a newer one than the article we read exists (see
# _select_console_article). Offline/converter articles are different products.
LOOKALIKE_TITLES = {
    "digico:quantum": re.compile(r"\bQuantum\b.*\bSoftware\b", re.IGNORECASE),
    "digico:sd": re.compile(r"\bSD\b.*\bSoftware\b", re.IGNORECASE),
}
NOT_CONSOLE_TITLE = re.compile(r"Offline|Convert|\b852\b", re.IGNORECASE)

# ".../uploads/2026/10/Quantum1_V2242-4x_Update_Package.zip" -> year, month,
# "2242", "4". The trailing letter (x/z) is a build flavour, not part of the
# version DiGiCo quotes (v2242.4).
PACKAGE_RE = re.compile(r"/uploads/(\d{4})/(\d{2})/[^/]*?_V(\d+)(?:-(\d+))?[a-z]*_[^/]*\.zip", re.IGNORECASE)


def _download_links(article):
    """[(label, url)] for every .zip download in an article body, in whichever
    form DiGiCo is using: <span data-link="...zip">label</span> buttons, <a
    href="...zip">, or <option value="...zip">label</option> in a dropdown."""
    soup = BeautifulSoup(article.get("body") or "", "lxml")
    links = []
    for el in soup.find_all(True):
        url = el.get("data-link") or (el.get("href") if el.name == "a" else None) or (el.get("value") if el.name == "option" else None)
        if url and url.lower().split("?")[0].endswith(".zip"):
            links.append((el.get_text(" ", strip=True), url))
    return links


def _console_links(article, key):
    """The article's console update packages for this family, as (label,
    url) - not its offline installers or converters."""
    prefix = PER_MODEL_PACKAGES[key]
    return [
        (label, url)
        for label, url in _download_links(article)
        if "update_package" in url.lower() and prefix.match(url.rsplit("/", 1)[-1])
    ]


def _select_console_article(key, articles):
    """(article, links, error) for a per-model key. articles are newest first.
    Picks the newest article that has console update packages for the family,
    whatever it's titled; error is set (and article None) if there isn't one,
    or if a newer article *looks* like this family's console software but has
    nothing we can read - better a loud failure than quietly reading an older
    release (see the module docstring)."""
    chosen, links = None, []
    for a in articles:
        found = _console_links(a, key)
        if found:
            chosen, links = a, found
            break
    lookalike = LOOKALIKE_TITLES[key]
    newest_titled = next(
        (a for a in articles if lookalike.search(a.get("title", "")) and not NOT_CONSOLE_TITLE.search(a.get("title", ""))),
        None,
    )
    if newest_titled and (chosen is None or newest_titled["created_at"] > chosen["created_at"]):
        return None, [], (
            f"The newest article that looks like {key.split(':')[1]} console software, "
            f"{newest_titled.get('title', '')!r} ({newest_titled['created_at'][:10]}), has no download links "
            "I can read - has the article layout changed?"
        )
    if chosen is None:
        return None, [], f"No {key.split(':')[1]} console software article with download links found on support.digico.biz"
    return chosen, links, None


def _norm(name):
    """Comparable form of a model name: lower-case, single spaces, and
    DiGiCo's "Dual Screen" folded into "DS", so the article's "Quantum 225
    Dual Screen" button matches our "Quantum 225DS" (and "Quantum 225 DS")."""
    name = re.sub(r"\s+", " ", name).strip().lower()
    name = re.sub(r"\s*dual screen$", "ds", name)
    return re.sub(r"\s+ds$", "ds", name)


def _label_models(label):
    """Model names a download link covers (normalised): "Quantum 326 & 338"
    and "Quantum 326 / 338" are both "Quantum 326" and "Quantum 338";
    "Quantum 225 Dual Screen" is only the DS model, so it never matches the
    plain "Quantum 225"."""
    parts = [p.strip() for p in re.split(r"[&/]", label) if p.strip()]
    m = re.match(r"^(\D*)\d", parts[0]) if parts else None
    prefix = m.group(1) if m else ""
    return {_norm(p if i == 0 or not p[:1].isdigit() else prefix + p) for i, p in enumerate(parts)}


def _per_model_result(selection, model):
    """The CheckResult for one tracked model, from its own download link.
    selection is _select_console_article's (article, links, error)."""
    article, links, error = selection
    if article is None:
        return CheckResult(None, False, error or "No matching software article found on support.digico.biz")
    title = article.get("title", "")
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
                )
                break
        resolved[key] = match

    selections = {key: _select_console_article(key, articles) for key in PER_MODEL_KEYS}

    results = {}
    for item in equipment_items:
        if item.checker_key in PER_MODEL_KEYS:
            results[item.id] = _per_model_result(selections[item.checker_key], item.model)
            continue
        match = resolved.get(item.checker_key)
        if match:
            results[item.id] = match
        else:
            results[item.id] = CheckResult(
                None, False, "No matching software article found on support.digico.biz"
            )
    return results
