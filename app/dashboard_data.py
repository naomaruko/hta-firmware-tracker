"""Builds the by_manufacturer/summary/last_run context the dashboard template
needs, from a flat list of Equipment-like items. Shared by the live FastAPI
route and the static-site build script (scripts/build_static.py) so the two
can never drift apart - there's exactly one place this grouping/sorting logic
lives.
"""
import types
from collections import defaultdict

from app.families import FAMILY_CATEGORIES, FAMILY_NO_EXPAND, family_label

# Sub-category display order within a manufacturer's section. Categories not
# listed here (or None, for manufacturers with no sub-grouping) sort last,
# in the order encountered. "Rivage PM Series" and "SD Series" are each one
# product line's own dedicated subsection (the former a family's heading -
# see FAMILY_CATEGORIES in app/families.py, the latter a plain category on
# DiGiCo's singleton SD10 row), not a real equipment type like the rest of
# this list. "Rivage PM Series" sorts first, ahead of "Consoles" - it's
# Yamaha's flagship line, not an equipment type a generic ordering would
# otherwise place up front - while "SD Series" sits right after "Consoles",
# the closest thing to it product-wise. This list is shared across every
# manufacturer, but since no one else ever has a "Rivage PM Series" or "SD
# Series" category, pinning them here only affects Yamaha's and DiGiCo's
# own sections respectively.
CATEGORY_ORDER = [
    "Rivage PM Series",
    "Consoles",
    "SD Series",
    "DSP Engines",
    "I/O Racks",
    "I/O & Network",
    "Network & Cards",
    "Cards & Modules",
    "Accessories",
]


def _consolidate_families(items):
    """Collapses items sharing a checker_key (see app/families.py) into one
    pseudo-item per family, for display only - a family is "genuinely the
    same platform, always moves together" by construction (every member
    gets assigned the identical CheckResult from one check_all() call), not
    just items that happen to report matching version numbers, which are
    never grouped (no shared checker_key means no consolidation, full stop).
    Singletons (a checker_key with exactly one item, or no checker_key at
    all) pass through untouched - this only changes anything for the keys
    that actually have 2+ items under them.

    A pseudo-item keeps every attribute the template expects from a real
    Equipment row (status/current_version/.../source_url, all identical
    across members by construction, so the first member's values stand in
    for the group) plus `is_family` and `family_models` for the template's
    expand-to-pills treatment, and `expandable` - False for the rare family
    (see FAMILY_NO_EXPAND in app/families.py) whose collective name already
    spells out every member, so there's nothing left for a chevron to
    reveal. Its `category` is the one all members share; if they don't
    (e.g. Yamaha's RIVAGE PM family spans Consoles/DSP Engines/I/O Racks),
    it's FAMILY_CATEGORIES.get(key) instead - a dedicated heading for that
    family, rather than attributing a multi-component system to one of its
    parts arbitrarily - or None if that's not set either, which renders
    with no sub-heading at all, same as how a manufacturer with no
    sub-grouping already renders.
    """
    by_key = defaultdict(list)
    for item in items:
        if item.checker_key:
            by_key[item.checker_key].append(item)

    seen_keys = set()
    result = []
    for item in items:
        key = item.checker_key
        if key and len(by_key[key]) > 1:
            if key in seen_keys:
                continue
            seen_keys.add(key)
            members = by_key[key]
            categories = {m.category for m in members}
            shared_category = members[0].category if len(categories) == 1 else FAMILY_CATEGORIES.get(key)
            first = members[0]
            result.append(
                types.SimpleNamespace(
                    id=first.id,
                    manufacturer=first.manufacturer,
                    model=family_label(key, [m.model for m in members]),
                    category=shared_category,
                    checker_key=key,
                    source_url=first.source_url,
                    current_version=first.current_version,
                    previous_version=first.previous_version,
                    release_date=first.release_date,
                    status=first.status,
                    last_checked_at=first.last_checked_at,
                    last_changed_at=first.last_changed_at,
                    last_error=first.last_error,
                    notes=None,
                    platforms=None,
                    is_family=True,
                    family_models=[m.model for m in members],
                    expandable=key not in FAMILY_NO_EXPAND,
                )
            )
        else:
            item.is_family = False
            result.append(item)
    return result


def build_dashboard_context(items):
    # Stats (below) and manufacturer_has_release_dates reflect every real,
    # individually-tracked piece of equipment, unaffected by how rows are
    # grouped for display - "47 Tracked" means 47 physical devices whether
    # several of them currently share one row or not.
    display_items = _consolidate_families(items)

    # manufacturer -> category -> [items]. category is None for manufacturers
    # that don't use sub-grouping (the template renders those as a flat list,
    # no sub-heading). Items keep the order they arrived in (alphabetical by
    # model, per the callers' query order) rather than being reordered by
    # status - an update-available row is highlighted in place instead of
    # jumping to the top, so a row's position never shifts as its status
    # changes.
    by_manufacturer = {}
    for item in display_items:
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
