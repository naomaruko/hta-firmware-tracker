"""Builds the by_manufacturer/summary/last_run context the dashboard template
needs, from a flat list of Equipment-like items. Shared by the live FastAPI
route and the static-site build script (scripts/build_static.py) so the two
can never drift apart - there's exactly one place this grouping/sorting logic
lives.
"""
import types
from collections import defaultdict

from app.families import FAMILY_CATEGORIES, FAMILY_FORCE, FAMILY_NO_EXPAND, family_label

# Status precedence for a family's rolled-up display. Every checker
# assigns one identical CheckResult to every member of a checker_key in a
# given run, so this should never actually have to pick a "winner" from
# genuinely conflicting data - it exists for when members nonetheless
# disagree (a newly added member not yet checked, stale state left over
# from before it joined the family, ...), so a real failure on any one of
# them can't get silently absorbed into the group just because another
# member happens to report fine. Lower number wins: a check failure is the
# most urgent thing to surface, ahead of even a pending update.
_STATUS_PRIORITY = {"error": 0, "update_detected": 1, "ok": 2}

# Sub-category display order within a manufacturer's section. Categories not
# listed here (or None, for manufacturers with no sub-grouping) sort last,
# in the order encountered. "Rivage PM Series" is a family's own dedicated
# heading (see FAMILY_CATEGORIES in app/families.py), not a real equipment
# type like the rest of this list - pinned first, ahead of "Consoles", since
# it's Yamaha's flagship line rather than an equipment type a generic
# ordering would put up front. DiGiCo's SD series (see FAMILY_FORCE in
# app/families.py) isn't in this list at all: it's filed under "Consoles"
# like any other console, alongside the Quantum family row.
CATEGORY_ORDER = [
    "Rivage PM Series",
    "Consoles",
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
    A checker_key with exactly one current item renders as a plain row
    (its own model name, no chevron) unless it's in FAMILY_FORCE (see
    app/families.py) - a product line tracked today through only one
    model, but still genuinely a line rather than a one-off. No checker_key
    at all always passes through untouched.

    A pseudo-item keeps every attribute the template expects from a real
    Equipment row (status/current_version/.../source_url/last_error) plus
    `is_family` and `family_models` for the template's expand-to-pills
    treatment, and `expandable` - False for the rare family (see
    FAMILY_NO_EXPAND in app/families.py) whose collective name already
    spells out every member, so there's nothing left for a chevron to
    reveal. Those row-level fields come from whichever member has the
    most urgent status per _STATUS_PRIORITY above - normally every member
    agrees anyway, so this is just "the first member" in practice, but it
    means a genuinely failing member can never be masked by an 'ok' one:
    the row shows "Check failed", and last_error names exactly which
    model(s) broke and why, rather than reusing some other member's
    (irrelevant) error text. family_models carries each member's own
    status/last_error too (not just its name), so the expanded pills can
    flag the specific model(s) at fault instead of leaving every pill
    looking equally fine. Its `category` is the one all members share; if
    they don't (e.g. Yamaha's RIVAGE PM family spans Consoles/DSP
    Engines/I/O Racks), it's FAMILY_CATEGORIES.get(key) instead - a
    dedicated heading for that family, rather than attributing a
    multi-component system to one of its parts arbitrarily - or None if
    that's not set either, which renders with no sub-heading at all, same
    as how a manufacturer with no sub-grouping already renders.
    """
    by_key = defaultdict(list)
    for item in items:
        if item.checker_key:
            by_key[item.checker_key].append(item)

    seen_keys = set()
    result = []
    for item in items:
        key = item.checker_key
        if key and (len(by_key[key]) > 1 or key in FAMILY_FORCE):
            if key in seen_keys:
                continue
            seen_keys.add(key)
            members = by_key[key]
            categories = {m.category for m in members}
            shared_category = members[0].category if len(categories) == 1 else FAMILY_CATEGORIES.get(key)
            first = members[0]
            representative = min(members, key=lambda m: _STATUS_PRIORITY.get(m.status, 3))
            failing = [m for m in members if m.status == "error"]
            result.append(
                types.SimpleNamespace(
                    id=first.id,
                    manufacturer=first.manufacturer,
                    model=family_label(key, [m.model for m in members]),
                    category=shared_category,
                    checker_key=key,
                    source_url=representative.source_url,
                    current_version=representative.current_version,
                    previous_version=representative.previous_version,
                    release_date=representative.release_date,
                    status=representative.status,
                    last_checked_at=representative.last_checked_at,
                    last_changed_at=representative.last_changed_at,
                    last_error=(
                        "; ".join(f"{m.model}: {m.last_error}" if m.last_error else f"{m.model}: check failed" for m in failing)
                        if failing
                        else None
                    ),
                    notes=None,
                    platforms=None,
                    is_family=True,
                    family_models=[
                        types.SimpleNamespace(model=m.model, status=m.status, last_error=m.last_error)
                        for m in members
                    ],
                    # Even a FAMILY_NO_EXPAND family (nothing to add, its
                    # name already spells out every member) gets its
                    # chevron back the moment one member starts failing -
                    # that premise only holds while every member is fine,
                    # and a failure is exactly the kind of thing worth a
                    # pill to point at.
                    expandable=(key not in FAMILY_NO_EXPAND) or bool(failing),
                )
            )
        else:
            item.is_family = False
            result.append(item)
    return result


def build_dashboard_context(items):
    # manufacturer_has_release_dates reflects every real, individually-
    # tracked piece of equipment, unaffected by how rows are grouped for
    # display. The two stat counts below deliberately read from different
    # lists, for different reasons - see the summary dict.
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
        # Real physical units, from the unconsolidated list - "47 Tracked"
        # means 47 devices whether several of them currently share one row
        # or not. This is a coverage/scope number, so it shouldn't shrink
        # just because some of what it covers happens to report through
        # one firmware source.
        "total": len(items),
        # Rows, not units, from display_items - counts what's actually
        # visible on the dashboard. A family sharing one CheckResult (e.g.
        # Rivage PM's 8 components) reports one new version as one row, so
        # it shows "1 update available" rather than inflating to 8 for
        # what's genuinely a single thing to go look at.
        "updates_detected": sum(1 for i in display_items if i.status == "update_detected"),
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
