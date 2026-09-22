"""Regenerates app/static/icons/* from two canonical source assets at the
project root:

- hta-firmware-tracker-icon.png: the rounded-square app icon (opaque dark
  navy background baked in). Used for every favicon/PWA icon size, which
  all need a filled background regardless of what page/OS chrome they sit
  in.
- hta-firmware-tracker-logo-transparent.png: the same glyph with no
  background, true alpha transparency. Used only for the in-app header
  icon, which sits directly on the page's own background (and needs to
  work in both light and dark mode - checked contrast against both before
  adopting it).

Not run automatically by anything (icons don't change often) - run manually
with `python3 scripts/gen_icons.py` after activating the venv, then commit
the resulting PNGs/ICO.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "hta-firmware-tracker-icon.png"
SOURCE_LOGO = ROOT / "hta-firmware-tracker-logo-transparent.png"
OUT = ROOT / "app" / "static" / "icons"

# The source has its own rounded corners baked in with transparency outside
# them (not a plain square) - sampled from its background for the couple of
# spots that need a flat opaque fill instead of that transparency (Apple
# explicitly wants no alpha in touch icons; maskable icons need real
# padding, not baked-in rounding, so those corners get flattened too before
# padding out).
BG_FLATTEN_COLOR = (12, 40, 60, 255)


def _resize(im, size):
    return im.resize((size, size), Image.LANCZOS)


def _flatten(im, color):
    """Composites onto an opaque background of `color`, removing alpha."""
    bg = Image.new("RGBA", im.size, color)
    return Image.alpha_composite(bg, im).convert("RGB")


def _padded(im, size, scale, color):
    """Shrinks the (already-flattened, square) image to `scale` of `size`
    and centers it on an opaque `size`x`size` canvas of `color` - real
    margin on every side, not just relying on the source's own baked-in
    corner rounding (which doesn't help a mask that crops further in, e.g.
    a circle), for maskable-purpose PWA icons."""
    inner = size * scale
    canvas = Image.new("RGB", (size, size), color[:3])
    resized = im.resize((round(inner), round(inner)), Image.LANCZOS)
    offset = (round((size - inner) / 2), round((size - inner) / 2))
    canvas.paste(resized, offset)
    return canvas


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.open(SOURCE).convert("RGBA")

    # Favicons + PWA "any" icons: straight high-quality resize, transparency
    # (and the source's own rounded corners) kept as-is.
    for name, size in [
        ("favicon-16.png", 16),
        ("favicon-32.png", 32),
        ("icon-192.png", 192),
        ("icon-512.png", 512),
    ]:
        _resize(src, size).save(OUT / name)

    # apple-touch-icon: iOS doesn't want alpha in this one, so the
    # transparent corners get flattened to an opaque fill first (iOS
    # applies its own corner rounding on top regardless).
    flattened = _flatten(src, BG_FLATTEN_COLOR)
    _resize(flattened, 180).save(OUT / "apple-touch-icon.png")

    # In-app header icon: the transparent-background logo, not the
    # favicon/PWA source - it sits directly on the page rather than needing
    # its own background. Modest size (46px display, ~2x headroom for
    # retina).
    logo = Image.open(SOURCE_LOGO).convert("RGBA")
    _resize(logo, 96).save(OUT / "app-icon-header.png")

    # Maskable: real padding (not just the source's baked-in rounding) so
    # an aggressive OS mask (e.g. a circle) can't clip the glyph - the
    # unsimplified source has the arrow tip touching the very top edge with
    # zero margin, which a circular mask would cut into.
    _padded(flattened, 512, 0.72, BG_FLATTEN_COLOR).save(OUT / "icon-maskable-512.png")

    # favicon.ico: single 16x16 frame (its classic/primary use case).
    Image.open(OUT / "favicon-16.png").save(OUT / "favicon.ico", format="ICO", sizes=[(16, 16)])

    print(f"Wrote icons to {OUT}")


if __name__ == "__main__":
    main()
