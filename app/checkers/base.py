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
