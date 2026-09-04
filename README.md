# draughtsman

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22286341.svg)](https://doi.org/10.5281/zenodo.22286341)

**Readable architecture diagrams for PyTorch models.** The tracer supplies the
facts, an agent supplies the abstraction, and a coverage check proves nothing was
silently dropped.

> **Status: the three stages work end to end on the model that prompted them.**
> [`SPEC.md`](https://github.com/syncytium2/draughtsman/blob/main/SPEC.md) carries the design, the measurements behind it, and the
> failure it exists to prevent. [`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md) answers what the
> spec left open and records three places building found it mistaken — read that
> second, and before changing the trace layer.

## Why this exists

A 1,149-parameter model was drawn by five existing tools. Every one of them
failed, and they failed in two families:

| tool | what it did |
|---|---|
| **torchview** | Traced the true op graph. **Correct** — and forty nodes of `exp`/`clamp`/`div` in a strip one pixel tall at page width. |
| **pytorch-graph** (`research_paper` style) | Clean, styled, **and wrong** — see below. |
| **visualtorch** | 993 × **13 pixels**. Its renderers scale block height by channel count; this model has ≤ 8. |
| **nn-SVG** | Browser-only, no API. FCNN / LeNet / AlexNet styles, all linear stacks, aimed at 2D image CNNs. No branching. |
| **Model Explorer** (Google AI Edge) | Ingests PyTorch *ExportedProgram*. `torch.export` **cannot export this model** — data-dependent control flow. Doubly unavailable, and it is an interactive debugging viewer rather than a figure generator. |

**The pytorch-graph result is the one that matters.** It produced a clean
publication-styled figure of `head.0` … `head.12` and silently omitted the
max-pool, the mean over cells, the four difference-of-Gaussian kernels, the
bypass and the concat — which is to say, the architecture. Every shape field read
`Input: ()`. The summary box asserted *"Output Classes: Variable · End-to-end
trainable · GPU compatible."*

![torchview's output: a horizontal strip of about forty nodes, one pixel tall at page width, individual operations unreadable](https://raw.githubusercontent.com/syncytium2/draughtsman/main/examples/2-torchview-traced.png)

*torchview, 2419 × 123 px. **Correct and unreadable** — every operation is there,
including forty nodes of kernel construction, and none of it can be seen.*

![pytorch-graph's output: a clean vertically-stacked publication-styled figure of thirteen numbered layers, with empty shape fields](https://raw.githubusercontent.com/syncytium2/draughtsman/main/examples/4-pytorchgraph-paper.png)

*pytorch-graph, `research_paper` style. **Readable and wrong** — a tidy thirteen-layer
stack that omits the pooling, the mean, all four kernels, the bypass and the concat.
Every shape field reads `Input: ()`. This is the failure the repository is named for.*

It enumerates registered `nn.Module` children. That model's architecture lives in
`forward()`. So the tool drew a plain thirteen-layer conv stack and called it the
model, and a reader would come away confident and wrong.


## The gap, stated once

Tools either **trace the computation graph** — complete, unreadable — or
**enumerate registered modules** — readable, and blind to everything a `forward()`
does. Neither can decide *which operations matter*, because that is a judgement
about what a reader needs, not a fact about the graph.

That judgement is the only missing piece, and it is now cheap. Tony, 2026-09-01:

> *"except now we have very powerful coding agents. i'm fine with putting an agent
> in there for internal use."*

So: trace for the facts, agent for the abstraction, and a mechanical check that
the abstraction did not lose anything — because losing the architecture quietly is
exactly what the existing tools do.


## What it produces

![A draughtsman figure of a ResNet: nine named stages wrapped across three rows, with the residual identity drawn as a dashed arc around one opened-up block](https://raw.githubusercontent.com/syncytium2/draughtsman/main/examples/gallery/resnet/figure.svg)

Nine stages over 52 traced operations. Every quantity — `464 params`, `kernel 3`,
`16×32×32`, `10 classes` — is looked up from `graph.json` by node id at render
time; none of it is typed into the spec. The residual identity is a dashed arc
because it is a real fork in the traced graph. The other five blocks are
collapsed into two boxes, and the caption says so rather than letting the figure
imply the model is nine layers deep.

That figure and one for every other model are in [`examples/`](https://github.com/syncytium2/draughtsman/blob/main/examples/), each with the
`graph.json` it was measured from and the `spec.json` that arranged it.

## Running it

```
export PYTHONPATH=examples/gallery                # the models are written out here
draughtsman trace    models:build_resnet --input-shape 1,3,32,32 -o graph.json
draughtsman abstract graph.json -o spec.json      # prints the prompt; an agent answers it
draughtsman check    spec.json graph.json         # every traced node in exactly one stage
draughtsman render   spec.json -o figure.svg
draughtsman ui       examples/                    # review every model in a browser
```

That runs against a clone with nothing else installed, and it reproduces the
committed `graph.json` — byte for byte on the torch it was traced with, and fact
for fact otherwise. The facts are the durable claim, and
[`tests/test_reproduces.py`](https://github.com/syncytium2/draughtsman/blob/main/tests/test_reproduces.py) asserts them
by re-deriving the trace rather than by comparing bytes, because `torch.jit.trace`'s
value names are not stable across releases
([`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md) correction 3).

**What is measured is one torch at a time.** CI installs the current CPU wheel
across four Python versions, so that assertion is exercised against whichever
torch that is on the day, not across a range — a matrix of one, four times over.
"On any torch" is the reason the comparison is semantic instead of byte-exact and
it is the design intent; it is not something this repository has yet measured, and
the sentence used to claim it was. Earning it means pinning two or three torch
minors in the workflow matrix, which is not a free change: the minors do not span
3.10 to 3.13 uniformly, so the matrix has to exclude as well as include.

Every model in
[`examples/gallery/`](https://github.com/syncytium2/draughtsman/blob/main/examples/gallery/) is written out in full in this repo — no
torchvision, no downloads, no pinned third-party version — so the whole pipeline
reproduces from here.

## Installing

```
pip install -e .                  # check, render, ui — no dependencies at all
pip install -e ".[trace]"         # ... and read a PyTorch model
pip install -e ".[dev]"           # ... and run the tests
```

On PyPI this is `draughtsman-nn`, and everything else — the import, the
`draughtsman` command, this repository — keeps the unabbreviated spelling. PyPI's
`draughtsman` is an unrelated API Blueprint parser last released in 2020, so the
name had to move; nothing a reader types does. It is not published yet, so the
lines above are the only way in today. `tests/test_dist_name.py` holds the three
files that state the name to each other.

Runs on Python 3.10 through 3.13, and CI runs the whole suite on every one of
them — a range stated in three files and checked in `tests/test_versions.py`, so
the floor in `pyproject.toml`, the matrix in the workflow and this sentence
cannot drift apart.

**The first line installs nothing but draughtsman.** No torch, no graphviz, no
system binary, no CDN at runtime — the layout engine and the SVG emitter are in
this repo. A machine that only draws figures needs none of it, which is why the
staleness test in CI can be an unconditional assertion rather than one that skips
when a tool is missing.

That is checked rather than claimed: `pip install -e .` into an empty virtualenv,
then `draughtsman render examples/gallery/resnet/spec.json`, produces a file
byte-identical to the committed `figure.svg`. `trace` is the only verb that wants
torch, and without it says so in a sentence rather than a stack trace.

See [`examples/tube/`](https://github.com/syncytium2/draughtsman/blob/main/examples/tube/) for the result on the model below, and for
where every number in it comes from.


## The three stages, and why the split is the design

```
  model ──▶ [1 TRACE] ──▶ graph.json ──▶ [2 ABSTRACT] ──▶ spec.json ──▶ [3 RENDER] ──▶ figure.svg
             facts          facts          judgement        judgement      deterministic
             (torch)                       (agent)          (committed)
```

**The agent never supplies a fact.** Not a parameter count, not a shape, not a
kernel width. It supplies groupings, human names and topology. Where the figure
wants a number, `spec.json` carries a reference — `{stage.params}`,
`{node:n0149.constants.dilation}` — and the renderer looks it up in `graph.json`
by node id. An agent that hallucinates a parameter count produces exactly the
confident-and-wrong figure pytorch-graph produced, and coverage would not catch it
because every node would still be covered.

**Every traced node must be accounted for in exactly one stage.** Not zero, not
two. A node may be marked `elided` explicitly, with a reason — a decision in a
diff, not a silent loss. It is precisely what pytorch-graph lacked — and it is the
FIRST of the assertions that make an agent safe here, not the only one. Four more
things have since been caught being confidently wrong while coverage was green:
see [`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md) correction 5.

Coverage passing says nothing about whether the figure is any good. `check` says
so in its own output, so a green check is never read as a good figure.

## `draughtsman ui` — the part coverage cannot do

The check ends by naming what it does not verify: whether the names are good, the
grouping is natural, the figure legible. That is a person's job, and `ui` is where
they do it — the figure, the coverage panel, and every traced node in one place,
with the grouping editable and the picture redrawing as you change it.

```
draughtsman ui examples/tube/spec.json     # one model
draughtsman ui examples/                   # every model under it
```

Point it at a directory and it finds one model per folder — a `graph.json` with
its `spec.json` beside it, which is the convention `examples/tube/` already
follows. **`All models` renders every figure onto one sheet**, each with its
coverage state and aspect ratio, and clicking one opens it for editing. Unsaved
edits survive switching, and a model carrying them is marked in both the picker
and the sheet.

That sheet is a visual regression test. A layout defect in one model of many does
not announce itself in a passing check — coverage is about what was *dropped*, not
about what the picture looks like — and opening a tab per model to find it is how it stays
unfound. The half a machine can check is parametrised in `tests/test_render.py`,
so every committed model has its coverage and its figure's freshness asserted;
adding a folder adds a test.

Standard library only; it binds to localhost and writes the two paths you named.

**Every picture it shows comes from the same `render()` the CLI calls.** A
browser-side re-implementation would have been quicker and would have meant the
figure you judged was never the figure that shipped — so `Save` writes `spec.json`
and `figure.svg` together, byte-identical to the CLI's, and a test asserts it.

**Save writes into the repo; Export takes a copy out.** `Export ▾` (⌘E) gives you
Copy SVG, Download SVG, and PNG at 1×, 2× or 4×. The SVG it hands over is the
exact string `render()` produced — the same bytes `Save` writes — rather than a
re-serialisation of what the browser is displaying. The PNG is rasterised from
that, on a white ground, because the figure ships no background of its own and a
PNG has no page to inherit one from. For print or LaTeX, prefer the SVG.

If coverage is failing the menu says so before you export. Exporting anyway is
allowed — you may want it mid-edit — but it is never silent, because shipping a
figure that omits operations the model performs is the exact failure in §2.

**Arrangement is part of the judgement, so it lives in the spec.** A `layout`
field takes `orientation` (`lr` across, `tb` down) and `wrap` (break the spine
into rows at this width); the header carries a control for each, with the figure's
size and aspect ratio beside them. Depth otherwise converts directly into width —
LeNet, ResNet and the transformer all rendered as 8:1 ribbons, which is the defect
this README criticises torchview for, arrived at more slowly. Wrapped, they are
2.7:1, 1.6:1 and 3.4:1.

A row break is refused where a long edge is still in flight, so U-Net — three
skips spanning its whole depth — barely wraps. That is the honest answer rather
than a break drawn through a skip.

Click a stage in the figure to select it; click nodes in the table to move them
into it. Coverage updates as you go, so a regrouping that drops an operation says
so before you save rather than after. The spec is a small readable document and
the UI never becomes the only way to edit it: there is a raw-JSON escape hatch,
and hand edits survive, because `abstract` refuses to overwrite a spec without
`--force`.

## Two things this got wrong, and how they were caught

The value of this repository is not that its checks pass. It is that twice they
passed while the thing they checked was wrong, and both times something else
caught it. Both are worth a minute before you trust any figure it draws.

**A check that ran where it could not see.** `tests/test_claims.py` resolves each
claim against the branches it can find. GitHub Actions checks out shallow and
single-branch by default, so on CI every branch a claim named "did not exist" and
the board went red — for a reason that had nothing to do with the board. The
green runs before it were worse than the red one: the check could not see what it
was checking, and reported that as a failure of the subject rather than of
itself. **A gate has to distinguish *checked and wrong* from *could not check*,
and this one could not.** The fix is `fetch-depth: 0` and it is three characters;
the finding is that nothing would have told us. See [`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md)
correction 8.

**A figure that disagreed with its own spec, silently.** `check` validated a
glyph's `scale` against the two legal values and raised on anything else. It
validated the `style` field against nothing at all — so a spec asking for a style
that did not exist, or carrying a typo, rendered as the default block and passed
every assertion. The figure was not the spec, and the spec was not wrong enough
for anything to notice. Found by reading the schema, not by a test. The check now
names both valid styles and says what goes wrong: *an unknown style would be
drawn as a block, and the figure would not be the spec.*

Nine such corrections are written up in [`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md), and they are one
shape: **a quantity with a single correct value, computed in two places and
allowed to disagree, or computed in one place and never checked.** Coverage
cannot see any of them, because coverage answers a different question — was an
operation dropped.

## The page

[`index.html`](https://github.com/syncytium2/draughtsman/blob/main/index.html) is a
one-page site, served by GitHub Pages from this branch. It is 4KB and points at the
committed figures in `examples/` rather than embedding copies, so it cannot drift from
what the tool produces — change a figure and the page changes with it.

## Checking a figure will be legible

`check` refuses a spec whose figure would print under its stated type floor.
[`tools/measure_type.py`](https://github.com/syncytium2/draughtsman/blob/main/tools/measure_type.py)
answers the same question about a rendered file, at any width — a journal column, a
slide, a web page:

```
tools/measure_type.py --print 6in --floor 6pt examples/gallery/*/figure.svg
```

It reports `unit_size x display_width / viewBox_width` and exits 1 below the floor, so it
works as a gate. Three inputs decide that number and they are easy to get wrong together;
this repository got it wrong three different ways in one evening, and every one was
invisible to the eye and obvious to arithmetic. It refuses what it cannot measure — a
PNG, a missing viewBox, a relative font size — rather than reporting those as clean.

## Working on this

Several Claude Code sessions have worked this repository at once.
[`CLAIMS.md`](https://github.com/syncytium2/draughtsman/blob/main/CLAIMS.md) records who holds which files and what is queued, and
`tests/test_claims.py` fails when it goes stale — a claim board nothing checks is
decoration, which is [`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md) correction 5 applied to the
sessions themselves.

## Licence

BSD-3-Clause.
