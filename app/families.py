"""Firmware families: groups of equipment that share one checker_key, and
therefore are always checked together and always report the identical
version from one source - as opposed to items that just happen to report
matching version numbers by coincidence, which are never grouped.

checker_key is assigned per actual firmware source (see app/seed.py), not
per observed version match, so this is a reliable "these are really the
same platform" signal rather than a guess. Used both to collapse Slack
update notifications into one message per family (app/slack.py) and to
consolidate the dashboard's table/card rows into one row per family
(app/dashboard_data.py) - sharing this one mapping is what keeps the two
from ever disagreeing about what counts as "the same family."
"""

# checker_key -> a human-readable name for the family, shown instead of
# listing every model. Only worth naming here for keys that actually cover
# more than one item, or that stand for a whole product family even though
# only some of it is tracked (DiGiCo SD) - everything else falls back to
# the model name(s) in family_label() below.
#
# Deliberately brand-free (e.g. "Quantum series", not "DiGiCo Quantum
# series") - on the dashboard this sits inside a manufacturer's own
# section, directly under its "DiGiCo"/"Allen & Heath"/... heading, so
# repeating the brand in every row under it would just be noise. Slack
# notifications don't have that heading for context, so slack.py prepends
# the manufacturer itself (via MANUFACTURER_LABELS below) rather than
# using these names bare - still reads as "DiGiCo Quantum series" there,
# just assembled instead of stored twice.
FAMILY_NAMES = {
    "ah:dlive": "dLive series",
    "db:d40d90": "D25/D40/D90",
    "digico:quantum": "Quantum series",
    "digico:sd": "SD series",
    "ssl:live": "Live console series",
    "ssl:networkio": "Network I/O series",
    "yamaha:rio_d2": "Rio-D2 series",
    "yamaha:rivage_pm": "Rivage PM series",
}

# manufacturer (as stored on Equipment.manufacturer) -> how it should read
# in a sentence. Every manufacturer's raw field is already proper-cased
# except Yamaha's, which is kept ALL CAPS for the dashboard's own section
# heading (matching Yamaha's own logo styling) - "YAMAHA Rivage PM series"
# would look shouty next to it in a Slack message, so slack.py corrects it
# through this map rather than changing the stored field everywhere else
# that reads it (the dashboard heading included).
MANUFACTURER_LABELS = {
    "YAMAHA": "Yamaha",
}

# checker_key -> True for a family whose FAMILY_NAMES entry already spells
# out every member model by name (e.g. "D25/D40/D90" names all three),
# unlike the generic "<product line> series" names used everywhere else
# (e.g. "Quantum series", which doesn't say "112/225/326/338/5/7"). There's
# nothing left for a model-pills expand to add in that case, so that row
# skips the chevron/expand UI entirely - on both desktop and phone - rather
# than offering an expand control with nothing new behind it.
FAMILY_NO_EXPAND = {"db:d40d90"}

# checker_key -> a dedicated dashboard category heading for a family whose
# members span more than one of a manufacturer's existing type-based
# subsections (Consoles / DSP Engines / I/O Racks / ...) and so don't
# cleanly sort into any single one of them - RIVAGE PM is a multi-component
# system (console surfaces, DSP engines, I/O racks) tracked as one firmware
# release, not a console alone, so trying to file it under "Consoles" would
# misrepresent the other two-thirds of what it covers. Only worth setting
# here when the manufacturer already uses category sub-grouping for its
# other equipment - a family that's the only thing tracked under a
# manufacturer (e.g. Allen & Heath's dLive series) is left out of this map
# and stays uncategorized instead (see dashboard_data.py), since a heading
# identical to the one row underneath it would be pure noise.
FAMILY_CATEGORIES = {
    "yamaha:rivage_pm": "Rivage PM Series",
}

# checker_key -> True to render as a family row (collective name, chevron,
# model-pills expand) even though it currently has only one tracked member
# - DiGiCo SD stands for the whole SD console line, of which only SD10 is
# tracked today, same as how FAMILY_NAMES already names it "SD series"
# rather than leaving it to fall back to the bare model name. Without this,
# a lone member is indistinguishable from "a single oddly-named item" and
# renders as a plain row instead - this says that's not the case here, and
# a second SD-series console added later would join this family exactly
# like it already would any other.
FAMILY_FORCE = {"digico:sd"}


def family_label(checker_key, models):
    """models: every model name sharing checker_key, in display order.
    Prefers the FAMILY_NAMES friendly name; falls back to the plain model
    name for a genuine singleton, or "<model1>/<model2>" for an unnamed
    multi-item group - so a newly added shared checker_key still reads
    sensibly on the dashboard before anyone gets round to naming it above.
    No manufacturer in that fallback either, for the same reason FAMILY_NAMES
    itself is brand-free - the dashboard already shows it as the section
    heading. (Slack's equivalent lives in slack.py, not here, since Slack
    messages have no such heading to lean on.)"""
    if checker_key:
        name = FAMILY_NAMES.get(checker_key)
        if name:
            return name
    if len(models) == 1:
        return models[0]
    return "/".join(models)
