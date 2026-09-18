"""Entry point for the daily GitHub Actions run (see
.github/workflows/daily-check.yml). A CI checkout starts from scratch every
time - there's no persistent data/tracker.db (it's gitignored, same as local
dev) - so this script rebuilds a throwaway DB, restores the last known check
history from the git-committed data/equipment.json, runs the real checkers,
and writes the updated state back to that JSON file for the workflow to
commit. Local interactive use (start.command / app.main) never runs this and
is unaffected.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine, run_light_migrations  # noqa: E402
from app.export import load_json, restore_equipment_state, write_json  # noqa: E402
from app.runner import check_all  # noqa: E402
from app.seed import seed  # noqa: E402

JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "equipment.json"


def main():
    Base.metadata.create_all(bind=engine)
    run_light_migrations()
    seed()

    db = SessionLocal()
    try:
        previous = load_json(JSON_PATH)
        if previous:
            restore_equipment_state(db, previous)
            print(f"Restored check history for {len(previous)} items from {JSON_PATH.name}")
        else:
            print(f"No {JSON_PATH.name} found - starting fresh (first-ever run)")

        checked = check_all(db)
        print(f"Checked {checked} scrape-method items")

        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_json(db, JSON_PATH)
        print(f"Wrote {JSON_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
