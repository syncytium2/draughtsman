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
from draughtsman.spec import Spec, length_pt
from draughtsman.text import FONT_STACK, escape, width

# TWO TYPE SIZES IN A FIGURE, AND THE SMALLEST ONE IS KNOWN.
#
# There were eight: 14, 12, 10, 9.5, 9, 9, 9, 8 and 7. Nobody chose eight — each
# arrived with a feature that wanted to be a little smaller than the last, and
# the result reads as noise rather than as hierarchy. Hierarchy here comes from
# WEIGHT, POSITION and COLOUR, all of which survive a 3x reduction onto a journal
# column. A size difference of half a point does not.
#
# THE SECOND REASON IS THE ONE THAT MATTERS. `width_budget` computes the page
# budget from "the smallest type in the figure", and it used DETAIL_SIZE — which
# was NOT the smallest, because a meter label was 8 and a count badge 7. So the
# legibility floor added the same day was measured against the wrong number and a
# figure could pass while carrying type under the floor it had just promised.
# With two sizes the smallest is HEAD or BODY and there is nothing else to be
# wrong about.
TITLE_SIZE = 12.0        # HEAD: the figure's title and every stage name
DETAIL_SIZE = 9.5        # BODY: everything else, and provably the smallest
LANE_SIZE = DETAIL_SIZE
CAPTION_SIZE = DETAIL_SIZE
CAPTION_LINE = 13.0
# A caption never sets the figure's width, but a figure narrower than this would
# wrap prose into a column, so it is the floor the caption may widen the page to.
CAPTION_MIN_W = 460.0
PAD_X, PAD_Y = 12.0, 9.0
TITLE_LINE, DETAIL_LINE, LANE_ROW = 15.0, 12.5, 15.0
# A meter is a bar, a label and nothing else. Deliberately shorter than a text
# line: it replaces digits a reader has to compare in their head, and it should
# not cost more room than the digits did.
METER_ROW, METER_SIZE, METER_BAR = 12.5, DETAIL_SIZE, 4.5
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
# SHEETS: n x m x p drawn as n flat sheets of m x p, offset. The third edge is
# DEPTH, and the reader integrates face area x depth as a volume -- which is why
# this is the one style allowed a third axis. See Glyph.style in spec.py.
#
# THE CANVAS IS SIZED AGAINST THE WIDTH BUDGET, NOT AGAINST THE BOX. face +
# depth = 44 + 22 = 66, which is under MIN_W and under every box in this gallery
# whose width is already set by its title, so adopting sheets widens nothing.
# That is deliberate: no figure here is legible at a journal column width, the
# ceiling is 399 units and the narrowest figure is 750, so a style that widened
# every box would spend the one quantity the tool cannot afford. Depth is paid
# for in HEIGHT, which a column crop does not charge for — a figure is scaled to
# fit the column's WIDTH, so a taller glyph is free and a wider one is not.
# ONE SPAN, NOT ONE PER AXIS — the largest axis VALUE anywhere in the figure is
# drawn this long, and every other value is drawn in proportion to it.
#
# The first version gave each axis its own canvas and its own maximum: height
# normalised against 28, width against 44, depth against 22. So a 64x64 spatial
# map — the same number on two axes — was drawn 44 wide and 28 tall, and every
# square tensor in the gallery came out at 1.45:1. The aspect a reader saw was an
# artifact of the canvas rather than a fact about the tensor.
#
# With one span, equal values draw equal lengths: square maps are square, and
# 128x8x8 is the long rod it actually is. It also costs less room than the
# per-axis version did, because the axes no longer each claim their own budget.
SHEET_SPAN = 30.0
BARE_SPAN = 52.0
SHEET_SKEW_PAD = 6.0     # breathing room under the tallest glyph in a figure
# FLAT OBLIQUE, NOT ISOMETRIC. Skewing the faces into parallelograms is what the
# textbook figures do; it destroys area comparability -- the thing the glyph
# exists for -- and adds no information, because the depth is already carried by
# how far the stack travels. Offset rectangles read as depth honestly.
SHEET_SKEW = 0.5          # rise per unit run of the offset
# THE HONEST CEILING IS A PITCH, NOT A COUNT, AND STATING BOTH WAS A BUG.
#
# The first version of this carried SHEET_MAX = 12 beside a minimum pitch, on the
# reasoning that a stack can fail by having too many sheets OR too little depth.
# Both are real failures and they are not two rules: a count ceiling is just the
# pitch rule evaluated at the largest depth the canvas allows. Drawing 128 sheets
# at the minimum separable pitch needs 508 units of depth — against a 399-unit
# budget for an ENTIRE figure at a journal column — so the count never binds
# first. Measured: every n the cap refused, the pitch had already refused, in
# both canvases. SHEET_MAX decided nothing and was unreachable code.
#
# That is DECISIONS.md correction 5 in a rule written to enforce correction 5:
# one quantity, stated twice, allowed to disagree. So the pitch is the rule and
# the ceiling is DERIVED from it. `sheet_ceiling` reports what that works out to
# for a given canvas — 11 unboxed, 6 boxed — and the legend states it rather
# than a constant somebody typed.
#
# Kept low deliberately. Counting marks stops working near thirty; counting
# SHEETS stops sooner because each one occludes the last. Past the ceiling the
# stack is one slab of the SAME DEPTH with its count printed beside it, so a
# stack too deep to count is still drawn the right size and the shape survives.
SHEET_MIN_PITCH = 4.0
# WHEN THERE IS NO BOX, THE GLYPH IS THE STAGE, so it is drawn at this size
# instead. A box sets its own width from the longest label and the glyph then
# sits in whatever is left; with the box gone the drawing is the subject and the
# labels arrange around it. Same scale rules, same cap, just a bigger canvas —
# and still narrower than the titles it sits under, so the figure does not widen.

# How far above the stack's top edge the name sits. Small, so the name still
# reads as belonging to that drawing rather than floating over the figure.
TITLE_GAP = 4.0
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


# A FILL IS A STATED COLOUR ON A GROUND THIS FILE DOES NOT OWN.
#
# The ink above already splits on exactly this: pinned where it sits on a box
# fill, `currentColor` where it sits on the page. The fills themselves were left
# pinned, which is right for a figure on a white page and wrong for a MARK on a
# card -- tonydefazio.com could not use an icon because these pale fills glow on
# a dark plate, and flattening them host-side would have discarded the stage-kind
# distinction they encode.
#
# So each fill is emitted as `var(--ds-fill-<kind>, <hex>)`. The hex is the
# fallback, so a standalone file, a PNG export and every committed figure render
# exactly as before; a host that wants a dark ground restates the nine variables
# and nothing else. This is a deliberate reversal of "inline so a host rule
# cannot repaint it" -- for fills only, and only through a name the host must
# opt into. An unset variable cannot repaint anything by accident.
#
# WHAT THIS DOES NOT DO. It does not compute a dark palette. "Hue is the family,
# value is the kind" is a constraint on the VALUES, and a host that restates them
# owns keeping the convolutional kinds apart in a greyscale print. The variables
# make that possible; they do not make it automatic.
#
# AND IT ONLY WORKS IN A BROWSER. librsvg does not implement custom properties:
# `rsvg-convert` takes the fallback even when the variable is set on the root
# element, measured. That is the right default -- every PNG in this repo renders
# as it always did -- but it means a dark PNG cannot be produced by restating
# these and rasterising. Verified in WebKit, where it does work.
def paint(kind: str) -> tuple[str, str]:
    """(fill, stroke) for *kind*, each host-restatable with the hex as fallback."""
    key = kind if kind in PALETTE else "op"
    fill, stroke = PALETTE[key]
    return f"var(--ds-fill-{key},{fill})", f"var(--ds-stroke-{key},{stroke})"

LEGEND_SIZE = DETAIL_SIZE
LEGEND_ROW = 15.0
#: Continuation lines of a wrapped legend share, tighter than the row pitch --
#: the pitch separates entries, this separates lines of one entry.
LEGEND_LINE = 11.0
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


def _wrap(text: str, limit: float, size: float) -> list[str]:
    """Break *text* into lines that fit *limit*, on spaces.

    Greedy, because a caption is three lines at most and Knuth-Plass would be
    solving a problem nobody has. A single word longer than the limit is left
    long rather than broken: hyphenating a node id or a shape would make a false
    token out of a true one.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and width(trial, size) > limit:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


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
                 repeats: dict | None = None, batch_axis: int | None = None,
                 chrome: str = "box"):
        self.spec = stage
        self.chrome = chrome
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
        self.glyph: tuple[float, ...] | None = None
        self.marks: _Marks | None = None
        self.glyph_row = GLYPH_ROW
        self.sheets = False
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
                # A sheet stack is face + depth = GLYPH_W by construction, so
                # both styles cost a box exactly the same width. Only the row
                # height differs, and height is the cheap axis.
                if stage.glyph.style == "sheets":
                    self.sheets = True      # sized by fit_glyph, second pass
                else:
                    widths.append(GLYPH_W)
        # PADDING EXISTED TO KEEP TEXT OFF A BORDER. With no border there is no
        # border to clear, and the gutter between stages already separates them —
        # so an unboxed figure buys back most of what the bigger glyph spends.
        pad = 4.0 if chrome == "none" else PAD_X
        self.pad = pad
        self.text_w = max(widths)
        self.w = max(MIN_W, self.text_w + 2 * pad)
        self.rows_h = (2 * PAD_Y + TITLE_LINE + DETAIL_LINE * len(self.detail)
                       + (LANE_ROW * len(self.lane_labels) + 5
                          if self.lane_labels else 0)
                       + (METER_ROW * len(self.meters) + 4 if self.meters else 0))
        self.h = (self.rows_h
                  + (self.marks.h + 6 if self.marks
                     else self.glyph_row if self.glyph else 0))

    def fit_glyph(self, gw: float, gh: float) -> None:
        """Second pass: the real footprint, once the figure-wide span is known.

        A sheet stack cannot be measured when its stage is, because its size
        depends on the largest axis value ANYWHERE in the figure — which is not
        known until every stage has been measured. So the box reserves nothing
        for it, and this sets the width and row height afterwards.
        """
        self.glyph_row = gh + SHEET_SKEW_PAD
        self.w = max(MIN_W, max(self.text_w, gw) + 2 * self.pad)
        self.h = self.rows_h + self.glyph_row


def render(spec: Spec, graph: Graph) -> str:
    stages = {s.id: s.nodes for s in spec.stages}
    counts = repeat_counts(spec.stages, graph)
    measured = {s.id: _Stage(s, graph, stages, counts, spec.batch_axis,
                             s.chrome or spec.layout.chrome)
                for s in spec.stages}

    if not measured:
        # A spec with no stages yet — `draughtsman ui` starts here when there is a
        # graph but nobody has grouped it. An empty figure is the honest picture.
        return _empty(spec, graph)

    # SIZE THE SHEET STACKS BEFORE LAYING ANYTHING OUT. Their footprint depends
    # on the largest axis value anywhere in the figure, so it cannot be known
    # while the stages are being measured one at a time — and `build` consumes
    # the box sizes, so the second pass has to finish first.
    gscale = _glyph_scales(measured)
    if gscale and any(m.sheets for m in measured.values()):
        for _m in measured.values():
            if _m.sheets:
                # PER STAGE, because the padding a stack is fitted to depends on
                # whether THAT stage draws a box, not on whether the figure does.
                *_, _gw, _gh = _sheet_geom(_m, gscale, _m.chrome == "none")
                _m.fit_glyph(_gw, _gh)

    nodes_in = [(sid, m.w, m.h) for sid, m in measured.items()]
    edges_in = [(e.src, e.dst, e.label, e.style) for e in spec.edges]
    drawing = build(nodes_in, edges_in, orientation=spec.layout.orientation,
                    wrap=spec.layout.wrap)

    # SOLVE FOR THE PAGE, AND WRAP IS THE ONLY LEVER PULLED.
    #
    # With an output width stated, the figure has a unit budget (see
    # width_budget) and depth converts directly into width, so the fix for a
    # figure that is too wide is to break the spine into more rows. That is
    # `layout.wrap`, which already exists and already refuses to cut a row where
    # a long edge is in flight — so a model webbed with skips will decline to
    # wrap and the check downstream will say so rather than this loop pretending.
    #
    # THE TYPE IS NEVER TOUCHED. A figure that fits by shrinking its labels has
    # solved a different problem, and the whole point of the budget is that the
    # label size is the fixed quantity. An explicit `layout.wrap` in the spec is
    # a judgement already made and is left alone.
    budget = width_budget(spec)
    if budget and spec.layout.wrap is None and drawing.width > budget:
        for target in (budget, budget * 0.86, budget * 0.72, budget * 0.6):
            trial = build(nodes_in, edges_in,
                          orientation=spec.layout.orientation, wrap=target)
            if trial.width <= drawing.width:
                drawing = trial
            if drawing.width <= budget:
                break

    ba = spec.batch_axis
    title = resolve(spec.title, graph, stages=stages, where="title", batch_axis=ba)
    subtitle = (resolve(spec.subtitle, graph, stages=stages, where="subtitle",
                        batch_axis=ba) if spec.subtitle else None)
    caption = (resolve(spec.caption, graph, stages=stages, where="caption",
                       batch_axis=ba) if spec.caption else None)

    head_h = 22.0 + (14.0 if subtitle else 0.0)

    scales = _meter_scales(measured)
    rows = _legend(spec, graph) if spec.layout.legend else []
    # A BAR WITHOUT A STATED SCALE IS A NUMBER WITHOUT A UNIT. The legend
    # carries the axis: what a full bar equals, per series.
    rows += [("__meter__", label, f"full bar = {_fmt(full)}")
             for label, full in sorted(scales.items())]
    glyphed = [m for m in measured.values() if m.spec.glyph]
    # THE KEY STATES A CEILING THE GLYPH STAGES WERE ACTUALLY FITTED TO, so it
    # is read off those stages rather than off the figure. They agree in every
    # well-formed figure: a glyph inside a box is the thing the page decision
    # forbids, and `check` warns when one turns up.
    bare_glyphs = bool(glyphed) and all(m.chrome == "none" for m in glyphed)
    if glyphed:
        lbl = glyphed[0].spec.glyph.labels
        if glyphed[0].spec.glyph.style == "marks":
            # A different claim, so a different key. The block says "compare
            # these areas"; marks say "count these". Stating the limit is part of
            # it — a bar means the count was past counting, and a reader not told
            # that will read the bar as an axis of one.
            note = (f"one mark = one {lbl[0].rstrip('s') or 'element'} · "
                    f"a bar means more than {MARK_MAX}, counted beside it")
        elif glyphed[0].spec.glyph.style == "sheets":
            # THE COMPRESSION IS NAMED, AND SO IS THE CAP. A stack drawn under a
            # root scale is a nonlinear mapping, and an unstated nonlinear scale
            # is the confident-and-wrong figure this tool exists to prevent. The
            # slab threshold is part of that: a reader shown a slab must know it
            # is a stack that stopped being countable, not an axis of one.
            note = (f"deepest = {_fmt(gscale[0])}, tallest = {_fmt(gscale[1])}, "
                    f"widest = {_fmt(gscale[2])} · "
                    + ("each edge scales with value"
                       if glyphed[0].spec.glyph.scale == "linear"
                       else "each edge scales with the square root of value")
                    + " · sheets are drawn only where they separate; past "
                    + str(sheet_ceiling(BARE_SPAN if bare_glyphs
                                        else SHEET_SPAN))
                    + " the stack is one slab carrying its count")
        else:
            note = (f"tallest = {_fmt(gscale[0])}, widest = {_fmt(gscale[1])} · "
                    + ("each edge scales with value"
                       if glyphed[0].spec.glyph.scale == "linear"
                       else "each edge scales with the square root of value"))
        rows.append(("__glyph__", " × ".join(lbl), note))
    # THE SWATCH AND THE LABEL ARE A NAME; THE SHARE IS PROSE. Only the name is a
    # width the figure owes the legend, so only the name is in the max below. The
    # share used to be too, and that is what made `lenet` 822 units wide while its
    # drawing reached 719: the glyph note `deepest = 16, tallest = 28, widest = 28
    # · each edge ∝ √value` ran to 792 and the figure grew to hold it on one line.
    # `layout.wrap` could not touch it -- every value from 760 down to 280 left the
    # width at 822.19 and only made the figure taller, because the wrap solver
    # arranges boxes and this was a sentence.
    #
    # This is the rule the comment below already states, applied to the other piece
    # of prose in the file. Prose wraps to the drawing; the drawing does not stretch
    # to the prose.
    legend_w = max((LEGEND_SWATCH + 6 + width(lbl, LEGEND_SIZE, bold=True) + 18
                    for _, lbl, _ in rows), default=0.0)

    # THE CAPTION IS NOT IN THIS MAX, AND THAT IS THE POINT. Sized to fit its own
    # prose, a 416-character caption made U-Net 1831px wide -- the figure's width
    # set by a sentence rather than by the drawing -- and then clipped anyway,
    # because fitting exactly leaves 12px of margin for a text metric to be wrong
    # in. It was wrong by under one percent and the last word was cut. Prose wraps
    # to the drawing; the drawing does not stretch to the prose.
    total_w = max(drawing.width, width(title, TITLE_SIZE, bold=True) + 24,
                  width(subtitle or "", 10) + 24, legend_w + 24,
                  CAPTION_MIN_W if caption else 0.0)
    caption_lines = _wrap(caption, total_w - 24, CAPTION_SIZE) if caption else []
    foot_h = CAPTION_LINE * len(caption_lines) + 8.0 if caption_lines else 0.0

    # The shares wrap to the width the drawing settled, each into whatever the row
    # has left after its own swatch and label. A row keeps LEGEND_ROW for its first
    # line and grows by LEGEND_LINE for each one after, so a legend that wraps costs
    # height -- which the figure can afford -- instead of width, which it cannot.
    legend_lines: list[list[str]] = []
    for _, lbl, sh in rows:
        sx = 12 + LEGEND_SWATCH + 6 + width(lbl, LEGEND_SIZE, bold=True) + 6
        legend_lines.append(_wrap(sh, max(total_w - sx - 12, 1.0), LEGEND_SIZE)
                            if sh else [])
    legend_h = (sum(LEGEND_ROW + LEGEND_LINE * (max(1, len(ln)) - 1)
                    for ln in legend_lines) + 8.0) if rows else 0.0
    total_h = drawing.height + head_h + foot_h + legend_h

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" class="draughtsman" '
        f'role="img" aria-label="{escape(title)}" '
        f'viewBox="0 0 {_fmt(total_w)} {_fmt(total_h)}" '
        + _physical(spec, total_w, total_h) + ">"
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
        f'style="font-family:{FONT_STACK};font-size:{TITLE_SIZE}px;font-weight:600;'
        f'fill:{PAGE_INK}">{escape(title)}</text>'
    )
    if subtitle:
        out.append(
            f'<text class="ds-subtitle" x="12" y="29" '
            f'style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;'
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
        # CUMULATIVE, NOT `i * LEGEND_ROW`. A row is as tall as the number of lines
        # its share wrapped to, so a fixed pitch would draw later entries on top of
        # an earlier one's second line.
        y = top
        for i, (kind, label, share) in enumerate(rows):
            if i:
                y += LEGEND_ROW + LEGEND_LINE * (max(1, len(legend_lines[i - 1])) - 1)
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
                fill, stroke = paint(kind)
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
            # CONTINUATION LINES RETURN TO THE LABEL COLUMN, not to the share's own
            # indent: a second line hanging under the middle of a sentence reads as
            # a separate entry, which is the one thing a legend must never look like.
            for k, line in enumerate(legend_lines[i]):
                out.append(
                    f'<text class="ds-legend-share" x="{_fmt(sx if not k else tx)}" '
                    f'y="{_fmt(y + LEGEND_SWATCH - 0.5 + k * LEGEND_LINE)}" '
                    f'style="font-family:{FONT_STACK};font-size:{LEGEND_SIZE}px;'
                    f'fill:{PAGE_MUTED}">{escape(line)}</text>'
                )
        out.append("</g>")

    if caption_lines:
        base = total_h - foot_h + CAPTION_SIZE
        for k, line in enumerate(caption_lines):
            out.append(
                f'<text class="ds-caption" x="12" '
                f'y="{_fmt(base + k * CAPTION_LINE)}" '
                f'style="font-family:{FONT_STACK};font-size:{CAPTION_SIZE}px;'
                f'fill:{PAGE_MUTED}">{escape(line)}</text>'
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _empty(spec: Spec, graph: Graph) -> str:
    note = f"{len(graph.traced)} traced operations, no stages yet"
    w = max(240.0, width(spec.title, TITLE_SIZE, bold=True) + 24)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="draughtsman" role="img" '
        f'aria-label="{escape(spec.title)}" viewBox="0 0 {_fmt(w)} 46" '
        f'width="{_fmt(w)}" height="46">\n'
        f"<title>{escape(spec.title)}</title>\n"
        f'<text x="12" y="18" style="font-family:{FONT_STACK};font-size:{TITLE_SIZE}px;'
        f'font-weight:600;fill:{PAGE_INK}">{escape(spec.title)}</text>\n'
        f'<text x="12" y="34" style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;'
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


EDGE_LABEL_SIZE = DETAIL_SIZE
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


def _bare(box, m: _Stage, gscale: tuple[float, ...],
          scales: dict[str, float] | None = None) -> str:
    """A stage with no box: the tensor IS the stage.

    Draw order is the whole point. The stack goes down first and the name is
    painted over it, so the name reads as a caption ON the drawing rather than a
    heading above a container. Detail sits under the stack on the page ground.

    The colour family moves onto the glyph. In the boxed figure the fill carries
    the family and the glyph is a translucent mark inside it; with the box gone
    there is nothing else to carry it, so the sheets take the fill and the stroke
    and the reader still sees convolution green against join purple.
    """
    fill, stroke = paint(m.spec.kind)
    top = box.y - box.h / 2.0
    cx = box.x + box.w / 2.0
    # THE FOOTPRINT IS STATED ONLY WHERE THE INK NO LONGER ANSWERS IT. A boxed
    # stage draws a rect any consumer can measure; this one draws sheets and text
    # and has no single rectangle, though the layout engine knows the area just
    # the same. So the fact is emitted here and not in `_box` — putting it on
    # both would restate what the boxed figure already says and would make every
    # committed figure in the gallery stale to add an attribute nobody reads.
    parts = [f'<g class="ds-stage ds-bare ds-kind-{escape(m.spec.kind)}" '
             f'data-stage="{escape(m.spec.id)}" '
             f'data-box="{_fmt(box.x)} {_fmt(top)} {_fmt(box.w)} '
             f'{_fmt(box.h)}">']

    # THE NAME CLEARS THE DRAWING. It was set at a fixed drop from the top of the
    # stage and painted after the sheets, so on any stage whose stack reached
    # that high the two occupied the same pixels -- "conv + ReLU" sitting on
    # LeNet's six sheets. Text over line art is the one collision class that is
    # never intentional, and it is also the class interface2's overlap checker
    # says it cannot see, because it looks for text on TEXT.
    #
    # So the stack is drawn into a band that starts below a reserved title line,
    # and the name is placed at whichever is lower: that reserved line, or just
    # above the stack's actual top edge. Tall stacks get a title on the common
    # line; short ones get a title that hugs the drawing instead of floating.
    title_y = top + PAD_Y + TITLE_SIZE
    y = top + PAD_Y + TITLE_LINE
    drew = False
    if m.glyph and m.spec.glyph.style == "sheets":
        sheet_fill = (f'fill:{fill};fill-opacity:0.94;stroke:{stroke};'
                      f'stroke-width:0.9;stroke-linejoin:round')
        y, ink_top = _draw_sheets(parts, m, box, y, stroke, gscale,
                                  fill=sheet_fill)
        title_y = max(title_y, ink_top - TITLE_GAP)
        drew = True
    elif m.marks or m.glyph:
        # THE DRAWING IS THE SUBJECT, WHICH IS WHAT THE BOX COMING OFF MEANS.
        # Drawn after the detail -- where the boxed figure puts it -- a mark
        # column hangs below its own labels with nothing holding the two
        # together, and `mean over cells` becomes a speck under three lines of
        # text. In the band, the composition is the one `sheets` already gets:
        # the tensor, the name as a caption on it, the numbers underneath.
        start = y
        if m.marks:
            y = _draw_marks(parts, m.marks, box, y, stroke)
        else:
            tall, wide = m.glyph
            sc = m.spec.glyph.scale
            gh = _edge_px(tall, gscale[0], GLYPH_H, sc)
            gw = _edge_px(wide, gscale[1], GLYPH_W, sc)
            parts.append(
                f'<rect class="ds-glyph" x="{_fmt(box.x + (box.w - gw) / 2.0)}" '
                f'y="{_fmt(y + 3 + (GLYPH_H - gh))}" '
                f'width="{_fmt(gw)}" height="{_fmt(gh)}" '
                f'style="fill:{fill};fill-opacity:0.94;stroke:{stroke};'
                f'stroke-width:0.9"/>'
            )
            y += GLYPH_ROW
        title_y = max(title_y, start - TITLE_GAP)
        drew = True
    else:
        # NOTHING DRAWN MEANS NOTHING TO CLEAR, so the name keeps the reserved
        # line and the detail starts below it. Without this the two shared a
        # baseline: a stage with no tensor to draw -- `flatten`, `class logits`,
        # every dense layer in LeNet -- printed its name straight through its
        # first detail line.
        pass

    # The name, over the stack. PAGE_INK because with no box behind it this text
    # sits on whatever ground the embedding page provides, which is §4's rule and
    # the reason a pinned dark ink went invisible on GitHub's dark theme.
    parts.append(
        f'<text x="{_fmt(cx)}" y="{_fmt(title_y)}" '
        f'text-anchor="middle" '
        f'style="font-family:{FONT_STACK};font-size:{TITLE_SIZE}px;'
        f'font-weight:600;fill:{PAGE_INK}">{escape(m.name)}</text>'
    )
    if m.repeat and m.repeat > 1:
        parts.append(
            f'<text class="ds-repeat-badge" x="{_fmt(box.x + box.w)}" '
            f'y="{_fmt(title_y)}" text-anchor="end" '
            f'style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;font-weight:600;'
            f'fill:{PAGE_MUTED}">×{m.repeat}</text>'
        )
    for line in m.detail:
        y += DETAIL_SIZE
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;'
            f'fill:{PAGE_MUTED}">{escape(line)}</text>'
        )
        y += DETAIL_LINE - DETAIL_SIZE

    # LANES, WHICH THIS PATH ALSO USED TO DROP. They are drawn against the
    # stage's own width, and a bare stage HAS one -- the layout engine sized it
    # the same way; it simply draws no rect. The first bare `tube` refused to
    # render for exactly this reason and the refusal was right: `dog`'s four
    # kernels are the parallelism the figure exists to show. Drawing them is
    # better than refusing them, and both beat dropping them quietly.
    if m.lane_labels:
        y += 5
    for label in m.lane_labels:
        lx = box.x + 7                       # the inset the boxed path uses
        lw = box.w - 14
        parts.append(
            f'<rect class="ds-lane" x="{_fmt(lx)}" y="{_fmt(y)}" '
            f'width="{_fmt(lw)}" height="{_fmt(LANE_ROW - 3)}" rx="2" '
            f'style="fill:#ffffff;fill-opacity:0.62;stroke:{stroke};'
            f'stroke-width:0.7"/>'
        )
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y + LANE_ROW - 6.5)}" '
            f'text-anchor="middle" '
            f'style="font-family:{FONT_STACK};font-size:{LANE_SIZE}px;'
            f'fill:{PAGE_INK}">{escape(label)}</text>'
        )
        y += LANE_ROW

    # METERS, THE THIRD THING THIS PATH USED TO DROP. A bar is drawn on a scale
    # shared across the figure, so a stage that loses its bar does not lose a
    # decoration -- it drops out of a comparison the other bars are still making,
    # and the reader has no way to tell it was ever in one. `tube` has no meters
    # today; `test_meters_scale_against_the_largest_in_their_series` puts two on
    # stages that are now bare, and it is what found this.
    if m.meters:
        y += 4
        widest = max(width(lbl, METER_SIZE) for lbl, _ in m.meters)
        row_w = widest + 5 + METER_BAR_W
        bx = box.x + (box.w - row_w) / 2.0
        for label, value in m.meters:
            full = (scales or {}).get(label) or 1.0
            bar_x = bx + widest + 5
            parts.append(
                f'<text x="{_fmt(bx)}" y="{_fmt(y + METER_BAR)}" '
                f'style="font-family:{FONT_STACK};font-size:{METER_SIZE}px;'
                f'fill:{PAGE_MUTED}">{escape(label)}</text>'
            )
            parts.append(
                f'<rect class="ds-meter-track" x="{_fmt(bar_x)}" '
                f'y="{_fmt(y)}" width="{_fmt(METER_BAR_W)}" '
                f'height="{_fmt(METER_BAR)}" rx="1.5" '
                f'style="fill:#ffffff;fill-opacity:0.62;stroke:{stroke};'
                f'stroke-width:0.5"/>'
            )
            filled = METER_BAR_W * (value / full) if full else 0.0
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


def _box(box, m: _Stage, scales: dict[str, float],
         gscale: tuple[float, float]) -> str:
    if m.chrome == "none":
        return _bare(box, m, gscale, scales)
    fill, stroke = paint(m.spec.kind)
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
            f'style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;font-weight:600;'
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

    elif m.glyph and m.spec.glyph.style == "sheets":
        y, _ = _draw_sheets(parts, m, box, y, stroke, gscale)

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


def _shade(stroke: str) -> tuple[str, str]:
    """Top and side fills for a slab, from the stage's own stroke colour.

    Two steps of OPACITY rather than two new hues: the palette separates kinds by
    value as much as by hue so a figure survives a greyscale print, and inventing
    a lit and a shaded variant per family would be a second palette to keep in
    step with the first.
    """
    return (f'fill:{stroke};fill-opacity:0.46;stroke:{stroke};stroke-width:0.7;'
            f'stroke-linejoin:round',
            f'fill:{stroke};fill-opacity:0.60;stroke:{stroke};stroke-width:0.7;'
            f'stroke-linejoin:round')


def _sheet_geom(m, gscale, bare: bool):
    """The stack's drawn geometry: face, depth, and total footprint.

    ONE QUANTITY, ONE IMPLEMENTATION. This is called twice — once to size the
    box and once to draw into it — and if the two disagreed by a pixel the glyph
    would be off-centre or clipped. So neither computes it; both ask this.
    """
    span = BARE_SPAN if bare else SHEET_SPAN
    biggest = max(gscale) if gscale else 0.0
    depth_v, tall_v, wide_v = m.glyph
    sc = m.spec.glyph.scale
    fh = _edge_px(tall_v, biggest, span, sc)
    fw = _edge_px(wide_v, biggest, span, sc)
    dep = _edge_px(depth_v, biggest, span, sc)
    return fw, fh, dep, fw + dep, fh + dep * SHEET_SKEW


def sheet_ceiling(depth: float) -> int:
    """Most sheets separable in `depth` units — the count ceiling, derived."""
    return int(depth // SHEET_MIN_PITCH) + 1


def _countable(n: int, depth: float) -> bool:
    """Can a reader separate this stack as drawn?

    ONE TEST. Sheets nobody can tell apart are not a count, whether that is
    because there are too many of them or because the stage was allotted too
    little depth to spread them over — and those are the same measurement taken
    from opposite ends. A stack that fails falls back to the slab, which states
    the number instead of implying it.
    """
    if n <= 0:
        return False
    if n == 1:
        return True
    return depth / (n - 1) >= SHEET_MIN_PITCH


def _draw_sheets(parts: list[str], m, box, y: float, stroke: str,
                 gscale: tuple[float, ...], fill: str | None = None) -> float:
    """n x m x p as n flat sheets of m x p, offset up and to the right.

    THREE EDGES, ONE SCALE EACH, AND THE VOLUME IS THE CLAIM. Face height comes
    from axes[1], face width from axes[2] and the depth the stack travels from
    axes[0], every one of them through `_edge_px` against the figure-wide
    maximum for that position. So the perceived volume -- face area times depth
    -- stands in the same relation to the tensor as a block's area does to its
    two axes. That is the argument for allowing a third axis at all.

    A STACK NOBODY CAN SEPARATE BECOMES ONE SLAB WITH ITS COUNT. The slab keeps
    the SAME DEPTH, so a stack too deep to count still draws the right size and
    the shape of the model survives; only the countability is given up, and the
    number is printed rather than implied. This is `marks`' bar at MARK_MAX, one
    rank up — and see SHEET_MIN_PITCH for why the ceiling is a pitch rather than
    a count.
    """
    bare = m.chrome == "none"
    fw, fh, dep, total_w, total_h = _sheet_geom(m, gscale, bare)
    dx, dy = dep, dep * SHEET_SKEW
    n = int(m.glyph[0])

    # The whole stack, centred as one object and sitting on the row's baseline.
    ox = box.x + (box.w - total_w) / 2.0
    base = y + (m.glyph_row - SHEET_SKEW_PAD - total_h) + 3

    if fill is None:
        fill = f'fill:{stroke};fill-opacity:0.32;stroke:{stroke};stroke-width:0.55'
    if _countable(n, dx):
        # Back to front, so nearer sheets occlude further ones.
        for k in range(n - 1, -1, -1):
            frac = k / (n - 1) if n > 1 else 0.0
            sx, sy = ox + dx * frac, base + dy * (1.0 - frac)
            parts.append(
                f'<rect class="ds-sheet" x="{_fmt(sx)}" y="{_fmt(sy)}" '
                f'width="{_fmt(fw)}" height="{_fmt(fh)}" style="{fill}"/>'
            )
    else:
        # ONE SOLID OF THE SAME DEPTH, DRAWN AS A SOLID. The first version was a
        # single hexagon outline, and its whole claim to depth rested on two cut
        # corners — subtle enough that Tony read the slabs as flat shapes with an
        # odd bevel. A top and a side face at separated values cost nothing, need
        # no extra geometry, and read as a solid immediately. The three faces are
        # tinted from the SAME family colour so the kind is still legible in
        # greyscale, which SPEC.md §4 requires.
        top_f, side_f = _shade(stroke)
        parts.append(
            f'<polygon class="ds-sheet ds-sheet-top" points="'
            f'{_fmt(ox)},{_fmt(base + dy)} {_fmt(ox + dx)},{_fmt(base)} '
            f'{_fmt(ox + dx + fw)},{_fmt(base)} '
            f'{_fmt(ox + fw)},{_fmt(base + dy)}" style="{top_f}"/>')
        parts.append(
            f'<polygon class="ds-sheet ds-sheet-side" points="'
            f'{_fmt(ox + fw)},{_fmt(base + dy)} '
            f'{_fmt(ox + dx + fw)},{_fmt(base)} '
            f'{_fmt(ox + dx + fw)},{_fmt(base + fh)} '
            f'{_fmt(ox + fw)},{_fmt(base + fh + dy)}" style="{side_f}"/>')
        parts.append(
            f'<rect class="ds-sheet" x="{_fmt(ox)}" y="{_fmt(base + dy)}" '
            f'width="{_fmt(fw)}" height="{_fmt(fh)}" style="{fill}"/>')
        parts.append(
            f'<text x="{_fmt(ox + dx + fw + 3)}" '
            f'y="{_fmt(base + fh / 2 + dy / 2 + 2.5)}" '
            f'style="font-family:{FONT_STACK};font-size:{DETAIL_SIZE}px;'
            f'fill:{MUTED}">×{n}</text>'
        )
    return y + m.glyph_row, base


def _shape_axes(text: str, glyph, where: str) -> tuple[float, ...]:
    """Pull the named axes out of one resolved shape.

    RANK COMES FROM THE STYLE. Two for a rectangle, three for a stack of sheets,
    and nothing else — `check` states the rule and its reason; this is the same
    rule where the drawing happens, because a spec may be rendered unchecked.
    """
    parts = text.split(TIMES)
    try:
        dims = [float(p) for p in parts]
    except ValueError:
        raise FactError(
            f"{where}: glyph `of` resolved to {text!r}, which is not a shape. It "
            "must be one reference to a tensor shape, such as "
            "{stage.out_shape}.") from None
    want = 3 if glyph.style == "sheets" else 2
    if len(glyph.axes) != want or len(glyph.labels) != want:
        raise FactError(
            f"{where}: a {glyph.style!r} glyph needs exactly {want} axes and "
            f"{want} labels")
    out = []
    for i in glyph.axes:
        if i >= len(dims):
            raise FactError(
                f"{where}: glyph asks for axis {i} of {text!r}, which has "
                f"{len(dims)} axes.")
        out.append(dims[i])
    return tuple(out)


def _physical(spec, w: float, h: float) -> str:
    """The SVG's width and height attributes.

    THIS IS THE HALF THAT WAS MISSING. A viewBox says what the coordinates mean
    relative to each other; `width` and `height` say how big the thing is. With
    no unit they are pixels, so every figure asserted it was 1594 pixels wide and
    a page scaled it to fit — taking the type with it. Stating `6in` makes the
    figure the size it was solved for, in LaTeX, Word or a browser alike, and the
    aspect is preserved because the height is derived from the same scale.
    """
    if not spec.output.width:
        return f'width="{_fmt(w)}" height="{_fmt(h)}"'
    target = length_pt(spec.output.width, "output.width")
    per_unit = target / w if w else 0.0
    return (f'width="{spec.output.width}" '
            f'height="{_fmt(round(h * per_unit / 72.0, 4))}in"')


def width_budget(spec) -> float | None:
    """Widest the figure may be, in figure units, to keep type above the floor.

    A figure is drawn in arbitrary units and printed at a physical width, so the
    two together fix what a unit is worth in points. The smallest type in the
    figure is DETAIL_SIZE units, so:

        units_max = DETAIL_SIZE x target_points / floor_points

    At 6in with a 6pt floor that is 684 units. Returns None when the spec states
    no output width, which is every figure written before this existed.
    """
    if not spec.output.width:
        return None
    target = length_pt(spec.output.width, "output.width")
    floor = length_pt(spec.output.min_type, "output.min_type")
    if floor <= 0:
        raise FactError("output.min_type must be greater than zero")
    return DETAIL_SIZE * target / floor


def type_pt(spec, figure_units: float) -> float | None:
    """What the smallest type actually becomes at the stated output width."""
    if not spec.output.width or figure_units <= 0:
        return None
    return DETAIL_SIZE * length_pt(spec.output.width, "output.width") / figure_units


def _glyph_scales(measured) -> tuple[float, ...]:
    """The biggest value at each axis position, anywhere in the figure.

    ONE SCALE PER AXIS, SHARED BY EVERY GLYPH — so two stages with the same
    tensor draw the same rectangle, which is the whole claim the glyph makes.
    `check` proves every glyph in a figure has the same rank, so the tuples all
    have the same length and position i means the same thing in all of them.
    """
    biggest: list[float] = []
    for m in measured.values():
        if not m.glyph:
            continue
        if not biggest:
            biggest = [0.0] * len(m.glyph)
        for i, v in enumerate(m.glyph):
            biggest[i] = max(biggest[i], v)
    return tuple(biggest) or (0.0, 0.0)


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
