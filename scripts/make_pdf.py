"""Renders a Markdown file to PDF (README.md -> README.pdf, TODO.md -> TODO.pdf)
using the headless Chromium this project already installs for its scrapers.

    pip install markdown            # local only - not needed by the daily run
    python3 scripts/make_pdf.py README.md README.pdf "HTA Firmware Tracker - README"

The PDFs are committed copies of the markdown, so regenerate them after
editing either one.
"""
import sys

try:
    import markdown
except ImportError:
    sys.exit("This needs the 'markdown' package: pip install markdown")
from playwright.sync_api import sync_playwright

CSS = """
@page { margin: 18mm 16mm; }
body { font: 10.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color:#1a1a1a; }
h1 { font-size: 22pt; border-bottom: 2px solid #009B67; padding-bottom: 6px; }
h2 { font-size: 15pt; margin-top: 22px; color:#00694a; border-bottom: 1px solid #ddd; padding-bottom: 3px; }
h3 { font-size: 12pt; margin-top: 16px; }
code { font: 9pt "SF Mono", Menlo, monospace; background:#f2f4f3; padding: 1px 4px; border-radius: 3px; }
pre { background:#f2f4f3; padding: 10px 12px; border-radius: 6px; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.5pt; line-height: 1.35; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; }
th, td { border: 1px solid #d5d9d7; padding: 5px 8px; vertical-align: top; text-align: left; }
th { background:#eef3f1; }
tr { page-break-inside: avoid; }
li { margin: 2px 0; }
"""


def main(src, dest, title="HTA Firmware Tracker"):
    body = markdown.markdown(open(src).read(), extensions=["tables", "fenced_code", "sane_lists"])
    html = f"<!doctype html><meta charset='utf-8'><title>{title}</title><style>{CSS}</style>{body}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.pdf(path=dest, format="Letter", print_background=True)
        browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
