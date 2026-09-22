"""Regenerates app/static/icons/* from the same pulse-wave glyph used in the
header's inline SVG (app/templates/dashboard.html - keep the two in sync by
hand if that path ever changes).

Not run automatically by anything (icons don't change often) - run manually
with `python3 scripts/gen_icons.py` after activating the venv, then commit
the resulting PNGs/ICO.

16x16 uses a deliberately simplified single-peak version of the glyph, not
just a smaller/bolder render of the full 6-point wave: tested via direct
pixel inspection (render at true size, no anti-aliasing tricks) and the full
path collapses into an unrecognizable white blob at 16 real pixels no matter
how bold the stroke. 32px and up hold up fine with the real glyph - the
"needs simplifying" cutoff is specific to the smallest size, not a general
problem.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image

GREEN = "#009B67"
# Same path as the header's inline SVG (viewBox 0 0 24 24).
FULL_PATH = "M5 13H7.5L9.5 8L12.5 17L14.5 9.5L16 13H19"
# 16px-only: a single flat-peak-flat spike instead of the full double-bump
# wave - keeps the "pulse monitor" motif recognizable at a size where the
# real path just turns into a blob.
SIMPLE_PATH = "M3 13H9L13 5L17 13H21"

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "icons"


def _html(size, path, stroke, glyph_pct, radius_pct):
    glyph_px = size * glyph_pct
    radius_px = size * radius_pct
    return f"""
    <html><body style="margin:0;">
    <div style="width:{size}px;height:{size}px;background:{GREEN};border-radius:{radius_px}px;
                display:flex;align-items:center;justify-content:center;">
      <svg width="{glyph_px}" height="{glyph_px}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="{path}" stroke="white" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      </svg>
    </div>
    </body></html>
    """


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)

        def render(path_out, size, path, stroke, glyph_pct, radius_pct):
            page.set_viewport_size({"width": size, "height": size})
            page.set_content(_html(size, path, stroke, glyph_pct, radius_pct))
            page.screenshot(path=str(path_out))

        # Favicons: 16 (simplified) and 32 (full glyph), both rounded-square
        # to match the app's own visual language.
        render(OUT / "favicon-16.png", 16, SIMPLE_PATH, 3.6, 0.78, 0.25)
        render(OUT / "favicon-32.png", 32, FULL_PATH, 1.8, 0.68, 0.22)

        # apple-touch-icon: iOS applies its own corner rounding, so the
        # source is a plain square (no radius).
        render(OUT / "apple-touch-icon.png", 180, FULL_PATH, 1.3, 0.62, 0)

        # PWA manifest icons.
        render(OUT / "icon-192.png", 192, FULL_PATH, 1.3, 0.62, 0.22)
        render(OUT / "icon-512.png", 512, FULL_PATH, 1.15, 0.62, 0.22)
        # Maskable: OS applies its own mask shape, so no rounding of our own,
        # and the glyph is shrunk further to stay inside the safe zone.
        render(OUT / "icon-maskable-512.png", 512, FULL_PATH, 1.15, 0.40, 0)

        browser.close()

    # Classic /favicon.ico fallback for browsers/bookmarks that request it
    # directly regardless of <link> tags - a single 16x16 frame (its
    # historical primary use case), built from the same simplified glyph.
    Image.open(OUT / "favicon-16.png").save(OUT / "favicon.ico", format="ICO", sizes=[(16, 16)])

    print(f"Wrote icons to {OUT}")


if __name__ == "__main__":
    main()
