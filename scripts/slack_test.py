"""Sends one test message to Slack using the same SLACK_WEBHOOK_URL /
SLACK_ALERT_USER_ID the daily run uses - to confirm a new webhook or alert
recipient works before real alerts depend on it. Run from the workflow
(Actions -> Daily firmware check -> Run workflow -> tick "slack_test") or
locally:

    SLACK_WEBHOOK_URL=... SLACK_ALERT_USER_ID=U01ABCDE2F python3 scripts/slack_test.py

Exits non-zero if Slack rejects the post, printing Slack's reason (e.g.
"no_service" = webhook revoked, "channel_not_found", "invalid_token").
Never prints the webhook URL itself.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from app.slack import send_test  # noqa: E402


def main():
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("SLACK_WEBHOOK_URL is not set - nothing to test.")
        return 1
    try:
        mentioned = send_test(webhook, os.environ.get("SLACK_ALERT_USER_ID"))
    except requests.HTTPError as e:
        print(f"Slack rejected the test message: HTTP {e.response.status_code} - {e.response.text.strip()[:200]}")
        return 1
    except requests.RequestException as e:
        print(f"Could not reach Slack: {e.__class__.__name__}")
        return 1
    print("Test message posted.")
    print("Alert recipient mentioned." if mentioned else "No mention sent - SLACK_ALERT_USER_ID is unset or not a member ID.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
