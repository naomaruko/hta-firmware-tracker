"""Shared types and HTTP helper for checkers."""
import datetime as dt
import re
from dataclasses import dataclass
from typing import Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 hta-firmware-tracker/1.0"
)

DEFAULT_TIMEOUT = 20


@dataclass
class CheckResult:
    version: Optional[str]
    success: bool
    error: Optional[str] = None
    source_url: Optional[str] = None
    # Free text exactly as the manufacturer states it (formats vary between
    # sources) - None where that source doesn't publish a release date at all.
    release_date: Optional[str] = None
    # For products published as separate per-platform builds with their own
    # version numbers (Dante Controller: Windows / macOS Apple Silicon /
    # macOS Intel): display name -> version, in display order. When set,
    # `version` is the newest of them (see newest_version) and the runner
    # tracks each platform's changes separately. None for everything else.
    platforms: Optional[dict] = None
    # Per-platform release dates for a platforms result above (name -> date
    # string), independent of the single release_date field - Dante
    # Controller's three builds each publish their own. None for anything
    # that isn't a platforms result, or where none of them resolved.
    platform_release_dates: Optional[dict] = None


def version_key(version):
    """Sort key for dotted version strings ("4.18.1.2" > "4.18.1.1"); falls
    back to comparing as text if there are no digits to parse."""
    parts = re.findall(r"\d+", version or "")
    return (tuple(int(p) for p in parts), version or "")


def newest_version(versions):
    return max(versions, key=version_key) if versions else None


def http_get(url, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", USER_AGENT)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return requests.get(url, headers=headers, **kwargs)


class CheckerError(Exception):
    pass


_MONTH_ABBREVIATIONS = {
    "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
    "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
    "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec",
}
_FULL_MONTH_RE = re.compile("|".join(_MONTH_ABBREVIATIONS))


def abbreviate_month(date_str):
    """"March 27, 2026" -> "Mar 27, 2026", for a date scraped as raw text
    off a manufacturer's own page (Shure) rather than one we format
    ourselves via strftime (everyone else, see iso_to_readable_date below) -
    those just use %b directly. Leaves anything that isn't a recognized full
    month name untouched, including None."""
    if not date_str:
        return date_str
    return _FULL_MONTH_RE.sub(lambda m: _MONTH_ABBREVIATIONS[m.group(0)], date_str)


def iso_to_readable_date(iso_str):
    """Zendesk-style ISO timestamp -> "March 20, 2026", or None if unparseable."""
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%b %-d, %Y")
    except ValueError:
        return None


def describe_page(status, title, text, words=12):
    """One-line description of a page a checker couldn't find its version
    on, for putting in the failure message - e.g.
        HTTP 200, title "Just a moment...", starts "Checking your browser before"
    so a failure says what the page actually was (a bot-protection
    interstitial, an error page, a redesign) instead of leaving it a mystery
    to reproduce later. Any piece can be None. Whitespace is collapsed,
    control characters dropped, and everything capped, since this text comes
    from a third-party page and ends up in Slack and on the dashboard."""

    def clean(value, limit):
        value = re.sub(r"[\x00-\x1f\x7f]+", " ", value or "")
        value = re.sub(r"\s+", " ", value).strip()
        return value[: limit - 1] + "\u2026" if len(value) > limit else value

    parts = []
    if status is not None:
        parts.append(f"HTTP {status}")
    title = clean(title, 80)
    if title:
        parts.append(f'title "{title}"')
    start = clean(" ".join((text or "").split()[:words]), 90)
    parts.append(f'starts "{start}"' if start else "page text empty")
    return ", ".join(parts)


_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%b %Y", "%B %Y")


def parse_release_date(text):
    """(year, month, day-or-None) from the date formats the checkers produce
    ("Oct 26, 2026", "Jun 2026"), or None if it isn't one of them. Some
    sources only give a month, hence the optional day."""
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            d = dt.datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
        return (d.year, d.month, d.day if "%d" in fmt else None)
    return None


def _compare_dates(a, b):
    """-1/0/1 for a before/equal/after b, or None if either is unknown. If
    either only has a month, compares months ("Mar 2026" equals "Mar 20, 2026")."""
    if a is None or b is None:
        return None
    if a[2] is None or b[2] is None:
        a, b = a[:2], b[:2]
    return (a > b) - (a < b)


def version_regression(old_version, old_date, new_version, new_date):
    """True if a result looks like an OLDER release than the one already
    recorded - almost always a checker reading the wrong thing (a renamed
    article that falls back to a years-old one, a layout change exposing a
    stale list) rather than a manufacturer actually going backwards.

    The release date, when both have one, is the better evidence, because
    version numbering sometimes changes scheme (DiGiCo went from "V2126" to
    "V22", which sorts lower though it's newer): released earlier than what we
    have -> regression; released later -> never, whatever the version string
    looks like. With no usable dates, a lower version is a regression."""
    if not old_version or not new_version or old_version == new_version:
        return False
    by_date = _compare_dates(parse_release_date(new_date), parse_release_date(old_date))
    if by_date is not None and by_date < 0:
        return True
    if by_date is not None and by_date > 0:
        return False
    return version_key(new_version) < version_key(old_version)
