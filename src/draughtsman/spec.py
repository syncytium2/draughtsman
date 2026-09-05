"""``spec.json`` — the agent's judgement, and the only place it lives.

Committed, hand-editable, and reviewable in a diff (SPEC.md §6, §8.3). It carries
groupings, human names and topology. It carries no facts: quantities appear as
``{references}`` that :mod:`draughtsman.facts` resolves against ``graph.json`` at
render time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from draughtsman import FORMAT


@dataclass
class Lanes:
    """Parallel branches drawn inside one stage.

    THIS EXISTS BECAUSE PARALLELISM IS OFTEN NOT A FORK IN THE GRAPH. `tube` fans
    out into four difference-of-Gaussian kernels, and the trace records that as a
    single ``aten::_convolution`` with a ``(4, 1, 257)`` weight -- the four kernels
    are a channel dimension, not four edges. A figure drawn from topology alone
    therefore CANNOT show the fan-out, which is SPEC.md §9's acceptance test.

    So the agent may say "draw this as lanes" -- and may not say how many. The
    count is a reference resolved from graph.json; the labels are names, which are
    the agent's job. `check` asserts the two agree, so a label list that drifts
    from the model fails rather than misleads.
    """
    count_from: str
    labels: list[str] = field(default_factory=list)


@dataclass
class Meter:
    """A number in a box, drawn as a bar instead of read as digits.

    THE AGENT STILL SUPPLIES NO FACT. `value` is a {reference}; the renderer
    resolves it against graph.json and scales it. What the agent chooses is WHICH
    quantity deserves a picture and what to call it.

    `label` is also the SERIES. Every meter sharing a label is drawn on one scale
    computed across the whole figure, so two bars are comparable iff they are
    labelled the same -- and never comparable across labels, because a bar of
    parameters and a bar of frames have no common unit. A bar whose series has
    only one member compares with nothing and `check` says so.
    """
    value: str
    label: str


@dataclass
class Repeat:
    """This stage stands for N copies of the stages that draw one unit.

    THE AGENT NAMES THE UNIT; DRAUGHTSMAN COUNTS IT. No fact in graph.json says
    "there are four blocks" -- not a constant, not a shape -- so a `count_from`
    reference has nothing to point at. What the agent can supply is structure:
    "this collapsed stage is a repetition of those stages." draughtsman then takes
    the template's op-kind sequence and tiles it against this stage's nodes. The
    count is how many times it tiles, and a template that does not tile EXACTLY
    is an error.

    So a spec claiming a repetition the graph does not contain fails instead of
    drawing one, which is the whole reason the agent is allowed near the figure.
    """
    template: list[str]     # stage ids, in order, that draw one unit


@dataclass
class Glyph:
    """The stage's tensor, drawn to scale: one axis tall, another wide.

    BOTH AXES COME FROM ONE SHAPE, and that is the constraint that makes the mark
    honest rather than decorative. The eye reads a rectangle's AREA whether or not
    you meant it to, so if height and width came from unrelated references the
    reader would be perceiving a product that means nothing. Two axes of one
    tensor multiply to something real.

    Not the box's own geometry. A box is already sized by its text and is already
    an input to the layout engine, so an encoding put there would be clamped by
    the longest label -- and a clamped scale is a truncated baseline, which is the
    thing a figure must never do quietly. The glyph sits on a canvas of constant
    size instead, and the box is left alone.
    """
    of: str                 # ONE shape reference, e.g. "{stage.out_shape}"
    axes: list[int]         # [tall, wide] — indices into that shape
    labels: list[str]       # what to call them, in the same order
    # "sqrt" (default) or "linear". Linear is the faithful encoding and the one
    # to use when the range allows it: area is then literally the tensor. It is
    # not the default because channel counts in real models span three orders of
    # magnitude, and a linear edge there puts the smallest rectangle under a
    # pixel -- a figure showing "big" and "absent" rather than a range. Whichever
    # is chosen, the legend names it, so the compression is never silent.
    scale: str = "sqrt"
    # "block" (default) draws one rectangle scaled against the whole figure.
    # "marks" draws the axes as COUNTABLE OBJECTS instead -- axes[0] as rows,
    # axes[1] as columns, so a 3x5 tensor is three rows of five and a lone
    # countable axis is a column. It is the more literal encoding and the more
    # limited one: a reader can count to about thirty and no further, so an axis
    # past that is drawn as a solid bar with its number rather than as marks
    # nobody could count. See MARK_MAX in render.py.
    #
    # "sheets" TAKES A THIRD AXIS, and it is the only style that may. n x m x p
    # is drawn as n flat sheets of m x p, offset. axes are [depth, tall, wide]:
    # axes[0] is the sheet COUNT, axes[1] and axes[2] are the face.
    #
    # WHY A THIRD AXIS IS ALLOWED HERE AND NOWHERE ELSE. The two-axis rule above
    # exists because the eye reads a rectangle's AREA whether or not you meant it
    # to, so both edges must come from one tensor or the reader is perceiving a
    # product that means nothing. An offset stack is read the same way one step
    # up: the eye reads the VOLUME of the stack -- face area times how deep it
    # goes -- and three axes of one tensor multiply to something real exactly as
    # two do. So the rule is not relaxed, it is the same rule at rank three, and
    # `check` still refuses a glyph whose axes do not all come from one `of`.
    #
    # What this buys, measured on U-Net before the style existed: with axes
    # [-3,-2] its glyph is CONSTANT at every encoder stage, because channels
    # double at exactly the rate height halves. The figure reported "unchanging"
    # for the quantity that is the architecture. The dropped axis halves too, so
    # the volume runs 65536, 32768, 16384, 8192 and back -- the U the network is
    # named for, invisible in any two of its three axes.
    style: str = "block"


@dataclass
class Stage:
    id: str
    name: str
    kind: str = "op"
    nodes: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)
    note: str | None = None
    lanes: Lanes | None = None
    meters: list[Meter] = field(default_factory=list)
    glyph: Glyph | None = None
    repeat: Repeat | None = None
    # PER STAGE, AND None MEANS "WHATEVER THE FIGURE SAYS". The rule the page
    # runs on is about a stage, not a figure: a box is right when the content is
    # words and wrong when the content is a drawing of the tensor, and a figure
    # normally holds both. `layout.chrome` was the only way to say it, so a
    # figure was all boxes or none of them -- which made `tube` draw its marks
    # inside boxes because its last stage is words, and made the alternative
    # strip the box off that stage to fix the other six.
    #
    # Inheriting rather than defaulting to "box" is what keeps every committed
    # figure byte-identical: a spec that says nothing here renders exactly as it
    # did, through the same path.
    chrome: str | None = None


@dataclass
class Edge:
    src: str
    dst: str
    label: str | None = None
    style: str = "solid"
    # An arrow the trace does not contain, drawn anyway and SAID SO. The VAE's
    # noise is the case: a reader wants the sample to depend on mu and sigma, and
    # the trace only records the shape read. A reason here is a decision in a
    # diff, exactly as `elided` is for a dropped node.
    untraced: str | None = None


@dataclass
class Layout:
    """How the figure is arranged. Judgement, so it lives in the spec.

    Not a render-time flag: a wrapped figure must come out of the committed spec
    the same way on any machine, or SPEC.md §6's staleness test is asserting the
    shape of whoever last ran it.
    """
    orientation: str = "lr"        # "lr" left-to-right, "tb" top-to-bottom
    wrap: float | None = None      # break the spine into rows at this width
    # A key under the figure, one row per colour family present, each carrying its
    # share of the traced ops and parameters. Off by default: a figure that is one
    # colour family does not need one, and turning it on for every committed spec
    # would change every committed figure.
    legend: bool = False
    # "box" (default) draws a filled, stroked rectangle per stage and sets the
    # text inside it. "none" removes it and lets the TENSOR be the stage: the
    # glyph is drawn large, the name floats over it, and the detail sits
    # underneath on the page.
    #
    # WHY THIS IS A CHOICE AND NOT A DEFAULT. A box is the right container when
    # the stage's content is words — a name, three detail lines, a lane stack —
    # because it groups them and its fill carries the colour family. It is the
    # wrong one when the content is a DRAWING of the tensor: the box is then a
    # second rectangle around a rectangle, competing for the same reading, and
    # the eye settles on the larger one. Every glyph in this gallery was drawn
    # inside a box eight times its area, so the figure was a row of boxes with a
    # small mark inside rather than a row of tensors.
    #
    # With no box the colour family moves onto the glyph itself, which is where
    # it belonged once the glyph became the subject.
    chrome: str = "box"


# ONE PLACE THAT KNOWS WHAT A LENGTH MEANS.
#
# A figure had no physical size at all until now: the SVG said `width="1594.64"`,
# unitless, which is pixels — so a journal page placed it at whatever scale fit
# the column and took the type down with it. Measured across the gallery, that
# put detail text between 1.45pt and 3.06pt in a 3.5in column and between 2.49pt
# and 5.25pt at 6in. Nothing in the tool mentioned an inch.
#
# So a length is parsed here and nowhere else. Points are the internal currency
# because type is specified in points and the floor is a type size.
_PER_PT = {"pt": 1.0, "in": 72.0, "mm": 72.0 / 25.4, "cm": 720.0 / 25.4,
           "px": 0.75}          # CSS px: 96 per inch


def length_pt(text: str, where: str) -> float:
    """`"6in"`, `"180mm"`, `"12pt"` -> points. The only length parser."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(pt|in|mm|cm|px)\s*", str(text))
    if not m:
        raise ValueError(
            f"{where}: {text!r} is not a length. Write a number and a unit, one "
            f"of {', '.join(sorted(_PER_PT))} — for example '6in' or '180mm'.")
    return float(m.group(1)) * _PER_PT[m.group(2)]


@dataclass
class Output:
    """The size this figure will be PRINTED at, and the type it must keep there.

    THE FIGURE IS DRAWN IN ARBITRARY UNITS AND THAT IS FINE — what was missing is
    a statement of what those units become on a page. With `width` set, the
    renderer emits a real physical width, layout is solved against the budget it
    implies, and `check` refuses a figure whose smallest type would land under
    `min_type` at that size.

    NEVER THE TYPE. The one thing that may not give is the type size: a figure
    that fits by shrinking its labels has solved the wrong problem. Layout wraps
    harder and the graph gets smaller; if that is not enough the figure is
    refused and the author is told by how much.
    """
    width: str | None = None        # "6in", "3.5in", "180mm"
    min_type: str = "6pt"           # the floor the smallest label must clear


@dataclass
class Elision:
    nodes: list[str]
    reason: str


@dataclass
class Spec:
    title: str
    stages: list[Stage]
    edges: list[Edge]
    elided: list[Elision] = field(default_factory=list)
    subtitle: str | None = None
    caption: str | None = None
    graph: str = "graph.json"
    layout: Layout = field(default_factory=Layout)
    # How big this will be on the page, and the type it must keep at that size.
    output: Output = field(default_factory=Output)
    # Reference path -> why that traced constant is an architectural quantity.
    # Required only when graph.json carries a bake hazard; see check.py.
    constants: dict[str, str] = field(default_factory=dict)
    # Which axis of an activation shape is the batch, so the figure can stop
    # drawing it. A judgement -- the renderer cannot tell a batch axis of 1 from
    # a channel axis of 1 -- so the spec declares it and `check` refuses the
    # declaration wherever the hidden number is not 1. None: draw every axis.
    batch_axis: int | None = None

    @property
    def by_id(self) -> dict[str, Stage]:
        return {s.id: s for s in self.stages}


def _stage_chrome(raw: dict) -> str | None:
    """A typo here would silently draw a box, so it is refused instead."""
    value = raw.get("chrome")
    if value is None:
        return None
    if value not in ("box", "none"):
        raise ValueError(
            f"stage {raw.get('id')!r}: chrome must be 'box' or 'none', not "
            f"{value!r}. A stage that says nothing takes the figure's.")
    return value


def load(doc: dict) -> Spec:
    stages = []
    for raw in doc.get("stages", []):
        lanes = None
        if raw.get("lanes"):
            lanes = Lanes(count_from=raw["lanes"]["count_from"],
                          labels=list(raw["lanes"].get("labels", [])))
        stages.append(Stage(
            id=raw["id"], name=raw["name"], kind=raw.get("kind", "op"),
            nodes=list(raw.get("nodes", [])), detail=list(raw.get("detail", [])),
            note=raw.get("note"), lanes=lanes,
            meters=[Meter(value=m["value"], label=m["label"])
                    for m in raw.get("meters", [])],
            repeat=(Repeat(template=list(raw["repeat"]["template"]))
                    if raw.get("repeat") else None),
            chrome=_stage_chrome(raw),
            glyph=(Glyph(of=raw["glyph"]["of"],
                         axes=list(raw["glyph"]["axes"]),
                         labels=list(raw["glyph"]["labels"]),
                         scale=raw["glyph"].get("scale", "sqrt"),
                         style=raw["glyph"].get("style", "block"))
                   if raw.get("glyph") else None),
        ))
    edges = [Edge(src=e["from"], dst=e["to"], label=e.get("label"),
                  style=e.get("style", "solid"), untraced=e.get("untraced"))
             for e in doc.get("edges", [])]
    elided = [Elision(nodes=list(e["nodes"]), reason=e["reason"])
              for e in doc.get("elided", [])]
    lay = doc.get("layout") or {}
    return Spec(title=doc.get("title", "model"), stages=stages, edges=edges,
                elided=elided, subtitle=doc.get("subtitle"),
                caption=doc.get("caption"), graph=doc.get("graph", "graph.json"),
                layout=Layout(orientation=lay.get("orientation", "lr"),
                              wrap=lay.get("wrap"),
                              legend=bool(lay.get("legend", False)),
                              chrome=lay.get("chrome", "box")),
                output=Output(
                    width=(doc.get("output") or {}).get("width"),
                    min_type=(doc.get("output") or {}).get("min_type", "6pt")),
                constants=dict(doc.get("constants") or {}),
                batch_axis=doc.get("batch_axis"))


def dump(spec: Spec) -> dict:
    out = {"draughtsman": FORMAT, "graph": spec.graph, "title": spec.title}
    if spec.subtitle:
        out["subtitle"] = spec.subtitle
    out["stages"] = []
    for s in spec.stages:
        rec = {"id": s.id, "name": s.name, "kind": s.kind, "nodes": s.nodes}
        if s.detail:
            rec["detail"] = s.detail
        if s.note:
            rec["note"] = s.note
        if s.lanes:
            rec["lanes"] = {"count_from": s.lanes.count_from,
                            "labels": s.lanes.labels}
        if s.meters:
            rec["meters"] = [{"value": m.value, "label": m.label}
                             for m in s.meters]
        if s.repeat:
            rec["repeat"] = {"template": s.repeat.template}
        if s.chrome is not None:
            rec["chrome"] = s.chrome
        if s.glyph:
            rec["glyph"] = {"of": s.glyph.of, "axes": s.glyph.axes,
                            "labels": s.glyph.labels}
            if s.glyph.scale != "sqrt":
                rec["glyph"]["scale"] = s.glyph.scale
            if s.glyph.style != "block":
                rec["glyph"]["style"] = s.glyph.style
        out["stages"].append(rec)
    out["edges"] = [
        {k: v for k, v in (("from", e.src), ("to", e.dst), ("label", e.label),
                           ("style", e.style if e.style != "solid" else None),
                           ("untraced", e.untraced))
         if v is not None}
        for e in spec.edges
    ]
    if spec.elided:
        out["elided"] = [{"nodes": e.nodes, "reason": e.reason} for e in spec.elided]
    if spec.batch_axis is not None:
        out["batch_axis"] = spec.batch_axis
    if spec.constants:
        out["constants"] = dict(spec.constants)
    if spec.caption:
        out["caption"] = spec.caption
    # Omitted entirely when it is the default, so adding this field changes no
    # existing spec and no existing figure.
    if spec.output.width or spec.output.min_type != "6pt":
        out["output"] = {}
        if spec.output.width:
            out["output"]["width"] = spec.output.width
        if spec.output.min_type != "6pt":
            out["output"]["min_type"] = spec.output.min_type
    if (spec.layout.orientation != "lr" or spec.layout.wrap
            or spec.layout.legend or spec.layout.chrome != "box"):
        out["layout"] = {"orientation": spec.layout.orientation}
        if spec.layout.wrap:
            out["layout"]["wrap"] = spec.layout.wrap
        if spec.layout.legend:
            out["layout"]["legend"] = True
        if spec.layout.chrome != "box":
            out["layout"]["chrome"] = spec.layout.chrome
    return out


def dumps(spec: Spec) -> str:
    return json.dumps(dump(spec), indent=2, ensure_ascii=False) + "\n"
