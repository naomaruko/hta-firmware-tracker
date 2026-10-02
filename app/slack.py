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
import re

import requests

from app.families import FAMILY_NAMES, MANUFACTURER_LABELS

logger = logging.getLogger("firmware_tracker.slack")

# Not a secret - just where the dashboard happens to be hosted right now.
# Update if that ever moves to a custom domain (see TODO.md).
DASHBOARD_URL = "https://hta-firmware-tracker.vercel.app/"


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
            # FAMILY_NAMES itself is brand-free (see app/families.py) since
            # the dashboard already shows the manufacturer as a section
            # heading - a Slack message has no such heading, so it's
            # prepended here instead (correcting Yamaha's all-caps raw
            # field through MANUFACTURER_LABELS, the one manufacturer whose
            # stored casing doesn't already read naturally in a sentence).
            manufacturer = group[0]["manufacturer"]
            manufacturer = MANUFACTURER_LABELS.get(manufacturer, manufacturer)
            return f"{manufacturer} {name}"
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


def _post_all(groups, format_group, webhook_url, what):
    """Posts one Slack message per (key, group), never raising - a Slack
    outage must never break the daily commit. Returns a short status string
    so the caller can print a clear outcome (ci_check.py doesn't configure
    Python logging, so this module's own log calls aren't visible in the
    GitHub Actions log by default)."""
    sent = 0
    failures = []
    for key, group in groups:
        try:
            r = requests.post(webhook_url, json={"text": format_group(key, group)}, timeout=10)
            r.raise_for_status()
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to post Slack %s notification for %r", what, key)
            failures.append(e.__class__.__name__)

    logger.info("Posted %d/%d Slack %s notification(s)", sent, len(groups), what)
    if failures:
        return f"sent {sent}/{len(groups)}, failed: {', '.join(failures)}"
    return f"sent {sent}/{len(groups)}"


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
    """
    if not changes:
        return "no changes"
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL not set - skipping notification for %d update(s)", len(changes))
        return "skipped (no SLACK_WEBHOOK_URL)"
    return _post_all(_group_changes(changes), _format_message, webhook_url, "update")


def _format_error_message(key, group, mention=""):
    label = _family_label(key, group)
    # One shared fetch failing gives every member of a family the identical
    # message - say it once. Name models only if the messages differ.
    by_message = {}
    for c in group:
        by_message.setdefault(c["error"], []).append(c["model"])
    if len(by_message) == 1:
        detail = next(iter(by_message))
    else:
        detail = "; ".join(f"{', '.join(models)}: {msg}" for msg, models in by_message.items())
    return f"{mention}:warning: Firmware check failed for *{label}*: {detail}\n\n<{DASHBOARD_URL}|View dashboard>"


def notify_errors(errors, webhook_url, alert_user_id=None):
    """errors: list of {manufacturer, model, checker_key, error} dicts, one
    per item whose check newly failed this run (see changes.find_new_errors).
    Grouped by family exactly like version updates, so a shared fetch failing
    is one message, not one per model. Pings just one person (alert_user_id,
    the same Slack member ID the "daily run failed" alert uses) rather than
    @channel - a broken scraper needs one person to look, not everyone
    informed. Same never-raises guarantee as notify_updates."""
    if not errors:
        return "no new errors"
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL not set - skipping notification for %d error(s)", len(errors))
        return "skipped (no SLACK_WEBHOOK_URL)"
    mention = f"<@{alert_user_id}> " if alert_user_id and re.match(r"^[UW][A-Z0-9]{6,}$", alert_user_id) else ""
    return _post_all(
        _group_changes(errors),
        lambda key, group: _format_error_message(key, group, mention),
        webhook_url,
        "error",
    )
