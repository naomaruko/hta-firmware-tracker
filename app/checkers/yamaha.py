"""Yamaha checker.

Source: usa.yamaha.com publishes a static page per firmware family at a
stable URL of the form /support/updates/<slug>_firm.html, e.g.
rivage_pm_firm.html, dm7_firm.html, swp1_firm.html, hy144-d-src_firm.html.
The current version is in the page <title>/<h1>, e.g. "RIVAGE PM Firmware
V7.10 - Yamaha USA".

Per Yamaha's official RIVAGE PM/DM7/CL/QL/R/Tio compatibility chart
(download.yamaha.com/files/tcm:39-1161321): DSP-R10, DSP-RX, DSP-RX-EX,
RPio622, and RPio222 genuinely share ONE firmware version with the console
itself, so those stay bundled under the rivage_pm slug. Rio3224-D2 and
Rio1608-D2 do NOT - they're on their own separate firmware track entirely
(shown as a distinct column in that chart), so each gets its own slug here
rather than being lumped in with the console version.
"""
import re

from app.checkers.base import CheckResult, http_get

BASE_URL = "https://usa.yamaha.com/support/updates/{slug}_firm.html"

# checker_key -> URL slug
SLUGS = {
    "yamaha:rivage_pm": "rivage_pm",
    "yamaha:dm7": "dm7",
    "yamaha:swp1": "swp1",
    "yamaha:hy144dsrc": "hy144-d-src",
    "yamaha:rio3224d2": "rio3224-d2",
    "yamaha:rio1608d2": "rio1608-d2",
}

VERSION_RE = re.compile(r"V([\d]+(?:\.[\d]+)*)", re.IGNORECASE)


def _fetch_one(slug):
    url = BASE_URL.format(slug=slug)
    r = http_get(url)
    r.raise_for_status()
    # Cheap title extraction without pulling in a full parser twice.
    m = re.search(r"<title>(.*?)</title>", r.text, re.IGNORECASE | re.DOTALL)
    title = m.group(1).strip() if m else ""
    vm = VERSION_RE.search(title)
    version = vm.group(0) if vm else None
    return version, url, title


def check_all(equipment_items):
    # Fetch each distinct slug once, then fan out to matching equipment.
    needed_keys = {item.checker_key for item in equipment_items}
    resolved = {}
    for key in needed_keys:
        slug = SLUGS.get(key)
        if not slug:
            continue
        try:
            version, url, title = _fetch_one(slug)
            if version:
                resolved[key] = CheckResult(version, True, source_url=url)
            else:
                resolved[key] = CheckResult(
                    None, False, f"Could not find version in page title: {title!r}", source_url=url
                )
        except Exception as e:  # noqa: BLE001
            resolved[key] = CheckResult(None, False, f"Fetch failed: {e}")

    results = {}
    for item in equipment_items:
        results[item.id] = resolved.get(
            item.checker_key, CheckResult(None, False, "Unknown Yamaha checker key")
        )
    return results
