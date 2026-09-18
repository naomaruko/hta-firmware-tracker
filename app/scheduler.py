"""Background scheduler for automatic checks.

Runs inside the same process as the web app via APScheduler. This means
automatic checking only happens while the app is running continuously
somewhere (see README's "Running this for real" section) - if it's only
open on your laptop, it only checks while your laptop has it open.
"""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.runner import check_all

logger = logging.getLogger("firmware_tracker.scheduler")

CHECK_INTERVAL_HOURS = float(os.environ.get("CHECK_INTERVAL_HOURS", "24"))

_scheduler = None


def _run_check_job():
    db = SessionLocal()
    try:
        n = check_all(db)
        logger.info("Scheduled check complete: %d equipment rows checked", n)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled check failed")
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_check_job,
        "interval",
        hours=CHECK_INTERVAL_HOURS,
        id="check_all_firmware",
        next_run_time=None,  # first run scheduled explicitly by caller
    )
    _scheduler.start()
    return _scheduler


def schedule_first_run(delay_seconds: int = 10):
    """Kick off one check shortly after startup, then settle into the interval."""
    import datetime as dt

    if _scheduler is None:
        return
    _scheduler.modify_job(
        "check_all_firmware",
        next_run_time=dt.datetime.utcnow() + dt.timedelta(seconds=delay_seconds),
    )


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
