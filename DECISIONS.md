# Decisions — what SPEC.md left open, and three things it had wrong

> **Written 2026-09-01, building the spec.** SPEC.md §8 says *"decide before
> building, not during"*. These are the decisions, and the measurements behind
> them. It also records three places where building found the spec mistaken;
> those are first, because they are the ones that would cost someone a day.
>
> **Not murderboarded** — internal, like the spec it answers.

---

## Corrections to the spec

### 1. The fan-out is not a fork in the graph

SPEC.md §2 and §9 describe `tube` as fanning out "into four difference-of-Gaussian
kernels *in parallel*", and §9 makes drawing that fan-out the acceptance test. The
model does that. **The trace does not record it.**

`_kernels` builds one `(4, 1, 257)` tensor and `forward` performs a single
`aten::_convolution` producing `(1, 4, 600)`. The four kernels are a channel
dimension. The only true fork in the traced graph is `bright` → {conv, cat} — the
bypass.

So the acceptance test cannot be met from topology, and a figure drawn from
topology alone would render the bank as one block: a linear stack, which is
pytorch-graph's defect arrived at from the other direction.

**What was built.** A stage may carry `lanes`, and its `count_from` is a
`{reference}` resolved from `graph.json` — never a number the agent types. The
labels are the agent's, the count is the model's, and `check` fails when they
disagree. A bank of N filters is the common case, not a quirk of this model, so
this is a first-class part of the spec format rather than a patch.

**The spec's author, on reading the result — and this belongs in the record more
than the original §2 text did:**

> *"I wrote that the four kernels 'fan out in parallel' as if that were graph
> topology. It isn't — they're one conv1d with four output channels, so it can't
> be drawn from the trace. Collapsing 26 ops into one bank box with σ₁–σ₄ as rows
> is the honest rendering, and it's a better figure than the parallel lanes I'd
> hand-drawn."*

Note what that concedes and what it does not. The **model** does fan out; §2's
description of the architecture is right. What is wrong is treating that as
something a tracer could hand you. The distinction matters for every model this
tool meets next, because it is the general shape of the problem: **a reader's
"parallel" and a graph's "parallel" are different claims, and only one of them is
in `graph.json`.** Anything that draws only what the trace forks will understate
every filter bank it ever sees.

### 2. §5's coverage check needs a stated node class

`tube` traces to 200 nodes, of which 153 are `prim::Constant`, `ListConstruct`,
`GetAttr`, int/tensor crossings and shape queries. Requiring the agent to assign
all 200 buries the signal in clerical noise, and a `spec.json` nobody can read is
not reviewable in a diff, which is the reason §6 commits it.

**What was built.** `tracing.STRUCTURAL_KINDS` and `tracing.STRUCTURAL_RULE` — the
rule in code, the verdict recorded per node, the counts reported by `trace` and
printed in the `abstract` payload. Coverage then ranges over the 47 substantive
nodes.

This is the one place draughtsman drops a node without the agent saying so, which
is why the rule is conservative and visible rather than a hardcoded skip-list.
Every op that changes a tensor's values stays. All five of pytorch-graph's
omissions are substantive under it, and `tests/test_coverage.py` asserts each one
individually.

### 3. §6's byte-equality test should split in two

§6 wants a staleness test and notes the tension: it drags a system binary into CI
in an estate where *"a skip is what silence looks like when it is being careful."*
There is a second problem it does not name — `torch.jit.trace`'s value names are
not stable across torch releases, so a byte comparison against a freshly traced
model would pin the torch version too.

**What was built.** Two tests, neither of which can skip.

- `test_render.py::test_committed_figure_is_current` renders the committed
  `spec.json` + `graph.json` and asserts byte equality. Pure Python, no torch, no
  graphviz. It fires whenever the abstraction or the renderer moves — it fired
  during this build, on a layout change, which is the behaviour wanted.
- `test_trace.py` traces a fixture model and asserts the facts *semantically*:
  every parameter attributed, shapes on every node, the concat seeing both
  branches. A torch point release that renames `%202` does not turn CI red.

## SPEC.md §8, answered

### 1. Where the agent call lives — **payload in, spec out**

No HTTP anywhere in the package. `draughtsman abstract graph.json` prints the
rules, the reference grammar, the schema and a node table; an agent session or a
person writes `spec.json`. No key handling, and the tool stays usable inside a
coding-agent session, which is the primary internal use.

### 2. Graphviz — **not a dependency, in any form**

Rejected, and more firmly than §8 anticipated. Three reasons, in order of weight:

1. **§4 already forbids graphviz's output as it stands.** Ship no styling, inline
   `style=` rather than `fill=`, classes for the embedding page. Every one of
   those means rewriting the SVG graphviz hands back — so an emitter had to be
   written regardless, and going through `dot` only adds a translation step.
2. **It is the whole of §8.2's tension.** `dot` is a system binary whose output
   moves between versions. Dropping it makes the staleness test unconditional.
3. **The layout is not hard for these figures.** `layout.py` is rank by longest
   path, a dummy per rank a long edge crosses, barycentre ordering, then
   placement — about 200 lines for any DAG, not just this one.

**This is not a return to hand placement.** The objection that started this repo
is coordinates *typed per figure*. These are derived from topology, once.

One deliberate inversion of the textbook: Sugiyama straightens the dummy chains
first, so long edges run level and real nodes bend around them. A reader follows
the main path, so here a real stage is positioned by its real neighbours only, and
the skipping edge bows out of the way. That is what makes `tube`'s spine straight
and its bypass an arc. Down-weighting the dummies is not enough — any weight at
all leaves the chain a few pixels crooked, which `test_layout.py` pins.

### 3. Is the spec hand-editable — **yes, and one thing follows**

`draughtsman abstract` refuses to name an output that already exists without
`--force`. A second agent pass silently eating a human edit would make
"hand-editable" untrue in exactly the way that matters.

Edge declaration order sets lane order top to bottom. That is the one knob a human
has over vertical arrangement, and it is worth more than a better prompt.

### 4. Multiple models per figure — **partly built, and the reason changed**

§8 framed this as *"a diff view between two specs may matter more than six
separate figures"*. That is still true and still unbuilt. What was not
anticipated is why ten models want to be in one place: **not to be compared, but
to be looked at.**

`draughtsman ui examples/` discovers one model per folder and adds a picker and an
`All models` sheet that renders every figure at once. The motivation is that a
layout engine meeting ten architectures will get some of them wrong, and coverage
cannot tell you which: §5 is about operations dropped, not about pictures that do
not read. Ten figures on one screen finds in a glance what ten passing checks
conceal.

The measurement that justified it, on the first ten:

| | |
|---|---|
| coverage | 10/10 pass, every traced node in exactly one place |
| typed facts | one warning in ten specs, and it is `ε ~ N(0, I)` — a distribution's name, which is the case the warning text already excuses |
| skips | U-Net's three nested skips and ResNet's identity route cleanly, no crossings, no struck-through labels |
| **aspect ratio** | **lenet 8.1:1, resnet 8.1:1, transformer 7.8:1** |

That last row is the finding. §2 condemned torchview for a strip; at 8:1 these are
approaching the same defect from the other side, and no check catches it because
nothing is wrong with them except the shape. U-Net's own caption names the second
half of the same limitation — *"a ranked left-to-right layout gets the topology
right and cannot produce the U readers expect."* **Wrapping the spine across rows
is now the highest-value open item**, and it is a layout change, not a spec one.

## The strip, answered

Built after the gallery measured it, and the gallery README reached the same
conclusion independently: *"Layout is rank-by-longest-path with no wrapping, so
depth converts directly into width — the same defect the README criticises
torchview for, arrived at more slowly."*

Two fields, both on the spec rather than on the renderer:

```json
"layout": {"orientation": "lr" | "tb", "wrap": 760}
```

**They belong in the spec because arrangement is judgement.** A flag on `render`
would mean the committed figure came out the shape of whoever last ran the
command, and §6's staleness test would be asserting that accident. Both default
to off and are omitted from `dump()` when defaulted, so adding them changed no
existing spec and moved no existing figure — the ten staleness tests are how that
was checked rather than claimed.

| model | was | wrapped at 760 | top-to-bottom |
|---|---|---|---|
| lenet | 8.1:1 | **2.7:1** | 0.7:1 |
| resnet | 8.1:1 | **1.6:1** | 0.7:1 |
| transformer | 7.8:1 | **3.4:1** | 0.6:1 |
| unet | 6.4:1 | 4.1:1 | 0.6:1 |

Three decisions inside that are worth keeping:

**Orientation is a transpose, not a second layout.** `tb` swaps each box's width
and height on the way in and swaps the coordinates on the way out. One engine,
two readings. A second engine would drift from the first, which is the mistake
this project keeps declining to make — see also the renderer the UI shares and
the coverage count the badge does not recompute.

**A row break is illegal where a long edge is in flight.** U-Net's three skips
span the whole depth, so no boundary is free and it barely wraps — 6.4:1 to
4.1:1 and no further. That is the honest answer. Cutting a skip across a break
would not fix the shape, it would hide where the edge went. U-Net's own caption
already says a ranked layout cannot produce the U readers expect, and this does
not pretend otherwise.

**Rows are balanced, not greedy.** Greedy packing fills each row to the brim and
leaves whatever is left standing alone on the last one; ResNet's first attempt
put `class logits` on a row by itself. The packing runs twice — once to learn the
row count, once at an even share of the width — and keeps the even one if it costs
no extra row.

The wrap connector returns through a gutter to the left margin, drawn as an
orthogonal path with rounded corners rather than a curve: the return is not a
branch, it is the same line continued on the next row, and it should read as a
pipe. Reading direction stays left-to-right on every row, which a serpentine
would not.

`lenet`, `resnet` and `transformer` now carry `"layout": {"wrap": 760}` in their
committed specs — a one-line diff each, and the figures are regenerated. The
other seven are unchanged.

## Beyond §8: where the UI lives

SPEC.md does not mention a UI. It should, because §5 ends by naming a job it
cannot do — *"the names are good, the grouping is natural, the figure is
legible… those need a human"* — and leaves that human a JSON file and a
rasteriser.

`draughtsman ui` is a stdlib HTTP server on localhost and one page of vanilla
JavaScript. No dependencies, no build step, no network: a CDN font that failed to
load would resize every box the layout had already measured, and a test asserts
the page reaches nothing.

**The decision that shaped it: there is exactly one renderer.** Every picture the
UI shows is produced by `render()` — the same function the CLI calls and the same
one the staleness test asserts against. Re-implementing layout and render in
JavaScript would have been quicker to build and would have shipped a second,
divergent truth: the figure judged in the browser would not be the figure
committed to the repo, and §6's byte-equality test would be guarding a picture
nobody had looked at. `Save` therefore writes `spec.json` *and* `figure.svg`
together, and `test_ui.py` asserts the saved figure is byte-identical to the
CLI's.

The corollary is that the UI cannot be a shareable static page. That is the right
trade for a tool whose primary use is a person at the repo they are editing, and
a read-only page showing the committed SVG remains available later without any of
the drift.

**One place counts coverage.** The first cut of the UI derived its own coverage
number in JavaScript, and it read `48/47` — the numerator counting the model input
that a stage names, the denominator counting only traced nodes. It was cosmetic
here, and the objection to it was not:

> *"That indicator is the entire safety argument for letting an agent into the
> pipeline. Worth a look before it's trusted."*

Correct, and the shallow fix was insufficient. Counting distinct owned ids gives
the right total *and* would have reported `47/47` with a node sitting in two
stages — a §5 violation reading as success, with only the badge's colour
dissenting. So `check.Counts` is now the single implementation: it distinguishes
*placed in exactly one place* from *placed*, reports duplicates and unplaced nodes
separately, names the untraced model inputs rather than folding them in, and
`summary()` renders the failure into the number itself — `46/47 in exactly one
place · 1 in two`. The CLI report and the UI badge both display it. Neither
computes it.

**Edits land on disk.** SPEC.md §8.3 asks that a human edit survive regeneration.
A review surface that cannot save is a surface whose work is thrown away, so the
UI writes the files, and the raw-JSON escape hatch is always there because
`spec.json` staying hand-editable matters more than the editor being complete.

## Two things measured that the spec should carry

**Attribution needs both the module path and the source range.** Of `tube`'s 47
substantive nodes, 13 have a `scopeName` — exactly the registered `nn.Module`
children, which is all pytorch-graph could ever see. All 47 have a `sourceRange`.
Neither field alone attributes the graph; `graph.json` carries both.

**`torch.jit.trace` is deprecated on Python 3.14.** Tracing on 3.14.5 emits
`DeprecationWarning: torch.jit.trace_method is not supported in Python 3.14+ and
may break. Please switch to torch.compile or torch.export.` It works today and
produces everything above. But SPEC.md §3 rules out `torch.export` on measurement,
and this is torch telling us the other road is closing. **Nothing to do now; do
not be surprised later.** The trace layer is one module behind a stable
`graph.json` contract, which is the right shape for that risk.
