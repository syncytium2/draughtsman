# draughtsman — specification

> **Written 2026-09-01, from a bugarach session.** Nothing here is built. This is
> what to build and why, with the measurements that decided each choice.
>
> **Not murderboarded** — an internal spec, not a document for outside readers. If
> any of it reaches one, review it first.

---

## 1. The problem this solves

A reader needs to understand a network's architecture. The two available families
of tool cannot give them that:

- **Graph tracers** (torchview, torchviz, `torch.export`-based viewers) record
  every operation. Complete, and unreadable — see §2 for the measurement.
- **Module enumerators** (pytorch-graph, most "summary" tools) list registered
  `nn.Module` children. Readable, and blind to anything a `forward()` does with
  functional ops — which for many interesting architectures is the architecture.

The missing step is choosing **which operations matter to a reader**. That is a
judgement, not a derivation, which is why no tracer supplies it and why
publication figures are still drawn by hand.

**draughtsman puts an agent in that step and nowhere else.**

## 2. The evidence, measured on one model

The subject was `bugarach`'s `tube` — a 1-D coordinated-event detector,
1,149 parameters. Its structure: a raster is max-pooled per cell, averaged across
cells into one brightness trace, then **fans out** into four difference-of-Gaussian
kernels *in parallel* while the raw trace **bypasses** them, and all five channels
**concatenate** into a six-layer dilated conv stack ending in a 1×1.

The fan-out, bypass and concat are the whole architecture. What each tool did:

| tool | version | result |
|---|---|---|
| torchview | 0.2.7 | Rendered. ~40 nodes including every `exp`, `clamp`, `div`, `view` from kernel construction. Output 2419 × 123 px — a strip. **Correct and unusable.** |
| pytorch-graph | 0.2.5 | Rendered `head.0`…`head.12` only. **Omitted the max-pool, the mean, all four DoG kernels, the bypass and the concat.** All shape fields empty (`Input: ()`). Boilerplate summary box. **Readable and wrong.** |
| visualtorch | latest on PyPI | `layered_view` → 993 × 13 px. Block height scales with channel count; this model has 1–8. |
| nn-SVG | LeNail (2019), *JOSS* 4(33):747 | Browser-only, no API. Linear stacks, image CNNs, no branching. Manual entry, so numbers would be typed. |
| Model Explorer | Google AI Edge | Requires PyTorch ExportedProgram. `torch.export` fails on this model (below). Also a viewer, not a figure generator. |

**Keep these artifacts.** They are the regression suite for "did we actually do
better", and they are in bugarach's darkroom at
`<darkroom>/bugarach/net-figure-options/`.

## 3. Which tracer works — measured, and it narrows fast

| tracer | result on `tube` |
|---|---|
| `torch.fx.symbolic_trace` | **Fails.** `TypeError: int() argument must be … not 'Proxy'` — the model computes an integer kernel width from a parameter. |
| `torch.export.export` | **Fails.** `GuardOnDataDependentSymNode: Could not guard on data-dependent expression` — same line, via `aten.item`. |
| `torch.jit.trace` | **Works. 200 nodes**, with shapes. |
| torchview (hooks on a real forward) | **Works.** |

**So the trace layer must be `torch.jit.trace` or hook-based, not `fx` or
`export`.** Any design that assumes `torch.export` excludes models with
data-dependent control flow, which includes the first model this tool was built
for. Do not discover this again.

## 4. Architecture

Three stages. **The split is the point and must not be blurred.**

```
  model ──▶ [1 TRACE] ──▶ graph.json ──▶ [2 ABSTRACT] ──▶ spec.json ──▶ [3 RENDER] ──▶ figure.svg
             facts          facts          judgement        judgement      deterministic
             (torch)                       (agent)          (committed)
```

### Stage 1 — trace. Facts only.

`torch.jit.trace` the model on a dummy input; emit every node with: id, op kind,
input ids, output shape, the owning module path where one exists, and the
parameter count attributable to it.

**Every number that ever appears in the final figure originates here.** Parameter
counts, tensor shapes, kernel widths, dilations, receptive fields.

### Stage 2 — abstract. Judgement only.

Give the agent `graph.json` and ask for a **layout spec**: which node ids collapse
into one stage, what that stage is called, its kind (for colour), and the edges —
including where the graph forks and rejoins.

**The agent never supplies a fact.** It does not write a parameter count, a shape,
or a name for a tensor dimension. It writes groupings, human names, and topology.
Every quantity in the rendered figure is looked up from `graph.json` by node id at
render time.

> This is the rule the whole design rests on. An agent that hallucinates a
> parameter count produces exactly the confident-and-wrong figure §2 records
> pytorch-graph producing, and the check in §5 would not catch it because the
> nodes would all still be covered.

### Stage 3 — render. Deterministic.

`spec.json` + `graph.json` → SVG. **Graphviz for layout** (`rankdir=LR`, a cluster
per parallel branch), because hand-computed coordinates are what this replaces —
the bugarach figure's first draft had its lane labels struck through by its own
edges, invisible in the source and obvious in the render.

Ship no styling in the SVG; inherit from the embedding page. **Fills must be
inline `style=`, not `fill=`** — a presentation attribute loses to a host
stylesheet rule, and a `.arch rect { fill: … }` in the embedding page repainted
every glyph one flat colour the first time this was tried.

## 5. The check that can fail

**Every traced node must be accounted for in exactly one stage.** Not zero, not
two.

This is the entire safety argument for letting an agent into the pipeline. It is
also precisely what pytorch-graph lacked: it dropped five whole stages and
reported success. A coverage assertion turns that class of failure from invisible
into a test failure.

- **Uncovered node** → error, naming the node and its op.
- **Node in two stages** → error.
- A node may be marked `elided` **explicitly**, with a reason recorded in the spec
  — that is a decision in a diff, not a silent loss.

What this check does **not** verify: that the names are good, the grouping is
natural, or the figure is legible. Those need a human. Say so in the output, so a
green check is never read as a good figure.

## 6. Artifacts and their contracts

| file | produced by | committed? | why |
|---|---|---|---|
| `graph.json` | stage 1 | yes | reproducibility; render reads facts from it |
| `spec.json` | stage 2 | **yes** | rendering needs no API call, and the agent's judgement is reviewable in a diff |
| `figure.svg` | stage 3 | yes | generate-commit-verify, as bugarach does for its viewer |

**A staleness test regenerates and asserts byte equality**, so a model change that
would move the figure turns CI red instead of shipping a figure of a model that no
longer exists. Note the tension to resolve: that test needs graphviz in CI, and
this estate dislikes tests that skip when a tool is absent — *"a skip is what
silence looks like when it is being careful."*

## 7. CLI

```
draughtsman trace   mypkg.nets:build_tube --input-shape 1,30,600 -o graph.json
draughtsman abstract graph.json -o spec.json      # agent; --dry-run prints the payload
draughtsman render   spec.json  -o figure.svg
draughtsman check    spec.json graph.json         # §5 coverage
```

`abstract` must work **without** an API key by printing the prompt payload for a
human or an agent session to answer and paste back. That keeps the tool usable
inside a coding-agent session, which is the primary internal use, and keeps the
API optional rather than load-bearing.

## 8. Open questions — decide before building, not during

1. **Where does the agent call live?** Anthropic API directly, or payload-in /
   spec-out so the surrounding agent session does it? The second is simpler, has
   no key handling, and matches how this will actually be used first.
2. **Graphviz as a dependency.** A system binary. Acceptable for a dev/regen path;
   the §6 staleness test drags it into CI. Alternative: keep our own SVG emitter
   and use graphviz only for coordinates.
3. **Is the spec hand-editable?** It should be — the agent's first pass will want
   correcting, and a human edit that survives regeneration is worth more than a
   better prompt.
4. **Multiple models per figure.** bugarach has six registered architectures that
   differ in small ways; a diff view between two specs may matter more than six
   separate figures.

## 9. First example, and the acceptance test

`examples/tube/` — the model from §2.

**Acceptance: the figure shows the fan-out to four kernels, the bypass, and the
concat.** All five tools in §2 failed that. Anything that draws the tube as a
linear stack has reproduced pytorch-graph's defect and is not done.

The current hand-laid figure — `<darkroom>/bugarach/net-figure-options/1-current-hand-laid.png`,
generated by `bugarach/tools/make_architecture_diagram.py` — is the bar to beat.
It is the only one of the five that got the topology right, and it is here as a
comparison, not as code to port: its content is derived from the model, and its
**coordinates are placed by hand**, which is the objection that started this repo.

## 10. What this is not

Not a debugger, not a viewer, not an activation visualiser. Model Explorer and
Netron do the interactive-exploration job and do it well. This produces **one
static figure a person can read**, and it is finished when a stranger looks at it
and describes the architecture correctly.
