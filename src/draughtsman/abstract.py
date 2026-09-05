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

5. NAME EVERY NUMBER YOU DRAW. A shape is only a fact to a reader who knows what
   its axes count. `1x30x600` under the label "cells x frames" is three numbers
   and two names, and the reader is one short at the first box. Set `batch_axis`
   when the model has one and the figure will stop drawing it -- the batch axis
   is 1 throughout an architecture figure and carries nothing -- then label the
   axes that remain. `check` refuses the declaration wherever the hidden number
   is not 1, because an axis that is not 1 is carrying information. THE CASE TO
   GET RIGHT: a model that reshapes to fold a real axis INTO the batch. `tube`
   traces [30, 1, 600] midway -- that leading 30 is CELLS, not a batch of 30 --
   and a figure that dropped it would delete the cell count and say nothing. If
   any shape you draw has something other than 1 there, do not declare the axis.
   An indexed reference to a declared batch axis (`{stage.out_shape[0]}`) is an
   error; every other index still addresses the TRACED shape, so
   `{stage.out_shape[1]}` is the same axis it was before you declared.
   A GLYPH'S `axes` ARE DIFFERENT AND YOU SHOULD WRITE THEM NEGATIVE. They index
   the shape AS DRAWN, so declaring `batch_axis` shifts them by one: `[1, 2]` on
   a four-axis shape means (channels, height) and then means (height, width),
   with the labels still claiming the first and nothing erroring. `[-3, -2]`
   names the same two axes either way, because hiding a LEADING axis leaves the
   trailing positions where they were. WATCH FOR AN
   AXIS THAT CHANGES MEANING: in a model that reduces over a spatial or ROI axis
   and then convolves, the same POSITION counts something different before and
   after, and only your labels can say so.

6. A TRACED CONSTANT MAY BE AN INITIALISATION. A trace watches one instantiation
   and cannot see which of its numbers would survive training. bugarach's `tube`
   max-pools at `2 * kmin + 1` where kmin comes off a TRAINED parameter: 3 at
   init, 9-15 once trained. draughtsman drew "max-pool, width 3" and it was true
   of an untrained model and of nothing else. Where the payload reports a BAKE
   HAZARD, quoting a `constants.*` reference is an error until the spec's
   top-level `constants` block says why THAT one is architectural — a kernel
   size, a dilation schedule and a stride usually are; anything computed from a
   parameter is not. If you cannot tell, do not put the number in the figure.

6. A QUANTITY A READER COMPARES ACROSS STAGES WANTS A BAR, NOT DIGITS. `meters`
   draws one: `value` is a {reference} like any other, `label` is the name AND
   the series. Every meter sharing a label is scaled together across the whole
   figure, full bar = the largest value, empty = zero, and the legend states
   what full means. Use it for what a reader would otherwise compare in their
   head -- parameters per stage, or a width that shrinks down the network. Do
   not use it for a quantity only one stage has: that bar is full by definition
   and `check` will say so.

7. A GLYPH AND A METER ON THE SAME STAGE COMPETE, AND THE GLYPH LOSES. A meter
   is a row, and adding one widens the box and pulls the eye along it; the glyph
   is a shape, read at a glance, and it stops reading. Measured on U-Net: with a
   params meter added the hourglass its glyphs draw became hard to see. Use one
   or the other per stage unless you have looked at both together and want them.

8. THE TENSOR ITSELF CAN BE DRAWN. `glyph` puts a rectangle in the box: one axis
   of a shape as its height, another as its width, on a scale shared by the whole
   figure. BOTH AXES MUST COME FROM THE ONE `of` REFERENCE -- the eye reads a
   rectangle's area whether you meant it to or not, and two axes of one tensor
   multiply to something real while two unrelated numbers do not. `scale` is
   "sqrt" by default because channel counts span three orders of magnitude in
   real models and a linear edge would put the smallest rectangle under a pixel;
   use "linear" when the figure's range is narrow enough, and the legend will say
   which you chose. Every glyph in a figure must label its axes the same way.

9. A REPEATED BLOCK IS COUNTED, NOT CLAIMED. Deep models are one block over and
   over, and a stage whose name says "and three more like it" has put a number in
   the figure that came from you. `repeat` fixes that the way `lanes` does: you
   name the TEMPLATE — the ordered stage ids that draw ONE unit — and draughtsman
   tiles that unit's operation sequence against this stage's nodes and supplies
   the count. Write `{stage.repeat}` where the number goes. A template that does
   not tile EXACTLY is an error, not a rounding: regroup until it does, or drop
   the claim. If a stage will not tile, the usual cause is that it holds
   something that enters ONCE — a mask, an initial state — which belongs
   upstream, not in one of N identical blocks.

9. A SMALL AXIS CAN BE COUNTED INSTEAD OF COMPARED. `glyph` defaults to
   `"style": "block"` — one rectangle, scaled against the figure, which answers
   "bigger or smaller than that one". `"style": "marks"` answers a different
   question: HOW MANY. `axes[0]` becomes rows and `axes[1]` columns, so a 3x5
   tensor draws three rows of five objects a reader can literally count, and a
   single countable axis draws a column of that many.

   Counting stops working around thirty. An axis past the limit is NOT drawn as
   marks — it becomes a solid bar with its number beside it, so `1x30x600` is
   thirty marks down the page with `600` written under them. That is automatic
   and you cannot override it: marks nobody can count are a picture pretending to
   be a number.

   Use marks where the count is the point — channels, filters, heads, scales —
   and block where the question is relative size. `axes` indexes the shape AS
   DRAWN, so if the spec declares a `batch_axis` the hidden axis is not there to
   be indexed.

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
  {stage.repeat}                 verified copies of this stage's `repeat` template
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
      "note": "<optional: kept in the spec, never drawn. Why this grouping is"
              " the right one, or what a reader should not conclude from it>",
      "lanes": {"count_from": "{node:n0126.out_shape[1]}",
                "labels": ["<one name per lane>"]},
      "meters": [{"value": "{stage.params}", "label": "params"}],
      "repeat": {"template": ["<stage id>", "<stage id>"]},
      "glyph": {"of": "{stage.out_shape}", "axes": [1, 2],
                "labels": ["channels", "frames"], "scale": "sqrt",
                "style": "block|marks"},
      "chrome": "box|none"
    }
  ],
  "edges": [
    {"from": "<stage id>", "to": "<stage id>",
     "label": "<optional, e.g. 'bypass'>", "style": "solid|dashed",
     "untraced": "<only if graph.json has no path here: why you drew it anyway>"}
  ],
  "batch_axis": 0,
  "elided": [{"nodes": ["n0017"], "reason": "<why a reader does not need this>"}],
  "constants": {"n0149.constants.dilation": "<why this traced constant is an"
                " architectural quantity and not an initialisation>"},
  "layout": {"orientation": "lr|tb", "wrap": 760, "legend": false,
             "chrome": "box|none"},
  "output": {"width": "6in", "min_type": "6pt"},
  "caption": "<optional one line>"
}

Edge declaration order sets lane order top to bottom, so declare the branch you
want uppermost first.
"""

ARRANGEMENT = """\
ARRANGEMENT — `layout`, and why you have to think about it.

Stages are ranked by depth and laid left to right, so a deep model turns its
depth directly into width. Left alone, a nine-stage figure comes out around 8:1 —
a ribbon a page cannot show and a reader cannot follow. That is the exact defect
this tool exists to beat: it is what torchview produced, and arriving at it more
slowly is not an improvement.

Nothing catches this for you. Coverage is about operations dropped, not about
pictures that do not read, so a figure can be 8:1 with every check green.

  "wrap": 760          break the spine into rows at that width. For anything
                       past about six stages in a line, set it. A row break is
                       refused where a long edge is still in flight, so a model
                       webbed with skips will wrap little or not at all — that
                       is the tool declining to cut an edge, not a failure.
  "orientation": "tb"  run the figure top to bottom instead. Better for a deep
                       stack in a single column, and for a page taller than wide.
  "legend": true       a key naming each colour family, with its share of the
                       traced ops and parameters counted off graph.json.
  "chrome": "none"     drop the box around every stage and let the TENSOR be the
                       stage: the glyph is drawn large, the name floats over it,
                       the detail sits underneath.
                       A box is the right container when a stage's content is
                       WORDS; it is the wrong one when the content is a picture
                       of the tensor, because then it is a rectangle drawn
                       around a rectangle and the eye settles on the bigger one.
                       With "sheets" this is usually what you want.

                       SAY IT PER STAGE WHERE THE FIGURE IS MIXED, which most
                       are. A stage may carry its own `"chrome": "box"` or
                       `"chrome": "none"` and it wins over the figure's; a stage
                       that says nothing takes the figure's. The rule is about a
                       stage, so answer it stage by stage: glyph stages bare,
                       word stages boxed. Setting it once at the figure and
                       leaving a stage with nothing to draw makes a bare label
                       floating between drawings, which is the other half of the
                       same mistake. `check` warns when a glyph is left in a box.

These default to off and all are judgement, which is why they live here rather
than in a render flag: the committed spec has to produce the same figure on any
machine.

HOW BIG WILL THIS BE ON THE PAGE? Set `output` and the figure is solved for it.

  "width": "6in"       the width it will be PRINTED at — a journal column is
                       about 3.5in, a double column about 6 to 7in. The rendered
                       SVG then declares that size instead of a pixel count, so a
                       page places it correctly instead of scaling it to fit.
  "min_type": "6pt"    the floor the smallest label must clear at that size.

Set it whenever you know where the figure is going, and it changes what layout
does: the spine wraps into more rows until the figure fits the budget the two
numbers imply. THE TYPE IS NEVER SHRUNK — a figure that fits by shrinking its
labels has solved a different problem. If wrapping cannot get there, `check`
refuses the spec and tells you the width to aim for.

This matters more than it sounds. Measured across this gallery before it existed:
scaled to a 6in double column the smallest type landed between 2.49pt and 5.25pt,
and not one figure cleared 6pt. Every number in a figure can be correct and the
figure still be unreadable at the size anybody sees it.
"""


def payload(graph: Graph, *, out_path: str = "spec.json") -> str:
    """The prompt, the node table, and where to put the answer."""
    doc = graph.doc
    model = doc["model"]
    cls = doc["classification"]

    shapes = model.get("input_shapes") or [model["input_shape"]]
    described = ", ".join(_shape(s) for s in shapes)
    lines = [RULES, "", GRAMMAR, "", SCHEMA, "", ARRANGEMENT, "", "-" * 78, "",
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
