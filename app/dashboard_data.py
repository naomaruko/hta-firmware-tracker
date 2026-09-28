"""Builds the by_manufacturer/summary/last_run context the dashboard template
needs, from a flat list of Equipment-like items. Shared by the live FastAPI
route and the static-site build script (scripts/build_static.py) so the two
can never drift apart - there's exactly one place this grouping/sorting logic
lives.
"""

# Sub-category display order within a manufacturer's section. Categories not
# listed here (or None, for manufacturers with no sub-grouping) sort last,
# in the order encountered.
CATEGORY_ORDER = [
    "Consoles",
    "DSP Engines",
    "I/O Racks",
    "I/O & Network",
    "Network & Cards",
    "Cards & Modules",
    "Accessories",
]


def build_dashboard_context(items):
    # manufacturer -> category -> [items]. category is None for manufacturers
    # that don't use sub-grouping (the template renders those as a flat list,
    # no sub-heading). Items keep the order they arrived in (alphabetical by
    # model, per the callers' query order) rather than being reordered by
    # status - an update-available row is highlighted in place instead of
    # jumping to the top, so a row's position never shifts as its status
    # changes.
    by_manufacturer = {}
    for item in items:
        cats = by_manufacturer.setdefault(item.manufacturer, {})
        cats.setdefault(item.category, []).append(item)

    for manufacturer, cats in by_manufacturer.items():
        by_manufacturer[manufacturer] = dict(
            sorted(
                cats.items(),
                key=lambda kv: CATEGORY_ORDER.index(kv[0]) if kv[0] in CATEGORY_ORDER else len(CATEGORY_ORDER),
            )
        )

    # Case-insensitive manufacturer order - SQL's default ORDER BY is
    # case-sensitive (uppercase sorts before lowercase), which put "d&b" dead
    # last after "YAMAHA" instead of between "Audinate/Dante" and "DiGiCo"
    # where it actually belongs alphabetically.
    by_manufacturer = dict(sorted(by_manufacturer.items(), key=lambda kv: kv[0].lower()))

    summary = {
        "total": len(items),
        "updates_detected": sum(1 for i in items if i.status == "update_detected"),
        "errors": sum(1 for i in items if i.status == "error"),
    }

    last_run = max((i.last_checked_at for i in items if i.last_checked_at), default=None)

    # Some manufacturers (Yamaha, Allen & Heath, Dante/Audinate as of this
    # writing) never publish a release date at all - their checkers simply
    # have nothing to put in that field. For those, the column becomes
    # "Detected on" and shows last_changed_at (when the tracker itself first
    # caught a version change) instead of a manufacturer-published date.
    # Determined from the data (does any item for this manufacturer have a
    # release_date) rather than a hardcoded manufacturer list, so a future
    # manufacturer with the same gap is handled automatically. A manufacturer
    # counts as "has release dates" if *any* of its items has one - checkers
    # are per-manufacturer, so this is a stable, all-or-nothing trait, not
    # something that varies item to item.
    manufacturer_has_release_dates = {}
    for item in items:
        manufacturer_has_release_dates[item.manufacturer] = (
            manufacturer_has_release_dates.get(item.manufacturer, False) or bool(item.release_date)
        )

    return {
        "by_manufacturer": by_manufacturer,
        "summary": summary,
        "last_run": last_run,
        "manufacturer_has_release_dates": manufacturer_has_release_dates,
    }
