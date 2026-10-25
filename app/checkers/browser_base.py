"""Shared helper for headless-browser checkers (Playwright).

Used by manufacturers whose version info either renders client-side via JS
(Dante, d&b's search) or whose site blocks plain HTTP requests (Allen &
Heath). Heavier and slower than the requests-based checkers, so it's kept
isolated here rather than used by default everywhere.
"""
from contextlib import contextmanager

from app.checkers.base import USER_AGENT, describe_page

NAV_TIMEOUT_MS = 30_000


@contextmanager
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.set_default_timeout(NAV_TIMEOUT_MS)
            yield page
        finally:
            browser.close()


def dismiss_cookie_banner(page):
    """Best-effort click on a common 'Accept' consent button. Never raises -
    if there's no banner (or a different one), we just move on."""
    for sel in (
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
        "[data-testid='uc-accept-all-button']",
    ):
        try:
            page.click(sel, timeout=3000)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def describe_browser_page(page, status=None, text=None):
    """describe_page() for a live Playwright page. status is the HTTP status
    of the navigation (page.goto's response.status) if the caller kept it;
    text defaults to the whole body. Never raises - this runs while already
    reporting a failure, so it must not be the thing that fails."""
    try:
        title = page.title()
    except Exception:  # noqa: BLE001
        title = None
    if text is None:
        try:
            text = page.inner_text("body")
        except Exception:  # noqa: BLE001
            text = None
    return describe_page(status, title, text)
