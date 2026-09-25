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

# checker_key -> a human-readable name for the family of items it covers,
# used instead of listing every model when several share one firmware
# release (e.g. all 5 DiGiCo Quantum consoles are one release, one
# checker_key, and always report the identical version - that's exactly
# why they share a checker_key in the first place, so it's a more reliable
# "these are really the same family" signal than just matching version
# strings, which could coincidentally collide between two unrelated
# manufacturers). Only worth naming here for keys that actually cover more
# than one item - see _family_label for the fallback for everything else.
FAMILY_NAMES = {
    "ah:dlive": "Allen & Heath dLive series",
    "db:d40d90": "d&b D40/D90",
    "digico:quantum": "DiGiCo Quantum series",
    "shure:ad_transmitters": "Shure AD/ADX transmitters",
    "shure:adxr": "Shure ADXR/ADTQ receivers",
    "ssl:live": "Solid State Logic Live console series",
    "ssl:networkio": "Solid State Logic Network I/O series",
    "yamaha:rivage_pm": "Yamaha Rivage PM series",
}


def _group_changes(changes):
    """Groups changes by checker_key, preserving first-seen order (so
    messages post in a stable, deterministic sequence) - items sharing a
    checker_key were checked together and always carry the same new
    version, which is what makes collapsing them into one message correct
    rather than just convenient. Items with no checker_key (shouldn't
    happen, but not load-bearing to assume) fall
    back to grouping by (manufacturer, model), i.e. their own singleton
    group."""
    groups = {}
    order = []
    for c in changes:
        key = c.get("checker_key") or (c["manufacturer"], c["model"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)
    return [(key, groups[key]) for key in order]


def _family_label(key, group):
    if isinstance(key, str):
        name = FAMILY_NAMES.get(key)
        if name:
            return name
    # Several entries can be the same *item* (one per changed platform), not
    # several items - count distinct models.
    models = list(dict.fromkeys(c["model"] for c in group))
    if len(models) == 1:
        c = group[0]
        return f"{c['manufacturer']} {c['model']}"
    # A genuinely multi-item family we haven't given a friendly name to
    # (e.g. a new checker_key added since) - list the actual models rather
    # than invent a collective name we can't vouch for.
    manufacturer = group[0]["manufacturer"]
    return f"{manufacturer} {'/'.join(models)}"


def _format_message(key, group):
    label = _family_label(key, group)
    if group[0].get("platform"):
        # Per-platform product (Dante Controller): versions can differ by
        # platform, so name each one rather than implying a single version.
        if len(group) == 1:
            label, version = f"{label} ({group[0]['platform']})", group[0]["current_version"]
        else:
            version = ", ".join(f"{c['platform']} {c['current_version']}" for c in group)
    else:
        version = group[0]["current_version"]
    return f"<!channel> New firmware available for *{label}* → {version}\n\n<{DASHBOARD_URL}|View dashboard>"


def notify_updates(changes, webhook_url):
    """changes: list of {manufacturer, model, checker_key, previous_version,
    current_version} dicts, one per item that genuinely changed version this
    run. Groups them by family (see _group_changes) and posts one message
    per family - not one message per item, and not everything bundled into
    a single message, so a DiGiCo update and an unrelated Yamaha update the
    same day still read as two distinct notifications.

    No-ops (never raises) if there's nothing to say or nowhere to say it -
    a Slack outage or a missing webhook_url (e.g. running this locally,
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

    groups = _group_changes(changes)
    sent = 0
    failures = []
    for key, group in groups:
        try:
            r = requests.post(webhook_url, json={"text": _format_message(key, group)}, timeout=10)
            r.raise_for_status()
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to post Slack notification for %r", key)
            failures.append(e.__class__.__name__)

    logger.info("Posted %d/%d Slack notification(s)", sent, len(groups))
    if failures:
        return f"sent {sent}/{len(groups)}, failed: {', '.join(failures)}"
    return f"sent {sent}/{len(groups)}"
