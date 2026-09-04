# How far does the agent's grouping move between runs?

**2026-09-04. Five independent sessions, one prompt, ResNet, answer key withheld.**

Everything else this repository claims is checked. The agent supplies no facts;
coverage proves no traced operation was dropped; arrows are checked against the
trace; repetition counts, reference resolution, glyph axes and type size at print
width all have gates. About **the quality of the abstraction — the one step the
tool is named for — nothing.** Ten figures, judged good by one person, who also
wrote nine of the ten models.

"How do you know the agent is any good at this?" answered to *"a person looked at
them"*, in a repository whose argument is that an unchecked claim is decoration.

So this is the measurement.

## Method

`draughtsman abstract examples/gallery/resnet/graph.json` produces a 304-line
prompt: the rules, the JSON grammar, and the full traced node table for 52
operations. Five fresh agent sessions were each given that prompt alone and asked
to write a spec. Each could read the repository, run `draughtsman check`, render
its own answer and iterate — the real workflow. Each was forbidden to read
`examples/gallery/resnet/spec.json` or `figure.svg`, which are a previous answer
to the same question. None could see the others.

All five produced specs that pass `check` clean: 52 of 52 nodes placed, nothing
elided, every parameter reaching a drawn stage, no warnings.

Compared with [`tools/abstract_variance.py`](../../tools/abstract_variance.py).

## Result

| run | stages | edges | ARI vs the others |
|---|---|---|---|
| run-1 | 12 | 14 | 0.870 0.510 0.823 0.860 |
| run-2 | 12 | 14 | 0.870 0.555 0.879 0.991 |
| run-3 | **9** | 9 | 0.510 0.555 0.650 0.553 |
| run-4 | 11 | 11 | 0.823 0.879 0.650 0.886 |
| run-5 | 13 | 15 | 0.860 0.991 0.553 0.886 |

**Adjusted Rand index over all ten pairs: mean 0.758, min 0.510, max 0.991.**
Excluding the one run that cut materially coarser: **mean 0.885, min 0.823.**

The index asks whether two runs put the same *operations* together. It is
invariant to how many stages there are and to what they are called, which is the
invariance this question needs — `stem` and `stem conv` are the same judgement in
different words, and a name comparison would score that as total disagreement.
Chance is 0.0, identical is 1.0. See the tool's docstring for why an *unadjusted*
index would have scored two partitions that share nothing at about 0.85 and
reported this design as working no matter what came back.

## What is stable, and it is not what I expected

**Eighteen of 53 nodes were placed with exactly the same companions by all five
runs, and they are not scattered.** They are the input, the whole stem, and the
first two residual blocks — `in1`, `n0014`–`n0024`, `n0048`–`n0067`,
`n0077`–`n0096`. Every run drew the front of the network the same way.

Disagreement is concentrated in the repetitive middle. The most contested
operations — four distinct groupings across five runs — are the 32- and
64-channel blocks, which is exactly where the model stops introducing anything
new and a reader's needs genuinely differ.

**The load-bearing judgement was unanimous, and arrived at independently.** All
five runs opened the *first* residual block into a branch and an add, and left
the rest closed. All five gave the same reason unprompted: a ResNet whose skip
connection is invisible has reproduced the failure this tool exists to prevent,
and expanding all six blocks costs 16+ stages and breaks the legibility budget.

**All five considered `repeat` and all five refused it**, for the same structural
reason: with two blocks per width, any template tiles its stage exactly once, and
`check` correctly calls that not a repetition. Three of the five recorded the
refusal in a stage note rather than silently dropping it. One named the cost
plainly — the figure then never tells the reader how many blocks a collapsed box
holds.

The closest pair, run-2 and run-5 at 0.991, differ by **one node**: whether the
global average pool joins the flatten and linear in a `classifier` stage or
stands alone as `gap`. Their other twelve groupings are identical while six of
their stage names differ.

## What this does and does not license

**It supports:** the grouping is reproducible where it carries the figure's
meaning. Two readers handed two independent runs would take away the same
architecture — the same stem, the same residual pattern taught once, the same
refusal to imply a repetition the graph does not have.

**It does not support:** "the agent is deterministic here," or any claim about
stage count. Nine to thirteen stages is a real spread, and the coarsest run is
not wrong — it is a different, defensible answer to how much detail a reader
needs.

**Limits, stated because five runs is not many.** One model, one prompt, one
agent family, n=5. Every run was Claude Opus 5, so a systematic bias they share
is invisible to this method — this measures reproducibility, not correctness, and
a unanimous mistake would score 1.0. The runs could iterate against `check`, which
is the real workflow but means these are *checked* answers rather than first
drafts. ResNet is also the friendly case: it is regular, and its ambiguity is
about granularity rather than about what the operations mean. The measurement
worth doing next is `tube` or `whisper`, where it is not.

## Reproducing

```
tools/abstract_variance.py experiments/abstraction-variance/run-*.json
tools/abstract_variance.py --selftest
```
