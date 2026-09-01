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
| `max-pool, width 3` | `{node:n0031.constants.kernel_size}` |
| `26 ops, 12 learned params` | `{stage.nodes}`, `{stage.params}` |
| `kernel 257, area-normalised` | `{node:n0100.out_shape[2]}` |
| four lanes | `{node:n0116.out_shape[1]}` — the bank is **one** convolution with four output channels, so the count is a channel dimension, not a fork |
| `5 channels` | `{stage.out_shape[1]}` |
| `dilation 1 → 32` | `{node:n0149.constants.dilation}`, `{node:n0189.constants.dilation}` |

The lane labels `σ₁ … σ₄` are the agent's, and are indices rather than
measurements: the centre widths are fitted parameters, so no width is a fact
`graph.json` holds. `check` asserts there are exactly as many labels as the model
has channels.
