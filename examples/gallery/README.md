# The gallery — the models, and what they broke

> **Run 2026-09-01.** Everything in [`SPEC.md`](../../SPEC.md) and
> [`DECISIONS.md`](../../DECISIONS.md) was measured on one model: `tube`, 1,149
> parameters, one architecture family. This is the generalisation run. Each model
> below was chosen for a **specific way it could break the tool**, written down
> before it was traced.
>
> Two of them broke it. Both are fixed, both are pinned by tests, and the
> corrections are the most valuable thing here — read them first.

Every model is written out in full in [`models.py`](models.py) and
[`whisper_tiny.py`](whisper_tiny.py), so the gallery reproduces from this repo
alone: no torchvision, no downloads, no pinned third-party version. Weights are
random. These draw architectures, not trained models.

## The models

| model | family | verdict |
|---|---|---|
| [`mlp`](mlp/) | dense stack | held — and added nothing |
| [`lenet`](lenet/) | 2-D image CNN | held |
| [`dual`](dual/) | parallel branches, concat | held, best figure in the set |
| [`vae`](vae/) | sibling heads, external source | held; exposed the edge blind spot |
| [`resnet`](resnet/) | residual blocks ×6 | gap: repetition |
| [`unet`](unet/) | encoder–decoder, long skips | held topologically |
| [`transformer`](transformer/) | fused attention, ×4 blocks | gap: repetition |
| [`lstm`](lstm/) | fused recurrent op | gap: nothing to abstract |
| [`whisper`](whisper/) | encoder–decoder, cross-attention | **broke two things** |
| [`../tube/`](../tube/) | filter bank, bypass, dilated stack | the control |

Totals: 2,078 traced nodes, 506 substantive, one spec and one green coverage
check each, zero trace failures. These are computed from the committed graphs by
`tests/test_counts.py`, not typed here — they were typed here once, and adding a
model made every count in three READMEs wrong for a day.

## CASCADE, which was here and is not

For a day this gallery held an eleventh model: CASCADE, the calcium-to-spike-rate
network of Rupprecht et al., *Nature Neuroscience* 25:1471-1481 (2022). It was the
only one not written to break draughtsman — a tool in use, whose figure was wanted
for its own sake, and the first thing in this repo drawn because someone needed
the drawing.

It has moved to the project it was drawn for. Two reasons, and the second is the
one that decided it: CascadeTorch is GPL-3.0 and this repository is BSD-3, which
is latent while a repo is private and real on the day it is not.

One observation from it is worth keeping even though the model has gone, because
it is about how to caption a figure rather than about that network. CASCADE ships
dozens of pretrained models and **they do not differ in architecture** — what
differs is the ground-truth set, the frame rate the data was resampled to, and
the smoothing applied to the target. One figure serves all of them, and a caption
naming a single model would have been wrong about the rest. A figure's caption
makes a claim about scope, and scope is not something the trace can check.

## What broke, and what it cost

### 1. A tied weight was counted twice

The most serious finding, and Whisper produced it in one line:

```
warning: only 57100800 of 37184640 parameters could be attributed
```

Whisper's output projection **is** its token embedding. One tensor, two
`prim::GetAttr` nodes, both charged — so the model was reported as having 54%
more parameters than it has. **Coverage was green throughout**: every node was in
exactly one stage, and the figure would still have printed a total the model does
not have. That is precisely the confident-and-wrong number SPEC.md §4 exists to
prevent, arriving through a door the check does not watch.

Fixed in [`tracing.py`](../../src/draughtsman/tracing.py) by collecting every
substantive consumer of a parameter and charging the **earliest in trace order**.
That also decides *where* it is drawn: the 19.9M-entry table now appears at the
embedding, where a reader meets it, rather than at the matmul four hundred nodes
later. Pinned by `test_a_tied_weight_is_counted_once`.

### 2. One input, one shape

`trace` built a single dummy tensor, so every encoder–decoder, two-tower and
masked model was excluded — not by difficulty, by signature. `--input-shape` is
now repeatable with an optional `--dtype` per input:

```
draughtsman trace whisper_tiny:build_whisper_tiny \
    --input-shape 1,80,3000 --dtype float32 \
    --input-shape 1,12      --dtype int64 \
    -o whisper/graph.json
```

One shape still produces byte-identical output, so nothing written before this
means anything different. A model with several inputs has **no** singular
`{model.input_shape}` fact: asking for it raises rather than quietly describing
half the input.

## Gaps still open

**No `repeat` primitive — now closed, and a prediction made before the run held.**
ResNet has six identical blocks, the transformer four, Whisper four and four, and
every one of those figures spent its width opening block one and then collapsed
the rest into a box whose name said "three more identical blocks" — a number the
agent typed, spelled as a word so the bare-number heuristic could not see it.

`repeat` counts it instead. The agent names a **template**: the ordered stages
that draw one unit. draughtsman takes that unit's operation sequence and tiles it
against the collapsed stage's nodes; the count is how many times it tiles, and a
template that does not tile **exactly** is an error. It is `lanes` generalised —
the agent says "this is a repetition of that", the tool says how many — and
`{stage.repeat}` puts the verified number in the name.

**The prediction, written down before it was run:** Whisper would not tile,
because `dself` carried the two causal-mask slices and 123 does not divide by 43.
It did not tile. The check refused the spec, and **the check was right and the
grouping was wrong** — a causal mask enters the model once and has no business
inside one of four identical blocks. Moving the two slices upstream to the
embedding, where the sequence length is already being read, made 123 divide by 41
exactly and `drest` verify as three copies. A spec that has to be regrouped to
satisfy a check is the check doing its job.

One thing the check could not catch, worth knowing: moving those two nodes changed
which node the embedding stage exits through, so `{stage.out_shape}` silently
began resolving to the mask's `12×12` instead of the embedding's `1×12×384`. Every
reference still resolved, so nothing failed — it was caught by looking at the
figure. `{stage.out_shape}` is convenient and it is only as stable as a stage's
membership.

**ResNet still cannot use it, honestly.** Its later blocks project their identity
through a pointwise conv when the shape changes, so they are *not* copies of the
first — the tiling refuses, and it is correct to. Six blocks that a reader calls
identical are three pairs that differ.

**Everything is a horizontal strip.** The transformer renders 1937×247, an 8:1
ribbon; LeNet is 8:1 with nine stages. Layout is rank-by-longest-path with no
wrapping, so depth converts directly into width — the same defect the README
criticises torchview for, arrived at more slowly. Whisper escapes it only because
its two input rails give the figure a second row for free.

**Coverage checked placement, not edges — now closed, and it was backwards.**
The original finding here said the VAE "draws an edge the trace does not
contain". Building the assertion showed the opposite: **every drawn edge in every
committed figure was real.** What the VAE does is *omit* an edge the trace has —
`randn_like` reads the mean's shape, so `graph.json` records mean → noise, and
the figure does not draw it. The hole was never the arrows being false; it was
that nothing looked at the arrows at all.

`check` now derives the traced stage-to-stage topology from `tensor_inputs` and
compares it with the declared edges, in both directions and at different
severities:

- **An arrow with nothing under it is an error.** The figure would be asserting
  a data path the model does not have. It can be declared instead, with
  `"untraced": "<reason>"` on the edge — a decision in a diff, exactly as
  `elided` is for a dropped node. An empty reason buys nothing.
- **A traced path the figure omits is a warning.** It cannot be an error: many
  are shape dependencies no reader wants drawn (`raster → mean` divides by the
  raster's channel count; `tokens → pos` is a sequence length), and collapsing a
  repeated block legitimately buries fan-out inside one box. A check that cried
  wolf here would be turned off.

It found a real defect on its first run. Whisper's figure drew the audio
features into decoder block one and stopped, and **every** decoder block
cross-attends to that same audio. The figure understated the model. The edge is
drawn now.

**`lanes` can claim a parallelism that is not there.** Found by the Whisper figure
looking wrong. The first draft put six head lanes on the collapsed four-block
encoder — but that box is four blocks in *sequence*, and lanes assert parallelism.
The count resolved from a real fact and `check` passed, because nothing verifies
that a lane count is attached to a single sublayer. The committed spec carries
lanes only on the decoder's two real attention stages.

## The one thing this run actually taught

Five findings here look unrelated — a parameter counted twice, an arrow nobody
checked, a reference with two answers, a format the agent was never told about, a
badge derived in JavaScript. They are one shape, and it took five of them to see
it:

> **A quantity with a single correct value was either computed in two places and
> allowed to disagree, or computed in one place and never checked at all — and in
> every case the checks were green while the figure was wrong.**

Coverage cannot see either. It answers *was an operation dropped*, which is one
question, and each of these is a different one: is this number the model's, is
this arrow the graph's, can this reference be answered at all, does the agent even
know this field exists.

The habit that follows is written up as
[`DECISIONS.md`](../../DECISIONS.md) correction 5, and it is the most useful thing
in this repository: **one quantity, one implementation, and something that fails
when it cannot be answered.** Where a number has two possible sources, ask both
and refuse when they disagree rather than picking one. Where nothing checks a
claim, the claim is decoration until something does.

That is why `SPEC.md` §5's "the entire safety argument" is now corrected in three
places rather than left standing. Coverage is the first assertion. It was never
the only one it needed to be.

## What held

**`lanes` generalised across three families, which is the headline.** The
kernel-bank finding in DECISIONS.md was written about one model and read like a
quirk of it. It is not:

| model | the same idea | what the tracer hands you |
|---|---|---|
| `tube` | four DoG kernels | one `conv1d`, four output channels |
| `transformer` | four attention heads | one `_native_multi_head_attention` |
| `whisper` | six attention heads | written out — heads visible as a shape |

Three architectures, three different answers for the same idea, and `lanes` spans
all of them unmodified. The two transformer plates bracket that range on purpose:
`nn.MultiheadAttention` fuses, and Whisper's hand-written attention does not.

**The trace layer did not flinch.** Every model in the table above traced on the
first attempt, with every parameter attributed — the totals are stated once, at
the top, where something computes them. Whisper's 835
nodes and 37M parameters traced in under a second. Given that SPEC.md §3 reached
`torch.jit.trace` by eliminating two alternatives on a single model, that
generalisation was not guaranteed.

## Two smaller notes, left standing rather than worked around

**An edge label collided with a stage box.** Whisper's audio-features edge crosses
a rank boundary and its label was drawn under the cross-attention box that starts
there. Worked around by dropping a label the stage name already carried, but edge
labels have no collision handling at all.

**The bare-number heuristic has false positives.** The VAE's noise stage is named
`ε ~ N(0, I)`, and `check` warns that `0` is "a fact in the figure that did not
come from graph.json". It is a warning rather than an error, which is the right
severity, and it is **left in the committed spec** — a reader should see what the
heuristic costs.

## What torchview draws for the same model

`whisper/torchview.png` is committed beside `whisper/figure.svg`, and it is there for
the same reason `../2-torchview-traced.png` is: the bar this tool has to clear is an
artifact, not an assertion. It is torchview 0.2.7 on the same `build_whisper_tiny`,
called the way its own documentation calls it, with `depth` left at its default of 3:

```
pip install torch torchview                     # graphviz binaries also required
python - <<'EOF'
import torch, torchview
from whisper_tiny import build_whisper_tiny      # PYTHONPATH=examples/gallery
g = torchview.draw_graph(
    build_whisper_tiny().eval(),
    input_data=[torch.randn(1, 80, 3000), torch.randint(0, 51865, (1, 12))],
    graph_name="whisper_tiny", device="cpu")
g.visual_graph.graph_attr["dpi"] = "192"       # same drawing, twice the pixels
g.visual_graph.format = "png"
g.visual_graph.render(filename="examples/gallery/whisper/torchview", cleanup=True)
EOF
```

74 boxes, 96 edges, **547 × 4,896 points** — committed at `dpi=192`, so the file is
1,094 × 9,792 pixels and the page shows it at half that. Graphviz's `dpi` changes the
raster only: the layout is in points and does not move, so the committed file is the
same drawing at twice the density and stays legible when a reader zooms it. At `depth=10`, which is the level of detail
`whisper/figure.svg` accounts for, it is 234 boxes at **2,088 × 14,688 pixels**. Both
are correct: every box is a real operation carrying its real input and output shapes.
Neither fits on a page, and that is the whole of the gap — the same one
[`../README.md`](../README.md) measures on `tube`, arriving again on a model three
orders of magnitude larger.

Random weights change nothing about the layout, so the committed file is stable across
runs. It is a PNG rather than an SVG for the same reason the tube artifacts are: it is
evidence of what a tool produced, and a raster cannot be mistaken for something this
repository rendered. That choice is what makes density a question at all — every other
picture in this repository is vector and has no resolution to state.

## Reproducing

```
PYTHONPATH=src:examples/gallery
draughtsman trace    models:build_resnet --input-shape 1,3,32,32 -o examples/gallery/resnet/graph.json
draughtsman abstract examples/gallery/resnet/graph.json          # prints the prompt
draughtsman check    examples/gallery/resnet/spec.json examples/gallery/resnet/graph.json
draughtsman render   examples/gallery/resnet/spec.json -o examples/gallery/resnet/figure.svg
draughtsman ui       examples/                                    # all ten, in a browser
```

Stage 2 was answered by a coding-agent session, which is the primary intended use:
`abstract` prints a payload and makes no network call. The specs are committed and
hand-editable, so every grouping and every name is reviewable in a diff.

`../tube/graph.json` is **not** regenerated by this run — it comes from bugarach's
model, which is not in this repo, and `torch.jit.trace`'s value names are not
stable across torch releases (DECISIONS.md, corrections §3). It therefore predates
`input_shapes` and carries only the singular `input_shape`, which is what its spec
references.
