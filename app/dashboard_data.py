"""Builds the by_manufacturer/summary/last_run context the dashboard template
needs, from a flat list of Equipment-like items. Shared by the live FastAPI
route and the static-site build script (scripts/build_static.py) so the two
can never drift apart - there's exactly one place this grouping/sorting logic
lives.
"""

STATUS_ORDER = {"update_detected": 0, "error": 1, "manual": 2, "unchecked": 3, "ok": 4}

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
    # no sub-heading).
    by_manufacturer = {}
    for item in items:
        cats = by_manufacturer.setdefault(item.manufacturer, {})
        cats.setdefault(item.category, []).append(item)

    for manufacturer, cats in by_manufacturer.items():
        for group in cats.values():
            group.sort(key=lambda i: STATUS_ORDER.get(i.status, 9))
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

    total = len(items)
    scraped = sum(1 for i in items if i.check_method == "scrape")
    summary = {
        "total": total,
        "scraped": scraped,
        "manual": sum(1 for i in items if i.check_method == "manual"),
        "updates_detected": sum(1 for i in items if i.status == "update_detected"),
        "errors": sum(1 for i in items if i.status == "error"),
        "coverage_pct": round(scraped / total * 100) if total else 0,
    }

    last_run = max((i.last_checked_at for i in items if i.last_checked_at), default=None)

    return {"by_manufacturer": by_manufacturer, "summary": summary, "last_run": last_run}
