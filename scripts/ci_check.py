"""Entry point for the daily GitHub Actions run (see
.github/workflows/daily-check.yml). A CI checkout starts from scratch every
time - there's no persistent data/tracker.db (it's gitignored, same as local
dev) - so this script rebuilds a throwaway DB, restores the last known check
history from the git-committed data/equipment.json, runs the real checkers,
and writes the updated state back to that JSON file for the workflow to
commit. Local interactive use (start.command / app.main) never runs this and
is unaffected.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine, run_light_migrations  # noqa: E402
from app.export import load_json, restore_equipment_state, write_json  # noqa: E402
from app.models import Equipment  # noqa: E402
from app.runner import check_all  # noqa: E402
from app.seed import seed  # noqa: E402
from app.slack import notify_updates  # noqa: E402

JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "equipment.json"


def main():
    Base.metadata.create_all(bind=engine)
    run_light_migrations()
    seed()

    db = SessionLocal()
    try:
        previous = load_json(JSON_PATH)
        # Snapshot of each item's version *before* this run, for diffing
        # against after check_all() - what actually changed just now, not
        # just what's currently flagged (a still-pending update reconfirmed
        # today, or one auto-clearing after its 2-week window, both leave
        # current_version untouched, so neither shows up here). Empty on
        # the very first-ever run, which correctly means nothing counts as
        # "changed" yet - there's nothing to compare against.
        old_versions = {(r["manufacturer"], r["model"]): r.get("current_version") for r in previous}
        if previous:
            restore_equipment_state(db, previous)
            print(f"Restored check history for {len(previous)} items from {JSON_PATH.name}")
        else:
            print(f"No {JSON_PATH.name} found - starting fresh (first-ever run)")

        checked = check_all(db)
        print(f"Checked {checked} scrape-method items")

        changes = [
            {
                "manufacturer": item.manufacturer,
                "model": item.model,
                "previous_version": old_versions[(item.manufacturer, item.model)],
                "current_version": item.current_version,
            }
            for item in db.query(Equipment).all()
            if old_versions.get((item.manufacturer, item.model))
            and item.status == "update_detected"
            and item.current_version != old_versions[(item.manufacturer, item.model)]
        ]
        if changes:
            print(f"{len(changes)} genuine version change(s) detected this run")
            status = notify_updates(changes, os.environ.get("SLACK_WEBHOOK_URL"))
            print(f"Slack notification: {status}")

        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_json(db, JSON_PATH)
        print(f"Wrote {JSON_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
