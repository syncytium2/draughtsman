# The five failures, kept as the regression suite

These are not decoration. Five existing tools were tried on the same
1,149-parameter model, and they are the bar `draughtsman` has to clear. Two of the
five left an artifact worth keeping; both are below, alongside the hand-laid
figure they were measured against, which is not one of the five. See
[`../SPEC.md`](../SPEC.md) §2 for versions and measurements.

| file | tool | verdict |
|---|---|---|
| `1-current-hand-laid.png` | bugarach's own generator | The only one that got the topology right. Content derived from the model; **coordinates placed by hand**, which is why this repo exists. |
| `2-torchview-traced.png` | torchview 0.2.7 | Correct and unusable — ~40 nodes, a strip one pixel tall at page width. |
| *(no `3-`)* | visualtorch | **Never committed, and the gap is left visible rather than renumbered.** `layered_view` scaled block height by channel count and this model has 1–8, so it produced 993 × 13 pixels — a result that is a sentence, not a picture worth keeping. The numbering follows [`../SPEC.md`](../SPEC.md) §2, so closing the gap would break the correspondence. |
| `4-pytorchgraph-paper.png` | pytorch-graph 0.2.5 | **The instructive one.** Clean, styled, and it silently omitted the pooling, the mean, all four DoG kernels, the bypass and the concat. Empty shape fields. A reader would come away confident and wrong. |

The other three left nothing. visualtorch's result is described above; nn-SVG is
browser-only with no API and would have needed every number typed in by hand; and
Model Explorer never got as far as drawing, because `torch.export` cannot export
this model at all. All three are measured in [`../SPEC.md`](../SPEC.md) §2.

**Acceptance test:** the figure shows the fan-out to four kernels, the bypass, and
the concat. Every tool above except the first failed that.

## What draughtsman draws for the same model

[`tube/figure.svg`](tube/figure.svg), with the `graph.json` and `spec.json` it came
from and a note on where every number in it originates — see
[`tube/README.md`](tube/README.md). It clears the bar: the fan-out is four lanes,
the bypass is a dashed arc around them, the concat is a stage of its own, and the
twenty-six kernel-construction operations that made torchview a strip collapse
into one named block. The topology is the hand-laid figure's; the coordinates are
not placed by anyone.

## The generalisation run

[`gallery/`](gallery/) — the rest of the models, spanning the architecture
families named in its own table, each
chosen for a specific way it could break the tool, with the two things that did
break it and the four gaps still open. Read
[`gallery/README.md`](gallery/README.md) before trusting the design to generalise
from `tube` alone.
