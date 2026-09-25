"""Solid State Logic checker.

Source: support.solidstatelogic.com also runs on Zendesk (same trick as
DiGiCo). SSL doesn't publish L650/L550+/L350+ firmware as a standalone
download - instead "SOLSA" (a PC/Mac standalone version of the Live console
software) is versioned identically to the console software itself, and its
article lists versions newest-first. Network I/O gear (ML 32.32, Blacklight
II Concentrator) ships firmware via a separate "Network I/O Update Package".
"""
import re

from app.checkers.base import CheckResult, content_fingerprint, http_get, iso_to_readable_date

CATEGORIES = {
    "ssl:live": 360003462038,       # Live Consoles
    "ssl:networkio": 360003462078,  # Network I/O
}

ARTICLES_URL = "https://support.solidstatelogic.com/api/v2/help_center/en-gb/categories/{cat}/articles.json"

PATTERNS = {
    "ssl:live": (re.compile(r"SOLSA", re.IGNORECASE), re.compile(r"\bV([\d.]+)\b")),
    "ssl:networkio": (re.compile(r"Network I/?O Downloads", re.IGNORECASE), re.compile(r"Network\s*I/?O\s*V([\d.]+)\s*Package")),
}


def _fetch_article_body(checker_key):
    title_pattern, version_pattern = PATTERNS[checker_key]
    cat = CATEGORIES[checker_key]
    r = http_get(ARTICLES_URL.format(cat=cat), params={"sort_by": "created_at", "sort_order": "desc", "per_page": 30})
    r.raise_for_status()
    articles = r.json().get("articles", [])
    for a in articles:
        if title_pattern.search(a.get("title", "")):
            from bs4 import BeautifulSoup

            text = BeautifulSoup(a.get("body", ""), "lxml").get_text(" ", strip=True)
            m = version_pattern.search(text)
            if m:
                # This is a single evergreen article that gets edited in place
                # for each new release (unlike DiGiCo, which creates a new
                # article per release) - so updated_at is the release date
                # here, not created_at (which is just when the article was
                # first written, back in 2022).
                return (
                    m.group(1),
                    a.get("html_url"),
                    iso_to_readable_date(a.get("updated_at")),
                    content_fingerprint(a.get("body")),
                )
            raise ValueError(f"Article found but no version pattern matched: {a['title']!r}")
    raise ValueError("No matching article found")


def check_all(equipment_items):
    needed_keys = {item.checker_key for item in equipment_items}
    resolved = {}
    for key in needed_keys:
        if key not in CATEGORIES:
            resolved[key] = CheckResult(None, False, "Unknown SSL checker key")
            continue
        try:
            version, url, release_date, content_hash = _fetch_article_body(key)
            resolved[key] = CheckResult(
                version, True, source_url=url, release_date=release_date, content_hash=content_hash
            )
        except Exception as e:  # noqa: BLE001
            resolved[key] = CheckResult(None, False, f"Fetch failed: {e}")

    results = {}
    for item in equipment_items:
        results[item.id] = resolved.get(item.checker_key, CheckResult(None, False, "Unknown SSL checker key"))
    return results
