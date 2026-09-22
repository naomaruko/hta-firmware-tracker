"""Posts a Slack notification when the daily check finds a genuinely new
firmware version - not on every run, only when something actually changed.
Called from scripts/ci_check.py, which does the before/after diffing.

Reads the webhook URL from the caller (see notify_updates) rather than any
hardcoded value or module-level constant - in CI that's the SLACK_WEBHOOK_URL
repo secret, injected as an env var in .github/workflows/daily-check.yml.
Never logged: if the POST fails, the exception can legitimately mention the
URL, but GitHub Actions masks any exact occurrence of a registered secret's
value in step output automatically, so that's covered without this module
needing its own redaction.
"""
import logging

import requests

logger = logging.getLogger("firmware_tracker.slack")

# Not a secret - just where the dashboard happens to be hosted right now.
# Update if that ever moves to a custom domain (see TODO.md).
DASHBOARD_URL = "https://hta-firmware-tracker.vercel.app/"


def _format_message(changes):
    lines = ["<!channel> Firmware update detected:", ""]
    for c in changes:
        previous = c["previous_version"] or "unknown"
        lines.append(f"• *{c['manufacturer']} {c['model']}*: {previous} → {c['current_version']}")
    lines.append("")
    lines.append(f"<{DASHBOARD_URL}|View dashboard>")
    return "\n".join(lines)


def notify_updates(changes, webhook_url):
    """changes: list of {manufacturer, model, previous_version,
    current_version} dicts, one per item that genuinely changed version this
    run. No-ops (never raises) if there's nothing to say or nowhere to say
    it - a Slack outage or a missing webhook_url (e.g. running this locally,
    where the secret isn't set) must never break the daily commit.

    Returns a short status string (not just True/False) so the caller can
    print a clear outcome - ci_check.py doesn't configure Python logging, so
    this module's own log calls aren't visible in the GitHub Actions log by
    default, and "why didn't a message show up" is exactly the kind of thing
    worth being able to see at a glance in CI output.
    """
    if not changes:
        return "no changes"
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL not set - skipping notification for %d update(s)", len(changes))
        return "skipped (no SLACK_WEBHOOK_URL)"

    try:
        r = requests.post(webhook_url, json={"text": _format_message(changes)}, timeout=10)
        r.raise_for_status()
        logger.info("Posted Slack notification for %d update(s)", len(changes))
        return "sent"
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to post Slack notification")
        return f"failed ({e.__class__.__name__})"
