"""Runs checkers against equipment rows and persists results."""
import datetime as dt
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

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


def check_equipment(db: Session, equipment_items):
    """Run checkers for the given list of Equipment rows (scrape-method only)."""
    scrape_items = [e for e in equipment_items if e.check_method == "scrape"]
    if not scrape_items:
        return 0

    grouped = defaultdict(list)
    for item in scrape_items:
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
