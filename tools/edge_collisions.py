#!/usr/bin/env python3
"""Report edges that run through boxes they have nothing to do with.

    tools/edge_collisions.py examples/gallery/*/figure.svg
    tools/edge_collisions.py --floor 20 examples/gallery/dual/figure.svg
    tools/edge_collisions.py --selftest

Exit 1 when any collision is at or past `--floor` percent of the box it crosses,
so it works as a gate.

WHY THIS EXISTS
---------------
An arrow drawn through a stage is a figure making a claim the model does not.
A reader of `dual` sees the wide branch's output pass through the narrow branch
on its way to the concatenate, and there is no such path in the trace. That is
the confident-and-wrong figure this repository convicts other tools of, in its
own gallery.

It passed everything. Coverage was green -- every traced node in exactly one
stage. The legibility gate was green -- the type clears its floor at the declared
width. The byte-exact render test was green -- the committed SVG is what the spec
produces. `tests/test_edge_labels.py` checks that an edge's LABEL does not sit on
a box. Nothing had ever asked where the edge's own path goes.

Found on 2026-09-04 by Tony looking at a rendering of `dual` and saying there was
something in it he did not think the session could see. He was right, and the way
that session was working could not have found it: it was measuring type size,
unit width and print points, and none of those asks whether the drawing reads as
a drawing. This is that look, mechanised, so it does not depend on someone
happening to glance at the right figure.

WHAT COUNTS AS A COLLISION
--------------------------
A segment of an edge passing through the interior of a box that is neither its
source nor its target. Endpoint boxes are excluded on purpose: an edge must enter
its own source and target -- that is the arrowhead -- and flagging it would bury
the real finding under one false positive per edge.

Depth is reported as a percentage of the box's extent along the crossing axis,
because the difference matters: a run that crosses 100% of a box has gone in one
side and out the other, and a run that clips 4% has grazed a corner while
routing past it. Both are wrong; only the first is unreadable.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

NUM = r"-?\d+\.?\d*"
CURVE_SAMPLES = 24          # points per bezier; corners here are 9-unit radii
EPS = 0.01
PAD = 0.5                   # ignore a hairline graze of the border itself


# ----------------------------------------------------------------- parsing
def _stage_boxes(svg: str) -> list[tuple[str, float, float, float, float]]:
    """(id, x1, y1, x2, y2) per stage.

    THE RECT CARRIES NO CLASS -- the class and the id are on the enclosing group.
    A `<rect class=...>` filter finds nothing and reports every figure clean,
    which is how the first version of this check passed on a figure that was
    visibly wrong.
    """
    out = []
    for g in re.finditer(
            r'<g class="ds-stage[^"]*" data-stage="([^"]*)"[^>]*>(.*?)</g>',
            svg, re.S):
        sid, body = g.group(1), g.group(2)
        m = re.search(r"<rect\b([^>]*)>", body)
        if not m:
            continue                       # chrome:"none" draws sheets, not a box
        a = m.group(1)
        try:
            x = float(re.search(r'\bx="(%s)"' % NUM, a).group(1))
            y = float(re.search(r'\by="(%s)"' % NUM, a).group(1))
            w = float(re.search(r'\bwidth="(%s)"' % NUM, a).group(1))
            h = float(re.search(r'\bheight="(%s)"' % NUM, a).group(1))
        except AttributeError:
            continue
        out.append((sid, x, y, x + w, y + h))
    return out


def _flatten(d: str) -> list[tuple[float, float]]:
    """Path data to a polyline.

    M and L are exact. Q and C are SAMPLED rather than approximated by their
    control points: a control point is not on the curve, and for the cubic used
    on short branch connectors it can sit well off it. Treating controls as
    vertices was the first version and it reported segments the figure does not
    draw.
    """
    toks = re.findall(r"[MLQCZmlqcz]|%s" % NUM, d)
    pts: list[tuple[float, float]] = []
    i = 0
    cur = (0.0, 0.0)
    cmd = "M"
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t.upper()
            i += 1
            continue
        if cmd in ("M", "L"):
            x, y = float(toks[i]), float(toks[i + 1])
            i += 2
            pts.append((x, y))
            cur = (x, y)
        elif cmd == "Q":
            cx, cy, x, y = (float(toks[i]), float(toks[i + 1]),
                            float(toks[i + 2]), float(toks[i + 3]))
            i += 4
            for k in range(1, CURVE_SAMPLES + 1):
                s = k / CURVE_SAMPLES
                px = (1 - s) ** 2 * cur[0] + 2 * (1 - s) * s * cx + s * s * x
                py = (1 - s) ** 2 * cur[1] + 2 * (1 - s) * s * cy + s * s * y
                pts.append((px, py))
            cur = (x, y)
        elif cmd == "C":
            c1x, c1y, c2x, c2y, x, y = (float(toks[i + j]) for j in range(6))
            i += 6
            for k in range(1, CURVE_SAMPLES + 1):
                s = k / CURVE_SAMPLES
                m0 = (1 - s) ** 3
                m1 = 3 * (1 - s) ** 2 * s
                m2 = 3 * (1 - s) * s * s
                m3 = s ** 3
                pts.append((m0 * cur[0] + m1 * c1x + m2 * c2x + m3 * x,
                            m0 * cur[1] + m1 * c1y + m2 * c2y + m3 * y))
            cur = (x, y)
        else:
            i += 1
    return pts


def _edges(svg: str) -> list[tuple[str, str, list[tuple[float, float]]]]:
    out = []
    for m in re.finditer(r'<path class="ds-edge[^"]*"([^>]*)>', svg):
        a = m.group(1)
        d = re.search(r'\bd="([^"]+)"', a)
        if not d:
            continue
        frm = re.search(r'data-from="([^"]*)"', a)
        to = re.search(r'data-to="([^"]*)"', a)
        out.append((frm.group(1) if frm else "?",
                    to.group(1) if to else "?",
                    _flatten(d.group(1))))
    return out


# --------------------------------------------------------------- geometry
def _overlap(p, q, box) -> tuple[float, float] | None:
    """How far segment p->q reaches into the box, and the box's extent.

    Returns None when the segment stays outside. Handles the general case by
    clipping the segment to the rect (Liang-Barsky), so a diagonal sample from a
    flattened curve is measured rather than skipped.
    """
    _, rx1, ry1, rx2, ry2 = box
    rx1, ry1, rx2, ry2 = rx1 + PAD, ry1 + PAD, rx2 - PAD, ry2 - PAD
    if rx2 <= rx1 or ry2 <= ry1:
        return None
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    # Liang-Barsky, as (p, q) pairs. Getting these the wrong way round produces a
    # clipper that reports every crossing as a miss -- t0 lands past t1 and the
    # segment is discarded -- so the check comes back clean on a figure that is
    # visibly wrong. The selftest below is what caught it.
    for p_, q_ in ((-dx, x1 - rx1), (dx, rx2 - x1),
                   (-dy, y1 - ry1), (dy, ry2 - y1)):
        if abs(p_) < EPS:
            if q_ < 0:
                return None            # parallel to this edge and outside it
            continue
        t = q_ / p_
        if p_ < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    length = math.hypot(dx, dy) * (t1 - t0)
    if length <= EPS:
        return None
    # measure against the box along whichever axis the run is travelling
    span = (rx2 - rx1) if abs(dx) >= abs(dy) else (ry2 - ry1)
    return length, span


def collisions(svg: str):
    """[(from, to, box_id, depth, span, pct)], worst first."""
    boxes = _stage_boxes(svg)
    found: dict[tuple[str, str, str], tuple[float, float]] = {}
    for frm, to, pts in _edges(svg):
        for p, q in zip(pts, pts[1:]):
            for box in boxes:
                if box[0] in (frm, to):
                    continue               # its own endpoints: that is the arrowhead
                hit = _overlap(p, q, box)
                if not hit:
                    continue
                depth, span = hit
                key = (frm, to, box[0])
                prev = found.get(key)
                # segments of one crossing accumulate along the same run
                found[key] = ((prev[0] if prev else 0.0) + depth, span)
    out = []
    for (frm, to, bid), (depth, span) in found.items():
        depth = min(depth, span)
        out.append((frm, to, bid, depth, span, 100.0 * depth / span if span else 0.0))
    out.sort(key=lambda r: -r[5])
    return out


# ------------------------------------------------------------------ report
def report(paths, floor):
    worst = 0.0
    any_found = False
    for p in paths:
        svg = Path(p).read_text(encoding="utf-8")
        hits = collisions(svg)
        name = Path(p).parent.name or Path(p).stem
        if not hits:
            print(f"{name}: clean")
            continue
        any_found = True
        print(f"{name}:")
        for frm, to, bid, depth, span, pct in hits:
            worst = max(worst, pct)
            verdict = ("CROSSES IT" if pct >= 80 else
                       "clips it" if pct >= 20 else "cuts a corner")
            print(f"  {frm} -> {to}  runs through {bid!r}: "
                  f"{depth:.0f} of {span:.0f} units ({pct:.0f}%) {verdict}")
    if any_found and floor is not None and worst >= floor:
        print(f"\nFAIL: a collision reaches {worst:.0f}% against a floor of {floor:.0f}%")
        return 1
    return 0


# ---------------------------------------------------------------- selftest
_CLEAN = '''<svg viewBox="0 0 200 100">
<g class="ds-stage ds-kind-op" data-stage="a"><rect x="10" y="10" width="40" height="30"/></g>
<g class="ds-stage ds-kind-op" data-stage="b"><rect x="150" y="10" width="40" height="30"/></g>
<g class="ds-stage ds-kind-op" data-stage="c"><rect x="80" y="60" width="40" height="30"/></g>
<path class="ds-edge ds-edge-solid" data-from="a" data-to="b" d="M50 25 L150 25"/>
</svg>'''

_THROUGH = _CLEAN.replace('<rect x="80" y="60" width="40" height="30"/>',
                          '<rect x="80" y="10" width="40" height="30"/>')

_CURVE = '''<svg viewBox="0 0 200 100">
<g class="ds-stage ds-kind-op" data-stage="a"><rect x="10" y="10" width="20" height="20"/></g>
<g class="ds-stage ds-kind-op" data-stage="b"><rect x="170" y="10" width="20" height="20"/></g>
<g class="ds-stage ds-kind-op" data-stage="c"><rect x="90" y="70" width="20" height="20"/></g>
<path class="ds-edge" data-from="a" data-to="b" d="M30 20 C60 20 60 20 170 20"/>
</svg>'''


def selftest() -> int:
    fail = 0

    def t(label, ok):
        nonlocal fail
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            fail = 1

    t("a figure whose edge misses every third box is clean",
      collisions(_CLEAN) == [])

    hits = collisions(_THROUGH)
    t("an edge crossing a third box is found", len(hits) == 1)
    if hits:
        frm, to, bid, depth, span, pct = hits[0]
        t("it names the box it crosses, not the endpoints", bid == "c")
        t(f"and reports a full traversal ({pct:.0f}%)", pct > 95)

    # THE ENDPOINT EXCLUSION MUST NOT BE A BLANKET ONE. Removing it would report
    # every edge against its own source and target, which is one false positive
    # per edge and would bury a real finding.
    both = [h for h in collisions(_THROUGH) if h[2] in ("a", "b")]
    t("an edge is not reported against its own source or target", both == [])

    # THE RECT IS UNCLASSED AND THE ID IS ON THE GROUP. A `<rect class=...>`
    # filter finds no boxes and calls every figure clean -- which is exactly how
    # the first version of this check passed on a figure that was visibly wrong.
    t("boxes are found at all", len(_stage_boxes(_THROUGH)) == 3)

    # A CONTROL POINT IS NOT ON THE CURVE. Treating one as a vertex reports a
    # segment the figure does not draw; this cubic's controls sit at y=20 and
    # the curve never approaches the box at y=70.
    t("a curve is sampled, not read off its control points",
      collisions(_CURVE) == [])

    # AND THE SAMPLER MUST STILL CATCH A CURVE THAT GENUINELY DOES CROSS.
    #
    # The box moves to meet the curve rather than the reverse, and the first
    # version of this case did it the other way round and failed for the wrong
    # reason: a cubic from (30,20) to (170,20) with both controls at y=200 peaks
    # at y=155 and passes y=70..90 at x≈60 and x≈140, so it missed a box at
    # x[90,110] horizontally. The tool was right and the fixture was wrong, which
    # is the failure this whole file exists to make harder.
    #
    # At s=0.5 that curve is at exactly (100, 155), so a box spanning x[90,110]
    # y[140,170] is one the curve must enter.
    dipped = _CURVE.replace('<rect x="90" y="70" width="20" height="20"/>',
                            '<rect x="90" y="140" width="20" height="30"/>')
    dipped = dipped.replace('d="M30 20 C60 20 60 20 170 20"',
                            'd="M30 20 C60 200 140 200 170 20"')
    hit = collisions(dipped)
    t("a curve that does cross is still caught",
      len(hit) == 1 and hit[0][2] == "c")

    print("PASS" if not fail else "FAIL")
    return fail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("svg", nargs="*", type=Path)
    ap.add_argument("--floor", type=float, default=None,
                    help="exit 1 when a collision reaches this percent of a box")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.svg:
        ap.error("give at least one figure.svg, or --selftest")
    return report(a.svg, a.floor)


if __name__ == "__main__":
    sys.exit(main())
