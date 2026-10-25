"""Runs checkers against equipment rows and persists results."""
import datetime as dt
import logging
import time
from collections import defaultdict

from sqlalchemy.orm import Session

from app.checkers.base import newest_version
from app.checkers.registry import module_for
from app.models import CheckLog, Equipment

logger = logging.getLogger("firmware_tracker.runner")

# How long a genuinely new version stays flagged "Update available" (amber
# row + badge) before it automatically reverts to "ok" with no one needing
# to do anything. Set to a month rather than the 2 weeks it started at,
# since the team typically waits to see whether a new release has reported
# bugs before applying it, and a shorter flag would clear before they're
# done watching. Re-confirming the *same* pending version on a later check
# does not restart this clock - only a fresh version change (current_version
# actually changing again) does, since that's the only thing that sets
# last_changed_at.
UPDATE_HIGHLIGHT_WINDOW = dt.timedelta(days=30)

# A failed check gets this many more attempts, after a pause, before it
# counts as failed (and so before it can show "Check failed" or alert
# anyone). Most failures are momentary - a bot-protection page, a
# half-rendered page, a slow response - and a minute later the same fetch
# works; the dLive scraper failed exactly that way once and was fine the
# next day. Only the items that failed are retried, and only the final
# outcome is recorded, so a blip that clears on retry leaves no trace. A
# genuinely broken checker costs ~1 extra minute per run, and still fails.
RETRY_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 30


def _apply_platforms(item: Equipment, result, now):
    """Per-platform version tracking (see Equipment.platforms). Each platform
    keeps its own previous version and change time, so an update to one
    platform is caught even when it doesn't change the row's headline version
    (e.g. the Mac build catching up to a Windows build that's already the
    newest). The row is "update available" while *any* platform's change is
    still inside the highlight window - the same rule the single-version path
    applies, evaluated per platform."""
    old = {p["name"]: p for p in (item.platforms or [])}
    platform_dates = result.platform_release_dates or {}
    platforms = []
    for name, version in result.platforms.items():
        prev = old.get(name)
        entry = {
            "name": name,
            "current_version": version,
            "previous_version": prev.get("previous_version") if prev else None,
            "last_changed_at": prev.get("last_changed_at") if prev else None,
            "release_date": platform_dates.get(name),
        }
        if prev and prev.get("current_version") and prev["current_version"] != version:
            entry["previous_version"] = prev["current_version"]
            entry["last_changed_at"] = now.isoformat()
            logger.info(
                "Version change: %s %s (%s)  %s -> %s",
                item.manufacturer,
                item.model,
                name,
                prev["current_version"],
                version,
            )
        changed_at = dt.datetime.fromisoformat(entry["last_changed_at"]) if entry["last_changed_at"] else None
        entry["update_pending"] = bool(changed_at and now - changed_at < UPDATE_HIGHLIGHT_WINDOW)
        platforms.append(entry)

    item.platforms = platforms
    item.current_version = newest_version([p["current_version"] for p in platforms])
    changed = [p for p in platforms if p["last_changed_at"]]
    if changed:
        latest = max(changed, key=lambda p: p["last_changed_at"])
        item.last_changed_at = dt.datetime.fromisoformat(latest["last_changed_at"])
        item.previous_version = latest["previous_version"]
    item.status = "update_detected" if any(p["update_pending"] for p in platforms) else "ok"


def _apply_result(db: Session, item: Equipment, result):
    now = dt.datetime.utcnow()
    item.last_checked_at = now

    db.add(
        CheckLog(
            equipment_id=item.id,
            checked_at=now,
            version_found=result.version,
            success=result.success,
            error=result.error,
        )
    )

    if result.source_url:
        item.source_url = result.source_url

    if not result.success:
        item.status = "error"
        item.last_error = result.error
        return

    item.last_error = None
    if result.platforms:
        _apply_platforms(item, result, now)
        item.release_date = result.release_date
        return

    if item.current_version and result.version != item.current_version:
        item.previous_version = item.current_version
        item.last_changed_at = now
        item.status = "update_detected"
        logger.info(
            "Version change: %s %s  %s -> %s",
            item.manufacturer,
            item.model,
            item.current_version,
            result.version,
        )
    elif item.status == "update_detected" and result.version == item.current_version:
        # Same pending version reconfirmed, not a new change - last_changed_at
        # stays untouched. Auto-clear once the highlight window has elapsed
        # since it was *first* detected; otherwise stay flagged.
        if item.last_changed_at and now - item.last_changed_at >= UPDATE_HIGHLIGHT_WINDOW:
            item.status = "ok"
    else:
        item.status = "ok"

    item.current_version = result.version
    item.release_date = result.release_date


def _check_module(mod, items):
    """Runs mod.check_all(items), retrying just the failures (see
    RETRY_ATTEMPTS). Returns (results, crash): results is {item.id:
    CheckResult} from the best attempt per item; crash is the exception from
    the last attempt if the module raised on it (only meaningful for items
    that never got a result)."""
    results = {}
    crash = None
    pending = items
    for attempt in range(1 + RETRY_ATTEMPTS):
        if attempt:
            logger.info(
                "Retrying %d failed item(s) from %s in %ds (attempt %d of %d)",
                len(pending), mod.__name__, RETRY_DELAY_SECONDS, attempt + 1, 1 + RETRY_ATTEMPTS,
            )
            time.sleep(RETRY_DELAY_SECONDS)
        try:
            got = mod.check_all(pending)
        except Exception as e:  # noqa: BLE001
            logger.exception("Checker module %s raised", mod.__name__)
            crash = e
            continue
        crash = None
        results.update(got)
        pending = [i for i in pending if not (got.get(i.id) and got[i.id].success)]
        if not pending:
            break
    return results, crash


def check_equipment(db: Session, equipment_items):
    """Run checkers for the given list of Equipment rows."""
    if not equipment_items:
        return 0

    grouped = defaultdict(list)
    for item in equipment_items:
        mod = module_for(item.checker_key)
        if mod is None:
            item.status = "error"
            item.last_error = f"No checker module for key {item.checker_key!r}"
            continue
        grouped[mod].append(item)

    checked = 0
    for mod, items in grouped.items():
        results, crash = _check_module(mod, items)
        for item in items:
            result = results.get(item.id)
            if result is None:
                item.status = "error"
                item.last_error = f"Checker crashed: {crash}" if crash else "Checker returned no result"
                item.last_checked_at = dt.datetime.utcnow()
            else:
                _apply_result(db, item, result)
            checked += 1

    db.commit()
    return checked


def check_all(db: Session):
    items = db.query(Equipment).all()
    return check_equipment(db, items)
