"""Works out which items genuinely changed version during a check run, for
the Slack notification (see app/slack.py). Kept separate from
scripts/ci_check.py so the logic can be exercised on its own."""


def snapshot_versions(records):
    """Before-the-run snapshot from a previously exported equipment.json:
    ({(manufacturer, model): current_version},
     {(manufacturer, model): {platform name: version}})."""
    versions = {(r["manufacturer"], r["model"]): r.get("current_version") for r in records}
    platforms = {
        (r["manufacturer"], r["model"]): {p["name"]: p["current_version"] for p in r.get("platforms") or []}
        for r in records
    }
    return versions, platforms


def find_changes(items, old_versions, old_platforms):
    """One change dict per item - or, for items tracked per platform, per
    platform - whose version genuinely changed since the snapshot. A still-
    pending update reconfirmed today, or one auto-clearing after its window,
    leaves the version untouched so isn't reported again. Nothing is reported
    for a version with no prior value to compare against (first-ever run, or
    a platform seen for the first time)."""
    changes = []
    for item in items:
        key = (item.manufacturer, item.model)
        base = {
            "manufacturer": item.manufacturer,
            "model": item.model,
            "checker_key": item.checker_key,
        }
        if item.platforms:
            before = old_platforms.get(key, {})
            for p in item.platforms:
                old = before.get(p["name"])
                if old and p["current_version"] != old and p.get("update_pending"):
                    changes.append(
                        {**base, "platform": p["name"], "previous_version": old, "current_version": p["current_version"]}
                    )
        elif (
            old_versions.get(key)
            and item.status == "update_detected"
            and item.current_version != old_versions[key]
        ):
            changes.append({**base, "previous_version": old_versions[key], "current_version": item.current_version})
    return changes


def snapshot_statuses(records):
    """{(manufacturer, model): status} from a previously exported
    equipment.json - the before-the-run half of find_new_errors."""
    return {(r["manufacturer"], r["model"]): r.get("status") for r in records}


def find_new_errors(items, old_statuses):
    """One dict per item whose check *newly* failed this run: status is
    "error" now and wasn't before. A failure that's merely still failing
    from a previous day is not reported again, so a broken scraper pings
    once rather than every morning until someone fixes it. An item that
    wasn't in the snapshot at all counts as new (a freshly added item that
    fails its very first check is worth knowing about) - except when the
    snapshot is empty, i.e. the first-ever run, where there's nothing to
    compare against and everything would look new."""
    if not old_statuses:
        return []
    return [
        {
            "manufacturer": item.manufacturer,
            "model": item.model,
            "checker_key": item.checker_key,
            "error": item.last_error or "check failed",
        }
        for item in items
        if item.status == "error" and old_statuses.get((item.manufacturer, item.model)) != "error"
    ]
