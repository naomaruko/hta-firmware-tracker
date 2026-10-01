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
FAMILY_NAMES = {
    "ah:dlive": "Allen & Heath dLive series",
    "db:d40d90": "d&b D40/D90",
    "digico:quantum": "DiGiCo Quantum series",
    "digico:sd": "DiGiCo SD series",
    "shure:ad_transmitters": "Shure AD/ADX transmitters",
    "ssl:live": "Solid State Logic Live console series",
    "ssl:networkio": "Solid State Logic Network I/O series",
    "yamaha:rivage_pm": "Yamaha Rivage PM series",
}


def family_label(checker_key, manufacturer, models):
    """models: every model name sharing checker_key, in display order.
    Prefers the FAMILY_NAMES friendly name; falls back to the plain model
    name for a genuine singleton, or "<manufacturer> <model1>/<model2>" for
    an unnamed multi-item group - so a newly added shared checker_key still
    reads sensibly before anyone gets round to adding it above."""
    if checker_key:
        name = FAMILY_NAMES.get(checker_key)
        if name:
            return name
    if len(models) == 1:
        return models[0]
    return f"{manufacturer} {'/'.join(models)}" if manufacturer else "/".join(models)
