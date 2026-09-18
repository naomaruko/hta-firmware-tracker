"""Allen & Heath checker.

Source: allen-heath.com's dLive resources page blocks plain HTTP requests
(403, likely bot protection) but loads fine in a real browser. The "Firmware
Downloads" section shows the current version as plain text, e.g.
"dLive Firmware V2.12" - covers the whole dLive family (S-Class surfaces,
C-Class surfaces, and DM-Class MixRacks alike), so one fetch covers both
S5000 and DM64 MixRack.
"""
import re

from app.checkers.base import CheckResult
from app.checkers.browser_base import browser_page

DLIVE_URL = "https://www.allen-heath.com/hardware/dlive-series/all-models/resources/"

VERSION_RE = re.compile(r"dLive Firmware\s+V([\d.]+)", re.IGNORECASE)


def _fetch_dlive_version():
    with browser_page() as page:
        page.goto(DLIVE_URL, wait_until="networkidle")
        text = page.inner_text("body")
    m = VERSION_RE.search(text)
    if not m:
        raise ValueError("Version pattern not found on page")
    return f"V{m.group(1)}"


def check_all(equipment_items):
    try:
        version = _fetch_dlive_version()
        result = CheckResult(version, True, source_url=DLIVE_URL)
    except Exception as e:  # noqa: BLE001
        result = CheckResult(None, False, f"Fetch failed: {e}", source_url=DLIVE_URL)

    return {item.id: result for item in equipment_items}
