#!/usr/bin/env python3
"""One frame, one vertical axis: torchview's graph and the stages that replace it.

    tools/compare_stack.py -o examples/gallery/whisper/compare.svg

WHY THIS EXISTS. The page already shows both views of Whisper tiny side by side,
each in its own window, and a reader has to take on trust that the eleven stages
on one side ARE the seventy-four boxes on the other. This draws the claim: every
stage sits level with the nodes it covers, on torchview's own vertical axis, at
torchview's own scale. A stage that swallows twenty-four boxes is twenty-four
boxes tall.

WHAT IS MEASURED AND WHAT IS DECLARED. The geometry is measured: node positions
come from graphviz's own layout of torchview's graph, and every label in the
right-hand column is lifted verbatim out of the committed `figure.svg` by its
`data-stage` handle -- so no quantity is typed here, and a figure that changes
changes this too.

The assignment of node to stage is DECLARED, in `ASSIGNMENT` below, and it is the
same kind of object as a spec: judgement, written down, and checked. `check()`
refuses an assignment that misses a node, names one twice, or claims a node the
graph does not have -- the coverage rule this repository applies to its own
figures, applied to its comparison of one.

RUNNING IT needs torch, torchview and graphviz, which the package does not depend
on; the output is committed instead. See examples/gallery/README.md.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGURE = ROOT / "examples/gallery/whisper/figure.svg"

# torchview node ids, by the stage of `whisper/spec.json` that covers them. Read
# off the labels and shapes: the encoder spine carries (1, 1500, 384), the decoder
# spine (1, 12, 384), and the three nodes taking both are the cross-attentions of
# decoder blocks two, three and four.
ASSIGNMENT: dict[str, list[int]] = {
    "mel":      [0],
    "frontend": [2, 3, 4, 5, 6, 7],
    "enc":      list(range(8, 32)),
    "audio":    [32],
    "tokens":   [1],
    "embed":    [33, 34],
    "dself":    [35, 36, 37],
    "dcross":   [38, 39, 40],
    "dff":      [41, 42, 43],
    "drest":    list(range(44, 71)),
    "logits":   [71, 72, 73],
}
# The order the right-hand column is read in, which is the order of the spec.
ORDER = ["mel", "frontend", "enc", "audio", "tokens", "embed",
         "dself", "dcross", "dff", "drest", "logits"]


def torchview_graph():
    """The same call examples/gallery/README.md documents, at 1x."""
    import torch
    import torchview
    sys.path.insert(0, str(ROOT / "examples/gallery"))
    from whisper_tiny import build_whisper_tiny
    g = torchview.draw_graph(
        build_whisper_tiny().eval(),
        input_data=[torch.randn(1, 80, 3000), torch.randint(0, 51865, (1, 12))],
        graph_name="whisper_tiny", device="cpu")
    return g.visual_graph


def geometry(vg):
    """Node boxes in points, from graphviz's own layout. y grows upward there."""
    doc = json.loads(vg.pipe(format="json"))
    nodes = {}
    for o in doc["objects"]:
        x, y = (float(v) for v in o["pos"].split(","))
        w, h = float(o["width"]) * 72.0, float(o["height"]) * 72.0
        nodes[int(o["_gvid"])] = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    bb = [float(v) for v in doc["bb"].split(",")]            # x0 y0 x1 y1
    return nodes, bb


def check(nodes: dict[int, tuple[float, float]]) -> None:
    """Coverage, for the comparison itself. Same rule, same reason."""
    claimed = [n for ids in ASSIGNMENT.values() for n in ids]
    dupes = {n for n in claimed if claimed.count(n) > 1}
    missing = set(nodes) - set(claimed)
    unknown = set(claimed) - set(nodes)
    if dupes or missing or unknown:
        raise SystemExit(
            "the assignment does not cover torchview's graph:\n"
            f"  claimed twice: {sorted(dupes)}\n"
            f"  never claimed: {sorted(missing)}\n"
            f"  not in the graph: {sorted(unknown)}\n"
            "Every node belongs to exactly one stage or the figure is a claim "
            "about a grouping that was never made.")
    if set(ASSIGNMENT) != set(ORDER):
        raise SystemExit("ASSIGNMENT and ORDER name different stages")


def regions(svg: str) -> dict[str, tuple[float, float, float, float]]:
    """The regions a committed figure says it drew."""
    out = {}
    for m in re.finditer(
            r'<rect class="ds-region" data-stage="(\w+)" x="([-\d.]+)" '
            r'y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg):
        sid, x, y, w, h = m.group(1), *(float(v) for v in m.groups()[1:])
        out[sid] = (x, y, x + w, y + h)
    return out


def overlapping(boxes: dict[str, tuple[float, float, float, float]]):
    """Every pair of regions that share area, with how much.

    WHY A TOOL AND NOT AN EYE. Two regions overlapped by 5.0 x 65.7 units in the
    committed figure and nobody saw it here -- it was found on a phone, zoomed
    in, by the person the figure is for. At page width the encoder's tint runs
    five units into the first decoder block and reads as a rounded corner.

    A region is a claim that THESE nodes are that stage. Two regions over one
    node claim it twice, which is the coverage rule this repository runs on
    arriving in the picture instead of the spec.
    """
    names = list(boxes)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ax0, ay0, ax1, ay1 = boxes[a]
            bx0, by0, bx1, by1 = boxes[b]
            w = min(ax1, bx1) - max(ax0, bx0)
            h = min(ay1, by1) - max(ay0, by0)
            if w > 0 and h > 0:
                out.append((a, b, w, h))
    return out


def pad_without_touching(boxes, pad: float, floor: float = 0.5):
    """Breathing room, but never more than the gap that is there.

    A fixed pad is what caused this: the encoder's nodes and the first decoder
    block's are about one unit apart, and three units on each side closed that
    and then some. So the pad is capped per axis at half the smallest gap to any
    other region -- full pad where there is room, none where there is not.
    """
    out = {}
    for name, (x0, y0, x1, y1) in boxes.items():
        gaps = []
        for other, (ox0, oy0, ox1, oy1) in boxes.items():
            if other == name:
                continue
            if min(y1, oy1) - max(y0, oy0) > 0:          # they share a band
                if ox0 >= x1:
                    gaps.append(ox0 - x1)
                elif ox1 <= x0:
                    gaps.append(x0 - ox1)
        room = min(gaps, default=pad * 2) / 2 - floor
        px = max(0.0, min(pad, room))
        out[name] = (x0 - px, y0 - pad, x1 + px, y1 + pad)
    return out


def stage_text(svg: str) -> dict[str, tuple[str, list[str], str]]:
    """Every label in the right-hand column, lifted out of the committed figure."""
    out = {}
    for m in re.finditer(r'<g class="ds-stage ds-kind-(\w+)" data-stage="(\w+)">(.*?)</g>',
                         svg, re.S):
        kind, stage, body = m.groups()
        lines = [html.unescape(re.sub(r"<[^>]+>", "", t))
                 for t in re.findall(r"<text[^>]*>(.*?)</text>", body, re.S)]
        fill = re.search(r"fill:var\(--ds-fill-\w+,(#\w+)\)", body)
        stroke = re.search(r"stroke:var\(--ds-stroke-\w+,(#\w+)\)", body)
        out[stage] = (kind, lines,
                      (fill.group(1) if fill else "#eee",
                       stroke.group(1) if stroke else "#999"))
    return out


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def wrapped(x: float, y: float, text: str, width: float, size: float,
            fill: str = "#5b5b5b", weight: str = "") -> tuple[list[str], float]:
    """<text> does not wrap, and the first draft ran two lines off the frame."""
    per = size * 0.52                                  # mean glyph width, measured
    limit = max(int(width / per), 20)
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if len(trial) > limit and line:
            lines.append(line); line = word
        else:
            line = trial
    lines.append(line)
    w = f"font-weight:{weight};" if weight else ""
    out = []
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x:.2f}" y="{y + i * (size + 3.5):.2f}" '
                   f'style="font-size:{size}px;{w}fill:{fill}">{esc(ln)}</text>')
    return out, y + (len(lines) - 1) * (size + 3.5)


def build(nodes, bb, frame, labels, height=1560.0) -> str:
    """The regions go BEHIND the nodes they cover, not beside them.

    Whisper runs two spines and graphviz draws them side by side, so the encoder
    and the decoder occupy the SAME levels. A single column of bands down one
    edge therefore stacks stages that are not on top of each other at all -- the
    first attempt did exactly that, and put `token ids` inside the audio
    encoder's band. A region drawn around the nodes themselves cannot make that
    mistake: it is the nodes' own bounding box.
    """
    x0, y0, x1, y1 = bb
    s, tx, ty, inner_w, inner_h = frame          # graphviz's own scale and flip
    k = height / inner_h                         # its svg units -> figure units
    col_w = inner_w * k

    LEFT, TOP, GAP, PAD = 12.0, 96.0, 34.0, 3.0
    label_x = LEFT + col_w + GAP
    width = label_x + 300.0

    # A NODE'S PLACE IS GRAPHVIZ'S TO STATE, AND IT STATES IT TWICE: once in the
    # json layout, in points with y running up, and again in the svg, scaled by
    # the `size` attribute torchview sets and flipped. Reading the first and
    # drawing over the second put every region 1/0.7 too large -- visible only
    # because the tints ran off the ends of the graph they were meant to be on.
    def X(pt):
        return LEFT + k * s * (pt + tx)

    def Y(pt):
        return TOP + k * s * (ty - pt)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="draughtsman" role="img" '
        f'aria-label="Whisper tiny: torchview\'s graph with the eleven draughtsman '
        f'stages drawn as regions over the nodes each one covers" '
        f'viewBox="0 0 {width:.2f} {TOP + height + 74:.2f}" '
        f'width="{width:.2f}" height="{TOP + height + 74:.2f}">',
        '<title>Whisper tiny — the same model, both views, one vertical axis</title>',
        '<desc>torchview 0.2.7\'s graph of Whisper tiny, 74 boxes on two parallel '
        'spines, with the 11 stages of draughtsman\'s committed spec drawn as tinted '
        'regions around the nodes each one collapses, named down the right-hand side.</desc>',
        "<style>text{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif}</style>",
        f'<rect x="0" y="0" width="{width:.2f}" height="{TOP + height + 74:.2f}" '
        f'style="fill:#ffffff"/>',
        f'<text x="{LEFT}" y="26" style="font-size:15px;font-weight:600;fill:#1a1a1a">'
        'Whisper tiny — 74 traced boxes, 11 stages, one vertical axis</text>',
    ]
    sub, _ = wrapped(LEFT, 47, "torchview 0.2.7's own layout, scaled to fit. Each tint "
                     "is one stage of the committed spec, drawn around the nodes it "
                     "covers and named on the right.", width - 2 * LEFT, 10.5)
    parts += sub

    # regions first, so the graph draws over them
    boxes, order_by_y = {}, []
    for stage in ORDER:
        xs = [nodes[n] for n in ASSIGNMENT[stage]]
        boxes[stage] = (X(min(b[0] for b in xs)), Y(max(b[3] for b in xs)),
                        X(max(b[2] for b in xs)), Y(min(b[1] for b in xs)))
    boxes = pad_without_touching(boxes, PAD)
    overlaps = overlapping(boxes)
    if overlaps:
        raise SystemExit(
            "regions overlap and the figure would be a claim about a grouping "
            "that is not the one drawn:\n" + "\n".join(
                f"  {a} x {b}: {w:.1f} x {h:.1f} units" for a, b, w, h in overlaps))

    for stage in ORDER:
        bx0, by0, bx1, by1 = boxes[stage]
        order_by_y.append(((by0 + by1) / 2, stage))
        kind, lines, (fill, stroke) = labels[stage]
        parts.append(
            f'<rect class="ds-region" data-stage="{stage}" x="{bx0:.2f}" '
            f'y="{by0:.2f}" width="{bx1 - bx0:.2f}" height="{by1 - by0:.2f}" '
            f'rx="3" style="fill:{fill};fill-opacity:.55;stroke:{stroke};'
            f'stroke-width:1"/>')

    parts.append(f'<g transform="translate({LEFT} {TOP}) scale({k})">__TORCHVIEW__</g>')

    # labels down the right, in the order the levels put them, which is not the
    # order of the spec: the encoder's last stage sits level with the decoder's
    # third, because that is when it runs.
    LH, total = 12.0, sum(len(v) for v in ASSIGNMENT.values())
    order_by_y.sort()
    slots = [[s, (boxes[s][1] + boxes[s][3]) / 2, labels[s][1],
              len(ASSIGNMENT[s]), labels[s][2][1]] for _, s in order_by_y]
    heights = [LH * (len(s[2]) + 1) for s in slots]
    for i in range(1, len(slots)):
        floor_ = slots[i - 1][1] + heights[i - 1] / 2 + 7 + heights[i] / 2
        if slots[i][1] < floor_:
            slots[i][1] = floor_

    for (stage, cy, lines, n, stroke), h in zip(slots, heights):
        bx0, by0, bx1, by1 = boxes[stage]
        parts.append(
            f'<path d="M{bx1:.2f} {(by0 + by1) / 2:.2f} L{label_x - 6:.2f} {cy:.2f}" '
            f'style="fill:none;stroke:{stroke};stroke-width:.9;opacity:.75"/>')
        y = cy - h / 2 + LH
        parts.append(f'<text x="{label_x:.2f}" y="{y:.2f}" style="font-size:12px;'
                     f'font-weight:600;fill:#1a1a1a">{esc(lines[0])}</text>')
        for line in lines[1:]:
            y += LH
            parts.append(f'<text x="{label_x:.2f}" y="{y:.2f}" '
                         f'style="font-size:9.5px;fill:#5b5b5b">{esc(line)}</text>')
        y += LH
        parts.append(f'<text x="{label_x:.2f}" y="{y:.2f}" style="font-size:9.5px;'
                     f'fill:{stroke}">{n} of {total} boxes</text>')

    cap = (f"The encoder and the decoder run at the same levels, so their regions "
           f"share heights without sharing place. torchview's layout is "
           f"{int(x1 - x0)} × {int(y1 - y0)} points, drawn here at {k * s:.2f}×.")
    parts += wrapped(LEFT, TOP + height + 40, cap, width - 2 * LEFT, 9.5)[0]
    parts.append("</svg>")
    return "\n".join(parts)


def selftest() -> int:
    """WHAT CAN BE CHECKED WITHOUT torchview, WHICH IS WHERE CI STANDS.

    The figure is generated by hand and committed, so the thing that rots is not
    the drawing: it is the declaration. If a stage is renamed, split or dropped in
    `whisper/spec.json`, `ASSIGNMENT` still names the old one and the committed
    figure still shows it -- correct-looking, and about a grouping that no longer
    exists. That is this repository's own subject, so it is checked here.
    """
    fails = []
    labels = stage_text(FIGURE.read_text())
    if set(labels) != set(ORDER):
        fails.append(f"figure.svg draws {sorted(labels)}; this tool names {sorted(ORDER)}")
    for stage in set(labels) & set(ORDER):
        if not labels[stage][1]:
            fails.append(f"stage {stage} has no label text to lift")

    # the committed figure must still be about the stages the spec draws
    out = Path(ROOT / "examples/gallery/whisper/compare.svg")
    if out.exists():
        drawn = out.read_text()
        for stage in set(labels) & set(ORDER):
            name = html.escape(labels[stage][1][0], quote=False)
            if name not in drawn:
                fails.append(f"compare.svg does not name {stage} ({name!r}); "
                             f"regenerate it")
    else:
        fails.append("compare.svg is not committed")

    # THE GEOMETRY, READ BACK OUT OF THE COMMITTED FILE. CI has no torchview, so
    # it cannot redraw this figure -- but the figure states where it put every
    # region, and two regions sharing area is checkable from that alone. It is
    # `data-box` again: a checker that cannot see a thing must not be able to
    # report it fine.
    if out.exists():
        drawn = regions(out.read_text())
        if len(drawn) != len(ORDER):
            fails.append(f"compare.svg draws {len(drawn)} regions, not {len(ORDER)}")
        for a, b, w, h in overlapping(drawn):
            fails.append(f"regions {a} and {b} overlap by {w:.1f} x {h:.1f} units")

    # coverage, against a stand-in graph of the size the real one has
    fake = {n: (0.0, 0.0, 1.0, 1.0) for n in range(74)}
    try:
        check(fake)
    except SystemExit as e:
        fails.append(f"the assignment does not cover a 74-node graph: {e}")
    for broken, why in ((dict(list(fake.items())[:-1]), "a node that is not there"),
                        ({**fake, 99: (0.0, 0.0, 1.0, 1.0)}, "a node nobody claimed")):
        try:
            check(broken)
        except SystemExit:
            pass
        else:
            fails.append(f"check() passed {why}")

    for f in fails:
        print("FAIL " + f)
    print("ok" if not fails else f"{len(fails)} failed")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default="examples/gallery/whisper/compare.svg")
    ap.add_argument("--height", type=float, default=1560.0,
                    help="figure units for torchview's full height")
    ap.add_argument("--selftest", action="store_true",
                    help="check the declaration against the committed figures")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    vg = torchview_graph()
    nodes, bb = geometry(vg)
    check(nodes)
    labels = stage_text(FIGURE.read_text())
    missing = set(ORDER) - set(labels)
    if missing:
        raise SystemExit(f"figure.svg has no stage {sorted(missing)} to take labels from")

    svg = vg.pipe(format="svg").decode()
    m = re.search(r'<svg width="([\d.]+)pt" height="([\d.]+)pt"', svg)
    g = re.search(r'transform="scale\(([\d.]+) [\d.]+\) rotate\(0\) '
                  r'translate\(([-\d.]+) ([-\d.]+)\)"', svg)
    if not (m and g):
        raise SystemExit("graphviz's svg is not shaped the way this reads it")
    frame = (float(g.group(1)), float(g.group(2)), float(g.group(3)),
             float(m.group(1)), float(m.group(2)))
    inner = svg[svg.index("<g id="):svg.rindex("</svg>")]         # drop their <svg>
    # its first polygon is an opaque white canvas, which would bury the regions
    inner = re.sub(r'<polygon fill="white"[^/]*?/>', "", inner, count=1)
    out = build(nodes, bb, frame, labels, args.height).replace("__TORCHVIEW__", inner)
    Path(args.out).write_text(out)
    print(f"{args.out}: {len(nodes)} torchview nodes, {len(ORDER)} stages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
