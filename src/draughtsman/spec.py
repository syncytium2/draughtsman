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
class Stage:
    id: str
    name: str
    kind: str = "op"
    nodes: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)
    note: str | None = None
    lanes: Lanes | None = None


@dataclass
class Edge:
    src: str
    dst: str
    label: str | None = None
    style: str = "solid"


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
        ))
    edges = [Edge(src=e["from"], dst=e["to"], label=e.get("label"),
                  style=e.get("style", "solid"))
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
                constants=dict(doc.get("constants") or {}))


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
        out["stages"].append(rec)
    out["edges"] = [
        {k: v for k, v in (("from", e.src), ("to", e.dst), ("label", e.label),
                           ("style", e.style if e.style != "solid" else None))
         if v is not None}
        for e in spec.edges
    ]
    if spec.elided:
        out["elided"] = [{"nodes": e.nodes, "reason": e.reason} for e in spec.elided]
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
