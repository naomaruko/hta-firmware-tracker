#!/usr/bin/env bash
# Posts the "daily run failed" Slack alert (the workflow calls this from its
# last step, `if: failure()`), or with --test a clearly-labelled sample of
# it, so the whole path can be checked without anything actually failing.
#
# Deliberately curl + jq (both preinstalled on the runner) rather than
# app/slack.py: if the failure was the dependency install itself, `requests`
# may not exist yet. Goes to SLACK_ALERTS_WEBHOOK_URL (the private alerts
# channel), falling back to SLACK_WEBHOOK_URL if that's unset, so a missing
# secret never silences it. Mentions just the one person who needs to act (not
# @channel) via their Slack member ID in SLACK_ALERT_USER_ID - a webhook only
# pings for the <@ID> form, plain "@name" text notifies no one; falls back to
# an unmentioned message if it's unset or malformed.
#
# Normal mode never fails the step itself - a Slack outage shouldn't add noise
# on top of the failure already being reported. --test mode does exit non-zero
# if Slack rejects the post, since finding that out is the point.
set -uo pipefail

test_mode=0
[ "${1:-}" = "--test" ] && test_mode=1

webhook="${SLACK_ALERTS_WEBHOOK_URL:-${SLACK_WEBHOOK_URL:-}}"
if [ -z "$webhook" ]; then
  echo "No Slack webhook set (SLACK_ALERTS_WEBHOOK_URL / SLACK_WEBHOOK_URL) - skipping failure notification"
  [ "$test_mode" = 1 ] && exit 1
  exit 0
fi

mention=""
if [[ "${SLACK_ALERT_USER_ID:-}" =~ ^[UW][A-Z0-9]{6,}$ ]]; then
  mention="<@${SLACK_ALERT_USER_ID}> "
else
  echo "SLACK_ALERT_USER_ID unset or not a Slack member ID - posting without a mention"
fi

run_url="${RUN_URL:-https://github.com}"
# -f: an HTTP error from Slack (revoked webhook, deleted channel) is a failure,
# not "posted". Without it curl exits 0 on a 404 and we'd claim success.
if [ "$test_mode" = 1 ]; then
  text="${mention}:white_check_mark: *TEST* - this is how the \"daily run failed\" alert will look and where it will land. Nothing is wrong. <$run_url|This test run>"
else
  text="${mention}:warning: The daily firmware check failed - the dashboard may be out of date. <$run_url|View the run>"
fi

if curl -sSf -X POST --max-time 10 -H 'Content-type: application/json' \
     --data "$(jq -n --arg text "$text" '{text: $text}')" "$webhook"; then
  echo
  echo "Slack notification posted."
else
  echo "Slack failure notification could not be sent"
  [ "$test_mode" = 1 ] && exit 1
fi
exit 0
