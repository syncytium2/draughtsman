"""``spec.json`` — the agent's judgement, and the only place it lives.

Committed, hand-editable, and reviewable in a diff (SPEC.md §6, §8.3). It carries
groupings, human names and topology. It carries no facts: quantities appear as
``{references}`` that :mod:`draughtsman.facts` resolves against ``graph.json`` at
render time.
"""

from __future__ import annotations

import json
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
                              legend=bool(lay.get("legend", False))),
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
    if (spec.layout.orientation != "lr" or spec.layout.wrap
            or spec.layout.legend):
        out["layout"] = {"orientation": spec.layout.orientation}
        if spec.layout.wrap:
            out["layout"]["wrap"] = spec.layout.wrap
        if spec.layout.legend:
            out["layout"]["legend"] = True
    return out


def dumps(spec: Spec) -> str:
    return json.dumps(dump(spec), indent=2, ensure_ascii=False) + "\n"
