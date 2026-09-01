# draughtsman

**Readable architecture diagrams for PyTorch models.** The tracer supplies the
facts, an agent supplies the abstraction, and a coverage check proves nothing was
silently dropped.

> **Status: specification only. No code yet.** Read [`SPEC.md`](SPEC.md) — it
> carries the design, the measurements behind it, and the failure it exists to
> prevent. Written 2026-09-01 from a bugarach session that needed this figure and
> could not get one.

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

## Licence

BSD-3-Clause.
