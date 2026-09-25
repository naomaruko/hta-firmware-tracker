"""Seed the database from the HTA equipment list.

Each row: (manufacturer, model, category, checker_key, source_url, notes)

Every row is checked automatically by the checker module its checker_key
points at. category is an
optional sub-grouping shown within a manufacturer's section on the dashboard
(e.g. "Consoles" vs "I/O Racks") - None means that manufacturer's items are
just listed flat, no sub-grouping (used where the list is short enough or
homogeneous enough that splitting it up wouldn't help).
"""
from app.database import Base, SessionLocal, engine, run_light_migrations
from app.models import Equipment

DIGICO_QUANTUM_URL = "https://support.digico.biz/hc/en-gb/categories/26478756671377-Software-Downloads"
DIGICO_SD_URL = DIGICO_QUANTUM_URL
DIGICO_ORANGEBOX_URL = DIGICO_QUANTUM_URL
DIGICO_DMI_URL = DIGICO_QUANTUM_URL

YAMAHA_RIVAGE_URL = "https://usa.yamaha.com/support/updates/rivage_pm_firm.html"
YAMAHA_DM7_URL = "https://usa.yamaha.com/support/updates/dm7_firm.html"
YAMAHA_SWP1_URL = "https://usa.yamaha.com/support/updates/swp1_firm.html"
YAMAHA_HY144_URL = "https://usa.yamaha.com/support/updates/hy144-d-src_firm.html"
YAMAHA_RIO3224D2_URL = "https://usa.yamaha.com/support/updates/rio3224-d2_firm.html"
YAMAHA_RIO1608D2_URL = "https://usa.yamaha.com/support/updates/rio1608-d2_firm.html"

SHURE_ARCHIVE_INDEX = "https://www.shure.com/en-US/support/downloads/software-firmware-archive"

SSL_DOWNLOADS_URL = "https://solidstatelogic.com/support-page/downloads"
AH_DLIVE_URL = "https://www.allen-heath.com/hardware/dlive-series/all-models/resources/"
DB_DOWNLOADS_URL = "https://www.dbaudio.com/global/en/service-and-support/downloads/"
DANTE_DOWNLOADS_URL = "https://www.getdante.com/resources/software-downloads/"

# fmt: off
EQUIPMENT = [
    # --- DiGiCo: scraped from support.digico.biz's Zendesk help-center API ---
    ("DiGiCo", "Quantum 7", "Consoles", "digico:quantum", DIGICO_QUANTUM_URL, None),
    ("DiGiCo", "Quantum 5", "Consoles", "digico:quantum", DIGICO_QUANTUM_URL, None),
    ("DiGiCo", "Quantum 338", "Consoles", "digico:quantum", DIGICO_QUANTUM_URL, None),
    ("DiGiCo", "Quantum 326", "Consoles", "digico:quantum", DIGICO_QUANTUM_URL, None),
    ("DiGiCo", "Quantum 225", "Consoles", "digico:quantum", DIGICO_QUANTUM_URL, None),
    ("DiGiCo", "SD10", "Consoles", "digico:sd", DIGICO_SD_URL, None),
    ("DiGiCo", "Orange Box", "Accessories", "digico:orangebox", DIGICO_ORANGEBOX_URL, None),
    ("DiGiCo", "DMI-Dante / DMI-Dante2 (Zynq HC)", "Cards & Modules", "digico:dmidante_zynq", DIGICO_DMI_URL, "The DMI-Dante64@96 card with the newer Zynq HC Dante module (cards built from March 2023 on)."),
    ("DiGiCo", "DMI-Dante / DMI-Dante2 (Summit HC)", "Cards & Modules", "digico:dmidante_summit", DIGICO_DMI_URL, "The older DMI-Dante64@96 with the Summit HC Dante module (discontinued design; separate firmware line from Zynq)."),

    # --- Yamaha: static per-product firmware pages on usa.yamaha.com ---
    ("YAMAHA", "Rivage PM10", "Consoles", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, None),
    ("YAMAHA", "Rivage PM7", "Consoles", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, None),
    ("YAMAHA", "Rivage PM5", "Consoles", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, None),
    ("YAMAHA", "DM7-EX", "Consoles", "yamaha:dm7", YAMAHA_DM7_URL, None),
    ("YAMAHA", "DSP-R10", "DSP Engines", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, "Shares the RIVAGE PM console firmware version (confirmed via Yamaha's official compatibility chart)."),
    ("YAMAHA", "DSP-RX", "DSP Engines", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, "Shares the RIVAGE PM console firmware version (confirmed via Yamaha's official compatibility chart)."),
    ("YAMAHA", "DSP-RX-EX", "DSP Engines", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, "Shares the RIVAGE PM console firmware version (confirmed via Yamaha's official compatibility chart)."),
    ("YAMAHA", "RPio622", "I/O Racks", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, "Shares the RIVAGE PM console firmware version (confirmed via Yamaha's official compatibility chart)."),
    ("YAMAHA", "RPio222", "I/O Racks", "yamaha:rivage_pm", YAMAHA_RIVAGE_URL, "Shares the RIVAGE PM console firmware version (confirmed via Yamaha's official compatibility chart)."),
    ("YAMAHA", "Rio3224-D2", "I/O Racks", "yamaha:rio3224d2", YAMAHA_RIO3224D2_URL, None),
    ("YAMAHA", "Rio1608-D2", "I/O Racks", "yamaha:rio1608d2", YAMAHA_RIO1608D2_URL, None),
    ("YAMAHA", "SWP1-8", "Network & Cards", "yamaha:swp1", YAMAHA_SWP1_URL, None),
    ("YAMAHA", "HY144-D-SRC", "Network & Cards", "yamaha:hy144dsrc", YAMAHA_HY144_URL, None),

    # --- Solid State Logic: support.solidstatelogic.com runs on Zendesk too
    # (same trick as DiGiCo). SOLSA versions 1:1 with Live console software;
    # ML 32.32/Blacklight II ship firmware via the Network I/O package. ---
    ("Solid State Logic", "L650", "Consoles", "ssl:live", SSL_DOWNLOADS_URL, "Tracked via SOLSA. Confirmed identical to the console software version (verified against SSL's logged-in \"Live Software Downloads\" page, which lists both under the same version number) - that exact page is login-gated so isn't scraped directly, but SOLSA's public article mirrors it exactly."),
    ("Solid State Logic", "L550+", "Consoles", "ssl:live", SSL_DOWNLOADS_URL, "Tracked via SOLSA. Confirmed identical to the console software version (verified against SSL's logged-in \"Live Software Downloads\" page, which lists both under the same version number) - that exact page is login-gated so isn't scraped directly, but SOLSA's public article mirrors it exactly."),
    ("Solid State Logic", "L350+", "Consoles", "ssl:live", SSL_DOWNLOADS_URL, "Tracked via SOLSA. Confirmed identical to the console software version (verified against SSL's logged-in \"Live Software Downloads\" page, which lists both under the same version number) - that exact page is login-gated so isn't scraped directly, but SOLSA's public article mirrors it exactly."),
    ("Solid State Logic", "ML 32.32", "I/O & Network", "ssl:networkio", SSL_DOWNLOADS_URL, None),
    ("Solid State Logic", "Blacklight II Concentrator", "I/O & Network", "ssl:networkio", SSL_DOWNLOADS_URL, None),

    # --- Allen & Heath: site returns HTTP 403 to plain requests (bot
    # protection) but loads fine in a real (headless) browser. ---
    ("Allen & Heath", "dLive S5000", "Consoles", "ah:dlive", AH_DLIVE_URL, None),
    ("Allen & Heath", "dLive DM64 MixRack", "I/O Racks", "ah:dlive", AH_DLIVE_URL, None),

    # --- Shure: most have a static per-product firmware archive page.
    # AD221, AD651B, P9HW, and SBC-200 were dropped at HTA's request (not
    # gear they're tracking).
    ("Shure", "AD1/AD2 — Axient Digital Bodypack/Handheld Transmitter", None, "shure:ad_transmitters", None, None),
    ("Shure", "AD4Q — Axient Digital Four-Channel Receiver", None, "shure:ad4q", None, None),
    ("Shure", "AD600 — Axient Digital Spectrum Manager", None, "shure:ad600", None, None),
    ("Shure", "AD610 — Axient Digital Diversity ShowLink Access Point", None, "shure:ad610", None, "Confirmed via Shure Update Utility (1.5.4.0, Mar 27 2026)."),
    ("Shure", "AD8C — Axient Digital PSM 8-Port Antenna Combiner", None, "shure:ad8c", None, None),
    ("Shure", "ADTQ — Axient Digital PSM Quad Channel Transmitter", None, "shure:adtq", None, "G57 band, US SKU. Shure lists its firmware together with the ADTD as \"ADTD and ADTQ\"."),
    ("Shure", "ADX1/ADX2 — Axient Digital Bodypack/Handheld Transmitter", None, "shure:ad_transmitters", None, None),
    ("Shure", "ADXR — Axient Digital PSM Wireless Bodypack Receiver", None, "shure:adxr", None, None),
    ("Shure", "SBC240 — Two-Bay Networked Docking Charger", None, "shure:sbc240", None, "Shares a firmware page with SBC220 (\"SBC220/240 - 2-Bay Chargers\")."),
    ("Shure", "SBC441 — Axient Digital PSM 4-Bay Docking Charger", None, "shure:sbc441", None, None),
    ("Shure", "SBRC-US — Shure Battery Rack Charger", None, "shure:sbrc", None, None),

    # --- d&b audiotechnik: the Download Center's search is JS-rendered and
    # sits behind a cookie-consent overlay, so it needs a real browser. D40
    # and D90 share one combined firmware release; DN1 Switch has its own
    # separate release ("DN1 Firmware Release notes").
    ("d&b", "D40", None, "db:d40d90", DB_DOWNLOADS_URL, "Shares a firmware release with D90 (\"D90/D40/D25/40D/25D Firmware Release notes\")."),
    ("d&b", "D90", None, "db:d40d90", DB_DOWNLOADS_URL, "Shares a firmware release with D40."),
    ("d&b", "DN1 Switch", None, "db:dn1", DB_DOWNLOADS_URL, None),

    # --- Dante/Audinate: the software-downloads page is an accordion -
    # version numbers only appear in the DOM after clicking a section open,
    # so it needs a real browser rather than a plain fetch. ---
    ("Audinate/Dante", "Dante Controller", None, "dante:controller", DANTE_DOWNLOADS_URL, None),
]
# fmt: on


def seed(reset: bool = False):
    """Sync the `equipment` table to match EQUIPMENT above: add new rows,
    update fields on existing rows if they changed (e.g. a model moving to a
    different checker), and remove rows no longer listed (e.g. gear HTA
    dropped from tracking). Existing current_version/status history is left
    alone unless the checker itself changed.
    """
    Base.metadata.create_all(bind=engine)
    run_light_migrations()
    db = SessionLocal()
    try:
        if reset:
            db.query(Equipment).delete()
            db.commit()

        existing = {(e.manufacturer, e.model): e for e in db.query(Equipment).all()}
        wanted_keys = set()
        added = updated = removed = 0

        for manufacturer, model, category, checker_key, source_url, notes in EQUIPMENT:
            key = (manufacturer, model)
            wanted_keys.add(key)
            row = existing.get(key)

            if row is None:
                db.add(
                    Equipment(
                        manufacturer=manufacturer,
                        model=model,
                        category=category,
                        checker_key=checker_key,
                        source_url=source_url,
                        notes=notes,
                        status="unchecked",
                    )
                )
                added += 1
                continue

            changed = False
            if row.checker_key != checker_key:
                row.checker_key = checker_key
                # Checker changed: reset so it gets picked up on the next
                # check rather than showing stale state from the old one.
                row.status = "unchecked"
                row.current_version = None
                row.previous_version = None
                row.last_error = None
                row.platforms = None
                row.content_hash = None
                row.review_since = None
                changed = True
            if category != row.category:
                row.category = category
                changed = True
            if notes != row.notes:
                row.notes = notes
                changed = True
            if source_url and row.source_url != source_url:
                row.source_url = source_url
                changed = True
            if changed:
                updated += 1

        for key, row in existing.items():
            if key not in wanted_keys:
                db.delete(row)
                removed += 1

        db.commit()
        return {"added": added, "updated": updated, "removed": removed}
    finally:
        db.close()


if __name__ == "__main__":
    stats = seed()
    print(f"Seed sync: {stats}")
