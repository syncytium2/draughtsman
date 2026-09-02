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

import math

from draughtsman.facts import (TIMES, FactError, Graph, repeat_counts,
                               resolve)
from draughtsman.layout import build
from draughtsman.spec import Spec
from draughtsman.text import FONT_STACK, escape, width

TITLE_SIZE = 12.0
DETAIL_SIZE = 9.5
LANE_SIZE = 9.0
CAPTION_SIZE = 10.0
PAD_X, PAD_Y = 12.0, 9.0
TITLE_LINE, DETAIL_LINE, LANE_ROW = 15.0, 12.5, 15.0
# A meter is a bar, a label and nothing else. Deliberately shorter than a text
# line: it replaces digits a reader has to compare in their head, and it should
# not cost more room than the digits did.
METER_ROW, METER_SIZE, METER_BAR = 11.0, 8.0, 4.5
# ONE BAR LENGTH FOR THE WHOLE FIGURE, NOT ONE PER BOX. If the track stretched to
# fit its box, two stages with the same value would draw different lengths and
# the reader would be comparing box widths -- which is exactly the misreading the
# meter exists to remove. Boxes widen to fit the bar instead.
METER_BAR_W = 54.0
# The glyph's canvas. Constant for every stage in the figure, because the scale
# is shared: two stages with the same tensor must draw the same rectangle.
GLYPH_W, GLYPH_H, GLYPH_ROW, GLYPH_MIN = 46.0, 26.0, 32.0, 1.5
# MARKS: the tensor drawn as objects a reader can count, rather than a rectangle
# they can only compare. axes[0] is rows and axes[1] is columns, so a 3x5 tensor
# is three rows of five and a single countable axis is a column of that many.
#
# MARK_MAX IS THE HONEST LIMIT AND IT IS LOW ON PURPOSE. Counting stops working
# somewhere around thirty objects; past that the eye estimates, and marks it
# cannot count are a picture pretending to be a number. An axis over the limit is
# drawn as a solid bar with its count written beside it -- which is also what
# those marks would look like at the pitch they would need, so it is the same
# drawing continued rather than a different one.
MARK_MAX = 32
# PITCH IS SET BY COUNTABILITY, NOT BY FIT. At 3.2 the marks touched and thirty
# of them read as a dotted line -- a picture of "many", which is the thing the
# block already does better. They have to be separable to be countable, and if
# that makes a thirty-element box tall then the box is tall: the height IS the
# thirty, and shrinking it to fit would trade the only claim this style makes.
MARK_PITCH, MARK_SIZE, MARK_BAR_H, MARK_BAR_ROW = 5.0, 3.0, 5.0, 11.0
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


class _Marks:
    """The geometry of a countable glyph: what is drawn, and what is too big.

    Each axis is countable or it is not, and the two cases are drawn differently
    rather than blended: countable becomes that many marks, uncountable becomes a
    bar with the number. A stage may have one of each — `1x30x600` draws thirty
    marks down the page with `600` written under them, which is the shape a reader
    was going to have to hold in their head anyway.
    """

    def __init__(self, shape: tuple[float, float], labels: list[str]):
        self.rows, self.cols = int(shape[0]), int(shape[1])
        self.labels = list(labels) + ["", ""]
        self.rows_ok = 0 < self.rows <= MARK_MAX
        self.cols_ok = 0 < self.cols <= MARK_MAX

        grid_cols = self.cols if self.cols_ok else 1
        grid_rows = self.rows if self.rows_ok else 1
        self.grid_w = grid_cols * MARK_PITCH
        self.grid_h = grid_rows * MARK_PITCH

        # a bar per axis that could not be drawn, each on its own row underneath
        self.bars = [(i, self.rows if i == 0 else self.cols)
                     for i, ok in ((0, self.rows_ok), (1, self.cols_ok)) if not ok]
        bar_text = max((width(f"{n}", METER_SIZE) for _, n in self.bars),
                       default=0.0)
        self.w = max(self.grid_w, METER_BAR_W + 4 + bar_text if self.bars else 0)
        self.h = ((self.grid_h if self.rows_ok or self.cols_ok else 0)
                  + MARK_BAR_ROW * len(self.bars))


class _Stage:
    """One stage, measured."""

    def __init__(self, stage, graph: Graph, stages: dict[str, list[str]],
                 repeats: dict | None = None, batch_axis: int | None = None):
        self.spec = stage
        where = f"stage {stage.id!r}"
        self.repeat = (repeats or {}).get(stage.id) if stage.repeat else None
        # ONE AXIS NUMBERING PER SPEC. `lanes.count_from` and `meters` resolve to
        # scalars and are unaffected, but `glyph.axes` indexes POSITIONALLY into
        # a resolved shape, so the glyph must see the same shape the text does.
        # Otherwise a spec declaring batch_axis carries two numbering
        # conventions -- axis 1 is "cells" in the glyph and "frames" in the
        # label -- which is DECISIONS.md correction 5 exactly: one quantity, two
        # places, allowed to disagree.
        rkw = dict(stage_id=stage.id, repeats=repeats or {},
                   batch_axis=batch_axis)
        self.name = resolve(stage.name, graph, node_ids=stage.nodes,
                            stages=stages, where=where, **rkw)
        self.detail = [resolve(d, graph, node_ids=stage.nodes, stages=stages,
                               where=where, **rkw) for d in stage.detail]
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
        self.meters = [
            (m.label, _number(resolve(m.value, graph, node_ids=stage.nodes,
                                      stages=stages, where=where), where, m.label))
            for m in stage.meters
        ]
        widths += [width(lbl, METER_SIZE) + 5 + METER_BAR_W
                   for lbl, _ in self.meters]
        self.glyph: tuple[float, float] | None = None
        self.marks: _Marks | None = None
        if stage.glyph:
            shape = _shape_axes(
                resolve(stage.glyph.of, graph, node_ids=stage.nodes,
                        stages=stages, where=where, batch_axis=batch_axis),
                stage.glyph, where)
            self.glyph = shape
            if stage.glyph.style == "marks":
                self.marks = _Marks(shape, stage.glyph.labels)
                widths.append(self.marks.w)
            else:
                widths.append(GLYPH_W)
        self.w = max(MIN_W, max(widths) + 2 * PAD_X)
        self.h = (2 * PAD_Y + TITLE_LINE + DETAIL_LINE * len(self.detail)
                  + (LANE_ROW * len(self.lane_labels) + 5 if self.lane_labels else 0)
                  + (METER_ROW * len(self.meters) + 4 if self.meters else 0)
                  + (self.marks.h + 6 if self.marks
                     else GLYPH_ROW if self.glyph else 0))


def render(spec: Spec, graph: Graph) -> str:
    stages = {s.id: s.nodes for s in spec.stages}
    counts = repeat_counts(spec.stages, graph)
    measured = {s.id: _Stage(s, graph, stages, counts, spec.batch_axis)
                for s in spec.stages}

    if not measured:
        # A spec with no stages yet — `draughtsman ui` starts here when there is a
        # graph but nobody has grouped it. An empty figure is the honest picture.
        return _empty(spec, graph)

    drawing = build(
        [(sid, m.w, m.h) for sid, m in measured.items()],
        [(e.src, e.dst, e.label, e.style) for e in spec.edges],
        orientation=spec.layout.orientation, wrap=spec.layout.wrap,
    )

    ba = spec.batch_axis
    title = resolve(spec.title, graph, stages=stages, where="title", batch_axis=ba)
    subtitle = (resolve(spec.subtitle, graph, stages=stages, where="subtitle",
                        batch_axis=ba) if spec.subtitle else None)
    caption = (resolve(spec.caption, graph, stages=stages, where="caption",
                       batch_axis=ba) if spec.caption else None)

    head_h = 22.0 + (14.0 if subtitle else 0.0)
    foot_h = 18.0 if caption else 0.0

    scales = _meter_scales(measured)
    gscale = _glyph_scales(measured)
    rows = _legend(spec, graph) if spec.layout.legend else []
    # A BAR WITHOUT A STATED SCALE IS A NUMBER WITHOUT A UNIT. The legend
    # carries the axis: what a full bar equals, per series.
    rows += [("__meter__", label, f"full bar = {_fmt(full)}")
             for label, full in sorted(scales.items())]
    glyphed = [m for m in measured.values() if m.spec.glyph]
    if glyphed:
        lbl = glyphed[0].spec.glyph.labels
        if glyphed[0].spec.glyph.style == "marks":
            # A different claim, so a different key. The block says "compare
            # these areas"; marks say "count these". Stating the limit is part of
            # it — a bar means the count was past counting, and a reader not told
            # that will read the bar as an axis of one.
            note = (f"one mark = one {lbl[0].rstrip('s') or 'element'} · "
                    f"a bar means more than {MARK_MAX}, counted beside it")
        else:
            note = (f"tallest = {_fmt(gscale[0])}, widest = {_fmt(gscale[1])} · "
                    + ("each edge ∝ value"
                       if glyphed[0].spec.glyph.scale == "linear"
                       else "each edge ∝ √value"))
        rows.append(("__glyph__", f"{lbl[0]} × {lbl[1]}", note))
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

    # Every box is something an edge label must not land on, and so is every
    # label already placed. Routes are walked in the spec's edge order, so which
    # label gets the good spot is decided by the spec and not by chance.
    occupied = [(b.x, b.y - b.h / 2, b.x + b.w, b.y + b.h / 2)
                for b in drawing.boxes.values() if not b.dummy]
    for route in drawing.routes:
        out.append(_edge(route, drawing.vertical, occupied))

    for sid, m in measured.items():
        out.append(_box(drawing.boxes[sid], m, scales, gscale))

    out.append("</g>")

    if rows:
        top = head_h + drawing.height + 8.0
        out.append('<g class="ds-legend">')
        for i, (kind, label, share) in enumerate(rows):
            y = top + i * LEGEND_ROW
            if kind == "__glyph__":
                out.append(
                    f'<rect class="ds-legend-glyph" x="12" '
                    f'y="{_fmt(y + 1)}" width="{_fmt(LEGEND_SWATCH)}" '
                    f'height="{_fmt(LEGEND_SWATCH - 1)}" '
                    f'style="fill:currentColor;fill-opacity:0.42"/>'
                )
            elif kind == "__meter__":
                # A MINIATURE OF THE THING, NOT A COLOUR. A family swatch here
                # would say the meter is a family, and it is not -- it is an axis.
                out.append(
                    f'<rect class="ds-legend-meter" x="12" '
                    f'y="{_fmt(y + 2.2)}" width="{_fmt(LEGEND_SWATCH)}" '
                    f'height="{_fmt(METER_BAR)}" rx="1.5" '
                    f'style="fill:none;stroke:currentColor;stroke-opacity:0.55;'
                    f'stroke-width:0.7"/>'
                )
                out.append(
                    f'<rect class="ds-legend-meter-fill" x="12" '
                    f'y="{_fmt(y + 2.2)}" width="{_fmt(LEGEND_SWATCH * 0.6)}" '
                    f'height="{_fmt(METER_BAR)}" rx="1.5" '
                    f'style="fill:currentColor;fill-opacity:0.55"/>'
                )
            else:
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


EDGE_LABEL_SIZE = 9.0
LABEL_GAP = 4.0
# How far along the path to try, in order. The true middle first, then either
# side of it — a label pushed off-centre still reads as belonging to its edge,
# and a label on top of a box does not.
LABEL_STOPS = (0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74)


def _along(points, t: float) -> tuple[float, float]:
    """The point *t* of the way along a polyline BY LENGTH.

    Not `points[len(points) // 2]`, which was the bug this replaces: for a
    two-point edge that index is the destination's entry point, so every short
    labelled edge drew its label centred on the box it pointed at. Whisper is
    where it was noticed, because its label was long enough to be obvious, but
    every one of them was doing it.
    """
    spans = [_dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(spans)
    if total <= 0:
        return points[0]
    want = total * t
    for (ax, ay), (bx, by), span in zip(points, points[1:], spans):
        if want > span:
            want -= span
            continue
        f = want / span if span else 0.0
        return (ax + (bx - ax) * f, ay + (by - ay) * f)
    return points[-1]


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _label_rect(x: float, y: float, w: float) -> tuple[float, float, float, float]:
    """`y` is a text baseline; the ink sits above it."""
    return (x - w / 2, y - EDGE_LABEL_SIZE * 0.8, x + w / 2,
            y + EDGE_LABEL_SIZE * 0.25)


def _place_label(points, text: str, vertical: bool, occupied) -> tuple[float, float]:
    """A spot on the path where the label lands on nothing.

    Tries the middle first, then along the path, then further off it. Failing
    everything it returns the least bad spot rather than refusing to draw: a
    label that is hard to read still carries more than a label that is absent,
    and absent is what the workaround for this bug had to do to Whisper's figure.
    """
    w = width(text, EDGE_LABEL_SIZE)
    best, best_cost = None, None
    for t in LABEL_STOPS:
        cx, cy = _along(points, t)
        for step in (0, 1, 2):
            for sign in (-1, 1):
                off = (LABEL_GAP + step * (EDGE_LABEL_SIZE + 3)) * sign
                x, y = ((cx + off, cy + EDGE_LABEL_SIZE * 0.35) if vertical
                        else (cx, cy + off - LABEL_GAP))
                rect = _label_rect(x, y, w)
                cost = sum(1 for o in occupied if _overlaps(rect, o))
                if cost == 0:
                    occupied.append(rect)
                    return x, y
                if best_cost is None or cost < best_cost:
                    best, best_cost = (x, y), cost
    occupied.append(_label_rect(best[0], best[1], w))
    return best


def _edge(route, vertical: bool = False, occupied=None) -> str:
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
        lx, ly = _place_label(pts, route.label, vertical,
                              [] if occupied is None else occupied)
        parts.append(
            f'<text class="ds-edge-label" x="{_fmt(lx)}" '
            f'y="{_fmt(ly)}" text-anchor="middle" '
            f'style="font-family:{FONT_STACK};font-size:{EDGE_LABEL_SIZE}px;'
            f'fill:{PAGE_MUTED}">{escape(route.label)}</text>'
        )
    return "".join(parts)


def _box(box, m: _Stage, scales: dict[str, float],
         gscale: tuple[float, float]) -> str:
    fill, stroke = PALETTE.get(m.spec.kind, PALETTE["op"])
    top = box.y - box.h / 2.0
    # data-stage is how `draughtsman ui` binds a click in the figure back to the
    # stage in the spec, and it costs an embedding page nothing.
    parts = [f'<g class="ds-stage ds-kind-{escape(m.spec.kind)}" '
             f'data-stage="{escape(m.spec.id)}">']
    # A REPEATED STAGE IS DRAWN AS A STACK, AND THE STACK IS THE COUNT. Up to
    # three sheets behind the box, because past that they stop being countable and
    # become texture; the exact number is on the badge and in the name, which is a
    # {stage.repeat} reference rather than a word the agent chose.
    if m.repeat and m.repeat > 1:
        for i in range(min(m.repeat - 1, 3), 0, -1):
            off = 3.0 * i
            parts.append(
                f'<rect class="ds-repeat-sheet" x="{_fmt(box.x + off)}" '
                f'y="{_fmt(top - off)}" width="{_fmt(box.w)}" '
                f'height="{_fmt(box.h)}" rx="4" '
                f'style="fill:{fill};stroke:{stroke};stroke-width:1;'
                f'stroke-opacity:0.55"/>'
            )
    parts.append(
        f'<rect x="{_fmt(box.x)}" y="{_fmt(top)}" width="{_fmt(box.w)}" '
        f'height="{_fmt(box.h)}" rx="4" '
        f'style="fill:{fill};stroke:{stroke};stroke-width:1.2"/>'
    )
    if m.repeat and m.repeat > 1:
        parts.append(
            f'<text class="ds-repeat-badge" x="{_fmt(box.x + box.w - 5)}" '
            f'y="{_fmt(top + box.h - 5)}" text-anchor="end" '
            f'style="font-family:{FONT_STACK};font-size:9px;font-weight:600;'
            f'fill:{MUTED}">×{m.repeat}</text>'
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

    if m.marks:
        y = _draw_marks(parts, m.marks, box, y, stroke)

    elif m.glyph:
        tall, wide = m.glyph
        sc = m.spec.glyph.scale
        gh = _edge_px(tall, gscale[0], GLYPH_H, sc)
        gw = _edge_px(wide, gscale[1], GLYPH_W, sc)
        gx = box.x + (box.w - gw) / 2.0
        gy = y + 3 + (GLYPH_H - gh)          # sits ON a baseline, not centred
        parts.append(
            f'<rect class="ds-glyph" x="{_fmt(gx)}" y="{_fmt(gy)}" '
            f'width="{_fmt(gw)}" height="{_fmt(gh)}" '
            f'style="fill:{stroke};fill-opacity:0.5;stroke:{stroke};'
            f'stroke-width:0.6"/>'
        )
        y += GLYPH_ROW

    if m.meters:
        y += 4
        widest = max(width(lbl, METER_SIZE) for lbl, _ in m.meters)
        row_w = widest + 5 + METER_BAR_W
        bx = box.x + (box.w - row_w) / 2.0
        for label, value in m.meters:
            full = scales.get(label) or 1.0
            bar_x = bx + widest + 5
            bar_w = METER_BAR_W
            parts.append(
                f'<text x="{_fmt(bx)}" y="{_fmt(y + METER_BAR)}" '
                f'style="font-family:{FONT_STACK};font-size:{METER_SIZE}px;'
                f'fill:{MUTED}">{escape(label)}</text>'
            )
            # The track is the whole series, so an almost-empty bar reads as
            # "small share of the largest", not as a missing value.
            parts.append(
                f'<rect class="ds-meter-track" x="{_fmt(bar_x)}" '
                f'y="{_fmt(y)}" width="{_fmt(bar_w)}" '
                f'height="{_fmt(METER_BAR)}" rx="1.5" '
                f'style="fill:#ffffff;fill-opacity:0.62;stroke:{stroke};'
                f'stroke-width:0.5"/>'
            )
            filled = bar_w * (value / full) if full else 0.0
            if filled > 0:
                parts.append(
                    f'<rect class="ds-meter-fill" x="{_fmt(bar_x)}" '
                    f'y="{_fmt(y)}" width="{_fmt(max(1.0, filled))}" '
                    f'height="{_fmt(METER_BAR)}" rx="1.5" '
                    f'style="fill:{stroke}"/>'
                )
            y += METER_ROW
    parts.append("</g>")
    return "".join(parts)


def _number(text: str, where: str, label: str) -> float:
    """A meter's value must BE a number. A bar drawn from '1×4×600' would be
    drawing the string's length, which is not a fact about anything."""
    try:
        return float(text.replace(",", ""))
    except ValueError:
        raise FactError(
            f"{where}: meter {label!r} resolved to {text!r}, which is not a "
            "number. A meter draws a magnitude, so its reference must be one — "
            "{stage.params}, {stage.nodes} or one axis of a shape such as "
            "{stage.out_shape[1]}.") from None


def _meter_scales(measured) -> dict[str, float]:
    """One scale per series, over the whole figure.

    FULL BAR IS THE LARGEST VALUE IN THE SERIES AND EMPTY IS ZERO. No truncated
    baseline, no log: a stage holding most of the model's parameters SHOULD read
    as a bar that is nearly all of the width, because that is the fact. The
    legend states what full width means, so the bar is never a number without a
    scale.
    """
    scales: dict[str, float] = {}
    for m in measured.values():
        for label, value in m.meters:
            scales[label] = max(scales.get(label, 0.0), value)
    return scales


def _draw_marks(parts: list[str], mk: _Marks, box, y: float, stroke: str) -> float:
    """Draw the countable axes as marks and the rest as bars with their numbers.

    Marks are drawn at one mark per element, never scaled to fit: the whole claim
    is that they can be counted, and a grid squeezed to fit its box would be a
    picture of a number rather than the number. The box widened for this in
    `_Stage` instead.
    """
    top = y + 3
    if mk.rows_ok or mk.cols_ok:
        gx = box.x + (box.w - mk.grid_w) / 2.0
        rows = mk.rows if mk.rows_ok else 1
        cols = mk.cols if mk.cols_ok else 1
        pad = (MARK_PITCH - MARK_SIZE) / 2.0
        for r in range(rows):
            for c in range(cols):
                parts.append(
                    f'<rect class="ds-mark" '
                    f'x="{_fmt(gx + c * MARK_PITCH + pad)}" '
                    f'y="{_fmt(top + r * MARK_PITCH + pad)}" '
                    f'width="{_fmt(MARK_SIZE)}" height="{_fmt(MARK_SIZE)}" '
                    f'style="fill:{stroke};fill-opacity:0.75"/>'
                )
        top += mk.grid_h

    for axis, n in mk.bars:
        # Past counting. A solid bar and the number, which is what those marks
        # would have looked like at the pitch they would have needed.
        bx = box.x + (box.w - (METER_BAR_W + 4
                               + width(f"{n}", METER_SIZE))) / 2.0
        parts.append(
            f'<rect class="ds-mark-bar" x="{_fmt(bx)}" '
            f'y="{_fmt(top + (MARK_BAR_ROW - MARK_BAR_H) / 2)}" '
            f'width="{_fmt(METER_BAR_W)}" height="{_fmt(MARK_BAR_H)}" rx="1" '
            f'style="fill:{stroke};fill-opacity:0.75"/>'
        )
        parts.append(
            f'<text class="ds-mark-count" x="{_fmt(bx + METER_BAR_W + 4)}" '
            f'y="{_fmt(top + MARK_BAR_ROW - 3)}" '
            f'style="font-family:{FONT_STACK};font-size:{METER_SIZE}px;'
            f'fill:{MUTED}">{escape(str(n))}</text>'
        )
        top += MARK_BAR_ROW
    return y + mk.h + 6


def _shape_axes(text: str, glyph, where: str) -> tuple[float, float]:
    """Pull the two named axes out of one resolved shape."""
    parts = text.split(TIMES)
    try:
        dims = [float(p) for p in parts]
    except ValueError:
        raise FactError(
            f"{where}: glyph `of` resolved to {text!r}, which is not a shape. It "
            "must be one reference to a tensor shape, such as "
            "{stage.out_shape}.") from None
    if len(glyph.axes) != 2 or len(glyph.labels) != 2:
        raise FactError(f"{where}: a glyph needs exactly two axes and two labels")
    out = []
    for i in glyph.axes:
        if i >= len(dims):
            raise FactError(
                f"{where}: glyph asks for axis {i} of {text!r}, which has "
                f"{len(dims)} axes.")
        out.append(dims[i])
    return out[0], out[1]


def _glyph_scales(measured) -> tuple[float, float]:
    """Tallest and widest values anywhere in the figure. One scale, both axes."""
    tall = wide = 0.0
    for m in measured.values():
        if m.glyph:
            tall = max(tall, m.glyph[0])
            wide = max(wide, m.glyph[1])
    return tall, wide


def _edge_px(value: float, biggest: float, full: float,
             scale: str = "sqrt") -> float:
    """SQUARE ROOT, AND THE LEGEND SAYS SO.

    Channel counts in this gallery span 1568:1. Linear edges would put the
    smallest rectangle below one pixel while the largest filled the box, so the
    figure would be showing "big" and "absent" rather than a range. Rooting each
    edge compresses 1568:1 to 40:1 and preserves order exactly. The cost is that
    area becomes the root of the tensor rather than the tensor, which is why the
    legend states the scale and `detail` keeps the true numbers.
    """
    if biggest <= 0:
        return GLYPH_MIN
    frac = max(value, 0.0) / biggest
    return max(GLYPH_MIN, full * (frac if scale == "linear" else math.sqrt(frac)))
