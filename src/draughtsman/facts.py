"""Reading facts out of ``graph.json``, and only out of ``graph.json``.

SPEC.md §4: "The agent never supplies a fact. Every quantity in the rendered
figure is looked up from graph.json by node id at render time."

So the spec's text carries REFERENCES, not numbers, and this module resolves
them. ``"{stage.out_shape} · {stage.params} params"`` renders as
``"1x4x600 · 12 params"``. An unresolvable reference is an error, never a blank:
a figure with a missing number is better than a figure with a wrong one.
"""

from __future__ import annotations

import re


class FactError(ValueError):
    """A reference that graph.json cannot answer."""


TIMES = "×"

REF_RE = re.compile(r"\{([^{}]+)\}")


class Graph:
    """``graph.json``, indexed."""

    def __init__(self, doc: dict):
        self.doc = doc
        self.model = doc["model"]
        self.inputs = doc.get("inputs", [])
        self.outputs = doc.get("outputs", [])
        self.traced = [n["id"] for n in doc["nodes"]]  # what §5 coverage ranges over
        self.nodes = {n["id"]: n for n in doc["nodes"]}
        # The model's own inputs are facts too -- a stage naming the raster wants
        # its shape -- but they are not traced ops, so they are addressable here
        # and absent from `traced`, which coverage ranges over.
        for rec in self.inputs:
            self.nodes[rec["id"]] = {
                "id": rec["id"], "kind": "input", "module": None, "source": None,
                "inputs": [], "tensor_inputs": [], "params": 0, "param_names": [],
                "constants": {}, "out_shape": rec["shape"],
                "outputs": [{"value": rec["value"], "shape": rec["shape"]}],
            }
        self.order = [r["id"] for r in self.inputs] + self.traced
        # The tracer's own testimony that it baked a Python value out of a
        # tensor, so a traced constant here may be an initialisation rather than
        # an architectural quantity. Absent on a graph traced before this field
        # existed, which reads as "the tracer said nothing", not "all clear" --
        # check.py distinguishes the two.
        self.hazards = list(doc.get("hazards") or [])
        self.hazards_recorded = "hazards" in doc
        # Only a bake in the MODEL's own code is evidence about this figure; one
        # inside torch reflects how a stock module was constructed. See
        # tracing._hazards.
        self.model_hazards = [h for h in self.hazards if not h.get("internal")]

    # -- shaping -------------------------------------------------------------
    @staticmethod
    def fmt(value) -> str:
        if value is None:
            raise FactError("value is null in graph.json")
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, list):
            if len(value) == 1:
                return Graph.fmt(value[0])
            return TIMES.join(Graph.fmt(v) for v in value)
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    # -- lookup --------------------------------------------------------------
    def _dig(self, obj, path: list[str], where: str):
        for step in path:
            idx = None
            if step.endswith("]") and "[" in step:
                step, _, rest = step.partition("[")
                idx = int(rest.rstrip("]"))
            if step:
                if not isinstance(obj, dict) or step not in obj:
                    raise FactError(f"{where}: no field {step!r}")
                obj = obj[step]
            if idx is not None:
                if not isinstance(obj, list):
                    raise FactError(f"{where}: {step!r} is not indexable")
                if idx >= len(obj):
                    raise FactError(f"{where}: index {idx} out of range "
                                    f"(length {len(obj)})")
                obj = obj[idx]
        return obj

    def node_fact(self, nid: str, path: list[str]):
        if nid not in self.nodes:
            raise FactError(f"no node {nid!r} in graph.json")
        return self._dig(self.nodes[nid], path, f"node {nid}")

    def model_fact(self, path: list[str]):
        return self._dig(self.model, path, "model")

    def stage_params(self, node_ids) -> int:
        return sum(self.nodes[n]["params"] for n in node_ids if n in self.nodes)

    def stage_exits(self, node_ids) -> list[str]:
        """Every member of a stage whose output leaves it, in trace order.

        USUALLY THERE IS ONE. When there are several, `{stage.out_shape}` has no
        single answer, and the old code silently returned the last — see
        :meth:`stage_fact` for why that is worth an error rather than a guess.
        """
        members = [n for n in self.order if n in set(node_ids)]
        if not members:
            raise FactError("stage has no nodes in graph.json")
        inside = set(members)
        exits = []
        for nid in members:
            consumers = [m for m in self.order
                         if nid in self.nodes[m].get("tensor_inputs", [])]
            if not consumers or any(c not in inside for c in consumers):
                exits.append(nid)
        return exits or [members[-1]]

    def stage_terminal(self, node_ids) -> str:
        """The node a stage exits through, when that is not in doubt."""
        return self.stage_exits(node_ids)[-1]

    def stage_fact(self, node_ids, path: list[str]):
        """A fact about the stage as a whole.

        `params` and `nodes` are properties of the membership, so they are
        summed. Everything else is a property of the node the stage EXITS
        THROUGH, and that is where this got dangerous.

        WHAT HAPPENED. Whisper's embedding stage carried two causal-mask slices.
        They were moved upstream — correctly, a mask enters once and does not
        belong inside one of four repeated blocks — and that changed which member
        was last out. `{stage.out_shape}` silently stopped meaning the embedding's
        1x12x384 and started meaning the mask's 12x12. Every reference still
        resolved. Coverage was green, the edge assertion was green, the repeat
        verified, and the figure stated the wrong shape. It was caught by a person
        looking at the picture, which is the one check SPEC.md §5 admits it cannot
        make.

        So: when a stage has several exits, ask each of them. If they agree there
        was never any ambiguity and the answer stands. If they disagree, REFUSE —
        naming the candidates and what each would have said. A figure with a
        missing number beats one with a wrong one, and this module already
        declines to guess everywhere else.

        Note what is NOT offered: a way to declare which exit is meant. The
        reference to name one node already exists — `{node:n0123.out_shape}` — and
        adding a second spelling for it would be two ways to say one thing.
        """
        if path and path[0] == "params":
            return self._dig({"params": self.stage_params(node_ids)}, path, "stage")
        if path and path[0] == "nodes":
            return len(node_ids)

        exits = self.stage_exits(node_ids)
        answers = {}
        for nid in exits:
            try:
                answers[nid] = self.fmt(self.node_fact(nid, path))
            except FactError:
                answers[nid] = None
        distinct = {v for v in answers.values() if v is not None}
        if len(distinct) > 1:
            said = ", ".join(f"{nid} would say {v}" for nid, v in answers.items()
                             if v is not None)
            raise FactError(
                f"this stage exits through {len(exits)} nodes and they do not "
                f"agree ({said}). Name the one you mean — "
                f"{{node:{exits[-1]}.{'.'.join(path)}}} — rather than letting the "
                "grouping decide it"
            )
        return self.node_fact(exits[-1], path)


def repeat_counts(spec_stages, graph: Graph) -> dict[str, int | None]:
    """Every `repeat` stage's count, computed once, here.

    ONE PLACE COUNTS A REPETITION, for the same reason one place counts coverage
    (DECISIONS.md): the check that can fail and the figure that gets drawn must
    never be reading two different numbers.
    """
    by_id = {s.id: s for s in spec_stages}
    out: dict[str, int | None] = {}
    for s in spec_stages:
        if not s.repeat:
            continue
        try:
            unit = [graph.nodes[n]["kind"]
                    for sid in s.repeat.template
                    for n in sorted(by_id[sid].nodes)]
        except KeyError:
            out[s.id] = None
            continue
        mine = [graph.nodes[n]["kind"] for n in sorted(s.nodes)
                if n in graph.nodes]
        out[s.id] = tiles(unit, mine)
    return out


#: Fields whose value is a whole activation shape, and therefore carry the batch
#: axis. `weight_shape` is deliberately absent -- a conv weight is
#: (out_ch, in_ch, k) and has no batch axis to hide.
BATCHED_SHAPE_FIELDS = ("out_shape", "input_shape")


def drop_batch(value, path: list[str], batch_axis: int | None):
    """Hide the batch axis from a whole shape, when the spec declared one.

    THE RENDERER CANNOT KNOW WHICH AXIS IS BATCH, so it is never guessed. A
    traced `[1, 1, 28, 28]` has two axes of size 1 and only the spec's author
    knows which is the batch. And `tube` traces `[30, 1, 600]` midway --
    **that leading 30 is CELLS, not a batch of 30** -- so a renderer that
    guessed would delete the cell count and say nothing about it.

    So this fires only on a declared `batch_axis`, only on a whole shape, and
    `check` refuses the declaration wherever the hidden number is not 1 --
    because an axis that is not 1 is carrying information and hiding it would be
    a lie.
    """
    if batch_axis is None or not isinstance(value, list):
        return value
    if not path or path[-1].partition("[")[0] not in BATCHED_SHAPE_FIELDS:
        return value
    if path[-1].endswith("]"):          # an index was taken; this is a scalar
        return value
    if not (-len(value) <= batch_axis < len(value)):
        return value
    return value[:batch_axis] + value[batch_axis + 1:]


def _indexed_axis(path: list[str]) -> int | None:
    """The index in ``out_shape[2]``, when the field is a batch-carrying shape."""
    if not path:
        return None
    field, br, rest = path[-1].partition("[")
    if not br or field not in BATCHED_SHAPE_FIELDS:
        return None
    try:
        return int(rest.rstrip("]"))
    except ValueError:
        return None


def _same_axis(a: int, b: int, rank: int) -> bool:
    """Whether two indices name the same axis of a shape of *rank*.

    Negative indices count from the end, so on a 3-axis shape ``[-3]`` and
    ``[0]`` are one axis. Comparing the literals would let ``[-3]`` walk past
    the rule that ``[0]`` is refused by.
    """
    norm = lambda i: i + rank if i < 0 else i
    return norm(a) == norm(b)


def resolve(text: str, graph: Graph, *, node_ids=None, stages=None,
            where: str = "", stage_id: str | None = None,
            repeats: dict | None = None, batch_axis: int | None = None) -> str:
    """Substitute every ``{reference}`` in *text*. Unresolvable -> FactError."""

    def sub(m: re.Match) -> str:
        ref = m.group(1).strip()
        head, _, rest = ref.partition(".")
        path = [p for p in rest.split(".") if p] if rest else []

        def shaped(value, dig=None):
            # A DECLARED BATCH AXIS MUST NOT COME BACK THROUGH AN INDEX.
            #
            # `{stage.out_shape}` hides it and `{stage.out_shape[0]}` handed it
            # straight back, because 1 is a true number and nothing objected.
            # That is a claim with a path it does not reach: the spec has said
            # this axis carries nothing, so asking for it is an error rather than
            # a fact. Every OTHER index still addresses the traced shape --
            # renumbering them would silently move what index 1 means.
            if batch_axis is not None and dig is not None:
                axis = _indexed_axis(path)
                if axis is not None:
                    rank = len(dig(path[:-1] + [path[-1].partition("[")[0]]))
                    if _same_axis(axis, batch_axis, rank):
                        raise FactError(
                            f"this spec declares axis {batch_axis} the batch and "
                            f"does not draw it, so {{{ref}}} asks for a number "
                            "the figure has said carries nothing. Use a named "
                            "axis, or drop batch_axis if you need it shown")
            return Graph.fmt(drop_batch(value, path, batch_axis))

        try:
            if head == "model":
                return shaped(graph.model_fact(path), graph.model_fact)
            if head == "stage":
                if node_ids is None:
                    raise FactError("'stage.' used outside a stage")
                if path == ["repeat"]:
                    n = (repeats or {}).get(stage_id)
                    if n is None:
                        raise FactError(
                            "this stage has no verified repeat count")
                    return Graph.fmt(n)
                return shaped(graph.stage_fact(node_ids, path),
                              lambda q: graph.stage_fact(node_ids, q))
            if head.startswith("node:"):
                return shaped(graph.node_fact(head[5:], path),
                              lambda q: graph.node_fact(head[5:], q))
            if head.startswith("stage:"):
                if stages is None or head[6:] not in stages:
                    raise FactError(f"no stage {head[6:]!r}")
                return shaped(graph.stage_fact(stages[head[6:]], path),
                              lambda q: graph.stage_fact(stages[head[6:]], q))
        except FactError as exc:
            raise FactError(f"{where}: {{{ref}}} -> {exc}") from None
        raise FactError(
            f"{where}: {{{ref}}} is not a reference draughtsman understands "
            "(expected model.* / stage.* / node:<id>.* / stage:<id>.*)")

    return REF_RE.sub(sub, text)


# A bare integer in agent-written text is the §4 violation this whole design is
# organised against, so `check` reports them. It cannot be an error -- "1x1 conv"
# and "block 2" are legitimate -- but it is never invisible.
# Digits after a dot are a dotted name (`head.12`), not a measurement. The
# leading digit of a decimal still trips it, which is right: `0.5` is a fact.
BARE_NUMBER_RE = re.compile(r"(?<![\w{.])\d+(?![\w}])")


def bare_numbers(text: str) -> list[str]:
    """Digits in *text* that are not inside a ``{reference}``."""
    masked = REF_RE.sub(lambda m: " " * len(m.group(0)), text)
    return BARE_NUMBER_RE.findall(masked)


def tiles(unit_kinds: list[str], node_kinds: list[str]) -> int | None:
    """How many times *unit_kinds* tiles *node_kinds* exactly, or None.

    THE ONLY THING THAT MAKES `repeat` A FACT. A stage saying "and three more like
    it" is the agent's word for it; this is the graph's. Whole multiples only, and
    every tile identical to the template -- a near-miss is a different structure
    wearing the same label, and drawing it as a repetition would say the model
    does something it does not.
    """
    if not unit_kinds or not node_kinds:
        return None
    n, rem = divmod(len(node_kinds), len(unit_kinds))
    if rem or n < 1:
        return None
    step = len(unit_kinds)
    for i in range(n):
        if node_kinds[i * step:(i + 1) * step] != unit_kinds:
            return None
    return n
