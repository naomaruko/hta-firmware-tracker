"""Sends test messages to Slack using the same secrets the daily run uses - to
confirm a new webhook or alert recipient works before real alerts depend on it.
Run from the workflow (Actions -> Daily firmware check -> Run workflow ->
tick "slack_test") or locally:

    SLACK_WEBHOOK_URL=... SLACK_ALERTS_WEBHOOK_URL=... SLACK_ALERT_USER_ID=U01ABCDE2F \
        python3 scripts/slack_test.py

It posts:
  - one connection check to the main (firmware-updates) channel, via
    SLACK_WEBHOOK_URL - no @channel;
  - a sample FAILURE alert and a sample RECOVERED message, built by the real
    alert code about a fake "TEST Sample item", to the alerts channel, via
    SLACK_ALERTS_WEBHOOK_URL (or the main webhook if that isn't set - and it
    says so).
Exits non-zero if Slack rejects any post, printing Slack's reason (e.g.
"no_service" = webhook revoked, "channel_not_found", "invalid_token"). Never
prints a webhook URL.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from app.slack import alerts_webhook_url, send_test, send_test_alerts  # noqa: E402


def _try(label, fn):
    try:
        mentioned = fn()
    except requests.HTTPError as e:
        print(f"[{label}] Slack rejected the post: HTTP {e.response.status_code} - {e.response.text.strip()[:200]}")
        return None
    except requests.RequestException as e:
        print(f"[{label}] Could not reach Slack: {e.__class__.__name__}")
        return None
    print(f"[{label}] posted." + (" Alert recipient mentioned." if mentioned else " No one mentioned."))
    return mentioned


def main():
    main_hook = os.environ.get("SLACK_WEBHOOK_URL")
    alerts_hook = alerts_webhook_url()
    user = os.environ.get("SLACK_ALERT_USER_ID")
    if not main_hook and not alerts_hook:
        print("Neither SLACK_WEBHOOK_URL nor SLACK_ALERTS_WEBHOOK_URL is set - nothing to test.")
        return 1

    failed = False
    if main_hook:
        failed |= _try("updates channel", lambda: send_test(main_hook, user)) is None
    else:
        print("[updates channel] SLACK_WEBHOOK_URL is not set - skipped.")

    if os.environ.get("SLACK_ALERTS_WEBHOOK_URL"):
        print("[alerts channel] using SLACK_ALERTS_WEBHOOK_URL (separate from the updates channel).")
    else:
        print("[alerts channel] SLACK_ALERTS_WEBHOOK_URL is not set - failure alerts will use the main webhook.")
    failed |= _try("alerts channel", lambda: send_test_alerts(alerts_hook, user)) is None
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
