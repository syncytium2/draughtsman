# `tube` — the first example, and SPEC.md §9's acceptance test

`figure.svg` is what draughtsman draws for bugarach's `tube`: a 1,149-parameter
1-D coordinated-event detector. It is the model that broke all five tools in
[`../README.md`](../README.md).

**The acceptance test is whether the figure shows the fan-out to four kernels, the
bypass, and the concat.** It does. Every tool but the hand-laid original failed
that, and `../../tests/test_render.py` asserts each of the three against the
committed SVG so it cannot quietly stop being true.

## Provenance

| file | how |
|---|---|
| `graph.json` | `draughtsman trace bugarach.learn.nets.tube:build_tube --input-shape 1,30,600 -o graph.json`, against bugarach `8cf06f6` on torch 2.13.0 |
| `spec.json` | stage 2 — written from the `draughtsman abstract graph.json` payload in a Claude Code session, 2026-09-01 |
| `figure.svg` | `draughtsman render spec.json -o figure.svg` |

`graph.json` is committed because regenerating it needs bugarach installed, and
this repo does not depend on bugarach. **So the staleness test runs on the
committed graph, not on a fresh trace** — it catches a spec or renderer change,
and it cannot catch a change to bugarach's model. Regenerate by hand after one:

```
draughtsman trace bugarach.learn.nets.tube:build_tube --input-shape 1,30,600 \
    -o examples/tube/graph.json
draughtsman check  examples/tube/spec.json examples/tube/graph.json
draughtsman render examples/tube/spec.json -o examples/tube/figure.svg
```

The `check` in the middle is the point of the sequence: if the model gained an
operation, the spec no longer covers every node and it fails there rather than
producing a figure that quietly omits it.

The test suite does not use these artifacts as its only subject.
`../../tests/fixtures/branchy.py` is a separate model with the same three awkward
properties — a data-dependent integer, a filter bank that is one convolution with
N channels, and a bypass that rejoins at a concat — so the torch-facing tests run
without bugarach, and no vendored copy of `tube` can drift from its original in
silence.

## What the figure says, and where each number comes from

Every quantity is resolved from `graph.json` by node id at render time. Nothing in
`spec.json` is a number:

| shown | from |
|---|---|
| `1149 parameters` | `{model.params}` |
| `max-pool, width fitted` | nothing — **see below**; the traced width is an initialisation |
| `26 ops, 12 learned params` | `{stage.nodes}`, `{stage.params}` |
| `kernel 257, area-normalised` | `{node:n0100.out_shape[2]}` |
| four lanes | `{node:n0116.out_shape[1]}` — the bank is **one** convolution with four output channels, so the count is a channel dimension, not a fork |
| `5 channels` | `{stage.out_shape[1]}` |
| `dilation 1 → 32` | `{node:n0149.constants.dilation}`, `{node:n0189.constants.dilation}` |

The lane labels `σ₁ … σ₄` are the agent's, and are indices rather than
measurements: the centre widths are fitted parameters, so no width is a fact
`graph.json` holds. `check` asserts there are exactly as many labels as the model
has channels.

## The legend, and what colour can and cannot say

Tony asked for an Inception-style figure for a stated reason — *"how much of the
model is convolution, at a glance"* — and the first version of this figure could
not answer it. The difference-of-Gaussian bank was gold and the dilated stack was
green, so the two convolutional stages of a model that is 99% convolution by
parameter read as unrelated things.

**Hue is now the family and value is the kind.** Both convolutional stages are
green and differ in value, which also keeps them apart in a greyscale print.

**Colour still cannot carry the proportion, and this is the honest limit.** The
Inception figure colours *layers*, so counting its boxes counts them. draughtsman
collapses 26 traced operations into one stage, so a box here is not a layer and no
amount of box area means anything. The legend is what answers the question: one
row per family present, generated from the stages actually drawn, with the share
counted off `graph.json`.

```
■ Convolution      38 ops, 1140 params
■ Pool / reduce     6 ops
■ Concat / join     1 op
■ Input / output    2 ops, 9 params
```

That is the answer to "how much is convolution" as a fact rather than an
impression, and every op and every parameter lands in exactly one row —
`tests/test_render.py` asserts the two totals against `graph.json`. Turn it on
with `"layout": {"legend": true}`; it is off by default, because a figure of one
colour family does not need a key.

## The pool width, and what a trace cannot see

This figure said **`max-pool, width 3`** until 2026-09-01, read straight from
`{node:n0031.constants.kernel_size}`. It was wrong, and nothing here could tell.

`tube` pools at `2·kmin + 1` where

```python
kmin = int(torch.exp(self.log_center.detach()).min().clamp(1, self.k))
```

and `log_center` is a **trained parameter**. At initialisation the centres are
1/2/4/8 samples, so `kmin` is 1 and the pool is 3 wide; the class docstring
records trained widths of ~4–7, which is a pool of **9–15**. The figure stated an
initialisation as though it were an architectural constant.

**Re-running the trace does not catch this.** `build_tube` initialises
`log_center` deterministically, so the baked `3` is perfectly reproducible. A
determinism check and an architecture check are different claims.

**Neither does walking `graph.json`.** `int()` on a tensor leaves tensor-land for
Python, and `2*kmin + 1` is then Python arithmetic torch never records, so the
width reaches `max_pool1d` as a bare `prim::Constant` — the same node kind a
literal `kernel_size=3` produces. Verified against torch 2.13.

What *is* available is that torch says so, and draughtsman was discarding it:

> `TracerWarning: Converting a tensor to a Python integer might cause the trace to
> be incorrect. We can't record the data flow of Python values, so this value will
> be treated as a constant in the future.`

`trace` now records those warnings in `graph.json` under `hazards`, and `check`
refuses to let a spec quote a `constants.*` reference while a hazard stands
unless the spec's `constants` block says why that one is architectural. This
spec declares two — both dilations, which `_dilated_stack` sets as `d = 2 ** i`
from the layer index — and quotes no width at all.

The general form is in [`../../DECISIONS.md`](../../DECISIONS.md); the model-side
write-up is bugarach's
`docs/todo/2026-09-01-a-traced-figure-cannot-tell-a-constant-from-an-initialisation.md`.
