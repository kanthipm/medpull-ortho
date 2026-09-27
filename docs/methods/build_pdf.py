#!/usr/bin/env python3
"""Render custom-metrics-methodology.md to PDF.

Markdown -> HTML with markdown-it (front matter stripped, GFM tables on),
a print stylesheet, then headless Google Chrome prints it. No project
dependency is added for a document: run it with the system python3.

    python3 docs/methods/build_pdf.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

from markdown_it import MarkdownIt

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "custom-metrics-methodology.md"
OUT = HERE / "custom-metrics-methodology.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

FONT_DIR = "/System/Library/Fonts/Supplemental"
CSS = f"""
@font-face {{ font-family: Uni; src: url('{FONT_DIR}/Arial Unicode.ttf'); }}
@font-face {{ font-family: UniBold; src: url('{FONT_DIR}/Arial Bold.ttf'); }}
@page {{ size: A4; margin: 18mm 16mm 20mm 16mm; }}
html {{ font-size: 10.5pt; }}
body {{ font-family: Uni, "Arial Unicode MS", -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
       color: #1c1c1a; line-height: 1.42; max-width: 100%; }}
h1, h2, h3, th, strong {{ font-family: UniBold, Uni, "Arial Unicode MS", Helvetica, Arial, sans-serif; }}
"""
CSS = CSS + """
h1 { font-size: 20pt; margin: 0 0 6pt; letter-spacing: -0.01em; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; border-bottom: 1px solid #d8d6cf; padding-bottom: 3pt;
     page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; page-break-after: avoid; }
p, li { margin: 0 0 6pt; }
ul, ol { padding-left: 18pt; }
code { font-family: Uni, "Arial Unicode MS", Menlo, monospace; font-size: 9.4pt; background: #f3f2ee;
       padding: 0 3px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.2pt;
        page-break-inside: auto; }
th, td { border: 1px solid #cfcdc5; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #ecebe6; font-weight: 600; }
tr { page-break-inside: avoid; }
strong { font-weight: 600; }
.meta { color: #5c5b56; font-size: 9.5pt; margin-bottom: 14pt; }
"""


def strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def main() -> int:
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    body = md.render(strip_front_matter(SRC.read_text()))
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>MedPull in-house metrics: methodology</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    work = pathlib.Path(tempfile.mkdtemp(prefix="medpull-methods-"))
    page = work / "methodology.html"
    page.write_text(html)
    if not pathlib.Path(CHROME).exists():
        print(f"Chrome not found at {CHROME}; HTML left at {page}", file=sys.stderr)
        return 1
    profile = work / "profile"
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--hide-scrollbars", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=4000",
        f"--user-data-dir={profile}", "--no-pdf-header-footer",
        f"--print-to-pdf={OUT}", page.as_uri(),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)
        engine = "chrome"
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        # Headless Chrome can hang on this Mac (see memory: drive it over CDP
        # or avoid it); xhtml2pdf is pure Python and fetched on demand by uvx.
        subprocess.run(["pkill", "-f", str(profile)], capture_output=True)
        OUT.unlink(missing_ok=True)
        subprocess.run(["uvx", "--from", "xhtml2pdf", "xhtml2pdf", str(page), str(OUT)],
                       check=True, timeout=300, capture_output=True)
        engine = "xhtml2pdf"
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB) via {engine}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
