#!/usr/bin/env python3
"""Two models in one frame, at ONE scale — and the scale is checked, not assumed.

    tools/beside.py examples/tube/beside-line.json examples/line/beside-tube.json \
        -o examples/line/beside-the-tube.svg

WHY THIS EXISTS. bugarach asked for `line` drawn *beside* `tube` rather than in
isolation, because the whole content of the newer architecture is WHERE the ROI
axis collapses — after the bounded vote, not before the first kernel — and a
difference between two figures is only visible when the two figures are
comparable. Two SVGs opened in two tabs are not: a browser scales each to its own
window and a mark in one is no longer the size of a mark in the other.

WHAT "ONE SCALE" MEANS HERE, EXACTLY. Each panel is rendered by draughtsman
itself and embedded as a NESTED `<svg>` whose `width`/`height` are its own
viewBox extent, so nothing is resampled: a figure unit is a figure unit across
the whole frame. That is necessary and not sufficient — two panels drawn at
different `output.width` would still put different physical sizes on one page —
so this REFUSES a pair whose specs disagree about what a unit is worth. The
check is the tool; the composition is the easy part.

The panels are NOT committed. They are rendered from the two committed specs on
every run, so the frame cannot drift from the specs the way a pasted-in picture
would. `tests/test_beside.py` re-runs this and diffs the result.

RUNNING IT needs nothing the package does not already have — `render` wants
neither torch nor a system binary, which is the property SPEC.md §6 is built on.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from draughtsman.facts import Graph                      # noqa: E402
from draughtsman.render import (CAPTION_SIZE, CAPTION_LINE, DETAIL_SIZE,  # noqa: E402
                                INK, MUTED, TITLE_SIZE, render)
from draughtsman.spec import length_pt, load             # noqa: E402
from draughtsman.text import FONT_STACK                  # noqa: E402

#: Space around and between the panels, in figure units. The gutter is wider than
#: the margin on purpose: two columns that nearly touch read as one drawing.
PAD, GUTTER = 16.0, 34.0
HEAD_GAP, SUB_GAP = 24.0, 18.0

_ROOT_SVG = re.compile(r'<svg\b[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"[^>]*>')
_PHYSICAL = re.compile(r'\bwidth="([\d.]+)([a-z]*)"\s+height="([\d.]+)([a-z]*)"')


class Panel:
    """One rendered figure, with what it says about its own physical size."""

    def __init__(self, spec_path: Path):
        self.path = spec_path
        doc = json.loads(spec_path.read_text())
        graph = Graph(json.loads(
            (spec_path.parent / doc.get("graph", "graph.json")).read_text()))
        self.svg = render(load(doc), graph)

        m = _ROOT_SVG.search(self.svg)
        if not m:
            raise SystemExit(f"{spec_path}: rendered SVG has no viewBox to place")
        self.w, self.h = float(m.group(1)), float(m.group(2))
        self.head = m.group(0)
        self.body = self.svg[m.end():self.svg.rindex("</svg>")]

        # WHAT A UNIT IS WORTH, IN POINTS. None when the spec states no output
        # width, which is a pair this tool must refuse rather than guess at.
        p = _PHYSICAL.search(self.head)
        self.pt_per_unit = None
        if p and p.group(2):
            self.pt_per_unit = length_pt(p.group(1) + p.group(2),
                                         f"{spec_path}: output.width") / self.w


def _text(x: float, y: float, size: float, fill: str, body: str,
          weight: str = "") -> str:
    w = f"font-weight:{weight};" if weight else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" style="font-size:{size}px;{w}'
            f'fill:{fill}">{body}</text>')


def compose(panels: list[Panel], title: str, subtitle: list[str]) -> str:
    """The frame. Panels are placed, never scaled."""
    if len(panels) < 2:
        raise SystemExit("beside.py draws a comparison; give it two specs")

    # ONE SCALE, OR NOTHING. A pair that disagrees here would be two figures on
    # one page at two sizes, which is the thing this tool exists to prevent.
    scales = [p.pt_per_unit for p in panels]
    if any(s is None for s in scales):
        bare = ", ".join(str(p.path) for p in panels if p.pt_per_unit is None)
        raise SystemExit(
            f"{bare}: states no output.width, so what a figure unit is worth on "
            "the page is undefined and the two panels cannot be held to one "
            "scale. Set output.width and output.min_type on every panel.")
    if max(scales) - min(scales) > 1e-9:
        detail = ", ".join(f"{p.path.name} {p.pt_per_unit:.6f}pt/unit"
                           for p in panels)
        raise SystemExit(
            f"the panels disagree about what a figure unit is worth ({detail}). "
            "Drawn beside each other they would be two different scales wearing "
            "one frame. Give them the same output.width, or the same ratio of "
            "output.width to figure width.")

    top = PAD + TITLE_SIZE + HEAD_GAP + len(subtitle) * CAPTION_LINE + SUB_GAP
    width = PAD * 2 + sum(p.w for p in panels) + GUTTER * (len(panels) - 1)
    height = top + max(p.h for p in panels) + PAD

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="draughtsman" role="img" '
        f'aria-label="{title}" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width * scales[0] / 72.0:.4f}in" '
        f'height="{height * scales[0] / 72.0:.4f}in">',
        f"<title>{title}</title>",
        f"<desc>{' '.join(subtitle)}</desc>",
        f"<style>text{{font-family:{FONT_STACK}}}</style>",
        f'<rect x="0" y="0" width="{width:.2f}" height="{height:.2f}" '
        f'style="fill:#ffffff"/>',
        _text(PAD, PAD + TITLE_SIZE, TITLE_SIZE, INK, title, weight="600"),
    ]
    y = PAD + TITLE_SIZE + HEAD_GAP
    for line in subtitle:
        parts.append(_text(PAD, y, CAPTION_SIZE, MUTED, line))
        y += CAPTION_LINE

    x = PAD
    for p in panels:
        # NESTED, NOT SCALED: width and height are the panel's own viewBox
        # extent, so the embedded figure is placed at 1:1 and a mark in one
        # column is the size of a mark in the other.
        parts.append(f'<svg x="{x:.2f}" y="{top:.2f}" '
                     f'width="{p.w:.2f}" height="{p.h:.2f}" '
                     f'viewBox="0 0 {p.w:.2f} {p.h:.2f}">{p.body}</svg>')
        x += p.w + GUTTER
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


DEFAULT_TITLE = "Where the ROI axis collapses — tube and line, at one scale"
DEFAULT_SUBTITLE = [
    "Both panels are draughtsman figures of a traced model, placed at 1:1: one "
    "mark is one ROI in either column.",
    "tube takes its mean in the third box, before a kernel has run. line smears "
    "and votes per ROI first, so the column",
    "of marks survives to the fourth. After each mean there is no ROI axis in "
    "the tensor, and nothing is drawn for one.",
]


def selftest() -> int:
    """THE PROPERTY THIS TOOL IS FOR: placed, not scaled — and refused otherwise.

    A composition that silently resampled a panel would look almost right and be
    worthless, because the one thing the frame asserts is that the two columns
    are comparable. So this asks the output whether each nested panel's declared
    size is its own viewBox extent, and asks the composer to refuse a pair that
    does not agree about the scale.
    """
    tube = Panel(ROOT / "examples/tube/beside-line.json")
    line = Panel(ROOT / "examples/line/beside-tube.json")
    out = compose([tube, line], DEFAULT_TITLE, DEFAULT_SUBTITLE)

    nested = re.findall(r'<svg x="[\d.]+" y="[\d.]+" width="([\d.]+)" '
                        r'height="([\d.]+)" viewBox="0 0 ([\d.]+) ([\d.]+)"', out)
    if len(nested) != 2:
        print(f"selftest: expected 2 nested panels, found {len(nested)}")
        return 1
    for w, h, vw, vh in nested:
        if (w, h) != (vw, vh):
            print(f"selftest: a panel is scaled — {w}x{h} shown for a "
                  f"{vw}x{vh} viewBox. The frame's one claim is 1:1.")
            return 1

    # And the refusal. A panel at half the width per unit must not compose.
    half = Panel(ROOT / "examples/line/beside-tube.json")
    half.pt_per_unit = tube.pt_per_unit / 2.0
    try:
        compose([tube, half], DEFAULT_TITLE, DEFAULT_SUBTITLE)
    except SystemExit:
        pass
    else:
        print("selftest: two panels at different scales were composed anyway")
        return 1

    print(f"ok — 2 panels placed 1:1, {len(out)} bytes, "
          f"{tube.pt_per_unit:.6f}pt per figure unit in both")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("specs", nargs="*", type=Path,
                    help="two spec.json paths, left panel first")
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--title", default=DEFAULT_TITLE)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if len(args.specs) != 2:
        ap.error("give exactly two specs, left panel first")

    panels = [Panel(p) for p in args.specs]
    out = compose(panels, args.title, DEFAULT_SUBTITLE)
    if args.out:
        args.out.write_text(out)
        print(f"{args.out}: {' + '.join(f'{p.w:g}x{p.h:g}' for p in panels)} "
              f"at {panels[0].pt_per_unit:.6f}pt per unit")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
