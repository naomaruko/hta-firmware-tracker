"""Runs checkers against equipment rows and persists results."""
import datetime as dt
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.checkers.base import CheckResult
from app.checkers.registry import module_for
from app.models import CheckLog, Equipment

logger = logging.getLogger("firmware_tracker.runner")


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
        # Someone acknowledged it (or nothing new since) - keep as-is unless
        # explicitly cleared elsewhere. We leave update_detected sticky until
        # a human clears it via the dashboard, so it doesn't get silently lost.
        pass
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


def clear_update_flag(db: Session, equipment_id: int):
    item = db.query(Equipment).get(equipment_id)
    if item and item.status == "update_detected":
        item.status = "ok"
        # previous_version is deliberately left in place - it's useful history
        # ("this went from V21 to V22"), not just an alert-pending marker. The
        # "Up to date" badge already makes clear nothing is pending; the next
        # real version change will naturally overwrite this when it happens.
        db.commit()
    return item


def record_manual_check(db: Session, equipment_id: int, version: str, release_date: str = None):
    """A human checked a manual-only item themselves and is logging what they
    found. Goes through the exact same _apply_result logic an automated
    checker's result would - so a manually-logged version change gets the
    same "sticky until Acknowledged" treatment as a scraped one, and shows up
    in the same version history.
    """
    item = db.query(Equipment).get(equipment_id)
    if not item:
        return None
    if item.check_method != "manual":
        raise ValueError("This item is auto-checked - only manual-check items can be logged by hand")
    if not version or not version.strip():
        raise ValueError("Version is required")

    result = CheckResult(
        version=version.strip(),
        success=True,
        source_url=item.source_url,
        release_date=release_date.strip() if release_date and release_date.strip() else None,
    )
    _apply_result(db, item, result)
    db.commit()
    return item
