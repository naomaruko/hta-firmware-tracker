"""JSON <-> Equipment table round-trip, used by the CI pipeline
(scripts/ci_check.py) so the git-committed data/equipment.json file - not a
throwaway CI filesystem - is the durable source of truth for check history
(current/previous version, last_checked_at, etc.) across scheduled runs.
Local interactive use (start.command) is untouched by any of this - it keeps
using data/tracker.db exactly as before.
"""
import datetime as dt
import json

from app.models import Equipment

_DT_FIELDS = ("last_checked_at", "last_changed_at")


def equipment_to_json(db) -> list:
    items = db.query(Equipment).order_by(Equipment.manufacturer, Equipment.model).all()
    return [item.to_dict() for item in items]


def write_json(db, path):
    with open(path, "w") as f:
        json.dump(equipment_to_json(db), f, indent=2)
        f.write("\n")


def _parse_dt(value):
    return dt.datetime.fromisoformat(value) if value else None


def load_json(path):
    """Returns the raw list of dicts from a previously-written
    data/equipment.json, or [] if the file doesn't exist yet (first-ever run)."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def restore_equipment_state(db, records: list):
    """Overlays the dynamic, check-history fields (current_version,
    previous_version, status, timestamps, last_error) from a previously
    exported JSON list onto the Equipment rows seed() just (re)created in a
    fresh DB - matched by (manufacturer, model), the same natural key seed()
    itself uses. Rows with no matching record (new equipment) are left as
    seed() initialized them. This is what lets a from-scratch CI checkout
    remember "the last known version was X" instead of re-flagging every
    single item as a false 'update detected' on every run.
    """
    by_key = {(r["manufacturer"], r["model"]): r for r in records}
    for item in db.query(Equipment).all():
        r = by_key.get((item.manufacturer, item.model))
        if not r:
            continue
        item.current_version = r.get("current_version")
        item.previous_version = r.get("previous_version")
        item.release_date = r.get("release_date")
        item.platforms = r.get("platforms")
        item.status = r.get("status") or item.status
        item.last_error = r.get("last_error")
        for field in _DT_FIELDS:
            setattr(item, field, _parse_dt(r.get(field)))
    db.commit()
