#!/usr/bin/env python3
"""Report the size a figure's type will ACTUALLY render at.

    tools/measure_type.py examples/gallery/*/figure.svg
    tools/measure_type.py --width 1002 examples/gallery/dual/figure.svg
    tools/measure_type.py --print 3.5in examples/gallery/unet/figure.svg
    tools/measure_type.py --floor 6pt --print 6in examples/gallery/*/figure.svg

Exit 1 when anything falls under `--floor`, so it works as a gate.

WHY THIS EXISTS
---------------
Effective type size is one expression:

    rendered = unit_size x display_width / viewBox_width

Three inputs, and they are easy to get wrong together. In one evening this
repository got it wrong three ways:

  - the page stretched a 1594-unit figure into a 1460px column, a 0.92x
    REDUCTION, so 9.5-unit labels rendered at 8.7px;
  - `width_budget` computed the print floor from DETAIL_SIZE while the smallest
    type in the figure was actually a 7-unit count badge;
  - and once the SVG began declaring `width="6in"` for print, a browser honoured
    it at 576px and the same labels came out at 9.8px on a page.

Every one of those was invisible to the eye and obvious to arithmetic. `check`
already refuses a figure that would print under its floor; this answers the same
question for any display width, including a slide or a web page, and it answers
it about a RENDERED file rather than about the constants that produced it.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CSS_PX_PER_IN = 96.0
PT_PER_IN = 72.0
_UNIT_PX = {"px": 1.0, "in": CSS_PX_PER_IN, "pt": CSS_PX_PER_IN / PT_PER_IN,
            "mm": CSS_PX_PER_IN / 25.4, "cm": CSS_PX_PER_IN / 2.54}


def length_px(text: str) -> float:
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(px|in|pt|mm|cm)?\s*", str(text))
    if not m:
        raise SystemExit(f"{text!r} is not a length; try '6in', '450px' or '9pt'")
    return float(m.group(1)) * _UNIT_PX[m.group(2) or "px"]


def viewbox_width(svg: str) -> float:
    m = re.search(r'viewBox="\s*[\d.-]+\s+[\d.-]+\s+([\d.]+)', svg)
    if not m:
        raise SystemExit("no viewBox: this does not look like a draughtsman figure")
    return float(m.group(1))


def declared_width(svg: str) -> str | None:
    m = re.search(r"<svg[^>]*?\swidth=\"([^\"]+)\"", svg)
    return m.group(1) if m else None


def type_sizes(svg: str) -> list[float]:
    """Every distinct font-size in the file, in figure units."""
    return sorted({float(v) for v in re.findall(r"font-size:([\d.]+)px", svg)})


def measure(path: Path, display_px: float | None, floor_px: float | None):
    svg = path.read_text(encoding="utf-8")
    units = viewbox_width(svg)
    declared = declared_width(svg)
    intrinsic = length_px(declared) if declared else None
    shown = display_px if display_px is not None else intrinsic
    if shown is None:
        raise SystemExit(f"{path}: no width declared; pass --width or --print")
    scale = shown / units
    print(f"\n{path}")
    print(f"  {units:.0f} units wide, declared {declared!r}"
          + (f" ({intrinsic:.0f}px)" if intrinsic else ""))
    print(f"  shown at {shown:.0f}px  ->  {scale:.2f}x")
    under = []
    for u in type_sizes(svg):
        px = u * scale
        pt = px * PT_PER_IN / CSS_PX_PER_IN
        bad = floor_px is not None and px < floor_px - 1e-9
        if bad:
            under.append((u, px))
        print(f"    {u:>5.1f}u  ->  {px:6.2f}px  ({pt:5.2f}pt){'   UNDER FLOOR' if bad else ''}")
    return under


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--width", help="display width, e.g. 1002px")
    g.add_argument("--print", dest="printed", help="physical width, e.g. 6in")
    ap.add_argument("--floor", help="fail below this, e.g. 6pt")
    a = ap.parse_args(argv)

    shown = length_px(a.width or a.printed) if (a.width or a.printed) else None
    floor = length_px(a.floor) if a.floor else None
    failed = False
    for p in a.files:
        if measure(p, shown, floor):
            failed = True
    if floor is not None:
        print(f"\n{'FAIL' if failed else 'ok'}: floor {a.floor}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
