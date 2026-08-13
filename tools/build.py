#!/usr/bin/env python3
"""Build index.html by embedding the blank checklist PDF into src/app.html.

The generated report is a stamped copy of the real form, so the form itself has
to travel with the page. Run this after changing either file:

    python3 tools/build.py
"""
import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "app.html"
PDF = ROOT / "assets" / "FPGROC_Service_Checklist.pdf"
OUT = ROOT / "index.html"
PLACEHOLDER = "__TEMPLATE_PDF_B64__"


def main() -> int:
    html = SRC.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        print(f"error: {PLACEHOLDER} not found in {SRC}", file=sys.stderr)
        return 1

    b64 = base64.b64encode(PDF.read_bytes()).decode("ascii")
    OUT.write_text(html.replace(PLACEHOLDER, b64), encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, template {len(b64) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
