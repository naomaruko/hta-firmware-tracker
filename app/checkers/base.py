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


def iso_to_readable_date(iso_str):
    """Zendesk-style ISO timestamp -> "March 20, 2026", or None if unparseable."""
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%B %-d, %Y")
    except ValueError:
        return None
