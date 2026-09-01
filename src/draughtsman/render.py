"""Stage 3b — render. Deterministic, and it invents nothing.

Reads `spec.json` for shape and `graph.json` for every number, resolves the
spec's ``{references}`` against the graph, lays the result out with
:mod:`draughtsman.layout`, and emits SVG.

TWO RULES ABOUT STYLING, BOTH LEARNED THE HARD WAY (SPEC.md §4).

1. No ``<style>`` block, no font import, no script. The figure is meant to be
   dropped into a page.
2. What it *does* set, it sets as an inline ``style=`` and never as a
   presentation attribute. ``fill="#eee"`` is a presentation attribute and loses
   to any host rule; a single ``.arch rect { fill: … }`` in the embedding page
   repainted every glyph one flat colour the first time this was tried.
   ``style="fill:#eee"`` outranks the host's rule, which is the point.

Class names are still emitted (``ds-stage``, ``ds-kind-conv``) so a page that
*wants* to restyle can, with a specificity it has to mean.
"""

from __future__ import annotations

from draughtsman.facts import Graph, resolve
from draughtsman.layout import build
from draughtsman.spec import Spec
from draughtsman.text import FONT_STACK, escape, width

TITLE_SIZE = 12.0
DETAIL_SIZE = 9.5
LANE_SIZE = 9.0
CAPTION_SIZE = 10.0
PAD_X, PAD_Y = 12.0, 9.0
TITLE_LINE, DETAIL_LINE, LANE_ROW = 15.0, 12.5, 15.0
MIN_W = 76.0

# TWO KINDS OF INK, AND THE DIFFERENCE IS WHAT THEY SIT ON.
#
# Anything drawn on a box sits on a fill this file chose, so it is pinned: a
# stated colour on a stated ground. Anything drawn on the PAGE — the title, the
# caption, every edge and arrowhead — sits on a ground the embedding page owns,
# and pinning it there is only half of §4's "inherit from the embedding page".
# Pinned dark ink is invisible on a dark page, which is what a README rendered in
# GitHub's dark theme is.
#
# So page-ground ink is `currentColor`, still written as an inline style so a
# host rule cannot repaint it. Standalone — a file opened directly, or the PNG
# export — `currentColor` resolves to black, which is the old behaviour.
INK = "#1a1a1a"            # on a box fill
MUTED = "#5b5b5b"          # on a box fill, secondary
PAGE_INK = "currentColor"  # on whatever the embedding page provides
PAGE_MUTED = "currentColor;opacity:0.62"
LINE = "currentColor"

# HUE IS THE FAMILY, VALUE IS THE KIND.
#
# Tony asked for an Inception-style figure for a stated reason -- *"how much of
# the model is convolution, at a glance"* -- and the first cut of this palette
# could not answer it: the difference-of-Gaussian bank was gold and the dilated
# stack was green, so the two convolutional stages of a model that is 99% convolution
# by parameter read as unrelated. They are now both green and differ in value, which
# also keeps them apart in a greyscale print (SPEC.md §4's constraint, unchanged).
#
# NOTE WHAT THIS IS NOT. The Inception figure colours LAYERS, and counting its
# boxes counts them. draughtsman collapses 26 traced ops into one stage, so a box
# here is not a layer and no colouring of boxes can be read as a proportion. That
# is what the legend is for: the swatch names the family and the number beside it
# is counted off graph.json, so "how much is convolution" is answered by a fact
# rather than by eyeballing box area.
FAMILIES = {
    "input":   ("flow", "Input / output"),
    "output":  ("flow", "Input / output"),
    "pool":    ("pool", "Pool / reduce"),
    "reduce":  ("pool", "Pool / reduce"),
    "kernel":  ("conv", "Convolution"),
    "conv":    ("conv", "Convolution"),
    "stack":   ("conv", "Convolution"),
    "concat":  ("join", "Concat / join"),
    "op":      ("other", "Other"),
}

# Light fills, mid strokes: this has to survive a greyscale print, so the kinds
# are separated by value as much as by hue.
PALETTE = {
    "input":   ("#f2f2f0", "#8a8a86"),
    "output":  ("#f2f2f0", "#8a8a86"),
    "pool":    ("#e4eef5", "#6f93a8"),
    "reduce":  ("#d5e5ef", "#5b829a"),
    "kernel":  ("#eef6f1", "#7fae99"),
    "conv":    ("#e2eee7", "#6f9c85"),
    "stack":   ("#d1e4d9", "#5a8a71"),
    "concat":  ("#ece6f2", "#8d7ba8"),
    "op":      ("#f0f0ef", "#8a8a86"),
}

LEGEND_SIZE = 9.0
LEGEND_ROW = 15.0
LEGEND_SWATCH = 9.0


def _legend(spec: Spec, graph: Graph) -> list[tuple[str, str, str]]:
    """One row per FAMILY PRESENT: (kind to draw the swatch with, label, share).

    Generated from the stages that were drawn, never from a hand-kept list, so a
    kind cannot appear in the figure without appearing in the key. bugarach's own
    generator states that rule about its `KINDS` dict; it is the right rule and it
    is borrowed deliberately.

    The share is counted off graph.json — traced ops and attributed parameters —
    because that is the question the legend exists to answer and this tool does
    not let a figure carry a number nobody traced.
    """
    traced = set(graph.traced)
    seen: dict[str, dict] = {}
    for st in spec.stages:
        family, label = FAMILIES.get(st.kind, FAMILIES["op"])
        rec = seen.setdefault(family, {"kind": st.kind, "label": label,
                                       "ops": 0, "params": 0})
        for nid in st.nodes:
            if nid not in traced:
                continue      # a model input is addressable but is not an op
            rec["ops"] += 1
            rec["params"] += graph.nodes[nid].get("params", 0) or 0

    rows = []
    for family in ("conv", "pool", "join", "flow", "other"):
        rec = seen.get(family)
        if not rec:
            continue
        share = f"{rec['ops']} op" + ("s" if rec["ops"] != 1 else "")
        if rec["params"]:
            share += f", {rec['params']} params"
        rows.append((rec["kind"], rec["label"], share))
    return rows


def _fmt(v: float) -> str:
    return f"{round(v, 2):g}"


class _Stage:
    """One stage, measured."""

    def __init__(self, stage, graph: Graph, stages: dict[str, list[str]]):
        self.spec = stage
        where = f"stage {stage.id!r}"
        self.name = resolve(stage.name, graph, node_ids=stage.nodes,
                            stages=stages, where=where)
        self.detail = [resolve(d, graph, node_ids=stage.nodes, stages=stages,
                               where=where) for d in stage.detail]
        self.lane_labels: list[str] = []
        if stage.lanes:
            count = int(resolve(stage.lanes.count_from, graph,
                                node_ids=stage.nodes, stages=stages, where=where))
            labels = stage.lanes.labels
            # `check` proves these agree; if a spec is rendered unchecked, the
            # FACT wins and the labels are padded, never the other way round.
            self.lane_labels = [labels[i] if i < len(labels) else f"{i + 1}"
                                for i in range(count)]

        widths = [width(self.name, TITLE_SIZE, bold=True)]
        widths += [width(d, DETAIL_SIZE) for d in self.detail]
        widths += [width(l, LANE_SIZE) + 30 for l in self.lane_labels]
        self.w = max(MIN_W, max(widths) + 2 * PAD_X)
        self.h = (2 * PAD_Y + TITLE_LINE + DETAIL_LINE * len(self.detail)
                  + (LANE_ROW * len(self.lane_labels) + 5 if self.lane_labels else 0))


def render(spec: Spec, graph: Graph) -> str:
    stages = {s.id: s.nodes for s in spec.stages}
    measured = {s.id: _Stage(s, graph, stages) for s in spec.stages}

    if not measured:
        # A spec with no stages yet — `draughtsman ui` starts here when there is a
        # graph but nobody has grouped it. An empty figure is the honest picture.
        return _empty(spec, graph)

    drawing = build(
        [(sid, m.w, m.h) for sid, m in measured.items()],
        [(e.src, e.dst, e.label, e.style) for e in spec.edges],
        orientation=spec.layout.orientation, wrap=spec.layout.wrap,
    )

    title = resolve(spec.title, graph, stages=stages, where="title")
    subtitle = (resolve(spec.subtitle, graph, stages=stages, where="subtitle")
                if spec.subtitle else None)
    caption = (resolve(spec.caption, graph, stages=stages, where="caption")
               if spec.caption else None)

    head_h = 22.0 + (14.0 if subtitle else 0.0)
    foot_h = 18.0 if caption else 0.0

    rows = _legend(spec, graph) if spec.layout.legend else []
    legend_w = max((LEGEND_SWATCH + 6 + width(lbl, LEGEND_SIZE, bold=True)
                    + 6 + width(sh, LEGEND_SIZE) + 18
                    for _, lbl, sh in rows), default=0.0)
    legend_h = LEGEND_ROW * len(rows) + (8.0 if rows else 0.0)

    total_w = max(drawing.width, width(title, 14, bold=True) + 24,
                  width(subtitle or "", 10) + 24, width(caption or "", CAPTION_SIZE) + 24,
                  legend_w + 24)
    total_h = drawing.height + head_h + foot_h + legend_h

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" class="draughtsman" '
        f'role="img" aria-label="{escape(title)}" '
        f'viewBox="0 0 {_fmt(total_w)} {_fmt(total_h)}" '
        f'width="{_fmt(total_w)}" height="{_fmt(total_h)}">'
    )
    out.append(f"<title>{escape(title)}</title>")
    out.append(f"<desc>{escape(_describe(spec, graph))}</desc>")
    out.append(
        '<defs><marker id="ds-arrow" viewBox="0 0 8 8" refX="7" refY="4" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0.6 L8 4 L0 7.4 Z" style="fill:{LINE}"/></marker></defs>'
    )

    out.append(
        f'<text class="ds-title" x="12" y="15" '
        f'style="font-family:{FONT_STACK};font-size:14px;font-weight:600;'
        f'fill:{PAGE_INK}">{escape(title)}</text>'
    )
    if subtitle:
        out.append(
            f'<text class="ds-subtitle" x="12" y="29" '
            f'style="font-family:{FONT_STACK};font-size:10px;'
            f'fill:{PAGE_MUTED}">{escape(subtitle)}</text>'
        )

    # A vertical figure is often narrower than its own caption, which would leave
    # the column stranded against the left edge of a canvas sized by prose.
    shift = max(0.0, (total_w - drawing.width) / 2.0)
    out.append(f'<g class="ds-body" '
               f'transform="translate({_fmt(shift)} {_fmt(head_h)})">')

    for route in drawing.routes:
        out.append(_edge(route, drawing.vertical))

    for sid, m in measured.items():
        out.append(_box(drawing.boxes[sid], m))

    out.append("</g>")

    if rows:
        top = head_h + drawing.height + 8.0
        out.append('<g class="ds-legend">')
        for i, (kind, label, share) in enumerate(rows):
            y = top + i * LEGEND_ROW
            fill, stroke = PALETTE.get(kind, PALETTE["op"])
            out.append(
                f'<rect class="ds-legend-swatch ds-kind-{escape(kind)}" x="12" '
                f'y="{_fmt(y)}" width="{_fmt(LEGEND_SWATCH)}" '
                f'height="{_fmt(LEGEND_SWATCH)}" rx="2" '
                f'style="fill:{fill};stroke:{stroke};stroke-width:1"/>'
            )
            tx = 12 + LEGEND_SWATCH + 6
            out.append(
                f'<text class="ds-legend-label" x="{_fmt(tx)}" '
                f'y="{_fmt(y + LEGEND_SWATCH - 0.5)}" '
                f'style="font-family:{FONT_STACK};font-size:{LEGEND_SIZE}px;'
                f'font-weight:600;fill:{PAGE_INK}">{escape(label)}</text>'
            )
            sx = tx + width(label, LEGEND_SIZE, bold=True) + 6
            out.append(
                f'<text class="ds-legend-share" x="{_fmt(sx)}" '
                f'y="{_fmt(y + LEGEND_SWATCH - 0.5)}" '
                f'style="font-family:{FONT_STACK};font-size:{LEGEND_SIZE}px;'
                f'fill:{PAGE_MUTED}">{escape(share)}</text>'
            )
        out.append("</g>")

    if caption:
        out.append(
            f'<text class="ds-caption" x="12" y="{_fmt(total_h - 6)}" '
            f'style="font-family:{FONT_STACK};font-size:{CAPTION_SIZE}px;'
            f'fill:{PAGE_MUTED}">{escape(caption)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _empty(spec: Spec, graph: Graph) -> str:
    note = f"{len(graph.traced)} traced operations, no stages yet"
    w = max(240.0, width(spec.title, 14, bold=True) + 24)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="draughtsman" role="img" '
        f'aria-label="{escape(spec.title)}" viewBox="0 0 {_fmt(w)} 46" '
        f'width="{_fmt(w)}" height="46">\n'
        f"<title>{escape(spec.title)}</title>\n"
        f'<text x="12" y="18" style="font-family:{FONT_STACK};font-size:14px;'
        f'font-weight:600;fill:{PAGE_INK}">{escape(spec.title)}</text>\n'
        f'<text x="12" y="34" style="font-family:{FONT_STACK};font-size:10px;'
        f'fill:{PAGE_MUTED}">{escape(note)}</text>\n</svg>\n'
    )


def _describe(spec: Spec, graph: Graph) -> str:
    n = len(graph.traced)
    return (f"{spec.title}: {len(spec.stages)} stages over {n} traced operations, "
            f"{graph.model['params']} parameters.")


def _ortho(pts, radius: float = 9.0) -> list[str]:
    """An axis-aligned path with rounded corners, for a wrap connector.

    A bezier here would bow through the gutter and read as another branch. The
    return is not a branch; it is the same line, continued on the next row, and
    it should look like a pipe rather than an edge."""
    d = [f"M{_fmt(pts[0][0])} {_fmt(pts[0][1])}"]
    for i in range(1, len(pts) - 1):
        (px, py), (cx, cy), (nx, ny) = pts[i - 1], pts[i], pts[i + 1]
        r1 = min(radius, _dist((px, py), (cx, cy)) / 2)
        r2 = min(radius, _dist((cx, cy), (nx, ny)) / 2)
        a = _towards((cx, cy), (px, py), r1)
        b = _towards((cx, cy), (nx, ny), r2)
        d.append(f"L{_fmt(a[0])} {_fmt(a[1])}")
        d.append(f"Q{_fmt(cx)} {_fmt(cy)} {_fmt(b[0])} {_fmt(b[1])}")
    d.append(f"L{_fmt(pts[-1][0])} {_fmt(pts[-1][1])}")
    return d


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _towards(frm, to, by):
    length = _dist(frm, to) or 1.0
    return (frm[0] + (to[0] - frm[0]) * by / length,
            frm[1] + (to[1] - frm[1]) * by / length)


def _edge(route, vertical: bool = False) -> str:
    pts = route.points
    if route.wrapped:
        d = _ortho(pts)
    else:
        d = [f"M{_fmt(pts[0][0])} {_fmt(pts[0][1])}"]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            # handles run along the direction of flow, which the orientation sets
            if vertical:
                cy = (y1 - y0) * 0.5
                d.append(f"C{_fmt(x0)} {_fmt(y0 + cy)} {_fmt(x1)} {_fmt(y1 - cy)} "
                         f"{_fmt(x1)} {_fmt(y1)}")
            else:
                cx = (x1 - x0) * 0.5
                d.append(f"C{_fmt(x0 + cx)} {_fmt(y0)} {_fmt(x1 - cx)} {_fmt(y1)} "
                         f"{_fmt(x1)} {_fmt(y1)}")
    dash = ";stroke-dasharray:5 3" if route.style == "dashed" else ""
    parts = [
        f'<path class="ds-edge ds-edge-{route.style}" '
        f'data-from="{escape(route.src)}" data-to="{escape(route.dst)}" '
        f'd="{" ".join(d)}" '
        f'style="fill:none;stroke:{LINE};stroke-width:1.4{dash}" '
        f'marker-end="url(#ds-arrow)"/>'
    ]
    if route.label:
        mid = pts[len(pts) // 2]
        parts.append(
            f'<text class="ds-edge-label" x="{_fmt(mid[0])}" '
            f'y="{_fmt(mid[1] - 5)}" text-anchor="middle" '
            f'style="font-family:{FONT_STACK};font-size:9px;'
            f'fill:{PAGE_MUTED}">{escape(route.label)}</text>'
        )
    return "".join(parts)


def _box(box, m: _Stage) -> str:
    fill, stroke = PALETTE.get(m.spec.kind, PALETTE["op"])
    top = box.y - box.h / 2.0
    # data-stage is how `draughtsman ui` binds a click in the figure back to the
    # stage in the spec, and it costs an embedding page nothing.
    parts = [f'<g class="ds-stage ds-kind-{escape(m.spec.kind)}" '
             f'data-stage="{escape(m.spec.id)}">']
    parts.append(
        f'<rect x="{_fmt(box.x)}" y="{_fmt(top)}" width="{_fmt(box.w)}" '
        f'height="{_fmt(box.h)}" rx="4" '
        f'style="fill:{fill};stroke:{stroke};stroke-width:1.2"/>'
    )
    cx = box.x + box.w / 2.0
    y = top + PAD_Y + TITLE_SIZE
    parts.append(
        f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
        f'style="font-family:{FONT_STACK};font-size:{TITLE_SIZE}px;'
        f'font-weight:600;fill:{INK}">{escape(m.name)}</text>'
    )
    y += TITLE_LINE - TITLE_SIZE
    for line in m.detail:
        y += DETAIL_SIZE
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;'
            f'fill:{MUTED}">{escape(line)}</text>'
        )
        y += DETAIL_LINE - DETAIL_SIZE

    if m.lane_labels:
        y += 5
        lx = box.x + 7
        lw = box.w - 14
        for label in m.lane_labels:
            parts.append(
                f'<rect class="ds-lane" x="{_fmt(lx)}" y="{_fmt(y)}" '
                f'width="{_fmt(lw)}" height="{_fmt(LANE_ROW - 3)}" rx="2" '
                f'style="fill:#ffffff;fill-opacity:0.62;stroke:{stroke};'
                f'stroke-width:0.7"/>'
            )
            parts.append(
                f'<text x="{_fmt(box.x + box.w / 2)}" '
                f'y="{_fmt(y + LANE_ROW - 6.5)}" text-anchor="middle" '
                f'style="font-family:{FONT_STACK};font-size:{LANE_SIZE}px;'
                f'fill:{INK}">{escape(label)}</text>'
            )
            y += LANE_ROW
    parts.append("</g>")
    return "".join(parts)
