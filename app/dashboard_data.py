"""Builds the by_manufacturer/summary/last_run context the dashboard template
needs, from a flat list of Equipment-like items. Shared by the live FastAPI
route and the static-site build script (scripts/build_static.py) so the two
can never drift apart - there's exactly one place this grouping/sorting logic
lives.
"""
import os
import re
import types
from collections import defaultdict

from app.families import FAMILY_CATEGORIES, FAMILY_FORCE, FAMILY_NAMES, FAMILY_NO_EXPAND, family_label

# Explicit row order within a manufacturer's section, by the product code
# before " - " in the model name; anything not listed keeps its default
# alphabetical position, after the listed ones. Shure's firmware ships in
# release lines whose members share a version number, so rows that move
# together sit together (checked against Shure's own release notes, which
# name "Axient Digital 1.6.18" and "Axient Digital PSM 1.3.6" as the system
# versions): the Axient Digital line (receiver, then transmitters, then
# ShowLink access point and charger) and the PSM line (transmitter, then
# receiver, then charger). This is a fixed order, not a sort by whatever
# version a row currently shows, so rows don't jump around if one product's
# version ever diverges from the rest of its line.
MODEL_ORDER = {
    "Shure": [
        "AD4Q", "ADX1/ADX2", "AD610", "SBC240",
        "ADTQ", "ADXR", "SBC441",
    ],
}


def _model_rank(item):
    order = MODEL_ORDER.get(item.manufacturer)
    if not order:
        return 0
    code = item.model.split(" — ")[0]
    return order.index(code) if code in order else len(order)


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

def display_version(version):
    """How a version is shown: always with a leading "V" ("V2242", "V6.2.14").
    Manufacturers write them both ways - DiGiCo/Yamaha "V22", Shure/d&b/SSL
    "1.6.18" - and the dashboard and Slack read better consistent. Display
    only: the stored value stays exactly as the source publishes it, because
    update detection compares stored strings run to run, and adding a "V" there
    would make every item look newly changed."""
    if version is None:
        return version
    text = str(version).strip()
    if text[:1].isdigit():
        return "V" + text
    if text[:1] == "v" and text[1:2].isdigit():
        return "V" + text[1:]
    return text


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


def _family_error(members, failing):
    """One error line for a family row. The normal case is every member
    failing together with the identical message (one shared fetch failed) -
    that's just the message, once, rather than the same text repeated per
    model. Models are only named when the failure doesn't cover the whole
    family or the messages differ."""
    if not failing:
        return None
    by_message = defaultdict(list)
    for m in failing:
        by_message[m.last_error or "check failed"].append(m.model)
    if len(by_message) == 1 and len(failing) == len(members):
        return next(iter(by_message))
    return "; ".join(f"{', '.join(models)}: {msg}" for msg, models in by_message.items())


_ROW_FIELDS = (
    "id", "manufacturer", "model", "checker_key", "source_url", "notes", "current_version",
    "previous_version", "release_date", "platforms", "status", "last_checked_at",
    "last_changed_at", "last_error",
)


def _plain_row(item, category):
    """A standalone row for one member of a family that has split apart.
    A copy rather than the item itself, because items from the live app are
    database rows and setting a column (category) on one could get written
    back; this is display-only."""
    row = types.SimpleNamespace(**{f: getattr(item, f, None) for f in _ROW_FIELDS})
    row.category = category
    row.is_family = False
    return row


def _version_groups(members):
    """Splits a family's members into groups that currently share a version,
    in first-seen order. If there's only one version among them (the normal
    case), that's one group - and a member with no version yet (a newly added
    item, not yet checked) rides along with it. If there are several, members
    with no version can't be placed anywhere, so each stands alone."""
    versions = list(dict.fromkeys(m.current_version for m in members if m.current_version))
    if len(versions) <= 1:
        return [members]
    groups = {v: [] for v in versions}
    unchecked = []
    for m in members:
        (groups[m.current_version] if m.current_version else unchecked).append(m)
    return list(groups.values()) + [[m] for m in unchecked]


def _natural(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def _subset_label(key, models):
    """Name for part of a family that has split from the rest - the family
    name alone would wrongly imply the whole line, and two rows with the same
    name would look like a duplicate. "Quantum series (112, 225, 225DS)": the
    models' shared leading words are dropped so the list stays short. A family
    whose name already spells out its members (FAMILY_NO_EXPAND, e.g.
    "D25/D40/D90") just lists the subset the same way ("D40/D90")."""
    models = sorted(models, key=_natural)
    if key in FAMILY_NO_EXPAND:
        return "/".join(models)
    name = FAMILY_NAMES.get(key)
    if not name:
        return family_label(key, models)
    prefix = os.path.commonprefix(models)
    prefix = prefix[: prefix.rfind(" ") + 1]  # whole words only
    return f"{name} ({', '.join(m[len(prefix):] for m in models)})"


def _family_row(key, members, label):
    """One collapsed pseudo-item standing in for `members` (see
    _consolidate_families for what it carries and why)."""
    categories = {m.category for m in members}
    shared_category = members[0].category if len(categories) == 1 else FAMILY_CATEGORIES.get(key)
    first = members[0]
    # Most urgent status wins; among equals prefer a member that has a
    # version, so an unchecked newcomer doesn't blank the row.
    representative = min(members, key=lambda m: (_STATUS_PRIORITY.get(m.status, 3), m.current_version is None))
    failing = [m for m in members if m.status == "error"]
    return types.SimpleNamespace(
        id=first.id,
        manufacturer=first.manufacturer,
        model=label,
        category=shared_category,
        checker_key=key,
        source_url=representative.source_url,
        current_version=representative.current_version,
        previous_version=representative.previous_version,
        release_date=representative.release_date,
        status=representative.status,
        last_checked_at=representative.last_checked_at,
        last_changed_at=representative.last_changed_at,
        last_error=_family_error(members, failing),
        notes=None,
        platforms=None,
        is_family=True,
        family_models=[m.model for m in members],
        expandable=key not in FAMILY_NO_EXPAND,
    )


def _consolidate_families(items):
    """Collapses items sharing a checker_key (see app/families.py) into
    pseudo-items, for display only. A family is "genuinely the same platform"
    - which is what makes one row honest in the normal case, since a shared
    source gives every member the identical result - but a source can publish
    different versions for different members: DiGiCo shipped v2242.4 for the
    Q112/Q225/Q225DS only, while the rest of the Quantum line stayed on
    v2242. So within a family, members that currently share a version
    collapse together and members on a different version don't: two
    collapsed rows for that Quantum case ("Quantum series (112, 225, 225DS)"
    and "Quantum series (5, 7, 326, 338)", see _subset_label), a plain row
    for a lone member on its own version. It's all recomputed from the
    current versions every build, so the family is back to one row the moment
    everyone matches again. Items that merely happen to report matching
    versions are still never grouped (no shared checker_key means no
    consolidation, full stop).
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
    the row shows "Check failed", and last_error says why (see
    _family_error), rather than reusing some other member's (irrelevant)
    error text. Its `category` is the one all members share; if they don't
    (e.g. Yamaha's RIVAGE PM family spans Consoles/DSP Engines/I/O Racks),
    it's FAMILY_CATEGORIES.get(key) instead - a dedicated heading for that
    family, rather than attributing a multi-component system to one of its
    parts arbitrarily - or None if that's not set either, which renders
    with no sub-heading at all, same as how a manufacturer with no
    sub-grouping already renders. A lone member split off from such a family
    stays in that same dedicated subsection.
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
            groups = _version_groups(by_key[key])
            whole = len(groups) == 1
            for group in groups:
                if len(group) == 1 and not (whole and key in FAMILY_FORCE):
                    result.append(_plain_row(group[0], FAMILY_CATEGORIES.get(key, group[0].category)))
                else:
                    models = [m.model for m in group]
                    label = family_label(key, models) if whole else _subset_label(key, models)
                    result.append(_family_row(key, group, label))
        else:
            item.is_family = False
            result.append(item)
    return result


def build_dashboard_context(items):
    # manufacturer_has_release_dates reflects every real, individually-
    # tracked piece of equipment, unaffected by how rows are grouped for
    # display. The two stat counts below deliberately read from different
    # lists, for different reasons - see the summary dict.
    # Stable sort: only reorders manufacturers that have a MODEL_ORDER; every
    # other row keeps the order it arrived in.
    display_items = sorted(_consolidate_families(items), key=_model_rank)

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
        # Real physical units, from the unconsolidated list - "48 Tracked"
        # means 48 devices whether several of them currently share one row
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
