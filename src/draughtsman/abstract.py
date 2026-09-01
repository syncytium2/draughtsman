"""Stage 2 — abstract. Judgement only, and no API key.

SPEC.md §8.1 is decided: payload in, spec out. This module prints a prompt and a
node table; a coding-agent session or a person answers it and writes `spec.json`.
There is no HTTP call anywhere in draughtsman, which keeps the tool usable inside
an agent session — the primary internal use — and keeps the API optional rather
than load-bearing.

The payload's whole job is to make SPEC.md §4's rule operational: the agent writes
groupings, human names and topology, and cannot write a number even if it wants
to, because the schema has nowhere to put one.
"""

from __future__ import annotations

from draughtsman.facts import Graph

RULES = """\
You are doing stage 2 of draughtsman: turning a traced computation graph into a
LAYOUT SPEC for a figure a person can read. Read these four rules first.

1. YOU SUPPLY NO FACTS. Not a parameter count, not a shape, not a kernel width,
   not a dilation, not a channel count. Every quantity in the figure is looked up
   from graph.json at render time. Where you want a number in a label, write a
   {reference} (grammar below) and the renderer fills it in. If you type a number
   the check reports it.

2. YOU SUPPLY GROUPINGS, NAMES AND TOPOLOGY. Which node ids collapse into one
   stage, what a reader should call that stage, what kind it is (that picks a
   colour), and how the stages connect — including where the computation forks
   and where it rejoins.

3. EVERY SUBSTANTIVE NODE GOES IN EXACTLY ONE PLACE. One stage, or one `elided`
   entry with a reason. Not zero, not two. A node you cannot place is a node you
   have not understood; elide it deliberately rather than dropping it, because
   silently losing whole stages is the exact failure this tool exists to prevent.

4. PARALLELISM IS OFTEN NOT A FORK IN THE GRAPH. A bank of N filters is usually
   ONE convolution with N output channels, not N edges. When a stage should read
   as N parallel branches, give it `lanes` — the count is a {reference} to a
   fact, the labels are yours. Drawing such a stage as a single block is how a
   figure ends up saying "linear stack" about a model that fans out.

5. A TRACED CONSTANT MAY BE AN INITIALISATION. A trace watches one instantiation
   and cannot see which of its numbers would survive training. bugarach's `tube`
   max-pools at `2 * kmin + 1` where kmin comes off a TRAINED parameter: 3 at
   init, 9-15 once trained. draughtsman drew "max-pool, width 3" and it was true
   of an untrained model and of nothing else. Where the payload reports a BAKE
   HAZARD, quoting a `constants.*` reference is an error until the spec's
   top-level `constants` block says why THAT one is architectural — a kernel
   size, a dilation schedule and a stride usually are; anything computed from a
   parameter is not. If you cannot tell, do not put the number in the figure.

Aim for six to twelve stages. Fewer and the figure says nothing; more and it is
the trace again, which is already unreadable.
"""

GRAMMAR = """\
REFERENCE GRAMMAR — resolved against graph.json at render time.

  {model.params}                 the model's total parameter count
  {model.input_shape}            e.g. 1x30x600 — ONLY on single-input models
  {model.input_shapes[0]}        one input of a model that takes several
  {stage.out_shape}              output shape of the node this stage exits through
  {stage.out_shape[1]}           one axis of it — channels, here
  {stage.params}                 parameters summed over this stage's nodes
  {stage.nodes}                  how many nodes this stage collapses
  {node:n0031.out_shape}         any field of any node, by id
  {node:n0031.constants.dilation}
  {node:n0031.params}
  {stage:head.params}            another stage, by id
"""

SCHEMA = """\
WRITE THIS, AND NOTHING ELSE — one JSON object:

{
  "draughtsman": "0",
  "graph": "graph.json",
  "title": "<the model's name>",
  "subtitle": "<optional, e.g. '{model.params} parameters'>",
  "stages": [
    {
      "id": "<short slug>",
      "name": "<what a reader should call this>",
      "kind": "input|pool|reduce|kernel|conv|stack|concat|output|op",
      "nodes": ["n0021", "n0031"],
      "detail": ["{stage.out_shape}", "{stage.params} params"],
      "lanes": {"count_from": "{node:n0126.out_shape[1]}",
                "labels": ["<one name per lane>"]}
    }
  ],
  "edges": [
    {"from": "<stage id>", "to": "<stage id>",
     "label": "<optional, e.g. 'bypass'>", "style": "solid|dashed"}
  ],
  "elided": [{"nodes": ["n0017"], "reason": "<why a reader does not need this>"}],
  "constants": {"n0149.constants.dilation": "<why this traced constant is an"
                " architectural quantity and not an initialisation>"},
  "caption": "<optional one line>"
}

Edge declaration order sets lane order top to bottom, so declare the branch you
want uppermost first.
"""


def payload(graph: Graph, *, out_path: str = "spec.json") -> str:
    """The prompt, the node table, and where to put the answer."""
    doc = graph.doc
    model = doc["model"]
    cls = doc["classification"]

    shapes = model.get("input_shapes") or [model["input_shape"]]
    described = ", ".join(_shape(s) for s in shapes)
    lines = [RULES, "", GRAMMAR, "", SCHEMA, "", "-" * 78, "",
             f"MODEL: {model['target']}",
             f"  input{'s' if len(shapes) > 1 else ''} {described}, "
             f"{model['params']} parameters",
             f"  traced by {doc['tracer']['backend']} "
             f"(torch {doc['tracer']['torch']})",
             f"  {cls['nodes_total']} nodes traced, {cls['nodes_structural']} "
             f"structural and already set aside, "
             f"{cls['nodes_substantive']} substantive and yours to place",
             ""]

    if doc.get("hazards"):
        lines.append("BAKE HAZARDS — the tracer converted a tensor to a Python")
        lines.append("value here, so a constant recorded downstream may be an")
        lines.append("initialisation. See rule 5; the data flow is severed and")
        lines.append("graph.json cannot tell you which constants are affected.")
        for h in doc["hazards"]:
            tag = "  (inside torch — how a stock module was built)" \
                if h.get("internal") else "  <- THE MODEL'S OWN CODE"
            lines.append(f"  {h['file']}:{h['line']}  {h['kind']}{tag}")
        lines.append("")

    if doc.get("inputs"):
        lines.append("MODEL INPUTS (addressable, not counted in coverage):")
        for rec in doc["inputs"]:
            lines.append(f"  {rec['id']:<8} {_shape(rec['shape'])}")
        lines.append("")

    lines.append("SUBSTANTIVE NODES — every one of these must be placed:")
    lines.append(f"  {'id':<8} {'op':<22} {'out shape':<16} {'params':>6}  "
                 "from -> where")
    for n in doc["nodes"]:
        src = n.get("source") or {}
        where = n.get("module") or (
            f"{src.get('file')}:{src.get('line')}" if src else "")
        if src.get("internal") and n.get("module"):
            where = n["module"]
        consts = _interesting(n.get("constants") or {})
        lines.append(
            f"  {n['id']:<8} {n['kind'].replace('aten::', ''):<22} "
            f"{_shape(n.get('out_shape')):<16} {n.get('params', 0):>6}  "
            f"{','.join(n.get('tensor_inputs') or []) or '-'} -> {where}"
            + (f"   [{consts}]" if consts else "")
        )

    if doc.get("outputs"):
        lines.append("")
        lines.append("MODEL OUTPUT: " + ", ".join(
            f"{o['producer']} {_shape(o['shape'])}" for o in doc["outputs"]))

    lines += ["", "-" * 78, "",
              f"Write the JSON object to {out_path}. Then run:",
              f"  draughtsman check {out_path} graph.json",
              "and fix what it reports before rendering."]
    return "\n".join(lines) + "\n"


def _shape(shape) -> str:
    if not shape:
        return "scalar" if shape == [] else "-"
    return "×".join(str(s) for s in shape)


_NOISE = {"benchmark", "deterministic", "cudnn_enabled", "allow_tf32",
          "transposed", "output_padding", "ceil_mode", "arg1"}


def _interesting(consts: dict) -> str:
    keep = {k: v for k, v in consts.items()
            if k not in _NOISE and v not in (False, None)}
    return " ".join(f"{k}={_shape(v) if isinstance(v, list) else v}"
                    for k, v in keep.items())
