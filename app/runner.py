"""Runs checkers against equipment rows and persists results."""
import datetime as dt
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.checkers.base import newest_version
from app.checkers.registry import module_for
from app.models import CheckLog, Equipment

logger = logging.getLogger("firmware_tracker.runner")

# How long a genuinely new version stays flagged "Update available" (amber
# row + badge) before it automatically reverts to "ok" with no one needing
# to do anything. Re-confirming the *same* pending version on a later check
# does not restart this clock - only a fresh version change (current_version
# actually changing again) does, since that's the only thing that sets
# last_changed_at.
UPDATE_HIGHLIGHT_WINDOW = dt.timedelta(days=14)


def _apply_platforms(item: Equipment, result, now):
    """Per-platform version tracking (see Equipment.platforms). Each platform
    keeps its own previous version and change time, so an update to one
    platform is caught even when it doesn't change the row's headline version
    (e.g. the Mac build catching up to a Windows build that's already the
    newest). The row is "update available" while *any* platform's change is
    still inside the highlight window - the same rule the single-version path
    applies, evaluated per platform."""
    old = {p["name"]: p for p in (item.platforms or [])}
    platforms = []
    for name, version in result.platforms.items():
        prev = old.get(name)
        entry = {
            "name": name,
            "current_version": version,
            "previous_version": prev.get("previous_version") if prev else None,
            "last_changed_at": prev.get("last_changed_at") if prev else None,
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


def _apply_content_check(item: Equipment, result, now, version_changed):
    """Article-based sources only (result.content_hash set): if the matched
    article's content changed but the version didn't, mark the row
    "needs_review" - it might be a real firmware change published without a
    new title/article, or just a typo fix, and we can't tell which, so it's
    deliberately not treated with the confidence of an "update_detected".
    The first fingerprint ever stored is just a baseline (nothing to compare
    against), and a row already showing a pending update isn't overridden -
    edits during an update's window are most likely part of that update."""
    if result.content_hash is None:
        return
    previous = item.content_hash
    item.content_hash = result.content_hash
    if previous and previous != result.content_hash and not version_changed and item.status in ("ok", "needs_review"):
        item.status = "needs_review"
        item.review_since = now
        logger.info("Content change (same version): %s %s", item.manufacturer, item.model)


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

    version_changed = bool(item.current_version and result.version != item.current_version)
    if version_changed:
        item.previous_version = item.current_version
        item.last_changed_at = now
        item.status = "update_detected"
        item.review_since = None
        logger.info(
            "Version change: %s %s  %s -> %s",
            item.manufacturer,
            item.model,
            item.current_version,
            result.version,
        )
    elif item.status == "update_detected":
        # Same pending version reconfirmed, not a new change - last_changed_at
        # stays untouched. Auto-clear once the highlight window has elapsed
        # since it was *first* detected; otherwise stay flagged.
        if item.last_changed_at and now - item.last_changed_at >= UPDATE_HIGHLIGHT_WINDOW:
            item.status = "ok"
    elif item.status == "needs_review":
        # Same clock as update flags: clears itself after the window, no one
        # has to acknowledge it (the deployed dashboard has no controls that
        # write anything).
        if item.review_since is None or now - item.review_since >= UPDATE_HIGHLIGHT_WINDOW:
            item.status = "ok"
            item.review_since = None
    else:
        item.status = "ok"
        item.review_since = None

    _apply_content_check(item, result, now, version_changed)

    item.current_version = result.version
    item.release_date = result.release_date


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
        try:
            results = mod.check_all(items)
        except Exception as e:  # noqa: BLE001
            logger.exception("Checker module %s raised", mod.__name__)
            results = {i.id: None for i in items}
            for item in items:
                item.status = "error"
                item.last_error = f"Checker crashed: {e}"
                item.last_checked_at = dt.datetime.utcnow()
                checked += 1
            continue

        for item in items:
            result = results.get(item.id)
            if result is None:
                item.status = "error"
                item.last_error = "Checker returned no result"
                item.last_checked_at = dt.datetime.utcnow()
            else:
                _apply_result(db, item, result)
            checked += 1

    db.commit()
    return checked


def check_all(db: Session):
    items = db.query(Equipment).all()
    return check_equipment(db, items)
